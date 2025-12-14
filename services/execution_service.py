"""
规则执行服务 - 根据规则配置执行采集任务
"""
from typing import Dict, Any
from fastapi.responses import JSONResponse, Response

from services.proxy_service import proxy_request
from services.rule_service import ScrapeConfig
from services.proxy_manager import proxy_manager
from utils.logger import log
from utils.response_builder import decode_response, make_html_response


def _get_proxy_for_rule(rule: ScrapeConfig) -> str:
    """根据规则配置获取代理"""
    proxy_mode = getattr(rule, "proxy_mode", "none")

    if proxy_mode == "pool":
        # 从代理池获取
        proxy = proxy_manager.get_proxy()
        if proxy:
            log.info(f"[Execution] 使用代理池: {proxy}")
            return proxy
        log.warning("[Execution] 代理池为空，使用直连")
        return None
    elif proxy_mode == "fixed" and rule.proxy:
        log.info(f"[Execution] 使用指定代理: {rule.proxy}")
        return rule.proxy

    return None


def _extract_data(html: str, selectors: Dict[str, str]) -> Dict[str, str]:
    """使用 CSS 选择器从 HTML 中提取数据"""
    if not selectors:
        return {}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        result = {}
        for key, selector in selectors.items():
            try:
                element = soup.select_one(selector)
                if element:
                    result[key] = element.get_text(strip=True)
                else:
                    result[key] = None
            except Exception as e:
                log.warning(f"[Execution] 选择器 {selector} 提取失败: {e}")
                result[key] = None

        return result
    except ImportError:
        log.error("[Execution] 需要安装 beautifulsoup4: pip install beautifulsoup4")
        return {}
    except Exception as e:
        log.error(f"[Execution] 数据提取失败: {e}")
        return {}


def execute_rule_proxy(rule: ScrapeConfig) -> Dict[str, Any]:
    """执行规则 - JSON 代理模式

    返回结构化的 JSON 数据，支持 CSS 选择器提取
    """
    try:
        # 获取代理
        proxy = _get_proxy_for_rule(rule)

        # 确定 fetcher
        fetcher = "browser" if rule.mode == "browser" else "cookie"

        # 构建请求头
        headers = dict(rule.headers) if rule.headers else {}

        # 构建请求体
        data = None
        json_body = None
        if rule.method.upper() == "POST" and rule.body:
            body_type = getattr(rule, "body_type", "none")
            if body_type == "json":
                import json
                json_body = json.loads(rule.body)
            elif body_type in ["form", "raw"]:
                data = rule.body

        # 执行请求
        body_type = getattr(rule, "body_type", "none")
        wait_for = getattr(rule, "wait_for", None)
        resp = proxy_request(
            url=rule.target_url,
            method=rule.method,
            headers=headers,
            data=data,
            json=json_body,
            fetcher=fetcher,
            proxy=proxy,
            body_type=body_type,
            wait_for=wait_for,
        )

        # 获取响应文本
        text = resp.text if hasattr(resp, 'text') else decode_response(
            resp.content,
            getattr(resp, "apparent_encoding", None)
        )

        # 提取数据
        extracted_data = {}
        if rule.selectors:
            extracted_data = _extract_data(text, rule.selectors)

        # 构建响应
        cookies = resp.cookies if isinstance(resp.cookies, dict) else (
            resp.cookies.get_dict() if hasattr(resp.cookies, 'get_dict') else dict(resp.cookies)
        )

        return {
            "success": True,
            "data": extracted_data,
            "meta": {
                "rule_id": rule.id,
                "name": rule.name,
                "status": resp.status_code,
                "url": str(resp.url),
            },
            "raw_length": len(text),
            "cookies_count": len(cookies),
        }

    except Exception as e:
        log.error(f"[Execution] proxy 模式执行失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "meta": {"rule_id": rule.id, "name": rule.name}
        }


def _build_request_body(rule: ScrapeConfig):
    """根据规则配置构建请求体

    Returns:
        tuple: (data, json_body, body_type, wait_for)
    """
    data = None
    json_body = None
    body_type = getattr(rule, "body_type", "none")
    wait_for = getattr(rule, "wait_for", None)
    if rule.method.upper() == "POST" and rule.body:
        if body_type == "json":
            import json
            json_body = json.loads(rule.body)
        elif body_type in ["form", "raw"]:
            data = rule.body
    return data, json_body, body_type, wait_for


def execute_rule_raw(rule: ScrapeConfig, test_mode: bool = False):
    """执行规则 - 原始数据模式

    直接返回二进制数据，test_mode=True 时返回 JSON 摘要
    """
    try:
        proxy = _get_proxy_for_rule(rule)
        fetcher = "browser" if rule.mode == "browser" else "cookie"
        headers = dict(rule.headers) if rule.headers else {}
        data, json_body, body_type, wait_for = _build_request_body(rule)

        resp = proxy_request(
            url=rule.target_url,
            method=rule.method,
            headers=headers,
            data=data,
            json=json_body,
            fetcher=fetcher,
            proxy=proxy,
            body_type=body_type,
            wait_for=wait_for,
        )

        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        if isinstance(content_type, list):
            content_type = content_type[0]

        # 测试模式返回 JSON 摘要
        if test_mode:
            return {
                "success": True,
                "meta": {
                    "rule_id": rule.id,
                    "name": rule.name,
                    "status": resp.status_code,
                    "content_type": content_type,
                    "content_length": len(resp.content),
                }
            }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )

    except Exception as e:
        log.error(f"[Execution] raw 模式执行失败: {e}")
        if test_mode:
            return {"success": False, "error": str(e), "meta": {"rule_id": rule.id, "name": rule.name}}
        return Response(content=f"Error: {str(e)}", status_code=500)


def execute_rule_reader(rule: ScrapeConfig, test_mode: bool = False):
    """执行规则 - 阅读模式

    返回处理后的 HTML，test_mode=True 时返回 JSON 摘要
    """
    try:
        proxy = _get_proxy_for_rule(rule)
        fetcher = "browser" if rule.mode == "browser" else "cookie"
        headers = dict(rule.headers) if rule.headers else {}
        data, json_body, body_type, wait_for = _build_request_body(rule)

        resp = proxy_request(
            url=rule.target_url,
            method=rule.method,
            headers=headers,
            data=data,
            json=json_body,
            fetcher=fetcher,
            proxy=proxy,
            body_type=body_type,
            wait_for=wait_for,
        )

        # 测试模式返回 JSON 摘要
        if test_mode:
            text = resp.text if hasattr(resp, 'text') else ''
            return {
                "success": True,
                "meta": {
                    "rule_id": rule.id,
                    "name": rule.name,
                    "status": resp.status_code,
                    "content_length": len(text),
                    "title": _extract_title(text),
                }
            }

        return make_html_response(resp, rule.target_url)

    except Exception as e:
        log.error(f"[Execution] reader 模式执行失败: {e}")
        if test_mode:
            return {"success": False, "error": str(e), "meta": {"rule_id": rule.id, "name": rule.name}}
        return Response(content=f"Error: {str(e)}", status_code=500)


def _extract_title(html: str) -> str:
    """从 HTML 中提取标题"""
    try:
        import re
        match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""
