"""Label Studio 预标注适配器。

将 VideoAnalysisDemo 返回的中文嵌套 JSON 转换为 Label Studio
ML backend 所需的 prediction result。该模块不负责加载模型。
"""
from __future__ import annotations

import ipaddress
import http.client
import ssl
import os
import shutil
import socket
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEO_ROOT = BASE_DIR / "uploads"
MAX_VIDEO_BYTES = int(os.getenv("LABEL_STUDIO_MAX_VIDEO_BYTES", str(2 * 1024**3)))
DOWNLOAD_TIMEOUT = float(os.getenv("LABEL_STUDIO_DOWNLOAD_TIMEOUT", "120"))
MODEL_VERSION = os.getenv("LABEL_STUDIO_MODEL_VERSION", "qwen2.5-vl-labelstudio-v1")

HERITAGE_TYPES = {
    "民间文学", "传统音乐", "传统舞蹈", "传统戏剧", "曲艺",
    "传统体育游艺与杂技", "传统美术", "传统技艺", "传统医药", "民俗", "其他",
}
USAGE_CONTEXTS = {"仪式化", "娱乐化", "商业化", "教学演示", "日常生活", "其他"}
AUDIENCE_TYPES = {"本地居民", "游客", "官方人员", "学徒", "儿童", "其他"}
CAMERA_MOVEMENTS = {
    "固定机位", "推镜头", "拉镜头", "摇镜头", "移镜头", "推拉摇移",
    "手持镜头", "跟拍镜头", "航拍镜头（无人机）", "其他",
}
NARRATIVE_STRUCTURES = {
    "线性叙事", "非线性叙事", "环状结构", "并置结构", "多声部叙事",
    "观察式叙事", "提问式（访谈驱动）叙事", "过程性（技艺流程）叙事",
    "档案式/历史拼贴叙事", "片段式/段落式叙事", "仪式化叙事结构",
    "师徒/传承叙事结构", "空间迁移叙事", "季节/节令叙事", "冲突驱动文化叙事", "其他",
}
URBAN_RURAL_SCENES = {
    "乡村社区", "城市街区", "市场场域", "家庭空间", "宗教/仪式场所",
    "舞台/表演场所", "作坊/生产场所", "其他", "无法确定",
}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_text(value: Any, empty: str = "") -> str:
    if value is None:
        return empty
    if isinstance(value, (list, tuple)):
        return "\n".join(f"{index}. {item}" for index, item in enumerate(value, 1))
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            rendered = _as_text(item)
            if rendered:
                lines.append(f"{key}：{rendered}")
        return "\n".join(lines)
    return str(value).strip()


def _choice_result(name: str, choices: Iterable[str]) -> Optional[Dict[str, Any]]:
    values = [str(item) for item in choices if str(item).strip()]
    if not values:
        return None
    return {
        "from_name": name,
        "to_name": "video",
        "type": "choices",
        "value": {"choices": values},
    }


def _text_result(name: str, value: Any) -> Optional[Dict[str, Any]]:
    text = _as_text(value)
    if not text:
        return None
    return {
        "from_name": name,
        "to_name": "video",
        "type": "textarea",
        "value": {"text": [text]},
    }


def _filtered_choices(value: Any, allowed: set[str]) -> List[str]:
    return [item for item in _as_list(value) if item in allowed]


def _nested(result: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    value: Any = result
    for key in keys:
        if not isinstance(value, dict):
            return {}
        value = value.get(key, {})
    return value if isinstance(value, dict) else {}


def analysis_to_results(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将模型分析 JSON 转换为 Label Studio annotation results。"""
    if not isinstance(analysis, dict) or analysis.get("error") or not any(
        isinstance(analysis.get(name), dict) and analysis[name]
        for name in ("模块三_非遗文化信息", "模块四_影像技术与风格分析",
                     "模块五_人物与社会关系结构", "模块六_叙事与语义层级分析")
    ):
        raise ValueError("模型没有返回可用于预标注的结构化结果")

    module3 = analysis.get("模块三_非遗文化信息", {})
    module4 = analysis.get("模块四_影像技术与风格分析", {})
    module5 = analysis.get("模块五_人物与社会关系结构", {})
    module6 = analysis.get("模块六_叙事与语义层级分析", {})
    if not all(isinstance(item, dict) for item in (module3, module4, module5, module6)):
        raise ValueError("模型结果的模块结构无效")

    material = _nested(module3, "物质文化元素")
    intangible = _nested(module3, "非物质文化元素")
    context = _nested(module3, "社会文化语境与场域")
    process = _nested(module3, "技艺仪式流程解析")
    audio = _nested(module4, "声音内容分析")
    scene = _nested(module4, "场景与景别")
    color = _nested(module4, "色彩风格分析")
    rhythm = _nested(module4, "镜头节奏统计")
    themes = _nested(module6, "主题聚类")
    values = _nested(module6, "价值取向与情感")

    results: List[Dict[str, Any]] = []
    choice_specs = (
        ("heritage_type", _filtered_choices(module3.get("类型"), HERITAGE_TYPES)),
        ("urban_rural_scene", [context.get("城乡场景")] if context.get("城乡场景") in URBAN_RURAL_SCENES else []),
        ("usage_context", _filtered_choices(context.get("使用语境"), USAGE_CONTEXTS)),
        ("audience_type", _filtered_choices(context.get("观众类型"), AUDIENCE_TYPES)),
        ("camera_movement", _filtered_choices(module4.get("镜头运动类型"), CAMERA_MOVEMENTS)),
        ("narrative_structure", _filtered_choices(module6.get("叙事结构"), NARRATIVE_STRUCTURES)),
    )
    for name, choices in choice_specs:
        item = _choice_result(name, choices)
        if item:
            results.append(item)

    narration = audio.get("是否有旁白")
    narration_label = "有旁白" if narration is True else "无旁白" if narration is False else "无法确定"
    results.append(_choice_result("has_narration", [narration_label]))

    text_specs = (
        ("material_elements", {
            "道具": material.get("道具"),
            "服饰": material.get("服饰"),
            "建筑与场地": material.get("建筑与场地"),
            "民族或地区关联": material.get("民族或地区关联"),
        }),
        ("intangible_elements", {
            "仪式元素": intangible.get("仪式元素"),
            "技艺流程": intangible.get("技艺流程"),
            "口述传统文本": intangible.get("口述传统文本"),
            "身体动作序列": intangible.get("身体动作序列"),
        }),
        ("process_analysis", {
            "技艺流程分段": process.get("技艺流程分段"),
            "仪式程序分段": process.get("仪式程序分段"),
            "关键步骤": process.get("关键步骤"),
        }),
        ("audio_analysis", {
            "环境音类型": audio.get("环境音类型"),
            "传统乐器识别": audio.get("传统乐器识别"),
            "唱腔类型": audio.get("唱腔类型"),
        }),
        ("scene_shot_analysis", {
            "场景": scene.get("场景"),
            "景别": scene.get("景别"),
        }),
        ("color_style_analysis", {
            "色调": color.get("色调"),
            "饱和度": color.get("饱和度"),
            "民族色彩特征": color.get("民族色彩特征"),
        }),
        ("shot_rhythm", {
            "平均镜头长度": rhythm.get("平均镜头长度"),
            "稳定vs快剪比例": rhythm.get("稳定vs快剪比例"),
            "长镜头分布": rhythm.get("长镜头分布"),
        }),
        ("person_social_identity", module5.get("人物社会身份")),
        ("person_relationship", module5.get("人物关系")),
        ("community_structure", module5.get("社区群体结构")),
        ("theme_cluster", {
            "主要主题": themes.get("主要主题"),
            "子主题": themes.get("子主题"),
        }),
        ("value_emotion", {
            "价值取向": values.get("价值取向"),
            "情感分析": values.get("情感分析"),
        }),
        ("conflict_points", module6.get("冲突点识别")),
    )
    for name, value in text_specs:
        item = _text_result(name, value)
        if item:
            results.append(item)
    if len(results) == 1 and results[0]["from_name"] == "has_narration":
        raise ValueError("模型没有返回可用于预标注的结构化结果")
    return results


def _public_address(host: str) -> str:
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("为防止 SSRF，不允许访问内网视频地址") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("为防止 SSRF，不允许访问内网视频地址")
    return sorted(addresses)[0]


def _resolve_video_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname:
            raise ValueError("为防止 SSRF，不允许访问内网视频地址")
        return value
    if parsed.scheme:
        raise ValueError("仅支持 http(s) 视频地址或受控本地路径")
    return value


def _open_video(request: Request, timeout: float):
    host = urlparse(request.full_url).hostname
    address = _public_address(host)

    class PinnedHTTPConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.create_connection((address, self.port), self.timeout)

    class PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            self.sock = socket.create_connection((address, self.port), self.timeout)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

    class PinnedHTTPHandler(HTTPHandler):
        def http_open(self, req):
            return self.do_open(PinnedHTTPConnection, req)

    class PinnedHTTPSHandler(HTTPSHandler):
        def https_open(self, req):
            return self.do_open(PinnedHTTPSConnection, req, context=ssl.create_default_context())

    class NoRedirects(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    return build_opener(ProxyHandler({}), PinnedHTTPHandler(), PinnedHTTPSHandler(), NoRedirects()).open(request, timeout=timeout)


def materialize_video(value: Any) -> Tuple[str, Optional[str]]:
    """返回本地视频路径和需要清理的临时目录；本地受控文件不清理。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Label Studio 任务缺少 data.video")
    value = value.strip()
    studio_file = value.startswith("/data/local-files/")
    if studio_file:
        label_studio_url = os.getenv("LABEL_STUDIO_URL", "").strip()
        if not label_studio_url:
            raise ValueError("相对 Label Studio local-files 地址需要设置 LABEL_STUDIO_URL")
        value = urljoin(label_studio_url.rstrip("/") + "/", value.lstrip("/"))
        if os.getenv("LABEL_STUDIO_API_KEY", "").strip() and urlparse(value).scheme != "https":
            raise ValueError("携带 Label Studio API Key 时必须使用 HTTPS")
    value = _resolve_video_url(value)
    if value.startswith(("http://", "https://")):
        suffix = Path(urlparse(value).path).suffix.lower() or ".mp4"
        if suffix not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            suffix = ".mp4"
        temp_dir = tempfile.mkdtemp(prefix="label-studio-video-")
        target = Path(temp_dir) / f"input{suffix}"
        request_headers = {"User-Agent": "video-vl-labelstudio/1.0"}
        api_key = os.getenv("LABEL_STUDIO_API_KEY", "").strip() if studio_file else ""
        if api_key:
            request_headers["Authorization"] = f"Token {api_key}"
        request = Request(value, headers=request_headers)
        try:
            try:
                response = _open_video(request, timeout=DOWNLOAD_TIMEOUT)
            except HTTPError as exc:
                if 300 <= exc.code < 400:
                    raise ValueError("视频下载不允许重定向") from exc
                raise
            with response, target.open("wb") as output:
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_VIDEO_BYTES:
                        raise ValueError("视频超过 LABEL_STUDIO_MAX_VIDEO_BYTES 限制")
                    output.write(chunk)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return str(target), temp_dir

    path = Path(value).expanduser().resolve()
    allowed_root = Path(os.getenv("LABEL_STUDIO_VIDEO_ROOT", str(DEFAULT_VIDEO_ROOT))).expanduser().resolve()
    if not path.is_file() or (path != allowed_root and allowed_root not in path.parents):
        raise ValueError(f"本地视频必须位于受控目录: {allowed_root}")
    return str(path), None


def predict_tasks(tasks: Iterable[Dict[str, Any]], analyzer: Any) -> List[Dict[str, Any]]:
    """同步处理 Label Studio 任务；调用方应在外部加 GPU 串行锁。"""
    predictions = []
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("tasks 中包含无效任务")
        data = task.get("data") or {}
        video_path, cleanup_dir = materialize_video(data.get("video"))
        try:
            with tempfile.TemporaryDirectory(prefix="label-studio-result-") as output_dir:
                analysis = analyzer.analyze_video(
                    video_path,
                    output_path=str(Path(output_dir) / "analysis.json"),
                )
            results = analysis_to_results(analysis)
            predictions.append({"model_version": MODEL_VERSION, "result": results})
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
    return predictions
