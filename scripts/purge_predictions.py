#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 model_version 清理 Label Studio 里的预标注。

同一批任务被灌了多版预标注时，标注页会同时列出几组 Prediction，标注员容易点错。
本脚本按版本号精确删除，不碰其它版本、也不碰人工标注（annotations）。

用法：
    export LS_URL=http://127.0.0.1:8080 LS_TOKEN=xxxx
    python scripts/purge_predictions.py --dry-run          # 先看会删什么
    python scripts/purge_predictions.py                    # 删默认的旧版本
    python scripts/purge_predictions.py --model-version xxx
"""

import argparse
import os
import sys

import requests

BASE = os.getenv("LS_URL", "http://127.0.0.1:8080")
TOKEN = os.getenv("LS_TOKEN")
PROJECT = int(os.getenv("LS_PROJECT", "2"))
OLD_DEFAULT = "yolov8n-cpu-bytetrack-v1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-version", default=OLD_DEFAULT)
    ap.add_argument("--project", type=int, default=PROJECT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not TOKEN:
        sys.exit("请设置 LS_TOKEN")
    H = {"Authorization": f"Token {TOKEN}"}

    r = requests.get(f"{BASE}/api/predictions", headers=H,
                     params={"project": args.project, "page_size": 500}, timeout=60)
    r.raise_for_status()
    data = r.json()
    items = data.get("results", []) if isinstance(data, dict) else data

    targets = [p for p in items if p.get("model_version") == args.model_version]
    print(f"项目 {args.project} 共 {len(items)} 条预测，"
          f"其中 {len(targets)} 条属于 {args.model_version}")

    if not targets:
        print("没有需要删除的")
        return

    if args.dry_run:
        for p in targets:
            print(f"  [将删除] id={p['id']} task={p['task']} 轨迹={len(p.get('result', []))}")
        print("\n--dry-run：未实际删除")
        return

    gone = 0
    for p in targets:
        resp = requests.delete(f"{BASE}/api/predictions/{p['id']}", headers=H, timeout=30)
        if resp.status_code in (200, 204):
            gone += 1
        else:
            print(f"  [失败 {resp.status_code}] id={p['id']}: {resp.text[:120]}")
    print(f"\n已删除 {gone} 条")


if __name__ == "__main__":
    main()
