"""Label Studio 预标注接口的无模型回归测试。"""
import sys
import threading
import types
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

import label_studio_adapter as adapter


@pytest.fixture
def client(monkeypatch):
    fake_model = types.ModuleType("video_analysis_demo")
    fake_model.VideoAnalysisDemo = type("VideoAnalysisDemo", (), {})
    monkeypatch.setitem(sys.modules, "video_analysis_demo", fake_model)
    sys.modules.pop("web_app", None)
    import web_app

    monkeypatch.setattr(web_app, "analyzer", None)
    monkeypatch.setitem(web_app.model_state, "status", "idle")
    with TestClient(web_app.app) as test_client:
        yield test_client, web_app
    sys.modules.pop("web_app", None)


def test_api_only_server_imports_without_local_model_dependencies(monkeypatch):
    import importlib
    import builtins
    original_import = builtins.__import__

    def reject_local_model(name, *args, **kwargs):
        if name == "video_analysis_demo":
            raise ImportError("local model dependencies unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_local_model)
    sys.modules.pop("web_app", None)
    import web_app
    assert web_app.app is not None
    sys.modules.pop("web_app", None)


def test_setup_returns_model_version_and_checks_label_config(client):
    http, _ = client
    config = Path(__file__).with_name("label_studio_config.xml").read_text(encoding="utf-8")
    response = http.post("/setup", json={"project": "1", "schema": config})
    assert response.status_code == 200
    assert response.json()["model_version"] == adapter.MODEL_VERSION
    response = http.post("/setup", json={"project": "1", "schema": '<View><Video name="other" value="$video" /></View>'})
    assert response.status_code == 400


def test_setup_rejects_missing_prediction_control(client):
    http, _ = client
    response = http.post("/setup", json={"project": "1", "schema": '<View><Video name="video" value="$video" /></View>'})
    assert response.status_code == 400


def test_setup_rejects_misconfigured_control(client):
    http, _ = client
    config = Path(__file__).with_name("label_studio_config.xml").read_text(encoding="utf-8")
    config = config.replace('name="heritage_type" toName="video"', 'name="heritage_type" toName="other"')
    response = http.post("/setup", json={"schema": config})
    assert response.status_code == 400


def test_predict_runs_outside_event_loop(client, tmp_path, monkeypatch):
    http, web_app = client
    video = tmp_path / "input.mp4"
    video.write_bytes(b"test video")
    monkeypatch.setenv("LABEL_STUDIO_VIDEO_ROOT", str(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    class FakeAnalyzer:
        def analyze_video(self, video_path, output_path=None):
            entered.set()
            assert release.wait(3)
            return {"模块三_非遗文化信息": {"类型": ["传统技艺"]}}

    monkeypatch.setattr(web_app, "analyzer", FakeAnalyzer())
    with ThreadPoolExecutor(max_workers=1) as pool:
        prediction = pool.submit(http.post, "/predict", json={"tasks": [{"data": {"video": str(video)}}]})
        try:
            assert entered.wait(3)
            assert http.get("/health").status_code == 200
        finally:
            release.set()
        assert prediction.result(timeout=3).status_code == 200


def test_web_analysis_waits_for_prediction_lock(client, tmp_path, monkeypatch):
    _, web_app = client
    monkeypatch.setattr(web_app, "UPLOAD_DIR", tmp_path)
    entered = threading.Event()

    class FakeAnalyzer:
        def analyze_video(self, video_path, output_path=None):
            entered.set()
            return {"模块三_非遗文化信息": {"类型": ["传统技艺"]}}

    monkeypatch.setattr(web_app, "analyzer", FakeAnalyzer())
    video = tmp_path / "input.mp4"
    video.write_bytes(b"test video")
    with web_app.label_studio_predict_lock:
        thread = threading.Thread(target=web_app._analyze_thread, args=(str(video), "input.mp4"))
        thread.start()
        assert not entered.wait(0.1)
    thread.join(timeout=3)
    assert entered.is_set()
    assert web_app.analysis_state["status"] == "done"


def test_analyze_reserves_running_state_before_thread_starts(client, monkeypatch):
    http, web_app = client
    pending = []

    class DelayedThread:
        def __init__(self, target, args, daemon):
            pending.append((target, args))

        def start(self):
            pass

    monkeypatch.setattr(web_app.threading, "Thread", DelayedThread)
    monkeypatch.setattr(web_app, "analyzer", object())
    monkeypatch.setitem(web_app.model_state, "status", "ready")
    first = http.post("/api/analyze", files={"video": ("one.mp4", b"video", "video/mp4")})
    second = http.post("/api/analyze", files={"video": ("two.mp4", b"video", "video/mp4")})
    assert first.status_code == 200
    assert second.status_code == 409
    assert web_app.analysis_state["status"] == "running"
    assert len(pending) == 1
    Path(pending[0][1][0]).unlink()


def test_analyze_rejects_upload_above_limit(client, monkeypatch, tmp_path):
    http, web_app = client
    monkeypatch.setattr(web_app, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(web_app, "MAX_VIDEO_BYTES", 4, raising=False)
    monkeypatch.setattr(web_app, "analyzer", object())
    monkeypatch.setitem(web_app.model_state, "status", "ready")
    response = http.post("/api/analyze", files={"video": ("huge.mp4", b"12345", "video/mp4")})
    assert response.status_code == 413
    assert web_app.analysis_state["status"] != "running"
    assert list(tmp_path.iterdir()) == []


def test_model_loading_uses_qwen_api_when_key_is_configured(client, monkeypatch):
    _, web_app = client
    fake_analyzer = object()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "configured-but-not-printed")
    monkeypatch.setattr(web_app, "build_qwen_api_analyzer_from_env", lambda: fake_analyzer)
    web_app._load_model_thread("ignored-local-model", None)
    assert web_app.analyzer is fake_analyzer
    assert web_app.model_state["status"] == "ready"
    assert web_app.model_state["model_path"].startswith("qwen-api:") is False


def test_predict_can_use_qwen_api_analyzer(client, tmp_path, monkeypatch):
    http, web_app = client
    video = tmp_path / "input.mp4"
    video.write_bytes(b"test video")
    monkeypatch.setenv("LABEL_STUDIO_VIDEO_ROOT", str(tmp_path))

    class QwenAnalyzer:
        def analyze_video(self, video_path, output_path=None):
            return {"模块三_非遗文化信息": {"类型": ["传统技艺"]},
                    "模块四_影像技术与风格分析": {"声音内容分析": {"是否有旁白": None}},
                    "模块五_人物与社会关系结构": {}, "模块六_叙事与语义层级分析": {}}

    monkeypatch.setattr(web_app, "analyzer", QwenAnalyzer())
    response = http.post("/predict", json={"tasks": [{"data": {"video": str(video)}}]})
    assert response.status_code == 200
    assert response.json()["results"][0]["result"][0]["value"] == {"choices": ["传统技艺"]}


def test_predict_uses_fake_analyzer_and_returns_valid_results(client, tmp_path, monkeypatch):
    http, web_app = client
    video = tmp_path / "input.mp4"
    video.write_bytes(b"test video")
    monkeypatch.setenv("LABEL_STUDIO_VIDEO_ROOT", str(tmp_path))

    class FakeAnalyzer:
        def analyze_video(self, video_path, output_path=None):
            assert video_path == str(video)
            return {
                "模块三_非遗文化信息": {"类型": ["传统技艺"], "社会文化语境与场域": {"城乡场景": "家庭空间"}},
                "模块四_影像技术与风格分析": {"声音内容分析": {"是否有旁白": False}},
                "模块五_人物与社会关系结构": {},
                "模块六_叙事与语义层级分析": {},
            }

    monkeypatch.setattr(web_app, "analyzer", FakeAnalyzer())
    response = http.post("/predict", json={"tasks": [{"id": 1, "data": {"video": str(video)}}], "project": "1"})
    assert response.status_code == 200
    predictions = response.json()["results"]
    assert len(predictions) == 1
    assert predictions[0]["model_version"] == adapter.MODEL_VERSION
    values = {r["from_name"]: r["value"]["choices"] for r in predictions[0]["result"] if r["type"] == "choices"}
    assert values == {"heritage_type": ["传统技艺"], "urban_rural_scene": ["家庭空间"], "has_narration": ["无旁白"]}


def test_predict_rejects_missing_model(client):
    http, _ = client
    assert http.post("/predict", json={"tasks": [{"data": {"video": "https://example.com/a.mp4"}}]}).status_code == 503


@pytest.mark.parametrize("analysis", [{}, {"class": "传统技艺"}, {"error": "解析失败"},
                                      {"模块三_非遗文化信息": {"物质文化元素": {}}}])
def test_invalid_analysis_is_not_reported_as_success(analysis):
    with pytest.raises(ValueError, match="结构化结果"):
        adapter.analysis_to_results(analysis)


def test_predict_rejects_invalid_analysis(client, tmp_path, monkeypatch):
    http, web_app = client
    video = tmp_path / "input.mp4"
    video.write_bytes(b"test video")
    monkeypatch.setenv("LABEL_STUDIO_VIDEO_ROOT", str(tmp_path))

    class FakeAnalyzer:
        def analyze_video(self, video_path, output_path=None):
            return {"class": "传统技艺"}

    monkeypatch.setattr(web_app, "analyzer", FakeAnalyzer())
    response = http.post("/predict", json={"tasks": [{"data": {"video": str(video)}}]})
    assert response.status_code == 400
    assert "结构化结果" in response.json()["detail"]


def test_prediction_choices_are_defined_in_label_config():
    tree = ET.parse(Path(__file__).with_name("label_studio_config.xml"))
    declared = {element.attrib["name"]: {choice.attrib["value"] for choice in element.findall("Choice")}
                for element in tree.findall(".//Choices")}
    for name, allowed in {
        "heritage_type": adapter.HERITAGE_TYPES,
        "urban_rural_scene": adapter.URBAN_RURAL_SCENES,
        "usage_context": adapter.USAGE_CONTEXTS,
        "audience_type": adapter.AUDIENCE_TYPES,
        "camera_movement": adapter.CAMERA_MOVEMENTS,
        "narrative_structure": adapter.NARRATIVE_STRUCTURES,
        "has_narration": {"有旁白", "无旁白", "无法确定"},
    }.items():
        assert allowed <= declared[name], name


def test_external_video_does_not_receive_label_studio_token(monkeypatch):
    monkeypatch.setenv("LABEL_STUDIO_API_KEY", "secret")
    monkeypatch.setenv("LABEL_STUDIO_URL", "https://studio.example.com")
    monkeypatch.setattr(adapter, "_public_address", lambda host: "93.184.215.14")

    def fake_open(request, timeout):
        assert request.get_header("Authorization") is None
        raise HTTPError(request.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(adapter, "_open_video", fake_open)
    with pytest.raises(HTTPError):
        adapter.materialize_video("https://example.com/video.mp4")


def test_local_files_uses_configured_studio_token(monkeypatch):
    monkeypatch.setenv("LABEL_STUDIO_API_KEY", "secret")
    monkeypatch.setenv("LABEL_STUDIO_URL", "https://studio.example.com")
    monkeypatch.setattr(adapter, "_public_address", lambda host: "93.184.215.14")

    def fake_open(request, timeout):
        assert request.full_url == "https://studio.example.com/data/local-files/?d=video.mp4"
        assert request.get_header("Authorization") == "Token secret"
        raise HTTPError(request.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(adapter, "_open_video", fake_open)
    with pytest.raises(HTTPError):
        adapter.materialize_video("/data/local-files/?d=video.mp4")


def test_local_files_rejects_plain_http_when_sending_token(monkeypatch):
    monkeypatch.setenv("LABEL_STUDIO_API_KEY", "secret")
    monkeypatch.setenv("LABEL_STUDIO_URL", "http://studio.example.com")
    monkeypatch.setattr(adapter, "_public_address", lambda host: "93.184.215.14")
    with pytest.raises(ValueError, match="HTTPS"):
        adapter.materialize_video("/data/local-files/?d=video.mp4")


def test_public_video_connection_uses_prevalidated_address(monkeypatch):
    import socket
    resolutions = []
    original_lookup = adapter.socket.getaddrinfo

    def fake_lookup(host, port, *args, **kwargs):
        if host == "video.example.com":
            resolutions.append(host)
            address = "93.184.215.14" if len(resolutions) == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]
        return original_lookup(host, port, *args, **kwargs)

    monkeypatch.setattr(adapter.socket, "getaddrinfo", fake_lookup)
    created = []
    def fake_connect(address, timeout=None, source_address=None):
        created.append(address)
        raise OSError("stop before network")
    monkeypatch.setattr(adapter.socket, "create_connection", fake_connect)
    with pytest.raises(OSError):
        adapter.materialize_video("https://video.example.com/video.mp4")
    assert resolutions == ["video.example.com"]
    assert created[0][0] == "93.184.215.14"


def test_public_video_download_ignores_environment_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setattr(adapter, "_public_address", lambda host: "93.184.215.14")
    created = []
    def fake_connect(address, timeout=None, source_address=None):
        created.append(address)
        raise OSError("stop before network")
    monkeypatch.setattr(adapter.socket, "create_connection", fake_connect)
    with pytest.raises(OSError):
        adapter.materialize_video("https://video.example.com/video.mp4")
    assert created[0][0] == "93.184.215.14"


def test_remote_video_redirect_is_rejected(monkeypatch):
    def fake_open(request, timeout):
        raise HTTPError(request.full_url, 302, "redirect", {"Location": "http://127.0.0.1/secret"}, None)

    monkeypatch.setattr(adapter, "_open_video", fake_open)
    with pytest.raises(ValueError, match="重定向"):
        adapter.materialize_video("https://example.com/video.mp4")
