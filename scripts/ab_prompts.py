#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B 对比：全量词表（v1）vs 按门类定制词表（v3），看哪个标注起来更省事。

背景：YOLO-World 是「prompt-then-detect」。给一份词表，它把候选区域和词表里
**所有词**一起算相似度再 softmax。所以词表不是「多给词就多找东西」，而是
**词表越宽、每个词分到的概率越薄**，不相干的词还会跑来抢分数。

这带来两个可直接观测的后果：
  1. 框变松 —— 分数被摊薄后，边界收紧带来的收益变小
  2. 跨门类串门 —— 竹编片段里冒出「织机」、木雕片段里冒出「绣品」

对标注员来说，第 2 条是纯损耗：这些框只能一条条删。所以本脚本把「串门框数量」
当作核心指标，而不只是看置信度均值。

用法：
  python3 scripts/ab_prompts.py --clips 01_xxx.mp4 07_xxx.mp4
  python3 scripts/ab_prompts.py --limit 4          # 取前 4 段
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prelabel_world import (  # noqa: E402
    CLIPS, MODEL_VERSION, ORDER, WORLD_PROMPTS, CATEGORY_PROMPTS,
    prompts_for_clip, run_one, split_tracks, prune_tracks,
)


def plausible_labels(clip: Path) -> set:
    """该门类「工艺上说得通」的标签集合。

    判断「串门框」用的。取 CATEGORY_PROMPTS 里该门类词表映射出的标签；
    门类匹配不上时返回 None，表示无法判断（此时不统计串门）。
    """
    key = clip.name[:2]
    if key not in CATEGORY_PROMPTS:
        return None
    return {WORLD_PROMPTS[p] for p in CATEGORY_PROMPTS[key]}


def measure(tracks):
    """汇总一组轨迹的可观测量。

    per_label 里同时给出每个标签的框面积均值——**这个才是能横向比较的量**。
    整体 mean_area 不能直接比：两版检出的标签构成不一样，
    删掉几条小散框就会让均值被大人形框拉高，看起来像「框变松了」，
    其实是样本构成变了，不是定位变差。
    """
    areas, confs = [], []
    per_label = defaultdict(lambda: {"n": 0, "area": [], "conf": []})
    for t in tracks.values():
        e = per_label[t["label"]]
        e["n"] += 1
        confs.extend(t["scores"])
        e["conf"].extend(t["scores"])
        for _, x, y, w, h in t["frames"]:
            a = (w / 100.0) * (h / 100.0)
            areas.append(a)
            e["area"].append(a)
    out = {k: {"n": v["n"], "kf": len(v["area"]),
               "area": sum(v["area"]) / len(v["area"]) if v["area"] else 0.0,
               "conf": sum(v["conf"]) / len(v["conf"]) if v["conf"] else 0.0}
           for k, v in per_label.items()}
    return {
        "tracks": len(tracks),
        "mean_conf": sum(confs) / len(confs) if confs else 0.0,
        "peak_conf": max(confs) if confs else 0.0,
        "mean_area": sum(areas) / len(areas) if areas else 0.0,
        "per_label": out,
    }


def run_variant(model, clip, order, args):
    labels = [WORLD_PROMPTS[k] for k in order]
    model.set_classes(order)
    tracks = run_one(model, clip, args.step, args.imgsz, args.max_area,
                     order, labels)
    tracks, _ = split_tracks(tracks, args.max_gap, args.min_frames)
    tracks, _ = prune_tracks(tracks, args.min_frames)
    return tracks


def fmt_pct(x):
    return f"{x * 100:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights",
                    default=str(Path(__file__).resolve().parent.parent
                                / ".tmp" / "yolov8s-worldv2.pt"))
    ap.add_argument("--clips", nargs="*")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--min-frames", type=int, default=5)
    ap.add_argument("--max-gap", type=int, default=15)
    ap.add_argument("--max-area", type=float, default=0.6)
    ap.add_argument("--json", help="把结果写成 JSON 便于后续比较")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("请先安装：pip install ultralytics")

    print(f"加载 {Path(args.weights).name} ...")
    model = YOLO(args.weights)

    if args.clips:
        targets = [CLIPS / c for c in args.clips]
    else:
        targets = sorted(CLIPS.glob("*.mp4"))[: args.limit]

    rows = []
    for clip in targets:
        if not clip.exists():
            print(f"[skip] 找不到 {clip}")
            continue

        order_b = prompts_for_clip(clip)
        plausible = plausible_labels(clip)

        tracks_a = run_variant(model, clip, list(ORDER), args)
        tracks_b = run_variant(model, clip, order_b, args)

        ma, mb = measure(tracks_a), measure(tracks_b)

        # 串门框：出现在该片段里、但工艺上不该出现的标签
        stray = 0
        stray_detail = {}
        if plausible is not None:
            for lb, e in ma["per_label"].items():
                if lb not in plausible:
                    stray += e["n"]
                    stray_detail[lb] = e["n"]

        # 同类比较：只看两版都检出的标签，比框面积和置信度。
        # 这是唯一能公平比较「定位有没有变紧」的方式。
        common = sorted(set(ma["per_label"]) & set(mb["per_label"]))
        if common:
            print(f"  {'':22}{'A 全量':>12}{'B 定制':>12}")
            print(f"  -- 同类比较（两版共有的 {len(common)} 个标签）--")
            for lb in common:
                a, b = ma["per_label"][lb], mb["per_label"][lb]
                note = ""
                if a["area"] > 1e-9:
                    d = (b["area"] - a["area"]) / a["area"]
                    note = f"  框{'紧' if d < 0 else '松'}{abs(d) * 100:.0f}%"
                print(f"  {lb:<20}{fmt_pct(a['area']):>12}{fmt_pct(b['area']):>12}{note}")

        print(f"\n=== {clip.name} ===")
        print(f"  词表: A=全量 {len(ORDER)} 词  |  B=门类定制 {len(order_b)} 词"
              f" ({', '.join(order_b)})")
        print(f"  {'':22}{'A 全量':>12}{'B 定制':>12}")
        print(f"  {'轨迹数':<20}{ma['tracks']:>14}{mb['tracks']:>14}")
        print(f"  {'平均置信度':<20}{ma['mean_conf']:>14.3f}{mb['mean_conf']:>14.3f}")
        print(f"  {'峰值置信度':<20}{ma['peak_conf']:>14.3f}{mb['peak_conf']:>14.3f}")
        print(f"  {'平均框面积':<20}"
              f"{fmt_pct(ma['mean_area']):>14}{fmt_pct(mb['mean_area']):>14}")
        if plausible is not None and stray:
            d = "、".join(f"{k}×{v}" for k, v in sorted(stray_detail.items()))
            print(f"  ⚠ A 版串门框 {stray} 条（{d}），B 版按构造为 0")

        rows.append({
            "clip": clip.name, "A": ma, "B": mb,
            "stray_A": stray, "stray_detail_A": stray_detail,
        })

    # 汇总。注意整体 mean_area 不能跨版本直接比（构成不同），
    # 所以这里也按「两版共有的标签」做加权同类比较，权重是关键帧数。
    print("\n" + "=" * 56)
    print("汇总 —— 同类比较（只统计两版都检出的标签，按关键帧数加权）")
    agg = {"A": defaultdict(lambda: [0, 0.0]), "B": defaultdict(lambda: [0, 0.0])}
    for r in rows:
        for k in ("A", "B"):
            for lb, e in r[k]["per_label"].items():
                agg[k][lb][0] += e["kf"]
                agg[k][lb][1] += e["area"] * e["kf"]

    common = sorted(set(agg["A"]) & set(agg["B"]))
    print(f"  {'标签':<18}{'A 框面积':>11}{'B 框面积':>11}{'  变化':>10}")
    ta = tb = 0.0
    ka = kb = 0
    for lb in common:
        ka_a, sa = agg["A"][lb]
        ka_b, sb = agg["B"][lb]
        aa, ab = sa / ka_a, sb / ka_b
        ta += sa; tb += sb; ka += ka_a; kb += ka_b
        d = (ab - aa) / aa if aa > 1e-9 else 0.0
        print(f"  {lb:<18}{fmt_pct(aa):>11}{fmt_pct(ab):>11}"
              f"{('+' if d >= 0 else '-') + f'{abs(d) * 100:.0f}%':>10}")
    if ka and kb:
        wa, wb = ta / ka, tb / kb
        d = (wb - wa) / wa if wa > 1e-9 else 0.0
        print(f"  {'加权合计':<18}{fmt_pct(wa):>11}{fmt_pct(wb):>11}"
              f"{('+' if d >= 0 else '-') + f'{abs(d) * 100:.0f}%':>10}")
    print(f"\n  串门框合计: A={sum(r['stray_A'] for r in rows)} 条，B=0 条")
    print("  置信度均值: "
          f"A={sum(r['A']['mean_conf'] * r['A']['tracks'] for r in rows) / max(1, sum(r['A']['tracks'] for r in rows)):.3f}"
          f"  B={sum(r['B']['mean_conf'] * r['B']['tracks'] for r in rows) / max(1, sum(r['B']['tracks'] for r in rows)):.3f}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {args.json}")


if __name__ == "__main__":
    main()
