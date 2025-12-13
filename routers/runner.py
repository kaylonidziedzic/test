
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

    from services.api_key_store import api_key_store
    user = api_key_store.get_user_by_key(api_key)
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
    from services.api_key_store import api_key_store
    user = api_key_store.get_user_by_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 API Key")


def _get_proxy_for_rule(rule: ScrapeConfig) -> Optional[str]:
    """根据规则配置获取代理"""
    proxy_mode = getattr(rule, "proxy_mode", "none")

    if proxy_mode == "none":
        return None
    elif proxy_mode == "pool":
        # 从 IP 池获取
        return proxy_manager.get_proxy()
    elif proxy_mode == "fixed":
        return rule.proxy
    return None


def _execute_proxy(rule: ScrapeConfig) -> Dict[str, Any]:
    """执行 proxy 类型请求，返回 JSON"""
    # 构建请求参数
    request_data = None
    request_json = None

    if rule.body and rule.body_type != "none":
        if rule.body_type == "json":
            try:
                request_json = json.loads(rule.body)
            except:
                request_data = rule.body
        elif rule.body_type == "form":
            # 解析 form 数据
            request_data = dict(x.split("=") for x in rule.body.split("&") if "=" in x)
        else:
            request_data = rule.body

    # 获取代理
    proxy = _get_proxy_for_rule(rule)

    resp = proxy_request(
        url=rule.target_url,
        method=rule.method,
        headers=rule.headers or None,
        data=request_data,
        json=request_json,
        fetcher=rule.mode if rule.mode in ["cookie", "browser"] else "cookie",
        proxy=proxy
    )

    # 获取响应内容
    html_content = ""
    status_code = 200
    resp_headers = {}
    cookies = {}

    if hasattr(resp, "text"):
        html_content = resp.text
        status_code = getattr(resp, "status_code", 200)
        resp_headers = dict(getattr(resp, "headers", {}))
        cookies = getattr(resp, "cookies", {})
        if hasattr(cookies, "get_dict"):
            cookies = cookies.get_dict()
    elif isinstance(resp, dict):
        html_content = resp.get("text", "")
        status_code = resp.get("status_code", 200)

    # 数据提取
    data = {}
    if rule.selectors:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")

            for key, selector in rule.selectors.items():
                elements = soup.select(selector)
                if not elements:
                    data[key] = None
                else:
                    data[key] = elements[0].get_text(strip=True)
        except ImportError:
            data["_error"] = "BeautifulSoup not installed"
        except Exception as e:
            data["_error"] = str(e)

    return {
        "meta": {
            "rule_id": rule.id,
            "name": rule.name,
            "target": rule.target_url,
            "api_type": rule.api_type
        },
        "status": status_code,
        "data": data,
        "text": html_content if not rule.selectors else None,
        "headers": resp_headers,
        "cookies": cookies,
        "raw_length": len(html_content)
    }


def _execute_raw(rule: ScrapeConfig) -> Response:
    """执行 raw 类型请求，返回原始内容"""
    request_data = None
    if rule.body and rule.body_type != "none":
        request_data = rule.body

    proxy = _get_proxy_for_rule(rule)

    resp = proxy_request(
        url=rule.target_url,
        method=rule.method,
        headers=rule.headers or None,
        data=request_data,
        fetcher=rule.mode if rule.mode in ["cookie", "browser"] else "cookie",
        proxy=proxy
    )

    content = b""
    content_type = "application/octet-stream"
    status_code = 200

    if hasattr(resp, "content"):
        content = resp.content
        content_type = resp.headers.get("content-type", "application/octet-stream")
        status_code = resp.status_code

    return Response(
        content=content,
        status_code=status_code,
        media_type=content_type
    )


def _execute_reader(rule: ScrapeConfig) -> HTMLResponse:
    """执行 reader 类型请求，返回阅读模式 HTML"""
    request_data = None
    if rule.body and rule.body_type != "none":
        request_data = rule.body

    proxy = _get_proxy_for_rule(rule)

    resp = proxy_request(
        url=rule.target_url,
        method=rule.method,
        headers=rule.headers or None,
        data=request_data,
        fetcher=rule.mode if rule.mode in ["cookie", "browser"] else "cookie",
        proxy=proxy
    )

    html_content = ""
    if hasattr(resp, "text"):
        html_content = resp.text
    elif isinstance(resp, dict):
        html_content = resp.get("text", "")

    return HTMLResponse(content=html_content)


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
            return _execute_raw(rule)
        elif api_type == "reader":
            return _execute_reader(rule)
        else:  # proxy (默认)
            return _execute_proxy(rule)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Runner] 执行异常: {e}")
        return {
            "error": str(e),
            "meta": {"rule_id": rule_id}
        }
