#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 refs/annotation_spec_v4.json 生成 Label Studio 标注界面配置。

甲方那套「三层十二项」是文本输出制，不是画框：每项要填
  ① 标签（有词表的项才填） ② 输出文本 ③ 置信度
旧 label_config.xml 是 VideoRectangle 框选，和这套对不上，这里重做。

词表不在 spec['tasks'][i]['label_vocab'] 里 —— 那只是个**词表名**（"T2-1"、
"genre_taxonomy"），真正的选项在 spec['vocab'][名字]['items'][*]['name']。
一开始按前者生成，结果每个 Choices 只有一个叫 "T2-1" 的选项。

输出：labelstudio/label_config_t12.xml
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "refs" / "annotation_spec_v4.json"
OUT = ROOT / "labelstudio" / "label_config_t12.xml"

LAYER_TITLE = {
    "T1": "T1 客观表征 · 权重 0.35",
    "T2": "T2 中层语义 · 权重 0.50",
    "T3": "T3 深层解释 · 权重 0.15",
}

# 允许多选的任务：一个片段里本来就可能同时存在多个角色 / 价值 / 关系。
# 其余单选。T2-4 门类严格单选（0.30 权重、零容错），次选写进「补充说明」。
MULTI = {"T2-3", "T3-3", "T3-4"}

HINTS = {
    "T1-1": "总体判断（有/无）+ 物件名称 + 所属类别，如「有；竹篾、刻刀；材料与工具」",
    "T1-2": "总体判断 + 动作名称 + 动作主体，如「有；劈篾、编织；老师傅」",
    "T1-3": "先判是否仪式性场景（是/否 + 依据），再写人物数量、身份、场景类型",
    "T1-4": "有无同期声 / 音乐 / 解说 / 方言；听不清就三段都写「无法判断」，禁止猜语种",
    "T2-1": "先选主导叙事模式，再用一句话说明依据；次要模式写进补充说明",
    "T2-2": "社会空间类型 + 空间特征描述（室内/室外、公共/私人、仪式性标识物）",
    "T2-3": "可多选。角色类型 + 性别（如「传承人[女]」）+ 代际关系；看不出来写「无法判断」",
    "T2-4": "只填一个主门类，依据要指向画面可见证据；把握不大时次选写进补充说明",
    "T3-1": "只写画面里能指出具体位置的符号物；抽象文化断言一律不写",
    "T3-2": "整体情绪基调 + 触发该情绪的画面元素",
    "T3-3": "可多选。这段影像承载的社会价值判断 + 判断依据",
    "T3-4": "可多选。人与人之间的关系类型 + 支撑该判断的互动细节",
}

# 画框用的标签：口径对齐 T1（客观表征），只放「画面上真能圈出来」的东西，
# 不放「传承」「仪式功能」这种抽象概念——那些属于 T2/T3，圈不出来。
BOX_LABELS = [
    ("人物", "#FFCDD2"),
    ("工具", "#C8E6C9"),
    ("材料", "#FFF9C4"),
    ("乐器", "#B3E5FC"),
    ("法器/仪式物", "#E1BEE7"),
    ("服饰/头饰", "#F8BBD0"),
    ("设备", "#D7CCC8"),
    ("场所元素", "#DCE775"),
]


def esc(s: str) -> str:
    return escape(s or "")


def resolve_vocab(spec: dict, task: dict) -> list:
    """label_vocab 是词表名，取回真正的选项名列表。"""
    key = task.get("label_vocab")
    if not key:
        return []
    if key == "genre_taxonomy":
        return list(spec.get("genre_taxonomy") or [])
    block = (spec.get("vocab") or {}).get(key)
    if not block:
        return []
    items = block.get("items") or []
    return [it["name"] for it in items if it.get("name")]


def build() -> str:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    tasks = spec["tasks"]
    confs = spec.get("confidence_levels") or ["高", "中", "低"]

    head = [
        "<View>",
        "  <Style>",
        "    .lsq { font-size: 13px; color: #555; line-height: 1.6; margin: 4px 0 8px; }",
        "    .box { border: 1px solid #e3e3e3; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }",
        "  </Style>",
        '  <Header value="非遗影像 · 三层十二项文本标注"/>',
        '  <Text name="tip" value="上半部分：视频和要素框，AI 已圈出画面里的主要要素，只改错的和补漏的。'
        '下半部分：12 个文本问题，AI 已预填。"/>',
        '  <Video name="video" value="$video" frameRate="25"/>',
        '  <Labels name="tag" toName="video" allowEmpty="true">',
    ]
    for name, color in BOX_LABELS:
        head.append(f'    <Label value="{esc(name)}" background="{color}"/>')
    head += [
        "  </Labels>",
        '  <VideoRectangle name="box" toName="video" smart="true"/>',
        '  <Header value="以下为十二项文本标注"/>',
    ]

    body, last_layer = [], None
    for t in tasks:
        tid, layer = t["id"], t["layer"]
        if layer != last_layer:
            body.append(f'  <Header value="{esc(LAYER_TITLE.get(layer, layer))}"/>')
            last_layer = layer

        weight = t["weight"]
        star = " · 零容错" if tid == "T2-4" else ""
        body.append('  <View class="box">')
        body.append(
            f'    <Header value="{esc(tid)} {esc(t["name"])} · 权重 {weight:.2f}{star}"/>'
        )
        body.append(f'    <Text name="q_{tid}" value="{esc(t["question"])}"/>')

        vocab = resolve_vocab(spec, t)
        if vocab:
            mode = "multiple" if tid in MULTI else "single"
            body.append(
                f'    <Choices name="{tid}_label" toName="video" choice="{mode}" '
                f'required="true" showInline="true">'
            )
            for v in vocab:
                body.append(f'      <Choice value="{esc(v)}"/>')
            body.append("    </Choices>")

        body.append(
            f'    <TextArea name="{tid}_out" toName="video" required="false" editable="true" '
            f'rows="3" maxsubmissions="1" placeholder="{esc(HINTS.get(tid, ""))}"/>'
        )
        body.append(
            f'    <Choices name="{tid}_conf" toName="video" choice="single" '
            f'required="true" showInline="true" title="置信度">'
        )
        for c in confs:
            body.append(f'      <Choice value="{esc(c)}"/>')
        body.append("    </Choices>")
        body.append("  </View>")

    tail = [
        '  <View class="box">',
        '    <Header value="复核备注 · 不计分"/>',
        '    <TextArea name="note" toName="video" required="false" editable="true" rows="2" '
        'placeholder="存疑处、需要跟甲方确认的地方"/>',
        "  </View>",
        "</View>",
    ]
    return "\n".join(head + body + tail) + "\n"


def main():
    xml = build()
    OUT.write_text(xml, encoding="utf-8")

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    print(f"已写出 {OUT.relative_to(ROOT)}  {len(xml)} 字符")
    print(f"<View> {xml.count('<View')} 层，<Choice> {xml.count('<Choice ')} 个")
    for t in spec["tasks"]:
        n = len(resolve_vocab(spec, t))
        mode = "多选" if t["id"] in MULTI else ("单选" if n else "纯文本")
        print(f"  {t['id']}  {t['name'][:10]:<12} 选项 {n:>3}  {mode}")


if __name__ == "__main__":
    main()
