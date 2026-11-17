#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按非遗门类检索 B 站候选视频，输出 candidates.json

仅用于本地标注练习/流程验证，请勿用于任何商业或再分发用途。
"""
import json
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
COOKIE_FILE = Path("/tmp/bili.txt")
OUT = Path(__file__).resolve().parent.parent / "candidates.json"

# (关键词, 非遗门类)
QUERIES = [
    ("非遗 剪纸 技法",       "传统美术"),
    ("非遗 苏绣 刺绣 针法",  "传统美术"),
    ("非遗 景德镇 拉坯 陶瓷", "传统技艺"),
    ("非遗 木雕 雕刻",       "传统技艺"),
    ("非遗 竹编 编织",       "传统技艺"),
    ("非遗 皮影戏",          "传统戏剧"),
    ("非遗 打铁花",          "民俗"),
    ("非遗 云锦 织造",       "传统技艺"),
    ("非遗 毛笔 制作",       "传统技艺"),
    ("非遗 制茶 手工",       "传统技艺"),
    ("非遗 银饰 锻造",       "传统技艺"),
    ("非遗 油纸伞 制作",     "传统技艺"),
]


def ensure_cookie():
    """拿 buvid3，否则接口返回 412"""
    if not COOKIE_FILE.exists():
        subprocess.run(["curl", "-s", "-c", str(COOKIE_FILE), "-o", "/dev/null",
                        "-A", UA, "--max-time", "15", "https://www.bilibili.com/"],
                       check=False)
    txt = COOKIE_FILE.read_text()
    return "buvid3=" + txt.split("buvid3\t")[1].split("\n")[0].strip()


def search(keyword, cookie, page=1):
    url = ("https://api.bilibili.com/x/web-interface/search/type"
           f"?search_type=video&page={page}&keyword={urllib.parse.quote(keyword)}")
    r = requests.get(url, headers={"User-Agent": UA, "Cookie": cookie,
                                   "Referer": "https://search.bilibili.com/"},
                     timeout=20)
    try:
        data = r.json()
    except Exception:
        return []
    if data.get("code") != 0:
        return []
    out = []
    for it in (data.get("data") or {}).get("result", []):
        dur = it.get("duration", "")
        secs = 0
        if dur and ":" in dur:
            parts = [int(x) for x in dur.split(":") if x.isdigit()]
            secs = sum(v * 60 ** (len(parts) - 1 - i) for i, v in enumerate(parts))
        out.append({
            "bvid": it.get("bvid"),
            "title": it.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", ""),
            "author": it.get("author"),
            "duration": dur,
            "seconds": secs,
            "play": it.get("play"),
            "url": f"https://www.bilibili.com/video/{it.get('bvid')}",
        })
    return out


def main():
    cookie = ensure_cookie()
    seen, cands = set(), []
    for kw, cat in QUERIES:
        res = search(kw, cookie)
        time.sleep(1.2)                      # 别太快，避免被限流
        picked = 0
        for it in res:
            if not it["bvid"] or it["bvid"] in seen:
                continue
            if not (30 <= it["seconds"] <= 900):     # 30s~15min，太短/太长都不适合做标注任务
                continue
            seen.add(it["bvid"])
            it["category"] = cat
            it["query"] = kw
            cands.append(it)
            picked += 1
            if picked >= 6:
                break
        print(f"[{kw}] 命中 {len(res)}，采用 {picked}")
    cands.sort(key=lambda x: -(x["play"] or 0))
    OUT.write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共 {len(cands)} 条候选 -> {OUT}")


if __name__ == "__main__":
    main()
