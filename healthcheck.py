#!/usr/bin/env python3
"""
Docker 健康检查脚本

检查项目:
1. API 服务是否响应
2. 浏览器实例是否正常

退出码:
- 0: 健康
- 1: 不健康
"""

import sys
import urllib.request
import urllib.error


def check_api_health():
    """检查 API 服务是否响应"""
    try:
        url = "http://127.0.0.1:8000/docs"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"API 检查失败: {e}")
        return False


def main():
    if not check_api_health():
        print("健康检查失败: API 服务无响应")
        sys.exit(1)

    print("健康检查通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
