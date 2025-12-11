"""FastAPI entrypoint wiring proxy-related routers.

严格保持路由签名与行为不变，仅做分层与可读性优化。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from core.browser_pool import browser_pool
from routers import health, proxy, raw, reader
from services.cache_service import credential_cache
from utils.logger import log


async def watchdog_task():
    """后台看门狗任务：定期清理空闲浏览器、清理过期缓存"""
    while True:
        await asyncio.sleep(settings.WATCHDOG_INTERVAL)
        try:
            # 1. 清理空闲浏览器
            cleaned = browser_pool.cleanup_idle()
            if cleaned > 0:
                log.info(f"[Watchdog] 回收了 {cleaned} 个空闲浏览器")

            # 2. 记录浏览器池状态
            stats = browser_pool.get_stats()
            log.info(f"[Watchdog] 浏览器池状态: {stats}")

            # 3. 清理过期缓存
            expired = credential_cache.cleanup_expired()
            if expired > 0:
                log.info(f"[Watchdog] 清理了 {expired} 条过期缓存")

        except Exception as e:
            log.error(f"[Watchdog] 任务异常: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    log.info("[Startup] 启动看门狗任务...")
    task = asyncio.create_task(watchdog_task())

    yield

    # 关闭时
    log.info("[Shutdown] 停止看门狗任务...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # 关闭浏览器池
    log.info("[Shutdown] 关闭浏览器池...")
    browser_pool.shutdown()


app = FastAPI(title=settings.API_TITLE, version="2.0.0", lifespan=lifespan)

# Register routers
app.include_router(health.router)
app.include_router(proxy.router)
app.include_router(raw.router)
app.include_router(reader.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
