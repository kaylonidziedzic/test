# 1. 更改基础镜像为 Debian 12 (bookworm)，它是目前的稳定版
FROM python:3.9-slim-bookworm

# 2. 安装系统依赖
# 注意：移除了 libappindicator1 和 libindicator7，因为它们在 Debian 12 中已被废弃
# 增加了 ca-certificates 以确保 https 请求正常
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    xvfb \
    fonts-liberation \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-freefont-ttf \
    libxss1 \
    --no-install-recommends

# 3. 安装 Google Chrome (Stable 版)
# Bookworm 下 apt-key 会有警告但依然可用，为了脚本简单保持原样
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# 4. 设置工作目录
WORKDIR /app

# 5. 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 复制源代码
COPY . .

# 7. 运行
CMD ["python", "main.py"]
