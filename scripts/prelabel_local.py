#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 CPU 预标注：YOLOv8n + ByteTrack -> Label Studio videorectangle predictions

不需要 GPU、不需要联网请求任何 API（仅首次下载模型权重）。
用途：在无模型 API 的情况下跑通「预标注 -> 导入 -> 人工修正」这条链路，
      验证 VideoRectangle 的数据格式与界面呈现是否符合预期。

产出 preds_local.jsonl，可直接喂给 labelstudio/setup_project.py --predictions

注意：YOLOv8n 是 COCO 80 类通用模型，**不是为非遗场景训练的**。
它能可靠覆盖的只有 `person`（映射到 人物/传承人）等少数类别，
工具/材料类目标识别不了 —— 这是 Demo 的天花板，不是流程的问题。
真正生产请用见 `prelabel_video.py`（云端多模态）或回流训练自有检测器。
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fix_tempdir():
    """沙箱环境适配。

    tempfile 判断目录是否可用靠的是「写一个文件再删掉」，而本环境里删除操作
    会被安全护栏拦截，于是它把 /tmp、工作区等所有候选都判为不可用，最终抛
    FileNotFoundError。显式赋值 tempfile.tempdir 可以跳过这轮探测。
    正常环境下这一步是空操作。
    """
    import tempfile

    p = ROOT / ".tmp" / "pt"
    try:
        p.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(p)
    except Exception:
        pass


_fix_tempdir()
CLIPS = ROOT / "data" / "clips"
MODEL_VERSION = "yolov8n-cpu-bytetrack-v1"

# COCO 类别 -> 本项目标签体系（只映射有把握的，宁缺毋滥）
# COCO 共 80 类，索引 0~79。曾把剪刀误写成 87（越界），导致工具类一次都没检出过。
COCO_TO_LABEL = {
    0: "人物/传承人",     # person
    43: "工具/刻刀",      # knife
    76: "工具/剪刀",      # scissors
}
COCO_CLASSES = list(COCO_TO_LABEL.keys())
MIN_CONF = 0.35


def frames_meta(path: Path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.release()
    return n, fps


def build_prediction(tracks, frames_count, duration, model_version=MODEL_VERSION):
    """tracks: {track_id: {"label": str, "frames": [(frame_no, x, y, w, h)], "scores": [...]}}"""
    result, all_scores = [], []
    for tid, t in tracks.items():
        if not t["frames"]:
            continue
        result.append({
            "id": tid,
            "from_name": "box",
            "to_name": "video",
            "type": "videorectangle",
            "value": {
                "framesCount": frames_count,
                "duration": round(duration, 3),
                "sequence": [
                    {"frame": f, "x": round(x, 2), "y": round(y, 2),
                     "width": round(w, 2), "height": round(h, 2),
                     "enabled": True, "rotation": 0}
                    for f, x, y, w, h in sorted(t["frames"])
                ],
                "labels": [t["label"]],
            },
        })
        all_scores.extend(t["scores"])
    return {
        "model_version": model_version,
        "score": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0,
        "result": result,
    }


def prune_tracks(tracks, min_frames):
    """丢掉碎片段，只留下真正跟住的轨迹。

    ByteTrack 一旦目标被短暂遮挡就会分配新 ID，同一个人在 30 秒视频里能被切成
    十几条轨迹 —— 人在界面上看到的就是一堆只有两三帧的碎片，修正成本比重新画还高。
    这里按「记录到的帧数」设一道下限把它们滤掉。
    """
    keep, dropped = {}, 0
    for tid, t in tracks.items():
        if len(t["frames"]) >= min_frames:
            keep[tid] = t
        else:
            dropped += 1
    return keep, dropped


def check_prediction(pred):
    assert pred.get("model_version"), "缺 model_version"
    for r in pred["result"]:
        v = r["value"]
        assert r["type"] == "videorectangle", f"type 错: {r['type']}"
        assert v["framesCount"] > 0, "framesCount 必须为正"
        seq = v["sequence"]
        assert seq, "sequence 为空"
        assert min(s["frame"] for s in seq) >= 1, "帧号从 1 开始"
        for s in seq:
            assert 0 <= s["x"] <= 100 and 0 <= s["width"] <= 100, f"坐标越界: {s}"
            assert 0 <= s["y"] <= 100 and 0 <= s["height"] <= 100, f"坐标越界: {s}"
            assert s["frame"] <= v["framesCount"], f"帧号超出总帧数: {s['frame']}"
    return True


def run_one(model, clip: Path, step: int, imgsz: int, max_area: float = 0.6):
    """对单个片段做检测 + 跨帧跟踪，返回 tracks"""
    results = model.track(
        source=str(clip),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
        conf=MIN_CONF,
        classes=COCO_CLASSES,
        imgsz=imgsz,
    )
    tracks = defaultdict(lambda: {"label": None, "frames": [], "scores": []})
    frame_no = 0
    for r in results:
        frame_no += 1
        if step > 1 and (frame_no - 1) % step:
            continue
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            continue
        h, w = r.orig_shape
        ids = boxes.id
        clss = boxes.cls
        confs = boxes.conf
        xyxy = boxes.xyxy
        for i in range(len(clss)):
            tid_raw = ids[i] if ids is not None else None
            cls_id = int(clss[i])
            label = COCO_TO_LABEL.get(cls_id)
            if label is None:
                continue
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            x = max(0.0, min(100.0, x1 / w * 100))
            y = max(0.0, min(100.0, y1 / h * 100))
            bw = max(0.0, min(100.0 - x, (x2 - x1) / w * 100))
            bh = max(0.0, min(100.0 - y, (y2 - y1) / h * 100))

            # 面积闸门。低分辨率推理下最容易出现的误检是把整面墙/整块背景判成
            # person，框几乎糊满全屏 —— 这种框进了标注界面比没有还糟。
            # 近景人物实测最大也就占画面四成多，0.6 留足余量。
            area = (bw / 100.0) * (bh / 100.0)
            if area > max_area or area < 0.005:
                continue

            tid = f"track_{int(tid_raw):03d}" if tid_raw is not None else f"det_{frame_no}_{i}"
            t = tracks[tid]
            t["label"] = label
            t["frames"].append((frame_no, x, y, bw, bh))
            t["scores"].append(float(confs[i]))
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="*", help="指定片段文件名；不给则跑 --limit 个")
    ap.add_argument("--limit", type=int, default=8, help="跑前 N 个片段（默认 8）")
    ap.add_argument("--step", type=int, default=1, help="每隔 N 帧取一帧（默认 1，即逐帧）")
    ap.add_argument("--imgsz", type=int, default=480, help="推理边长，越小越快")
    ap.add_argument("--min-frames", type=int, default=3,
                    help="轨迹至少被记录到多少帧才保留，用于滤除 ID 碎片（默认 3）")
    ap.add_argument("--max-area", type=float, default=0.6,
                    help="单框面积占画面比例上限，滤除糊满全屏的误检（默认 0.6）")
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--out", default="preds_local.jsonl")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("请先安装：pip install ultralytics")

    print(f"加载模型 {args.weights} ...")
    model = YOLO(args.weights)

    if args.clips:
        targets = [CLIPS / c for c in args.clips]
    else:
        targets = sorted(CLIPS.glob("*.mp4"))[: args.limit]

    out_f = open(ROOT / args.out, "w", encoding="utf-8")
    ok = 0
    for clip in targets:
        if not clip.exists():
            print(f"[skip] {clip}")
            continue
        n, fps = frames_meta(clip)
        if n <= 0:
            print(f"[skip] 读不到帧数 {clip.name}")
            continue
        tracks = run_one(model, clip, args.step, args.imgsz, args.max_area)
        tracks, dropped = prune_tracks(tracks, args.min_frames)
        pred = build_prediction(tracks, n, n / fps if fps else 0.0)
        try:
            check_prediction(pred)
        except AssertionError as e:
            print(f"[schema 失败] {clip.name}: {e}")
            continue
        out_f.write(json.dumps({"video": str(clip), "prediction": pred},
                               ensure_ascii=False) + "\n")
        print(f"[ok] {clip.name}: {n}帧 {n/fps:.0f}s -> {len(pred['result'])} 条轨迹, "
              f"均分 {pred['score']}"
              + (f"（滤掉碎片 {dropped} 条）" if dropped else ""))
        ok += 1
    out_f.close()
    print(f"\n完成 {ok} 条 -> {args.out}")


if __name__ == "__main__":
    main()
