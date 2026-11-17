#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比两版预标注的整体质量：v1（全量词表）vs v3（按门类定制词表）。

不做逐条匹配——两次检测的 track id 是独立生成的，硬配会得到一堆假匹配。
改用**聚合指标**，这些是可比的：

  1. 轨迹总数 / 各标签轨迹数
  2. **串门框**：出现在某片段里、但工艺上不该出现的标签（纯损耗，标注员只能删）
  3. 每个标签的框面积与置信度
  4. 零检出片段数

用法：
  python3 scripts/compare_versions.py --a preds_world_all.jsonl --b preds_world_v3.jsonl
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        name = Path(r["video"]).name
        rows[name] = r["prediction"]
    return rows


def category_of(name):
    return name[:2]


def plausible_by_category():
    """从 prelabel_world 的门类词表反推「该门类说得通的标签集合」。

    这里刻意 import 真实配置，而不是另抄一份——另抄一份迟早会跟主配置不同步，
    然后对比结果就悄悄失效了。
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from prelabel_world import CATEGORY_PROMPTS, WORLD_PROMPTS
    return {k: {WORLD_PROMPTS[p] for p in ps} for k, ps in CATEGORY_PROMPTS.items()}


def stats(preds):
    per_label = Counter()
    label_area = defaultdict(list)
    zero = []
    for name, p in preds.items():
        if not p["result"]:
            zero.append(name)
        for r in p["result"]:
            lb = r["value"]["labels"][0]
            per_label[lb] += 1
            for s in r["value"]["sequence"]:
                if not s.get("enabled", True):
                    continue        # 哨兵帧不在画面里，不参与框面积统计
                label_area[lb].append((s["width"] / 100.0) * (s["height"] / 100.0))
    return per_label, label_area, zero


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="preds_world_all.jsonl", help="旧版（全量词表）")
    ap.add_argument("--b", default="preds_world_v3.jsonl", help="新版（门类定制）")
    args = ap.parse_args()

    A, B = load(ROOT / args.a), load(ROOT / args.b)
    plausible = plausible_by_category()

    if set(A) != set(B):
        print(f"[注意] 两版覆盖的片段不同：A={len(A)} B={len(B)}")
        print(f"  只在 A: {sorted(set(A) - set(B))[:5]}")
        print(f"  只在 B: {sorted(set(B) - set(A))[:5]}")

    common = sorted(set(A) & set(B))

    def stray_map(preds):
        """{片段: {不该出现的标签: 轨迹数}}"""
        out = {}
        for name in common:
            pl = plausible.get(category_of(name))
            if pl is None:
                continue
            bad = {lb: n for lb, n in
                   Counter(r["value"]["labels"][0]
                           for r in preds[name]["result"]).items()
                   if lb not in pl}
            if bad:
                out[name] = bad
        return out

    sa, sb = stray_map(A), stray_map(B)

    def stray_total(m):
        return sum(sum(v.values()) for v in m.values())

    print("\n" + "=" * 62)
    print(f"轨迹总数    A={sum(len(A[n]['result']) for n in common)}"
          f"    B={sum(len(B[n]['result']) for n in common)}")
    print(f"零检出片段  A={sum(1 for n in common if not A[n]['result'])}"
          f"    B={sum(1 for n in common if not B[n]['result'])}")
    print(f"**串门框**  A={stray_total(sa)} 条    B={stray_total(sb)} 条"
          f"    （涉及 A {len(sa)} 段 / B {len(sb)} 段）")

    if sa:
        print("\nA 版的串门框明细（这些是标注员必须手动删的）：")
        for name, bad in sorted(sa.items()):
            d = "、".join(f"{k}×{v}" for k, v in sorted(bad.items()))
            print(f"  {name}: {d}")

    pa, aa, _ = stats({n: A[n] for n in common})
    pb, ab, _ = stats({n: B[n] for n in common})

    print("\n各标签轨迹数与框面积（只列两版都有的标签）")
    print(f"  {'标签':<14}{'A条数':>7}{'B条数':>7}{'A框面积':>10}{'B框面积':>10}{'变化':>9}")
    for lb in sorted(set(pa) & set(pb)):
        ma = sum(aa[lb]) / len(aa[lb]) if aa[lb] else 0
        mb = sum(ab[lb]) / len(ab[lb]) if ab[lb] else 0
        d = (mb - ma) / ma * 100 if ma > 1e-9 else 0
        print(f"  {lb:<14}{pa[lb]:>7}{pb[lb]:>7}{ma*100:>9.1f}%{mb*100:>9.1f}%{d:>+8.0f}%")

    only_a = sorted(set(pa) - set(pb))
    only_b = sorted(set(pb) - set(pa))
    if only_a:
        print(f"\n只在 A 出现（B 没检出）: "
              + "、".join(f"{k}×{pa[k]}" for k in only_a))
    if only_b:
        print(f"只在 B 出现（A 没检出）: "
              + "、".join(f"{k}×{pb[k]}" for k in only_b))


if __name__ == "__main__":
    main()
