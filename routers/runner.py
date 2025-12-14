
"""
Runner API - 规则执行与管理
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from typing import Dict, Any, List, Optional
import json
import hashlib
import time

from services.rule_service import rule_service, ScrapeConfig
from services.proxy_service import proxy_request
from services.proxy_manager import proxy_manager
from dependencies import verify_api_key
from utils.logger import log

# 规则结果缓存 (使用 Redis)
try:
    import redis
    from config import settings
    _result_cache = redis.from_url(getattr(settings, "REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    _RESULT_CACHE_PREFIX = "result:"
except Exception as e:
    log.warning(f"[Runner] Redis 缓存不可用: {e}")
    _result_cache = None

router = APIRouter(prefix="/v1", tags=["Runner"])


def _get_current_user(request: Request) -> tuple:
    """从请求中获取当前用户信息"""
    api_key = request.headers.get("X-API-KEY") or request.query_params.get("key")
    if not api_key:
        return None, False

    from services.api_key_store import find_user_by_key
    user = find_user_by_key(api_key)
    if user:
        return user.get("user"), user.get("role") == "admin"
    return None, False


# ========== 规则管理 ==========

@router.post("/rules", summary="创建爬虫规则", dependencies=[Depends(verify_api_key)])
def create_rule(rule: ScrapeConfig, request: Request) -> Dict[str, Any]:
    # 自动设置规则所有者
    username, is_admin = _get_current_user(request)
    if username and not rule.owner:
        rule.owner = username

    rule_id = rule_service.create_rule(rule)
    return {
        "id": rule_id,
        "permlink": f"/v1/run/{rule_id}",
        "message": "规则创建成功"
    }

@router.get("/rules", summary="获取规则列表", dependencies=[Depends(verify_api_key)])
def list_rules(request: Request) -> Dict[str, List[ScrapeConfig]]:
    username, is_admin = _get_current_user(request)
    rules = rule_service.list_rules(owner=username, is_admin=is_admin)
    return {"rules": rules}

@router.put("/rules/{rule_id}", summary="更新规则", dependencies=[Depends(verify_api_key)])
def update_rule(rule_id: str, rule: ScrapeConfig, request: Request) -> Dict[str, Any]:
    # 检查权限
    username, is_admin = _get_current_user(request)
    existing = rule_service.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="规则不存在")

    # 非管理员只能更新自己的规则
    if not is_admin and existing.owner and existing.owner != username:
        raise HTTPException(status_code=403, detail="无权更新此规则")

    # 设置规则 ID 和所有者
    rule.id = rule_id
    if not rule.owner:
        rule.owner = existing.owner or username

    rule_service.create_rule(rule)
    return {
        "id": rule_id,
        "message": "规则更新成功"
    }

@router.delete("/rules/{rule_id}", summary="删除规则", dependencies=[Depends(verify_api_key)])
def delete_rule(rule_id: str, request: Request) -> Dict[str, Any]:
    # 检查权限
    username, is_admin = _get_current_user(request)
    rule = rule_service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # 非管理员只能删除自己的规则
    if not is_admin and rule.owner and rule.owner != username:
        raise HTTPException(status_code=403, detail="无权删除此规则")

    if rule_service.delete_rule(rule_id):
        return {"message": "规则已删除"}
    raise HTTPException(status_code=500, detail="删除失败")

# ========== 规则执行 (Permlink) ==========

def _check_access(rule: ScrapeConfig, request: Request):
    """检查访问权限"""
    if rule.is_public:
        return  # 公开规则，无需验证

    # 私有规则，需要 API Key
    api_key = request.headers.get("X-API-KEY") or request.query_params.get("key")
    if not api_key:
        raise HTTPException(status_code=401, detail="此规则需要 API Key 访问")

    # 验证 API Key（简单验证，实际应调用 verify_api_key）
    from services.api_key_store import find_user_by_key
    user = find_user_by_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 API Key")


from services.execution_service import execute_rule_proxy, execute_rule_raw, execute_rule_reader

# Execution logic moved to services/execution_service.py


def _get_cache_key(rule_id: str, params: Dict[str, str]) -> str:
    """生成缓存键"""
    # 将参数排序后拼接，确保相同参数生成相同的 key
    param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
    raw_key = f"{rule_id}:{param_str}"
    return f"{_RESULT_CACHE_PREFIX}{hashlib.md5(raw_key.encode()).hexdigest()}"


def _get_cached_result(cache_key: str) -> Optional[Dict]:
    """从缓存获取结果"""
    if not _result_cache:
        return None
    try:
        data = _result_cache.get(cache_key)
        if data:
            return json.loads(data)
    except Exception as e:
        log.warning(f"[Runner] 读取缓存失败: {e}")
    return None


def _set_cached_result(cache_key: str, result: Any, ttl: int):
    """将结果写入缓存"""
    if not _result_cache or ttl <= 0:
        return
    try:
        # 只缓存可序列化的结果
        if isinstance(result, dict):
            _result_cache.setex(cache_key, ttl, json.dumps(result))
            log.info(f"[Runner] 结果已缓存 (TTL={ttl}s)")
        elif isinstance(result, Response):
            # 对于 Response 对象，缓存其内容
            cache_data = {
                "_type": "response",
                "content": result.body.decode("utf-8", errors="ignore") if result.body else "",
                "status_code": result.status_code,
                "media_type": result.media_type,
            }
            _result_cache.setex(cache_key, ttl, json.dumps(cache_data))
            log.info(f"[Runner] Response 已缓存 (TTL={ttl}s)")
    except Exception as e:
        log.warning(f"[Runner] 写入缓存失败: {e}")


def _apply_params_to_rule(rule: ScrapeConfig, params: Dict[str, str]) -> ScrapeConfig:
    """将 URL 查询参数应用到规则的 target_url 和 body 中

    支持占位符格式: {param_name}
    例如: target_url="https://example.com/search?q={q}" 或 body="searchkey={q}"
    """
    if not params:
        return rule

    # 创建规则副本，避免修改原始规则
    rule_copy = rule.model_copy()

    # 替换 target_url 中的占位符
    if rule_copy.target_url:
        for key, value in params.items():
            rule_copy.target_url = rule_copy.target_url.replace(f"{{{key}}}", value)

    # 替换 body 中的占位符
    if rule_copy.body:
        for key, value in params.items():
            rule_copy.body = rule_copy.body.replace(f"{{{key}}}", value)

    return rule_copy


@router.get("/run/{rule_id}", summary="执行爬虫规则")
def run_rule(rule_id: str, request: Request, test: bool = False, refresh: bool = False):
    """
    通过 Permlink 执行预定义的爬虫规则。
    根据规则配置的 api_type 返回不同格式的响应。

    Args:
        test: 测试模式，返回 JSON 摘要而非原始响应
        refresh: 强制刷新，忽略缓存

    支持动态参数替换:
        URL 查询参数会替换规则中的 {param} 占位符
        例如: /v1/run/abc123?q=斗破 会将规则中的 {q} 替换为 "斗破"
    """
    rule = rule_service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # 检查访问权限
    _check_access(rule, request)

    # 获取查询参数（排除保留参数）
    reserved_params = {"test", "key", "refresh"}
    query_params = {k: v for k, v in request.query_params.items() if k not in reserved_params}

    # 检查缓存 (仅当 cache_ttl > 0 且非强制刷新时)
    cache_ttl = getattr(rule, "cache_ttl", 0)
    cache_key = None
    if cache_ttl > 0 and not refresh and not test:
        cache_key = _get_cache_key(rule_id, query_params)
        cached = _get_cached_result(cache_key)
        if cached:
            log.info(f"[Runner] 命中缓存: {rule.name} ({rule_id})")
            # 检查是否是 Response 类型的缓存
            if cached.get("_type") == "response":
                return Response(
                    content=cached["content"],
                    status_code=cached["status_code"],
                    media_type=cached["media_type"],
                )
            return cached

    # 应用参数替换
    if query_params:
        rule = _apply_params_to_rule(rule, query_params)
        log.info(f"[Runner] 参数替换: {query_params}")

    log.info(f"[Runner] 执行规则: {rule.name} ({rule_id}) [api_type={rule.api_type}] [test={test}] [cache_ttl={cache_ttl}]")

    try:
        api_type = getattr(rule, "api_type", "proxy")

        if api_type == "raw":
            result = execute_rule_raw(rule, test_mode=test)
        elif api_type == "reader":
            result = execute_rule_reader(rule, test_mode=test)
        else:  # proxy (默认)
            result = execute_rule_proxy(rule)

        # 写入缓存
        if cache_key and cache_ttl > 0:
            _set_cached_result(cache_key, result, cache_ttl)

        return result

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Runner] 执行异常: {e}")
        return {
            "success": False,
            "error": str(e),
            "meta": {"rule_id": rule_id}
        }
