# 用 Qwen 做三层十二项标注 —— 操作手册

> 依据：甲方《非遗影像智能分析与评测标准构建》（PPTX）+《20260608影片片段标注》（XLSX v4.0）
> 所有规范都从这两份文件抽出来，落在 `refs/annotation_spec_v4.json`，代码不硬编码词表。

## 0. 一次性准备

```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxx      # 百炼控制台申请，Qwen 和 ASR 共用一个
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1   # 默认值，可不设
export QWEN_MODEL=qwen-vl-max-latest      # 也可换 qwen3-vl-plus

PY=~/.workbuddy/binaries/python/envs/ultra/bin/python
```

依赖已装好：`openpyxl`、`dashscope`、`opencv`、`imageio-ffmpeg`（自带 ffmpeg 7.1，本机没有系统 ffmpeg）。

## 1. 看提示词（不花钱）

```bash
$PY scripts/qwen_label.py --show-prompt refs/qwen_system_prompt.md
```

输出 5500 字符，12 项全齐，每项带词表原词 + 甲方判断说明 + 甲方实际的输出句式。

## 2. 跑一段试试

```bash
# 先抽音轨转写（T1-4 需要，没有就别跑它）
$PY scripts/asr.py --clip /Users/lixin/video-vl/SD0022004522630060044.mp4 --out .tmp/asr/v3.txt

# 再标注
$PY scripts/qwen_label.py \
  --clip /Users/lixin/video-vl/SD0022004522630060044.mp4 \
  --asr .tmp/asr/v3.txt \
  --fewshot 3 \
  --out .tmp/out_v3.json
```

`--fewshot 3` 会从金标准里自动挑「仪式 / 工序 / 口述」各一条做示范，明显提升格式稳定性，代价是多花 token。先不加以省成本。

## 2.5 四条冒烟测试片段（`/Users/lixin/video-vl`）

| 片段 | 内容 | 时长 | 画质 | 参考门类 |
|---|---|---:|---|---|
| `482344871227e9f9193de1e2a7e67ec5_raw` | 藏族草原节庆演出，蓝红藏袍、经幡 | 81s | 1568×886 | 传统舞蹈（次选民俗） |
| `SD0012003522630060003` | 门口烧纸点香，幼童旁观 | 36s | 720×576 | 民俗 |
| `SD0022004522630060044` | 苗族芦笙队，黑包头、绣花坎肩，县城街道巡游 | 101s | 720×576 | 传统音乐（次选民俗） |
| `ea9fe2e3209eccbf5471ac6c6656b51a_raw` | 户外手工织机特写，老人带幼童 | 71s | 1572×878 | 传统技艺 |

四条都有音轨，覆盖三个门类（舞蹈 / 民俗 / 音乐 / 技艺），适合做冒烟集。

参考标注在 `refs/ref4_reference.jsonl`（`scripts/ref4_reference.py` 生成，自带词表校验）。
**它是「参考基准」不是甲方金标准**，来源是逐帧判读 + 项目里已有的旧标注，只用于验证格式合规和判断是否离谱。

```bash
# 跑四条
$PY scripts/qwen_label.py --batch /Users/lixin/video-vl --out .tmp/qwen4.jsonl

# 跟参考基准比
$PY scripts/evaluate.py --pred .tmp/qwen4.jsonl --gold refs/ref4_reference.jsonl --md .tmp/report4.md
```

## 3. 批量跑

```bash
$PY scripts/qwen_label.py --batch data/clips --limit 5 --out .tmp/preds.jsonl
```

每条约 12.5k 输入 token（16 帧 + 5.5k 系统提示词）。全量 1391 段粗算 **¥55/轮**。

## 4. 打分

有两条路，**优先用裁判**：

### 4.1 大模型裁判（推荐，甲方原表就要求 GPT-as-Judge）

```bash
$PY scripts/judge.py --pred .tmp/qwen4_run3.jsonl --gold refs/ref4_reference.jsonl \
    --out .tmp/judge_run3.json --md .tmp/judge_run3.md
```

只判「结论对不对、依据成不成立」，明确告知裁判篇幅长短不扣分。
这份才是可信的分数。

### 4.2 字符指标（只作回归自检，不当作性能结论）

```bash
$PY scripts/evaluate.py --pred .tmp/preds.jsonl --md .tmp/report.md
```

自检方式（应与自己完全一致，得分 1.000）：

```bash
$PY scripts/evaluate.py --pred refs/gold.jsonl
```

⚠️ **字符 n-gram F1 会被篇幅差异主导**。实测 Qwen 输出是参考的 1.6~2.6 倍长，
结论基本一致却只拿 0.15 分。它能验证「流程对了没有」，不能回答「答得好不好」。

### 4.3 多轮一致性（甲方要求的「逻辑自洽」检验）

```bash
$PY scripts/stability.py .tmp/qwen4_run3.jsonl .tmp/qwen4_run4.jsonl .tmp/qwen4_run5.jsonl \
    --md .tmp/stability.md
```

输出每个任务的标签 Jaccard、三轮是否全一致、文本 F1、置信度是否同档。
标签不稳的条目会被逐条列出，那些就是要人工复核的。

## 5. 规范怎么维护

甲方改词表时，只改配置、不改代码：

```bash
$PY scripts/build_spec.py      # 重读 xlsx，重建 refs/annotation_spec_v4.json
$PY scripts/build_gold.py      # 重建 refs/gold.jsonl + 归一化报告
```

`build_spec.py` 会自检权重合计是否为 1.00；`build_gold.py` 会报「未解析残留」数量，目前 10 处 / 7489 个标签实例。

## 已知边界（别指望自动分能替代人工）

| 项 | 状态 | 说明 |
|---|---|---|
| T1-4 听觉 | 需 ASR | 乐器音、唱腔、仪式音效 ASR 转不出来，仍要靠模型从音色推断或人工补 |
| T2-4 门类 | 结构性风险 | 占 0.30 权重、零容错，但只有 87 秒片段信息，金标准里 402 条这列本来就是空的 |
| T3-2/3/4 | 参考级 | 甲方自己写「AI 仅作参考提示器」，别拿它做验收指标 |
| 置信度 | 不可用 | 人工 91% 填「高」、0.4% 填「低」，没有区分度，用它评估可靠性会失效 |
| 文本相似度 | 弱代理 | 字符 n-gram F1 对「截断一半」的文本仍给 0.73，偏宽松；正式报告建议换 BERTScore |
