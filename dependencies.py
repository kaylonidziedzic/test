"""FastAPI dependencies for header/query API key validation."""

from typing import Optional

from fastapi import HTTPException, Query, Security
from fastapi.security import APIKeyHeader

from config import settings
from utils.logger import log

# 1. Header 鉴权 (给程序/爬虫用)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    依赖注入：用于校验请求头 (Header) 中的 API Key
    """
    # 如果没设置密码，直接放行
    if not settings.API_KEY:
        return True
    
    if api_key != settings.API_KEY:
        log.warning(f"⚠️ Header 鉴权失败，接收到的 Key: {api_key}")
        raise HTTPException(
            status_code=403, 
            detail="Invalid API Key in Header"
        )
    return api_key

# 2. Query 参数鉴权 (给浏览器/阅读APP用)
async def verify_query_key(key: Optional[str] = Query(None)) -> Optional[str]:
    """
    依赖注入：用于校验 URL 参数 (Query) 中的 API Key
    例如: /raw?url=...&key=123456
    """
    # 如果没设置密码，直接放行
    if not settings.API_KEY:
        return True
    
    if key != settings.API_KEY:
        log.warning(f"⚠️ URL 参数鉴权失败，接收到的 Key: {key}")
        raise HTTPException(
            status_code=403, 
            detail="Invalid Key in Query Param"
        )
    return key
