#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
非遗视频预标注流水线（A 档：纯云端 API，零 GPU）

抽帧去重 -> 云端多模态大模型出框 -> 帧间关联成 tracklet -> 组装 Label Studio predictions -> 导入

用法：
    # 1) 只生成 predictions JSON（推荐先这样跑，人工检查一遍再导入）
    python prelabel_video.py run ./clips --out preds.jsonl

    # 2) 确认无误后导入 Label Studio
    export LS_URL=http://localhost:8080
    export LS_TOKEN=xxxxxxxx
    python prelabel_video.py import preds.jsonl --project 1

依赖：
    pip install opencv-python requests
    env: DASHSCOPE_API_KEY（或改成你自己的多模态 API）
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import requests

# ----------------------------- 配置区 -----------------------------

API_URL = os.getenv("VLM_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
MODEL = os.getenv("VLM_MODEL", "qwen-vl-max-latest")

TARGET_FPS = 25        # 必须与转码帧率、LS 标注配置的 frameRate 三者一致
SAMPLE_FPS = 1         # 送模型的采样帧率（非遗视频镜头固定，1fps 足够）
HASH_THRESH = 6        # 感知哈希汉明距离 <= 该值视为重复帧，跳过（省 API 钱的关键）
MIN_SCORE = 0.5        # 模型返回置信度低于此值的框直接丢弃

LABELS = [
    "人物/传承人", "人物/学徒",
    "手部/左手", "手部/右手",
    "工具/刻刀", "工具/织梭", "工具/绣针", "工具/錾子",
    "材料/泥坯", "材料/丝线", "材料/木料",
    "成品/玉器", "成品/织锦",
    "设备/织机", "设备/窑炉",
]

MODEL_VERSION = "vlm-keyframe-v1"

PROMPT = f"""你是非物质文化遗产工艺视频的标注助手。
请在画面中定位以下类别的目标：{LABELS}

要求：
- 只输出 JSON，不要解释，不要 markdown 代码块，不要省略号。
- 坐标使用相对画面宽高的百分比（0-100），x/y 表示边界框左上角。
- 看不到的目标不要输出，宁缺毋滥。
- score 是你对该框的置信度（0-1）。

输出格式：
{{"objects":[{{"label":"工具/刻刀","x":12.4,"y":30.1,"w":18.2,"h":24.5,"score":0.9}}]}}"""

# ----------------------------- 工具函数 -----------------------------


def probe(video: str) -> tuple:
    """用 ffprobe 拿真实帧数和时长，比 cv2 的 CAP_PROP 可靠"""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=nb_frames,r_frame_rate:format=duration",
           "-of", "json", video]
    try:
        out = json.loads(subprocess.check_output(cmd, stderr=subprocess.DEVNULL))
        st = out["streams"][0]
        num, den = st.get("r_frame_rate", "25/1").split("/")
        fps = float(num) / float(den) if float(den) else 25.0
        n = int(st.get("nb_frames", 0)) or None
        dur = float(out.get("format", {}).get("duration", 0)) or None
        if n is None and dur:
            n = int(round(dur * fps))
        return (n or 0, dur or 0.0, fps)
    except Exception:
        cap = cv2.VideoCapture(video)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS
        cap.release()
        return n, (n / fps if fps else 0.0), fps


def dhash(img, size=8) -> int:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size))
    bits = 0
    for i in range(size * size):
        if g[i // size, i % size] > g[i // size, i % size + 1]:
            bits |= 1 << i
    return bits


def extract_keyframes(video: str, sample_fps: int = SAMPLE_FPS) -> list:
    """抽帧 + 感知哈希去重，返回 [(frame_no, bgr_image)]，frame_no 从 1 开始"""
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS
    step = max(1, int(round(src_fps / sample_fps)))

    frames, prev_h, idx = [], None, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % step:
            continue
        h = dhash(frame)
        if prev_h is not None and bin(h ^ prev_h).count("1") <= HASH_THRESH:
            continue          # 画面几乎没变，不值得花钱送模型
        prev_h = h
        frames.append((idx, frame))
    cap.release()
    return frames


def call_vlm(frame) -> list:
    """调用云端多模态大模型，返回原始 objects 列表"""
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return []
    b64 = base64.b64encode(buf.tobytes()).decode()
    payload = {
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
    }
    r = requests.post(API_URL,
                      headers={"Authorization": f"Bearer {API_KEY}",
                               "Content-Type": "application/json"},
                      json=payload, timeout=120)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"].strip()
    for fence in ("```json", "```"):
        if txt.startswith(fence):
            txt = txt[len(fence):]
    if txt.endswith("```"):
        txt = txt[:-3]
    try:
        return json.loads(txt.strip()).get("objects", [])
    except Exception:
        return []            # 大模型偶尔不守规矩，直接丢这帧，不要让流水线挂掉


def clean(obj: dict) -> dict:
    """校验并夹紧坐标。大模型输出的框必须过滤，否则前端渲染会炸"""
    if obj.get("label") not in LABELS:
        return None
    if float(obj.get("score", 0)) < MIN_SCORE:
        return None
    try:
        x, y, w, h = (float(obj[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if w < 0.5 or h < 0.5 or w > 100 or h > 100:
        return None
    x = min(max(x, 0.0), 100.0 - w)
    y = min(max(y, 0.0), 100.0 - h)
    return {"label": obj["label"], "x": x, "y": y, "w": w, "h": h,
            "score": float(obj.get("score", 0.8))}


def iou(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def associate(detections: dict, max_gap_frames: int = 3 * TARGET_FPS, iou_thresh: float = 0.3) -> dict:
    """把逐帧检测结果按「同类别 + IoU 匹配」串成 tracklet"""
    tracks, next_id = {}, 1
    for frame_no, objs in sorted(detections.items()):
        for o in objs:
            best, best_iou = None, iou_thresh
            for tid, t in tracks.items():
                if t["label"] != o["label"]:
                    continue
                if frame_no - t["last_frame"] > max_gap_frames:
                    continue
                i = iou(t["last_box"], (o["x"], o["y"], o["w"], o["h"]))
                if i > best_iou:
                    best, best_iou = tid, i
            if best is None:
                tid = f"track_{next_id:03d}"
                next_id += 1
                tracks[tid] = {"label": o["label"], "frames": [],
                               "last_box": None, "last_frame": frame_no,
                               "scores": []}
            else:
                tid = best
            t = tracks[tid]
            t["frames"].append((frame_no, o["x"], o["y"], o["w"], o["h"]))
            t["last_box"] = (o["x"], o["y"], o["w"], o["h"])
            t["last_frame"] = frame_no
            t["scores"].append(o["score"])
    return tracks


def build_prediction(tracks: dict, frames_count: int, duration: float) -> dict:
    """组装 Label Studio videorectangle predictions"""
    result, all_scores = [], []
    for tid, t in tracks.items():
        if len(t["frames"]) < 1:
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
        "model_version": MODEL_VERSION,
        "score": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0,
        "result": result,
    }


def check_prediction(pred: dict) -> bool:
    """导入前的 schema 自检，早发现早改"""
    assert pred.get("model_version"), "缺 model_version，无法做模型版本对比"
    for r in pred["result"]:
        v = r["value"]
        assert r["type"] == "videorectangle", f"type 错: {r['type']}"
        assert v["framesCount"] > 0, "framesCount 必须为正"
        seq = v["sequence"]
        assert seq, "sequence 为空"
        assert min(s["frame"] for s in seq) >= 1, "帧号必须从 1 开始"
        for s in seq:
            assert 0 <= s["x"] <= 100 and 0 <= s["width"] <= 100, f"坐标越界: {s}"
            assert 0 <= s["y"] <= 100 and 0 <= s["height"] <= 100, f"坐标越界: {s}"
            assert s["frame"] <= v["framesCount"], f"帧号超出总帧数: {s['frame']}"
    return True


# ----------------------------- 子命令 -----------------------------


def cmd_run(args):
    videos = sorted([p for p in Path(args.dir).rglob("*")
                     if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm")])
    if not videos:
        print(f"[!] {args.dir} 下没有找到视频", file=sys.stderr)
        return 1
    if not API_KEY:
        print("[!] 未设置 DASHSCOPE_API_KEY", file=sys.stderr)
        return 1

    out_f = open(args.out, "w", encoding="utf-8")
    total_api = 0
    for vp in videos[: args.limit] if args.limit else videos:
        n, dur, fps = probe(str(vp))
        if not n:
            print(f"[skip] 无法读取 {vp.name}")
            continue
        frames = extract_keyframes(str(vp), args.sample_fps)
        detections = {}
        for frame_no, img in frames:
            for o in call_vlm(img):
                c = clean(o)
                if c:
                    detections.setdefault(frame_no, []).append(c)
            total_api += 1
        tracks = associate(detections)
        pred = build_prediction(tracks, n, dur)
        try:
            check_prediction(pred)
        except AssertionError as e:
            print(f"[schema] {vp.name}: {e} —— 已跳过")
            continue
        out_f.write(json.dumps({"video": str(vp), "prediction": pred},
                               ensure_ascii=False) + "\n")
        print(f"[ok] {vp.name}: {n}帧/{dur:.1f}s, 送模型 {len(frames)} 帧, "
              f"轨迹 {len(pred['result'])} 条, 均分 {pred['score']}")
    out_f.close()
    print(f"\n完成：{args.out}（累计调用模型 {total_api} 次）")
    return 0


def cmd_import(args):
    ls, token = os.getenv("LS_URL", "http://localhost:8080"), os.getenv("LS_TOKEN")
    if not token:
        print("[!] 未设置 LS_TOKEN", file=sys.stderr)
        return 1
    headers = {"Authorization": f"Token {token}"}

    payload = []
    for line in open(args.jsonl, encoding="utf-8"):
        if not line.strip():
            continue
        item = json.loads(line)
        # 用 /data/local-files/ 形式引用本地文件；如走云存储，在这里换成 URL
        payload.append({"data": {"video": item["video"]},
                        "predictions": [item["prediction"]]})

    r = requests.post(f"{ls}/api/projects/{args.project}/import",
                      headers=headers, json=payload, timeout=300)
    r.raise_for_status()
    print(f"导入完成：{r.json().get('task_count', len(payload))} 条任务")
    return 0


def main():
    ap = argparse.ArgumentParser(description="非遗视频 Label Studio 预标注流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("run", help="生成 predictions JSONL")
    p1.add_argument("dir", help="视频目录（递归）")
    p1.add_argument("--out", default="preds.jsonl")
    p1.add_argument("--sample-fps", type=int, default=SAMPLE_FPS)
    p1.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    p1.set_defaults(func=cmd_run)

    p2 = sub.add_parser("import", help="导入 Label Studio")
    p2.add_argument("jsonl")
    p2.add_argument("--project", type=int, required=True)
    p2.set_defaults(func=cmd_import)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
