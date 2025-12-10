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
        )

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
