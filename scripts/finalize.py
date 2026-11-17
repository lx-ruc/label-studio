#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以磁盘上的实际文件为准，重建 clips_manifest.json 与 labelstudio/tasks.json。

build_dataset.py 只记录本次运行选中的片段；如果目录里还有历史残留的片段
（同一源视频的其他镜头，内容并不重复），这一步会把它们补进清单，
保证「磁盘文件数 == 任务数」，不会出现导入了却找不到文件的情况。
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "data" / "clips"
FFMPEG = Path("/Users/lixin/.workbuddy/binaries/python/envs/default/bin/ffmpeg")


def dur_of(p: Path) -> float:
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(p)],
                       capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def main():
    sources = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in sources}

    known = {}
    if (ROOT / "clips_manifest.json").exists():
        for c in json.loads((ROOT / "clips_manifest.json").read_text(encoding="utf-8")):
            known[Path(c["file"]).name] = c

    out = []
    for p in sorted(CLIPS.glob("*.mp4")):
        if p.name in known:
            out.append(known[p.name])
            continue
        # 历史片段：从文件名解析 序号_门类_镜号
        m = re.match(r"(\d+)_([^_]+)_(\d+)\.mp4$", p.name)
        sid, cat = (m.group(1), m.group(2)) if m else ("00", "未知")
        src = by_id.get(sid, {})
        out.append({
            "clip_id": p.stem,
            "file": str(p.relative_to(ROOT)),
            "source": src.get("name", "未知"),
            "bvid": src.get("bvid", ""),
            "category": cat,
            "start": None, "end": None,
            "duration": round(dur_of(p), 2),
            "content_score": None,
            "size_mb": round(p.stat().st_size / 1e6, 2),
            "source_url": src.get("source_url", ""),
            "license": src.get("license", ""),
        })

    out.sort(key=lambda c: c["clip_id"])
    (ROOT / "clips_manifest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    tasks = [{
        "data": {
            "video": f"/data/local-files/?d=clips/{Path(c['file']).name}",
            "meta_category": c["category"],
            "meta_source": c["source"],
        }
    } for c in out]
    (ROOT / "labelstudio" / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(c["duration"] for c in out)
    print(f"片段 {len(out)} 个，总时长 {total/60:.1f} 分钟，"
          f"{sum(c['size_mb'] for c in out):.0f} MB")
    cats = {}
    for c in out:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    print("门类分布:", cats)


if __name__ == "__main__":
    main()
