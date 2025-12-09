from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from config import settings
from services.proxy_service import proxy_request
from utils.logger import log

app = FastAPI(title=settings.API_TITLE, version="2.0.0")

# --- 鉴权模块 ---
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    # 如果 settings.API_KEY 设置为空，则不鉴权
    if not settings.API_KEY:
        return True
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

# --- 数据模型 ---
class ProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    data: Optional[Dict[str, Any]] = None
    json_body: Optional[Dict[str, Any]] = None

# --- 路由 ---

@app.get("/health")
def health_check():
    """健康检查，K8s/Docker用"""
    return {"status": "healthy", "service": settings.API_TITLE}

@app.post("/v1/proxy", dependencies=[Depends(verify_api_key)])
def proxy_handler(req: ProxyRequest):
    """
    通用代理接口
    外部程序调用此接口，无需关心 CF 盾，直接拿回结果
    """
    try:
        # 调用服务层
        resp = proxy_request(
            url=req.url, 
            method=req.method, 
            headers=req.headers, 
            data=req.data, 
            json=req.json_body
        )
        
        # 返回结果 (透传)
        # 注意：这里我们返回 JSON 结构以便下游处理
        return JSONResponse(content={
            "status": resp.status_code,
            "url": resp.url,
            "headers": dict(resp.headers),
            "cookies": resp.cookies.get_dict(),
            "text": resp.text
        })
    except Exception as e:
        log.error(f"API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
