import re
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 🔧 自动编码需要的库
from urllib.parse import urlparse, quote_from_bytes
import urllib.parse

from config import settings
from services.proxy_service import proxy_request
from utils.logger import log
from dependencies import verify_api_key, verify_query_key

app = FastAPI(title=settings.API_TITLE, version="2.0.0")

# --- 数据模型 ---
class ProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    data: Optional[Dict[str, Any]] = None
    json_body: Optional[Dict[str, Any]] = None

# ==========================================
# ✅ 1. 基础工具：智能解码
# ==========================================
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
        charset_match = re.search(b'charset=["\']?([a-zA-Z0-9\-]+)["\']?', head_content, re.IGNORECASE)
        if charset_match:
            encoding = charset_match.group(1).decode('ascii')
            if encoding.lower() in ['gbk', 'gb2312']:
                encoding = 'gb18030'
            return content.decode(encoding)
    except Exception:
        pass

    # 2. 尝试 chardet 猜测
    if apparent_encoding:
        try:
            return content.decode(apparent_encoding)
        except:
            pass
            
    # 3. 常见编码轮询
    for enc in ['utf-8', 'gb18030', 'big5', 'latin-1']:
        try:
            return content.decode(enc)
        except:
            continue
            
    # 4. 兜底
    return content.decode('utf-8', errors='replace')

# ==========================================
# ✅ 2. 高级工具：生成 HTML 响应 (解码+注入Base)
# ==========================================
def _make_html_response(resp, url: str) -> Response:
    """
    将响应转换为 FastAPI Response 对象：
    1. 调用 decode_response 解码
    2. 注入 Base 标签修复相对路径
    3. 返回 text/html
    """
    # 1. 解码
    apparent_enc = getattr(resp, "apparent_encoding", None)
    html = decode_response(resp.content, apparent_enc)

    # 2. 注入 <base>
    base_tag = f'<base href="{url}">'
    if re.search(r"<head>", html, re.IGNORECASE):
        html = re.sub(r"<head>", f"<head>\n{base_tag}", html, count=1, flags=re.IGNORECASE)
    elif re.search(r"<html>", html, re.IGNORECASE):
        html = re.sub(r"<html>", f"<html>\n{base_tag}", html, count=1, flags=re.IGNORECASE)

    # 3. 返回 UTF-8
    return Response(
        content=html.encode("utf-8"),
        status_code=resp.status_code,
        media_type="text/html; charset=utf-8",
    )

# --- 路由 ---

@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "healthy", "service": settings.API_TITLE}

# =========================
#  1) JSON 模式通用代理接口
# =========================
@app.post("/v1/proxy", dependencies=[Depends(verify_api_key)], summary="⚡ 通用代理 (JSON)")
def proxy_handler(req: ProxyRequest):
    try:
        resp = proxy_request(
            url=req.url,
            method=req.method,
            headers=req.headers,
            data=req.data,
            json=req.json_body,
        )

        # 使用 decode_response 工具
        apparent_enc = getattr(resp, "apparent_encoding", None)
        text = decode_response(resp.content, apparent_enc)

        return JSONResponse(
            content={
                "status": resp.status_code,
                "url": str(resp.url),
                "headers": dict(resp.headers),
                "cookies": resp.cookies.get_dict(),
                "encoding": resp.encoding or "unknown",
                "text": text,
            }
        )
    except Exception as e:
        log.error(f"API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# =========================
#  2) 原始字节代理接口 /raw
# =========================
@app.get("/raw", dependencies=[Depends(verify_query_key)], summary="💾 原始数据代理")
def raw_proxy(url: str):
    """直接返回二进制数据"""
    try:
        resp = proxy_request(url=url, method="GET", headers={})
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("Content-Type", "application/octet-stream"),
        )
    except Exception as e:
        log.error(f"Raw Proxy Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)

# =========================
#  3) 阅读模式接口 (GET)
# =========================
@app.get("/reader", dependencies=[Depends(verify_query_key)], summary="📖 阅读模式 (获取章节)")
def reader_proxy_get(url: str):
    try:
        resp = proxy_request(url=url, method="GET", headers={})
        # ✅ 使用 _make_html_response 统一处理
        return _make_html_response(resp, url)
    except Exception as e:
        log.error(f"Reader GET Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)

# =========================
#  4) 阅读模式接口 (POST) - 通用 POST 代理（不特例任何站点）
# =========================
@app.post("/reader", dependencies=[Depends(verify_query_key)], summary="🔍 搜索模式 (通用 POST 表单)")
async def reader_proxy_post(request: Request, url: str):
    try:
        raw_body = await request.body()
        content_type = request.headers.get("Content-Type", "")

        # ===============================
        # 1) 处理 application/x-www-form-urlencoded
        # ===============================
        if "application/x-www-form-urlencoded" in content_type:
            body_str = raw_body.decode("utf-8", errors="ignore")
            log.info(f"🔍 FORM-urlencoded body: {body_str}")

            resp = proxy_request(
                url=url,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=body_str,   # 🔥 关键：直接透传字符串，不解析、不改动
            )
            return _make_html_response(resp, url)

        # ===============================
        # 2) 处理 multipart/form-data
        # ===============================
        try:
            form_data = dict(await request.form())
            log.info(f"🔍 multipart/form-data body: {form_data}")

            resp = proxy_request(
                url=url,
                method="POST",
                headers={"Content-Type": content_type},
                data=form_data,  # requests 自动编码
            )
            return _make_html_response(resp, url)
        except:
            pass

        # ===============================
        # 3) Fallback：原始 bytes 透传
        # ===============================
        log.info(f"🔍 FALLBACK raw body: {raw_body[:200]}")
        resp = proxy_request(
            url=url,
            method="POST",
            headers={"Content-Type": content_type},
            data=raw_body
        )
        return _make_html_response(resp, url)

    except Exception as e:
        log.error(f"Reader POST Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
