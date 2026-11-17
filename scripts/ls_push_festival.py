#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把节日志字段（C/N 层文本 + O 层框）推进 Label Studio，建「AI 预填、人来改」项目。

与 ls_push_qwen.py 的区别：
  - 用节日志三层字段（场景层 C / 事件叙事层 N / 实体实例层 O），不是三层十二项
  - 实体框标签按新词表重命名（人物 / 器具与工具 / 材料与制作物 / 服饰与配饰 /
    装置与标识物 …），Qwen 旧标签在推送时映射过去
  - C/N 层结果直接落 TextArea + Choices，不再有「标签列/输出列/置信度列」三连

用法：
  python3 scripts/ls_push_festival.py --dry-run
  python3 scripts/ls_push_festival.py
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ls_push_qwen as base  # noqa: E402  复用 API 调用 / 建项目 / 任务导入 / 框时间线修正

ROOT = Path(__file__).resolve().parent.parent
CONFIG_XML = ROOT / "labelstudio" / "label_config_festival.xml"
PROJECT_TITLE = "节日志影像标注（AI 预填）"

# Qwen 旧标签 -> 节日志 O 层新标签。一对多时取语义最近的：
# 法器/仪式物、场所元素 都归到「装置与标识物」，设备和乐器归「器具与工具」。
BOX_LABEL_REMAP = {
    "人物": "人物",
    "服饰/头饰": "服饰与配饰",
    "工具": "器具与工具",
    "设备": "器具与工具",
    "乐器": "器具与工具",
    "材料": "材料与制作物",
    "法器/仪式物": "装置与标识物",
    "场所元素": "装置与标识物",
}

# 带词表的子键 -> LS Choices 控件名。键名与 qwen_label_festival.FIELDS 一致。
CHOICE_KEYS = {
    "C-4": {"shot": "c4_shot", "angle": "c4_angle", "move": "c4_move"},
    "C-5": {"lang": "c5_lang", "music": "c5_music"},
    "N-2": {"stage": "n2_stage", "rel": "n2_rel"},
    "N-3": {"org": "n3_org", "rel": "n3_rel"},
    "N-5": {"mode": "n5_mode"},
}
TEXT_KEYS = {"C-1": "c1", "C-2": "c2", "C-3": "c3", "C-4": "c4", "C-5": "c5",
             "N-1": "n1", "N-2": "n2", "N-3": "n3", "N-4": "n4", "N-5": "n5"}


def answer_to_result(answer: dict) -> list[dict]:
    """把节日志 JSON 答案转成 LS result 列表（TextArea + Choices）。"""
    result = []
    for fid, ctrl in TEXT_KEYS.items():
        item = answer.get(fid) or {}
        text = str(item.get("out") or "").strip()
        if text and text != "无法判断":
            result.append({"type": "textarea", "from_name": ctrl, "to_name": "video",
                           "value": [text]})
        for sub, from_name in CHOICE_KEYS.get(fid, {}).items():
            v = item.get(sub) or []
            if isinstance(v, str):
                v = [v]
            v = [x for x in v if x and x != "无法判断"]
            if v:
                result.append({"type": "choices", "from_name": from_name,
                               "to_name": "video", "value": {"choices": v}})
    return result


def boxes_to_result(boxes_jsonl: Path) -> dict:
    """读框缓存并改成节日志标签。"""
    box_map = {}
    for line in boxes_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        items = rec.get("result") or []
        for it in items:
            if it.get("type") == "videorectangle":
                it["from_name"] = "tag"           # 必须指向 Labels 控件
                labs = it["value"].get("labels") or []
                it["value"]["labels"] = [BOX_LABEL_REMAP.get(l, l) for l in labs]
        box_map[rec["clip"]] = items
    fixed = sum(base.normalize_box_timeline(v) for v in box_map.values())
    print(f"读到 {len(box_map)} 条片段的框："
          + "、".join(f"{k[:16]}={len(v)} 框" for k, v in box_map.items()))
    print(f"帧号按 {base.CFG_FPS}fps 重算，修正 {fixed} 个关键帧；标签已映射到节日志词表")
    return box_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / ".tmp" / "qwen_festival_run1.jsonl"))
    ap.add_argument("--boxes", default=str(ROOT / ".tmp" / "boxes23.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    xml = CONFIG_XML.read_text(encoding="utf-8")
    box_map = boxes_to_result(Path(a.boxes)) if a.boxes else {}

    records = [json.loads(l) for l in Path(a.run).read_text(encoding="utf-8").splitlines()
               if l.strip()]
    clips = [r["clip"] for r in records]
    print(f"读到 {len(records)} 条 Qwen 结果：{', '.join(clips)}\n")

    base.PROJECT_TITLE = PROJECT_TITLE       # get_or_create_project 按标题查重
    pid = base.get_or_create_project(xml, a.dry_run)
    base.ensure_storage(pid, a.dry_run)
    base.import_tasks(pid, clips, a.dry_run)
    if a.dry_run:
        for rec in records[:2]:
            res = answer_to_result(rec.get("answer") or {})
            print(f"[dry] {rec['clip']} -> {len(res)} 条结果")
        print("\n[dry] 以上为预演，未写库。")
        return

    mapping = base.task_map(pid)
    print(f"项目内任务 {len(mapping)} 条")
    print("\n推送预标注：")
    done = skipped = 0
    for rec in records:
        clip = rec["clip"]
        tid = mapping.get(clip)
        if not tid:
            print(f"  [跳过] 找不到任务：{clip}")
            skipped += 1
            continue
        result = answer_to_result(rec.get("answer") or {})
        n_text = len(result)
        if clip in box_map:
            result = result + box_map[clip]
        if not result:
            skipped += 1
            continue

        # 幂等：先删本流程之前推的预标注
        code, old = base.call("GET", f"/api/predictions?task={tid}&page_size=50")
        items = old if isinstance(old, list) else (old or {}).get("results", [])
        for p in items:
            if str(p.get("model_version") or "").startswith("qwen3-vl-plus"):
                base.call("DELETE", f"/api/predictions/{p['id']}")

        payload = {"task": tid, "result": result,
                   "model_version": "qwen3-vl-plus-festival", "score": 0.7}
        code, body = base.call("POST", "/api/predictions/", payload)
        if code in (200, 201):
            done += 1
            print(f"  [ok] {clip} -> task {tid}，{n_text} 条文本 + {len(result) - n_text} 条框")
        else:
            print(f"  [失败 {code}] {clip}\n    {str(body)[:300]}")

    print(f"\n完成：{done} 条成功，{skipped} 条跳过")
    print(f"\n打开：{base.API.rstrip('/')}/projects/{pid}/data")
    print("推送后记得跑 pred2annot.py 把预测转成标注（prediction 是只读的）：")
    print(f"  python3 scripts/pred2annot.py --project {pid}")


if __name__ == "__main__":
    main()
