# 使用 Slim 版本减小体积
FROM python:3.9-slim-bookworm

# 1. 安装 Chrome 和系统依赖 (一步完成减少层数)
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates xvfb \
    fonts-liberation fonts-wqy-zenhei \
    --no-install-recommends \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 创建日志目录
RUN mkdir -p logs

# 4. 复制代码
COPY . .

# 5. 启动
CMD ["python", "main.py"]
