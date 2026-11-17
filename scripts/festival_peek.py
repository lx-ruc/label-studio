"""抽查节日志预标注结果。

    .venv/bin/python scripts/festival_peek.py .tmp/qwen_festival_run1.jsonl
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else ".tmp/qwen_festival_run1.jsonl"
for line in open(path, encoding="utf-8"):
    r = json.loads(line)
    print("=" * 20, r["clip"][:34])
    a = r["answer"]
    for fid in ("C-1", "C-2", "C-3", "C-4", "C-5", "N-1", "N-2", "N-3", "N-5"):
        it = a.get(fid, {})
        subs = {k: v for k, v in it.items() if k != "out"}
        print(f"{fid}: {subs}")
        print(f"   out: {it.get('out', '')[:110]}")
    print("N-4:", a.get("N-4", {}).get("out", "")[:180])
