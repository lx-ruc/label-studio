#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出每个片段里「人物框同时可见最多」的时刻，方便抽样看图。"""
import json

import os
for line in open(os.getenv("QX_BOXES", ".tmp/boxes_flow.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    best = (0, 0.0)
    t = 0.0
    while t < r["duration"]:
        n = 0
        for res in r["result"]:
            if res["value"]["labels"][0] != "人物":
                continue
            seq = res["value"]["sequence"]
            if seq[0]["time"] <= t <= seq[-1]["time"]:
                n += 1
        if n > best[0]:
            best = (n, t)
        t += 0.5
    print(f"{r['clip']:46s} 人物峰值 {best[0]:2d} @ {best[1]:5.1f}s  时长 {r['duration']:.1f}s")
