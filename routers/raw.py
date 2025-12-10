"""Raw binary proxy endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from dependencies import verify_query_key
from services.proxy_service import proxy_request
from utils.logger import log

router = APIRouter()


@router.get("/raw", dependencies=[Depends(verify_query_key)], summary="💾 原始数据代理")
def raw_proxy(url: str) -> Response:
    """直接返回二进制数据，保持原有 header/状态码行为。"""
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
