from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from config import settings
from utils.logger import log

# 定义 API Key 的 Header 名字，比如 X-API-KEY: my-secret-key
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    依赖注入函数：用于校验请求头中的 API Key
    """
    # 如果配置文件里没有设置密码，默认允许所有访问（开发模式）
    if not settings.API_KEY:
        return True
    
    if api_key != settings.API_KEY:
        log.warning(f"⚠️ 鉴权失败，接收到的 Key: {api_key}")
        raise HTTPException(
            status_code=403, 
            detail="Could not validate credentials"
        )
    return api_key
