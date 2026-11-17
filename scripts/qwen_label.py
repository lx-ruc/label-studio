"""用 Qwen 按甲方《非遗影像智能分析评测标准 v4.0》做十二项标注。

设计要点
--------
1. 提示词不手写，从 refs/annotation_spec_v4.json **编译**出来 —— 词表、判断说明、
   提问原文、权重全部读配置，甲方改词表时只改配置，不碰代码。
2. 输出严格对齐甲方 42 列表格：每一项都是「标签列 / 输出结果列 / 置信度列」三连。
3. 兼容任何 OpenAI 兼容端点：阿里云百炼（DashScope）、本地 vLLM、硅基流动等。
   只需设环境变量 QWEN_BASE_URL / QWEN_API_KEY / QWEN_MODEL。
4. T1-4 听觉特征需要音频。视觉模型听不到声音，所以：
   - 给了 --asr 结果 → 让模型基于 ASR 文本判听觉特征；
   - 没给 → 明确要求填「无法判断」，不允许猜。

用法
----
    # 只看编译出来的提示词，不调模型（不花钱）
    python scripts/qwen_label.py --clip data/clips/01_传统技艺_01.mp4 --dry-run

    # 真跑一段
    python scripts/qwen_label.py --clip data/clips/01_传统技艺_01.mp4 --out out.json

    # 批量
    python scripts/qwen_label.py --batch data/clips --limit 5 --out results.jsonl
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "refs" / "annotation_spec_v4.json"
GOLD_PATH = ROOT / "refs" / "gold.jsonl"

# 每项任务的字段构成（决定 JSON schema 和落表方式）
TASK_FIELDS: dict[str, list[str]] = {
    "T1-1": ["out", "conf"],
    "T1-2": ["out", "conf"],
    "T1-3": ["out", "conf"],
    "T1-4": ["out", "conf"],
    "T2-1": ["label", "aux", "out", "conf"],
    "T2-2": ["label", "out", "conf"],
    "T2-3": ["label", "gender", "out", "conf"],
    "T2-4": ["label", "alt", "out", "conf"],
    "T3-1": ["label", "out", "conf"],
    "T3-2": ["label", "out", "conf"],
    "T3-3": ["label", "out", "conf"],
    "T3-4": ["label", "out", "conf"],
}

# 输出结果列的固定句式 —— 从甲方 1391 行的实际写法里归纳出来的，不是我们发明的
OUT_TEMPLATE: dict[str, str] = {
    "T1-1": "先给「有/没有」判断，再列举物件名。示例（把示例物件换成本片实际看到的东西）：「画面中出现了与非遗相关的工具或材料，为芦笙、绣花坎肩、银饰。」或「画面中没有出现与非遗相关的工具或材料。」",
    "T1-2": "先给「有/没有」判断，若有则写动作类型＋发力部位＋节奏。示例：「画面中出现具有非遗特征的身体动作，为手工投纬，发力于指尖与手腕，节奏均匀缓慢。」",
    "T1-3": "必须分两段，且每段先给是/否再说明：「人物方面：…。场景方面：是否存在仪式性场景＝是/否，依据…；特定场景标识物＝有/无，为…。」**「有标识物」不等于「有仪式」——经幡、彩旗、民族服饰是身份标识物，不构成仪式性场景；只有当画面里存在祭拜、诵经、献供、程序化仪轨行为时才算仪式性场景。**",
    "T1-4": "必须分三段，格式固定：「语言：…。音乐：…。环境音：…。」无则写「无」。**如果音频转写不可得或明显是噪声误识，三段全部写「无法判断」，不要从转写碎片里推断语种或民族语。**",
    "T2-1": "「该片段核心叙事模式为工序说明。判断依据：…」——开头这句里的门类名必须换成你实际选的标签；若还给了辅助标签，在依据里说明为何并列。",
    "T2-2": "「行为发生的社会空间为户外场地，可判断为户外自然环境。」——先引视觉线索再下判断，同样把示例空间名换成实际的。",
    "T2-3": "「画面中的主要人物为老师傅/传承人、儿童传习者。判断依据：…」同一人物只取一个主角色；涉及性别隔离角色时在 gender 写「角色[女]」。",
    "T2-4": "「由画面内容判断，该影像应属于传统音乐。歧义点：…」——**label 只填一个主类**；有歧义时把次选放进 alt 字段，并在 out 里说明歧义点。不要同时给两个主类。",
    "T3-1": "列出具体符号名（如「三跪九叩（跪拜仪轨）」「孔纹黄纸（符箓类纸钱）」），并说明所属文化传统；确实没有则写「画面中未出现明显的非遗文化符号」并说明理由。",
    "T3-2": "「该片段整体氛围为欢快热烈。视觉依据：…听觉依据：…」混合氛围要说明成分比重；听觉不可得就写「听觉依据：音频信息不可得，未纳入判断」。",
    "T3-3": "「主要体现为文化传承与教育的功能：…」每个维度都要给影像证据；不适用要写排除说明。",
    "T3-4": "「画面中呈现师徒代际传承的关系。…」要给权力不对称程度和具体行为证据。",
}

SYSTEM_RULES = """你是非遗影像标注员，严格按《非遗影像智能分析评测标准 v4.0》给视频片段打标。

## 硬性规则（违反任何一条，该条标注作废）

1. **标签只能用词表原词**。词表里没有的，写 `其他：<你自拟的类名>`，自拟名要具体（如「其他：现代办公与机构空间」），不要写「其他：其他」。
2. **多标签用中文分号 `；` 连接**，不要用逗号、顿号、斜杠。注意词表内部本身含顿号或斜杠的（如「传统体育、游艺与杂技」「老师傅/传承人」）必须整词照抄，不得拆开。
3. **每项先给结论，再给依据**，依据要指向画面里实际能看到的东西（人物动作、器物、字幕、布景、声音）。禁止编造片名以外的人名、地名、机构名——除非画面字幕里明确出现。
4. **置信度只能填「高」「中」「低」**。画面证据充分填「高」；有推断成分填「中」；画面看不清或信息不足填「低」。不要因为谨慎就一律填「中」。
5. **画面里没有的，就答「没有」**。宁可答无，不要为了显得有发现而虚构。这一点比覆盖率重要。
6. 你看的是**一个连续片段**，不是整部片子。判断只针对这一段。
7. **不要把模板里的示例词、占位符号（如 X、Y、……）原样抄进答案**。每一处都要换成这段片子里的实际内容。
8. **有词表的任务，label 只填主类**（T2-1 除外，它允许主标签＋辅助标签）。有歧义时把次选放进 alt 字段，不要塞进 label。
9. **音频转写不可靠时，不要推断语种**。若转写里是零星外语音节、乱码式短语、或与画面明显无关的内容，就判定为「音频信息不可得」，T1-4 三段全写「无法判断」。据碎片猜「疑似日语」「疑似南岛语系」属于编造。

## 输出格式

只返回一个 JSON 对象，不要 Markdown 代码块，不要任何解释文字。结构：

```
{
  "T1-1": {"out": "...", "conf": "高"},
  ...
  "T2-1": {"label": ["..."], "aux": [], "out": "...", "conf": "中"},
  ...
}
```

缺失的键视为未标注；字段类型必须与上面一致（label 是字符串数组，conf 是字符串）。
"""


# --------------------------------------------------------------------------- #
# 规范 -> 提示词
# --------------------------------------------------------------------------- #

def load_spec(path: Path = SPEC_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_vocab(spec: dict, task: dict) -> str:
    """把一个任务的词表渲染成「编号. 名称 —— 判断说明」。"""
    key = task.get("label_vocab")
    if not key:
        return ""
    if key == "genre_taxonomy":
        items = [{"code": "", "name": g, "note": ""} for g in spec["genre_taxonomy"]]
    else:
        items = spec["vocab"][key]["items"]

    lines = []
    for i, it in enumerate(items, 1):
        name, note = it["name"], it.get("note", "")
        if name == "其他" or name.startswith("其他"):
            continue
        lines.append(f"  {i}. {name}" + (f" —— {note}" if note else ""))
    lines.append("  （以上都不合适时用 `其他：<自拟类名>`）")
    return "\n".join(lines)


def render_tasks(spec: dict) -> str:
    order = ["T1", "T2", "T3"]
    blocks = []
    for lv in order:
        meta = spec["layers"][lv]
        tasks = [t for t in spec["tasks"] if t["layer"] == lv]
        wsum = sum(t["weight"] or 0 for t in tasks)
        blocks.append(
            f"\n### {lv} {meta['name']}（层级权重 {meta['weight']:.2f}，{meta['note']}）\n"
        )
        for t in tasks:
            fields = TASK_FIELDS[t["id"]]
            blocks.append(f"\n**【{t['id']}】{t['name']}**（单项权重 {t['weight']:.2f}）")
            blocks.append(f"问：{t['question']}")
            blocks.append(f"输出字段：{', '.join(fields)}")
            if "label" in fields:
                v = render_vocab(spec, t)
                if v:
                    blocks.append("词表：\n" + v)
            blocks.append(f"写法：{OUT_TEMPLATE[t['id']]}")
        del wsum
    return "\n".join(blocks)


def build_system_prompt(spec: dict) -> str:
    head = (
        "# 任务\n\n"
        "下面给你一段非遗影像片段（若干等间隔抽帧）和它的元信息。"
        "请按十二项任务逐项标注，每项都要给出输出结果与置信度。\n"
    )
    tail = (
        "\n\n## 最后再确认一遍\n\n"
        "- 12 个键是否齐全（T1-1 ~ T3-4）\n"
        "- label 是否为字符串数组，conf 是否为「高/中/低」之一\n"
        "- 有没有用了词表之外的标签却没写 `其他：`\n"
        "- 有没有编造画面里不存在的人名、地名、机构名\n"
    )
    return head + render_tasks(spec) + "\n\n" + SYSTEM_RULES + tail


def build_user_prompt(meta: dict, n_frames: int, asr_text: str | None, fps: float) -> str:
    lines = [
        f"片名：{meta.get('film', '未提供')}",
        f"片段时长：{meta.get('dur_s', '未知')} 秒",
    ]
    if meta.get("genre_hint"):
        lines.append(f"所属门类（整片级，仅供参考，不要直接照抄到 T2-4）：{meta['genre_hint']}")
    if meta.get("desc"):
        lines.append(f"人工写的片段概述（仅供参考，可能不完整）：{meta['desc']}")
    lines.append(f"抽帧：{n_frames} 张，等间隔覆盖全片，约 {fps:.1f} fps")
    if asr_text:
        lines.append(f"\n音频转写（ASR，可能有错字）：\n{asr_text[:1500]}")
    else:
        lines.append("\n未提供音频转写。T1-4 听觉特征必须填「低」置信度，"
                     "并在输出里写明「音频信息不可得，无法判断」。不要猜测语言、乐器或环境音。")
    lines.append("\n请输出 JSON。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# few-shot：从金标准里挑高质量样例
# --------------------------------------------------------------------------- #

def pick_fewshot(gold_path: Path = GOLD_PATH, k: int = 3) -> list[dict]:
    """挑全项置信度为「高」、且叙述较完整的样例，覆盖不同层级气质。"""
    if not gold_path.exists():
        return []
    pool = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        confs = [t.get("conf") for t in r["tasks"].values()]
        if confs.count("高") < 10:
            continue
        if not r.get("desc") or len(r["desc"]) < 40:
            continue
        pool.append(r)
    # 按 T2-1 主标签去重，尽量覆盖仪式 / 工序 / 口述 三种
    want = ["仪式场景", "工序说明", "口述访谈", "日常生活嵌入型", "节庆民俗型"]
    chosen, seen = [], set()
    for tag in want:
        for r in pool:
            if r["id"] in seen:
                continue
            labels = r["tasks"]["T2-1"].get("labels") or []
            if tag in labels:
                chosen.append(r)
                seen.add(r["id"])
                break
        if len(chosen) >= k:
            break
    return chosen[:k]


def gold_to_answer(r: dict) -> dict:
    """把金标准一条记录转成「模型应答」格式，用作 few-shot 的 assistant 内容。"""
    ans = {}
    for tid, fields in TASK_FIELDS.items():
        t = r["tasks"][tid]
        item: dict[str, Any] = {}
        for f in fields:
            if f == "label":
                if tid == "T3-1":
                    item["label"] = t.get("symbols") or []
                else:
                    item["label"] = t.get("labels") or []
            elif f == "aux":
                item["aux"] = t.get("aux_labels") or []
            elif f == "alt":
                item["alt"] = t.get("alt_labels") or []
            elif f == "gender":
                item["gender"] = t.get("gender_raw") or ""
            elif f == "out":
                item["out"] = t.get("out") or ""
            elif f == "conf":
                item["conf"] = t.get("conf") or "中"
        ans[tid] = item
    return ans


# --------------------------------------------------------------------------- #
# 抽帧
# --------------------------------------------------------------------------- #

def sample_frames(clip: Path, max_frames: int = 16) -> list[str]:
    """等间隔抽帧，返回 base64 JPEG 列表。用 OpenCV，不依赖 ffmpeg。"""
    import cv2

    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频：{clip}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if total <= 0:
        cap.release()
        raise RuntimeError(f"读不到帧数：{clip}")

    n = max(1, min(max_frames, total))
    idxs = [int(round(i * (total - 1) / max(1, n - 1))) for i in range(n)]
    out: list[str] = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = min(1.0, 896 / max(h, w))          # 长边压到 896，省 token
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if ok:
            out.append(base64.b64encode(buf.tobytes()).decode("ascii"))
    cap.release()
    return out


def extract_audio(clip: Path, out_dir: Path | None = None, sr: int = 16000) -> Path | None:
    """抽 16k 单声道 wav，供 ASR 用。用 imageio-ffmpeg 自带的 ffmpeg。"""
    import subprocess

    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    out_dir = out_dir or (ROOT / ".tmp" / "audio")
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / (clip.stem + ".wav")
    cmd = [exe, "-y", "-loglevel", "error", "-i", str(clip),
           "-vn", "-ac", "1", "-ar", str(sr), str(wav)]
    try:
        subprocess.run(cmd, check=True, timeout=300)
    except Exception:
        return None
    return wav if wav.exists() else None


# --------------------------------------------------------------------------- #
# 调用模型
# --------------------------------------------------------------------------- #

def call_qwen(messages: list[dict], *, model: str | None = None,
              base_url: str | None = None, api_key: str | None = None,
              temperature: float = 0.1, max_tokens: int = 4096) -> str:
    import requests

    base_url = (base_url or os.getenv("QWEN_BASE_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    api_key = api_key or os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    model = model or os.getenv("QWEN_MODEL") or "qwen3-vl-plus"
    if not api_key:
        raise RuntimeError("缺 API key：请设 QWEN_API_KEY（或 DASHSCOPE_API_KEY）")

    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def parse_json_reply(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        t = m.group(0)
    return json.loads(t)


def validate(answer: dict, spec: dict) -> tuple[dict, list[str]]:
    """校验并修正模型输出：缺键补空、标签分词、置信度归位。"""
    problems: list[str] = []
    fixed: dict[str, Any] = {}
    valid_labels = {
        t["id"]: ({i["name"] for i in spec["vocab"][t["label_vocab"]]["items"]}
                  if t.get("label_vocab") and t["label_vocab"] != "genre_taxonomy"
                  else (set(spec["genre_taxonomy"]) if t.get("label_vocab") == "genre_taxonomy"
                        else set()))
        for t in spec["tasks"]
    }
    for t in spec["tasks"]:
        tid = t["id"]
        item = answer.get(tid) or {}
        out: dict[str, Any] = {}
        allowed = valid_labels[tid]
        for f in TASK_FIELDS[tid]:
            v = item.get(f)
            if f in ("label", "aux", "alt"):
                if isinstance(v, str):
                    v = [x.strip() for x in re.split(r"[；;，,、]", v) if x.strip()]
                v = [str(x).strip() for x in (v or []) if str(x).strip()]
                if allowed:
                    for lb in v:
                        if lb not in allowed and not lb.startswith("其他"):
                            problems.append(f"{tid}.{f}: 词表外标签「{lb}」")
                if f == "label" and not v:
                    problems.append(f"{tid}.label: 空（该任务必须给标签）")
                out[f] = v
            elif f == "conf":
                c = str(v or "").strip()
                if c not in ("高", "中", "低"):
                    problems.append(f"{tid}.conf: 非法置信度「{c}」→中")
                    c = "中"
                out[f] = c
            elif f == "gender":
                out[f] = str(v or "").strip()
            else:
                out[f] = str(v or "").strip()
                if not out[f]:
                    problems.append(f"{tid}.out: 空")
        fixed[tid] = out
    missing = [t["id"] for t in spec["tasks"] if t["id"] not in answer]
    if missing:
        problems.append(f"缺任务: {missing}")
    return fixed, problems


def probe_duration(clip: Path) -> float | None:
    import cv2

    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return round(n / fps, 1) if fps > 0 and n > 0 else None


def annotate(clip: Path, meta: dict, spec: dict, *, max_frames: int = 16,
             asr_text: str | None = None, shots: list[dict] | None = None,
             fewshot: int = 0, **kw) -> tuple[dict, list[str], str]:
    meta = dict(meta)
    if not meta.get("dur_s"):
        meta["dur_s"] = probe_duration(clip)
    frames = sample_frames(clip, max_frames=max_frames)
    fps = len(frames) / max(meta.get("dur_s") or 1, 1)

    messages: list[dict] = [{"role": "system", "content": build_system_prompt(spec)}]
    if fewshot:
        for r in pick_fewshot(k=fewshot):
            messages.append({"role": "user",
                             "content": build_user_prompt(
                                 {"film": r["film"], "dur_s": r["dur_s"],
                                  "desc": r["desc"]}, 0, None, 0.0)})
            messages.append({"role": "assistant",
                             "content": json.dumps(gold_to_answer(r), ensure_ascii=False)})

    content: list[dict] = [{"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
                           for b in frames]
    content.append({"type": "text",
                    "text": build_user_prompt(meta, len(frames), asr_text, fps)})
    messages.append({"role": "user", "content": content})

    raw = call_qwen(messages, **kw)
    answer = parse_json_reply(raw)
    fixed, problems = validate(answer, spec)
    return fixed, problems, raw


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def load_asr_text(path: Path | None, min_chars: int = 8) -> str | None:
    """读 ASR 结果。太短或明显是噪声的当作没有——宁可说「无法判断」，也不让垃圾转写误导模型。"""
    if not path or not path.exists():
        return None
    t = path.read_text(encoding="utf-8").strip()
    if len(t) < min_chars:
        return None
    # 纯拉丁/假名混杂且几乎无中文，说明是环境噪声误识，不能当语言证据
    han = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    if han < 4 and not any(ch.isalpha() and "\u4e00" <= ch <= "\u9fff" for ch in t):
        return None
    return t


def main() -> None:
    ap = argparse.ArgumentParser(description="用 Qwen 按三层十二项标准标注非遗片段")
    ap.add_argument("--clip", type=Path, help="单个视频片段")
    ap.add_argument("--batch", type=Path, help="批量目录")
    ap.add_argument("--limit", type=int, default=0, help="批量时只跑前 N 个")
    ap.add_argument("--out", type=Path, help="输出 json / jsonl")
    ap.add_argument("--max-frames", type=int, default=16)
    ap.add_argument("--fewshot", type=int, default=0, help="插入几个金标准样例（消耗 token）")
    ap.add_argument("--asr", help="单个片段的 ASR 转写文本文件（T1-4 需要）")
    ap.add_argument("--asr-dir", type=Path, help="批量时按 <片段名>.txt 查 ASR 结果的目录")
    ap.add_argument("--dry-run", action="store_true", help="只编译提示词并打印，不调模型")
    ap.add_argument("--show-prompt", type=Path, help="把编译后的系统提示词写到文件")
    ap.add_argument("--model", help="覆盖 QWEN_MODEL")
    ap.add_argument("--base-url", help="覆盖 QWEN_BASE_URL")
    args = ap.parse_args()

    spec = load_spec()

    if args.show_prompt or args.dry_run:
        prompt = build_system_prompt(spec)
        if args.show_prompt:
            args.show_prompt.write_text(prompt, encoding="utf-8")
            print(f"系统提示词已写出：{args.show_prompt}（{len(prompt)} 字符）")
        if args.dry_run:
            print("=" * 70)
            print(prompt)
            print("=" * 70)
            if args.clip:
                frames = sample_frames(args.clip, args.max_frames)
                meta = {"film": args.clip.stem, "dur_s": None}
                print(f"\n抽帧：{len(frames)} 张")
                print("\n用户消息（文本部分）：")
                print(build_user_prompt(meta, len(frames), None, 0))
            if not os.getenv("QWEN_API_KEY") and not os.getenv("DASHSCOPE_API_KEY"):
                print("\n[提示] 未检测到 QWEN_API_KEY，真跑前需要设置。")
        return

    kw = {}
    if args.model:
        kw["model"] = args.model
    if args.base_url:
        kw["base_url"] = args.base_url

    asr_single = Path(args.asr) if args.asr else None

    if args.clip:
        clips = [args.clip]
    elif args.batch:
        clips = sorted(p for p in args.batch.iterdir()
                       if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"})
        if args.limit:
            clips = clips[: args.limit]
    else:
        ap.error("需要 --clip 或 --batch")

    results = []
    for i, clip in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {clip.name}", flush=True)
        asr_path = asr_single or (args.asr_dir / (clip.stem + ".txt") if args.asr_dir else None)
        asr_text = load_asr_text(asr_path)
        if asr_path and not asr_text:
            print("  ASR 文本缺失或质量过低，按「无音频信息」处理", flush=True)
        try:
            fixed, problems, raw = annotate(
                clip, {"film": clip.stem, "dur_s": None}, spec,
                max_frames=args.max_frames, asr_text=asr_text,
                fewshot=args.fewshot, **kw)
        except Exception as exc:                     # noqa: BLE001
            print(f"  失败：{exc}", flush=True)
            continue
        rec = {"clip": clip.name, "answer": fixed, "problems": problems,
               "raw": raw if os.getenv("QWEN_KEEP_RAW") else None}
        results.append(rec)
        n_prob = len(problems)
        print(f"  完成，{n_prob} 个问题" + (f"：{problems[:3]}" if n_prob else ""), flush=True)

    if args.out:
        if args.out.suffix == ".jsonl":
            args.out.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
                encoding="utf-8")
        else:
            args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"\n写出 {args.out}（{len(results)} 条）")


if __name__ == "__main__":
    main()
