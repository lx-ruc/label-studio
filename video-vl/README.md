# 基于Qwen2.5-VL的视频理解分析Demo

这是一个基于Qwen2.5-VL模型的视频理解分析工具，可以对上传的视频进行全面的文化影像分析，并按照结构化格式输出分析结果。

## 功能特点

本demo可以对视频进行以下六个模块的全面分析：

### 模块三-非遗文化信息
- 类型分类（十大门类）
- 非遗相关物质文化元素识别（道具、服饰、建筑与场地）
- 非遗相关非物质文化元素识别（仪式、技艺、口述传统、身体动作）
- 社会文化语境与场域识别
- 技艺/仪式流程结构化解析

### 模块四-影像技术与风格分析
- 声音内容分析
- 场景与景别识别
- 色彩风格分析
- 镜头运动类型识别
- 镜头节奏与镜头长度统计

### 模块五-人物与社会关系结构
- 人物社会身份信息
- 人物关系识别
- 社区或群体结构分析

### 模块六-叙事与语义层级分析
- 叙事结构识别（多种叙事类型）
- 主题聚类/扎根理论编码
- 价值取向与情感分析
- 冲突点识别

## 安装要求

### 基础依赖
```bash
pip install torch transformers qwen-vl-utils
```

### Streamlit Web界面（推荐）
```bash
pip install -r requirements.txt
# 或
pip install streamlit torch transformers qwen-vl-utils
```

确保已安装Qwen2.5-VL模型到指定路径（默认：`/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B`）

## Label Studio 多模态预标注

项目提供了兼容 Label Studio ML Backend 的 `POST /predict` 接口。它会读取 Label Studio 任务中的 `data.video`，调用 Qwen2.5-VL 分析视频，并把模块三至模块六的结果转换为可编辑的预标注。

### 启动

先安装服务及模型依赖（72B 模型需要有足够显存的 GPU）：

```bash
pip install -r label_studio_ml_requirements.txt
```

启动服务时指定实际存在的模型路径，并使用空闲端口（下面以 8765 为例）：

```bash
MODEL_PATH=/path/to/Qwenvl_72B \
LABEL_STUDIO_VIDEO_ROOT=/path/to/shared/videos \
python -m uvicorn web_app:app --host 0.0.0.0 --port 8765
```

服务启动后需要**单独加载模型**，等待 `model_status` 为 `ready`；`/health` 返回 `ok` 并不表示模型已就绪：

```bash
curl -X POST http://localhost:8765/api/load-model -F 'model_path=/path/to/Qwenvl_72B' -F 'gpu_ids=0,1,2,3'
curl http://localhost:8765/api/model-status
```

在 Label Studio 项目中先导入 `label_studio_config.xml` 标注配置，再到 **Machine Learning → Add Model** 填写：

```text
http://<推理服务地址>:8765
```

`/setup` 会校验项目标注配置中的预测控件；不匹配时返回 400。当前只用模拟分析器进行了本地接口测试，尚未在真实 Label Studio 和 72B 模型上完成联调。

### 使用阿里云百炼通义千问视觉 API

设置 API Key 后，服务启动时会优先使用 Qwen API，不加载本地 72B 模型：

```bash
export DASHSCOPE_API_KEY='从阿里云控制台新生成的 Key'
export QWEN_MODEL='qwen3.8-max'
export DASHSCOPE_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export QWEN_VIDEO_FPS=1
python -m uvicorn web_app:app --host 0.0.0.0 --port 8765
curl -X POST http://localhost:8765/api/load-model -F 'model_path=qwen-api' -F 'gpu_ids='
```

随后确认 `/api/model-status` 为 `ready`，再在 Label Studio 中调用 `/predict`。本地视频会以内联 Base64 视频发送到百炼；默认限制为 7 MiB，超过限制会返回明确错误。百炼视觉接口不理解视频音频，因此旁白、乐器和唱腔字段不会被模型猜测。API Key 不要写入代码、文档或 Git；你此前发送过的 Key 应先在控制台轮换。


任务中的视频字段必须叫 `video`。推理服务支持可达的公网 HTTP(S) 地址，或位于 `LABEL_STUDIO_VIDEO_ROOT` 下的受控本地文件：

```json
{
  "data": {
    "video": "https://example.com/videos/demo.mp4"
  }
}
```

也可以使用与推理服务共享挂载的受控本地路径，例如：

```json
{
  "data": {
    "video": "/path/to/shared/videos/demo.mp4"
  }
}
```

服务端会调用 `/predict`，请求格式为：

```json
{
  "tasks": [
    {"id": 1, "data": {"video": "https://example.com/videos/demo.mp4"}}
  ],
  "project": 1
}
```

返回结果是 Label Studio `predictions` 格式。非遗类型会被限制为十大门类及“其他”，`是否有旁白`会转换为“有旁白/无旁白/无法确定”三态选项。当前模型没有可靠时间码，因此不会自动生成 `VideoLabels` 时间段；流程时间轴由标注员人工校正。

注意：72B 模型推理资源消耗很大，建议只运行一个模型进程；普通 Web 分析与 Label Studio 预标注在同一进程中共用推理锁。不要让任务请求传入模型路径或 GPU 参数。公网视频仅允许 HTTP(S) 且不跟随重定向，本地视频必须位于 `LABEL_STUDIO_VIDEO_ROOT` 目录下；仅当任务使用 `/data/local-files/` 且 `LABEL_STUDIO_URL` 指向允许访问的公网地址时，才会向该地址发送 `LABEL_STUDIO_API_KEY`。内网 Label Studio URL 与 `/data/upload/...` 暂不支持；共享挂载的文件路径还须另行保证浏览器可以播放。模型推理接口目前没有认证，部署时应限制访问来源。

无模型回归测试：`python -m pytest -q test_label_studio_integration.py`（需安装 pytest、httpx；测试使用模拟分析器，不验证真实 GPU、Label Studio 接入和人工导出）。


### 🌐 Streamlit Web界面（推荐）

启动Web界面：
```bash
streamlit run streamlit_app.py
```

然后在浏览器中打开显示的URL（通常是 `http://localhost:8501`）

**使用步骤：**
1. 在侧边栏点击"加载模型"按钮（首次使用需要加载，可能需要几分钟）
2. 在"视频上传与分析"标签页上传视频文件
3. 点击"开始分析"按钮
4. 等待分析完成（可能需要较长时间）
5. 切换到"分析结果"标签页查看详细的分析结果
6. 可以下载JSON格式的分析结果

**界面特点：**
- 🎨 美观的Web界面
- 📊 结构化的结果展示（按模块分类）
- 📥 支持下载分析结果
- 🔄 实时显示分析进度
- 📹 视频预览功能

### 命令行使用

```bash
python video_analysis_demo.py --video <视频路径> [--output <输出路径>] [--model_path <模型路径>]
```

**参数说明：**
- `--video`: 必需，要分析的视频文件路径
- `--output`: 可选，输出JSON文件路径（默认：视频同目录下，文件名_analysis.json）
- `--model_path`: 可选，模型路径（默认：`/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B`）

**示例：**
```bash
# 基本使用
python video_analysis_demo.py --video /path/to/video.mp4

# 指定输出路径
python video_analysis_demo.py --video /path/to/video.mp4 --output /path/to/output.json

# 指定模型路径
python video_analysis_demo.py --video /path/to/video.mp4 --model_path /path/to/model
```

### Python代码中使用

```python
from video_analysis_demo import VideoAnalysisDemo

# 初始化分析器
analyzer = VideoAnalysisDemo(model_path="/path/to/model")

# 分析视频
result = analyzer.analyze_video(
    video_path="/path/to/video.mp4",
    output_path="/path/to/output.json"  # 可选
)

# 使用分析结果
print(result)
```

## 输出格式

分析结果以JSON格式保存，包含以下结构：

```json
{
  "模块三_非遗文化信息": {
    "类型": ["类别1", "类别2"],
    "物质文化元素": {...},
    "非物质文化元素": {...},
    "社会文化语境与场域": {...},
    "技艺仪式流程解析": {...}
  },
  "模块四_影像技术与风格分析": {...},
  "模块五_人物与社会关系结构": {...},
  "模块六_叙事与语义层级分析": {...}
}
```

## 注意事项

1. 确保有足够的GPU内存来加载模型（72B模型需要较大内存）
2. 视频分析可能需要较长时间，请耐心等待
3. 如果模型输出无法解析为JSON，原始输出会保存到error_output.txt文件
4. 建议视频文件大小适中，过大的视频文件可能需要更长的处理时间

## 文件说明

- `streamlit_app.py`: **Streamlit Web界面**（推荐使用）
- `video_analysis_demo.py`: 主程序文件，包含完整的分析功能（命令行版本）
- `video.py`: 原始的视频分析脚本（简化版）
- `video_vllm.py`: 使用vLLM的版本（需要vLLM支持）
- `requirements.txt`: Python依赖包列表

## 故障排除

如果遇到问题：

1. **模型加载失败**：检查模型路径是否正确，确保模型文件完整
2. **GPU内存不足**：尝试使用更小的模型或减少batch size
3. **JSON解析失败**：查看error_output.txt文件中的原始输出，可能需要调整prompt
4. **视频处理失败**：确保视频格式支持（建议使用MP4格式）

