#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在同一个问题上试几种策略，看哪种能把「一条竖条」拆成贴着人的小框。

A. 竖条裁图，按现在的方式放大（长边 1200）
B. 竖条裁图，强制放大到 2.5 倍
C. 整帧切成 2x2 带重叠的块，每块单独认（块内人物变大，模型更容易分开框）

用法：.venv/bin/python scripts/try_tiles.py 片段名 帧号
"""
import json
import sys

import cv2

sys.path.insert(0, "scripts")
import qwen_boxes as qx  # noqa: E402

CLIP = sys.argv[1]
FRAME = int(sys.argv[2])

rec = next(json.loads(l) for l in open(".tmp/dets4.jsonl", encoding="utf-8")
           if json.loads(l)["clip"] == CLIP)
sample = next(s for s in rec["samples"] if s[0] == FRAME)
cap = cv2.VideoCapture(f"data/clips4/{CLIP}")
cap.set(cv2.CAP_PROP_POS_FRAMES, FRAME)
ok, frame = cap.read()
cap.release()
H, W = frame.shape[:2]


def enc(img, q=92):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return bytes(buf)


def show(tag, kids):
    print(f"  {tag}: {len(kids)} 个")
    for kl, x1, y1, x2, y2 in kids:
        print(f"    {kl:8s} w{x2-x1:5.0f} h{y2-y1:5.0f} 面积{(x2-x1)*(y2-y1)/1e4:5.2f}%")


for lab, x1, y1, x2, y2 in sample[1]:
    box = (float(x1), float(y1), float(x2), float(y2))
    if not qx.need_refine(lab, box):
        continue
    print(f"\n=== 大框 {lab} x{x1:.0f} y{y1:.0f} w{x2-x1:.0f} h{y2-y1:.0f} ===")
    px1, py1, px2, py2 = qx._px(box, W, H)
    cw, ch = px2 - px1, py2 - py1
    cx1, cy1 = max(0, int(px1 - cw * 0.06)), max(0, int(py1 - ch * 0.04))
    cx2, cy2 = min(W, int(px2 + cw * 0.06)), min(H, int(py2 + ch * 0.04))
    crop = frame[cy1:cy2, cx1:cx2]

    kA = min(4.0, max(1.0, 1200.0 / max(crop.shape[1], crop.shape[0])))
    show(f"A 现有放大 {kA:.2f}x", qx.detect(enc(cv2.resize(crop, None, fx=kA, fy=kA,
                                                          interpolation=cv2.INTER_CUBIC)),
                                             prompt=qx.REFINE_PROMPT))
    kB = 2.5
    show(f"B 强制放大 {kB}x", qx.detect(enc(cv2.resize(crop, None, fx=kB, fy=kB,
                                                       interpolation=cv2.INTER_CUBIC)),
                                          prompt=qx.REFINE_PROMPT))

print("\n=== C 整帧 2x2 带重叠 ===")
ov = 0.12
merged = []
for gy in range(2):
    for gx in range(2):
        tw, th = W / 2, H / 2
        bx1 = max(0, int(gx * tw - tw * ov))
        by1 = max(0, int(gy * th - th * ov))
        bx2 = min(W, int((gx + 1) * tw + tw * ov))
        by2 = min(H, int((gy + 1) * th + th * ov))
        tile = frame[by1:by2, bx1:bx2]
        k = max(1.0, 1400.0 / max(tile.shape[1], tile.shape[0]))
        big = cv2.resize(tile, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC) if k > 1.02 else tile
        kids = qx.detect(enc(big), prompt=qx.REFINE_PROMPT)
        print(f"  块({gx},{gy}) {bx2-bx1}x{by2-by1} 放大{k:.2f}x -> {len(kids)} 个")
        tw_px, th_px = bx2 - bx1, by2 - by1
        for kl, kx1, ky1, kx2, ky2 in kids:
            g = ((bx1 + kx1 / 1000 * tw_px) / W * 1000, (by1 + ky1 / 1000 * th_px) / H * 1000,
                 (bx1 + kx2 / 1000 * tw_px) / W * 1000, (by1 + ky2 / 1000 * th_px) / H * 1000)
            merged.append((kl,) + g)

# 跨块 NMS（同标签 IoU>0.5 去重，保留面积小的那个：小块更贴）
merged.sort(key=lambda b: (b[3] - b[1]) * (b[4] - b[2]))
final = []
for b in merged:
    if all(b[0] != f[0] or qx.iou((b[1], b[2]), (f[1], f[2])) < 0.5 for f in []):
        pass
    dup = False
    for f in final:
        if f[0] == b[0] and qx.iou((b[1], b[2], b[3], b[4]), (f[1], f[2], f[3], f[4])) > 0.4:
            dup = True
            break
    if not dup:
        final.append(b)
print(f"  合并后 {len(final)} 个：")
for kl, x1, y1, x2, y2 in final:
    print(f"    {kl:8s} x{x1:4.0f} y{y1:4.0f} w{x2-x1:4.0f} h{y2-y1:4.0f} 面积{(x2-x1)*(y2-y1)/1e4:5.2f}%")
