"""Qwen API analyzer regression tests; all network calls stay mocked."""
import base64
import json
from pathlib import Path

import pytest

from qwen_api_analyzer import QwenApiAnalyzer


def test_analyzer_sends_video_data_uri_and_parses_structured_json(tmp_path, monkeypatch):
    video = tmp_path / "tiny.mp4"
    video.write_bytes(b"fake-video")
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "模块三_非遗文化信息": {"类型": ["传统技艺"]},
                "模块四_影像技术与风格分析": {"声音内容分析": {"是否有旁白": None}},
                "模块五_人物与社会关系结构": {},
                "模块六_叙事与语义层级分析": {},
            }, ensure_ascii=False)}}]}

    def post(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)
        return Response()

    monkeypatch.setattr("qwen_api_analyzer.requests.post", post)
    result = QwenApiAnalyzer(api_key="test-key", max_inline_bytes=100).analyze_video(str(video))
    assert result["模块三_非遗文化信息"]["类型"] == ["传统技艺"]
    assert captured["url"].endswith("/chat/completions")
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-key"
    content = captured["kwargs"]["json"]["messages"][0]["content"]
    video_block = next(item for item in content if item["type"] == "video_url")
    assert video_block["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert base64.b64encode(b"fake-video").decode() in video_block["video_url"]["url"]


def test_analyzer_rejects_non_structured_response(tmp_path, monkeypatch):
    video = tmp_path / "tiny.mp4"
    video.write_bytes(b"fake-video")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    monkeypatch.setattr("qwen_api_analyzer.requests.post", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="结构化 JSON"):
        QwenApiAnalyzer(api_key="test-key").analyze_video(str(video))


def test_analyzer_rejects_oversized_local_video(tmp_path):
    video = tmp_path / "large.mp4"
    video.write_bytes(b"12345")
    with pytest.raises(ValueError, match="超过"):
        QwenApiAnalyzer(api_key="test-key", max_inline_bytes=4).analyze_video(str(video))


def test_analyzer_does_not_log_or_return_api_key(tmp_path, monkeypatch):
    video = tmp_path / "tiny.mp4"
    video.write_bytes(b"fake-video")
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "模块三_非遗文化信息": {"类型": ["传统技艺"]},
                "模块四_影像技术与风格分析": {},
                "模块五_人物与社会关系结构": {},
                "模块六_叙事与语义层级分析": {},
            }, ensure_ascii=False)}}]}

    def post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("qwen_api_analyzer.requests.post", post)
    result = QwenApiAnalyzer(api_key="secret-key").analyze_video(str(video))
    assert "secret-key" not in repr(captured.get("data"))
