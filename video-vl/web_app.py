"""
视频文化影像分析系统 - Web 后端 (FastAPI)
提供模型加载、视频分析 API，配合 HTML/CSS 前端使用。
"""
import os
import json
import threading
import traceback
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# 项目内模块
from label_studio_adapter import MAX_VIDEO_BYTES, MODEL_VERSION, predict_tasks
from qwen_api_analyzer import build_qwen_api_analyzer_from_env

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="视频文化影像分析系统", version="1.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# -----------------------------------------------------------------------------
# 全局状态（后台线程执行长耗时任务，前端轮询状态）
# -----------------------------------------------------------------------------
DEFAULT_MODEL_PATH = os.getenv(
    "MODEL_PATH",
    "/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B",
)
DEFAULT_GPU_IDS = os.getenv("GPU_IDS") or None

state_lock = threading.Lock()
model_load_lock = threading.Lock()
model_state = {
    "status": "idle",        # idle | loading | ready | error
    "error": None,
    "gpu_ids": None,
    "model_path": DEFAULT_MODEL_PATH,
}
analyzer: Optional[object] = None
label_studio_predict_lock = threading.Lock()

analysis_state = {
    "status": "idle",        # idle | running | done | error
    "error": None,
    "progress": 0,
    "stage": "",
    "video_name": "",
    "result": None,
    "result_path": None,
}


def _load_model_thread(model_path: str, gpu_ids: Optional[str]):
    """后台线程：加载模型。"""
    global analyzer
    try:
        with state_lock:
            model_state["status"] = "loading"
            model_state["error"] = None
            model_state["model_path"] = model_path
            model_state["gpu_ids"] = gpu_ids

        if gpu_ids:
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_ids

        if os.getenv("DASHSCOPE_API_KEY", "").strip():
            loaded_analyzer = build_qwen_api_analyzer_from_env()
            model_path = "qwen-api"
        else:
            from video_analysis_demo import VideoAnalysisDemo
            loaded_analyzer = VideoAnalysisDemo(model_path=model_path, gpu_ids=gpu_ids)
        with state_lock:
            analyzer = loaded_analyzer
            model_state["status"] = "ready"
        print("[模型加载] 完成")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[模型加载] 失败: {err}")
        traceback.print_exc()
        with state_lock:
            model_state["status"] = "error"
            model_state["error"] = err


def _analyze_thread(video_path: str, video_name: str):
    """后台线程：分析视频。"""
    global analyzer
    try:
        with state_lock:
            analysis_state.update(
                status="running", error=None, progress=10, stage="正在分析视频…",
                video_name=video_name, result=None, result_path=None,
            )

        if analyzer is None:
            raise RuntimeError("模型未加载")

        print(f"[分析] 开始: {video_name}")
        with state_lock:
            analysis_state["stage"] = "模型推理中…"
            analysis_state["progress"] = 30

        with label_studio_predict_lock:
            result = analyzer.analyze_video(video_path, output_path=None)

        # 保存结果
        base_name = Path(video_name).stem
        result_path = UPLOAD_DIR / f"{base_name}_analysis.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        with state_lock:
            analysis_state.update(
                status="done", progress=100, stage="分析完成",
                result=result, result_path=str(result_path),
            )
        print(f"[分析] 完成: {result_path}")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[分析] 失败: {err}")
        traceback.print_exc()
        with state_lock:
            analysis_state.update(status="error", error=err, stage="分析失败")
    finally:
        # 清理上传的临时视频
        try:
            if os.path.exists(video_path):
                os.unlink(video_path)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 路由
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/model-status")
async def model_status():
    with state_lock:
        return JSONResponse({
            "status": model_state["status"],
            "error": model_state["error"],
            "model_path": model_state["model_path"],
            "gpu_ids": model_state["gpu_ids"],
        })


@app.post("/api/load-model")
async def load_model(model_path: str = Form(DEFAULT_MODEL_PATH),
                     gpu_ids: str = Form("0,1,2,3")):
    global analyzer
    with state_lock:
        if model_state["status"] in {"loading", "ready"}:
            if model_state["status"] == "ready" and analyzer is not None:
                return {"ok": True, "msg": "模型已加载", "status": "ready"}
            return JSONResponse({"ok": False, "msg": "模型正在加载中，请稍候"}, status_code=409)

    gpu_value = gpu_ids.strip() if gpu_ids and gpu_ids.strip() else DEFAULT_GPU_IDS
    with model_load_lock:
        with state_lock:
            if model_state["status"] == "loading":
                return JSONResponse({"ok": False, "msg": "模型正在加载中，请稍候"}, status_code=409)
            model_state["status"] = "loading"
            model_state["error"] = None
        t = threading.Thread(
            target=_load_model_thread,
            args=(model_path, gpu_value),
            daemon=True,
        )
    t.start()
    return {"ok": True, "msg": "开始加载模型", "status": "loading"}


@app.get("/api/analysis-status")
async def analysis_status_api():
    with state_lock:
        return JSONResponse({
            "status": analysis_state["status"],
            "error": analysis_state["error"],
            "progress": analysis_state["progress"],
            "stage": analysis_state["stage"],
            "video_name": analysis_state["video_name"],
            "result": analysis_state["result"],
            "result_path": analysis_state["result_path"],
        })


@app.post("/api/analyze")
async def analyze(video: UploadFile = File(...)):
    global analyzer
    with state_lock:
        if model_state["status"] != "ready" or analyzer is None:
            raise HTTPException(status_code=400, detail="模型未加载，请先加载模型")
        if analysis_state["status"] == "running":
            raise HTTPException(status_code=409, detail="已有分析任务进行中")
        analysis_state.update(status="running", error=None, progress=0, stage="保存上传视频…")

    # 保存上传视频
    suffix = Path(video.filename).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=str(UPLOAD_DIR))
    try:
        total = 0
        while chunk := await video.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_VIDEO_BYTES:
                raise HTTPException(status_code=413, detail="视频过大")
            tmp.write(chunk)
        tmp.close()
    except HTTPException:
        tmp.close()
        os.unlink(tmp.name)
        with state_lock:
            analysis_state.update(status="idle", stage="", progress=0)
        raise
    except Exception as e:
        tmp.close()
        try:
            os.unlink(tmp.name)
        finally:
            with state_lock:
                analysis_state.update(status="error", error=f"保存视频失败: {e}", stage="分析失败")
        raise HTTPException(status_code=500, detail=f"保存视频失败: {e}")

    t = threading.Thread(
        target=_analyze_thread,
        args=(tmp.name, video.filename),
        daemon=True,
    )
    t.start()
    return {"ok": True, "msg": "开始分析", "video_name": video.filename}


@app.post("/setup")
async def label_studio_setup(payload: dict):
    """验证项目标注控件是否与视频级预测字段兼容。"""
    schema = payload.get("schema") or payload.get("label_config")
    try:
        root = ET.fromstring(schema)
    except (TypeError, ET.ParseError) as exc:
        raise HTTPException(status_code=400, detail="缺少有效的标注配置") from exc
    controls = {(element.tag, element.get("name"), element.get("toName")) for element in root.iter()}
    required = {
        ("Video", "video", None),
        *(("Choices", name, "video") for name in (
            "heritage_type", "urban_rural_scene", "usage_context", "audience_type",
            "camera_movement", "narrative_structure", "has_narration")),
        *(("TextArea", name, "video") for name in (
            "material_elements", "intangible_elements", "process_analysis", "audio_analysis",
            "scene_shot_analysis", "color_style_analysis", "shot_rhythm",
            "person_social_identity", "person_relationship", "community_structure",
            "theme_cluster", "value_emotion", "conflict_points")),
    }
    if not required <= controls:
        raise HTTPException(status_code=400, detail="标注配置缺少预标注所需控件")
    return {"model_version": MODEL_VERSION}


@app.post("/predict")
async def label_studio_predict(payload: dict):
    """Label Studio ML backend 兼容接口：生成视频级预标注。"""
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise HTTPException(status_code=400, detail="请求必须包含非空 tasks 数组")

    with state_lock:
        current_analyzer = analyzer
    if current_analyzer is None:
        raise HTTPException(status_code=503, detail="模型未加载，请先调用 /api/load-model")

    try:
        # Qwen 72B 推理通常占用大量 GPU，与 Web 分析共用推理锁。
        def predict_serially():
            with label_studio_predict_lock:
                return predict_tasks(tasks, current_analyzer)

        predictions = await run_in_threadpool(predict_serially)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"预标注失败: {type(exc).__name__}: {exc}") from exc

    return {"results": predictions}


@app.get("/health")
async def health():
    with state_lock:
        status = model_state["status"]
    return {"status": "ok", "model_status": status}


@app.get("/api/download")
async def download_result():
    with state_lock:
        path = analysis_state.get("result_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="无可下载的结果文件")
    return FileResponse(path, media_type="application/json",
                        filename=Path(path).name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=False)
