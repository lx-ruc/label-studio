#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开放词汇预标注：YOLO-World + ByteTrack -> Label Studio videorectangle predictions

与 `prelabel_local.py` 的区别：
  那个用 YOLOv8n（COCO 80 类固定词表），只能出 person 等通用类别，
  工具和材料基本检测不到。
  这个用 YOLO-World，词表由提示词现场指定 —— 你写什么它就去找什么，
  不再受 80 类限制。因此能覆盖「剪刀、刻刀、竹篾、丝线」这类非遗专属目标。

同样不需要 GPU、不需要 API Key（首次运行会下载 CLIP 文本编码器，约 338 MB）。

产出 preds_world.jsonl，可直接喂给 labelstudio/setup_project.py --predictions --predictions-only

注意：YOLO-World 的文本塔源自 CLIP，训练语料以英文为主，
所以提示词一律用英文，检出后映射回中文标签（见 WORLD_PROMPTS）。

v3 起，词表**按门类拆开**（见 CATEGORY_PROMPTS）：每个片段只喂它工艺上真正
会用到的 4~6 个词，而不是全段统一 16 个。

**为什么拆、以及拆的代价（实测，别想当然）**

YOLO-World 的类间关系不是 softmax 竞争。`ContrastiveHead` 算的是逐类余弦相似度
（`cos(x, w_k) * logit_scale + bias`），数学上各类互不影响。但它的 `ImagePoolingAttn`
会拿**图像特征对整组文本嵌入做注意力聚合**，再把聚合结果送进 `C2fAttn` 颈部——
于是词表会经由**图像特征**反向影响每一个类的分数。这个影响没有语义逻辑：

    剪纸片段，6 词基线 → red paper 最高分 0.23
    只多加一个 "embroidery"（绣品，语义上八竿子打不着）→ 0.52
    回到 16 词全量 → 0.52
    只给一个 "red paper" → 0.03

所以「词表越窄分数越高」是**错的**，方向完全不固定。40 段全量的实测后果：

    串门框（工艺上不该出现的标签）  32 条 → 0 条        ← 实打实的收益
    非人物合法轨迹                  165 → 108          ← 掉了约 25 条
    人物轨迹                        128 → 184          ← 涨了 56 条

也就是说 v3 是「更干净但更少」，不是无脑更好。按「漏了比错了更贵」的标准，
这笔账未必划算。

**结论**：类词表不该靠语义推理手工裁，必须在**每个门类各标一小段金标准集**，
用召回/精确率实测定谁更好。这也是不做微调时唯一能收敛的做法。
对比工具：`scripts/ab_prompts.py`（同片段跑两遍）、`scripts/compare_versions.py`（两版全量对账）。
"""

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "data" / "clips"


def _fix_tempdir():
    """见 prelabel_local.py 同名函数：绕过沙箱下 tempfile 的目录探测失败。"""
    p = ROOT / ".tmp" / "pt"
    try:
        p.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(p)
    except Exception:
        pass


_fix_tempdir()

# 英文提示词 -> 本项目标签体系
# 提示词怎么写很关键：CLIP 认的是「通用视觉概念」，太生僻或太抽象它会失效。
# 比如 "bamboo strip"（竹篾）比 "zhumei" 有效，"carving knife" 比 "雕刻工具" 有效。
WORLD_PROMPTS = {
    "person": "人物/传承人",
    "hand": "手部/左手",
    "scissors": "工具/剪刀",
    "carving knife": "工具/刻刀",
    "embroidery needle": "工具/绣针",
    # 别改回 "writing brush"：实测它对毛笔的响应只有 0.041，
    # 而阈值是 0.20，差 5 倍，一条都检不出来（01_传统技艺 四段零检出就是这么来的）。
    # "brush in hand" 实测 0.687、24 采样帧里命中 14 帧 —— 模型其实认得，是词没对上。
    "brush in hand": "工具/毛笔",
    "hammer": "工具/锤",
    "red paper": "材料/纸张",
    "bamboo strip": "材料/竹篾",
    "wooden block": "材料/木料",
    "clay": "材料/泥坯",
    "silk thread": "材料/丝线",
    "paper cutting": "成品/剪纸",
    "embroidery": "成品/绣品",
    "bamboo basket": "成品/竹编",
    "loom": "设备/织机",
}

# 按门类定制提示词（v3 的核心改动）
#
# 初衷：让每个门类只看到自己工艺上的对象，去掉跨门类误检。
# 实测确实做到了——40 段全量的串门框从 32 条降到 0 条。
#
# **但代价必须知道**：词表一变，各类的分数会整体重排，而且方向没有语义逻辑。
# 实测（剪纸片段）：6 词时 `red paper` 最高 0.23，只多加一个语义无关的
# `embroidery` 就涨到 0.52；反过来，从 16 词裁到 6 词时 `材料/纸张` 从 13 条
# 掉到 0 条、`成品/竹编` 从 17 条掉到 1 条。机制见模块 docstring。
#
# 所以下面这张表是**待验证的假设**，不是结论。改任何一个门类的词表后，
# 都应该用 `scripts/ab_prompts.py` 在同一片段上跑 A/B，别凭语义推断。
CATEGORY_PROMPTS = {
    # 01 毛笔制作：笔头靠刻刀修、笔杆是竹的、扎头用丝线
    "01": ["person", "hand", "brush in hand", "carving knife",
           "bamboo strip", "silk thread"],
    # 02/03 剪纸：剪刀与刻刀两条路线，材料是红纸，产出是剪纸成品
    "02": ["person", "hand", "scissors", "carving knife",
           "red paper", "paper cutting"],
    "03": ["person", "hand", "scissors", "carving knife",
           "red paper", "paper cutting"],
    # 04 苏绣：绣针、丝线、绣品，绷架近似织机
    "04": ["person", "hand", "embroidery needle", "silk thread",
           "embroidery", "loom"],
    # 05 传统木雕：刻刀为主，锤敲凿，料是木料
    "05": ["person", "hand", "carving knife", "hammer", "wooden block"],
    # 06 苗银头饰：锤打 + 錾刻。錾子在现有词表里没有，只能靠刻刀近似顶上
    # （两者形制不同：錾子被锤击、刻刀手推，会漏，但比不放好）。
    # 不要加 "clay"——苗银是失蜡铸造用蜡模，不是泥坯，加了只会出噪声框。
    "06": ["person", "hand", "hammer", "carving knife"],
    # 07 传统竹编：竹篾 → 竹编成品
    "07": ["person", "hand", "bamboo strip", "bamboo basket",
           "carving knife"],
    # 08 油纸伞：竹骨架 + 皮纸伞面 + 刷桐油的刷子
    "08": ["person", "hand", "bamboo strip", "red paper",
           "brush in hand", "wooden block"],
    # 09 皮影戏：核心对象是皮影人偶和操纵杆，现有词表里都没有，
    # 所以这里只剩人物和手部。**不要加 "red paper"** —— 皮影是牛皮/驴皮制的，
    # 红纸是臆想，实测只会往画面里的布景上乱框。
    # 这一格是 v3 里最弱的一环，要真正覆盖得先扩标签体系（见标签体系v2提案）。
    "09": ["person", "hand"],
    # 10 打铁花：勺子击打、木板、坩埚炉（后两者词表里没有）
    "10": ["person", "hand", "hammer", "wooden block", "clay"],
}


def prompts_for_clip(clip: Path) -> list:
    """按文件名前两位取该门类的提示词。

    匹配不上就**回退到全量词表**，不要返回空表——宁可多检几个框让人删，
    也不能让某个门类因为文件名对不上而整段零产出。这种静默失败最难查。
    """
    key = clip.name[:2]
    return list(CATEGORY_PROMPTS.get(key, list(WORLD_PROMPTS.keys())))


# 分档阈值。人物框 YOLO-World 很有把握，可以给高阈值；
# 工具/材料/手部属于开放词汇的弱项，实测置信度多在 0.2~0.4，
# 卡到 0.5 就一个都剩不下了。给低阈值，让标注员做最终判断 ——
# 预标注的价值是「给个起点」，漏了比错了更贵。
CONF_PERSON = 0.45
CONF_TOOL = 0.20

# v2：把「工具/毛笔」的提示词从 writing brush 换成 brush in hand（v1 对毛笔零检出）。
# 导入 Label Studio 时按 model_version 去重，换版本号才能让旧结果被替换掉。
# v3：提示词改为按门类定制（v2 是所有片段统一喂 16 个词，见 CATEGORY_PROMPTS）。
# 换版本号是必须的：Label Studio 导入预测时按 model_version 去重，
# 不换号的话新结果不会覆盖旧的。
MODEL_VERSION = "yolov8s-worldv2-openvocab-v3"


def conf_of(label: str) -> float:
    return CONF_PERSON if label == "人物/传承人" else CONF_TOOL


def close_sequence(seq, frames_count):
    """在轨迹末尾补一个 enabled=False 的哨兵关键帧。

    关键一步，别省。Label Studio 判定「当前帧要不要显示这个框」用的是
    VideoRegion.isInLifespan() → closestKeypoint()：取**帧号 ≤ 当前帧的最后一个
    关键帧**，再看它的 enabled。而 getShape() 里 `if (!next) return prev` ——
    超过最后一个关键帧之后，形状一直沿用最后一个。

    两条合起来的后果：只要所有关键帧都是 enabled=True，这个框就会从第一个关键帧
    一路显示到**视频结束**，哪怕目标早就走了。这就是「框一直存在」的真正原因。

    补上哨兵之后，哨兵之后的帧 closestKeypoint 取到哨兵 → enabled 为 false →
    isInLifespan 返回 false → 框才真正消失。

    不需要在开头补哨兵：getShape() 在第一个关键帧之前返回 null，框本来就不显示。

    注：LSF 有个特例 `frame === targetFrame && !enabled → 仍显示`（方便选中后重新启用），
    所以哨兵所在那一帧还会露一下，1 帧约 40ms，之后彻底隐藏。
    """
    if not seq:
        return seq
    last = seq[-1]
    end = last["frame"] + 1
    if end > frames_count:
        return seq  # 已经贴在视频最后一帧，没地方补
    return seq + [dict(last, frame=end, enabled=False)]


def build_prediction(tracks, frames_count, duration, model_version=MODEL_VERSION):
    """tracks: {track_id: {"label": str, "frames": [...], "scores": [...]}}"""
    result, all_scores = [], []
    for tid, t in tracks.items():
        if not t["frames"]:
            continue
        seq = [
            {"frame": f, "x": round(x, 2), "y": round(y, 2),
             "width": round(w, 2), "height": round(h, 2),
             "enabled": True, "rotation": 0}
            for f, x, y, w, h in sorted(t["frames"])
        ]
        result.append({
            "id": tid,
            "from_name": "box",
            "to_name": "video",
            "type": "videorectangle",
            "value": {
                "framesCount": frames_count,
                "duration": round(duration, 3),
                "sequence": close_sequence(seq, frames_count),
                "labels": [t["label"]],
            },
        })
        all_scores.extend(t["scores"])
    return {
        "model_version": model_version,
        "score": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0,
        "result": result,
    }


def check_prediction(pred):
    assert pred.get("model_version"), "缺 model_version"
    for r in pred["result"]:
        v = r["value"]
        assert r["type"] == "videorectangle", f"type 错: {r['type']}"
        assert v["framesCount"] > 0, "framesCount 必须为正"
        seq = v["sequence"]
        assert seq, "sequence 为空"
        assert min(s["frame"] for s in seq) >= 1, "帧号从 1 开始"
        for s in seq:
            assert 0 <= s["x"] <= 100 and 0 <= s["width"] <= 100, f"坐标越界: {s}"
            assert 0 <= s["y"] <= 100 and 0 <= s["height"] <= 100, f"坐标越界: {s}"
            assert s["frame"] <= v["framesCount"], f"帧号超出总帧数: {s['frame']}"
    return True


def prune_tracks(tracks, min_frames):
    keep, dropped = {}, 0
    for tid, t in tracks.items():
        if len(t["frames"]) >= min_frames:
            keep[tid] = t
        else:
            dropped += 1
    return keep, dropped


def split_tracks(tracks, max_gap, min_frames):
    """把内部有长时间断裂的轨迹切成多段。

    关键一步，别省。Label Studio 的 videorectangle 只存关键帧，
    关键帧之间由它自动插值。所以只要一条轨迹里存在一大段没有记录的空隙，
    它就会自作主张地补出一段平滑运动 —— 表现为「目标早就走了，框还飘在画面里」。

    这跟标注规范也是一致的：同一物理对象全程一个 tracklet，
    离开画面再回来应当新建 ID。所以断裂处应当切断，而不是让它插值过去。
    """
    out, cuts = {}, 0
    for tid, t in tracks.items():
        frames = sorted(t["frames"])
        segments = [[frames[0]]]
        for prev, cur in zip(frames, frames[1:]):
            if cur[0] - prev[0] > max_gap:
                segments.append([cur])
            else:
                segments[-1].append(cur)

        if len(segments) == 1:
            out[tid] = t
            continue

        cuts += 1
        for i, seg in enumerate(segments, 1):
            if len(seg) < min_frames:      # 太短的段本来也会被剪掉，直接丢
                continue
            # 取出这一段对应的置信度
            idx = frames.index(seg[0])
            scores = t["scores"][idx:idx + len(seg)]
            out[f"{tid}_seg{i}"] = {"label": t["label"], "frames": seg,
                                    "scores": scores}
    return out, cuts


def run_one(model, clip: Path, step: int, imgsz: int, max_area: float,
            order: list, labels: list):
    """检测 + 跨帧跟踪。分类别使用不同置信度阈值。

    order/labels 由调用方按门类传入（见 prompts_for_clip），
    调用前必须先 model.set_classes(order)。
    """
    results = model.track(
        source=str(clip),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
        conf=CONF_TOOL,          # 先用最低阈值全检出来，逐框再按类别筛
        imgsz=imgsz,
    )
    tracks = defaultdict(lambda: {"label": None, "frames": [], "scores": []})
    frame_no = 0
    for r in results:
        frame_no += 1
        if step > 1 and (frame_no - 1) % step:
            continue
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            continue
        h, w = r.orig_shape
        ids = boxes.id
        clss = boxes.cls
        confs = boxes.conf
        xyxy = boxes.xyxy
        for i in range(len(clss)):
            cls_id = int(clss[i])
            if cls_id >= len(order):
                continue
            label = labels[cls_id]
            conf = float(confs[i])
            if conf < conf_of(label):
                continue
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            x = max(0.0, min(100.0, x1 / w * 100))
            y = max(0.0, min(100.0, y1 / h * 100))
            bw = max(0.0, min(100.0 - x, (x2 - x1) / w * 100))
            bh = max(0.0, min(100.0 - y, (y2 - y1) / h * 100))
            area = (bw / 100.0) * (bh / 100.0)
            if area > max_area or area < 0.003:
                continue
            tid_raw = ids[i] if ids is not None else None
            tid = (f"{label.split('/')[-1]}_{int(tid_raw):03d}"
                   if tid_raw is not None else f"det_{frame_no}_{i}")
            t = tracks[tid]
            t["label"] = label
            t["frames"].append((frame_no, x, y, bw, bh))
            t["scores"].append(conf)
    return tracks


ORDER = list(WORLD_PROMPTS.keys())
LABELS = [WORLD_PROMPTS[k] for k in ORDER]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / ".tmp" / "yolov8s-worldv2.pt"))
    ap.add_argument("--clips", nargs="*")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--min-frames", type=int, default=5)
    ap.add_argument("--max-gap", type=int, default=15,
                    help="轨迹内相邻帧间隔超过这么多帧就切成两段（默认 15 帧 ≈ 0.6 秒）")
    ap.add_argument("--max-area", type=float, default=0.6)
    ap.add_argument("--out", default="preds_world.jsonl")
    ap.add_argument("--all", action="store_true", help="跑全部片段")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("请先安装：pip install ultralytics")

    print(f"加载 YOLO-World {args.weights} ...")
    model = YOLO(args.weights)
    print(f"开放词汇类别共 {len(ORDER)} 个，按门类取子集（各 2~6 个）\n")

    if args.clips:
        targets = [CLIPS / c for c in args.clips]
    elif args.all:
        targets = sorted(CLIPS.glob("*.mp4"))
    else:
        targets = sorted(CLIPS.glob("*.mp4"))[: args.limit]

    import cv2
    out_f = open(ROOT / args.out, "w", encoding="utf-8")
    ok = 0
    for clip in targets:
        if not clip.exists():
            print(f"[skip] {clip}")
            continue
        cap = cv2.VideoCapture(str(clip))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.release()
        if n <= 0:
            print(f"[skip] 读不到帧数 {clip.name}")
            continue

        order = prompts_for_clip(clip)
        labels = [WORLD_PROMPTS[k] for k in order]
        model.set_classes(order)

        tracks = run_one(model, clip, args.step, args.imgsz, args.max_area,
                         order, labels)
        # 先切断裂，再滤碎片 —— 顺序反了会切出一堆过短的段
        tracks, cuts = split_tracks(tracks, args.max_gap, args.min_frames)
        tracks, dropped = prune_tracks(tracks, args.min_frames)
        pred = build_prediction(tracks, n, n / fps if fps else 0.0)
        try:
            check_prediction(pred)
        except AssertionError as e:
            print(f"[schema 失败] {clip.name}: {e}")
            continue
        out_f.write(json.dumps({"video": str(clip), "prediction": pred},
                               ensure_ascii=False) + "\n")
        # 每段都落盘：否则重定向到文件时 stdout/文件都是块缓冲，
        # 想用 `wc -l` 看进度会一直显示 0，误以为卡住了。
        out_f.flush()
        # 按标签统计，便于一眼看出这一版有没有覆盖到工具/材料
        stat = defaultdict(int)
        for r in pred["result"]:
            stat[r["value"]["labels"][0]] += 1
        detail = "、".join(f"{k}×{v}" for k, v in sorted(stat.items()))
        print(f"[ok] {clip.name}: {n}帧 {n/fps:.0f}s -> {len(pred['result'])} 条轨迹"
              + (f"（切断裂 {cuts}、滤碎片 {dropped}）" if cuts or dropped else ""))
        print(f"      词表 {len(order)} 个: {', '.join(order)}")
        print(f"      {detail or '（无检出）'}", flush=True)
    out_f.close()
    print(f"\n完成 {ok} 条 -> {args.out}")


if __name__ == "__main__":
    main()
