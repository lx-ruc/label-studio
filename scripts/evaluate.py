"""把 Qwen 的十二项输出，和甲方金标准逐项比对打分。

评分口径全部来自甲方「任务总览」的「评分维度（权重）」列，不自己发明：
    T1-1  准确性50% 覆盖完整度30% 类别归属20%
    T2-4  主分类准确性50% 判断依据30% 歧义说明20%
    ...

自动化只能替代其中的「可判定」部分：
  - 标签类维度  -> Macro-F1 / micro-F1 / Jaccard（对齐甲方 Macro-F1、Top-3 Accuracy）
  - 文本类维度  -> 字符 n-gram F1 作为 BERTScore 的廉价代理（甲方写的是 BERTScore）
  - 依据类维度  -> 结构检查（有没有「判断依据」「因为」等），真正的质量仍需人工
所以报告里每一项都标了「自动 / 需人工」，不假装全能。

用法：
    python scripts/evaluate.py --pred preds.jsonl --gold refs/gold.jsonl
    python scripts/evaluate.py --pred refs/gold.jsonl --gold refs/gold.jsonl   # 自检，应全 1.0
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "refs" / "annotation_spec_v4.json"

# 哪些任务有封闭标签集
LABEL_TASKS = {"T2-1", "T2-2", "T2-3", "T2-4", "T3-2", "T3-3", "T3-4"}
# 哪些任务的输出是纯文本判定（无标签）
TEXT_ONLY = {"T1-1", "T1-2", "T1-3", "T1-4", "T3-1"}

# 依据类结构标志词
EVIDENCE_MARKERS = ("判断依据", "依据", "因为", "由于", "可见", "画面中", "字幕",
                    "从……可", "说明", "因此")


# --------------------------------------------------------------------------- #
# 基础指标
# --------------------------------------------------------------------------- #

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def macro_f1(pairs: list[tuple[set, set]], labels: list[str]) -> tuple[float, dict]:
    """多标签 macro-F1：对每个标签分别算 P/R/F1，再按标签平均。"""
    per: dict[str, dict] = {}
    for lb in labels:
        tp = sum(1 for g, p in pairs if lb in g and lb in p)
        fp = sum(1 for g, p in pairs if lb not in g and lb in p)
        fn = sum(1 for g, p in pairs if lb in g and lb not in p)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[lb] = {"tp": tp, "fp": fp, "fn": fn, "p": prec, "r": rec, "f1": f1}
    # 只在金标准中出现过、或模型预测过的标签上平均，避免被大量零样本标签稀释
    active = [lb for lb, m in per.items() if m["tp"] + m["fn"] + m["fp"] > 0]
    mf1 = statistics.mean(per[lb]["f1"] for lb in active) if active else 0.0
    return mf1, per


def micro_f1(pairs: list[tuple[set, set]]) -> float:
    tp = sum(len(g & p) for g, p in pairs)
    fp = sum(len(p - g) for g, p in pairs)
    fn = sum(len(g - p) for g, p in pairs)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def char_ngram_f1(a: str, b: str, n: int = 3) -> float:
    """字符 n-gram F1 —— BERTScore 的廉价代理，中文上相关性尚可。"""
    def grams(s: str) -> Counter:
        s = re.sub(r"[\s，。、；：！？“”‘’（）()]", "", s)
        return Counter(s[i:i + n] for i in range(max(0, len(s) - n + 1)))
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 1.0 if not ga and not gb else 0.0
    overlap = sum((ga & gb).values())
    prec = overlap / sum(ga.values())
    rec = overlap / sum(gb.values())
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def cohens_kappa(gold: list[set], pred: list[set]) -> float:
    """多标签 Cohen's κ：按标签逐一算 κ 后平均（甲方 T2-3/T3-3 明确要求）。"""
    labels = sorted({x for s in gold + pred for x in s})
    if not labels:
        return 1.0
    ks = []
    n = len(gold)
    for lb in labels:
        g = [lb in s for s in gold]
        p = [lb in s for s in pred]
        po = sum(1 for a, b in zip(g, p) if a == b) / n
        pg, pp = sum(g) / n, sum(p) / n
        pe = pg * pp + (1 - pg) * (1 - pp)
        k = (po - pe) / (1 - pe) if pe < 1 else 0.0
        ks.append(k)
    return statistics.mean(ks)


def ece(conf_pairs: list[tuple[float, float]], bins: int = 3) -> float:
    """置信度校准误差：把「高/中/低」映射到 0.9/0.6/0.3，看它与实际正确率的偏差。"""
    if not conf_pairs:
        return 0.0
    buckets = defaultdict(list)
    for c, acc in conf_pairs:
        buckets[min(bins - 1, int(c * bins))].append(acc)
    total = len(conf_pairs)
    e = 0.0
    for b, accs in buckets.items():
        center = (b + 0.5) / bins
        e += len(accs) / total * abs(center - statistics.mean(accs))
    return e


CONF_VAL = {"高": 0.9, "中": 0.6, "低": 0.3}


# --------------------------------------------------------------------------- #
# 逐任务打分
# --------------------------------------------------------------------------- #

def get_labels(item: dict) -> set:
    """金标准用 labels / symbols，模型输出用 label，统一取。"""
    for key in ("labels", "label", "symbols"):
        v = item.get(key)
        if isinstance(v, str):
            v = [x.strip() for x in re.split(r"[；;，,、]", v) if x.strip()]
        if v:
            return set(v)
    # 模型自拟的「其他：xxx」也算有效标签
    return set(item.get("other_labels") or [])


def score_task(tid: str, gold: list[dict], pred: list[dict], task: dict) -> dict:
    dims = task.get("scoring") or []
    out: dict[str, Any] = {"id": tid, "name": task["name"], "weight": task["weight"],
                           "n": len(gold)}

    if tid in LABEL_TASKS:
        g_sets = [get_labels(x) for x in gold]
        p_sets = [get_labels(x) for x in pred]
        pairs = list(zip(g_sets, p_sets))
        labels = sorted({x for s in g_sets + p_sets for x in s})
        mf1, per = macro_f1(pairs, labels)
        out.update({
            "macro_f1": mf1,
            "micro_f1": micro_f1(pairs),
            "jaccard": statistics.mean(jaccard(g, p) for g, p in pairs) if pairs else 0.0,
            "exact_match": (sum(1 for g, p in pairs if g == p) / len(pairs)) if pairs else 0.0,
            "kappa": cohens_kappa(g_sets, p_sets),
            "per_label": {k: v for k, v in sorted(per.items(),
                                                  key=lambda kv: -kv[1]["tp"])[:12]},
        })
        # 置信度校准：以「标签集合完全一致」当作正确
        cp = [(CONF_VAL.get(x.get("conf") or "中", 0.5), 1.0 if g == p else 0.0)
              for g, p, x in zip(g_sets, p_sets, pred)]
        # 样本量太小时 ECE 纯属噪音（4 条样本会算出 0.5 这种无意义的值），宁可不报
        out["ece"] = ece(cp) if len(cp) >= 30 else None
        # 置信度一致性：模型与人工在同一片段上给出的置信度是否同档
        out["conf_agree"] = sum(
            1 for g, p in zip(gold, pred)
            if (g.get("conf") or "") == (p.get("conf") or "") and g.get("conf")
        ) / max(len(gold), 1)
        # 三重评分维度：标签判定相关的维度吃 F1，文本相关的维度吃 n-gram
    # 文本一致性（所有任务都算）
    sims = [char_ngram_f1(g.get("out") or "", p.get("out") or "")
            for g, p in zip(gold, pred)]
    out["text_f1"] = statistics.mean(sims) if sims else 0.0
    out["text_len_ratio"] = (
        statistics.mean(len(p.get("out") or "") / max(len(g.get("out") or ""), 1)
                        for g, p in zip(gold, pred)) if gold else 0.0)
    # 依据结构：只在「人工确实写了依据」的样本上算召回，避免把人工的简写习惯算成模型缺陷
    need = [i for i, g in enumerate(gold)
            if any(m in (g.get("out") or "") for m in EVIDENCE_MARKERS)]
    if need:
        out["evidence_rate"] = sum(
            1 for i in need if any(m in (pred[i].get("out") or "") for m in EVIDENCE_MARKERS)
        ) / len(need)
        out["evidence_n"] = len(need)
    else:
        out["evidence_rate"] = 1.0
        out["evidence_n"] = 0

    # 按甲方维度合成单任务分
    auto_dims = []
    for d in dims:
        name = d["dim"]
        pct = d["pct"] / 100
        if any(k in name for k in ("准确性", "判断", "类别归属", "识别", "分类")):
            v = out.get("micro_f1") if tid in LABEL_TASKS else out["text_f1"]
            src = "micro_f1" if tid in LABEL_TASKS else "text_f1"
        elif any(k in name for k in ("覆盖", "完整", "依据", "说明", "推理", "解读",
                                     "描述", "分析", "深度", "证据")):
            # 依据类维度：一半看文本相似度，一半看结构完整度（真正质量仍需人工）
            v = 0.5 * out["text_f1"] + 0.5 * out["evidence_rate"]
            src = "0.5*text_f1+0.5*evidence_rate"
        else:
            v = out["text_f1"]
            src = "text_f1"
        auto_dims.append({"dim": name, "pct": d["pct"], "value": round(v, 4),
                          "source": src, "needs_human": "依据" in name or "深度" in name
                          or "质量" in name})
    out["dims"] = auto_dims
    out["score"] = round(sum(d["pct"] / 100 * d["value"] for d in auto_dims), 4)
    return out


# --------------------------------------------------------------------------- #
# 对齐
# --------------------------------------------------------------------------- #

def key_of(rec: dict) -> str:
    """把预测和金标准对齐的键。

    优先级：gold_id > clip 文件名 > G 开头 id > 片名+时间码。
    片段级样本（如四条测试片）只有 clip，时间码为空，所以 clip 必须排在时间码之前。
    """
    if rec.get("gold_id"):
        return rec["gold_id"]
    if rec.get("clip"):
        return "clip:" + Path(str(rec["clip"])).stem
    if rec.get("id", "").startswith("G"):
        return rec["id"]
    film = (rec.get("film") or "").strip("《》")
    film = Path(film).stem
    return f"{film}|{rec.get('start', '')}|{rec.get('end', '')}"


def normalize_pred(rec: dict) -> dict:
    """兼容三种形状：{answer:{T1-1:...}}、{tasks:{T1-1:...}}（金标准自身）、扁平 {T1-1:...}。"""
    if "answer" in rec:
        return rec["answer"]
    if "tasks" in rec:
        return rec["tasks"]
    return {k: v for k, v in rec.items() if re.fullmatch(r"T[123]-\d", k)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--gold", type=Path, default=ROOT / "refs" / "gold.jsonl")
    ap.add_argument("--spec", type=Path, default=SPEC_PATH)
    ap.add_argument("--out", type=Path, help="写出 JSON 报告")
    ap.add_argument("--md", type=Path, help="写出 Markdown 报告")
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    gold = [json.loads(l) for l in args.gold.read_text(encoding="utf-8").splitlines() if l.strip()]
    preds = [json.loads(l) for l in args.pred.read_text(encoding="utf-8").splitlines() if l.strip()]

    gmap = {key_of(r): r for r in gold}
    matched, unmatched = [], []
    for p in preds:
        k = key_of(p)
        if k in gmap:
            matched.append((gmap[k], p))
        else:
            unmatched.append(k)

    print(f"金标准 {len(gold)} 条，预测 {len(preds)} 条，对齐成功 {len(matched)} 条")
    if unmatched:
        print(f"未对齐 {len(unmatched)} 条（前 5）：{unmatched[:5]}")
    if not matched:
        print("没有可比的样本，退出。请检查 key_of() 的对齐键。")
        return

    results = []
    for task in spec["tasks"]:
        tid = task["id"]
        g_items = [g["tasks"][tid] for g, _ in matched]
        p_items = [normalize_pred(p).get(tid) or {} for _, p in matched]
        r = score_task(tid, g_items, p_items, task)
        results.append(r)

    total = sum(r["score"] * (r["weight"] or 0) for r in results)
    wsum = sum(r["weight"] or 0 for r in results)
    weighted = total / wsum if wsum else 0.0

    # ---- 控制台 ----
    print(f"\n{'任务':<6}{'权重':>6}{'自动分':>8}{'macroF1':>9}{'textF1':>8}{'ECE':>7}")
    print("-" * 46)
    for r in results:
        mf = r.get("macro_f1")
        e = r.get("ece")
        print(f"{r['id']:<6}{r['weight']:>6.2f}{r['score']:>8.3f}"
              f"{(f'{mf:.3f}' if mf is not None else '   -'):>9}"
              f"{r['text_f1']:>8.3f}{(f'{e:.3f}' if e is not None else '样本不足'):>7}")
    print("-" * 46)
    print(f"{'加权总分':<6}{wsum:>6.2f}{weighted:>8.3f}")
    if len(matched) < 30:
        print(f"\n[注意] 只有 {len(matched)} 条样本，ECE 与 macro-F1 的置信区间都很宽，"
              f"只能看失败模式，不要当结论。")

    # ---- 报告 ----
    md = ["# Qwen 标注 vs 甲方金标准 —— 自动评测报告", "",
          f"- 对齐样本：**{len(matched)}** 条"
          + (f"（另有 {len(unmatched)} 条未对齐）" if unmatched else ""),
          f"- 加权总分（按甲方单项权重）：**{weighted:.3f}**", "",
          "> 说明：文本类维度用字符 3-gram F1 代理甲方要求的 BERTScore；"
          "「依据/证据/深度」类维度只能自动查结构，**真实质量仍需人工复核**"
          "（甲方原表也留了 20%~80% 人工复核）。",
          "", "## 分项", "",
          "| 任务 | 名称 | 权重 | 自动分 | macro-F1 | micro-F1 | text-F1 | κ | ECE |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        def fmt(key: str, nd: int = 3) -> str:
            v = r.get(key)
            return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "-"
        md.append(
            f"| {r['id']} | {r['name']} | {r['weight']:.2f} | {r['score']:.3f} | "
            f"{fmt('macro_f1')} | {fmt('micro_f1')} | {r['text_f1']:.3f} | "
            f"{fmt('kappa')} | " + (f"{r['ece']:.3f}" if r.get("ece") is not None else "样本不足") + " |"
        )

    md += ["", "## 评分维度拆解（前 4 项）", ""]
    for r in results[:4]:
        md.append(f"### {r['id']} {r['name']}")
        md.append("")
        md.append("| 维度 | 权重 | 自动得分 | 计算方式 | 需人工 |")
        md.append("|---|---:|---:|---|---|")
        for d in r["dims"]:
            md.append(f"| {d['dim']} | {d['pct']}% | {d['value']:.3f} | "
                      f"`{d['source']}` | {'是' if d['needs_human'] else '否'} |")
        md.append("")

    if args.out:
        args.out.write_text(json.dumps(
            {"n_matched": len(matched), "weighted": weighted, "tasks": results},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n写出 {args.out}")
    if args.md:
        args.md.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"写出 {args.md}")


if __name__ == "__main__":
    main()
