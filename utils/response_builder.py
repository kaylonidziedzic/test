"""Utilities for decoding and converting upstream responses for FastAPI handlers."""
from __future__ import annotations

import re
from typing import Optional

from fastapi.responses import Response


def decode_response(content: bytes, apparent_encoding: Optional[str] = None) -> str:
    """
    智能解码函数：
    1. 优先从 HTML meta 标签中提取 charset
    2. 其次尝试 apparent_encoding
    3. 再次尝试 utf-8 / gb18030 等
    """
    # 1. 尝试从 meta 标签提取编码
    try:
        head_content = content[:2000]
        charset_match = re.search(
            b'charset=["\']?([a-zA-Z0-9\-]+)["\']?', head_content, re.IGNORECASE
        )
        if charset_match:
            encoding = charset_match.group(1).decode("ascii")
            if encoding.lower() in ["gbk", "gb2312"]:
                encoding = "gb18030"
            return content.decode(encoding)
    except Exception:
        pass

    # 2. 尝试 chardet 猜测
    if apparent_encoding:
        try:
            return content.decode(apparent_encoding)
        except Exception:
            pass

    # 3. 常见编码轮询
    for enc in ["utf-8", "gb18030", "big5", "latin-1"]:
        try:
            return content.decode(enc)
        except Exception:
            continue

    # 4. 兜底
    return content.decode("utf-8", errors="replace")


def make_html_response(resp, url: str) -> Response:
    """
    将响应转换为 FastAPI Response 对象：
    1. 调用 decode_response 解码
    2. 注入 Base 标签修复相对路径
    3. 返回 text/html
    """
    apparent_enc = getattr(resp, "apparent_encoding", None)
    html = decode_response(resp.content, apparent_enc)

    base_tag = f'<base href="{url}">'
    if re.search(r"<head>", html, re.IGNORECASE):
        html = re.sub(r"<head>", f"<head>\n{base_tag}", html, count=1, flags=re.IGNORECASE)
    elif re.search(r"<html>", html, re.IGNORECASE):
        html = re.sub(r"<html>", f"<html>\n{base_tag}", html, count=1, flags=re.IGNORECASE)

    return Response(
        content=html.encode("utf-8"),
        status_code=resp.status_code,
        media_type="text/html; charset=utf-8",
    )
