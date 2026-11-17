#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「预标注（prediction）」转成「标注（annotation）」。

为什么要转：Label Studio 里 prediction 是**只读**的。框能显示、能看见标签，
但点不中、改不了标签——这就是「框的标签改不了」的原因，不是 label_config 写错。
转成 annotation 之后，框就变成可编辑区域，点中直接换标签、拖边改尺寸。

走的是 Data Manager 同一个批量动作（界面上叫 Create Annotations From Predictions），
只是用 API 触发，省得手点。

用法：
  python3 scripts/pred2annot.py --project 6            # 真转
  python3 scripts/pred2annot.py --project 6 --dry-run
"""
import argparse
import json
import os
import urllib.error
import urllib.request

API = os.getenv("LS_URL", "http://ich.8.160.123.92.nip.io")
TOKEN = os.getenv("LS_TOKEN", "81ee86fd05b977f9deacae689afccc72e866c3e1")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    code, tasks = call("GET", f"/api/tasks?project={a.project}&page_size=100&fields=all")
    if code != 200:
        raise SystemExit(f"取任务失败 {code}: {tasks}")
    rows = tasks if isinstance(tasks, list) else tasks.get("tasks", tasks.get("results", []))
    print(f"项目 {a.project} 共 {len(rows)} 条任务")

    for t in rows:
        tid = t["id"]
        n_pred = len(t.get("predictions") or [])
        n_ann = len(t.get("annotations") or [])
        print(f"  task {tid}: prediction {n_pred}，annotation {n_ann}")

    if a.dry_run:
        print("[dry] 未执行转换")
        return

    ids = [t["id"] for t in rows]
    code, body = call("POST", f"/api/dm/actions?project={a.project}&id=predictions_to_annotations",
                      {"selectedItems": {"all": False, "included": ids}, "project": a.project})
    print(f"\n转换返回 {code}: {str(body)[:300]}")

    code, tasks = call("GET", f"/api/tasks?project={a.project}&page_size=100&fields=all")
    rows = tasks if isinstance(tasks, list) else tasks.get("tasks", tasks.get("results", []))
    for t in rows:
        print(f"  task {t['id']}: prediction {len(t.get('predictions') or [])}，"
              f"annotation {len(t.get('annotations') or [])}")


if __name__ == "__main__":
    main()
