#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端自检：从「视频可读」到「预标注可编辑」再到「导出格式正确」跑一遍。

不做任何破坏性改动 —— 模拟人工接受预标注后会把测试产生的标注删掉。

用法：
    export LS_URL=http://127.0.0.1:8080 LS_TOKEN=xxxx
    python scripts/e2e_test.py
"""

import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = os.getenv("LS_URL", "http://127.0.0.1:8080")
TOKEN = os.getenv("LS_TOKEN")
PROJECT = int(os.getenv("LS_PROJECT", "2"))
ROOT = Path(__file__).resolve().parent.parent

if not TOKEN:
    sys.exit("请设置 LS_TOKEN")
H = {"Authorization": f"Token {TOKEN}"}

PASS, FAIL = "  [OK]  ", "  [FAIL]"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{PASS if ok else FAIL}{name}" + (f"  {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


# ---------------------------------------------------------------- 1. 服务与鉴权
section("1. 服务与鉴权")

r = requests.get(f"{BASE}/api/projects", headers=H, timeout=30)
check("API 鉴权", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code != 200:
    sys.exit("鉴权失败，后续测试无意义")

projects = r.json()
plist = projects.get("results", []) if isinstance(projects, dict) else projects
pid = next((p["id"] for p in plist if p["id"] == PROJECT), None)
check(f"项目 {PROJECT} 存在", pid is not None)

# ---------------------------------------------------------------- 2. 视频可读
section("2. 视频能否经 /data/local-files/ 读取")

r = requests.get(f"{BASE}/api/tasks", headers=H,
                 params={"project": PROJECT, "page_size": 5}, timeout=60)
tasks = r.json()
tl = tasks.get("tasks", []) if isinstance(tasks, dict) else tasks
check("能列出任务", len(tl) > 0, f"{len(tl)} 条（分页前 5）")

sample = tl[0]
video_url = sample["data"]["video"]
full = f"{BASE}{video_url}" if video_url.startswith("/") else video_url
rv = requests.get(full, headers=H, stream=True, timeout=30)
size = rv.headers.get("Content-Length", "?")
check("视频 URL 可访问", rv.status_code == 200,
      f"HTTP {rv.status_code}, {int(size) / 1048576:.1f} MB" if size != "?" else f"HTTP {rv.status_code}")
rv.close()

# ---------------------------------------------------------------- 3. 预标注数据
section("3. 预标注数据完整性")

r = requests.get(f"{BASE}/api/predictions", headers=H,
                 params={"project": PROJECT, "page_size": 500}, timeout=60)
pd = r.json()
preds = pd.get("results", []) if isinstance(pd, dict) else pd
check("存在预标注", len(preds) > 0, f"{len(preds)} 条")

bad_schema, bad_coord, bad_frame = [], [], []
tracks_total = 0
for p in preds:
    for res in p.get("result", []):
        tracks_total += 1
        v = res["value"]
        if res.get("type") != "videorectangle" or v.get("framesCount", 0) <= 0:
            bad_schema.append(res.get("id"))
        seq = v.get("sequence", [])
        frames = [s["frame"] for s in seq]
        if frames and (min(frames) < 1 or max(frames) > v["framesCount"]):
            bad_frame.append(res.get("id"))
        for s in seq:
            if not (0 <= s["x"] <= 100 and 0 <= s["width"] <= 100
                    and 0 <= s["y"] <= 100 and 0 <= s["height"] <= 100):
                bad_coord.append(res.get("id"))
                break

check("type/framesCount 合法", not bad_schema, f"{tracks_total} 条轨迹")
check("帧号在 1..framesCount 内", not bad_frame)
check("坐标是 0-100 百分比且未越界", not bad_coord)

# ---------------------------------------------------------------- 4. 质量指标
section("4. 预标注质量指标")

cover_pcts, jitters = [], []
for p in preds:
    fc = 0
    for res in p.get("result", []):
        v = res["value"]
        fc = v.get("framesCount", 0)
        seq = sorted(v["sequence"], key=lambda s: s["frame"])
        if len(seq) < 2:
            continue
        # 位置抖动：相邻记录帧之间框中心位移的中位数（占画面宽高的百分比）
        moves = []
        for a, b in zip(seq, seq[1:]):
            dx = abs(b["x"] + b["width"] / 2 - (a["x"] + a["width"] / 2))
            dy = abs(b["y"] + b["height"] / 2 - (a["y"] + a["height"] / 2))
            moves.append((dx + dy) / 2)
        moves.sort()
        jitters.append(moves[len(moves) // 2])
        # 覆盖率：该轨迹跨越的帧数 / 总帧数
        cover_pcts.append((seq[-1]["frame"] - seq[0]["frame"] + 1) / max(fc, 1))

if cover_pcts:
    avg_cover = sum(cover_pcts) / len(cover_pcts)
    avg_jit = sum(jitters) / len(jitters)
    print(f"    轨迹平均跨越时长占比 : {avg_cover * 100:.1f}%")
    print(f"    相邻帧中心位移中位数 : {avg_jit:.2f}% 画面")
    check("轨迹跨越时长合理（>5%）", avg_cover > 0.05, f"{avg_cover * 100:.1f}%")
    check("框抖动可控（<8% 画面）", avg_jit < 8.0, f"{avg_jit:.2f}%")

labels = Counter()
for p in preds:
    for res in p.get("result", []):
        labels[res["value"]["labels"][0]] += 1
print("\n    标签分布：")
for lab, n in labels.most_common():
    print(f"      {lab:<12} {n} 条")
check("标签不止人物一类", len(labels) > 1, f"{len(labels)} 类")

# ---------------------------------------------------------------- 5. 端到端编辑
section("5. 端到端：模拟人工接受预标注 → 导出 → 回滚")

# 挑一条有内容的任务
target = None
for p in preds:
    if len(p.get("result", [])) >= 3:
        target = p
        break
if target is None:
    check("找到可测试的任务", False)
else:
    tid = target["task"]
    check(f"选用 task {tid} 做编辑测试", True, f"{len(target['result'])} 条轨迹")

    # 模拟人工接受：把 prediction 的 result 原样写成 annotation
    payload = {
        "result": target["result"],
        "was_cancelled": False,
        "ground_truth": False,
        "lead_time": 12.5,
        "task": tid,
    }
    ra = requests.post(f"{BASE}/api/tasks/{tid}/annotations/",
                       headers=H, json=payload, timeout=120)
    check("能提交人工标注（接受预标注）", ra.status_code in (200, 201),
          f"HTTP {ra.status_code}")
    ann_id = ra.json().get("id") if ra.status_code in (200, 201) else None

    if ann_id:
        rg = requests.get(f"{BASE}/api/tasks/{tid}", headers=H, timeout=60)
        got = rg.json()
        n_ann = len(got.get("annotations", []))
        check("任务上能读回标注", n_ann >= 1, f"{n_ann} 条 annotation")

        # 导出整项目，确认 predictions 与 annotations 都在
        rd = requests.get(f"{BASE}/api/projects/{PROJECT}/export",
                          headers=H, params={"exportType": "JSON"}, timeout=300)
        check("项目可导出", rd.status_code == 200, f"HTTP {rd.status_code}")
        if rd.status_code == 200:
            exported = rd.json()
            has_pred = has_ann = 0
            for t in exported:
                if t.get("predictions"):
                    has_pred += 1
                if t.get("annotations"):
                    has_ann += 1
            check("导出含 predictions", has_pred > 0, f"{has_pred} 条任务")
            check("导出含 annotations", has_ann > 0, f"{has_ann} 条任务（测试标注）")
            sample_exp = next((t for t in exported if t.get("annotations")), None)
            if sample_exp:
                a0 = sample_exp["annotations"][0]
                keys = {"result", "was_cancelled", "ground_truth"}
                check("导出标注字段完整", keys.issubset(a0.keys()),
                      f"{sorted(keys & set(a0.keys()))}")

        # 回滚：删掉测试产生的标注
        rdel = requests.delete(f"{BASE}/api/annotations/{ann_id}",
                               headers=H, timeout=60)
        check("测试标注已回滚", rdel.status_code in (200, 204), f"HTTP {rdel.status_code}")

# ---------------------------------------------------------------- 6. 标注页
section("6. 标注页可访问（不在此处验证，见说明）")

print("  跳过 —— 浏览器那套走的是 Django 表单登录 + CSRF cookie，")
print("  从外部用 requests 模拟会撞到 CSRF/Host 检查（403/404），")
print("  那是脚本的局限而非服务故障。改用服务端内部验证：\n")
print("    echo \"exec(open('scripts/check_ui.py').read())\" | \\")
print("      label-studio shell --database .tmp/lsdata/ls.sqlite3\n")
print("  该脚本验证：登录页 -> 表单登录(302) -> 首页/项目列表/数据管理页/标注页均 200")

# ---------------------------------------------------------------- 汇总
section("结果")
ok_n = sum(1 for x in results if x)
print(f"通过 {ok_n}/{len(results)}")
if ok_n == len(results):
    print("全部通过 —— 从视频读取到预标注编辑再到导出，整条链路是通的。")
else:
    print("有失败项，见上面对应的 [FAIL] 行。")
sys.exit(0 if ok_n == len(results) else 1)
