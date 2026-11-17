"""从 boxes jsonl（Label Studio result 格式）取某一时刻的框，画在整帧上。

比 crop_check 更直观：能一眼看出「一个框里是不是正好一个人」「有没有两个人
共用一个框」「框有没有切掉头脚」。

    .venv/bin/python scripts/render_frame.py --clips data/clips4 \
        --boxes .tmp/boxes12.jsonl --clip SD0022004522630060044.mp4 --t 89 --out /tmp/f.jpg
"""
import argparse
import json
from pathlib import Path

import cv2


def boxes_at(rec, t, label=None):
    """轨迹的 sequence 里，取 time 落在哪两个关键帧之间，线性插值出此刻的框。"""
    out = []
    for r in rec["result"]:
        lab = r["value"]["labels"][0]
        if label and lab != label:
            continue
        seq = [k for k in r["value"]["sequence"] if k.get("enabled", True)]
        prev = None
        for kf in seq:
            if kf["time"] <= t:
                prev = kf
            elif prev is not None:
                span = kf["time"] - prev["time"]
                k = (t - prev["time"]) / span if span > 0 else 0.0
                out.append((lab, tuple(prev[q] + (kf[q] - prev[q]) * k
                                       for q in ("x", "y", "width", "height"))))
                prev = None
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--boxes", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--t", type=float, required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rec = next(json.loads(l) for l in Path(a.boxes).read_text(encoding="utf-8").splitlines()
               if json.loads(l)["clip"] == a.clip)

    cap = cv2.VideoCapture(str(Path(a.clips) / a.clip))
    cap.set(cv2.CAP_PROP_POS_MSEC, a.t * 1000)
    ok, img = cap.read()
    if not ok:
        raise SystemExit("取帧失败")
    h, w = img.shape[:2]

    bs = boxes_at(rec, a.t, a.label)
    for i, (lab, (x, y, bw, bh)) in enumerate(bs):
        p1 = (int(x / 100 * w), int(y / 100 * h))
        p2 = (int((x + bw) / 100 * w), int((y + bh) / 100 * h))
        cv2.rectangle(img, p1, p2, (0, 0, 255), 2)
        cv2.putText(img, f"{i}", (p1[0] + 3, p1[1] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imwrite(a.out, img)
    print(f"{a.out}: {len(bs)} 个框")


if __name__ == "__main__":
    main()
