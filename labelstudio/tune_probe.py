#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预标注精度调优实验：量化「分辨率 / 采样步长 / 提示词」对检出的影响。

不讲玄学，只给数字。目标类固定为「工具/毛笔」，
在已知含毛笔特写的片段上跑，比较三件事：
  - 召回：有多少采样帧检出了
  - 置信度：模型有多确定
  - 框的松紧：框面积占画面比例（越小越贴合物体）

用法：
    python labelstudio/tune_probe.py 01_传统技艺_02.mp4
"""
import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
pt = ROOT / ".tmp" / "pt"
pt.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(pt)

import cv2  # noqa: E402

CLIPS = ROOT / "data" / "clips"
WEIGHTS = ROOT / ".tmp" / "yolov8s-worldv2.pt"

CONFIGS = [
    ("基线  imgsz640 step3", 640, 3, ["brush in hand"]),
    ("高清  imgsz960 step3", 960, 3, ["brush in hand"]),
    ("超清 imgsz1280 step3", 1280, 3, ["brush in hand"]),
    ("密采  imgsz640 step1", 640, 1, ["brush in hand"]),
    ("多词  imgsz640 step3", 640, 3,
     ["brush in hand", "calligraphy brush", "ink brush", "paintbrush"]),
]


def grab(path, step):
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames, idxs = [], []
    i = 1
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if (i - 1) % step == 0:
            frames.append(fr)
            idxs.append(i)
        i += 1
    cap.release()
    return total, idxs, frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", nargs="?", default="01_传统技艺_02.mp4")
    ap.add_argument("--limit", type=int, default=0,
                    help="只跑前 N 个采样帧（调试用）")
    args = ap.parse_args()

    src = CLIPS / args.clip
    if not src.exists():
        sys.exit(f"找不到视频: {src}")

    from ultralytics import YOLO
    model = YOLO(str(WEIGHTS))

    for name, imgsz, step, prompts in CONFIGS:
        total, idxs, frames = grab(src, step)
        if args.limit:
            idxs, frames = idxs[: args.limit], frames[: args.limit]

        model.set_classes(prompts)
        t0 = time.time()
        results = model.predict(frames, conf=0.05, iou=0.5,
                                imgsz=imgsz, verbose=False, device="cpu")
        dt = time.time() - t0

        hits, confs, areas = [], [], []
        for fno, r in zip(idxs, results):
            b = r.boxes
            if b is None or len(b) == 0:
                continue
            h, w = r.orig_shape
            best = int(b.conf.argmax())
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[best]]
            hits.append(fno)
            confs.append(float(b.conf[best]))
            areas.append((x2 - x1) / w * (y2 - y1) / h)

        fps = len(frames) / dt if dt else 0
        print(f"\n{name}  [{len(frames)} 采样帧, {dt:.1f}s, {fps:.1f} 帧/秒]")
        if not hits:
            print("  零检出")
            continue
        print(f"  检出帧数: {len(hits)} / {len(frames)}  ({len(hits)/len(frames)*100:.0f}%)")
        print(f"  置信度  : 均值 {statistics.mean(confs):.3f}  峰值 {max(confs):.3f}")
        print(f"  框面积  : 均值 {statistics.mean(areas)*100:.1f}%  "
              f"最小 {min(areas)*100:.1f}%")
        print(f"  帧号区间: {min(hits)}..{max(hits)}")


if __name__ == "__main__":
    main()
