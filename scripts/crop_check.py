#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把若干检测框连周围一起裁出来放大，框线画在上面，用来判断框是否真的套住物体。

如果物体被框线切掉了头/脚/手，说明是检测不准（框本身偏了）；
如果物体完整在框内、只是框留白多或少，那是尺寸精度问题，不是位置问题。

用法：.venv/bin/python scripts/crop_check.py 片段名 时间 输出.jpg [取几个]
"""
import json
import os
import sys

import cv2

CLIP = sys.argv[1]
T = float(sys.argv[2])
OUT = sys.argv[3]
TOPN = int(sys.argv[4]) if len(sys.argv) > 4 else 6
BOXES = os.getenv("QX_BOXES", ".tmp/boxes9.jsonl")
CFG_FPS = 25.0

rec = next(json.loads(l) for l in open(BOXES, encoding="utf-8")
           if json.loads(l)["clip"] == CLIP)


def boxes_at(T):
    out = []
    for r in rec["result"]:
        seq = r["value"]["sequence"]
        prev = None
        for kf in seq:
            if kf["time"] <= T:
                prev = kf
            elif prev is not None:
                if prev.get("enabled", True):
                    span = kf["time"] - prev["time"]
                    k = (T - prev["time"]) / span if span > 0 else 0.0
                    out.append((r["value"]["labels"][0], r["id"], tuple(
                        prev[q] + (kf[q] - prev[q]) * k for q in ("x", "y", "width", "height"))))
                break
    return out


cap = cv2.VideoCapture(f"data/clips4/{CLIP}")
fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(T * fps)))
ok, frame = cap.read()
cap.release()
if not ok:
    sys.exit("取帧失败")
H, W = frame.shape[:2]

act = [b for b in boxes_at(T) if b[0] == "人物"]
act.sort(key=lambda b: -b[2][2] * b[2][3])          # 按面积从大到小
act = act[:TOPN]
print(f"{CLIP} t={T}s 共 {len(act)} 个人物框（按面积取前 {TOPN} 个）")

tiles = []
for lab, rid, (x, y, w, h) in act:
    m = 0.35                                         # 四周留 35% 余量，看框有没有切掉东西
    x1 = max(0, int((x - w * m) / 100 * W))
    y1 = max(0, int((y - h * m) / 100 * H))
    x2 = min(W, int((x + w * (1 + m)) / 100 * W))
    y2 = min(H, int((y + h * (1 + m)) / 100 * H))
    crop = frame[y1:y2, x1:x2].copy()
    if crop.size == 0:
        continue
    k = max(1.0, 420.0 / max(crop.shape[1], crop.shape[0]))
    crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    # 框在裁剪图里的位置
    bx1 = (x / 100 * W - x1) * k
    by1 = (y / 100 * H - y1) * k
    bx2 = ((x + w) / 100 * W - x1) * k
    by2 = ((y + h) / 100 * H - y1) * k
    cv2.rectangle(crop, (int(bx1), int(by1)), (int(bx2), int(by2)), (60, 60, 235), 2)
    cv2.putText(crop, f"{w:.0f}x{h:.0f}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    tiles.append(crop)

hh = min(t.shape[0] for t in tiles)
tiles = [t[:hh, :int(t.shape[1] * 1.0)] for t in tiles]
w0 = max(t.shape[1] for t in tiles)
tiles = [cv2.copyMakeBorder(t, 0, 0, 0, w0 - t.shape[1], cv2.BORDER_CONSTANT, value=(30, 30, 30)) for t in tiles]
row1 = cv2.hconcat(tiles[:3]) if len(tiles) >= 3 else tiles[0]
if len(tiles) > 3:
    rest = tiles[3:6]
    rest = [cv2.copyMakeBorder(t, 0, 0, 0, w0 - t.shape[1], cv2.BORDER_CONSTANT, value=(30, 30, 30)) for t in rest]
    while len(rest) < 3:
        rest.append(rest[0] * 0 + 30)
    row2 = cv2.hconcat(rest)
    out = cv2.vconcat([row1, row2])
else:
    out = row1
cv2.imwrite(OUT, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
print(f"写出 {OUT} {out.shape[1]}x{out.shape[0]}")
