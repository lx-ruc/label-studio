"""从甲方标注表中抽取「三层十二项」规范，落成机器可读的 JSON 配置。

单一事实来源：所有 prompt 构建、评测打分都读这个配置，避免手抄走样。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path("/Users/lixin/WorkBuddy/2026-10-24-20-33-54")
SRC = ROOT / "refs" / "20260608影片片段标注.xlsx"
OUT = ROOT / "refs" / "annotation_spec_v4.json"

# 十二项任务：编号 -> (任务名, 层级, 词表 sheet 名, 词表锚点行, 截止行)
# 词表锚点 = 该分组标题所在行（1-based），其下一行是表头「编号/分类名称/判断说明/版本标记」
VOCAB_GROUPS = [
    ("T2-1", "核心叙事模式", "分类词表（第二层）", 3),
    ("T2-2", "社会空间",     "分类词表（第二层）", 18),
    ("T2-3", "社会角色",     "分类词表（第二层）", 34),
    ("T2-3@gender", "性别属性标签", "分类词表（第二层）", 49),
    ("T3-2", "整体氛围与情感", "分类词表（第三层）", 3),
    ("T3-3", "隐性社会价值",  "分类词表（第三层）", 15),
    ("T3-4", "社会互动关系",  "分类词表（第三层）", 26),
]

# 评测表列索引（0-based）
COLS = {
    "film": 0, "start": 1, "end": 2, "dur_s": 3, "dur_min": 4,
    "genre_raw": 5, "annotator": 6, "date": 7, "difficulty": 8, "desc": 9,
    "T1-1.out": 10, "T1-1.conf": 11,
    "T1-2.out": 12, "T1-2.conf": 13,
    "T1-3.out": 14, "T1-3.conf": 15,
    "T1-4.out": 16, "T1-4.conf": 17,
    "T2-1.label": 18, "T2-1.aux": 19, "T2-1.out": 20, "T2-1.conf": 21,
    "T2-2.label": 22, "T2-2.out": 23, "T2-2.conf": 24,
    "T2-3.label": 25, "T2-3.gender": 26, "T2-3.out": 27, "T2-3.conf": 28,
    "T2-4.label": 29, "T2-4.alt": 30, "T2-4.out": 31, "T2-4.conf": 32,
    "T3-1.label": 33, "T3-1.out": 34, "T3-1.conf": 35,
    "T3-2.label": 36, "T3-2.out": 37, "T3-2.conf": 38,
    "T3-3.label": 39, "T3-3.out": 40, "T3-3.conf": 41,
    "T3-4.label": 42, "T3-4.out": 43, "T3-4.conf": 44,
}


def clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    s = s.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s{2,}", " ", s)


def read_vocab(ws, anchor_row: int) -> list[dict]:
    """从锚点行开始，读到空行为止。返回 [{code,name,note,ver}]。"""
    items: list[dict] = []
    r = anchor_row + 1          # 表头
    header_seen = False
    while r <= ws.max_row:
        row = [clean(c) for c in next(ws.iter_rows(min_row=r, max_row=r, values_only=True), ())]
        row = (row + [""] * 4)[:4]
        code, name, note, ver = row
        if not name and not code:
            if header_seen:
                break
            r += 1
            continue
        if name in {"分类名称", "编号"}:
            header_seen = True
            r += 1
            continue
        items.append({"code": code, "name": name, "note": note, "ver": ver})
        header_seen = True
        r += 1
    return items


def read_task_overview(ws) -> list[dict]:
    """任务总览：行 3 起，9 列。"""
    tasks = []
    level = ""
    for r in range(3, ws.max_row + 1):
        row = [clean(c) for c in next(ws.iter_rows(min_row=r, max_row=r, values_only=True), ())]
        row = (row + [""] * 9)[:9]
        lv, tid, tname, ttype, question, out_struct, scoring, evalway, revision = row
        # 层级列是合并单元格，openpyxl 只在首行给值，其余给「并入 R2C1」这类占位
        if lv and not lv.startswith("并入"):
            level = lv
        if not tid:
            continue
        # 「一 表层可见」-> T1；「二 中层语义」-> T2；「三 深层解释」-> T3
        head = level.strip()[:1]
        layer = {"一": "T1", "二": "T2", "三": "T3"}.get(head, tid[:2])
        tasks.append({
            "level": level, "layer": layer, "id": tid, "name": tname, "type": ttype,
            "question": question, "output_structure": out_struct,
            "scoring": scoring, "evaluation": evalway, "revision": revision,
        })
    return tasks


def parse_weight(scoring: str) -> list[dict]:
    """把「准确性50% 覆盖完整度30% 类别归属20%」拆成结构化维度。"""
    dims = []
    for m in re.finditer(r"([^\s\d%]+?)\s*(\d+)%", scoring):
        dims.append({"dim": m.group(1).strip("（）()、,，"), "pct": int(m.group(2))})
    return dims


def usable_question(s: str) -> str:
    """评测表第 2 行有些格子是列注记而非提问（如「← 模型输出，直接粘贴」），需剔除。"""
    s = (s or "").strip()
    if not s or s.startswith(("←", "→", "如涉及", "有歧义")):
        return ""
    return s


def main() -> None:
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws_eval = wb["评测表"]
    ws_over = wb["任务总览"]

    # 1) 十二项的提问原文（评测表第 2 行）+ 输出列 + 置信度列
    questions: dict[str, str] = {}
    out_cols: dict[str, str] = {}
    conf_cols: dict[str, str] = {}
    for key, idx in COLS.items():
        if not key.startswith(("T1-", "T2-", "T3-")):
            continue
        task, field = key.split(".")
        cell = clean(ws_eval.cell(row=2, column=idx + 1).value)
        if field == "out":
            out_cols[task] = key
            questions[task] = cell
        elif field == "conf":
            conf_cols[task] = key

    # 2) 词表
    vocab: dict[str, list[dict]] = {}
    for tid, title, sheet, anchor in VOCAB_GROUPS:
        items = read_vocab(wb[sheet], anchor)
        # 兜底项：name 为「其他」「其他（开放式）」等
        vocab[tid] = {"title": title, "sheet": sheet, "items": items}

    # 3) 任务总览 -> 权重
    overview = read_task_overview(ws_over)
    weights = {t["id"]: parse_weight(t["scoring"]) for t in overview}

    # 4) 层级权重（来自 PPTX 第 3 页）
    layer_weights = {"T1": 0.35, "T2": 0.50, "T3": 0.15}
    # 单项权重（PPTX 第 3 页 权重列）
    item_weights = {
        "T1-1": 0.09, "T1-2": 0.10, "T1-3": 0.08, "T1-4": 0.08,
        "T2-1": 0.08, "T2-2": 0.06, "T2-3": 0.06, "T2-4": 0.30,
        "T3-1": 0.05, "T3-2": 0.03, "T3-3": 0.03, "T3-4": 0.04,
    }

    spec = {
        "version": "v4.0",
        "source": {
            "pptx": "非遗影像智能分析与评测标准构建.pptx",
            "xlsx": "20260608影片片段标注.xlsx",
        },
        "layers": {
            "T1": {"name": "客观表征层", "weight": layer_weights["T1"], "note": "基础 CV 任务，客观白描，低容错率"},
            "T2": {"name": "中层语义层", "weight": layer_weights["T2"], "note": "涉语境推断，允许误差"},
            "T3": {"name": "深层解释层", "weight": layer_weights["T3"], "note": "极主观，AI 仅作参考提示器"},
        },
        "tasks": [
            {
                "id": t["id"],
                "name": t["name"],
                "level": t["level"],
                "layer": t["layer"],
                "weight": item_weights.get(t["id"]),
                # 评测表第 2 行有几项原本为空或是列注记，退回「任务总览」的核心问题原文
                "question": usable_question(questions.get(t["id"])) or t["question"],
                "question_source": ("评测表第2行" if usable_question(questions.get(t["id"]))
                                    else "任务总览·核心问题"),
                "output_structure": t["output_structure"],
                "scoring_raw": t["scoring"],
                "scoring": weights.get(t["id"], []),
                "evaluation": t["evaluation"],
                "revision": t["revision"],
                "label_vocab": (t["id"] if t["id"] in vocab
                                else ("genre_taxonomy" if t["id"] == "T2-4" else None)),
                "out_field": out_cols.get(t["id"]),
                "conf_field": conf_cols.get(t["id"]),
            }
            for t in overview
        ],
        "vocab": vocab,
        "confidence_levels": ["高", "中", "低"],
        "genre_taxonomy": [
            "民间文学", "传统音乐", "传统舞蹈", "传统戏剧", "曲艺",
            "传统体育、游艺与杂技", "传统美术", "传统技艺", "传统医药", "民俗",
        ],
    }

    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    wb.close()

    # ---- 自检输出 ----
    print(f"已写出 {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"\n任务数: {len(spec['tasks'])}")
    tot = 0.0
    for t in spec["tasks"]:
        w = t["weight"] or 0
        tot += w
        ndim = len(t["scoring"])
        nv = len(vocab[t["id"]]["items"]) if t["id"] in vocab else 0
        print(f"  {t['id']}  w={w:.2f}  评分维度={ndim}  词表={nv:>3}  {t['name']}")
    print(f"  单项权重合计 = {tot:.2f}  （应为 1.00）")

    print("\n词表明细:")
    for tid, blk in vocab.items():
        names = [i["name"] for i in blk["items"]]
        print(f"  {tid:>12} [{blk['title']}] n={len(names)}")
        print(f"               {names}")

    miss = [t["id"] for t in spec["tasks"] if not (t["question"] or "").strip()]
    print(f"\n缺提问原文的任务: {miss or '无'}")


if __name__ == "__main__":
    main()
