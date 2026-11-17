#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载选定的非遗视频到 data/raw/，并生成 manifest.json 记录来源与版权信息。

用途声明：仅用于本地标注练习与流程验证，禁止商用或再分发。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CANDIDATES = ROOT / "candidates.json"
MANIFEST = ROOT / "manifest.json"
COOKIES = Path("/tmp/bili.txt")

# 挑选覆盖 5 个非遗门类、手部与工具清晰、镜头相对固定的样本
SELECTED = [
    ("BV1ju41157uB", "传统技艺", "毛笔制作"),
    ("BV1Qe4y1m7xX", "传统美术", "剪纸工具与材料"),
    ("BV1ue4y1Q744", "传统美术", "剪纸剪法与刀法"),
    ("BV1S4411c7ij", "传统美术", "苏绣刺绣"),
    ("BV1AQ4y1P7fw", "传统技艺", "传统木雕"),
    ("BV1ct411W7Lk", "传统技艺", "苗银头饰制作"),
    ("BV17L411y7fA", "传统技艺", "传统竹编"),
    ("BV1JQ4y1k7oE", "传统技艺", "油纸伞制作"),
    ("BV1stM3zGEvG", "传统戏剧", "皮影戏"),
    ("BV14Q4y1j7MS", "民俗",     "打铁花"),
]

FFMPEG_DIR = Path("/Users/lixin/.workbuddy/binaries/python/envs/default/bin")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    cands = {c["bvid"]: c for c in json.loads(CANDIDATES.read_text(encoding="utf-8"))}

    manifest = []
    for i, (bvid, cat, name) in enumerate(SELECTED, 1):
        out = RAW / f"{i:02d}_{cat}_{name}_{bvid}.mp4"
        if out.exists() and out.stat().st_size > 1024 * 100:
            print(f"[skip] {out.name} 已存在")
        else:
            url = f"https://www.bilibili.com/video/{bvid}"
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "-f", "bv[height<=720]+ba/b[height<=720]/bv+ba/b",
                "--ffmpeg-location", str(FFMPEG_DIR),
                "--cookies", str(COOKIES),
                "--no-warnings", "--no-playlist",
                "-o", str(out.with_suffix(".%(ext)s")),
                url,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[FAIL] {bvid} {name}: {r.stderr[-300:]}")
                continue

        meta = cands.get(bvid, {})
        manifest.append({
            "id": f"{i:02d}",
            "bvid": bvid,
            "name": name,
            "category": cat,
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "source_url": f"https://www.bilibili.com/video/{bvid}",
            "duration_sec": meta.get("seconds"),
            "file": str(out.relative_to(ROOT)),
            "license": "来源：哔哩哔哩（bilibili.com），版权归原作者所有；仅限本地标注练习与流程验证，禁止商用或再分发",
        })
        size = out.stat().st_size / 1e6 if out.exists() else 0
        print(f"[ok] {out.name}  {size:.1f} MB")

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmanifest -> {MANIFEST}  ({len(manifest)} 条)")


if __name__ == "__main__":
    main()
