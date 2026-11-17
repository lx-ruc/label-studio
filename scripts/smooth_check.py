#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化检查：光流补帧后，框的逐帧位移是否平滑（有没有跳）。

拿「相邻两个关键帧的中心位移」比上时间差，换算成「每 0.2 秒移动了画幅宽的百分之几」。
正常人走路大约 0.3~1.2；出现 3 以上多半是光流跟丢了又拽回来。
"""
import json
import statistics as st
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else ".tmp/boxes_flow.jsonl"
for line in open(PATH, encoding="utf-8"):
    r = json.loads(line)
    speeds, ious, n_tracks = [], [], 0
    for res in r["result"]:
        if res["value"]["labels"][0] != "人物":
            continue
        seq = [k for k in res["value"]["sequence"] if k.get("enabled", True)]
        if len(seq) < 3:
            continue
        n_tracks += 1
        for a, b in zip(seq, seq[1:]):
            dt = b["time"] - a["time"]
            if dt <= 0:
                continue
            ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
            bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            speeds.append(d / dt * 0.2)          # 每 0.2 秒移动了画幅宽的百分之几
            ix = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
            iy = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
            inter = ix * iy
            ua = a["width"] * a["height"] + b["width"] * b["height"] - inter
            ious.append(inter / ua if ua > 0 else 0)
    if not speeds:
        continue
    q = lambda a, p: sorted(a)[min(len(a) - 1, int(len(a) * p))]
    jumps = sum(1 for s in speeds if s > 3.0)
    print(f"{r['clip'][:40]:42s} 人物轨迹 {n_tracks:3d} 条，相邻关键帧 {len(speeds)} 对")
    print(f"    位移/0.2s  中位 {st.median(speeds):5.2f}  p95 {q(speeds, .95):5.2f}  "
          f"p99 {q(speeds, .99):5.2f}  最大 {max(speeds):6.2f}  超过 3 的有 {jumps} 对")
    print(f"    相邻关键帧 IoU  中位 {st.median(ious):.3f}  p05 {q(ious, .05):.3f}")
