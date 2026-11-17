#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比：现有提示词 vs 「先数人数、每人一个完整身体框」提示词。

重点看两件事：框数是否接近真实人数（不再一人多框），
以及框的高度是否覆盖整个人（而不是只框到胸口）。

用法：.venv/bin/python scripts/try_person_prompt.py 片段名 时间 [输出.jpg]
"""
import sys

import cv2

sys.path.insert(0, "scripts")
import qwen_boxes as qx  # noqa: E402

CLIP = sys.argv[1]
T = float(sys.argv[2])
OUT = sys.argv[3] if len(sys.argv) > 3 else ".tmp/prompt_cmp.jpg"

PERSON = (
    "先数清楚这张图里有几个人。然后**从左边第一个开始，一个人一个框，框出完整的人**。\n"
    "规则：\n"
    "1. 一个人只能有一个框，**绝对不要**把同一个人的头、身体、衣服、饰品分别框成几个框；\n"
    "2. 框的上沿贴他的头顶（戴帽子/头饰就框到帽顶），下沿贴他的脚底；\n"
    "   脚在画面外时就框到画面底边；\n"
    "3. 框的左右贴他身体的最外侧（肩膀或手臂），不要把旁边的人框进来；\n"
    "4. 被前面的人挡住大半个、只露出一点点的，不要框；\n"
    "5. 除了人，只额外框明显的乐器、法器、大型工具，且它们各自一个框。\n"
    "只输出 JSON 数组，不要解释、不要 markdown 代码块。\n"
    '格式：[{"label":"人物","bbox":[x1,y1,x2,y2]}, ...]\n'
    "bbox 用 0-1000 归一化坐标，相对这张图。label 只能取：" + "、".join(qx.ALLOWED)
)

cap = cv2.VideoCapture(f"data/clips4/{CLIP}")
cap.set(cv2.CAP_PROP_POS_MSEC, T * 1000)
ok, frame = cap.read()
cap.release()
if not ok:
    sys.exit("取帧失败")
H, W = frame.shape[:2]
print(f"{CLIP} t={T}s 帧 {W}x{H}")


def run(grid, prompt, tag):
    H_, W_ = frame.shape[:2]
    tw, th = W_ / grid, H_ / grid
    boxes = []
    for gy in range(grid):
        for gx in range(grid):
            x1 = max(0, int(gx * tw - tw * 0.15))
            y1 = max(0, int(gy * th - th * 0.15))
            x2 = min(W_, int((gx + 1) * tw + tw * 0.15))
            y2 = min(H_, int((gy + 1) * th + th * 0.15))
            tile = frame[y1:y2, x1:x2]
            k = max(1.0, 1400.0 / max(tile.shape[1], tile.shape[0]))
            if k > 1.02:
                tile = cv2.resize(tile, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
            ok, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, 92])
            tw_px, th_px = x2 - x1, y2 - y1
            for lab, kx1, ky1, kx2, ky2 in qx.detect(bytes(buf), prompt=prompt):
                boxes.append((lab,
                              (x1 + kx1 / 1000 * tw_px) / W_ * 1000,
                              (y1 + ky1 / 1000 * th_px) / H_ * 1000,
                              (x1 + kx2 / 1000 * tw_px) / W_ * 1000,
                              (y1 + ky2 / 1000 * th_px) / H_ * 1000))
    merged = qx.merge_boxes(boxes)
    persons = [b for b in merged if b[0] == "人物"]
    print(f"  {tag:22s} 原始 {len(boxes):2d} 合并后 {len(merged):2d}，其中人物 {len(persons)}")
    for b in persons:
        print(f"      x{b[1]:4.0f} y{b[2]:4.0f} w{b[3]-b[1]:4.0f} h{b[4]-b[2]:4.0f}"
              f"  高占画幅 {(b[4]-b[2])/10:.0f}%")
    return persons


a = run(2, qx.PROMPT, "2x2 现有提示词")
b = run(2, PERSON, "2x2 人物完整框")
c = run(3, PERSON, "3x3 人物完整框")


def draw(persons, tag):
    im = frame.copy()
    for p in persons:
        cv2.rectangle(im, (int(p[1] / 1000 * W), int(p[2] / 1000 * H)),
                      (int(p[3] / 1000 * W), int(p[4] / 1000 * H)), (60, 60, 235), 2)
    cv2.putText(im, tag, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    return im


h = 520
ims = []
for ps, tag in [(a, f"A 2x2 现有 {len(a)}"), (b, f"B 2x2 完整 {len(b)}"), (c, f"C 3x3 完整 {len(c)}")]:
    im = draw(ps, tag)
    ims.append(cv2.resize(im, (int(im.shape[1] * h / im.shape[0]), h)))
cv2.imwrite(OUT, cv2.hconcat(ims), [cv2.IMWRITE_JPEG_QUALITY, 92])
print(f"写出 {OUT}")
