"""把片段音轨转成文字，喂给 qwen_label 的 T1-4 听觉特征。

为什么单独一个脚本：视觉模型听不到声音。甲方 T1-4 要判「方言/少数民族语、
民俗乐器音、特征性环境音」，这三样必须从音频来，不能靠画面猜。

用的模型：阿里云百炼 Paraformer 实时版（paraformer-realtime-v2），中文和方言
识别好，和 Qwen 共用同一个 DASHSCOPE_API_KEY。

用法：
    export DASHSCOPE_API_KEY=sk-xxx
    python scripts/asr.py --clip data/clips/01_传统技艺_01.mp4 --out .tmp/asr/01.txt
    python scripts/asr.py --batch data/clips --out-dir .tmp/asr

注意：ASR 只能给「语言」和部分环境音线索。**乐器音、唱腔、仪式性音效 ASR 转不出来**，
所以 T1-4 里「音乐」那一格仍需模型从音色推断，或人工补。这一点在报告里要写清楚。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from qwen_label import extract_audio  # noqa: E402


def asr_dashscope(wav: Path, model: str = "paraformer-realtime-v2",
                  api_key: str | None = None) -> dict:
    """调百炼 Paraformer。返回 {text, sentences}。"""
    try:
        import dashscope
        from dashscope.audio.asr import Recognition
    except ImportError as exc:
        raise RuntimeError("需要 dashscope SDK：pip install dashscope") from exc

    key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    # dashscope 2.x 的 Recognition 走 legacy 兼容层，鉴权用全局 api_key，构造函数不收 api_key
    dashscope.api_key = key

    rec = Recognition(model=model, callback=None, format="wav", sample_rate=16000)
    result = rec.call(file=str(wav))
    status = getattr(result, "status_code", 200)
    if status != 200:
        raise RuntimeError(f"ASR 失败 {status}: {getattr(result, 'message', '')}")

    sentences = []
    for s in (result.get_sentence() or []):
        sentences.append({
            "text": s.get("text", ""),
            "begin": s.get("begin_time"),
            "end": s.get("end_time"),
        })
    return {
        "text": "".join(x["text"] for x in sentences).strip(),
        "sentences": sentences,
    }


def run_one(clip: Path, out_path: Path | None, model: str) -> dict:
    wav = extract_audio(clip)
    if not wav:
        return {"clip": clip.name, "error": "抽音轨失败（无音轨或 ffmpeg 不可用）"}
    try:
        r = asr_dashscope(wav, model=model)
    except Exception as exc:                       # noqa: BLE001
        return {"clip": clip.name, "error": str(exc)}
    r["clip"] = clip.name
    r["wav"] = str(wav)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # 给 qwen_label --asr 用的是纯文本，所以另存一份 .txt
        out_path.write_text(r["text"], encoding="utf-8")
        r["txt"] = str(out_path)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="片段音轨转文字（供 T1-4 使用）")
    ap.add_argument("--clip", type=Path)
    ap.add_argument("--batch", type=Path)
    ap.add_argument("--out", type=Path, help="单文件时输出 .txt 路径")
    ap.add_argument("--out-dir", type=Path, help="批量时输出目录")
    ap.add_argument("--model", default="paraformer-realtime-v2")
    ap.add_argument("--json", type=Path, help="把带时间码的完整结果写成 jsonl")
    args = ap.parse_args()

    if args.clip:
        clips = [args.clip]
    elif args.batch:
        clips = sorted(p for p in args.batch.iterdir()
                       if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"})
    else:
        ap.error("需要 --clip 或 --batch")

    rows = []
    for i, clip in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {clip.name}", flush=True)
        out = None
        if args.clip and args.out:
            out = args.out
        elif args.out_dir:
            out = args.out_dir / (clip.stem + ".txt")
        r = run_one(clip, out, args.model)
        if "error" in r:
            print(f"  失败：{r['error']}", flush=True)
        else:
            print(f"  {len(r['text'])} 字：{r['text'][:60]}", flush=True)
        rows.append(r)

    if args.json:
        args.json.write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
            encoding="utf-8")
        print(f"\n写出 {args.json}")


if __name__ == "__main__":
    main()
