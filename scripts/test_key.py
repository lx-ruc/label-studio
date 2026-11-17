#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用一次真实调用验证 QWEN_API_KEY 是否可用（顺便验证调用配额）。

只花一次请求：截一帧、压小、调一次 detect()。
"""
import json
import sys

import cv2

sys.path.insert(0, "scripts")
import qwen_boxes as qx  # noqa: E402

CLIP = "data/clips4/SD0012003522630060003.mp4"
cap = cv2.VideoCapture(CLIP)
cap.set(cv2.CAP_PROP_POS_MSEC, 15000)
ok, fr = cap.read()
cap.release()
if not ok:
    sys.exit("取帧失败")

ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 88])
boxes = qx.detect(bytes(buf))
print(f"模型 {qx.MODEL} 返回 {len(boxes)} 个框")
for b in boxes[:5]:
    print(f"  {b[0]:8s} x{b[1]:.0f} y{b[2]:.0f} w{b[3]-b[1]:.0f} h{b[4]-b[2]:.0f}")
if not boxes:
    sys.exit("没框 —— key 可能无效，或模型返回被 parse 全部滤掉")
