"""把某一时刻的框画在画面上，用来肉眼确认框是否真的套住物体。

    .venv-detect/bin/python scripts/draw_boxes.py --clips data/clips4 \
        --dets .tmp/dets_person.jsonl --clip SD0022004522630060044.mp4 --t 89 --out /tmp/check.jpg
"""
import argparse
import json
from pathlib import Path

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--dets", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--t", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thick", type=int, default=2)
    a = ap.parse_args()

    rec = None
    for line in Path(a.dets).read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["clip"] == a.clip:
            rec = json.loads(line)
    if rec is None:
        raise SystemExit(f"{a.dets} 里没有 {a.clip}")

    fps = rec["fps"]
    want = a.t * fps
    fr_no, boxes = min(rec["samples"], key=lambda s: abs(s[0] - want))

    cap = cv2.VideoCapture(str(Path(a.clips) / a.clip))
    cap.set(cv2.CAP_PROP_POS_MSEC, a.t * 1000)
    ok, img = cap.read()
    if not ok:
        raise SystemExit("取帧失败")
    h, w = img.shape[:2]

    for i, b in enumerate(boxes):
        lab, x1, y1, x2, y2 = b[:5]
        p1 = (int(x1 / 1000 * w), int(y1 / 1000 * h))
        p2 = (int(x2 / 1000 * w), int(y2 / 1000 * h))
        cv2.rectangle(img, p1, p2, (0, 0, 255), a.thick)
        cv2.putText(img, str(i), (p1[0] + 2, p1[1] + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

    cv2.imwrite(a.out, img)
    print(f"{a.out}  帧 {fr_no}（t={fr_no / fps:.1f}s），{len(boxes)} 个框")


if __name__ == "__main__":
    main()
