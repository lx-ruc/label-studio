#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qwen_boxes.refine_box 的坐标映射自测。

不调 API：把 detect() 换成一个假的，按给定的「局部坐标」返回子框，
然后检查映射回全图后的坐标是否等于手算值。
这个映射错了不会报错，只会让框整体偏移——比崩溃难查得多，所以单独测。

跑：.venv/bin/python scripts/test_refine.py
"""

import sys

import numpy as np

sys.path.insert(0, "scripts")
import qwen_boxes as qx  # noqa: E402

FAIL = 0


def check(name, got, want, tol=0.6):
    global FAIL
    ok = all(abs(g - w) <= tol for g, w in zip(got, want))
    print(f"  {'ok ' if ok else 'FAIL'} {name}: got {tuple(round(g, 1) for g in got)}"
          f" want {tuple(round(w, 1) for w in want)}")
    if not ok:
        FAIL += 1


W, H = 1088, 581
frame = np.zeros((H, W, 3), np.uint8)

# ---- 1. need_refine 阈值 ----
print("need_refine:")
print(f"  人物 全高竖条 h=960  -> {qx.need_refine('人物', (483, 39, 701, 999))} (应 True)")
print(f"  人物 小框 h=200      -> {qx.need_refine('人物', (100, 100, 200, 300))} (应 False)")
print(f"  器件 中等框          -> {qx.need_refine('工具', (100, 100, 300, 400))} (应 False)")

# ---- 2. 坐标映射 ----
# 父框：人物，x 483-701, y 39-999（就是截图里那条大竖条）
parent = (483.0, 39.0, 701.0, 999.0)
x1, y1, x2, y2 = qx._px(parent, W, H)
# refine_box 内部加的 padding：左右 6% 宽、上下 4% 高
cw, ch = x2 - x1, y2 - y1
cx1, cy1 = max(0, int(x1 - cw * 0.06)), max(0, int(y1 - ch * 0.04))
cx2, cy2 = min(W, int(x2 + cw * 0.06)), min(H, int(y2 + ch * 0.04))
crop_w, crop_h = cx2 - cx1, cy2 - cy1
print(f"\n裁剪区域: x {cx1}-{cx2} y {cy1}-{cy2}  ({crop_w}x{crop_h})")

# 假设模型在这个局部图里，把目标框在局部 (250-420, 300-660) /1000
# 这个尺寸映射回全图后 h≈360、面积≈1.5%，不触发二次细化，能干净地验一层映射
kid_local = (250.0, 300.0, 420.0, 660.0)
calls = []


def fake_detect(img_bytes, retries=3, prompt=qx.PROMPT):
    calls.append(prompt[:12])
    # 只回一个子框，且比父框小得多，保证能通过「没缩小就丢」的过滤
    return [("人物",) + kid_local]


qx.detect = fake_detect

kids = qx.refine_box(frame, parent, "人物", W, H)
print(f"refine_box 返回 {len(kids)} 个子框，detect 调用 {len(calls)} 次（应为 1）")
assert len(kids) == 1, kids
if len(calls) != 1:
    print("  FAIL 发生了意外的递归细化")
    FAIL += 1
got = kids[0]
want = (
    (cx1 + kid_local[0] / 1000 * crop_w) / W * 1000,
    (cy1 + kid_local[1] / 1000 * crop_h) / H * 1000,
    (cx1 + kid_local[2] / 1000 * crop_w) / W * 1000,
    (cy1 + kid_local[3] / 1000 * crop_h) / H * 1000,
)
check("子框映射回全图", got, want)
print(f"     子框面积占全幅 {(got[2]-got[0])*(got[3]-got[1])/1e4:.1f}%"
      f"（父框 {(parent[2]-parent[0])*(parent[3]-parent[1])/1e4:.1f}%）")

# ---- 2b. 子框还偏大时会再切一刀（只递归一层，别把 API 打成无底洞）----
calls.clear()


def fake_big(img_bytes, retries=3, prompt=qx.PROMPT):
    calls.append(1)
    return [("人物", 0.0, 0.0, 1000.0, 600.0)]


qx.detect = fake_big
qx.refine_box(frame, parent, "人物", W, H)
print(f"  子框仍偏大时：detect 调用 {len(calls)} 次（应为 2，递归一层后停）")
if len(calls) != 2:
    print("  FAIL 递归层数不对")
    FAIL += 1

# ---- 3. 模型没返回子框时必须保留父框，不能把要素弄丢 ----
print("\nrefine_box 兜底：")
qx.detect = lambda *a, **k: []
kept = qx.refine_box(frame, parent, "人物", W, H)
check("无子框时保留父框", kept[0], parent)

# ---- 4. 子框没缩小（跟父框一样大）要被丢掉 ----
qx.detect = lambda *a, **k: [("人物", 0.0, 0.0, 1000.0, 1000.0)]
kept = qx.refine_box(frame, parent, "人物", W, H)
check("没缩小的子框不算数", kept[0], parent)

# ---- 5. 标签不同的子框不接（避免和已有框重复）----
qx.detect = lambda *a, **k: [("服饰/头饰",) + kid_local]
kept = qx.refine_box(frame, parent, "人物", W, H)
check("异类子框不接", kept[0], parent)

# ---- 6. refine_frame 整体行为：全高人物框、细化失败 -> 丢弃 ----
print("\nrefine_frame 整体：")
qx.detect = lambda *a, **k: []
boxes = [("人物", 483.0, 39.0, 701.0, 999.0),          # 全高竖条，细化失败应被丢
         ("人物", 100.0, 600.0, 160.0, 700.0),          # 小框，原样保留
         ("工具", 800.0, 500.0, 900.0, 560.0)]          # 小框，原样保留
out, n_big, n_got = qx.refine_frame(frame, boxes, W, H)
print(f"  大框 {n_big} 个，缩小成功 {n_got} 个，输出 {len(out)} 个框")
for b in out:
    print(f"    {b[0]} x{b[1]:.0f} y{b[2]:.0f} w{b[3]-b[1]:.0f} h{b[4]-b[2]:.0f}")
if len(out) != 2 or any(b[0] == "人物" and b[4] - b[2] > 400 for b in out):
    print("  FAIL 全高人物框没有被丢掉")
    FAIL += 1

print("\n" + ("全部通过" if FAIL == 0 else f"{FAIL} 项失败"))
sys.exit(1 if FAIL else 0)
