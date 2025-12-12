"""FastAPI dependencies for header/query API key validation."""

from typing import Optional

from fastapi import HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader

from config import settings
from services.api_key_store import find_user_by_key, get_all_entries
from utils.logger import log, set_user

# 1. Header 鉴权 (给程序/爬虫用)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def verify_api_key(request: Request, api_key: str = Security(api_key_header)) -> dict:
    """
    依赖注入：用于校验请求头 (Header) 中的 API Key，返回用户信息。
    """
    # 如果没设置密码，直接放行
    if not settings.API_KEY and not get_all_entries():
        return {"user": "anonymous", "role": "user"}

    entry = find_user_by_key(api_key or "")
    if not entry:
        log.warning(f"⚠️ Header 鉴权失败，接收到的 Key: {api_key}")
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key in Header"
        )
    request.state.api_user = entry
    set_user(entry.get("user"))
    return entry


# 2. Query 参数鉴权 (给浏览器/阅读APP用)
async def verify_query_key(request: Request, key: Optional[str] = Query(None)) -> Optional[dict]:
    """
    依赖注入：用于校验 URL 参数 (Query) 中的 API Key
    例如: /raw?url=...&key=123456
    """
    if not settings.API_KEY and not get_all_entries():
        return {"user": "anonymous", "role": "user"}

    entry = find_user_by_key(key or "")
    if not entry:
        log.warning(f"⚠️ URL 参数鉴权失败，接收到的 Key: {key}")
        raise HTTPException(
            status_code=403,
            detail="Invalid Key in Query Param"
        )
    request.state.api_user = entry
    set_user(entry.get("user"))
    return entry


async def verify_admin(request: Request, api_key: str = Security(api_key_header)) -> dict:
    """仅管理员可用的依赖"""
    user = await verify_api_key(request, api_key)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="管理员权限不足")
    return user


async def verify_admin_flexible(
    request: Request,
    api_key: str = Security(api_key_header),
    key: Optional[str] = Query(None),
) -> dict:
    """
    兼容 Header 和 Query 的管理员校验（用于 SSE 等无法自定义 Header 的场景）
    """
    candidate = api_key or key
    if not candidate:
        raise HTTPException(status_code=401, detail="缺少 API Key")

    entry = find_user_by_key(candidate)
    if not entry:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    if entry.get("role") != "admin":
        raise HTTPException(status_code=403, detail="管理员权限不足")
    request.state.api_user = entry
    set_user(entry.get("user"))
    return entry
