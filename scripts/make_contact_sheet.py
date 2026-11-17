#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为每个片段抽 3 张缩略图，生成一份可直接在浏览器打开的预览页 contact_sheet.html"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "data" / "clips"
THUMBS = ROOT / "data" / "thumbs"
FFMPEG = Path("/Users/lixin/.workbuddy/binaries/python/envs/default/bin/ffmpeg")
OUT = ROOT / "contact_sheet.html"

CAT_COLOR = {
    "传统技艺": "#EAF3DE", "传统美术": "#FBEAF0", "传统戏剧": "#E6F1FB",
    "民俗": "#FAEEDA", "传统音乐": "#EEEDFE",
}


def thumb(src: Path, t: float, dst: Path) -> bool:
    cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
           "-vf", "scale=420:-2", "-q:v", "4", str(dst)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def main():
    THUMBS.mkdir(parents=True, exist_ok=True)
    clips = json.loads((ROOT / "clips_manifest.json").read_text(encoding="utf-8"))

    cards = []
    for c in clips:
        src = ROOT / c["file"]
        imgs = []
        for k, frac in enumerate([0.2, 0.5, 0.8]):
            dst = THUMBS / f"{c['clip_id']}_{k}.jpg"
            if thumb(src, c["duration"] * frac, dst):
                imgs.append(dst.relative_to(ROOT).as_posix())
        cards.append((c, imgs))

    total_dur = sum(c["duration"] for c in clips)
    cats = {}
    for c in clips:
        cats[c["category"]] = cats.get(c["category"], 0) + 1

    body = []
    for c, imgs in cards:
        src_link = (f'<a href="{c["source_url"]}" target="_blank">原视频</a>'
                    if c.get("source_url") else "")
        score = c.get("content_score")
        score_txt = f" · 内容分 {score:.1f}" if isinstance(score, (int, float)) else ""
        g = "".join(f'<img src="{p}" loading="lazy">' for p in imgs)
        body.append(f"""
    <div class="card">
      <div class="gallery">{g}</div>
      <div class="meta">
        <div class="row1">
          <span class="cat" style="background:{CAT_COLOR.get(c['category'], '#F1EFE8')}">{c['category']}</span>
          <code>{c['clip_id']}</code>
        </div>
        <div class="row2">{c['source']} · {c['duration']:.0f}s{score_txt}</div>
        <div class="row3">{src_link}</div>
      </div>
    </div>""")

    tag_chips = "".join(f'<span class="chip">{k} × {v}</span>' for k, v in sorted(cats.items()))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>非遗视频标注集 · 片段预览</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; margin: 0; padding: 28px 32px;
         background: #FAFAF8; color: #2C2C2A; }}
  h1 {{ font-size: 19px; font-weight: 500; margin: 0 0 6px; }}
  .sub {{ font-size: 13px; color: #5F5E5A; margin-bottom: 18px; line-height: 1.7; }}
  .chip {{ display: inline-block; font-size: 12px; padding: 3px 10px; margin: 0 6px 6px 0;
           background: #F1EFE8; border-radius: 10px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 18px; }}
  .card {{ background: #fff; border: 1px solid rgba(0,0,0,.10); border-radius: 12px; overflow: hidden; }}
  .gallery {{ display: flex; gap: 2px; background: #EDEDEA; }}
  .gallery img {{ width: 33.33%; display: block; object-fit: cover; aspect-ratio: 16/9; }}
  .meta {{ padding: 10px 14px 12px; }}
  .row1 {{ display: flex; align-items: center; gap: 8px; }}
  .cat {{ font-size: 12px; padding: 2px 8px; border-radius: 8px; }}
  code {{ font-size: 12px; color: #444441; }}
  .row2 {{ font-size: 12px; color: #5F5E5A; margin-top: 5px; }}
  .row3 {{ font-size: 12px; margin-top: 4px; }}
  .row3 a {{ color: #185FA5; text-decoration: none; }}
  .note {{ margin-top: 26px; font-size: 12px; color: #888780; line-height: 1.8;
           border-top: 1px solid rgba(0,0,0,.08); padding-top: 14px; }}
</style></head><body>
<h1>非遗视频标注集 · 片段预览</h1>
<div class="sub">
  共 <b>{len(clips)}</b> 个片段，总时长 <b>{total_dur/60:.1f}</b> 分钟，
  来自 {len({c['bvid'] for c in clips})} 条原始视频，覆盖 {len(cats)} 个非遗门类。<br>{tag_chips}
</div>
<div class="grid">{''.join(body)}
</div>
<div class="note">
  缩略图取自片段的 20% / 50% / 80% 处，用于快速确认内容是否适合做检测与跟踪标注。<br>
  素材来源：哔哩哔哩（bilibili.com），版权归原作者所有。本数据集<b>仅限本地标注练习与流程验证</b>，禁止商用或再分发。
</div>
</body></html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"-> {OUT}  ({len(clips)} 个片段)")


if __name__ == "__main__":
    main()
