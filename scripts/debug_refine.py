#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：某个采样帧里，大框细化为什么没成功。

把每个大框的裁剪尺寸、放大倍数、模型原始返回、以及每个子框是被哪一条
过滤规则挡掉的，全部打出来。

用法：.venv/bin/python scripts/debug_refine.py 片段名 帧号
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
if not ok:
    sys.exit("取帧失败")
H, W = frame.shape[:2]
print(f"{CLIP} f={FRAME}  帧尺寸 {W}x{H}\n")

for lab, x1, y1, x2, y2 in sample[1]:
    box = (float(x1), float(y1), float(x2), float(y2))
    flag = "REFINE" if qx.need_refine(lab, box) else "keep  "
    print(f"{flag} {lab:8s} x{x1:4.0f} y{y1:4.0f} w{x2-x1:4.0f} h{y2-y1:4.0f} 面积{(x2-x1)*(y2-y1)/1e4:5.1f}%")
    if flag != "REFINE":
        continue

    px1, py1, px2, py2 = qx._px(box, W, H)
    cw, ch = px2 - px1, py2 - py1
    cx1, cy1 = max(0, int(px1 - cw * 0.06)), max(0, int(py1 - ch * 0.04))
    cx2, cy2 = min(W, int(px2 + cw * 0.06)), min(H, int(py2 + ch * 0.04))
    crop = frame[cy1:cy2, cx1:cx2]
    k = min(4.0, max(1.0, 1200.0 / max(crop.shape[1], crop.shape[0])))
    big = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC) if k > 1.02 else crop
    ok2, buf = cv2.imencode(".jpg", big, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"        裁剪 {cx2-cx1}x{cy2-cy1} px，放大 {k:.2f}x -> {big.shape[1]}x{big.shape[0]}")

    kids = qx.detect(bytes(buf), prompt=qx.REFINE_PROMPT)
    print(f"        模型返回 {len(kids)} 个框")
    cw_px, ch_px = cx2 - cx1, cy2 - cy1
    parea = (box[2] - box[0]) * (box[3] - box[1])
    for kl, kx1, ky1, kx2, ky2 in kids:
        gx1 = (cx1 + kx1 / 1000 * cw_px) / W * 1000
        gx2 = (cx1 + kx2 / 1000 * cw_px) / W * 1000
        gy1 = (cy1 + ky1 / 1000 * ch_px) / H * 1000
        gy2 = (cy1 + ky2 / 1000 * ch_px) / H * 1000
        gw, gh = gx2 - gx1, gy2 - gy1
        why = ""
        if kl != lab:
            why = "标签不同"
        elif gw * gh < 1200:
            why = f"面积 {gw*gh:.0f} < 1200（噪声下限）"
        elif gw * gh > parea * 0.85:
            why = f"没缩小（占父框 {gw*gh/parea*100:.0f}%，需 <85%）"
        print(f"          {kl:8s} 局部({kx1:4.0f},{ky1:4.0f},{kx2:4.0f},{ky2:4.0f})"
              f" -> 全图 w{gw:4.0f} h{gh:4.0f} 面积{gw*gh/1e4:5.2f}%"
              + (f"   ✗ {why}" if why else "   ✓ 采用"))
    print()
