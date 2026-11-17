"""看一眼某一帧的原始检测框，以及 tidy_boxes 之后变成什么样。

用途：验证「碎片拼人」到底把谁和谁拼到了一起，避免把前后两个人
（远处那个在上、近处那个在下）拼成一个巨框。

    python3 scripts/frag_probe.py --dets .tmp/dets7.jsonl --clip 芦笙 --t 89
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qwen_boxes import tidy_boxes, _h_overlap, _v_gap  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dets", required=True)
    ap.add_argument("--clip", default="")
    ap.add_argument("--t", type=float, default=89.0)
    ap.add_argument("--frames", type=int, default=1, help="以 t 为中心看几帧")
    a = ap.parse_args()

    recs = []
    with open(a.dets, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    recs = [r for r in recs if a.clip in r["clip"]]
    if not recs:
        sys.exit(f"没找到片名含「{a.clip}」的记录")

    for rec in recs:
        fps = rec["fps"]
        want = round(a.t * fps)
        samples = sorted(rec["samples"], key=lambda s: abs(s[0] - want))[: a.frames]
        for fr, boxes in sorted(samples):
            print(f"\n=== {rec['clip']}  frame {fr}  (t={fr / fps:.1f}s)  "
                  f"{len(boxes)} 框 @0-1000 ===")
            for b in boxes:
                lab, x1, y1, x2, y2 = b
                w, h = x2 - x1, y2 - y1
                print(f"  {lab:6s} x {x1:4.0f}~{x2:4.0f}  y {y1:4.0f}~{y2:4.0f}  "
                      f"{w:3.0f}x{h:3.0f}  长宽比 {w / max(1e-6, h):.2f}")

            ps = [tuple(b[1:5]) for b in boxes if b[0] == "人物"]
            print(f"  -- 人物两两关系（横向重叠 / 上下缝隙）:")
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    ho, vg = _h_overlap(ps[i], ps[j]), _v_gap(ps[i], ps[j])
                    if ho > 0.2:
                        print(f"     #{i}~#{j}: 横向重叠 {ho:.2f}  上下缝隙 {vg:+.0f}")

            out = tidy_boxes([tuple(b) for b in boxes])
            print(f"  -- tidy 之后 {len(out)} 框:")
            for b in out:
                lab, x1, y1, x2, y2 = b
                print(f"  {lab:6s} x {x1:4.0f}~{x2:4.0f}  y {y1:4.0f}~{y2:4.0f}  "
                      f"{x2 - x1:3.0f}x{y2 - y1:3.0f}")


if __name__ == "__main__":
    main()
