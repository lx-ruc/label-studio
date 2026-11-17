#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键在 Label Studio 里建好「非遗视频检测与跟踪」项目并导入片段任务。

前置：
  1) 另开一个终端启动 Label Studio（必须设置本地文件根目录，否则读不到视频）：
       export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
       export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=<项目根>/data
       label-studio start --port 8080
  2) 浏览器打开 http://localhost:8080 注册账号，
     在 Account & Settings → Access Token 复制 token，设为环境变量 LS_TOKEN

用法：
  export LS_TOKEN=xxxxxxxx
  python setup_project.py                 # 建项目 + 导入 tasks.json
  python setup_project.py --predictions preds.jsonl   # 一并灌入预标注
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LS_URL = os.getenv("LS_URL", "http://localhost:8080")
TOKEN = os.getenv("LS_TOKEN")
PROJECT_TITLE = "非遗视频 · 目标检测与跨帧跟踪"


def headers():
    if not TOKEN:
        sys.exit("请先设置环境变量 LS_TOKEN（Label Studio → Account & Settings → Access Token）")
    return {"Authorization": f"Token {TOKEN}"}


def get_or_create_project():
    r = requests.get(f"{LS_URL}/api/projects", headers=headers(), timeout=30)
    r.raise_for_status()
    for p in r.json().get("results", r.json() if isinstance(r.json(), list) else []):
        if p.get("title") == PROJECT_TITLE:
            print(f"复用已有项目 id={p['id']}")
            return p["id"]

    payload = {
        "title": PROJECT_TITLE,
        "description": "非物质文化遗产工艺视频的目标检测与跨帧跟踪标注（VideoRectangle）",
        "label_config": (ROOT / "labelstudio" / "label_config.xml").read_text(encoding="utf-8"),
    }
    r = requests.post(f"{LS_URL}/api/projects", headers=headers(), json=payload, timeout=30)
    r.raise_for_status()
    pid = r.json()["id"]
    print(f"已创建项目 id={pid}")
    return pid


def ensure_local_storage(project_id):
    """登记本地文件存储。

    Label Studio 的 /data/local-files/ 视图会校验：请求文件的目录必须在某个
    LocalFilesImportStorage.path 之下，且该 storage 所属项目对当前用户有权限。
    不登记的话，即使 LOCAL_FILES_SERVING_ENABLED=true 也一律 404。
    """
    path = str(ROOT / "data" / "clips")
    r = requests.get(f"{LS_URL}/api/storages/localfiles?project={project_id}",
                     headers=headers(), timeout=30)
    for s in r.json() if isinstance(r.json(), list) else r.json().get("results", []):
        if s.get("path") == path:
            print(f"本地存储已存在 id={s['id']}")
            return s["id"]
    r = requests.post(f"{LS_URL}/api/storages/localfiles", headers=headers(), timeout=30,
                      json={"project": project_id, "path": path,
                            "title": "非遗标注片段", "regex_filter": ".*",
                            "use_blob_urls": False})
    r.raise_for_status()
    print(f"已登记本地存储 id={r.json()['id']} -> {path}")
    return r.json()["id"]


def existing_videos(project_id):
    """列出项目里已有任务的 video 字段，用于跳过重复导入。

    Label Studio 的 /import 不做去重 —— 重跑一次就翻倍一次。
    """
    got, page = set(), 1
    while True:
        r = requests.get(f"{LS_URL}/api/tasks", headers=headers(), timeout=120,
                         params={"project": project_id, "page_size": 100, "page": page})
        r.raise_for_status()
        j = r.json()
        batch = j.get("tasks") if isinstance(j, dict) else j
        if not batch:
            break
        for t in batch:
            got.add(t["data"].get("video"))
        page += 1
        if len(got) >= j.get("count", len(batch)) if isinstance(j, dict) else True:
            break
    return got


def task_video_map(project_id):
    """项目内 {片段文件名: task_id}。用于把预标注挂到已有任务上。"""
    mapping, page = {}, 1
    while True:
        r = requests.get(f"{LS_URL}/api/tasks", headers=headers(), timeout=120,
                         params={"project": project_id, "page_size": 100, "page": page})
        r.raise_for_status()
        j = r.json()
        batch = j.get("tasks") if isinstance(j, dict) else j
        if not batch:
            break
        for t in batch:
            v = t["data"].get("video", "")
            mapping[v.split("?d=clips/")[-1]] = t["id"]
        total = j.get("count") if isinstance(j, dict) else None
        if total is None or len(mapping) >= total:
            break
        page += 1
    return mapping


def import_predictions(project_id, path):
    """把预标注写入已存在的任务。

    走 POST /api/predictions/ —— 这是给「任务已经导入完毕」的场景用的，
    和 /import 里带 predictions 字段是两条路。
    同一个 model_version 重跑会先删旧的，保证幂等（不会叠加成两条预测）。
    """
    preds = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            it = json.loads(line)
            preds[Path(it["video"]).name] = it["prediction"]
    print(f"读到 {len(preds)} 条预标注")

    mapping = task_video_map(project_id)
    print(f"项目内任务 {len(mapping)} 条")

    created = deleted = 0
    for name, pred in preds.items():
        tid = mapping.get(name)
        if not tid:
            print(f"  [无对应任务] {name}")
            continue
        mv = pred.get("model_version") or "unknown"

        # 幂等：清掉同版本旧预测
        r = requests.get(f"{LS_URL}/api/predictions", headers=headers(), timeout=60,
                         params={"task": tid, "page_size": 200})
        if r.ok:
            j = r.json()
            items = j.get("results", []) if isinstance(j, dict) else j
            for p in items:
                if p.get("model_version") == mv:
                    requests.delete(f"{LS_URL}/api/predictions/{p['id']}",
                                    headers=headers(), timeout=30)
                    deleted += 1

        payload = {"task": tid, "result": pred["result"],
                   "model_version": mv, "score": pred.get("score", 0.0)}
        r = requests.post(f"{LS_URL}/api/predictions/",
                          headers=headers(), json=payload, timeout=120)
        if r.status_code in (200, 201):
            created += 1
            print(f"  [ok] task {tid} {name}: "
                  f"{len(pred['result'])} 条轨迹 / score {pred.get('score')}")
        else:
            print(f"  [失败 {r.status_code}] {name}: {r.text[:200]}")
    print(f"\n预标注写入 {created} 条（清理旧版本 {deleted} 条）")
    print(f"查看：{LS_URL}/projects/{project_id}/data")


def import_tasks(project_id, with_predictions=None):
    tasks = json.loads((ROOT / "labelstudio" / "tasks.json").read_text(encoding="utf-8"))

    already = existing_videos(project_id)
    fresh = [t for t in tasks if t["data"]["video"] not in already]
    if not fresh:
        print(f"任务已存在 {len(already)} 条，无需重复导入")
        return
    skipped = len(tasks) - len(fresh)
    if skipped:
        print(f"跳过已存在的 {skipped} 条，新增 {len(fresh)} 条")

    tasks = fresh

    if with_predictions:
        preds = {}
        for line in Path(with_predictions).read_text(encoding="utf-8").splitlines():
            if line.strip():
                it = json.loads(line)
                preds[Path(it["video"]).name] = it["prediction"]
        hit = 0
        for t in tasks:
            name = t["data"]["video"].split("?d=clips/")[-1]
            if name in preds:
                t["predictions"] = [preds[name]]
                hit += 1
        print(f"预标注匹配 {hit}/{len(tasks)} 条")

    r = requests.post(f"{LS_URL}/api/projects/{project_id}/import",
                      headers=headers(), json=tasks, timeout=300)
    r.raise_for_status()
    print(f"导入完成：{r.json().get('task_count', len(tasks))} 条任务")
    print(f"打开标注：{LS_URL}/projects/{project_id}/data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", help="prelabel_*.py 产出的 preds.jsonl")
    ap.add_argument("--predictions-only", action="store_true",
                    help="任务已导入时，只灌预标注（走 /api/predictions/）")
    args = ap.parse_args()
    pid = get_or_create_project()
    ensure_local_storage(pid)
    if args.predictions_only:
        if not args.predictions:
            sys.exit("--predictions-only 需要同时给 --predictions")
        import_predictions(pid, args.predictions)
    else:
        import_tasks(pid, args.predictions)


if __name__ == "__main__":
    main()
