"""统计检测框里有多少是「被分块窗口切出来的」。

2×2 带 15% 重叠的分块，接缝落在 0-1000 坐标的 424~426 和 574~576 附近
（实测值）。框的任意一条边正好落在这两个位置，说明这块是「窗口边」而不是
「物体边」——这就是框不贴人的原因。

    .venv/bin/python scripts/seam_stats.py .tmp/dets7.jsonl
"""
import json
import sys
from collections import Counter

SEAMS = (424, 425, 426, 574, 575, 576)


def on_seam(v: float) -> bool:
    return any(abs(v - k) <= 2 for k in SEAMS)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ".tmp/dets7.jsonl"
    tot, seam, big = Counter(), Counter(), Counter()
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        for _, boxes in rec["samples"]:
            for lab, x1, y1, x2, y2 in boxes:
                tot[lab] += 1
                if on_seam(x1) or on_seam(x2) or on_seam(y1) or on_seam(y2):
                    seam[lab] += 1
                if (x2 - x1) * (y2 - y1) > 250000:
                    big[lab] += 1
    print(f"{'标签':<12}{'框数':>6}{'贴分块缝':>10}{'面积>25%':>10}")
    for lab, n in tot.most_common():
        print(f"{lab:<12}{n:>6}{seam[lab] / n * 100:>9.1f}%{big[lab] / n * 100:>9.1f}%")


if __name__ == "__main__":
    main()
