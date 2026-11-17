#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 LSF 前端 sourcemap 里全量提取 UI 文案，跟现有词典做差集。

LSF 是把源码编译成 bundle 的，但构建时带上了 sourcemap，
`.js.map` 的 sourcesContent 里就是**未压缩的原始源码**。
所以能拿到真实的 UI 字符串，而不是从页面上肉眼抄。

提取两类位置：
  1. 属性位 —— title:/description:/tooltip:/placeholder:/aria-label:/alt:
  2. JSX 文本位 —— >Some text<

然后做英文性判定 + 代码特征排除，避免把变量名、CSS 类名、文件路径当成文案。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

DIST = Path("/Users/lixin/.workbuddy/binaries/python/envs/labelstudio/"
            "lib/python3.13/site-packages/web/dist/apps/labelstudio")
DICT_JS = Path("/Users/lixin/WorkBuddy/2026-10-24-20-33-54/labelstudio/ls-zh.user.js")

# 属性位：只取这些键后面的字符串字面量
ATTR_PAT = re.compile(
    r"\b(title|description|tooltip|placeholder|aria-label|alt|header|caption|hint)\s*:\s*"
    r"('([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\")"
)

# JSX 文本位：>文本<，中间不能出现 JSX 表达式的花括号
JSX_TEXT_PAT = re.compile(r">\s*([^{}<>][^{}<>]*?)\s*<")

# 明显是代码 / 数据，不是给人看的文案
CODEY = re.compile(
    r"[{}();=<>|*@#\\`]|=>|&&|\bvar\b|\bconst\b|\blet\b|\bfunction\b|"
    r"\breturn\b|\bimport\b|\bexport\b|\bextends\b|\bkeyof\b|\btypeof\b|"
    r"\bPromise\b|\bArray\b|\bvoid\b|\bunknown\b|\bnever\b|\bboolean\b|"
    r"\.css|\.js|\.svg|\.png|\.tsx|\.jsx|"
    r"^#[0-9a-fA-F]{3,8}$|^\d+(\.\d+)?(px|em|rem|%|s|ms)$|"
    r"https?://|//[a-z]|\bthis\b|\bclass\b"
)

# 英文：允许常见标点，但不允许中日韩字符
NON_EN = re.compile(r"[　-鿿＀-￯]")

STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "it",
             "for", "on", "by", "at", "as", "be", "not", "this", "that"}


def unq(lit: str) -> str:
    s = lit[1:-1]
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\n", " ").replace("\\t", " ")


def looks_like_ui(t: str) -> bool:
    t = t.strip()
    if not (2 <= len(t) <= 60):
        return False
    # 多行的基本都是 JSDoc 注释 / 代码片段，不是界面文案
    if "\n" in t or "\r" in t:
        return False
    if NON_EN.search(t):
        return False
    if CODEY.search(t):
        return False
    if t.lower() in STOPWORDS:
        return False
    # 纯数字 / 纯符号
    if not re.search(r"[A-Za-z]{2,}", t):
        return False
    # camelCase 且无空格 —— 大概率是变量或类名
    if " " not in t and re.match(r"^[a-z]+[A-Z]", t):
        return False
    # 以标点开头/含冒号的，基本是代码片段或「标签: 值」的组合串，翻了也不完整
    if t[0] in ".,:;!?-—" or ":" in t:
        return False
    # LS 的 UI 文案基本都首字母大写；小写开头的多半是英文句子片段或标识符
    if not t[0].isupper():
        return False
    return True


def main():
    if not DIST.exists():
        sys.exit(f"找不到 LSF dist: {DIST}")

    maps = sorted(DIST.glob("*.js.map"))
    print(f"找到 {len(maps)} 个 sourcemap\n")

    attr_cnt, jsx_cnt = Counter(), Counter()
    attr_src, jsx_src = {}, {}

    for m in maps:
        try:
            data = json.loads(m.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            print(f"[解析失败] {m.name}: {e}")
            continue
        for src in data.get("sourcesContent") or []:
            if not isinstance(src, str) or len(src) < 40:
                continue
            for mm in ATTR_PAT.finditer(src):
                t = unq(mm.group(2)).strip()
                if looks_like_ui(t):
                    attr_cnt[t] += 1
                    attr_src.setdefault(t, m.stem)
            for mm in JSX_TEXT_PAT.finditer(src):
                t = mm.group(1).strip()
                if looks_like_ui(t):
                    jsx_cnt[t] += 1
                    jsx_src.setdefault(t, m.stem)

    # 已翻译的词条：只在 `const ZH = { ... }` 这一段里取，别扫到函数体
    js_text = DICT_JS.read_text(encoding="utf-8")
    start = js_text.index("const ZH = {")
    end = js_text.index("\n  };", start)
    block = js_text[start:end]
    have = set()
    for mm in re.finditer(r"^\s{4}(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|([A-Za-z][A-Za-z0-9 ]*))\s*:",
                          block, re.M):
        key = mm.group(1) or mm.group(2) or mm.group(3)
        have.add(key.strip())

    print(f"现词典 {len(have)} 条")
    print(f"属性位提取 {len(attr_cnt)} 条，JSX 文本位提取 {len(jsx_cnt)} 条\n")

    out = Path("/Users/lixin/WorkBuddy/2026-10-24-20-33-54/.tmp/ui_strings.json")
    cand = {}
    for t, c in attr_cnt.items():
        cand.setdefault(t, {"n": 0, "where": "attr", "bundle": attr_src.get(t, "")})
        cand[t]["n"] += c
    for t, c in jsx_cnt.items():
        cand.setdefault(t, {"n": 0, "where": "jsx", "bundle": jsx_src.get(t, "")})
        cand[t]["n"] += c

    miss = {k: v for k, v in cand.items() if k not in have}
    ranked = sorted(miss.items(), key=lambda kv: (-kv[1]["n"], kv[0].lower()))
    print(f"未翻译 {len(miss)} 条。出现次数最多的 40 条：\n")
    for t, v in ranked[:40]:
        print(f"  {v['n']:4d}  [{v['where']:4s}|{v['bundle']:8s}] {t!r}")

    out.write_text(json.dumps(
        {"all": cand, "missing": {k: v for k, v in ranked}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完整清单 -> {out}")


if __name__ == "__main__":
    main()
