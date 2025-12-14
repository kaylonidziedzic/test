"""Health check endpoints - 健康检查接口

提供服务健康状态检查，支持 Kubernetes/Docker 健康探测。
"""
from __future__ import annotations

import time
from typing import Dict, Any

from fastapi import APIRouter

from config import settings

router = APIRouter(tags=["Health"])

# 启动时间
_start_time = time.time()


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """基础健康检查：用于外部存活探测 (Liveness Probe)"""
    return {"status": "healthy", "service": settings.API_TITLE}


@router.get("/health/ready")
def readiness_check() -> Dict[str, Any]:
    """就绪检查：检查所有依赖组件状态 (Readiness Probe)

    返回各组件状态：
    - redis: Redis 连接状态
    - browser_pool: 浏览器池状态
    - cache: 凭证缓存状态
    """
    from core.browser_pool import browser_pool
    from services.cache_service import credential_cache

    components = {}
    all_healthy = True

    # 1. 检查 Redis
    try:
        import redis as redis_lib
        redis_client = redis_lib.from_url(settings.REDIS_URL, socket_timeout=2)
        redis_client.ping()
        components["redis"] = {"status": "healthy", "url": settings.REDIS_URL}
    except Exception as e:
        components["redis"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # 2. 检查浏览器池
    try:
        pool_stats = browser_pool.get_stats()
        components["browser_pool"] = {
            "status": "healthy",
            "total": pool_stats.get("total", 0),
            "available": pool_stats.get("available", 0),
            "in_use": pool_stats.get("in_use", 0),
        }
    except Exception as e:
        components["browser_pool"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # 3. 检查缓存
    try:
        cache_stats = credential_cache.get_stats()
        components["cache"] = {
            "status": "healthy",
            "type": cache_stats.get("type", "unknown"),
            "entries": cache_stats.get("valid", 0),
        }
    except Exception as e:
        components["cache"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # 计算运行时间
    uptime = time.time() - _start_time

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.API_TITLE,
        "uptime_seconds": int(uptime),
        "components": components,
    }


@router.get("/health/live")
def liveness_check() -> Dict[str, str]:
    """存活检查：仅检查服务是否响应 (Liveness Probe)

    这是最轻量级的检查，用于 Kubernetes 快速判断 Pod 是否存活。
    """
    return {"status": "alive"}
