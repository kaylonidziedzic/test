
"""
异步任务队列配置 (Based on ARQ)
"""
from arq.connections import RedisSettings
from config import settings

# ARQ Redis 设置
redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

async def startup(ctx):
    print("ARQ Worker starting...")

async def shutdown(ctx):
    print("ARQ Worker shutting down...")

async def scrape_url_task(ctx, url: str, method: str = "GET", **kwargs):
    """异步采集任务"""
    from services.proxy_service import proxy_request
    from utils.response_builder import decode_response
    import asyncio
    
    print(f"[Job] Starting scrape: {url}")
    try:
        # 在 Worker 进程中执行请求
        # 注意：这里会再次初始化 BrowserPool (如果是 BrowserFetcher)
        # 建议 Worker 显式管理自己的 Pool
        resp = proxy_request(url=url, method=method, **kwargs)
        
        # 序列化结果
        text = resp.text if hasattr(resp, 'text') else decode_response(resp.content, getattr(resp, "apparent_encoding", None))
        return {
            "status": resp.status_code,
            "url": str(resp.url),
            "text_len": len(text),
            "title": text[:100] # 简略
        }
    except Exception as e:
        print(f"[Job] Scrape failed: {e}")
        return {"error": str(e)}

class WorkerSettings:
    """ARQ Worker 配置"""
    functions = [scrape_url_task]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
