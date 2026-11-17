#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一帧、同样 2x2 分块，比较两套提示词各能框出多少：
  PROMPT         —— 整帧用的那套（要求人、器物、材料分别框）
  REFINE_PROMPT  —— 细化用的那套（要求贴边、模糊的不要）
"""
import sys

import cv2

sys.path.insert(0, "scripts")
import qwen_boxes as qx  # noqa: E402


def tiles_of(frame, grid=2, overlap=0.15, target=1400):
    H, W = frame.shape[:2]
    tw, th = W / grid, H / grid
    for gy in range(grid):
        for gx in range(grid):
            x1 = max(0, int(gx * tw - tw * overlap))
            y1 = max(0, int(gy * th - th * overlap))
            x2 = min(W, int((gx + 1) * tw + tw * overlap))
            y2 = min(H, int((gy + 1) * th + th * overlap))
            tile = frame[y1:y2, x1:x2]
            k = max(1.0, target / max(tile.shape[1], tile.shape[0]))
            if k > 1.02:
                tile = cv2.resize(tile, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
            ok, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, 92])
            yield gx, gy, bytes(buf)


for clip, t in [("SD0022004522630060044.mp4", 50.0), ("ea9fe2e3209eccbf5471ac6c6656b51a_raw.mp4", 30.0)]:
    cap = cv2.VideoCapture(f"data/clips4/{clip}")
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"{clip}: 取帧失败")
        continue
    print(f"\n=== {clip} t={t}s  帧 {frame.shape[1]}x{frame.shape[0]} ===")
    for name, prompt in [("PROMPT", qx.PROMPT), ("REFINE", qx.REFINE_PROMPT)]:
        total = []
        for gx, gy, buf in tiles_of(frame):
            ks = qx.detect(buf, prompt=prompt)
            total.extend(ks)
        from collections import Counter
        c = Counter(k[0] for k in total)
        print(f"  {name:6s} 合计 {len(total):2d} 个框  {dict(c)}")
