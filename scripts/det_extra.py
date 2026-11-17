"""补三类实体的检测：食物与供品（Qwen grounding）、身体部位（mediapipe 手部）。

群体单元不从图里检测——它由人物框聚类派生（≥3 人相邻成队才算），在
add_extra_tracks.py 里做。

    # 食物与供品：Qwen grounding，和 qwen_boxes 一样按 2 秒采样
    .venv/bin/python scripts/det_extra.py --kind food \
        --clips data/clips4 --out .tmp/dets_food.jsonl

    # 身体部位（手）：mediapipe，模型随 pip 包自带，不用下载
    .venv-detect/bin/python scripts/det_extra.py --kind hands \
        --clips data/clips4 --out .tmp/dets_hands.jsonl
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

FOOD_PROMPT = (
    "定位画面里的食物与供品：节日食物（如糌粑、饺子、糯米饭）、供品祭品"
    "（如摆上供桌的三牲、水果、糕点、纸钱香烛之外的供奉物）。\n"
    "要求：\n"
    "1. 每一样单独一个框，框要贴住食物本体，不要把整张桌子、整口锅都框进去；\n"
    "2. 生食、半成品、成品都算；包装里看不清内容的不框；\n"
    "3. 画面里没有就返回空数组，不要硬找。\n"
    "只输出 JSON 数组，不要解释、不要 markdown 代码块。\n"
    '格式：[{"label":"食物","bbox":[x1,y1,x2,y2]}, ...]\n'
    "bbox 用 0-1000 归一化坐标，x 向右、y 向下。\n"
)

HAND_MIN_SCORE = 0.4
HAND_MIN_SIZE = 18          # 0-1000 单位，小于这个的手多半是远处噪声
HAND_MAX_SIZE = 320         # 关键点偶尔跑飞，包围盒会炸成半个身子，卡上限


def times_for(dur: float, step: float):
    """与 qwen_boxes.gather 相同的采样时刻，帧号才能和人物检测对齐。"""
    eff = max(step, dur / 60.0) if dur > step * 60 else step
    ts, t = [], eff / 2
    while t < dur:
        ts.append(t)
        t += eff
    return ts


def open_video(clips_dir: Path, name: str):
    cap = cv2.VideoCapture(str(clips_dir / name))
    if not cap.isOpened():
        raise RuntimeError(f"打不开 {name}")
    return cap


def detect_food(cap, fps: float, n: int, dur: float, step: float, workers: int):
    from concurrent.futures import ThreadPoolExecutor

    import qwen_boxes
    from qwen_boxes import detect, parse

    # qwen_boxes.parse 只认旧十二项词表 ALLOWED，「食物」会被整批丢弃；
    # 这里临时扩充词表再调用，不影响其它流程。
    qwen_boxes.ALLOWED = list(qwen_boxes.ALLOWED) + [
        "食物", "食物与供品", "供品", "祭品", "糕点", "水果", "点心", "饭菜"]

    ts = times_for(dur, step)
    frames = []
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            frames.append((t, bytes(buf)))

    def work(item):
        t, buf = item
        boxes = detect(buf, prompt=FOOD_PROMPT)
        # 模型自拟的 label 统一改成「食物与供品」，只留坐标
        return t, [("食物与供品", *b[1:]) for b in boxes]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(work, frames))
    print(f"    {len(frames)} 帧，{(time.time() - t0) / max(1, len(frames)):.1f}s/帧",
          flush=True)
    return [[int(round(t * fps)), boxes] for t, boxes in got]


def detect_hands(cap, fps: float, n: int, dur: float, step: float):
    import mediapipe as mp

    hands = mp.solutions.hands.Hands(
        static_image_mode=True, max_num_hands=6,
        min_detection_confidence=HAND_MIN_SCORE)
    ts = times_for(dur, step)
    samples = []
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        res = hands.process(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        boxes = []
        if res.multi_hand_landmarks:
            for lm, hd in zip(res.multi_hand_landmarks or [],
                              res.multi_handedness or []):
                score = hd.score if hasattr(hd, "score") else 1.0
                if score < HAND_MIN_SCORE:
                    continue
                xs = [p.x * w for p in lm.landmark]
                ys = [p.y * h for p in lm.landmark]
                pad = 0.15
                x1 = max(0.0, min(xs) - (max(xs) - min(xs)) * pad) / w * 1000
                x2 = min(1000.0, max(xs) + (max(xs) - min(xs)) * pad) / w * 1000
                y1 = max(0.0, min(ys) - (max(ys) - min(ys)) * pad) / h * 1000
                y2 = min(1000.0, max(ys) + (max(ys) - min(ys)) * pad) / h * 1000
                if x2 - x1 < HAND_MIN_SIZE or y2 - y1 < HAND_MIN_SIZE:
                    continue
                w_b, h_b = x2 - x1, y2 - y1
                if max(w_b, h_b) > HAND_MAX_SIZE:
                    continue
                if not (0.3 <= w_b / h_b <= 3.2):
                    continue
                side = hd.classification[0].label if hd.classification else ""
                name = {"Left": "左手", "Right": "右手"}.get(side, "手")
                boxes.append((f"身体部位·{name}", round(x1, 1), round(y1, 1),
                              round(x2, 1), round(y2, 1)))
        samples.append([int(round(t * fps)), boxes])
    hands.close()
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["food", "hands"], required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()

    d = Path(a.clips)
    files = sorted(p for p in d.iterdir()
                   if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm"))
    if a.only:
        files = [p for p in files if p.name in a.only]

    with open(a.out, "w", encoding="utf-8") as f:
        for k, p in enumerate(files, 1):
            cap = open_video(d, p.name)
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            dur = n / fps
            if a.kind == "food":
                samples = detect_food(cap, fps, n, dur, a.step, a.workers)
            else:
                samples = detect_hands(cap, fps, n, dur, a.step)
            cap.release()
            rec = {"clip": p.name, "fps": fps, "frames": n,
                   "duration": round(dur, 2), "samples": samples}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            tot = sum(len(s[1]) for s in samples)
            print(f"[{k}/{len(files)}] {p.name}: {tot} 个框", flush=True)
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
