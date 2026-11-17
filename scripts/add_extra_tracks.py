"""把「群体单元」「身体部位」两类实体补进 boxes23.jsonl。

- 群体单元（O-G）：不从图里检测，由人物检测框聚类派生——同一帧里 ≥3 人、
  横向相邻、高度相近、竖向大部分重叠，取并集框。人群片里这比任何检测器都稳。
- 身体部位（O-B）：mediapipe 手部关键点包围盒，已在 dets_hands.jsonl 里。
- 食物与供品（O-F）：本批素材实测无食物（15 个采样点 VLM 全答「没有」，
  且同模型框人正常），不生成框；脚本仍支持 --food 传入。

    .venv-detect/bin/python scripts/add_extra_tracks.py \
        --boxes .tmp/boxes23.jsonl --person .tmp/dets_person.jsonl \
        --hands .tmp/dets_hands.jsonl --out .tmp/boxes24.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qwen_boxes import build_tracks, to_result  # noqa: E402

GROUP_MIN_PEOPLE = 3


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _adjacent(a, b, gap_frac=0.6, vov=0.45, hlo=0.62, hhi=1.7):
    """两个人框像不像「并排站在一起」：高度接近、竖向重叠、横向不隔太远。"""
    ha, hb = a[3] - a[1], b[3] - b[1]
    if ha <= 1 or hb <= 1:
        return False
    if not (hlo <= ha / hb <= hhi):
        return False
    ov = min(a[3], b[3]) - max(a[1], b[1])
    if ov <= 0 or ov / min(ha, hb) < vov:
        return False
    wa, wb = a[2] - a[0], b[2] - b[0]
    gap = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    return gap <= gap_frac * max(wa, wb)


def group_boxes(person_boxes, max_w=600.0, max_h=950.0,
                max_area=520000.0, max_people=8):
    """一帧的人物框 -> 群体单元并集框列表。

    人群片里「相邻」是传递的：三四十人连锁成一整屏巨框，对标注毫无用处。
    所以合并时带约束——并集宽度 ≤600、面积 ≤52 万、人数 ≤8，超了就不合并，
    自然切成人堆里一个个能看清的小群体。
    """
    ps = [(b[1], b[2], b[3], b[4]) for b in person_boxes]
    n = len(ps)
    if n < GROUP_MIN_PEOPLE:
        return []

    parent = list(range(n))
    size = [1] * n
    boxes = list(ps)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if not _adjacent(ps[i], ps[j]):
                continue
            gap = max(0.0, max(ps[i][0], ps[j][0]) - min(ps[i][2], ps[j][2]))
            dc = abs((ps[i][0] + ps[i][2]) - (ps[j][0] + ps[j][2])) / 2.0
            edges.append((gap + dc * 0.3, i, j))
    edges.sort()

    for _, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        a, b = boxes[ri], boxes[rj]
        mb = (min(a[0], b[0]), min(a[1], b[1]),
              max(a[2], b[2]), max(a[3], b[3]))
        cnt = size[ri] + size[rj]
        if cnt > max_people:
            continue
        if (mb[2] - mb[0]) > max_w or (mb[3] - mb[1]) > max_h:
            continue
        if (mb[2] - mb[0]) * (mb[3] - mb[1]) > max_area:
            continue
        parent[rj] = ri
        boxes[ri] = mb
        size[ri] = cnt

    comp = {}
    for i in range(n):
        comp.setdefault(find(i), []).append(i)

    out = []
    for root, members in comp.items():
        if size[root] < GROUP_MIN_PEOPLE:
            continue
        x1, y1, x2, y2 = boxes[root]
        out.append(("群体单元", round(x1, 1), round(y1, 1),
                    round(x2, 1), round(y2, 1)))
    return out


def smooth_seq(seq):
    """3 点中值平滑，压住并集框随人数变化的抖动。"""
    if len(seq) < 3:
        return seq
    out = [seq[0]]
    for i in range(1, len(seq) - 1):
        f = seq[i][0]
        box = tuple(sorted(seq[i - 1 + k][1][j] for k in range(3))[1]
                    for j in range(4))
        out.append((f, box))
    out.append(seq[-1])
    return out


def tracks_to_results(samples, frames_count, fps, label_if_none, idx0,
                      thr=0.1, max_center=220.0, min_hits=2, max_cover=0.85):
    samples = [(int(f), list(b)) for f, b in samples]
    tracks = build_tracks(samples, max_age=1, thr=thr, max_center=max_center)
    res = []
    for t in tracks:
        if len(t.seq) < min_hits:
            continue
        seq = smooth_seq(t.seq) if t.label == "群体单元" else t.seq
        # 覆盖过大的框剔掉，否则整屏一个框
        big = sum(1 for _, b in seq
                  if (b[2] - b[0]) * (b[3] - b[1]) > max_cover * 1e6) / len(seq)
        if big > 0.5:
            continue
        res.append(to_result(seq, t.label or label_if_none,
                             frames_count, fps, idx0 + len(res)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", required=True)
    ap.add_argument("--person", required=True)
    ap.add_argument("--hands", required=True)
    ap.add_argument("--food", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    base = load_jsonl(a.boxes)
    person = {d["clip"]: d for d in load_jsonl(a.person)}
    hands = {d["clip"]: d for d in load_jsonl(a.hands)}
    food = {d["clip"]: d for d in load_jsonl(a.food)} if a.food else {}

    out = []
    for rec in base:
        clip = rec["clip"]
        fps = rec["fps"]
        n = int(rec["frames"])
        res = list(rec["result"])
        add = {"群体单元": 0, "身体部位": 0, "食物与供品": 0}

        p = person.get(clip)
        if p:
            gsamples = [(f, group_boxes(b)) for f, b in p["samples"]]
            g = tracks_to_results(gsamples, n, fps, "群体单元", len(res))
            res += g
            add["群体单元"] = len(g)

        h = hands.get(clip)
        if h:
            hsamples = [(f, [(x[0], x[1], x[2], x[3], x[4]) for x in b])
                        for f, b in h["samples"]]
            # 手左右之分在字段体系里没有对应项，落「身体部位」
            hsamples = [(f, [("身体部位", *x[1:]) for x in b])
                        for f, b in hsamples]
            hr = tracks_to_results(hsamples, n, fps, "身体部位", len(res),
                                   thr=0.06, max_center=120.0, min_hits=2)
            res += hr
            add["身体部位"] = len(hr)

        fd = food.get(clip)
        if fd:
            fsamples = [(f, list(b)) for f, b in fd["samples"] if b]
            fr = tracks_to_results(fsamples, n, fps, "食物与供品", len(res),
                                   thr=0.08, max_center=160.0, min_hits=1)
            res += fr
            add["食物与供品"] = len(fr)

        rec2 = dict(rec)
        rec2["result"] = res
        out.append(rec2)
        print(f"{clip[:20]}: +群体 {add['群体单元']} +手 {add['身体部位']} "
              f"+食物 {add['食物与供品']}  总框 {len(res)}", flush=True)

    with open(a.out, "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
