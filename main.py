"""FastAPI entrypoint wiring proxy-related routers.

严格保持路由签名与行为不变，仅做分层与可读性优化。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import settings
from core.browser_pool import browser_pool
from routers import dashboard, health, proxy, raw, reader, job, runner
from services.cache_service import credential_cache
from services import config_store

from utils.logger import log


async def watchdog_task():
    """后台看门狗任务：定期清理空闲浏览器、清理过期缓存、监控内存"""
    while True:
        await asyncio.sleep(settings.WATCHDOG_INTERVAL)
        try:
            # 1. 清理空闲浏览器
            cleaned = browser_pool.cleanup_idle()
            if cleaned > 0:
                log.info(f"[Watchdog] 回收了 {cleaned} 个空闲浏览器")

            # 2. 内存监控：重启内存超限的浏览器
            mem_usage = browser_pool.get_memory_usage_mb()
            if mem_usage > 0:
                log.info(f"[Watchdog] 浏览器总内存: {mem_usage:.1f}MB")
                if mem_usage > settings.MEMORY_LIMIT_MB:
                    restarted = browser_pool.restart_high_memory_browsers(
                        settings.MEMORY_LIMIT_MB / settings.BROWSER_POOL_MAX
                    )
                    if restarted > 0:
                        log.warning(f"[Watchdog] 重启了 {restarted} 个内存超限浏览器")

            # 3. 记录浏览器池状态
            stats = browser_pool.get_stats()
            log.info(f"[Watchdog] 浏览器池状态: {stats}")

            # 4. 清理过期缓存
            expired = credential_cache.cleanup_expired()
            if expired > 0:
                log.info(f"[Watchdog] 清理了 {expired} 条过期缓存")

        except Exception as e:
            log.error(f"[Watchdog] 任务异常: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：加载持久化配置
    log.info("[Startup] 加载持久化配置...")
    config_store.init_config()

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
app.include_router(job.router)
app.include_router(runner.router)
app.include_router(dashboard.router)


# 静态文件和 Dashboard 入口
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/dashboard")
async def dashboard_page():
    """Dashboard 管理面板入口"""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
