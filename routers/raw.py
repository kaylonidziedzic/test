"""Raw binary proxy endpoint."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from dependencies import verify_query_key
from services.proxy_service import proxy_request
from utils.logger import log

router = APIRouter()


@router.get("/raw", dependencies=[Depends(verify_query_key)], summary="💾 原始数据代理")
def raw_proxy(
    url: str,
    fetcher: Optional[str] = Query(None, description="指定 Fetcher: cookie 或 browser")
) -> Response:
    """直接返回二进制数据，保持原有 header/状态码行为。

    Args:
        url: 目标 URL
        fetcher: 可选，指定使用的 Fetcher ("cookie" 或 "browser")
    """
    try:
        resp = proxy_request(url=url, method="GET", headers={}, fetcher=fetcher)

        # 兼容 FetchResponse 和原始 Response 对象
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        if isinstance(content_type, list):
            content_type = content_type[0]

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )
    except Exception as e:
        log.error(f"Raw Proxy Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)
