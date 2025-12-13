
"""
Runner API - 规则执行与管理
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from typing import Dict, Any, List, Optional
import json

from services.rule_service import rule_service, ScrapeConfig
from services.proxy_service import proxy_request
from services.proxy_manager import proxy_manager
from dependencies import verify_api_key
from utils.logger import log

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


@router.get("/run/{rule_id}", summary="执行爬虫规则")
def run_rule(rule_id: str, request: Request):
    """
    通过 Permlink 执行预定义的爬虫规则。
    根据规则配置的 api_type 返回不同格式的响应。
    """
    rule = rule_service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # 检查访问权限
    _check_access(rule, request)

    log.info(f"[Runner] 执行规则: {rule.name} ({rule_id}) [api_type={rule.api_type}]")

    try:
        api_type = getattr(rule, "api_type", "proxy")

        if api_type == "raw":
            return execute_rule_raw(rule)
        elif api_type == "reader":
            return execute_rule_reader(rule)
        else:  # proxy (默认)
            return execute_rule_proxy(rule)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Runner] 执行异常: {e}")
        return {
            "error": str(e),
            "meta": {"rule_id": rule_id}
        }
