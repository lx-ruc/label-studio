#!/bin/bash
# 启动视频文化影像分析系统 Web 服务 (FastAPI + HTML/CSS)

PYTHON_BIN="/home/u20240148/anaconda3/envs/Qwenvl/bin/python"
PORT=8000

echo "============================================"
echo "  视频文化影像分析系统 - Web 服务启动"
echo "============================================"
echo ""

# 检查 python
if [ ! -f "$PYTHON_BIN" ]; then
    echo "[错误] 未找到 Python: $PYTHON_BIN"
    echo "请确认 Qwenvl conda 环境是否存在"
    exit 1
fi

cd "$(dirname "$0")"

echo "[信息] Python: $PYTHON_BIN"
echo "[信息] 端口:   $PORT"
echo "[信息] 访问:   http://localhost:$PORT"
echo ""

exec "$PYTHON_BIN" -m uvicorn web_app:app --host 0.0.0.0 --port "$PORT"
