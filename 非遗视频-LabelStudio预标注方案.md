# 非物质文化遗产视频 · Label Studio 预标注方案
### 任务类型：目标检测 + 跨帧跟踪（Video Rectangle）
### 算力假设：可调用云端多模态大模型 API（无本地 GPU）

---

## 0. 一句话结论

**不要一上来就训练模型。** 用「云端多模态大模型给关键帧打种子框 → 时序传播补全所有帧 → 导入 Label Studio 作为 `predictions` → 人工只做修正」这条路，可以在**不买 GPU、不写代码训练**的前提下，把单条视频标注耗时压到纯人工的 1/3～1/5。等攒够 300～500 条修正后的数据，再回流训练一个轻量检测器接管预标注，形成闭环。

---

## 1. 要标什么：先把标注对象定义清楚

非遗视频（传统技艺 / 传统美术 / 传统戏剧 / 民俗类）的检测目标，建议先收敛到 6 个实体大类：

| 实体大类 | 说明 | 典型例子 |
|---|---|---|
| 人物 | 传承人、学徒、围观者 | 绣娘、木匠、傩戏演员 |
| 手部 | **非遗工艺的核心**，建议单独建类 | 持针的手、拉坯的手 |
| 工具 | 直接参与工艺的器具 | 刻刀、织梭、绣针、錾子、毛笔 |
| 材料/半成品 | 正在被加工的对象 | 泥坯、丝线、木料、漆胎 |
| 成品 | 已完成的作品 | 玉雕、织锦、剪纸 |
| 设备/场景 | 大型固定装置 | 织机、窑炉、染缸 |

> **为什么单独标「手」**：非遗技艺的知识密度集中在手部动作上。手部框 + 工具框的**空间关系随时间的变化**，就是工序识别最直接的监督信号。这是纯分类标注拿不到的信息。

### 标签体系（用 Label Studio 的层级标签）

Label Studio 原生支持 `大类/子类` 的层级显示，直接写 `<Label value="工具/刻刀"/>` 即可在前端折叠成树：

```
人物/传承人        人物/学徒
手部/左手          手部/右手
工具/刻刀          工具/织梭       工具/绣针      工具/錾子
材料/泥坯          材料/丝线       材料/木料
成品/织锦          成品/玉雕       成品/剪纸
设备/织机          设备/窑炉
```

**执行建议**：第一版冻结 **20～40 个标签**，跑通流程再扩。标签一上来就铺开到 200 个，标注员会直接放弃。

---

## 2. 数据预处理：这一步决定后面 80% 的体验

### 2.1 转码规范化（必做）

```bash
ffmpeg -i raw.mov \
  -c:v libx264 -crf 23 -preset fast \
  -g 25 -keyint_min 25 -sc_threshold 0 \
  -vf "scale=1280:-2,fps=25" \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  out/clip_001.mp4
```

三个关键参数，缺一个都会踩坑：

- **`fps=25` 统一帧率** —— 后面 Label Studio 配置的 `frameRate` 必须和它一致，否则时间→帧号换算整体错位，预标注框会漂移。
- **`-g 25` 短 GOP** —— 关键帧间隔越小，Label Studio 时间轴拖动越跟手。默认 250 帧一个关键帧的素材，标注员拖动时会卡成幻灯片。
- **`scale=1280:-2`** —— 4K 素材对检测精度没有实质帮助，但会显著拖慢前端和推理。1280 宽足够。

### 2.2 镜头切分：单任务控制在 10～60 秒

```bash
scenedetect -i out/clip_001.mp4 detect-content split-video -o scenes/
```

**整段 30 分钟的视频绝对不要做成一个任务**，原因：
- 单个 prediction JSON 会膨胀到几十 MB，导入即超时；
- 跟踪模型长时间漂移，人工根本找不到漂在哪一秒；
- 标注员疲劳度非线性上升，20 分钟后质量断崖下跌。

### 2.3 存储与访问

**单机 / 小团队：**
```bash
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/data/ich
label-studio start
```
任务里填 `"/data/local-files/?d=clips/001.mp4"`。

**多人协作 / 视频量大：** 配置 S3/OSS 云存储 + 预签名 URL。否则所有视频流量都要过 Label Studio 服务器，带宽先崩。

---

## 3. Label Studio 标注配置（直接可用）

```xml
<View>
  <Header value="非遗工艺视频 · 目标检测与跨帧跟踪  |  先检查预标注框，按 ← → 逐帧微调"/>
  <Video name="video" value="$video" frameRate="25" sync="groupA"/>
  <Labels name="tag" toName="video" allowEmpty="true">
    <Label value="人物/传承人" background="#E1BEE7"/>
    <Label value="人物/学徒"   background="#CE93D8"/>
    <Label value="手部/左手"   background="#FFCDD2"/>
    <Label value="手部/右手"   background="#EF9A9A"/>
    <Label value="工具/刻刀"   background="#C8E6C9"/>
    <Label value="工具/织梭"   background="#A5D6A7"/>
    <Label value="工具/绣针"   background="#81C784"/>
    <Label value="材料/泥坯"   background="#FFF9C4"/>
    <Label value="材料/丝线"   background="#FFF59D"/>
    <Label value="成品/玉器"   background="#B3E5FC"/>
    <Label value="设备/织机"   background="#D7CCC8"/>
  </Labels>
  <VideoRectangle name="box" toName="video" smart="true"/>
  <TextArea name="note" toName="video"
            placeholder="遮挡 / 截断 / 存疑处备注，便于复核" editable="true"/>
</View>
```

要点：
- `frameRate="25"` 必须与转码后的实际帧率一致；
- `VideoRectangle` 自带**关键帧插值**能力，这是「稀疏预标注」能成立的前提；
- 加一个 `TextArea` 收集存疑反馈，数据质量复盘时非常有用。

---

## 4. 预标注总流程

```
原始视频
  │
  ├─(1) 转码规范化 + 镜头切分          → 10~60s 片段
  │
  ├─(2) 抽帧 + 感知哈希去重            → 变化关键帧（数量降 60~80%）
  │
  ├─(3) 冷启动打框                     → 云端多模态大模型 API
  │        │                            输出：类别 + 边界框 + 置信度
  │        ▼
  ├─(4) 时序传播                       → 关键帧插值 / SAM2 / 目标跟踪
  │        │                            输出：全帧 box 序列（tracklet）
  │        ▼
  ├─(5) 组装 LS predictions JSON       → POST /api/predictions/
  │        │
  │        ▼
  ├─(6) 人工修正（Label Studio）       → 修框 / 改类 / 拆 ID
  │        │
  │        ▼
  └─(7) 回流训练 → v2 模型 → 回到 (3)  ──闭环
```

---

## 5. 三档落地路径（按规模与预算选）

### 档位 A：纯 API、零 GPU —— 先跑通，适合 < 200 条

1. 每片段抽 1～2 fps，用**感知哈希/直方图差异去重**，只保留画面发生变化的帧；
2. 变化帧送云端多模态大模型做开放词汇目标定位，返回类别 + 边界框；
3. **只在关键帧打点**（目标出现、消失、显著位移的帧），中间交给 Label Studio 的 `VideoRectangle` 插值；
4. 人工只微调关键帧，插值自动带动中间帧。

> **为什么这一档对非遗视频特别有效**：非遗记录片镜头高度固定、运动缓慢、主体居中，线性插值的误差远小于通用场景。很多情况下 A 档就能达到可用质量。

**适用边界**：目标快速运动、镜头推拉摇移、频繁遮挡的素材，A 档插值会明显偏，直接上 B 档。

### 档位 B：API + 按量租 GPU —— 推荐，性价比最高

1. 同 A 档，云端大模型给**种子框**（每 2～5 秒一个）；
2. 用 **SAM 2 的 video predictor** 把种子框在整段传播，得到逐帧 mask/box；
3. 输出 dense 序列，人工只需修漂移和 ID 切换。

成本参考：按量付费的 A10 / 4090 实例，跑 SAM2 一小时是**个位数到几十元**。1000 条 5 分钟素材约几小时机时 —— 相比省下的人力，这笔钱可以忽略。

> 即使你现在「只能调 API」，也强烈建议租一张按量 GPU 跑 SAM2。这是整个方案里投入产出比最高的一笔钱。

### 档位 C：规模化自训练 —— 长期项目 / > 1000 条

1. 用 A/B 档产出的**人工修正后**数据训练 YOLOv8 / YOLO-E 检测器 + ByteTrack 跟踪；
2. 封装成 Label Studio ML Backend，标注员打开任务时实时返回预测；
3. 开启主动学习：优先派发模型低置信 / 多模型分歧大的样本。

---

## 6. 预标注结果的数据格式（最容易出错的地方）

视频包围盒的 prediction schema 比图片严格得多，错一个字段前端就不渲染：

```json
{
  "task": 12345,
  "model_version": "qwen-vl-keyframe-v1",
  "score": 0.86,
  "result": [
    {
      "id": "track_001",
      "from_name": "box",
      "to_name": "video",
      "type": "videorectangle",
      "value": {
        "framesCount": 750,
        "duration": 30.0,
        "sequence": [
          {"frame": 1,   "x": 12.4, "y": 30.1, "width": 18.2, "height": 24.5, "enabled": true,  "rotation": 0},
          {"frame": 60,  "x": 15.0, "y": 31.0, "width": 18.0, "height": 24.2, "enabled": true,  "rotation": 0},
          {"frame": 120, "x": 15.2, "y": 31.1, "width": 17.9, "height": 24.0, "enabled": true,  "rotation": 0},
          {"frame": 121, "x": 15.2, "y": 31.1, "width": 17.9, "height": 24.0, "enabled": false, "rotation": 0}
        ],
        "labels": ["工具/刻刀"]
      }
    }
  ]
}
```

**必须遵守的规则：**

| 项 | 规则 |
|---|---|
| 坐标 | 相对画面的**百分比 0–100**，不是像素 |
| 帧号 | 从 **1** 开始（不是 0） |
| `framesCount` | 该片段总帧数，错填会导致时间轴错位 |
| 遮挡/消失 | 用 `"enabled": false` 占位，**不要从 sequence 里删** |
| 一条轨迹 | 一个 result 对象；track_id 放 `id` 字段便于回溯 |
| 稀疏关键帧 | 可以只给关键帧靠前端插值，但 **dense 序列更稳，先用 20 条验证前端行为再定** |

---

## 7. 导入预测的三种方式

| 方式 | 接口 | 适用场景 |
|---|---|---|
| 任务导入时内联 | `POST /api/projects/{id}/import`，task 对象里带 `predictions` 字段 | 一次性批量导入，最简单 |
| 单独写预测 | `POST /api/predictions/` | 任务已存在，增量补预测 / 换模型版本重跑 |
| ML Backend 实时预测 | 部署 model server，LS 打开任务时回调 | 规模化、多模型版本对比、主动学习 |

推荐节奏：**前期用方式 1/2 批量灌，跑通后迁移到方式 3。**

关于 `model_version`：一定要填。Label Studio 会按模型版本聚合统计，你能直接对比「v1 大模型冷启动」和「v3 自训练模型」谁的修正率更低 —— 这是决定要不要投入训练的唯一依据。

---

## 8. 人工修正阶段：规范比工具更重要

### 8.1 标注规范（写进标注手册，培训必讲）

- **框的松紧**：贴着目标可见轮廓外扩 2～3 px；不要留大片背景。
- **遮挡**：目标被遮挡 < 50% 仍标完整框；> 50% 标 `enabled: false`（保留位置，不画框）。
- **截断**：出画目标框到画面边缘，不猜画外部分。
- **小目标**：面积 < 画面 2% 的目标不标（噪声大于价值）。
- **ID 一致性**：同一物理对象全程一个 tracklet；目标离开画面再回来 → **新建 ID**。
- **手与工具重叠**：两者都标，允许框重叠，不合并。
- **存疑**：填 `note` 字段，不要自己猜。

### 8.2 效率技巧

- 预标注框只需在**关键帧**调整，Label Studio 会自动插值带动中间帧；
- 熟练标注员的典型节奏：看一遍片段 → 跳到漂移最严重的 3～5 个关键帧 → 修 → 提交；
- 用 `model_version` 过滤 + 预测分数排序，先处理低置信任务。

---

## 9. 质量度量：怎么判断预标注到底有没有用

| 指标 | 定义 | 目标值 |
|---|---|---|
| 框命中率 | 人工未移动即采纳的框 / 总框数 | ≥ 60%（A 档） / ≥ 80%（B 档） |
| 类别准确率 | 人工未改类别的框 / 总框数 | ≥ 85% |
| 轨迹完整度 | 需要人工补帧的比例 | ≤ 20% |
| 效率提升 | 修正耗时 / 从零标注耗时 | ≤ 1/3 |
| 标注一致性 | 5% 样本双人重复标注的框 IoU | ≥ 0.75 |

**落地做法**：前 20 条同时做「从零标注」和「修预标注」，各计时。这个对比数据是你后续所有决策的基准线，一定要留。

---

## 10. 成本估算（量级参考，务必实测校准）

假设：1000 条素材，平均 5 分钟/条。

| 项目 | 档位 A（纯 API） | 档位 B（API + SAM2） |
|---|---|---|
| 抽帧去重后送模型的帧数 | ≈ 8 万帧 | ≈ 3 万帧（种子框更稀疏） |
| 多模态 API 费用 | ¥3000 ～ 8000 | ¥1000 ～ 3000 |
| GPU 机时（SAM2 传播） | 0 | ¥100 ～ 500 |
| 人工修正（按 1/3 耗时） | ≈ 330 小时 | ≈ 200 小时 |
| **小结** | 启动成本最低，人力偏重 | **总成本低，质量最好** |

> 省钱关键：**感知哈希去重**这一步能砍掉 60～80% 的 API 调用，务必做。非遗视频大量时间画面近乎静止。

---

## 11. 排期建议（6 周）

| 周 | 事项 | 交付物 |
|---|---|---|
| W1 | 定标签体系、写标注规范、选 20 条样板视频 | 标签集 v0.1、标注手册 |
| W2 | 转码切分流水线 + Label Studio 配置调优 | 可跑的预处理脚本、LS 项目 |
| W3 | 档位 A 冷启动预标注，跑通 20 条 | 预标注脚本 v1、predictions 导入成功 |
| W4 | 人工修正 + 质量评估（对比纯人工耗时） | 质量报告、是否上 B 档的决策依据 |
| W5 | 上档位 B（SAM2 传播）或启动回流训练 | 预标注质量提升到 80%+ |
| W6 | 规模化批处理 + 主动学习派单 | 正式产线、数据交付 |

---

## 12. 风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| 云端模型出框坐标不准/格式不稳 | 框飘、类别乱 | 每次调用要求严格 JSON 输出 + 落库前做校验（越界、宽高为负、NaN 一律丢弃）；低置信帧不送传播 |
| 帧率不一致导致时间轴错位 | 框整体提前/滞后 | 转码阶段强制 `fps=25`，LS 配置 `frameRate` 写死，导入前校验中间帧数 |
| 长视频 prediction JSON 过大 | 导入超时 | 强制镜头切分到 10～60s；dense 序列按 5fps 降采样后再写 |
| 跟踪 ID 频繁切换 | 同一目标多条轨迹 | 传播后做 ID 后处理：IoU 匹配 + 短轨迹（<0.5s）合并 |
| 标签体系失控 | 标注员随意新增类 | 版本化管理，v0.1 冻结，变更走评审 |
| 手部目标太小/模糊 | 手部框质量差 | 手部单独设较低置信阈值 + 强制人工复核；必要时提高素材分辨率到 1920 |

---

## 附录 A：预标注主脚本骨架（抽帧去重 → 调用 API → 生成 sequence）

```python
# prelabel.py  ——  A 档：抽帧去重 → 云端多模态模型出框 → 组装 LS predictions
import os, json, subprocess, hashlib
from pathlib import Path
import cv2, requests

FPS_TARGET   = 25      # 必须与转码帧率 & LS 配置一致
SAMPLE_FPS   = 1       # 送模型的采样帧率
HASH_THRESH  = 6       # 感知哈希汉明距离阈值，小于它视为重复帧
API_URL      = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
API_KEY      = os.environ["DASHSCOPE_API_KEY"]
MODEL        = "qwen-vl-max-latest"

LABELS = ["人物/传承人","手部/左手","手部/右手","工具/刻刀","工具/织梭",
          "材料/泥坯","成品/玉器","设备/织机"]

PROMPT = f"""你是非遗工艺视频的标注助手。请定位画面中的以下目标：{LABELS}
只输出 JSON，不要解释，不要 markdown 代码块：
{{"objects":[{{"label":"工具/刻刀","x":12.4,"y":30.1,"w":18.2,"h":24.5,"score":0.9}}]}}
坐标为相对画面宽高的百分比(0-100)，x/y 是框左上角。看不到的目标不要输出。"""

def dhash(img, size=8):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size+1, size))
    return sum(1 << i for i in range(size*size)
               if g[i//size, i%size] > g[i//size, i%size+1])

def hamming(a, b):
    return bin(a ^ b).count("1")

def extract_keyframes(video, out_dir):
    """抽帧 + 感知哈希去重，返回 [(frame_no, image_path)]，frame_no 从 1 开始"""
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or FPS_TARGET
    step = max(1, int(round(src_fps / SAMPLE_FPS)))
    out, prev_h, idx, saved = [], None, 0, 0
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    while True:
        ok, frame = cap.read()
        if not ok: break
        idx += 1
        if idx % step: continue
        h = dhash(frame)
        if prev_h is not None and hamming(h, prev_h) <= HASH_THRESH:
            continue                       # 与上一帧几乎一样，跳过不送模型
        prev_h = h
        p = f"{out_dir}/f{idx:06d}.jpg"
        cv2.imwrite(p, frame)
        out.append((idx, p)); saved += 1
    cap.release()
    return out

def call_model(img_path):
    import base64
    b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
    r = requests.post(API_URL, headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "messages":[{"role":"user","content":[
            {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text": PROMPT}]}], "temperature": 0},
        timeout=60)
    txt = r.json()["choices"][0]["message"]["content"]
    txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(txt).get("objects", [])

def valid(o):
    """过滤越界 / 非法框 —— 大模型输出必须校验，否则前端渲染会炸"""
    x, y, w, h = o["x"], o["y"], o["w"], o["h"]
    return (o.get("label") in LABELS and -5 <= x <= 100 and -5 <= y <= 100
            and 0.5 < w <= 100 and 0.5 < h <= 100
            and x + w <= 105 and y + h <= 105 and o.get("score", 0) >= 0.5)

def build_prediction(video, frames_count, duration, seq_by_track, model_version):
    """seq_by_track: {track_id: {"label": str, "frames": [(frame_no, x, y, w, h)]}}"""
    result, scores = [], []
    for tid, t in seq_by_track.items():
        result.append({
            "id": tid,
            "from_name": "box", "to_name": "video", "type": "videorectangle",
            "value": {
                "framesCount": frames_count,
                "duration": duration,
                "sequence": [{"frame": f, "x": round(x,2), "y": round(y,2),
                              "width": round(w,2), "height": round(h,2),
                              "enabled": True, "rotation": 0}
                             for f, x, y, w, h in sorted(t["frames"])],
                "labels": [t["label"]],
            }
        })
        scores.append(t.get("score", 0.8))
    return {"model_version": model_version,
            "score": round(sum(scores)/len(scores), 3) if scores else 0,
            "result": result}

# —— 简单最近邻关联：把逐帧的框串成 tracklet（B 档应替换为 SAM2 传播）——
def associate(detections_per_frame, iou_thresh=0.3):
    tracks, next_id = {}, 1
    for frame_no, objs in sorted(detections_per_frame.items()):
        for o in objs:
            best, best_iou = None, iou_thresh
            for tid, t in tracks.items():
                if t["label"] != o["label"] or frame_no - t["last_frame"] > 25:
                    continue
                i = iou(t["last_box"], (o["x"], o["y"], o["w"], o["h"]))
                if i > best_iou: best, best_iou = tid, i
            if best is None:
                tid = f"track_{next_id:03d}"; next_id += 1
                tracks[tid] = {"label": o["label"], "frames": [],
                               "last_box": None, "last_frame": frame_no,
                               "score": o.get("score", 0.8)}
            else:
                tid = best
            tracks[tid]["frames"].append((frame_no, o["x"], o["y"], o["w"], o["h"]))
            tracks[tid]["last_box"] = (o["x"], o["y"], o["w"], o["h"])
            tracks[tid]["last_frame"] = frame_no
    return tracks

def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax+aw, bx+bw), min(ay+ah, by+bh)
    inter = max(0, x2-x1) * max(0, y2-y1)
    union = aw*ah + bw*bh - inter
    return inter/union if union else 0
```

## 附录 B：导入与批量校验

```python
# import_predictions.py
import requests, json

LS = "http://localhost:8080"
TOKEN = "YOUR_TOKEN"
H = {"Authorization": f"Token {TOKEN}"}

# 方式 1：建任务时内联 predictions（批量一次性导入）
def import_tasks(project_id, tasks):
    r = requests.post(f"{LS}/api/projects/{project_id}/import",
                      headers=H, json=tasks, timeout=120)
    r.raise_for_status(); return r.json()

# 方式 2：任务已存在，单独补预测（换模型重跑时用它）
def create_prediction(task_id, prediction):
    payload = {"task": task_id, **prediction}
    r = requests.post(f"{LS}/api/predictions/", headers=H, json=payload, timeout=60)
    r.raise_for_status(); return r.json()

# 导入前必做的 schema 校验
def check(pred):
    assert pred.get("model_version"), "缺 model_version，无法做版本对比"
    for r_ in pred["result"]:
        v = r_["value"]
        assert r_["type"] == "videorectangle"
        assert v["framesCount"] > 0, "framesCount 必须为正"
        seq = v["sequence"]
        assert seq and min(s["frame"] for s in seq) >= 1, "帧号从 1 开始"
        for s in seq:
            assert 0 <= s["x"] <= 100 and 0 <= s["width"] <= 100, f"坐标越界: {s}"
            assert s["frame"] <= v["framesCount"], f"帧号超出总帧数: {s['frame']}"
    return True
```

## 附录 C：Label Studio ML Backend 骨架（档位 C）

```python
# ml_backend/model.py
from label_studio_ml.model import LabelStudioMLBase

class ICHVideoDetector(LabelStudioMLBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_version = "selftrained-yolo-v1"
        # self.detector = YOLO("best.pt")

    def predict(self, tasks, context=None, **kwargs):
        predictions = []
        for task in tasks:
            video = task["data"]["video"]
            # tracks = self.detector.track(video, tracker="bytetrack.yaml")
            # seq = to_ls_sequence(tracks)      # 见附录 A 的 build_prediction
            predictions.append({
                "model_version": self.model_version,
                "score": 0.0,
                "result": [],          # 替换为 to_ls_sequence 输出
            })
        return predictions

    def fit(self, event, data, **kwargs):
        """主动学习回调：标注提交后触发增量训练"""
        # 从 self.get_annotated_tasks() 拉取已标注数据 → 微调 → 更新 model_version
        return {"model_version": self.model_version}
```

启动与挂载：
```bash
pip install label-studio-ml
label-studio-ml start ./ml_backend -p 9090
# 然后在 Label Studio：Settings → Model → Add Model → http://localhost:9090
```

---

## 立即可做的三件事

1. **挑 20 条代表性视频**（覆盖不同门类、不同拍摄条件），转码 + 切分，先把流程跑通再谈规模。
2. **冻结标签集 v0.1**（20～40 个），写进标注手册，找 2 个人各标同一条验证一致性。
3. **跑档位 A 的冷启动**，同时让标注员对其中 5 条做「从零标注」计时 —— 拿到这个基准线，后面所有投入决策都有依据。
