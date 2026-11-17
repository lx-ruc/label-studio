"""用真正的目标检测器（torchvision Faster R-CNN / FCOS）出「人物」框。

为什么不用 Qwen 出人物框：Qwen 是「看图说话」的 grounding 模型，给它一块
裁剪区域的图，它给的框边界经常正好落在裁剪窗边缘（x 0~259 / y 424~998
这种），框出来的是「分块窗口」而不是「人」。要贴住人，只能用专门训练过的
检测器。

采样时刻与 qwen_boxes.gather 完全一致，所以帧号能一一对齐。

    .venv-detect/bin/python scripts/det_person.py \
        --clips clips --out .tmp/dets_person.jsonl [--model fasterrcnn|fcos|retina]
"""
import argparse
import json
import os
import time
from pathlib import Path

import cv2
import torch
from torchvision.models.detection import (
    fasterrcnn_resnet50_fpn_v2, FasterRCNN_ResNet50_FPN_V2_Weights,
    fcos_resnet50_fpn, FCOS_ResNet50_FPN_Weights,
    retinanet_resnet50_fpn_v2, RetinaNet_ResNet50_FPN_V2_Weights,
)

MODELS = {
    "fasterrcnn": (fasterrcnn_resnet50_fpn_v2, FasterRCNN_ResNet50_FPN_V2_Weights),
    "fcos": (fcos_resnet50_fpn, FCOS_ResNet50_FPN_Weights),
    "retina": (retinanet_resnet50_fpn_v2, RetinaNet_ResNet50_FPN_V2_Weights),
}


def load(model: str, min_size: int = 640):
    fn, w = MODELS[model]
    m = fn(weights=w.DEFAULT, box_score_thresh=0.05,
           min_size=min_size, max_size=1280)
    m.eval()
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
    return m


def dedupe_contained(persons, contain=0.8):
    """同一帧里被大框几乎完全包住的小框去掉。

    Faster R-CNN 的 NMS 只按 IoU 压重叠，遇到「整个人」和「这个人上半身」
    这种低 IoU、高包含的关系压不住，画面上就是同一个人挂两个框。
    """
    out = []
    for b in sorted(persons, key=lambda k: (k[2] - k[0]) * (k[3] - k[1]), reverse=True):
        inner = False
        for k in out:
            ix = max(0.0, min(b[2], k[2]) - max(b[0], k[0]))
            iy = max(0.0, min(b[3], k[3]) - max(b[1], k[1]))
            area = (b[2] - b[0]) * (b[3] - b[1])
            if area > 0 and ix * iy / area >= contain:
                inner = True
                break
        if not inner:
            out.append(b)
    return out


@torch.inference_mode()
def detect_persons(model, frame, thr=0.35, min_size=24):
    h, w = frame.shape[:2]
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    t = torch.from_numpy(img).permute(2, 0, 1).float().div_(255.0)
    out = model([t])[0]
    boxes, scores, labels = out["boxes"], out["scores"], out["labels"]
    keep = []
    for b, s, l in zip(boxes.tolist(), scores.tolist(), labels.tolist()):
        if l != 1 or s < thr:          # COCO 里 1 = person
            continue
        x1, y1, x2, y2 = b
        if (x2 - x1) < min_size or (y2 - y1) < min_size:
            continue
        keep.append([round(x1 / w * 1000, 1), round(y1 / h * 1000, 1),
                     round(x2 / w * 1000, 1), round(y2 / h * 1000, 1), round(s, 3)])
    keep.sort(key=lambda k: k[4], reverse=True)
    return dedupe_contained(keep)


def times_for(dur: float, step: float):
    """与 qwen_boxes.gather 里的采样时刻保持一致。"""
    eff = max(step, dur / 60.0) if dur > step * 60 else step
    ts, t = [], eff / 2
    while t < dur:
        ts.append(t)
        t += eff
    return ts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="fasterrcnn", choices=list(MODELS))
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--thr", type=float, default=0.35)
    ap.add_argument("--min-size", type=int, default=640,
                    help="推理前把短边缩到多少（越小越快，人在这几个片子里都很大，640 够）")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()

    d = Path(a.clips)
    files = sorted(p for p in d.iterdir()
                   if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm"))
    if a.only:
        files = [p for p in files if p.name in a.only]
    if not files:
        raise SystemExit(f"{d} 下没有视频")

    print(f"加载 {a.model} …", flush=True)
    model = load(a.model, a.min_size)
    print("加载完成", flush=True)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(a.out, "w", encoding="utf-8") as f:
        for k, p in enumerate(files, 1):
            cap = cv2.VideoCapture(str(p))
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            dur = n / fps
            ts = times_for(dur, a.step)
            samples, tt = [], time.time()
            for i, t in enumerate(ts, 1):
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, fr = cap.read()
                if not ok:
                    continue
                persons = detect_persons(model, fr, thr=a.thr)
                samples.append([int(round(t * fps)), [["人物", *b[:4]] for b in persons]])
                if i % 10 == 0:
                    print(f"    {i}/{len(ts)} 帧，{(time.time() - tt) / i:.2f}s/帧", flush=True)
            cap.release()
            rec = {"clip": p.name, "fps": fps, "frames": n, "duration": round(dur, 2),
                   "samples": samples}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            tot = sum(len(s[1]) for s in samples)
            print(f"[{k}/{len(files)}] {p.name}: {len(samples)} 帧，{tot} 个人物框"
                  f"（平均 {tot / max(1, len(samples)):.1f} 人/帧，"
                  f"{(time.time() - tt) / max(1, len(samples)):.2f}s/帧）", flush=True)
    print(f"写出 {a.out}，耗时 {(time.time() - t0) / 60:.1f} 分钟")


if __name__ == "__main__":
    main()
