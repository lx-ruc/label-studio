"""量化同一片段、同一提示词下多次推理的一致性。

甲方 PPTX 第 2 页的原话：要「通过跨提示词（Prompt）与多次重复推理，
检验 AI 的文化阐释是否符合人类学逻辑自洽」。这个脚本就是实现那一句。

对每个 (片段 × 任务)：
  - 标签：跨轮两两 Jaccard 取均值，再算「三轮完全相同」的比例
  - 输出结果：跨轮两两字符 3-gram F1
  - 置信度：三轮是否同档

全稳定（三轮完全一致）才算「可复现」，否则该条必须人工复核。
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import char_ngram_f1, get_labels  # noqa: E402

LABEL_TASKS = {"T2-1", "T2-2", "T2-3", "T2-4", "T3-2", "T3-3", "T3-4"}


def key_of(rec: dict) -> str:
    if rec.get("clip"):
        return Path(str(rec["clip"])).stem
    return rec.get("id", "")


def load_runs(paths: list[Path]) -> dict[str, list[dict]]:
    """返回 {clip: [run1_answer, run2_answer, ...]}"""
    out: dict[str, list[dict]] = defaultdict(list)
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out[key_of(r)].append(r.get("answer") or r.get("tasks") or {})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="多轮输出 jsonl")
    ap.add_argument("--md", type=Path)
    args = ap.parse_args()

    data = load_runs(args.runs)
    n_runs = len(args.runs)
    tasks = list(next(iter(data.values()))[0].keys())

    rows: list[dict] = []
    for clip, answers in data.items():
        if len(answers) < 2:
            continue
        for tid in tasks:
            items = [a.get(tid) or {} for a in answers]
            r: dict[str, Any] = {"clip": clip, "task": tid, "n": len(items)}
            if tid in LABEL_TASKS:
                sets = [get_labels(x) for x in items]
                pairs = list(itertools.combinations(sets, 2))
                r["label_jaccard"] = statistics.mean(
                    len(a & b) / len(a | b) if (a | b) else 1.0 for a, b in pairs)
                r["label_stable"] = all(s == sets[0] for s in sets)
                r["labels"] = [sorted(s) for s in sets]
            outs = [x.get("out") or "" for x in items]
            r["text_f1"] = statistics.mean(
                char_ngram_f1(a, b) for a, b in itertools.combinations(outs, 2))
            confs = [x.get("conf") or "" for x in items]
            r["conf_stable"] = all(c == confs[0] for c in confs)
            r["confs"] = confs
            rows.append(r)

    print(f"片段 {len(data)} 个 × 任务 {len(tasks)} 项 × {n_runs} 轮\n")
    print(f"{'任务':<6}{'标签Jaccard':>12}{'标签全稳定':>11}{'文本F1':>8}{'置信度稳定':>10}")
    print("-" * 48)
    for tid in tasks:
        rs = [r for r in rows if r["task"] == tid]
        if not rs:
            continue
        lj = [r["label_jaccard"] for r in rs if "label_jaccard" in r]
        ls = [r["label_stable"] for r in rs if "label_stable" in r]
        tf = [r["text_f1"] for r in rs]
        cs = [r["conf_stable"] for r in rs]
        print(f"{tid:<6}"
              f"{(f'{statistics.mean(lj):.3f}' if lj else '-'):>12}"
              f"{(f'{sum(ls)}/{len(ls)}' if ls else '-'):>11}"
              f"{statistics.mean(tf):>8.3f}"
              f"{f'{sum(cs)}/{len(cs)}':>10}")

    unstable = [r for r in rows if r.get("label_stable") is False]
    print(f"\n标签不稳定的条目：{len(unstable)} / {len([r for r in rows if 'label_stable' in r])}")
    for r in unstable:
        print(f"  {r['clip'][:26]:<28}{r['task']:<6}{' | '.join('；'.join(x) or '(空)' for x in r['labels'])}")

    if args.md:
        lines = ["# 多次推理一致性报告", "",
                 f"- 片段：{len(data)} 个，任务：{len(tasks)} 项，轮次：{n_runs}",
                 f"- 目的：检验同一提示词下模型判断是否可复现（甲方「逻辑自洽」要求）", "",
                 "| 任务 | 标签 Jaccard | 标签全稳定 | 文本 F1 | 置信度稳定 |",
                 "|---|---:|---:|---:|---:|"]
        for tid in tasks:
            rs = [r for r in rows if r["task"] == tid]
            if not rs:
                continue
            lj = [r["label_jaccard"] for r in rs if "label_jaccard" in r]
            ls = [r["label_stable"] for r in rs if "label_stable" in r]
            tf = [r["text_f1"] for r in rs]
            cs = [r["conf_stable"] for r in rs]
            lines.append(f"| {tid} | "
                         f"{(f'{statistics.mean(lj):.3f}' if lj else '-')} | "
                         f"{(f'{sum(ls)}/{len(ls)}' if ls else '-')} | "
                         f"{statistics.mean(tf):.3f} | {sum(cs)}/{len(cs)} |")
        lines += ["", "## 标签不稳定的条目", ""]
        for r in unstable:
            lines.append(f"- `{r['clip']}` {r['task']}："
                         + " ／ ".join("；".join(x) or "(空)" for x in r["labels"]))
        args.md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n写出 {args.md}")


if __name__ == "__main__":
    main()
