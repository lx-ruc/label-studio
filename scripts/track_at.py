"""打印某个时间点附近的轨迹关键帧，用来查「框为什么会在某一刻变成整屏」。

    .venv/bin/python scripts/track_at.py .tmp/boxes17.jsonl SD0022 89 --min-w 70
"""
import json
import sys


def main():
    path, clip_kw, t = sys.argv[1], sys.argv[2], float(sys.argv[3])
    min_w = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    rec = next(json.loads(l) for l in open(path, encoding="utf-8") if clip_kw in l)

    for r in rec["result"]:
        lab = r["value"]["labels"][0]
        seq = r["value"]["sequence"]
        hit = [k for k in seq if abs(k["time"] - t) <= 1.0 and k["width"] >= min_w]
        if not hit:
            continue
        print(f"track {r['id']} label={lab} keyframes={len(seq)}")
        for k in seq:
            mark = "  <=" if abs(k["time"] - t) < 0.02 else ""
            print(f"   t={k['time']:6.1f}  x{k['x']:5.1f} y{k['y']:5.1f} "
                  f"{k['width']:5.1f}x{k['height']:5.1f}{mark}")


if __name__ == "__main__":
    main()
