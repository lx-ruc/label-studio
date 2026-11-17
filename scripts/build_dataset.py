#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data/raw 下的长视频加工成可直接标注的短片段：

  转码规范化(25fps/短GOP) -> 镜头切分 -> 运动量打分筛选 -> 输出 10~60s 片段
  -> 生成 Label Studio 任务 JSON

输出：
  data/clips/*.mp4          标注用片段
  clips_manifest.json       片段元数据
  labelstudio/tasks.json    可直接导入 Label Studio 的任务
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CLIPS = ROOT / "data" / "clips"
LS = ROOT / "labelstudio"
FFMPEG = Path("/Users/lixin/.workbuddy/binaries/python/envs/default/bin/ffmpeg")

TARGET_FPS = 25
TARGET_W = 1280
MIN_CLIP = 8.0      # 短于 8s 的镜头与上一段合并
MAX_CLIP = 45.0     # 长镜头按 45s 再切
MAX_CLIPS_PER_VIDEO = 4
MIN_GAP = 25.0       # 同一视频内两个片段的起点最小间隔（秒）
SCENE_THRESH = 0.35


def dur_of(path: Path) -> float:
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        return 0.0
    h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mnt * 60 + s


def scene_stamps(path: Path) -> list:
    """用 ffmpeg 的场景变化检测拿切点（降采样到 320 宽，速度快很多）"""
    cmd = [str(FFMPEG), "-hide_banner", "-i", str(path), "-an",
           "-vf", f"scale=320:-2,select='gt(scene,{SCENE_THRESH})',showinfo",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ts = [float(m) for m in re.findall(r"pts_time:(\d+\.?\d*)", r.stderr)]
    return sorted(set(t for t in ts if t > 1.0))


def build_segments(total: float, stamps: list) -> list:
    """镜头边界 -> 合并过短 -> 拆分过长，得到 10~60s 的候选片段"""
    bounds = [0.0] + [t for t in stamps if t < total - 2] + [total]
    segs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < MIN_CLIP and segs:
            segs[-1] = (segs[-1][0], b)          # 过短镜头并入上一段
        else:
            segs.append((a, b))
    out = []
    for a, b in segs:
        if b - a <= MAX_CLIP:
            out.append((a, b))
        else:                                     # 长镜头等分切开
            n = int((b - a) // MAX_CLIP) + 1
            step = (b - a) / n
            for i in range(n):
                out.append((a + i * step, a + (i + 1) * step))
    return [(a, b) for a, b in out if (b - a) >= MIN_CLIP]


def content_score(path: Path, a: float, b: float) -> tuple:
    """判断片段是否适合做检测+跟踪标注。三个轻量信号，无需模型：

      motion 相邻采样帧的平均灰度差 —— 最强信号。实操镜头手部一直在动；
             念稿访谈、PPT/字幕卡几乎静止，靠它一刀切掉
      edge   拉普拉斯方差中位数    —— 过滤纯色、黑场、整体虚焦
      bright 平均亮度              —— 过滤过暗/过曝，标注时看不清工具

    返回 (score, ok)
    """
    cap = cv2.VideoCapture(str(path))
    edges, bris, diffs, prev = [], [], [], None
    for frac in [i / 11 for i in range(12)]:
        cap.set(cv2.CAP_PROP_POS_MSEC, (a + (b - a) * frac) * 1000)
        ok, f = cap.read()
        if not ok:
            continue
        small = cv2.resize(f, (240, 135))
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        bris.append(float(g.mean()))
        edges.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        if prev is not None:
            diffs.append(float(cv2.absdiff(g, prev).mean()))
        prev = g
    cap.release()
    if not diffs:
        return 0.0, False

    n = len(edges)
    bright = sum(bris) / n
    edge = sorted(edges)[n // 2]
    motion = sum(diffs) / len(diffs)

    if bright < 45 or bright > 235:          # 过暗 / 过曝
        return 0.0, False
    if edge < 80 or max(edges) < 260:        # 近乎纯色 / 整体虚焦
        return 0.0, False
    if motion < 1.0:                         # 几乎静止：字幕卡、PPT、静物空镜
        return 0.0, False

    score = (min(motion / 5.0, 1.0) * 2.0
             + min(edge / 400.0, 1.0)
             + min(bright / 140.0, 1.0) * 0.3)
    return round(score, 3), True


def transcode(src: Path, a: float, b: float, dst: Path) -> bool:
    cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{a:.2f}", "-i", str(src), "-t", f"{b - a:.2f}",
           "-vf", (f"scale='if(gt(iw,ih),min({TARGET_W},iw),-2)':"
                   f"'if(gt(iw,ih),-2,min({TARGET_W},ih))',fps={TARGET_FPS}"),
           "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
           "-g", str(TARGET_FPS), "-keyint_min", str(TARGET_FPS), "-sc_threshold", "0",
           "-c:a", "aac", "-b:a", "96k",
           "-movflags", "+faststart", str(dst)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def main():
    CLIPS.mkdir(parents=True, exist_ok=True)
    LS.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    clips_meta, tasks = [], []

    for item in manifest:
        src = ROOT / item["file"]
        if not src.exists():
            print(f"[skip] 缺少 {src}")
            continue
        total = dur_of(src)
        if total <= 0:
            print(f"[skip] 无法读取时长 {src.name}")
            continue
        stamps = scene_stamps(src)
        segs = build_segments(total, stamps)

        scored = []
        for a, b in segs:
            s, ok = content_score(src, a, b)
            if ok:
                scored.append((s, a, b))
        scored.sort(key=lambda x: -x[0])

        # 贪心挑选：优先高分，同时要求与已选片段至少间隔 MIN_GAP 秒，避免四段全来自同一场戏
        picked, used = [], []
        for s, a, b in scored:
            if len(picked) >= MAX_CLIPS_PER_VIDEO:
                break
            if any(abs(a - u) < MIN_GAP for u in used):
                continue
            picked.append((s, a, b))
            used.append(a)
        print(f"[{item['id']}] {item['name']}: {total:.0f}s -> {len(segs)} 段, "
              f"合格 {len(scored)} 段, 取 {len(picked)} 段")

        for j, (score, a, b) in enumerate(sorted(picked, key=lambda x: x[1]), 1):
            cid = f"{item['id']}_{item['category']}_{j:02d}"
            dst = CLIPS / f"{cid}.mp4"
            if not transcode(src, a, b, dst):
                print(f"  [FAIL] 转码失败 {cid}")
                continue
            size_mb = dst.stat().st_size / 1e6
            clips_meta.append({
                "clip_id": cid,
                "file": str(dst.relative_to(ROOT)),
                "source": item["name"],
                "bvid": item["bvid"],
                "category": item["category"],
                "start": round(a, 2),
                "end": round(b, 2),
                "duration": round(b - a, 2),
                "content_score": round(score, 2),
                "size_mb": round(size_mb, 2),
                "source_url": item["source_url"],
                "license": item["license"],
            })
            # Label Studio 本地文件引用：需在启动时设置
            # LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=<本项目>/data
            tasks.append({
                "data": {
                    "video": f"/data/local-files/?d=clips/{dst.name}",
                    "meta_category": item["category"],
                    "meta_source": item["name"],
                }
            })

    (ROOT / "clips_manifest.json").write_text(
        json.dumps(clips_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (LS / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    total_mb = sum(c["size_mb"] for c in clips_meta)
    print(f"\n片段数 {len(clips_meta)}，总时长 "
          f"{sum(c['duration'] for c in clips_meta)/60:.1f} 分钟，{total_mb:.0f} MB")
    print(f"-> clips_manifest.json")
    print(f"-> {LS/'tasks.json'}")


if __name__ == "__main__":
    main()
