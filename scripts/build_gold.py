"""把甲方 1397 行人工标注抽成机器可读的金标准集（gold.jsonl）。

标签切分的核心难点：分隔符与标签内部字符冲突
  - 「传统体育、游艺与杂技」内部的顿号
  - 「老师傅/传承人」「后勤/生活辅助空间」内部的斜杠
所以不用 split，改用**词表最长匹配**扫描，命中即切出，未命中才当分隔符跳过。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path("/Users/lixin/WorkBuddy/2026-10-24-20-33-54")
SRC = ROOT / "refs" / "20260608影片片段标注.xlsx"
SPEC = ROOT / "refs" / "annotation_spec_v4.json"
OUT_JSONL = ROOT / "refs" / "gold.jsonl"
OUT_REPORT = ROOT / "refs" / "gold_normalize_report.md"

# 同义写法 -> 规范名（来自对 1397 行的实测统计）
ALIASES = {
    "T2-1": {
        "日常生活嵌入性": "日常生活嵌入型", "日常生活型": "日常生活嵌入型",
        "物质与文化符号扫描": "物质文化与符号扫描",
        "工序说明型": "工序说明", "集体协作生产型": "集体协作生产",
        "演出准备型": "准备与制作前序", "世俗生活与家庭纪实": "日常生活嵌入型",
    },
    "T2-2": {
        "户外自然空间": "户外自然环境", "户外环境": "户外自然环境",
        "流动空间": "流动空间/仪式路径", "生活辅助空间": "后勤/生活辅助空间",
        "后勤辅助空间": "后勤/生活辅助空间", "后勤": "后勤/生活辅助空间",
        "学校": "学校/传习所",
        "传统民居与宗族聚落空间": "宗族祠堂",
        "集市": "集市/商业空间", "商业空间": "集市/商业空间",
        "仪式路线": "流动空间/仪式路径",
    },
    "T2-3": {
        "老师傅": "老师傅/传承人", "传承人": "老师傅/传承人",
        "传习者": "成年学徒/传习者", "成年学徒": "成年学徒/传习者",
        "仪式主持人": "仪式主持者",
        "仪式东家": "仪式委托人/东家", "仪式委托人": "仪式委托人/东家",
        "东家": "仪式委托人/东家", "／东家": "仪式委托人/东家",
        "口述访谈人": "口述访谈者",
        "社区居民": "社区成员", "社会成员": "社区成员",
        "村中长老": "社区成员", "参与者": "社区成员", "节日参与者": "社区成员",
        "研究者": "记录者/研究者/地方官员", "地方官员": "记录者/研究者/地方官员",
        "记录者": "记录者/研究者/地方官员", "记录员": "记录者/研究者/地方官员",
        "研究员": "记录者/研究者/地方官员",
        "家庭纽带": "家庭纽带/幕后支持者",
        "家庭纽带／幕后支持者": "家庭纽带/幕后支持者",
        "顾客": "顾客/买家",
    },
    "T2-4": {
        "传统戏曲": "传统戏剧", "民间音乐": "传统音乐",
        "传统体育游艺与杂技": "传统体育、游艺与杂技",
        "传统习俗": "民俗",
    },
    "T3-2": {
        "温泉怀旧": "温情怀旧", "混杂难以概括": "混合难以归类",
        "热闹兴奋": "欢快热烈",
    },
    "T3-3": {
        "家族与社区凝聚": "家庭与社区凝聚",
    },
    "T3-4": {
        "竞技与展示关系": "竞争与展示关系", "家庭内部传授关系": "家庭内部传授",
        "国家介入": "国家/机构介入关系", "机构介入": "国家/机构介入关系",
        "国家": "国家/机构介入关系",
        "代际传承关系": "师徒代际传承",
    },
}

# 标注者自创、但高频且语义明确的「事实上的新类」：不塞进封闭词表，单独计入 others，
# 并在报告里作为「词表缺口」证据。值为它在 others 里的规范名。
NOVEL = {
    "T2-1": {"同辈交流", "同辈技艺交流", "竞技场景", "竞争场景", "家庭生活"},
    "T2-2": {"现代办公与机构空间", "展演附属空间", "社区公共仪式空间",
             "专业工作室", "公共文化空间", "现代公共生活空间", "工作坊"},
    "T2-3": {"毕摩为口述访谈者", "灵魂", "断代传承者", "活动筹备者", "仪式协助者"},
    "T3-4": {"亲友情感互动与日常陪伴", "日常陪伴", "家庭分工协作关系",
             "礼俗互动关系", "记录者与报道人互动关系", "上下级协作"},
}

# 表示「无 / 不适用」的写法，统一成 None
NULLISH = {"无", "否", "/", "无特殊角色", "无可识别", "明显关系", "无特殊", "—", "-", "空"}
NULLISH_PREFIX = ("无明显", "并未体现", "无特殊")

CONF = {"高", "中", "低"}

# 评测表列（1-based，openpyxl 直接用）
COL = {
    "film": 1, "start": 2, "end": 3, "dur_s": 4, "genre_raw": 6, "annotator": 7,
    "difficulty": 9, "desc": 10,
    "T1-1.out": 11, "T1-1.conf": 12, "T1-2.out": 13, "T1-2.conf": 14,
    "T1-3.out": 15, "T1-3.conf": 16, "T1-4.out": 17, "T1-4.conf": 18,
    "T2-1.label": 19, "T2-1.aux": 20, "T2-1.out": 21, "T2-1.conf": 22,
    "T2-2.label": 23, "T2-2.out": 24, "T2-2.conf": 25,
    "T2-3.label": 26, "T2-3.gender": 27, "T2-3.out": 28, "T2-3.conf": 29,
    "T2-4.label": 30, "T2-4.alt": 31, "T2-4.out": 32, "T2-4.conf": 33,
    "T3-1.label": 34, "T3-1.out": 35, "T3-1.conf": 36,
    "T3-2.label": 37, "T3-2.out": 38, "T3-2.conf": 39,
    "T3-3.label": 40, "T3-3.out": 41, "T3-3.conf": 42,
    "T3-4.label": 43, "T3-4.out": 44, "T3-4.conf": 45,
}

# 有封闭词表、需要做标签切分的任务
LABEL_TASKS = ["T2-1", "T2-2", "T2-3", "T2-4", "T3-2", "T3-3", "T3-4"]


def clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\n", " ").replace("\r", " ").replace("\u3000", " ")
    return re.sub(r"\s{2,}", " ", s).strip()


class Splitter:
    """词表最长匹配切分器。"""

    def __init__(self, terms: list[str]) -> None:
        # 去掉兜底项和纯符号，按长度倒序匹配
        self.terms = sorted({t for t in terms if t and t != "其他"}, key=len, reverse=True)
        self.alias: dict[str, str] = {}
        self.novel: set[str] = set()

    def with_alias(self, task: str) -> "Splitter":
        self.alias = {k: v for k, v in ALIASES.get(task, {}).items()}
        self.novel = NOVEL.get(task, set())
        # 别名与自创类名本身也是合法匹配串（否则会被逐字打散）
        self.terms = sorted(set(self.terms) | set(self.alias) | self.novel,
                            key=len, reverse=True)
        return self

    def split(self, text: str) -> dict:
        """返回 {labels:[规范名], others:[其他/自创类名], nullish:bool, unresolved:[残留]}"""
        s = clean(text)
        labels: list[str] = []
        others: list[str] = []
        unresolved: list[str] = []
        nullish = False

        if not s:
            return {"labels": [], "others": [], "nullish": False, "unresolved": []}

        i, n = 0, len(s)
        while i < n:
            # 1) 「其他：xxx」/「其他 xxx」——吃掉到下一个分隔符
            m_other = re.match(r"其他\s*[：:]?\s*", s[i:])
            if m_other:
                rest = s[i + m_other.end():]
                stop = len(rest)
                for sep in "；;，,。":
                    p = rest.find(sep)
                    if p != -1:
                        stop = min(stop, p)
                payload = rest[:stop].strip(" 　、")
                if payload and payload not in others:
                    others.append(payload)
                i += m_other.end() + stop
                continue

            # 2) 最长匹配词表
            hit = None
            for t in self.terms:
                if s.startswith(t, i):
                    hit = t
                    break
            if hit:
                i += len(hit)
                if hit in self.novel:                    # 自创类 -> others
                    if hit not in others:
                        others.append(hit)
                else:
                    canon = self.alias.get(hit, hit)     # 别名 -> 规范名
                    if canon not in labels:
                        labels.append(canon)
                continue

            # 3) 未命中：判断是否是「无」类
            seg_end = len(s)
            for sep in "；;，,。、/ ":
                p = s.find(sep, i)
                if p != -1:
                    seg_end = min(seg_end, p)
            seg = s[i:seg_end].strip()
            if seg:
                if seg in NULLISH or seg.startswith(NULLISH_PREFIX):
                    nullish = True
                else:
                    unresolved.append(seg)
                i = seg_end
            else:
                i += 1

        if nullish and not labels and not others:
            labels = []
        return {"labels": labels, "others": others, "nullish": nullish, "unresolved": unresolved}


def sane_dur(v: Any) -> float | None:
    """时长清洗：Excel 时间序列号会算出负数或天文数字，一律置空。"""
    try:
        d = float(str(v))
    except (TypeError, ValueError):
        return None
    if d <= 0 or d > 3600:
        return None
    return round(d, 1)


def build():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    vocab = {k: [i["name"] for i in v["items"]] for k, v in spec["vocab"].items()}
    vocab["T2-4"] = spec["genre_taxonomy"]
    vocab["T3-3"] = [x for x in vocab["T3-3"] if "其他" not in x] + ["其他"]

    splitters = {t: Splitter(vocab[t]).with_alias(t) for t in LABEL_TASKS}

    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["评测表"]

    records = []
    stats = defaultdict(Counter)       # task -> Counter(规范标签)
    other_stat = defaultdict(Counter)  # task -> Counter(其他/自创类名)
    unresolved_stat = defaultdict(Counter)
    nullish_stat = Counter()
    conf_stat = defaultdict(Counter)
    skipped_empty = 0
    row_id = 0

    for r in range(3, ws.max_row + 1):
        row = [c for c in next(ws.iter_rows(min_row=r, max_row=r, values_only=True), ())]
        def g(key: str) -> str:
            idx = COL[key] - 1
            return clean(row[idx]) if idx < len(row) else ""

        film = g("film")
        if not film:
            skipped_empty += 1
            continue
        # 影片名去掉书名号，便于和片段文件名对齐
        film_name = film.strip("《》").strip()

        row_id += 1
        rec = {
            "id": f"G{row_id:04d}",
            "src_row": r,
            "film": film_name,
            "start": g("start"), "end": g("end"),
            "dur_s": sane_dur(g("dur_s")),
            "dur_s_raw": g("dur_s"),
            "genre_raw": g("genre_raw"),
            "annotator": g("annotator"),
            "difficulty": g("difficulty"),
            "desc": g("desc"),
            "tasks": {},
        }

        for task in spec["tasks"]:
            tid = task["id"]
            out = g(f"{tid}.out")
            conf = g(f"{tid}.conf")
            item = {"out": out, "conf": conf if conf in CONF else None,
                    "conf_raw": conf if conf not in CONF else None}

            if tid in LABEL_TASKS:
                raw = g(f"{tid}.label")
                res = splitters[tid].split(raw)
                item["label_raw"] = raw
                item["labels"] = res["labels"]
                item["other_labels"] = res["others"]
                item["nullish"] = res["nullish"] and not res["labels"]
                if res["unresolved"]:
                    unresolved_stat[tid].update(res["unresolved"])
                for lb in res["labels"]:
                    stats[tid][lb] += 1
                if res["others"]:
                    stats[tid]["（其他：自拟）"] += 1
                    other_stat[tid].update(res["others"])
                if item["nullish"]:
                    nullish_stat[tid] += 1
            elif tid == "T3-1":
                raw = g(f"{tid}.label")
                item["label_raw"] = raw
                low = raw.lower()
                if raw in {"无", "否", "/", ""} or raw.startswith("无"):
                    item["symbols"] = []
                    item["nullish"] = raw != ""
                elif raw in {"有"}:
                    item["symbols"] = []
                    item["has_symbol_flag"] = True
                else:
                    item["symbols"] = [x.strip() for x in re.split(r"[；;，,、]", raw) if x.strip()]

            rec["tasks"][tid] = item
            if item["conf"]:
                conf_stat[tid][item["conf"]] += 1

        records.append(rec)

    wb.close()

    OUT_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )

    # ---------- 报告 ----------
    lines = ["# 金标准集归一化报告", "",
             f"- 来源：`{SRC.name}` → sheet「评测表」",
             f"- 有效记录：**{len(records)}** 条（跳过整行空行 {skipped_empty} 条）",
             f"- 影片数：{len({r['film'] for r in records})} 部",
             f"- 输出：`{OUT_JSONL.name}`", ""]

    for tid in LABEL_TASKS:
        total = sum(stats[tid].values())
        lines.append(f"## {tid} 标签分布（归一化后，共 {total} 个标签实例）")
        lines.append("")
        lines.append("| 标签 | 次数 | 占比 |")
        lines.append("|---|---:|---:|")
        for lb, c in stats[tid].most_common():
            lines.append(f"| {lb} | {c} | {c/total*100:.1f}% |")
        if nullish_stat[tid]:
            lines.append(f"| （标注为「无/不适用」） | {nullish_stat[tid]} | - |")
        lines.append("")
        if other_stat[tid]:
            lines.append(f"**「其他」/自创类 Top 12**（合计 {sum(other_stat[tid].values())} 处，"
                         f"占该任务标签实例 {sum(other_stat[tid].values())/total*100:.1f}%）：")
            lines.append("")
            lines.append("| 自拟类名 | 次数 |")
            lines.append("|---|---:|")
            for u, c in other_stat[tid].most_common(12):
                lines.append(f"| {u} | {c} |")
            lines.append("")
        if unresolved_stat[tid]:
            lines.append(f"**未解析残留 {sum(unresolved_stat[tid].values())} 处**（前 15）：")
            lines.append("")
            lines.append("```")
            for u, c in unresolved_stat[tid].most_common(15):
                lines.append(f"{c:>4}  {u}")
            lines.append("```")
            lines.append("")

    lines.append("## 置信度分布")
    lines.append("")
    lines.append("| 任务 | 高 | 中 | 低 | 缺失 |")
    lines.append("|---|---:|---:|---:|---:|")
    for task in spec["tasks"]:
        tid = task["id"]
        c = conf_stat[tid]
        miss = len(records) - sum(c.values())
        lines.append(f"| {tid} | {c.get('高',0)} | {c.get('中',0)} | {c.get('低',0)} | {miss} |")

    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"写出 {OUT_JSONL} （{len(records)} 条）")
    print(f"写出 {OUT_REPORT}")
    print()
    for tid in LABEL_TASKS:
        total = sum(stats[tid].values())
        un = sum(unresolved_stat[tid].values())
        print(f"  {tid}: 标签实例 {total:>5}，未解析 {un:>4}，nullish {nullish_stat[tid]:>4}")
    return records


if __name__ == "__main__":
    build()
