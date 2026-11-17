"""把 /Users/lixin/video-vl 下四条视频接进流水线，生成片段清单。

产出 refs/clips4.jsonl，字段与 qwen_label 的 meta 对齐；
同时把 video-vl 里已有的旧标注（class/object/dialect/Minzu/shot/description）
一并带进来，作为「参考基准」的素材。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SRC = Path("/Users/lixin/video-vl")
OLD = ROOT / "video-vl"            # 旧分析与视频同名的 json 在这里
OUT = ROOT / "refs" / "clips4.jsonl"


def probe(p: Path) -> dict:
    cap = cv2.VideoCapture(str(p))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    try:
        import imageio_ffmpeg
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(p), "-hide_banner"],
                           capture_output=True, text=True)
        has_audio = "Audio:" in r.stderr
    except Exception:
        has_audio = None
    return {
        "dur_s": round(n / fps, 1) if fps and n else None,
        "fps": round(fps, 2),
        "width": w, "height": h,
        "size_mb": round(p.stat().st_size / 1e6, 1),
        "has_audio": has_audio,
    }


def main() -> None:
    rows = []
    for p in sorted(SRC.glob("*.mp4")):
        info = probe(p)
        old_path = OLD / (p.stem + ".json")
        old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else None
        rec = {
            "clip_id": p.stem,
            "file": str(p),
            "film": p.stem,
            "dur_s": info["dur_s"],
            "fps": info["fps"],
            "width": info["width"],
            "height": info["height"],
            "size_mb": info["size_mb"],
            "has_audio": info["has_audio"],
            "old_annotation": old,
        }
        rows.append(rec)
        print(f"{p.name}")
        print(f"   {info['width']}x{info['height']} {info['fps']}fps "
              f"{info['dur_s']}s {info['size_mb']}MB 音轨={'有' if info['has_audio'] else '无'}")
        if old:
            print(f"   旧标注: class={old.get('class')} | 民族={old.get('Minzu')} "
                  f"| 方言={old.get('dialect')}")

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    print(f"\n写出 {OUT}（{len(rows)} 条）")


if __name__ == "__main__":
    main()
