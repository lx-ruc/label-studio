"""用大模型当裁判（LLM-as-Judge），按甲方评分维度给「输出结果」打分。

为什么需要它：字符 n-gram F1 惩罚的是篇幅差异，不是判断对错。
实测 4 条片子：Qwen 输出是参考的 1.6~2.6 倍长，结论基本一致却只拿到 0.15 的 text-F1。
甲方 PPTX 第 4 页与「任务总览」的多项评估方式本来就要求 GPT-as-Judge / 专家评分，
所以这里补上语义裁决，而不是继续调字符指标。

裁判只判两件事：**结论对不对**、**依据成不成立**。明确告知它：
  - 篇幅长短不扣分，更详细但结论一致 = 满分
  - 用词不同但意思相同 = 一致
  - 结论冲突 = 0 分，哪怕写得很漂亮

用法：
    python scripts/judge.py --pred .tmp/qwen4_run1.jsonl --gold refs/ref4_reference.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from qwen_label import TASK_FIELDS, call_qwen, load_spec  # noqa: E402

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen3.8-flash")

SYSTEM = """你是非遗影像标注的评审专家。你的任务是判断「模型作答」与「参考答案」在实质内容上是否一致。

**只看实质，不看形式。** 以下情况都不扣分：
- 模型写得更长、更详细，只要结论一致、没有编造矛盾内容
- 用词不同但意思相同（如「银饰」vs「银项圈、银角头饰」：后者是前者的下位细化，算一致）
- 语序、句式、标点不同

以下情况要扣分或判零：
- 核心结论冲突（如参考答案说「不存在仪式性场景」，模型说「存在」）
- 标签给了参考答案里没有、且明显错误的类
- 编造画面里不可能存在的信息（人名、地名、机构名、具体年代）
- 把模板占位符（X、Y、……）留在答案里
- 该说「无法判断」的时候硬给结论

只返回一个 JSON 对象，不要 Markdown：
{"score": 0.0~1.0 的小数, "verdict": "一致|部分一致|冲突", "reason": "20 字以内说明"}"""


def judge_one(task: dict, ref: dict, hyp: dict) -> dict:
    vocab = ""
    if task.get("label_vocab") and task["label_vocab"] != "genre_taxonomy":
        vocab = "词表：\n" + "\n".join(
            f"  - {i['name']}" for i in task["vocab_items"])
    elif task.get("label_vocab") == "genre_taxonomy":
        vocab = "门类词表：\n" + "\n".join(f"  - {g}" for g in task["genres"])

    def show(d: dict) -> str:
        parts = []
        if d.get("label"):
            parts.append(f"标签：{'；'.join(d['label'])}")
        if d.get("aux"):
            parts.append(f"辅助标签：{'；'.join(d['aux'])}")
        if d.get("alt"):
            parts.append(f"次选：{'；'.join(d['alt'])}")
        if d.get("gender"):
            parts.append(f"性别属性：{d['gender']}")
        if d.get("conf"):
            parts.append(f"置信度：{d['conf']}")
        parts.append(f"输出结果：{d.get('out') or '（空）'}")
        return "\n".join(parts)

    user = (
        f"## 任务\n{task['id']} {task['name']}\n提问：{task['question']}\n{vocab}\n\n"
        f"## 参考答案\n{show(ref)}\n\n"
        f"## 模型作答\n{show(hyp)}\n\n"
        f"请判分。"
    )
    try:
        raw = call_qwen(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            model=JUDGE_MODEL, temperature=0.0, max_tokens=300)
        t = raw.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
            t = re.sub(r"\n?```$", "", t)
        m = re.search(r"\{.*\}", t, re.S)
        d = json.loads(m.group(0) if m else t)
        s = float(d.get("score", 0))
        return {"score": max(0.0, min(1.0, s)),
                "verdict": str(d.get("verdict", "")),
                "reason": str(d.get("reason", ""))[:60]}
    except Exception as exc:                       # noqa: BLE001
        return {"score": None, "verdict": "错误", "reason": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM-as-Judge 评测")
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--gold", type=Path, default=ROOT / "refs" / "ref4_reference.jsonl")
    ap.add_argument("--out", type=Path, help="明细 json")
    ap.add_argument("--md", type=Path, help="Markdown 报告")
    ap.add_argument("--tasks", help="只评这些任务，逗号分隔，如 T2-4,T1-4")
    ap.add_argument("--quiet", action="store_true", help="只打印汇总")
    args = ap.parse_args()

    spec = load_spec()
    tasks = spec["tasks"]
    if args.tasks:
        keep = {x.strip() for x in args.tasks.split(",")}
        tasks = [t for t in tasks if t["id"] in keep]

    # 给任务块补上词表原文，方便拼提示词
    for t in tasks:
        key = t.get("label_vocab")
        t["vocab_items"] = (spec["vocab"][key]["items"]
                            if key and key != "genre_taxonomy" else [])
        t["genres"] = spec["genre_taxonomy"]

    def key_of(rec: dict) -> str:
        if rec.get("gold_id"):
            return rec["gold_id"]
        if rec.get("clip"):
            return "clip:" + Path(str(rec["clip"])).stem
        return rec.get("id", "")

    gold = {}
    for line in args.gold.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            gold[key_of(r)] = r
    preds = [json.loads(l) for l in args.pred.read_text(encoding="utf-8").splitlines() if l.strip()]

    detail = []
    for p in preds:
        k = key_of(p)
        g = gold.get(k)
        if not g:
            print(f"跳过（无参考）：{k}")
            continue
        hyp_all = p.get("answer") or p.get("tasks") or p
        for t in tasks:
            ref = g["tasks"][t["id"]]
            hyp = hyp_all.get(t["id"]) or {}
            r = judge_one(t, ref, hyp)
            r.update({"clip": k, "task": t["id"], "name": t["name"],
                      "weight": t["weight"], "ref": ref.get("out", ""),
                      "hyp": hyp.get("out", "")})
            detail.append(r)
            if not args.quiet:
                icon = {"一致": "✓", "部分一致": "~", "冲突": "✗"}.get(r["verdict"], "?")
                print(f"{icon} {k[:26]:<28}{t['id']:<6}"
                      f"{r['score'] if r['score'] is not None else 'ERR'}  {r['reason']}")

    # ---- 汇总 ----
    by_task: dict[str, list[float]] = {}
    for d in detail:
        if d["score"] is not None:
            by_task.setdefault(d["task"], []).append(d["score"])

    print(f"\n{'任务':<6}{'权重':>6}{'裁判均分':>9}{'一致':>6}{'部分':>6}{'冲突':>6}")
    print("-" * 42)
    total, wsum = 0.0, 0.0
    for t in tasks:
        ss = by_task.get(t["id"], [])
        if not ss:
            continue
        avg = sum(ss) / len(ss)
        ds = [d for d in detail if d["task"] == t["id"]]
        c = {v: sum(1 for d in ds if d["verdict"] == v) for v in ("一致", "部分一致", "冲突")}
        print(f"{t['id']:<6}{t['weight']:>6.2f}{avg:>9.3f}{c['一致']:>6}{c['部分一致']:>6}{c['冲突']:>6}")
        total += avg * (t["weight"] or 0)
        wsum += t["weight"] or 0
    print("-" * 42)
    print(f"{'加权总分':<6}{wsum:>6.2f}{total/wsum if wsum else 0:>9.3f}")

    if args.out:
        args.out.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n写出 {args.out}")
    if args.md:
        lines = ["# LLM-as-Judge 评测报告", "",
                 f"- 裁判模型：`{JUDGE_MODEL}`",
                 f"- 样本：{len(preds)} 条 × {len(tasks)} 项",
                 f"- 加权总分：**{total/wsum if wsum else 0:.3f}**", "",
                 "| 任务 | 名称 | 权重 | 裁判均分 | 一致 | 部分 | 冲突 |",
                 "|---|---|---:|---:|---:|---:|---:|"]
        for t in tasks:
            ss = by_task.get(t["id"], [])
            if not ss:
                continue
            ds = [d for d in detail if d["task"] == t["id"]]
            c = {v: sum(1 for d in ds if d["verdict"] == v) for v in ("一致", "部分一致", "冲突")}
            lines.append(f"| {t['id']} | {t['name']} | {t['weight']:.2f} | "
                         f"{sum(ss)/len(ss):.3f} | {c['一致']} | {c['部分一致']} | {c['冲突']} |")
        lines += ["", "## 冲突明细", ""]
        for d in detail:
            if d["verdict"] == "冲突":
                lines.append(f"- **{d['clip']} {d['task']}**：{d['reason']}")
        args.md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"写出 {args.md}")


if __name__ == "__main__":
    main()
