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
from services.domain_intelligence import domain_intel
from services import config_store

from utils.logger import log


async def watchdog_task():
    """后台看门狗任务：定期清理空闲浏览器、清理过期缓存、监控内存、自动刷新凭证"""
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

            # 5. 主动刷新即将过期的凭证（5分钟内过期）
            expiring_domains = credential_cache.get_expiring_domains(threshold_seconds=300)
            if expiring_domains:
                log.info(f"[Watchdog] 发现 {len(expiring_domains)} 个即将过期的凭证，开始刷新...")
                for domain in expiring_domains[:3]:  # 每次最多刷新3个，避免阻塞太久
                    success = credential_cache.refresh_credential(domain)
                    if success:
                        log.info(f"[Watchdog] 凭证已提前刷新: {domain}")
                    else:
                        log.warning(f"[Watchdog] 凭证刷新失败: {domain}")

            # 6. 清理过期的域名智能统计
            intel_cleaned = domain_intel.cleanup_expired()
            if intel_cleaned > 0:
                log.info(f"[Watchdog] 清理了 {intel_cleaned} 条过期域名统计")

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


app = FastAPI(
    title=settings.API_TITLE,
    version="2.0.0",
    description="""
## CF-Gateway Pro

**Cloudflare 绕过网关** - 提供高性能的 Cloudflare 保护站点访问能力。

### 主要功能

- 🍪 **Cookie 复用模式**: 浏览器过盾后复用 Cookie，高效访问
- 🌐 **浏览器直读模式**: 实时浏览器渲染，确保成功率
- 🔄 **智能降级**: Cookie 失效自动切换浏览器模式
- 📊 **规则系统**: 可视化配置爬虫规则
- 🔑 **多用户支持**: API Key 鉴权与权限管理

### 快速开始

1. 获取 API Key（联系管理员）
2. 在请求头添加 `X-API-KEY: your_key`
3. 调用 `/v1/proxy` 接口代理请求

### API 分类

- **Health**: 健康检查接口
- **Proxy**: 代理请求接口（返回 JSON）
- **Raw**: 原始响应接口（返回原始内容）
- **Reader**: 阅读模式接口（返回处理后的 HTML）
- **Runner**: 规则执行接口（Permlink）
- **Dashboard**: 管理面板 API
""",
    openapi_tags=[
        {"name": "Health", "description": "健康检查接口，用于监控和探测"},
        {"name": "Proxy", "description": "代理请求接口，返回 JSON 格式响应"},
        {"name": "Raw", "description": "原始响应接口，返回目标站点原始内容"},
        {"name": "Reader", "description": "阅读模式接口，返回处理后的 HTML"},
        {"name": "Runner", "description": "规则执行接口，通过 Permlink 执行预定义规则"},
        {"name": "Dashboard", "description": "管理面板 API，需要管理员权限"},
    ],
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

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
