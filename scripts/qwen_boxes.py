#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Qwen3-VL 的视觉定位能力，在片段上框住出现的要素，产出 Label Studio
的 videorectangle 预标注。

为什么不用 YOLO-World（项目 1 那条路）：
  那套要 torch + ultralytics，本机环境清掉后重装是 2GB 起；而且它是开放词表检测，
  对「唐卡、经幡、芦笙」这类非遗专属物件召回很差，得手工调词表。
  Qwen3-VL 本身支持 grounding，直接问「框住画面里的人与物」就给坐标。

**第一版最大的错误（务必别再犯）**：匹配轨迹时不检查「上次出现是多久以前」。
于是某个框在两秒后消失、三十秒后又撞上另一个人，就被接成同一条轨迹，
LSF 从首帧插值到尾帧，画面上挂满几十个框——而这时画面里可能只有两个人。
现在强制「连续帧才算同一目标」，断档超过 max_age 个采样点就断开。

另外三个现实问题：
  1. 没有跟踪器。逐帧独立检测出来的框是散的，LS 的 sequence 要求同一条轨迹
     用同一个 id 贯穿。这里用贪心匹配（同类 + IoU，失配退中心距）。
  2. 坐标口径。LS 的 videorectangle 用百分比（0-100），模型给的是 0-1000。
  3. 输出不总是干净 JSON，解析要兜底。

用法（在服务器上跑，因为视频和 cv2 都在那边）：
  QWEN_API_KEY=... python3 scripts/qwen_boxes.py --clips data/clips4 \
      --out .tmp/boxes4.jsonl --step 2 --workers 6 --cache .tmp/dets4.jsonl

  有 --cache 时检测结果会存下来；再跑同一批片段直接读缓存，
  调跟踪参数不再重复调 API。
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = os.getenv("QWEN_VL_MODEL", "qwen3-vl-plus")

# 必须和 labelstudio/label_config_t12.xml 里 <Labels> 的值完全一致，否则 LS 拒收
ALLOWED = ["人物", "工具", "材料", "乐器", "法器/仪式物", "服饰/头饰", "设备", "场所元素"]

PROMPT = (
    "定位画面中的非遗要素，把可见的人与物分别框出来。\n"
    "要求：\n"
    "1. 每个人单独一个框，不要把人框成一整团；\n"
    "2. 乐器、法器、工具、材料、器物要单独框，不要只框人和衣服；\n"
    "3. 服饰/头饰只在特征明显时单独框（如银冠、刺绣围腰）；\n"
    "4. 框要贴合物体边界，不要留大片空白；上沿贴头顶、下沿贴脚，不要拉到画面上下边；\n"
    "5. 画面边缘被截断的人物也要框，但只框到被截断的那一侧为止。\n"
    "只输出 JSON 数组，不要解释、不要 markdown 代码块。\n"
    '格式：[{"label":"人物","bbox":[x1,y1,x2,y2]}, ...]\n'
    "bbox 用 0-1000 归一化坐标，x 向右、y 向下。\n"
    "label 只能取：" + "、".join(ALLOWED)
)

# 细化用：输入是从大画面里裁出来的一小块，画面里只有几个对象，
# 模型不用再考虑「远小近大」的整体布局，框能贴得紧得多。
REFINE_PROMPT = (
    "这是一张从大画面里裁出来的局部图，图里有非遗活动的人与物。\n"
    "要求：\n"
    "1. 每个人单独一个框；框的上沿贴头顶（有帽子/头饰就框到帽子顶），"
    "下沿贴脚底或这块图的底边，左右贴身体外沿；\n"
    "2. 框内不要留天空、远山、地面、草地这类背景；\n"
    "3. 不要把人框成一整团，不要把几个人并成一个框；\n"
    "4. 只框明显可见的对象，模糊到看不清的不要框；\n"
    "5. 被这块图边缘截断的对象也框，框到图边为止。\n"
    "只输出 JSON 数组，不要解释、不要 markdown 代码块。\n"
    '格式：[{"label":"人物","bbox":[x1,y1,x2,y2]}, ...]\n'
    "bbox 用 0-1000 归一化坐标，相对这张局部图。x 向右、y 向下。\n"
    "label 只能取：" + "、".join(ALLOWED)
)


# ---------------------------------------------------------------- API
def detect(img_bytes: bytes, retries: int = 3, prompt: str = PROMPT):
    """一帧 -> [(label, x1, y1, x2, y2)]，坐标 0-1000。"""
    b64 = base64.b64encode(img_bytes).decode()
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            {"type": "text", "text": prompt},
        ]}],
    }
    data = json.dumps(body).encode()
    last = None
    for i in range(retries):
        req = urllib.request.Request(API, data=data, headers={
            "Authorization": "Bearer " + os.environ["QWEN_API_KEY"],
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = json.loads(r.read())["choices"][0]["message"]["content"]
            return parse(txt)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.read().decode('utf-8', 'replace')[:160]}"
            if e.code in (429, 500, 502, 503):
                time.sleep(1.5 * (i + 1))
                continue
            break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.0 * (i + 1))
    print(f"    [警告] 检测失败：{last}", file=sys.stderr)
    return []


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def parse(txt: str):
    """模型输出兜底解析：去围栏、抠数组、NMS 去重、逐项校验。"""
    s = txt.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    a, b = s.find("["), s.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        raw = json.loads(s[a:b + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        lab = str(it.get("label") or "").strip()
        if lab not in ALLOWED:
            hit = next((x for x in ALLOWED if lab.startswith(x.split("/")[0]) and x.split("/")[0]), None)
            if not hit:
                continue
            lab = hit
        bb = it.get("bbox") or it.get("box") or []
        if not (isinstance(bb, list) and len(bb) == 4):
            continue
        try:
            x1, y1, x2, y2 = [float(v) for v in bb]
        except (TypeError, ValueError):
            continue
        if max(x1, y1, x2, y2) > 1000.5:      # 像素坐标，换算不了，丢
            continue
        x1, x2 = sorted((max(0.0, x1), min(1000.0, x2)))
        y1, y2 = sorted((max(0.0, y1), min(1000.0, y2)))
        if x2 - x1 < 20 or y2 - y1 < 20:      # 太小的是噪声
            continue
        # 超过画面 65% 的框没有信息量（模型把整片背景/人群圈成一团），
        # 还会把真正的要素盖住，直接丢
        if (x2 - x1) * (y2 - y1) > 0.65 * 1000 * 1000:
            continue
        out.append((lab, x1, y1, x2, y2))

    # 同标签内部做 NMS：模型偶尔给同一个人两个几乎重合的框
    out.sort(key=lambda b: (b[2] - b[1]) * (b[4] - b[3]), reverse=True)
    keep = []
    for b in out:
        if all(b[0] != k[0] or iou((b[1], b[2], b[3], b[4]), (k[1], k[2], k[3], k[4])) < 0.7
               for k in keep):
            keep.append(b)
    return keep


# ---------------------------------------------------------------- 跟踪
def center_dist(a, b):
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def size_ok(a, b, lo=0.55, hi=1.8):
    """两个框的尺寸是不是一个量级。

    补这个的原因：只看中心距时，一个 5% 宽的小框能接上 21% 宽的大框——
    两个采样点之间，同一个人不可能从「远处小人」变成「近处大人」，
    这种匹配实际上是把 A 的轨迹接到了 B 身上，画面上看就是框「嗖」地跳走。
    """
    ha, hb = a[3] - a[1], b[3] - b[1]
    wa, wb = a[2] - a[0], b[2] - b[0]
    if ha <= 0 or hb <= 0 or wa <= 0 or wb <= 0:
        return False
    return lo <= hb / ha <= hi and 0.4 <= wb / wa <= 2.5


class Track:
    __slots__ = ("label", "box", "seq", "last_i")

    def __init__(self, label, box, frame, i):
        self.label = label
        self.box = box
        self.seq = [(frame, box)]
        self.last_i = i

    @property
    def hits(self):
        return len(self.seq)


def build_tracks(samples, max_age=1, thr=0.12, max_center=160.0):
    """samples: [(frame, [boxes])] 按时间升序 -> [Track]

    关键是 **max_age**：只允许和「最近 max_age 个采样点内出现过」的轨迹续接。
    采样间隔 2 秒时 max_age=1 意味着目标消失超过 4 秒就断开、另起一条。
    不做这个限制的话轨迹会跨越整条片子，LS 会把首尾之间全程插值，
    画面上就挂满早已离开的目标——这是第一版最严重的错误。
    """
    tracks = []
    for i, (frame, boxes) in enumerate(samples):
        claimed = set()
        for lab, x1, y1, x2, y2 in boxes:
            box = (x1, y1, x2, y2)
            best, best_iou = None, thr
            for t in tracks:
                if t.label != lab or id(t) in claimed:
                    continue
                if i - t.last_i > max_age:          # 断档太久，不许续
                    continue
                if not size_ok(t.box, box):
                    continue
                v = iou(t.box, box)
                if v > best_iou:
                    best, best_iou = t, v
            if best is None:                        # IoU 没接上，退一步看中心点
                dmin, cand = max_center, None
                for t in tracks:
                    if t.label != lab or id(t) in claimed:
                        continue
                    if i - t.last_i > max_age:
                        continue
                    if not size_ok(t.box, box):
                        continue
                    d = center_dist(t.box, box)
                    if d < dmin:
                        dmin, cand = d, t
                best = cand
            if best is not None:
                best.box = box
                best.seq.append((frame, box))
                best.last_i = i
                claimed.add(id(best))
            else:
                t = Track(lab, box, frame, i)
                tracks.append(t)
                claimed.add(id(t))
    return tracks


def to_result(seq_items, label, frames_count, cfg_fps, idx):
    """一条轨迹 -> LS videorectangle 的一条 result。

    末尾补一个 enabled=false 的关键帧：LSF 各版本对「只在关键帧区间内显示」
    这一行为解释不完全一致，补一个关闭帧，无论按哪种规则，目标离开后框都会消失。
    """
    seq = []
    for frame, (x1, y1, x2, y2) in seq_items:
        seq.append({
            "frame": int(frame),
            "enabled": True,
            "x": round(x1 / 10.0, 2),
            "y": round(y1 / 10.0, 2),
            "width": round((x2 - x1) / 10.0, 2),
            "height": round((y2 - y1) / 10.0, 2),
            "rotation": 0,
            "time": round(frame / cfg_fps, 3),
        })
    last = seq[-1]
    seq.append({
        "frame": int(last["frame"] + 1),
        "enabled": False,
        "x": last["x"], "y": last["y"],
        "width": last["width"], "height": last["height"],
        "rotation": 0,
        "time": round((last["frame"] + 1) / cfg_fps, 3),
    })
    return {
        "id": f"{label}_{seq_items[0][0]}_{idx}",
        "from_name": "tag",          # 必须是 Labels 控件的名字，不是 VideoRectangle 的 box
        "to_name": "video",
        "type": "videorectangle",
        "value": {
            "framesCount": int(frames_count),
            "duration": round(frames_count / cfg_fps, 3),
            "sequence": seq,
            "labels": [label],
        },
    }


# ---------------------------------------------------------------- 分块检测
def _contains(a, b):
    """b 有多少落在 a 里（交集 / b 的面积）。"""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return ix * iy / ab if ab > 0 else 0.0


def merge_boxes(boxes, iou_thr=0.3):
    """同标签去重，留**面积小**的那个。小块更贴人。"""
    boxes = sorted(boxes, key=lambda b: (b[3] - b[1]) * (b[4] - b[2]))
    keep = []
    for b in boxes:
        dup = False
        for k in keep:
            if k[0] != b[0]:
                continue
            if iou((b[1], b[2], b[3], b[4]), (k[1], k[2], k[3], k[4])) > iou_thr \
                    or _contains((k[1], k[2], k[3], k[4]), (b[1], b[2], b[3], b[4])) > 0.55:
                dup = True
                break
        if not dup:
            keep.append(b)
    return keep


def detect_tiled(frame, grid=2, overlap=0.15, target=1400):
    """把整帧切成 grid×grid 带重叠的小块，逐块识别，再合并。

    为什么要这么做：整帧丢给模型时，远景里几十个像素高的人它看不清，
    就把「一群人」框成一条从山顶拉到画面底的竖条——用户看到的「大框没框到人」。
    切块并放大后，同一个人在一块里占几百像素，模型才会一个个框。

    用 PROMPT 而不是 REFINE_PROMPT：细化那套要求「模糊的不要框」，
    放在分块上会把器物、材料筛掉（实测同一帧 10 个框掉到 2 个）。

    跨块截断：贴着块边缘的目标先标成 tentative，只有当它被完整框覆盖时才丢。
    全丢会把真实目标一起丢掉——重叠 15% 保证它在邻块里有完整的一份。
    """
    if grid <= 1:
        buf = _jpg(frame)
        return [(b[0], b[1], b[2], b[3], b[4]) for b in detect(buf)] if buf else []

    H, W = frame.shape[:2]
    tw, th = W / grid, H / grid
    solid, tentative = [], []
    for gy in range(grid):
        for gx in range(grid):
            x1 = max(0, int(gx * tw - tw * overlap))
            y1 = max(0, int(gy * th - th * overlap))
            x2 = min(W, int((gx + 1) * tw + tw * overlap))
            y2 = min(H, int((gy + 1) * th + th * overlap))
            tile = frame[y1:y2, x1:x2]
            if tile.size == 0:
                continue
            k = max(1.0, target / max(tile.shape[1], tile.shape[0]))
            if k > 1.02:
                tile = cv2.resize(tile, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
            buf = _jpg(tile)
            if buf is None:
                continue
            tw_px, th_px = x2 - x1, y2 - y1
            for lab, kx1, ky1, kx2, ky2 in detect(buf, prompt=PROMPT):
                m = 12.0                     # 0-1000 里 12 约合 1.2%，贴边容差
                touch = ((kx1 < m and x1 > 0) or (ky1 < m and y1 > 0)
                         or (kx2 > 1000 - m and x2 < W) or (ky2 > 1000 - m and y2 < H))
                b = (lab,
                     (x1 + kx1 / 1000 * tw_px) / W * 1000,
                     (y1 + ky1 / 1000 * th_px) / H * 1000,
                     (x1 + kx2 / 1000 * tw_px) / W * 1000,
                     (y1 + ky2 / 1000 * th_px) / H * 1000)
                (tentative if touch else solid).append(b)

    solid = merge_boxes(solid)
    # 贴边的那些，只要有完整框盖住它就不要；否则留着，宁多勿漏
    rest = []
    for b in sorted(tentative, key=lambda b: (b[3] - b[1]) * (b[4] - b[2])):
        covered = any(b[0] == s[0] and
                      (iou((b[1], b[2], b[3], b[4]), (s[1], s[2], s[3], s[4])) > 0.3
                       or _contains((s[1], s[2], s[3], s[4]), (b[1], b[2], b[3], b[4])) > 0.5)
                      for s in solid)
        if not covered:
            rest.append(b)
    return merge_boxes(solid + rest)


# ---------------------------------------------------------------- 大框细化
def _jpg(frame, q=92):
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])
    return bytes(buf) if ok else None


def _px(box, W, H):
    return (box[0] / 1000 * W, box[1] / 1000 * H, box[2] / 1000 * W, box[3] / 1000 * H)


def need_refine(lab, box):
    """这个框是不是「太大、没贴住东西」，值得切出来放大重认。

    实测：本条片子里「人物」框高度中位数是全画幅的 62%，543 个里有 377 个超过 42%。
    远景人群加上「人物」这个词本身很笼统，模型会给一条从山坡拉到画面底的竖条，
    框里一个完整的人都没有。阈值按标签分开定——人比器物更容易被拉满。
    """
    w, h = box[2] - box[0], box[3] - box[1]
    if lab == "人物":
        return h > 400 or w * h > 80000
    return w * h > 60000 or h > 550


def refine_box(frame, box, lab, W, H, level=0):
    """把过大的框切出来放大，让模型在这块小图里重新找。返回替换用的框列表。

    粗定位 -> 裁图 -> 放大 -> 细定位 -> 坐标映射回全图。

    这就是「大框慢慢缩小去找人」：框大本身不算错，错在直接拿它用。
    把框里的内容放大到 1200px 再看一遍，模型才分得清一个人和一片人群——
    远景里那个 80×200 像素的人，在原图里只占几十个像素。
    """
    x1, y1, x2, y2 = _px(box, W, H)
    cw, ch = x2 - x1, y2 - y1
    if cw < 24 or ch < 24:
        return [box]
    # 留一点余量：模型需要看到人的完整轮廓，卡死在框边上会把头和脚切掉
    cx1, cy1 = max(0, int(x1 - cw * 0.06)), max(0, int(y1 - ch * 0.04))
    cx2, cy2 = min(W, int(x2 + cw * 0.06)), min(H, int(y2 + ch * 0.04))
    if cx2 - cx1 < 24 or cy2 - cy1 < 24:
        return [box]
    crop = frame[cy1:cy2, cx1:cx2]
    k = min(4.0, max(1.0, 1200.0 / max(crop.shape[1], crop.shape[0])))
    if k > 1.02:
        crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    buf = _jpg(crop)
    if buf is None:
        return [box]

    kids = detect(buf, prompt=REFINE_PROMPT)
    cw_px, ch_px = cx2 - cx1, cy2 - cy1
    parea = (box[2] - box[0]) * (box[3] - box[1])
    out = []
    for kl, kx1, ky1, kx2, ky2 in kids:
        if kl != lab:                        # 只接同类子框，避免和已有的框重复
            continue
        gx1 = (cx1 + kx1 / 1000 * cw_px) / W * 1000
        gx2 = (cx1 + kx2 / 1000 * cw_px) / W * 1000
        gy1 = (cy1 + ky1 / 1000 * ch_px) / H * 1000
        gy2 = (cy1 + ky2 / 1000 * ch_px) / H * 1000
        gw, gh = gx2 - gx1, gy2 - gy1
        if gw * gh < 1200:                   # 千分之一画幅以下当噪声
            continue
        if gw * gh > parea * 0.85:           # 没缩小，等于白问
            continue
        out.append((gx1, gy1, gx2, gy2))
    if not out:
        return [box]
    if level < 1:                            # 子框还可能偏大，再切一次；只递归一层
        nxt = []
        for sub in out:
            nxt.extend(refine_box(frame, sub, lab, W, H, level + 1)
                       if need_refine(lab, sub) else [sub])
        out = nxt
    return out


def refine_frame(frame, boxes, W, H):
    """整帧过一遍：大框换成细框，其余原样保留。返回 (新框列表, 大框数, 缩小成功数)。"""
    out, n_big, n_got = [], 0, 0
    for lab, x1, y1, x2, y2 in boxes:
        box = (x1, y1, x2, y2)
        if not need_refine(lab, box):
            out.append((lab, x1, y1, x2, y2))
            continue
        n_big += 1
        subs = refine_box(frame, box, lab, W, H)
        if len(subs) == 1 and tuple(subs[0]) == box:
            # 裁开放大也没找到更像的东西。高度接近整幅的「人物」几乎肯定是
            # 把人群/背景圈成一团，留着只会糊住画面，直接丢
            if lab == "人物" and (box[3] - box[1]) > 780:
                continue
            out.append((lab, x1, y1, x2, y2))
        else:
            n_got += 1
            for s in subs:
                out.append((lab, s[0], s[1], s[2], s[3]))
    return out, n_big, n_got


def refine_pass(cache_in: Path, cache_out: Path, clips_dir: Path, workers: int):
    """对已有检测缓存做一遍大框细化，产出新缓存。

    只对「有大框的采样帧」调 API，已经细化过的片段跳过——
    基线检测的钱不重复花。
    """
    done = set()
    if cache_out.exists():
        for line in cache_out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["clip"])
    recs = [json.loads(x) for x in cache_in.read_text(encoding="utf-8").splitlines() if x.strip()]

    for k, rec in enumerate(recs, 1):
        clip = rec["clip"]
        if clip in done:
            print(f"  [{k}/{len(recs)}] {clip}: 已细化，跳过")
            continue
        path = clips_dir / clip
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            print(f"  [跳过] 打不开 {path}", file=sys.stderr)
            continue

        todo = [(fr, boxes) for fr, boxes in rec["samples"]
                if any(need_refine(b[0], (b[1], b[2], b[3], b[4])) for b in boxes)]
        print(f"  [{k}/{len(recs)}] {clip}: {len(rec['samples'])} 个采样帧，"
              f"{len(todo)} 帧有大框要细化", flush=True)

        jobs = []
        for fr, boxes in todo:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
            ok, frame = cap.read()
            if ok:
                jobs.append((fr, boxes, frame))
        cap.release()

        def work(j):
            fr, boxes, frame = j
            H, W = frame.shape[:2]
            return (fr,) + refine_frame(frame, boxes, W, H)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            got = {fr: (new, nb, ng) for fr, new, nb, ng in pool.map(work, jobs)}

        samples, tb, tg = [], 0, 0
        for fr, boxes in rec["samples"]:
            if fr in got:
                new, nb, ng = got[fr]
                tb, tg = tb + nb, tg + ng
                samples.append([fr, [list(b) for b in new]])
            else:
                samples.append([fr, boxes])
        before = sum(len(b) for _, b in rec["samples"])
        after = sum(len(b) for _, b in samples)
        print(f"    -> 大框 {tb} 个，缩小成功 {tg} 个，框总数 {before} -> {after}", flush=True)

        with open(cache_out, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(rec, samples=samples), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 光流传播
def seed(gray, box, W, H, maxp=48):
    """在框内取角点作为光流跟踪点。box 是 (x1,y1,x2,y2)，坐标 0-1000，这里换成像素。"""
    x1 = max(0, int(box[0] / 1000 * W))
    y1 = max(0, int(box[1] / 1000 * H))
    x2 = min(W, int(box[2] / 1000 * W))
    y2 = min(H, int(box[3] / 1000 * H))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    p = cv2.goodFeaturesToTrack(gray[y1:y2, x1:x2], maxCorners=maxp,
                                qualityLevel=0.01, minDistance=4)
    if p is None:
        return None
    p = p.reshape(-1, 2)
    p[:, 0] += x1
    p[:, 1] += y1
    return p


def flow(prev, cur, st, W, H):
    """用 LK 光流把上一帧的框挪到当前帧。

    只算**平移 + 轻微缩放**：人走路时框的主要变化是位移，
    算旋转/仿射的收益抵不过误差放大。缩放按特征点离散度的比值估计并夹在
    0.94~1.06，防止某一帧估算炸掉之后一路崩到底。
    """
    pts, box = st["pts"], st["box"]
    if pts is None or len(pts) < 4:
        st["pts"] = seed(prev, box, W, H)
        return box
    nxt, status, _ = cv2.calcOpticalFlowPyrLK(
        prev, cur, pts.reshape(-1, 1, 2).astype(np.float32), None,
        winSize=(21, 21), maxLevel=3)
    good = status.reshape(-1) == 1
    if good.sum() < 6:                       # 点跟丢了大半，重新撒点，框原地不动
        st["pts"] = seed(prev, box, W, H)
        return box
    p0 = pts[good]
    p1 = nxt.reshape(-1, 2)[good]
    d = p1 - p0
    dx, dy = float(np.median(d[:, 0])), float(np.median(d[:, 1]))
    bw = (box[2] - box[0]) / 1000 * W
    bh = (box[3] - box[1]) / 1000 * H
    # 单帧位移超过框的大半，多半是特征点跳到旁边的人身上了，原地不动等下一个关键帧
    if (dx * dx + dy * dy) ** 0.5 > 0.6 * max(bw, bh):
        st["pts"] = seed(prev, box, W, H)
        return box
    s0 = float(np.std(p0, axis=0).mean()) + 1e-6
    s1 = float(np.std(p1, axis=0).mean()) + 1e-6
    scale = min(1.06, max(0.94, s1 / s0))
    nw = (box[2] - box[0]) * scale
    nh = (box[3] - box[1]) * scale
    # 尺寸锚回「上一次 Qwen 检测给的框」：单帧夹在 0.94~1.06 不够，
    # 10 帧连乘能到 1.79 倍，框会一路涨到满画幅——这正是「框越跟越大」的来源。
    rw, rh = st.get("rw"), st.get("rh")
    if rw and rh:
        nw = min(max(nw, rw * 0.80), rw * 1.20)
        nh = min(max(nh, rh * 0.80), rh * 1.20)
    cx = (box[0] + box[2]) / 2 + dx / W * 1000
    cy = (box[1] + box[3]) / 2 + dy / H * 1000
    nx1 = min(max(0.0, cx - nw / 2), max(0.0, 1000.0 - nw))
    ny1 = min(max(0.0, cy - nh / 2), max(0.0, 1000.0 - nh))
    st["pts"] = p1
    return (nx1, ny1, nx1 + min(nw, 1000.0), ny1 + min(nh, 1000.0))


def propagate(video_path, tracks, prop_step=5):
    """把稀疏的 Qwen 关键帧，用光流补成逐帧轨迹。

    单次顺序解码，所有轨迹一起推进——一个片段只读一遍视频。

    每个 Qwen 检测帧都**强制重置**框和特征点：Qwen 给的框是权威位置，
    光流只负责「两帧之间怎么走」，累计误差不会超过一个关键帧间隔（2 秒）。
    """
    kfmap, last_kf = {}, {}
    for ti, t in enumerate(tracks):
        for fr, box in t.seq:
            kfmap.setdefault(int(fr), []).append((ti, box))
        last_kf[ti] = int(t.seq[-1][0])
    if not kfmap:
        return {}

    start, end = min(kfmap), max(last_kf.values())
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    out = {ti: [] for ti in range(len(tracks))}
    state, prev_gray, W, H = {}, None, None, None

    fno = start
    while fno <= end:
        ok, frame = cap.read()
        if not ok:
            break
        if W is None:
            H, W = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        resets = dict(kfmap.get(fno, []))
        for ti, det in resets.items():
            # 正常情况下检测框是权威位置，直接对齐。但如果它和跟踪框差得太远
            # （IoU < 0.35），两个可能：光流跟丢了，或者这次检测落到别人身上。
            # 后者更常见——直接拽过去，画面上就是框「嗖」地跳到另一个人那儿。
            # 这种情况保留跟踪框，只重新撒点，等下一次检测再校。
            st = state.get(ti)
            box = det if (st is None or iou(st["box"], det) >= 0.35) else st["box"]
            state[ti] = {"box": box, "pts": seed(gray, box, W, H),
                         "rw": box[2] - box[0], "rh": box[3] - box[1]}
            out[ti].append((fno, box))

        for ti in list(state):
            if ti in resets:
                continue
            if fno > last_kf[ti]:
                del state[ti]
                continue
            if prev_gray is not None:
                state[ti]["box"] = flow(prev_gray, gray, state[ti], W, H)
            if fno % prop_step == 0:
                out[ti].append((fno, state[ti]["box"]))

        prev_gray = gray
        fno += 1
    cap.release()
    return out


# ---------------------------------------------------------------- 主流程
def gather(path: Path, step: float, workers: int, cache_path: Path, tile: int = 2):
    """抽帧 + 检测。有缓存就直接用，省 API 钱。"""
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec["clip"] == path.name:
                print(f"  {path.name}: 读缓存（{len(rec['samples'])} 帧）")
                return rec
    if not os.getenv("QWEN_API_KEY"):
        sys.exit("没有缓存且未设置 QWEN_API_KEY")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"打不开 {path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    dur = n / fps

    eff = max(step, dur / 60.0) if dur > step * 60 else step
    times, t = [], eff / 2
    while t < dur:
        times.append(t)
        t += eff

    print(f"  {path.name}: {dur:.1f}s, {n} 帧, fps {fps:.1f}, 采样 {len(times)} 帧（间隔 {eff:.1f}s）")

    frames = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if ok:
            frames.append((t, bytes(buf)))
    cap.release()

    def work(item):
        t, buf = item
        if tile <= 1:
            return t, detect(buf)
        # 存的是 JPEG 字节（省内存），分块要从像素裁，这里解回来
        arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return t, detect(buf)
        return t, detect_tiled(arr, grid=tile)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(work, frames))

    # 帧号按素材真实 fps 记，推送到 LS 时再统一换算到配置帧率
    samples = [[int(round(t * fps)), boxes] for t, boxes in sorted(got, key=lambda x: x[0])]
    rec = {"clip": path.name, "fps": fps, "frames": n, "duration": round(dur, 2),
           "samples": samples}
    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _h_overlap(a, b):
    """横向重叠占较窄那个宽度的比例。"""
    ox = min(a[2], b[2]) - max(a[0], b[0])
    return max(0.0, ox) / max(1e-6, min(a[2] - a[0], b[2] - b[0]))


def _v_gap(a, b):
    """上下缝隙，负数表示重叠。"""
    return max(a[1], b[1]) - min(a[3], b[3])


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


# 2×2 分块、15% 重叠时，窗口边界在归一化 0-1000 坐标里是固定的：
# 上半块覆盖 0~575、下半块覆盖 425~1000，左右同理。跟素材分辨率无关。
SEAM_OUT, SEAM_IN = 575.0, 425.0


def _at(v, target, tol=8.0):
    return abs(v - target) <= tol


def _same_object_fragments(a, b):
    """a、b 是不是同一个物体被分块窗口切开的两半。

    只认一种几何特征：一个框的下边正好贴在窗口下边界（575），另一个的上边正好
    贴在下一块窗口的上边界（425）。这两条边只可能来自分块，不可能是物体自己的
    边界，所以拼起来一定是同一个物体。左右切同理。

    这样就不会把「上一个人 / 下一个人」误拼成一个巨框——那种情况下两条边都落在
    575，或者都不在接缝上，判据不成立。
    """
    if _at(a[3], SEAM_OUT) and _at(b[1], SEAM_IN):
        return True
    if _at(b[3], SEAM_OUT) and _at(a[1], SEAM_IN):
        return True
    if _at(a[2], SEAM_OUT) and _at(b[0], SEAM_IN):
        return True
    if _at(b[2], SEAM_OUT) and _at(a[0], SEAM_IN):
        return True
    return False


def merge_seam_fragments(boxes):
    """同一标签里、被分块窗口切开的碎片取并集。

    每个框最多只拼一次，拼出来的并集不再参与后续拼接。试过连锁（反复迭代到
    稳定），结果一列碎片会一路并成 513×998 这种半屏巨框——人群里每两个相邻的
    人都能在接缝上连成一片。宁可留下两段，也不要再造巨框。
    """
    cur = [tuple(b) for b in boxes]
    used = [False] * len(cur)
    out = []
    for i in range(len(cur)):
        if used[i]:
            continue
        a = cur[i]
        for j in range(i + 1, len(cur)):
            if used[j] or cur[j][0] != a[0]:
                continue
            if _same_object_fragments(a[1:], cur[j][1:]):
                a = (a[0],) + _union(a[1:], cur[j][1:])
                used[j] = True
                break
        out.append(a)
    return out


def tidy_boxes(boxes, contain=0.6):
    """收拾 Qwen 的框：把被分块窗口切开的碎片拼回整体，再去掉同标签里的套娃。

    「人物」不参与拼接。人物框由 det_person.py 的检测器给（准、贴人）；
    没有检测器时保持 Qwen 原样——实测一拼就出 771×999 这种整屏框，
    因为 Qwen 给的「人物」本身就是窗口大小的块，两块一并不就是半屏。
    """
    others = [tuple(b) for b in boxes if b[0] != "人物"]
    persons = [tuple(b) for b in boxes if b[0] == "人物"]
    merged = merge_seam_fragments(others) + persons
    merged.sort(key=lambda b: -(b[3] - b[1]) * (b[4] - b[2]))
    keep = []
    for b in merged:
        if any(k[0] == b[0] and _contains(k[1:], b[1:]) > contain for k in keep):
            continue
        keep.append(b)
    return keep


# 由 det_person.py 产出的「人物」检测结果：{片名: {帧号: [框, ...]}}
# Qwen 给的「人物」框边界会落在分块窗口上，不是人。有真检测器结果就用它替换。
PERSON_DETS: dict[str, dict[int, list]] = {}

# 相邻两个采样点之间允许的最大中心位移（0-1000 单位）。检测器给的框更贴人，
# 相邻采样点上同一个人的中心不会跑太远；但跳舞的人动作大，160（16% 画幅）偏紧。
MAX_CENTER = 160.0

# 从人物框派生「服饰/头饰」：这类要素长在人身上，与其让 Qwen 在分块图里猜
# （实测 33% 的框边贴着分块缝），不如直接按人体结构切。头饰取头顶段——这几条
# 片子里全是苗族银冠，特征最明显；服饰取躯干段，避开腿。
DERIVE_CLOTHES = False
# 一个人就是一个「服饰/头饰」实例，只出一条。取 8%~62%（头顶略下到胸腹），
# 让它明显是人物框里的子区域——取 0~75% 时和人物框几乎重合，看着像重复框。
CLOTHES_FRAC = (0.08, 0.62)


def _plausible_person(b, lo=0.12, hi=0.85, max_area=600000.0):
    """这个框像不像一个站着的人。

    检测器偶尔会把「一群人」整体当成一个人：实测出现过 x 4~99、y 0~100
    （95%×99%、长宽比 0.95）的框。人是竖长的，宽高比落在 0.12~0.85，
    面积也不该超过画幅的 60%。
    """
    x1, y1, x2, y2 = b[-4:]
    w, h = x2 - x1, y2 - y1
    if h <= 0:
        return False
    return lo <= w / h <= hi and w * h <= max_area


def load_person_dets(path) -> None:
    p = Path(path)
    kept = drop = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        per = {}
        for fr, boxes in rec["samples"]:
            good = [list(b) for b in boxes if _plausible_person(b)]
            drop += len(boxes) - len(good)
            kept += len(good)
            per[int(fr)] = good
        PERSON_DETS[rec["clip"]] = per
    print(f"  人物检测：{p.name} 里 {len(PERSON_DETS)} 片，"
          f"留下 {kept} 个框（丢掉不像人的 {drop} 个）")


def clean_person_tracks(results):
    """把人物轨迹里「不成人形」的关键帧剔掉。

    光流在人群密集、遮挡严重的地方会一路放大：实测有一条轨迹从 50% 画幅
    宽长到 95%，t=89 时那个框满屏、什么也没圈住。检测框本身有合理性检查，
    但光流补出来的帧没有，所以这里补一道。
    """
    out, dropped_frames, dropped_tracks = [], 0, 0
    for r in results:
        if r["value"]["labels"][0] != "人物":
            out.append(r)
            continue
        seq = r["value"]["sequence"]
        good = [k for k in seq if _plausible_person(
            (k["x"] * 10, k["y"] * 10, (k["x"] + k["width"]) * 10, (k["y"] + k["height"]) * 10))]
        dropped_frames += len(seq) - len(good)
        if len(good) < 2:
            dropped_tracks += 1
            continue
        r["value"]["sequence"] = good
        out.append(r)
    if dropped_frames:
        print(f"    -> 剔掉不成人形的关键帧 {dropped_frames} 个、整条轨迹 {dropped_tracks} 条")
    return out


def process(rec, cfg_fps: float, max_age: int, min_hits: int,
            video_path: Path | None = None, prop_step: int = 5):
    # 分块识别会把一个人竖着切成好几段（头一段、胸一段、银饰上一根细条），
    # 这里按帧收拾一次：先把竖着叠在一起的碎片拼回一个人，再去掉被大框包住的套娃。
    # 放在 process 里而不是 detect_tiled 里，是为了不改缓存也能生效——
    # 调阈值不用重新调 API。
    pdet = PERSON_DETS.get(rec["clip"])
    samples, hit = [], 0
    for fr, boxes in rec["samples"]:
        boxes = [tuple(b) for b in boxes]
        got = None
        if pdet is not None:
            # 检测器给的框本来就贴人、且同一帧里是互相独立的两个人，
            # 拼碎片/去套娃都不能用在它们身上，否则会把前后两个人并成一个巨框。
            boxes = [b for b in boxes if b[0] != "人物"]
            got = pdet.get(int(fr))
            if got is not None:
                hit += 1
        boxes = tidy_boxes(merge_boxes(boxes, iou_thr=0.25))
        if got is not None:
            # det_person 写的是 ["人物", x1, y1, x2, y2, 置信度]，取最后四个坐标
            persons = [("人物",) + tuple(b[-4:]) for b in got]
        else:
            persons = [b for b in boxes if b[0] == "人物"]
        if DERIVE_CLOTHES:
            # Qwen 的「服饰/头饰」框是分块碎片，直接丢掉，换人体结构派生的
            boxes = [b for b in boxes if b[0] != "服饰/头饰"]
            f0, f1 = CLOTHES_FRAC
            for _, x1, y1, x2, y2 in persons:
                h = y2 - y1
                band = (x1, round(y1 + h * f0, 1), x2, round(y1 + h * f1, 1))
                if band[3] - band[1] >= 25:
                    boxes.append(("服饰/头饰",) + band)
        boxes = boxes + persons
        samples.append((fr, boxes))
    if pdet is not None:
        print(f"    人物框来自检测器：{hit}/{len(samples)} 帧对齐")
    tracks = build_tracks(samples, max_age=max_age, max_center=MAX_CENTER)

    # 只闪过一帧的多半是误检，先筛掉，别把光流算力浪费在它们身上
    keep = [t for t in tracks if t.hits >= min_hits]
    dropped = len(tracks) - len(keep)

    # 光流逐帧传播：Qwen 每 2 秒给一个权威框，中间用 LK 补到每 prop_step 帧一个。
    # 关键帧间隔从 2 秒降到 0.2 秒，LSF 的直线插值误差肉眼就看不出来了。
    seqs = None
    if video_path is not None and prop_step > 0 and keep:
        try:
            prop = propagate(video_path, keep, prop_step=prop_step)
            seqs = [prop.get(i) or keep[i].seq for i in range(len(keep))]
        except Exception as e:
            print(f"    [光流失败，退回关键帧插值] {type(e).__name__}: {e}", file=sys.stderr)

    results, seq_lens = [], []
    for i, t in enumerate(keep):
        raw = seqs[i] if seqs is not None else t.seq
        # 关键帧号按配置帧率重算：素材可能是 44.5fps，而 LS 按 frameRate 解释帧号
        seq = [(int(round(fr / rec["fps"] * cfg_fps)), b) for fr, b in raw]
        # 换算帧率后可能有两帧落到同一号上，合并，保证 frame 严格递增
        dedup = []
        for fr, b in seq:
            if dedup and fr <= dedup[-1][0]:
                dedup[-1] = (dedup[-1][0], b)      # 同一帧只留最后一个框
            else:
                dedup.append((fr, b))
        if len(dedup) < 2:                    # 塌成一帧的轨迹在画面上等于闪一下，丢掉
            continue
        results.append(to_result(dedup, t.label, round(rec["duration"] * cfg_fps), cfg_fps, i))
        seq_lens.append(len(dedup))

    boxes_total = sum(len(b) for _, b in samples)
    kept = len(results)
    mode = f"光流 {prop_step} 帧" if seqs is not None else "原始关键帧"
    print(f"    -> 检测框 {boxes_total} 个，成轨迹 {kept} 条"
          f"（丢弃单帧 {dropped} 条），关键帧共 {sum(seq_lens)} 个（{mode}），"
          f"单条最长 {max(seq_lens) if seq_lens else 0}")

    # 并发度自检：任一时刻最多有几条轨迹同时可见。这个数应该接近画面里实际的人数
    events = []
    for r in results:
        s = r["value"]["sequence"]
        events.append((s[0]["frame"], 1))
        events.append((s[-1]["frame"], -1))
    cur = peak = 0
    for _, d in sorted(events, key=lambda x: (x[0], x[1])):
        cur += d
        peak = max(peak, cur)
    print(f"    -> 同一时刻最多同时可见 {peak} 条轨迹")

    return {"clip": rec["clip"], "fps": rec["fps"], "frames": rec["frames"],
            "duration": rec["duration"], "result": clean_person_tracks(results)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=".tmp/dets.jsonl", help="检测结果缓存（避免重复调 API）")
    ap.add_argument("--step", type=float, default=2.0, help="采样间隔秒数")
    ap.add_argument("--tile", type=int, default=2,
                    help="整帧切成 tile×tile 小块分别识别再合并（1=不分块）。"
                         "不分块时远景人物会被框成一整条竖条")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cfg-fps", type=float, default=25.0, help="标注配置里的 frameRate")
    ap.add_argument("--max-age", type=int, default=1,
                    help="允许断档几个采样点仍算同一目标（0=必须逐帧连续）")
    ap.add_argument("--min-hits", type=int, default=2, help="少于几个关键帧的轨迹丢弃")
    ap.add_argument("--prop-step", type=int, default=5,
                    help="光流补帧间隔（帧）。0=不补，退回关键帧插值。5 在 25fps 下约 0.2 秒一个关键帧")
    ap.add_argument("--no-flow", action="store_true", help="等价于 --prop-step 0")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refine-from", default=None,
                    help="先对这份旧缓存做一遍大框细化，结果写进 --cache")
    ap.add_argument("--no-refine", action="store_true",
                    help="跳过细化，直接用缓存的原始框（调试用）")
    ap.add_argument("--max-center", type=float, default=160.0,
                    help="相邻采样点之间允许的最大中心位移（0-1000 单位）")
    ap.add_argument("--derive-clothes", action="store_true",
                    help="丢掉 Qwen 的「服饰/头饰」，从检测器的人物框按人体结构派生")
    ap.add_argument("--person-dets", default=None,
                    help="det_person.py 产出的人物检测缓存；给了就用它替换 Qwen 的「人物」框")
    a = ap.parse_args()

    d = Path(a.clips)
    files = sorted(p for p in d.iterdir()
                   if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm"))
    if a.only:
        files = [p for p in files if p.name in a.only]
    if not files:
        sys.exit(f"{d} 下没有视频")

    cache = Path(a.cache)
    prop_step = 0 if a.no_flow else a.prop_step
    out, t0 = [], time.time()

    global MAX_CENTER, DERIVE_CLOTHES
    MAX_CENTER = a.max_center
    DERIVE_CLOTHES = a.derive_clothes
    if a.person_dets:
        load_person_dets(a.person_dets)

    if a.refine_from and not a.no_refine:
        print(f"== 大框细化：{a.refine_from} -> {cache}")
        refine_pass(Path(a.refine_from), cache, d, a.workers)

    for k, p in enumerate(files, 1):
        print(f"[{k}/{len(files)}] {p.name}")
        try:
            rec = gather(p, a.step, a.workers, cache, a.tile)
            out.append(process(rec, a.cfg_fps, a.max_age, a.min_hits, p, prop_step))
        except Exception as e:
            print(f"    [失败] {type(e).__name__}: {e}", file=sys.stderr)

    with open(a.out, "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n写出 {a.out}（{len(out)} 条，耗时 {(time.time() - t0) / 60:.1f} 分钟）")


if __name__ == "__main__":
    main()
