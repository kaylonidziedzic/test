# 1. 使用一个存在的、稳定的版本 (不用纠结这里是不是最新，后面我们会手动修补)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# 2. 解决日志不显示的问题
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 3. 安装 Xvfb 和基础工具
RUN apt-get update && apt-get install -y \
    xvfb \
    x11-xkb-utils \
    xfonts-100dpi xfonts-75dpi xfonts-scalable xfonts-cyrillic \
    && rm -rf /var/lib/apt/lists/*

# 4. 安装 Python 依赖 (这里会安装最新版 Playwright v1.56.0)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# =======================================================
# 【关键修复】强制安装与 Python 库版本匹配的 Chromium
# 这一步会忽略 Docker 镜像自带的老浏览器，下载对应 v1.56.0 的新浏览器
# =======================================================
RUN playwright install chromium

# 5. 补丁文件
RUN mkdir -p /opt/xin/patches
COPY patches/stealth.js /opt/xin/patches/stealth.js

# 6. 代码
COPY main.py .

# 7. 启动
CMD xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" uvicorn main:app --host 0.0.0.0 --port 8000
