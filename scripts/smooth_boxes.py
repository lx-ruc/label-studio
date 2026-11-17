#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把框的尺寸/位置在时间轴上平滑一遍，消掉「忽大忽小」。

为什么需要：检测每 2 秒做一次，Qwen 对同一个人给的框尺寸每次都差一截
（实测相邻两次差 10%~100%）。关键帧之间 LSF 是线性插值，所以在每个检测帧上
框会「啪」地跳一下尺寸，然后 2 秒内匀速缩放回去——看上去就是忽大忽小。

做法：对每条轨迹的 宽/高/中心x/中心y 四条序列各做一次**双向**指数滑动平均
（正向一遍、反向一遍再取平均，相位抵消，不会滞后）。端点用原值锚住，
所以目标出现和消失那一帧的框不受影响。

尺寸的 τ 给大（默认 1.2 秒，突变摊开成缓变），位置给得小（0.35 秒，
人能跟得上，只是把单帧噪声磨掉）。

用法：
  python3 scripts/smooth_boxes.py --in .tmp/boxes8.jsonl --out .tmp/boxes9.jsonl
  python3 scripts/smooth_boxes.py --in ... --out ... --tau-size 0.8 --tau-pos 0.2
"""
import argparse
import json
import math


def fb_ema(vals, ts, tau):
    """双向指数滑动平均。tau 越大越平；端点保持原值。"""
    n = len(vals)
    if n < 3 or tau <= 0:
        return list(vals)
    alpha = [1.0 - math.exp(-max(1e-6, ts[i] - ts[i - 1]) / tau) for i in range(1, n)]

    fwd = [vals[0]]
    for i in range(1, n):
        fwd.append(fwd[-1] + alpha[i - 1] * (vals[i] - fwd[-1]))

    bwd = [0.0] * n
    bwd[-1] = vals[-1]
    for i in range(n - 2, -1, -1):
        bwd[i] = bwd[i + 1] + alpha[i] * (vals[i] - bwd[i + 1])

    return [(fwd[i] + bwd[i]) / 2.0 for i in range(n)]


def smooth_result(res, tau_size, tau_pos):
    seq = res["value"]["sequence"]
    live = [k for k in seq if k.get("enabled", True)]
    dead = [k for k in seq if not k.get("enabled", True)]
    if len(live) < 3:
        return 0

    ts = [float(k["time"]) for k in live]
    cx = [k["x"] + k["width"] / 2 for k in live]
    cy = [k["y"] + k["height"] / 2 for k in live]
    ws = [float(k["width"]) for k in live]
    hs = [float(k["height"]) for k in live]

    nws = fb_ema(ws, ts, tau_size)
    nhs = fb_ema(hs, ts, tau_size)
    ncx = fb_ema(cx, ts, tau_pos)
    ncy = fb_ema(cy, ts, tau_pos)

    for k, x, y, w, h in zip(live, ncx, ncy, nws, nhs):
        k["width"] = round(w, 2)
        k["height"] = round(h, 2)
        k["x"] = round(x - w / 2, 2)
        k["y"] = round(y - h / 2, 2)

    # 末尾那个 enabled=false 的帧跟着最后一下走，别留在旧位置
    last = live[-1]
    for k in dead:
        k["x"], k["y"] = last["x"], last["y"]
        k["width"], k["height"] = last["width"], last["height"]
    return len(live)


def measure(rec):
    rw, rh, dc = [], [], []
    for res in rec["result"]:
        live = [k for k in res["value"]["sequence"] if k.get("enabled", True)]
        for a, b in zip(live, live[1:]):
            dt = b["time"] - a["time"]
            if dt <= 0:
                continue
            rw.append(abs(b["width"] - a["width"]) / max(a["width"], 1e-6))
            rh.append(abs(b["height"] - a["height"]) / max(a["height"], 1e-6))
            dc.append((((a["x"] + a["width"] / 2) - (b["x"] + b["width"] / 2)) ** 2 +
                       ((a["y"] + a["height"] / 2) - (b["y"] + b["height"] / 2)) ** 2) ** 0.5)
    if not rw:
        return None
    p = lambda a, q: sorted(a)[min(len(a) - 1, int(len(a) * q))]
    jump = sum(1 for a, b in zip(rw, rh) if max(a, b) > 0.10) / len(rw) * 100
    return {"n": len(rw), "size_p50": p(rw, .5) * 100, "size_p99": p(rw, .99) * 100,
            "size_max": max(rw) * 100, "pos_p99": p(dc, .99), "jump10": jump}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--tau-size", type=float, default=1.2, help="尺寸平滑时间常数（秒）")
    ap.add_argument("--tau-pos", type=float, default=0.35, help="位置平滑时间常数（秒）")
    a = ap.parse_args()

    out = []
    for line in open(a.src, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        before = measure(rec)
        touched = sum(smooth_result(r, a.tau_size, a.tau_pos) for r in rec["result"])
        after = measure(rec)
        print(f"{rec['clip'][:34]:36s} 平滑 {touched} 条轨迹")
        if before and after:
            print(f"   尺寸单步变化  中位 {before['size_p50']:5.1f}% -> {after['size_p50']:5.1f}%"
                  f"   p99 {before['size_p99']:5.1f}% -> {after['size_p99']:5.1f}%"
                  f"   最大 {before['size_max']:6.1f}% -> {after['size_max']:6.1f}%")
            print(f"   单步跳 >10% 占 {before['jump10']:4.0f}% -> {after['jump10']:4.0f}%"
                  f"   中心位移 p99 {before['pos_p99']:4.1f} -> {after['pos_p99']:4.1f}")
        out.append(rec)

    with open(a.dst, "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n写出 {a.dst}（{len(out)} 条）")


if __name__ == "__main__":
    main()
