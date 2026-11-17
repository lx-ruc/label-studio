#!/bin/bash

# 启动Streamlit视频分析应用

echo "🚀 启动视频文化影像分析系统..."
echo ""

# 检查streamlit是否安装
if ! command -v streamlit &> /dev/null
then
    echo "❌ Streamlit未安装，正在安装..."
    pip install streamlit
fi

# 启动应用
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0


