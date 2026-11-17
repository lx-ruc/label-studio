"""用 Qwen 按《节日志影像标注字段》做场景层（C）与事件叙事层（N）预标注。

字段定义来自甲方《节日志影像标注字段.xlsx》（2026-11 版），三层：
  场景层 C：C-1 时间 / C-2 地点 / C-3 场所与空间用途 / C-4 镜头与画面呈现 / C-5 声音
  事件与叙事层 N：N-1 节日与活动识别 / N-2 活动阶段与流程 / N-3 参与组织方式 /
                  N-4 概括性描述 / N-5 影像呈现方式
  实体实例层 O：8 类框（人物 O-P / 群体单元 O-G / 身体部位 O-B / 器具与工具 O-T /
                  材料与制作物 O-M / 服饰与配饰 O-C / 食物与供品 O-F / 装置与标识物 O-D）
                —— 框走 qwen_boxes.py + det_person.py，不在这个脚本里。

复用 qwen_label.py 的抽帧 / 抽音频 / 调模型 / 解析，只换字段定义和提示词。

    # 先看编译出的提示词（不调模型）
    python3 scripts/qwen_label_festival.py --dry-run --show-prompt /tmp/f.txt
    # 批量真跑（ASR 文本按 .tmp/asr4/<片名>.txt）
    python3 scripts/qwen_label_festival.py --batch data/clips4 \
        --asr-dir .tmp/asr4 --out .tmp/qwen_festival_run1.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qwen_label import (build_user_prompt, call_qwen, extract_audio,  # noqa: E402
                        load_asr_text, parse_json_reply, probe_duration,
                        sample_frames)

# --------------------------------------------------------------------------- #
# 字段定义：id -> (中文名, 任务说明, 词表 {子键: (标题, [选项], 单选/多选)})
# 词表一律用甲方表里的原词。
# --------------------------------------------------------------------------- #
FIELDS: dict[str, dict] = {
    "C-1": {"name": "时间",
            "ask": "公历日期，农历/节日历法时间，节日相对位置（第几天、某环节前/中/后），昼夜",
            "note": "资料里提不出来的部分写「无法判断」，不要猜日期。",
            "keys": {}},
    "C-2": {"name": "地点",
            "ask": "行政区、村落或社区、具体场所、路线节点",
            "note": "根据字幕、场记或其他资料可直接提取；提不出来写「无法判断」。",
            "keys": {}},
    "C-3": {"name": "场所与空间用途",
            "ask": "识别室内外环境、场所类型及当前用途，如家庭厨房、村落广场、巡游道路，以及制作区、供奉区、宴饮区等",
            "note": "特写看不出环境时填「无法判断」。",
            "keys": {}},
    "C-4": {"name": "镜头与画面呈现",
            "ask": "记录景别、拍摄角度及镜头运动，说明人物、物件和活动在画面中的呈现方式",
            "note": "景别或镜头运动明显变化时分时段记录；手持可与其他镜头运动并存。",
            "keys": {
                "shot": ("景别", ["远景", "全景", "中景", "近景", "特写"], "multi"),
                "angle": ("角度", ["平视", "俯拍", "仰拍"], "multi"),
                "move": ("运动", ["固定", "推拉", "摇移", "跟拍", "手持"], "multi"),
            }},
    "C-5": {"name": "声音",
            "ask": "语言、现场音乐、环境声及后期配音或配乐",
            "note": "音频转写不可靠时不要推断语种，语言填「无」或写「无法判断」。",
            "keys": {
                "lang": ("语言", ["普通话", "具体方言", "民族语言", "无"], "multi"),
                "music": ("音乐来源", ["现场演奏", "后期配乐", "唱腔"], "multi"),
            }},
    "N-1": {"name": "节日与活动识别",
            "ask": "记录节日名称、地方称谓及具体活动名称，识别制作、祭祀礼仪、巡游、表演、竞技、宴饮馈赠等活动类型",
            "note": "示例：节日：妈祖诞辰（地方称“妈生”）；活动：请神；类型：祭祀礼仪。看不出来写「无法判断」。",
            "keys": {}},
    "N-2": {"name": "活动阶段与流程",
            "ask": "确定片段处于筹备、开展或收尾阶段；依据具体节日程序，记录环节名称、先后顺序及并行关系",
            "note": "示例：开展阶段，环节“请神”，承接“搭棚”。",
            "keys": {
                "stage": ("阶段", ["筹备", "开展", "收尾", "无法判断"], "single"),
                "rel": ("与前后事件的关系", ["承接", "并行", "独立", "无法判断"], "single"),
            }},
    "N-3": {"name": "参与组织方式",
            "ask": "分别记录参与者在当前活动中的组织形式，以及有明确证据支持的参与者关系或组织归属",
            "note": "关系要有明确证据（同期讲解、称呼、着装一致等）；没有证据选「无法判断」。一般性背景人群不算群体单元。",
            "keys": {
                "org": ("组织形式", ["单人", "多人协作", "队列或编队", "多人独立参与", "混合", "无法判断"], "multi"),
                "rel": ("参与者关系或组织归属",
                        ["家庭", "师徒", "邻里", "社区组织", "机构", "临时组合", "其他", "无法判断"], "multi"),
            }},
    "N-4": {"name": "概括性描述",
            "ask": "使用完整语句描述片段中谁参与、发生了什么、涉及哪些主要物件，以及出现了哪些可见变化",
            "note": "示例：六名男性村民在祠堂前广场抬神轿绕行，轿内神像由红绸覆盖，两侧有人持旌旗随行。",
            "keys": {}},
    "N-5": {"name": "影像呈现方式",
            "ask": "识别片段如何记录、讲述或展示活动，区分现场记录、口述访谈、示范教学、摆拍复现及资料插入等方式",
            "note": "示例：口述访谈；受访者面向采访者讲述本村节日巡游路线的变化。",
            "keys": {
                "mode": ("方式", ["现场记录", "口述访谈", "示范教学", "摆拍复现", "资料插入", "其他", "无法判断"], "multi"),
            }},
}

SYSTEM_RULES = """你是节日志影像标注员，严格按《节日志影像标注字段》给视频片段打标。

## 硬性规则（违反任何一条，该条标注作废）

1. **词表选项只能用原词**，一个字都不能改。词表外的情况用 `其他` 或 `无法判断`，
   并在 out 里写清楚是什么。
2. **每项先给结论再给依据**，依据要指向画面里实际能看到的东西。禁止编造人名、
   地名、机构名——除非画面字幕或音频里明确出现。
3. **画面或资料里没有的，就写「无法判断」**。宁可留白，不要为了显得有发现而虚构。
   这一点比覆盖率重要。
4. 你看的是**一个连续片段**，不是整部片子。判断只针对这一段。
5. 音频转写可能有错字。转写是零星外语音节、乱码式短语或与画面明显无关的内容时，
   判定为「音频信息不可得」，C-5 语言不要据碎片猜语种。
6. out 字段一律用完整中文语句；选了词表选项的，out 里补充依据或细节。

## 输出格式

只返回一个 JSON 对象，不要 Markdown 代码块，不要任何解释文字。每个字段一个键，
带词表的字段用子键存选项数组（多选给多个，单选给一个），out 存说明文字：

{
  "C-1": {"out": "..."},
  "C-4": {"shot": ["全景"], "angle": ["平视"], "move": ["跟拍", "手持"], "out": "..."},
  "C-5": {"lang": ["具体方言"], "music": ["现场演奏"], "out": "..."},
  "N-2": {"stage": ["开展"], "rel": ["承接"], "out": "..."},
  "N-3": {"org": ["多人协作"], "rel": ["家庭"], "out": "..."},
  "N-4": {"out": "..."},
  "N-5": {"mode": ["现场记录"], "out": "..."}
}

全部 10 个键（C-1 ~ C-5、N-1 ~ N-5）都必须出现。
"""


def render_fields() -> str:
    blocks = []
    for fid, f in FIELDS.items():
        blocks.append(f"\n**【{fid}】{f['name']}**")
        blocks.append(f"任务：{f['ask']}")
        if f["keys"]:
            for k, (title, opts, kind) in f["keys"].items():
                kind_txt = "多选" if kind == "multi" else "单选"
                blocks.append(f"  子键 {k}（{title}，{kind_txt}）：{' / '.join(opts)}")
        blocks.append(f"写法：{f['note']}")
    return "\n".join(blocks)


def build_system_prompt() -> str:
    head = ("# 任务\n\n下面给你一段节日志影像片段（若干等间隔抽帧）和它的元信息。"
            "请按场景层（C）与事件叙事层（N）共 10 个字段逐项标注。实体实例层（O）的框不用你标。\n")
    tail = ("\n\n## 最后再确认一遍\n\n"
            "- 10 个键是否齐全（C-1 ~ C-5、N-1 ~ N-5）\n"
            "- 词表选项是否用的原词、有没有该「无法判断」却硬猜的\n"
            "- 有没有编造画面里不存在的人名、地名、机构名\n")
    return head + render_fields() + "\n\n" + SYSTEM_RULES + tail


def validate(answer: dict) -> tuple[dict, list[str]]:
    """缺键补空、词表外选项剔掉（保留原词才进 LS）。"""
    problems: list[str] = []
    fixed: dict = {}
    for fid, f in FIELDS.items():
        item = answer.get(fid) or {}
        out: dict = {}
        for k, (title, opts, kind) in f["keys"].items():
            v = item.get(k)
            if isinstance(v, str):
                v = [v]
            v = [str(x).strip() for x in (v or []) if str(x).strip()]
            bad = [x for x in v if x not in opts]
            if bad:
                problems.append(f"{fid}.{k}: 词表外选项 {bad}")
                v = [x for x in v if x in opts]
            if not v:
                v = ["无法判断"]
            out[k] = v
        t = str(item.get("out") or "").strip()
        if not t:
            t = "无法判断"
            problems.append(f"{fid}.out: 空")
        out["out"] = t
        if fid not in answer:
            problems.append(f"{fid}: 缺字段")
        fixed[fid] = out
    return fixed, problems


def annotate(clip: Path, max_frames: int = 16, asr_text: str | None = None, **kw):
    dur = probe_duration(clip)
    frames = sample_frames(clip, max_frames=max_frames)
    fps = len(frames) / max(dur or 1, 1)

    messages = [{"role": "system", "content": build_system_prompt()}]
    content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
               for b in frames]
    content.append({"type": "text",
                    "text": build_user_prompt({"film": clip.stem, "dur_s": dur},
                                              len(frames), asr_text, fps)})
    messages.append({"role": "user", "content": content})

    raw = call_qwen(messages, **kw)
    answer, problems = validate(parse_json_reply(raw))
    return answer, problems, raw


def main() -> None:
    ap = argparse.ArgumentParser(description="节日志字段（C/N 层）Qwen 预标注")
    ap.add_argument("--clip", type=Path)
    ap.add_argument("--batch", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-frames", type=int, default=16)
    ap.add_argument("--asr", type=Path, help="单个片段的 ASR 文本文件")
    ap.add_argument("--asr-dir", type=Path, help="批量时按 <片段名>.txt 查 ASR 结果")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model")
    args = ap.parse_args()

    if args.dry_run:
        p = build_system_prompt()
        print(p[:2000])
        print(f"\n（提示词共 {len(p)} 字符）")
        return

    kw = {"model": args.model} if args.model else {}
    clips = [args.clip] if args.clip else sorted(
        p for p in args.batch.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"})
    if not args.clip and not args.batch:
        ap.error("需要 --clip 或 --batch")

    out = open(args.out, "a", encoding="utf-8")
    for i, clip in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {clip.name}", flush=True)
        asr_path = args.asr or (args.asr_dir / (clip.stem + ".txt") if args.asr_dir else None)
        asr_text = load_asr_text(asr_path)
        if asr_path and not asr_text:
            print("  ASR 缺失或质量过低，按「无音频信息」处理", flush=True)
        try:
            fixed, problems, _ = annotate(clip, max_frames=args.max_frames,
                                          asr_text=asr_text, **kw)
        except Exception as exc:                     # noqa: BLE001
            print(f"  失败：{type(exc).__name__}: {exc}", flush=True)
            continue
        out.write(json.dumps({"clip": clip.name, "answer": fixed,
                              "problems": problems}, ensure_ascii=False) + "\n")
        out.flush()
        print(f"  完成，{len(problems)} 个问题" + (f"：{problems[:4]}" if problems else ""),
              flush=True)
    out.close()
    print(f"\n写出 {args.out}")


if __name__ == "__main__":
    main()
