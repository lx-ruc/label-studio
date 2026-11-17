#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把预标注结果画到视频帧上，拼成一张总览图。

目的：不开 Label Studio 也能一眼看出预标注到底框得准不准。
每个片段取「框最多的那一帧」，因为那通常是模型最有把握的时刻。
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CELL_W, CELL_H = 480, 270
COLS = 4
PAD = 26


def pick_frame(results, total):
    """挑覆盖框最多的一帧，用来代表这条片段的预标注质量。"""
    counter = {}
    for r in results:
        for s in r["value"]["sequence"]:
            if s.get("enabled", True):
                counter[s["frame"]] = counter.get(s["frame"], 0) + 1
    if not counter:
        return max(1, total // 2)
    return max(counter, key=counter.get)


def draw_one(clip: Path, pred, cell_w=CELL_W, cell_h=CELL_H):
    cap = cv2.VideoCapture(str(clip))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target = pick_frame(pred.get("result", []), total)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target - 1)
    ok, img = cap.read()
    cap.release()
    if not ok:
        img = np.zeros((cell_h, cell_w, 3), np.uint8)
    else:
        h, w = img.shape[:2]
        # 保持比例缩放到格子，多余部分裁掉，避免人物被拉变形
        scale = max(cell_w / w, cell_h / h)
        nw, nh = int(w * scale), int(h * scale)
        img = cv2.resize(img, (nw, nh))
        y0 = max(0, (nh - cell_h) // 2)
        x0 = max(0, (nw - cell_w) // 2)
        img = img[y0:y0 + cell_h, x0:x0 + cell_w]

    n_boxes = 0
    for r in pred.get("result", []):
        label = (r["value"].get("labels") or ["?"])[0]
        for s in r["value"]["sequence"]:
            if s["frame"] == target and s.get("enabled", True):
                x = int(s["x"] / 100 * cell_w)
                y = int(s["y"] / 100 * cell_h)
                bw = int(s["width"] / 100 * cell_w)
                bh = int(s["height"] / 100 * cell_h)
                cv2.rectangle(img, (x, y), (x + bw, y + bh), (60, 220, 250), 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(img, (x, y - th - 6), (x + tw + 6, y), (60, 220, 250), -1)
                cv2.putText(img, label, (x + 3, y - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
                n_boxes += 1
    return img, target, total, n_boxes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", default="preds_local.jsonl")
    ap.add_argument("--out", default="data/preview_predictions.jpg")
    args = ap.parse_args()

    items = []
    for line in (ROOT / args.preds).read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))

    cells = []
    for it in items:
        clip = Path(it["video"])
        img, frame_no, total, n_boxes = draw_one(clip, it["prediction"])
        cap = cv2.VideoCapture(str(clip))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.release()
        title = f"{clip.stem}  f{frame_no}/{total}  {n_boxes}框  score {it['prediction'].get('score')}"
        bar = np.full((PAD, CELL_W, 3), 245, np.uint8)
        cv2.putText(bar, title, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (40, 40, 40), 1, cv2.LINE_AA)
        cells.append(np.vstack([bar, img]))

    rows = (len(cells) + COLS - 1) // COLS
    grid_h = rows * (CELL_H + PAD)
    canvas = np.full((grid_h, COLS * CELL_W, 3), 255, np.uint8)
    for i, c in enumerate(cells):
        r, cidx = divmod(i, COLS)
        y, x = r * (CELL_H + PAD), cidx * CELL_W
        canvas[y:y + c.shape[0], x:x + c.shape[1]] = c

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    print(f"已生成 {out}  ({len(cells)} 个片段, {canvas.shape[1]}x{canvas.shape[0]})")


if __name__ == "__main__":
    main()
