#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印某条人物轨迹的关键帧序列，看跳变发生在哪一类帧上
（Qwen 检测帧，还是光流补出来的中间帧）。"""
import json
import sys

CLIP = sys.argv[1] if len(sys.argv) > 1 else "482344871227e9f9193de1e2a7e67ec5_raw.mp4"
TOPN = int(sys.argv[2]) if len(sys.argv) > 2 else 3

rec = next(json.loads(l) for l in open(".tmp/boxes_flow.jsonl", encoding="utf-8")
           if json.loads(l)["clip"] == CLIP)

cands = []
for res in rec["result"]:
    if res["value"]["labels"][0] != "人物":
        continue
    seq = [k for k in res["value"]["sequence"] if k.get("enabled", True)]
    if len(seq) < 8:
        continue
    worst = 0.0
    for a, b in zip(seq, seq[1:]):
        d = (((a["x"] + a["width"] / 2) - (b["x"] + b["width"] / 2)) ** 2 +
             ((a["y"] + a["height"] / 2) - (b["y"] + b["height"] / 2)) ** 2) ** 0.5
        dt = max(1e-3, b["time"] - a["time"])
        worst = max(worst, d / dt * 0.2)
    cands.append((worst, res))

cands.sort(key=lambda x: -x[0])
for worst, res in cands[:TOPN]:
    seq = [k for k in res["value"]["sequence"] if k.get("enabled", True)]
    print(f"\n=== {res['id']}  共 {len(seq)} 个关键帧，最大跳变 {worst:.1f}%/0.2s ===")
    print("  t(s)   dt     x      y      w      h      位移   IoU")
    prev = None
    for k in seq:
        if prev is None:
            print(f"  {k['time']:6.2f}    -  {k['x']:6.2f} {k['y']:6.2f} "
                  f"{k['width']:6.2f} {k['height']:6.2f}")
        else:
            dt = k["time"] - prev["time"]
            d = (((k["x"] + k["width"] / 2) - (prev["x"] + prev["width"] / 2)) ** 2 +
                 ((k["y"] + k["height"] / 2) - (prev["y"] + prev["height"] / 2)) ** 2) ** 0.5
            ix = max(0, min(k["x"] + k["width"], prev["x"] + prev["width"]) - max(k["x"], prev["x"]))
            iy = max(0, min(k["y"] + k["height"], prev["y"] + prev["height"]) - max(k["y"], prev["y"]))
            inter = ix * iy
            ua = k["width"] * k["height"] + prev["width"] * prev["height"] - inter
            iou = inter / ua if ua > 0 else 0.0
            flag = "  <<<" if d / max(dt, 1e-3) * 0.2 > 3 else ""
            print(f"  {k['time']:6.2f} {dt:5.2f} {k['x']:6.2f} {k['y']:6.2f} "
                  f"{k['width']:6.2f} {k['height']:6.2f}  {d:6.1f} {iou:5.2f}{flag}")
        prev = k
