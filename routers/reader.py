"""Reader-oriented proxy endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from dependencies import verify_query_key
from services.proxy_service import proxy_request
from utils.logger import log
from utils.response_builder import make_html_response

router = APIRouter()


@router.get("/reader", dependencies=[Depends(verify_query_key)], summary="📖 阅读模式 (获取章节)")
def reader_proxy_get(url: str) -> Response:
    """GET 阅读模式：保持原有 HTML 注入与返回格式。"""
    try:
        resp = proxy_request(url=url, method="GET", headers={})
        return make_html_response(resp, url)
    except Exception as e:
        log.error(f"Reader GET Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)


@router.post(
    "/reader", dependencies=[Depends(verify_query_key)], summary="🔍 搜索模式 (通用 POST 表单)"
)
async def reader_proxy_post(request: Request, url: str) -> Response:
    """POST 阅读模式：分支与回退逻辑保持不变，增加类型标注。"""
    try:
        raw_body = await request.body()
        content_type = request.headers.get("Content-Type", "")

        if "application/x-www-form-urlencoded" in content_type:
            body_str = raw_body.decode("utf-8", errors="ignore")
            log.info(f"🔍 FORM-urlencoded body: {body_str}")

            resp = proxy_request(
                url=url,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=body_str,
            )
            return make_html_response(resp, url)

        try:
            form_data = dict(await request.form())
            log.info(f"🔍 multipart/form-data body: {form_data}")

            resp = proxy_request(
                url=url,
                method="POST",
                headers={"Content-Type": content_type},
                data=form_data,
            )
            return make_html_response(resp, url)
        except Exception:
            pass

        log.info(f"🔍 FALLBACK raw body: {raw_body[:200]}")
        resp = proxy_request(
            url=url,
            method="POST",
            headers={"Content-Type": content_type},
            data=raw_body,
        )
        return make_html_response(resp, url)

    except Exception as e:
        log.error(f"Reader POST Error: {str(e)}")
        return Response(content=f"Error: {str(e)}", status_code=500)
