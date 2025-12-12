"""Dashboard API - 管理面板后端接口"""

import asyncio
import json
import os
import time
import psutil
from collections import deque
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import settings
from core.browser_pool import browser_pool
from dependencies import verify_admin_flexible, verify_api_key, verify_query_key, verify_admin
from services import api_key_store
from services.cache_service import credential_cache
from utils.logger import log

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"], dependencies=[Depends(verify_admin_flexible)])

# 启动时间
_start_time = time.time()

# 请求统计
_request_stats = {
    "total": 0,
    "success": 0,
    "failed": 0,
    "total_time": 0.0,
}

# 请求历史（最近100条）
_request_history: deque = deque(maxlen=100)

# 时间序列数据（用于图表，最近60个点）
_time_series: deque = deque(maxlen=60)


def record_request(url: str, success: bool, duration: float, user: str = "anonymous", error: str = None):
    """记录请求统计（按用户标记）"""
    _request_stats["total"] += 1
    if success:
        _request_stats["success"] += 1
    else:
        _request_stats["failed"] += 1
    _request_stats["total_time"] += duration

    # 添加到历史记录
    _request_history.appendleft({
        "id": _request_stats["total"],
        "url": url,
        "success": success,
        "duration_ms": round(duration * 1000, 2),
        "error": error,
        "user": user,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


def update_time_series():
    """更新时间序列数据"""
    now = time.strftime("%H:%M:%S")
    success_rate = (_request_stats["success"] / _request_stats["total"] * 100) if _request_stats["total"] > 0 else 0
    avg_time = (_request_stats["total_time"] / _request_stats["total"] * 1000) if _request_stats["total"] > 0 else 0

    _time_series.append({
        "time": now,
        "requests": _request_stats["total"],
        "success_rate": round(success_rate, 1),
        "avg_time": round(avg_time, 0),
    })


# ========== 状态监控 API ==========

def _status_payload(user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    uptime = time.time() - _start_time
    return {
        "status": "running",
        "uptime_seconds": int(uptime),
        "uptime_human": _format_uptime(uptime),
        "version": "4.1.0",
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_start_time)),
        **({"current_user": user} if user else {}),
    }


@router.get("/status", dependencies=[Depends(verify_api_key)])
def get_status(request: Request) -> Dict[str, Any]:
    """获取服务状态"""
    user = getattr(request.state, "api_user", {"user": "unknown", "role": "user"})
    return _status_payload(user)


@router.get("/system", dependencies=[Depends(verify_api_key)])
def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(),
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent": memory.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": round(disk.percent, 1),
        },
    }


@router.get("/stats", dependencies=[Depends(verify_api_key)])
def get_stats() -> Dict[str, Any]:
    """获取综合统计信息"""
    browser_stats = browser_pool.get_stats()
    cache_stats = credential_cache.get_stats()

    avg_time = (_request_stats["total_time"] / _request_stats["total"]) if _request_stats["total"] > 0 else 0
    success_rate = (_request_stats["success"] / _request_stats["total"] * 100) if _request_stats["total"] > 0 else 0

    return {
        "browser_pool": browser_stats,
        "cache": cache_stats,
        "requests": {
            "total": _request_stats["total"],
            "success": _request_stats["success"],
            "failed": _request_stats["failed"],
            "success_rate": round(success_rate, 2),
            "avg_time_ms": round(avg_time * 1000, 2),
        },
    }


@router.get("/time-series", dependencies=[Depends(verify_api_key)])
def get_time_series() -> List[Dict]:
    """获取时间序列数据（用于图表）"""
    update_time_series()
    return list(_time_series)


@router.get("/history", dependencies=[Depends(verify_api_key)])
def get_request_history(limit: int = 20, user: Optional[str] = None) -> List[Dict]:
    """获取请求历史，可按用户过滤"""
    records = list(_request_history)
    if user:
        records = [r for r in records if r.get("user") == user]
    return records[:limit]


@router.get("/browser-pool", dependencies=[Depends(verify_api_key)])
def get_browser_pool_status() -> Dict[str, Any]:
    """获取浏览器池详细状态"""
    stats = browser_pool.get_stats()

    # 获取每个实例的详细信息
    instances = []
    for i, inst in enumerate(browser_pool._all_instances):
        instances.append({
            "id": i + 1,
            "pid": inst.pid,
            "in_use": inst.in_use,
            "use_count": inst.use_count,
            "created_at": time.strftime("%H:%M:%S", time.localtime(inst.created_at)),
            "last_used": time.strftime("%H:%M:%S", time.localtime(inst.last_used_at)),
        })

    return {
        **stats,
        "instances": instances,
    }


@router.get("/cache", dependencies=[Depends(verify_api_key)])
def get_cache_status() -> Dict[str, Any]:
    """获取缓存详细状态"""
    return credential_cache.get_stats()


# ========== 配置管理 API ==========

class ConfigUpdate(BaseModel):
    cookie_expire_seconds: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    watchdog_interval: Optional[int] = None
    fingerprint_enabled: Optional[bool] = None
    browser_pool_min: Optional[int] = None
    browser_pool_max: Optional[int] = None
    browser_pool_idle_timeout: Optional[int] = None


@router.get("/config", dependencies=[Depends(verify_api_key)])
def get_config() -> Dict[str, Any]:
    """获取当前配置（扁平结构，匹配前端期望）"""
    return {
        "cookie_expire_seconds": settings.COOKIE_EXPIRE_SECONDS,
        "memory_limit_mb": settings.MEMORY_LIMIT_MB,
        "watchdog_interval": settings.WATCHDOG_INTERVAL,
        "fingerprint_enabled": settings.FINGERPRINT_ENABLED,
        "browser_pool_min": settings.BROWSER_POOL_MIN,
        "browser_pool_max": settings.BROWSER_POOL_MAX,
        "browser_pool_idle_timeout": settings.BROWSER_POOL_IDLE_TIMEOUT,
    }


@router.put("/config", dependencies=[Depends(verify_api_key)])
def update_config(config: ConfigUpdate) -> Dict[str, Any]:
    """更新配置（运行时生效，重启后恢复默认）"""
    updated = {}

    if config.cookie_expire_seconds is not None:
        settings.COOKIE_EXPIRE_SECONDS = config.cookie_expire_seconds
        credential_cache.expire_seconds = config.cookie_expire_seconds
        updated["cookie_expire_seconds"] = config.cookie_expire_seconds

    if config.memory_limit_mb is not None:
        settings.MEMORY_LIMIT_MB = config.memory_limit_mb
        updated["memory_limit_mb"] = config.memory_limit_mb

    if config.watchdog_interval is not None:
        settings.WATCHDOG_INTERVAL = config.watchdog_interval
        updated["watchdog_interval"] = config.watchdog_interval

    if config.fingerprint_enabled is not None:
        settings.FINGERPRINT_ENABLED = config.fingerprint_enabled
        updated["fingerprint_enabled"] = config.fingerprint_enabled

    if config.browser_pool_min is not None:
        settings.BROWSER_POOL_MIN = config.browser_pool_min
        browser_pool.min_size = config.browser_pool_min
        updated["browser_pool_min"] = config.browser_pool_min

    if config.browser_pool_max is not None:
        settings.BROWSER_POOL_MAX = config.browser_pool_max
        browser_pool.max_size = config.browser_pool_max
        updated["browser_pool_max"] = config.browser_pool_max

    if config.browser_pool_idle_timeout is not None:
        settings.BROWSER_POOL_IDLE_TIMEOUT = config.browser_pool_idle_timeout
        browser_pool.idle_timeout = config.browser_pool_idle_timeout
        updated["browser_pool_idle_timeout"] = config.browser_pool_idle_timeout

    log.info(f"[Dashboard] 配置已更新: {updated}")
    return {"message": "配置已更新", "updated": updated}


@router.get("/config/export", dependencies=[Depends(verify_api_key)])
def export_config() -> Dict[str, Any]:
    """导出配置"""
    return get_config()


# ========== 操作 API ==========

@router.get("/logs", dependencies=[Depends(verify_api_key)])
def get_logs(limit: int = 100, user: Optional[str] = None) -> Dict[str, List[Dict]]:
    """获取实时日志，返回全局与用户分桶，便于前端分栏展示"""
    import os
    log_file = "logs/server.log"

    if not os.path.exists(log_file):
        return {"all": [], "user": []}

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        recent_lines = lines[-limit:] if len(lines) > limit else lines
        all_logs = _parse_log_lines(recent_lines, None)
        user_logs = _parse_log_lines(recent_lines, user) if user else []

        return {"all": all_logs, "user": user_logs}
    except Exception as e:
        log.error(f"读取日志文件失败: {e}")
        return {"all": [], "user": []}


@router.post("/cache/clear", dependencies=[Depends(verify_api_key)])
def clear_cache(domain: Optional[str] = None) -> Dict[str, Any]:
    """清除缓存"""
    if domain:
        success = credential_cache.invalidate(domain)
        return {"message": f"域名 {domain} 缓存已清除" if success else f"域名 {domain} 无缓存", "success": success}
    else:
        count = credential_cache.invalidate_all()
        return {"message": f"已清除 {count} 条缓存", "count": count}


@router.post("/browser-pool/restart", dependencies=[Depends(verify_api_key)])
def restart_browser_pool() -> Dict[str, Any]:
    """重启浏览器池"""
    browser_pool.shutdown()
    log.info("[Dashboard] 浏览器池已重启")
    return {"message": "浏览器池已重启，下次请求时将重新初始化"}


class TestRequest(BaseModel):
    url: str
    mode: str = "cookie"  # cookie 或 browser
    force_refresh: bool = False


def _get_request_user(request: Request) -> str:
    user = getattr(request.state, "api_user", None)
    return user.get("user") if isinstance(user, dict) else "unknown"


@router.post("/test", dependencies=[Depends(verify_api_key)])
def test_bypass(req: TestRequest, request: Request) -> Dict[str, Any]:
    """测试过盾"""
    from core.solver import solve_turnstile

    start = time.time()
    user = _get_request_user(request)
    try:
        # 如果强制刷新，先清除该域名缓存
        if req.force_refresh:
            from urllib.parse import urlparse
            domain = urlparse(req.url).netloc
            credential_cache.invalidate(domain)

        result = solve_turnstile(req.url)
        duration = time.time() - start
        record_request(req.url, True, duration, user)

        return {
            "success": True,
            "duration_ms": round(duration * 1000, 2),
            "mode": req.mode,
            "cookies": result["cookies"],
            "cookies_count": len(result["cookies"]),
            "ua": result["ua"],
            "user": user,
        }
    except Exception as e:
        duration = time.time() - start
        record_request(req.url, False, duration, user, str(e))
        return {
            "success": False,
            "duration_ms": round(duration * 1000, 2),
            "mode": req.mode,
            "user": user,
            "error": str(e),
        }


class BatchTestRequest(BaseModel):
    urls: List[str]
    mode: str = "cookie"


@router.post("/test/batch", dependencies=[Depends(verify_api_key)])
def batch_test_bypass(req: BatchTestRequest, request: Request) -> Dict[str, Any]:
    """批量测试过盾"""
    from core.solver import solve_turnstile

    user = _get_request_user(request)
    results = []
    for url in req.urls[:10]:  # 最多10个
        test_req = TestRequest(url=url, mode=req.mode)
        start = time.time()
        try:
            result = solve_turnstile(test_req.url)
            duration = time.time() - start
            record_request(test_req.url, True, duration, user)
            results.append({
                "url": url,
                "success": True,
                "duration_ms": round(duration * 1000, 2),
                "mode": test_req.mode,
                "cookies": result["cookies"],
                "cookies_count": len(result["cookies"]),
                "ua": result["ua"],
                "user": user,
            })
        except Exception as e:  # noqa: BLE001
            duration = time.time() - start
            record_request(test_req.url, False, duration, user, str(e))
            results.append({
                "url": url,
                "success": False,
                "duration_ms": round(duration * 1000, 2),
                "mode": test_req.mode,
                "error": str(e),
                "user": user,
            })

    success_count = sum(1 for r in results if r["success"])
    return {
        "total": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }


# ========== 辅助函数 ==========

def _format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if days > 0:
        return f"{days}天 {hours}小时 {minutes}分钟"
    elif hours > 0:
        return f"{hours}小时 {minutes}分钟"
    elif minutes > 0:
        return f"{minutes}分钟 {secs}秒"
    else:
        return f"{secs}秒"


# ========== SSE 流式接口 ==========
def _snapshot_state() -> Dict[str, Any]:
    """聚合状态数据供前端实时更新"""
    return {
        "status": _status_payload(),
        "stats": get_stats(),
        "config": get_config(),
        "time_series": get_time_series(),
        "history": get_request_history(limit=50),
        "system": get_system_info(),
        "browser_pool": get_browser_pool_status(),
        "logs": get_logs(limit=100),
    }


@router.get("/stream")
async def stream_dashboard(key: Optional[str] = Depends(verify_query_key)):
    """
    SSE 流式推送聚合数据，减少前端轮询压力。
    前端使用 EventSource 订阅: /api/dashboard/stream?key=xxx
    """

    async def event_generator():
        while True:
            try:
                payload = _snapshot_state()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001
                log.error(f"[Dashboard] SSE 推送失败: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(2)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 兼容 Nginx 关闭缓冲
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# ========== 日志流式接口 ==========


def _parse_log_lines(lines: List[str], user: Optional[str] = None) -> List[Dict]:
    parsed_logs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if user and f"[user:{user}]" not in line:
            continue
        try:
            parts = line.split('|')
            if len(parts) >= 3:
                timestamp = parts[0].strip()
                level = parts[1].strip().lower()
                message = '|'.join(parts[2:]).strip()
                if ' ' in timestamp:
                    time_part = timestamp.split(' ')[1].split('.')[0]
                else:
                    time_part = timestamp
                parsed_logs.append({
                    "timestamp": time_part,
                    "level": level,
                    "message": message
                })
        except Exception:
            parsed_logs.append({
                "timestamp": "",
                "level": "info",
                "message": line
            })
    return parsed_logs


@router.get("/logs/stream")
async def stream_logs(user: Optional[str] = None):
    """日志 SSE 流：实时推送日志行，支持按用户过滤"""
    log_file = "logs/server.log"

    async def event_generator():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(0, os.SEEK_END)
                while True:
                    where = f.tell()
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(1)
                        f.seek(where)
                        continue
                    parsed = _parse_log_lines([line], user)
                    if parsed:
                        payload = {"all": parsed, "user": parsed if user else []}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except FileNotFoundError:
            yield f"event: error\ndata: {json.dumps({'error': '日志文件不存在'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            log.error(f"[Dashboard] 日志 SSE 异常: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# ========== 用户/密钥管理（仅管理员） ==========

class ApiUserCreate(BaseModel):
    user: str
    role: str = "user"


@router.get("/users", dependencies=[Depends(verify_admin)])
def list_users() -> Dict[str, Any]:
    """列出所有可管理用户（文件存储部分）"""
    return {"users": api_key_store.list_mutable_entries()}


@router.post("/users", dependencies=[Depends(verify_admin)])
def create_user(user: ApiUserCreate) -> Dict[str, Any]:
    """创建新用户并自动生成 Key"""
    try:
        entry = api_key_store.add_user(user.user, user.role)
        return {"message": "用户创建成功", "user": entry}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{username}", dependencies=[Depends(verify_admin)])
def delete_user(username: str) -> Dict[str, Any]:
    """删除用户"""
    deleted = api_key_store.delete_user(username)
    if not deleted:
        raise HTTPException(status_code=404, detail="用户不存在或不可删除")
    return {"message": "用户已删除", "user": username}


@router.post("/users/{username}/rotate", dependencies=[Depends(verify_admin)])
def rotate_user_key(username: str) -> Dict[str, Any]:
    """重置用户 Key"""
    try:
        entry = api_key_store.rotate_key(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "密钥已重置", "user": entry}
