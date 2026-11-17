#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Qwen 的十二项标注结果推进 Label Studio，做成「AI 预填、人来改」的项目。

做三件事：
  1. 用 labelstudio/label_config_t12.xml 建一个十二项文本标注项目
  2. 登记本地文件存储，导入 4 条测试片段（走 /data/local-files/，不重复占空间）
  3. 把 .tmp/qwen4_runN.jsonl 里的 answer 转成 LS 的 prediction 挂到对应任务上

为什么要转：Qwen 输出是纯文本结构 {T2-4: {label:[...], out:"...", conf:"高"}}，
而 LS 的 prediction 必须是 region 形式的 result 列表，两边形状完全不同。

几个坑：
  - Qwen 的 label 字段是 Python 列表的 str（"['传统戏剧']"），不是 JSON，得用
    ast.literal_eval 解析，json.loads 会直接报错。
  - 标签不在词表里时 LS 会拒收整条 prediction，所以先过滤；被滤掉的写进正文，
    信息不丢（T3-1 没有词表，本来就该写正文）。
  - T2-1 的次要模式 / T2-4 的次选门类 / T2-3 的性别，配置里没有独立控件，
    统一并进正文的【补充】行。

用法：
  python3 scripts/ls_push_qwen.py --dry-run          # 只打印，不写库
  python3 scripts/ls_push_qwen.py                    # 真推
  python3 scripts/ls_push_qwen.py --run .tmp/qwen4_run3.jsonl
"""

import argparse
import ast
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_XML = ROOT / "labelstudio" / "label_config_t12.xml"
SPEC = ROOT / "refs" / "annotation_spec_v4.json"
VIDEOS = Path("/Users/lixin/video-vl")

API = os.getenv("LS_URL", "http://ich.8.160.123.92.nip.io")
TOKEN = os.getenv("LS_TOKEN", "81ee86fd05b977f9deacae689afccc72e866c3e1")
PROJECT_TITLE = "非遗影像 · 三层十二项（Qwen 预标注）"
REMOTE_CLIPS = "clips4"          # 服务器 data/ 下的子目录
LOCAL_ROOT_REMOTE = "/root/project/ich-prelabel/data"

CONF = ["高", "中", "低"]

# label_config 里 <Video frameRate="25">，LS 按这个值把帧号换算成时间。
# 但素材 fps 不统一（实测有一条是 44.5），照原文件的 fps 编帧号，LS 会按 25 解读，
# 框就会整体提前或滞后。所以统一用每个关键帧的 time（秒）重算帧号，
# 让帧号落在 LS 假定的那条时间轴上。
CFG_FPS = 25

# 配置里没有独立控件、要并进正文的附加字段
EXTRA_LABEL = {
    "aux": "次要模式",
    "alt": "次选门类",
    "gender": "角色性别",
}


# ---------------------------------------------------------------- HTTP
def call(method, path, payload=None, timeout=120):
    url = API.rstrip("/") + path
    data = None
    headers = {"Authorization": f"Token {TOKEN}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]
    except Exception as e:                                  # 网络层
        return 0, str(e)


def ok(method, path, payload=None, timeout=120):
    code, body = call(method, path, payload, timeout)
    if code not in (200, 201, 204):
        raise SystemExit(f"[{code}] {method} {path}\n{body}")
    return body


# ---------------------------------------------------------------- 词表
def load_vocab() -> dict:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    out = {}
    for t in spec["tasks"]:
        key = t.get("label_vocab")
        if not key:
            out[t["id"]] = []
        elif key == "genre_taxonomy":
            out[t["id"]] = list(spec.get("genre_taxonomy") or [])
        else:
            items = ((spec.get("vocab") or {}).get(key) or {}).get("items") or []
            out[t["id"]] = [it["name"] for it in items if it.get("name")]
    return out


def as_list(v):
    """Qwen 的 label 是 Python 列表的字符串表示，不是 JSON。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    s = str(v).strip()
    if not s:
        return []
    if s[0] in "[(":
        try:
            got = ast.literal_eval(s)
            if isinstance(got, (list, tuple)):
                return [str(x) for x in got]
        except (ValueError, SyntaxError):
            pass
    return [s]


# ---------------------------------------------------------------- 转换
def answer_to_result(answer: dict, vocab: dict, stat: dict) -> list:
    """一条片段的 12 项回答 -> LS 的 result 列表。"""
    result = []
    for tid, fields in answer.items():
        if not isinstance(fields, dict):
            continue
        v = vocab.get(tid, [])
        text = (fields.get("out") or "").strip()

        raw_labels = as_list(fields.get("label"))
        keep, drop = [], []
        for lab in raw_labels:
            if not v:                       # 该项本来就没有词表（T1-*、T3-1）
                drop.append(lab)
            elif lab in v:
                keep.append(lab)
            else:
                drop.append(lab)

        if v and keep:
            result.append({
                "from_name": f"{tid}_label", "to_name": "video", "type": "choices",
                "value": {"choices": keep},
            })
        if v and drop:
            stat["dropped"].extend((tid, d) for d in drop)

        extras = []
        # T2-3 的 gender 是和 label 等长、按下标对齐的（['角色[女]','不限',...]），
        # 单独列出来没人看得懂，得跟角色名配对；'角色[女]' 的前缀也去掉。
        gender_vals = as_list(fields.get("gender"))
        paired_gender = False
        if tid == "T2-3" and gender_vals and len(gender_vals) == len(raw_labels) and raw_labels:
            pairs = []
            for lab, g in zip(raw_labels, gender_vals):
                g = str(g).replace("角色", "").strip() or "不限"
                pairs.append(lab + (g if g.startswith("[") else f"（{g}）"))
            extras.append("角色性别：" + "、".join(pairs))
            paired_gender = True

        for key, title in EXTRA_LABEL.items():
            if paired_gender and key == "gender":
                continue
            vals = as_list(fields.get(key))
            if vals:
                extras.append(f"{title}：" + "、".join(vals))
        if not v and drop:
            # 没有词表的项，标签就是正文的一部分
            extras.insert(0, "标签：" + "、".join(drop))
        elif drop:
            extras.append("词表外：" + "、".join(drop))

        if extras:
            text = (text + "\n【补充】" + "；".join(extras)).strip()

        if text:
            result.append({
                "from_name": f"{tid}_out", "to_name": "video", "type": "textarea",
                "value": {"text": [text]},
            })

        conf = (fields.get("conf") or "").strip()
        if conf in CONF:
            result.append({
                "from_name": f"{tid}_conf", "to_name": "video", "type": "choices",
                "value": {"choices": [conf]},
            })
        elif conf:
            stat["bad_conf"].append((tid, conf))
    return result


# ---------------------------------------------------------------- 项目
def get_or_create_project(xml: str, dry: bool) -> int:
    body = ok("GET", "/api/projects?page_size=100")
    items = body.get("results", body) if isinstance(body, dict) else body
    for p in items:
        if p.get("title") == PROJECT_TITLE:
            print(f"复用已有项目 id={p['id']}")
            return p["id"]
    if dry:
        print(f"[dry] 将创建项目「{PROJECT_TITLE}」")
        return -1
    created = ok("POST", "/api/projects", {"title": PROJECT_TITLE, "label_config": xml})
    print(f"已创建项目 id={created['id']}")
    return created["id"]


def update_config(pid: int, xml: str, dry: bool):
    """把 label_config 换成当前 XML。

    只在你明确要求时调用：改配置会让已有标注里对不上的标签失效，
    所以不做「悄悄自动更新」，免得把人工标注搞坏。
    """
    if dry:
        print(f"[dry] 将更新项目 {pid} 的 label_config")
        return
    ok("PATCH", f"/api/projects/{pid}", {"label_config": xml})
    print(f"已更新项目 {pid} 的 label_config")


def ensure_storage(pid: int, dry: bool):
    path = f"{LOCAL_ROOT_REMOTE}/{REMOTE_CLIPS}"
    if pid < 0:                       # dry-run 时项目还没建，别去查
        print(f"[dry] 将登记本地存储 {path}")
        return
    body = ok("GET", f"/api/storages/localfiles?project={pid}")
    items = body if isinstance(body, list) else body.get("results", [])
    for s in items:
        if s.get("path") == path:
            print(f"本地存储已存在 id={s['id']} -> {path}")
            return
    if dry:
        print(f"[dry] 将登记本地存储 {path}")
        return
    s = ok("POST", "/api/storages/localfiles", {
        "project": pid, "path": path, "title": "Qwen 测试片段",
        "regex_filter": ".*", "use_blob_urls": False,
    })
    print(f"已登记本地存储 id={s['id']} -> {path}")


def import_tasks(pid: int, clips: list, dry: bool):
    """导入片段任务。已存在的跳过——LS 的 /import 不去重，重跑一次就翻一倍。"""
    if pid > 0:
        have = set(task_map(pid))
        fresh = [c for c in clips if c not in have]
        if len(fresh) != len(clips):
            print(f"跳过已存在的 {len(clips) - len(fresh)} 条，新增 {len(fresh)} 条")
    else:
        fresh = clips
    if dry:
        print(f"[dry] 将导入 {len(fresh)} 条任务")
        return
    if not fresh:
        print("任务已齐，无需导入")
        return
    tasks = [{"data": {"video": f"/data/local-files/?d={REMOTE_CLIPS}/{name}",
                       "clip": name}} for name in fresh]
    r = ok("POST", f"/api/projects/{pid}/import", tasks, timeout=300)
    print(f"导入完成：task_count={r.get('task_count')}")


def task_map(pid: int) -> dict:
    """{clip 文件名: task_id}"""
    out, page = {}, 1
    while True:
        body = ok("GET", f"/api/tasks?project={pid}&page_size=100&page={page}")
        batch = body.get("tasks") if isinstance(body, dict) else body
        if not batch:
            break
        for t in batch:
            d = t.get("data") or {}
            name = d.get("clip") or (d.get("video") or "").split("/")[-1]
            out[name] = t["id"]
        if isinstance(body, dict) and len(out) >= body.get("count", 0):
            break
        page += 1
        if page > 50:
            break
    return out


def normalize_box_timeline(results: list, cfg_fps: int = CFG_FPS) -> list:
    """把框的帧号重算到标注配置假定的帧率上。

    qwen_boxes.py 是按素材真实 fps 编帧号的（44.5fps 的片子帧号会到 3174），
    而 label_config 写的是 frameRate="25" —— 两边不一致时 LS 会把框放在错误的时间点。
    关键帧里已经存了 time（秒），按 25fps 反算即可，与真实 fps 无关。
    """
    changed = 0
    for r in results:
        v = r.get("value") or {}
        seq = v.get("sequence") or []
        if not seq:
            continue
        # 没有 time 的老数据，只能按原帧号比例推
        base = seq[0].get("time")
        for kf in seq:
            t = kf.get("time")
            if t is None:
                if base is None:
                    continue
                t = kf["frame"] / float(v.get("framesCount") or 1) * float(v.get("duration") or 0)
            new_frame = int(round(float(t) * cfg_fps))
            if new_frame != kf.get("frame"):
                changed += 1
            kf["frame"] = new_frame
        dur = float(v.get("duration") or 0)
        if dur:
            v["framesCount"] = int(round(dur * cfg_fps))
        v["sequence"] = sorted(seq, key=lambda x: x["frame"])
    return changed


def push_predictions(pid: int, mapping: dict, records: list, vocab: dict, dry: bool,
                     boxes: dict = None, model_version: str = "qwen3-vl-plus-run4"):
    stat = {"dropped": [], "bad_conf": []}
    done = skipped = 0
    for rec in records:
        clip = rec["clip"]
        tid = mapping.get(clip)
        if not tid:
            print(f"  [跳过] 找不到任务：{clip}")
            skipped += 1
            continue
        result = answer_to_result(rec.get("answer") or {}, vocab, stat)
        n_text = len(result)
        if boxes and clip in boxes:
            result = result + boxes[clip]
        if not result:
            print(f"  [跳过] 空结果：{clip}")
            skipped += 1
            continue
        n_box = len(result) - n_text

        if dry:
            print(f"  [dry] {clip} -> task {tid}, {n_text} 条文本 + {n_box} 条框")
            done += 1
            continue

        # 幂等：先删掉本流程之前推的预标注，避免同一个任务挂两条 prediction
        old = call("GET", f"/api/predictions?task={tid}&page_size=50")
        if old[0] == 200:
            items = old[1] if isinstance(old[1], list) else (old[1] or {}).get("results", [])
            for p in items:
                if str(p.get("model_version") or "").startswith("qwen3-vl-plus"):
                    call("DELETE", f"/api/predictions/{p['id']}")

        payload = {"task": tid, "result": result, "model_version": model_version,
                   "score": 0.7}
        code, body = call("POST", "/api/predictions/", payload)
        if code in (200, 201):
            done += 1
            print(f"  [ok] {clip} -> task {tid}，{n_text} 条文本 + {n_box} 条框")
        else:
            print(f"  [失败 {code}] {clip}\n    {str(body)[:300]}")
    return done, skipped, stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / ".tmp" / "qwen4_run4.jsonl"))
    ap.add_argument("--videos", default=str(VIDEOS))
    ap.add_argument("--boxes", help="qwen_boxes.py 产出的 boxes jsonl，会把框并进同一条 prediction")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--update-config", action="store_true",
                    help="把项目的 label_config 换成当前 XML（会改结构，慎用）")
    a = ap.parse_args()

    xml = CONFIG_XML.read_text(encoding="utf-8")
    vocab = load_vocab()

    box_map = {}
    if a.boxes:
        for line in Path(a.boxes).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                items = rec.get("result") or []
                # from_name 必须指向 Labels 控件（tag）。早期产物写成了 box
                # （VideoRectangle 的名字），LS 找不到控件，框能显示但改不了标签。
                for it in items:
                    if it.get("type") == "videorectangle":
                        it["from_name"] = "tag"
                box_map[rec["clip"]] = items
        fixed = sum(normalize_box_timeline(v) for v in box_map.values())
        print(f"读到 {len(box_map)} 条片段的框："
              + "、".join(f"{k[:16]}={len(v)} 框" for k, v in list(box_map.items())[:6]))
        print(f"帧号按 {CFG_FPS}fps 重算，修正 {fixed} 个关键帧")

    records = [json.loads(l) for l in Path(a.run).read_text(encoding="utf-8").splitlines() if l.strip()]
    clips = [r["clip"] for r in records]
    print(f"读到 {len(records)} 条 Qwen 结果：{', '.join(clips)}\n")

    missing = [c for c in clips if not (Path(a.videos) / c).exists()]
    if missing:
        raise SystemExit(f"视频不存在：{missing}")

    pid = get_or_create_project(xml, a.dry_run)
    if a.update_config:
        update_config(pid, xml, a.dry_run)
    ensure_storage(pid, a.dry_run)
    import_tasks(pid, clips, a.dry_run)

    if a.dry_run:
        print("\n[dry] 以上为预演，未写库。")
        return

    mapping = task_map(pid)
    print(f"项目内任务 {len(mapping)} 条")
    print("\n推送预标注：")
    mv = "qwen3-vl-plus-run4+grounding" if box_map else "qwen3-vl-plus-run4"
    done, skipped, stat = push_predictions(pid, mapping, records, vocab, False,
                                           boxes=box_map, model_version=mv)

    print(f"\n完成：{done} 条成功，{skipped} 条跳过")
    if stat["dropped"]:
        uniq = sorted({f"{t}:{d}" for t, d in stat["dropped"]})
        print(f"词表外标签 {len(uniq)} 个（已并入正文）：")
        for u in uniq[:15]:
            print("   ", u)
    if stat["bad_conf"]:
        print(f"非法置信度：{stat['bad_conf']}")
    print(f"\n打开：{API.rstrip('/')}/projects/{pid}/data")


if __name__ == "__main__":
    main()
