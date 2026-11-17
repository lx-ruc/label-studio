#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把某一时刻的框按 LSF 的插值规则画到真实帧上，几帧并排，用来目视检查跟踪是否贴人。

用法：.venv/bin/python scripts/strip.py 输出.jpg 片段名 时间1 时间2 时间3 ...
"""
import json
import sys

import cv2

OUT = sys.argv[1]
CLIP = sys.argv[2]
TIMES = [float(x) for x in sys.argv[3:]]
import os
BOXES = os.getenv("QX_BOXES", ".tmp/boxes_flow.jsonl")
CFG_FPS = 25.0

rec = next(json.loads(l) for l in open(BOXES, encoding="utf-8")
           if json.loads(l)["clip"] == CLIP)

PALETTE = {"人物": (99, 30, 233), "服饰/头饰": (176, 39, 156), "乐器": (243, 150, 33),
           "法器/仪式物": (183, 58, 103), "工具": (80, 175, 76), "材料": (7, 193, 255),
           "设备": (72, 85, 121), "场所元素": (74, 195, 139)}


def boxes_at(T):
    """返回该时刻可见的 (label, id, x, y, w, h)，按关键帧线性插值，和 LSF 一致。"""
    out = []
    for r in rec["result"]:
        seq = r["value"]["sequence"]
        prev = None
        for kf in seq:
            if kf["time"] <= T:
                prev = kf
            elif prev is not None:
                span = kf["time"] - prev["time"]
                k = (T - prev["time"]) / span if span > 0 else 0.0
                if prev.get("enabled", True):
                    bx = tuple(prev[key] + (kf[key] - prev[key]) * k
                               for key in ("x", "y", "width", "height"))
                    out.append((r["value"]["labels"][0], r["id"], bx))
                break
        else:
            # 落在最后一个关键帧之后：只有最后一帧开着才画
            if prev is not None and prev.get("enabled", True) and T >= prev["time"]:
                out.append((r["value"]["labels"][0], r["id"],
                            (prev["x"], prev["y"], prev["width"], prev["height"])))
    return out


cap = cv2.VideoCapture(f"data/clips4/{CLIP}")
if not cap.isOpened():
    sys.exit(f"打不开 data/clips4/{CLIP}")
fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
print(f"{CLIP}: fps {fps:.2f}")

tiles = []
for T in TIMES:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(T * fps)))
    ok, frame = cap.read()
    if not ok:
        continue
    H, W = frame.shape[:2]
    act = boxes_at(T)
    for lab, rid, (x, y, w, h) in act:
        c = PALETTE.get(lab, (0, 0, 0))
        p1 = (int(x / 100 * W), int(y / 100 * H))
        p2 = (int((x + w) / 100 * W), int((y + h) / 100 * H))
        cv2.rectangle(frame, p1, p2, c, 2)
        cv2.putText(frame, lab, (p1[0] + 3, max(12, p1[1] + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, c, 1, cv2.LINE_AA)
    n_person = sum(1 for a in act if a[0] == "人物")
    cv2.putText(frame, f"t={T:.1f}s  {len(act)} boxes ({n_person} person)",
                (8, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    print(f"  t={T:.1f}s: {len(act)} 个框，其中人物 {n_person}")
    tiles.append(frame)
cap.release()

if not tiles:
    sys.exit("没取到帧")
h = min(t.shape[0] for t in tiles)
tiles = [cv2.resize(t, (int(t.shape[1] * h / t.shape[0]), h)) for t in tiles]
strip = cv2.hconcat(tiles)
if strip.shape[1] > 2400:                    # 太长的话缩一下，方便看
    k = 2400 / strip.shape[1]
    strip = cv2.resize(strip, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
cv2.imwrite(OUT, strip, [cv2.IMWRITE_JPEG_QUALITY, 90])
print(f"写出 {OUT} {strip.shape[1]}x{strip.shape[0]}")
