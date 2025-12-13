"""Proxy-related HTTP endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from dependencies import verify_api_key
from schemas.proxy import ProxyRequest
from services.proxy_service import proxy_request
from utils.logger import log
from utils.response_builder import decode_response

router = APIRouter()


@router.post(
    "/v1/proxy",
    dependencies=[Depends(verify_api_key)],
    summary="⚡ 通用代理 (JSON)",
)
def proxy_handler(req: ProxyRequest) -> JSONResponse:
    """通用 JSON 代理端点，保持请求/响应结构不变。"""
    try:
        resp = proxy_request(
            url=req.url,
            method=req.method,
            headers=req.headers,
            data=req.data,
            json=req.json_body,
            data_encoding=req.data_encoding,
            proxy=req.proxy,
        )

        # 兼容 FetchResponse 和原始 Response 对象
        text = resp.text if hasattr(resp, 'text') else decode_response(resp.content, getattr(resp, "apparent_encoding", None))
        cookies = resp.cookies if isinstance(resp.cookies, dict) else (resp.cookies.get_dict() if hasattr(resp.cookies, 'get_dict') else dict(resp.cookies))

        return JSONResponse(
            content={
                "status": resp.status_code,
                "url": str(resp.url),
                "headers": dict(resp.headers),
                "cookies": cookies,
                "encoding": resp.encoding or "unknown",
                "text": text,
            }
        )
    except Exception as e:
        log.error(f"API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
