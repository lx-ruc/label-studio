"""Qwen vision API analyzer for Label Studio pre-annotation."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.8-max"
DEFAULT_TIMEOUT = 180.0
DEFAULT_MAX_INLINE_BYTES = 7 * 1024 * 1024


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value).strip()


def _heritage_type(value: Any) -> list[str]:
    text = " ".join(_text(item) for item in _as_list(value))
    for candidate in ("民间文学", "传统音乐", "传统舞蹈", "传统戏剧", "曲艺",
                      "传统体育游艺与杂技", "传统美术", "传统技艺", "传统医药", "民俗"):
        if candidate in text:
            return [candidate]
    return ["其他"] if text and text not in {"无法确定", "null"} else []


def normalize_qwen_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Qwen's valid but variable Chinese schema to adapter schema."""
    if not isinstance(analysis, dict):
        raise ValueError("Qwen API 返回结果必须是 JSON 对象")
    required = ("模块三_非遗文化信息", "模块四_影像技术与风格分析",
                "模块五_人物与社会关系结构", "模块六_叙事与语义层级分析")
    if all(isinstance(analysis.get(name), dict) for name in required):
        module3 = analysis[required[0]]
        module4 = analysis[required[1]]
        module5 = analysis[required[2]]
        module6 = analysis[required[3]]
        if "类型" in module3 or "社会文化语境与场域" in module3:
            return analysis

        material = module3.get("物质文化元素", {})
        intangible = module3.get("非物质文化元素", {})
        people = module5.get("人物", [])
        normalized_people = []
        for person in _as_list(people):
            if isinstance(person, dict):
                normalized_people.append(person)
            else:
                normalized_people.append({"描述": _text(person)})
        return {
            "模块三_非遗文化信息": {
                "类型": _heritage_type(module3.get("非遗类型")),
                "物质文化元素": {"道具": _as_list(material), "服饰": [], "建筑与场地": [], "民族或地区关联": []},
                "非物质文化元素": {"仪式元素": _as_list(intangible), "技艺流程": [], "口述传统文本": [], "身体动作序列": []},
                "社会文化语境与场域": {"城乡场景": "其他", "使用语境": ["仪式化"] if "祭祀" in _text(module3) else [], "观众类型": []},
                "技艺仪式流程解析": {"技艺流程分段": [], "仪式程序分段": _as_list(intangible), "关键步骤": []},
            },
            "模块四_影像技术与风格分析": {
                "声音内容分析": {"是否有旁白": module4.get("是否有旁白"), "环境音类型": [], "传统乐器识别": [], "唱腔类型": []},
                "场景与景别": {"场景": module3.get("场景", ""), "景别": module4.get("景别", "")},
                "色彩风格分析": {"色调": module4.get("色彩", ""), "饱和度": "", "民族色彩特征": ""},
                "镜头运动类型": ["固定机位"] if "固定" in _text(module4.get("运镜")) else [],
                "镜头节奏统计": {"平均镜头长度": "", "稳定vs快剪比例": "", "长镜头分布": ""},
            },
            "模块五_人物与社会关系结构": {"人物社会身份": normalized_people, "人物关系": module5.get("人物关系", ""), "社区群体结构": module5.get("社会关系结构", "")},
            "模块六_叙事与语义层级分析": {"叙事结构": ["线性叙事"] if "线性" in _text(module6.get("叙事结构")) else [], "主题聚类": {"主要主题": module6.get("主题", ""), "子主题": []}, "价值取向与情感": {"价值取向": "", "情感分析": module6.get("情感基调", "")}, "冲突点识别": ""},
        }
    raise ValueError("Qwen API 返回缺少模块化结构")


ANALYSIS_PROMPT = """请分析这段非遗影像，并且只返回一个合法 JSON 对象，不要 Markdown 代码块，不要解释文字。
JSON 必须包含以下四个顶层键：模块三_非遗文化信息、模块四_影像技术与风格分析、模块五_人物与社会关系结构、模块六_叙事与语义层级分析。
请依据视频画面填写非遗类型、物质/非物质文化元素、场景、镜头、人物、叙事和主题等字段；无法从画面可靠判断的字段使用 null、空数组或“无法确定”。
该视觉接口不分析视频音频，因此“是否有旁白”、传统乐器和唱腔必须填 null 或“无法确定”，不得猜测。
"""


class QwenApiAnalyzer:
    """Call Alibaba Bailian's OpenAI-compatible Qwen vision endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        fps: float = 1.0,
        max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES,
    ) -> None:
        if not api_key.strip():
            raise ValueError("缺少 DASHSCOPE_API_KEY")
        if not 0.1 <= fps <= 10:
            raise ValueError("Qwen 视频 fps 必须在 0.1 到 10 之间")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.fps = fps
        self.max_inline_bytes = max_inline_bytes

    def analyze_video(self, video_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(video_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"视频文件不存在: {path}")
        if path.stat().st_size > self.max_inline_bytes:
            raise ValueError("本地视频超过 Qwen API 内联传输限制，请先压缩视频或改用可访问公网 URL")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "video_url", "video_url": {
                    "url": f"data:video/{path.suffix.lstrip('.') or 'mp4'};base64,{encoded}",
                    "fps": self.fps,
                }},
                {"type": "text", "text": ANALYSIS_PROMPT},
            ]}],
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Qwen API 返回缺少模型内容") from exc
        result = self._parse_json(content)
        result = normalize_qwen_analysis(result)
        if output_path:
            Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    @staticmethod
    def _parse_json(content: Any) -> Dict[str, Any]:
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
        if not isinstance(content, str):
            raise ValueError("Qwen API 未返回结构化 JSON")
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Qwen API 未返回合法的结构化 JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("Qwen API 返回的结构化 JSON 必须是对象")
        return result


def build_qwen_api_analyzer_from_env() -> Optional[QwenApiAnalyzer]:
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return None
    return QwenApiAnalyzer(
        api_key,
        base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
        model=os.getenv("QWEN_MODEL", DEFAULT_MODEL),
        timeout=float(os.getenv("QWEN_API_TIMEOUT", str(DEFAULT_TIMEOUT))),
        fps=float(os.getenv("QWEN_VIDEO_FPS", "1")),
        max_inline_bytes=int(os.getenv("QWEN_MAX_INLINE_BYTES", str(DEFAULT_MAX_INLINE_BYTES))),
    )
