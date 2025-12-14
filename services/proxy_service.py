"""
代理服务 - 请求调度层

负责根据配置和目标站点选择合适的 Fetcher 策略，
并提供统一的代理请求接口。

架构说明:
┌─────────────────────────────────────────────────────────────┐
│                      proxy_service                          │
│                      (调度层)                                │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │CookieFetcher│ │BrowserFetch │ │ 未来扩展... │
    │  (默认)     │ │  (备选)     │ │             │
    └─────────────┘ └─────────────┘ └─────────────┘
            │               │
            ▼               ▼
    ┌─────────────┐ ┌─────────────┐
    │cache_service│ │browser_mgr  │
    │  (缓存)     │ │  (浏览器)   │
    └─────────────┘ └─────────────┘

使用方式:
    # 默认方式 (Cookie 复用)
    resp = proxy_request(url, method="GET", headers={})

    # 指定使用浏览器直读
    resp = proxy_request(url, method="GET", headers={}, fetcher="browser")
"""

from typing import Any, Dict, Optional, Union

from core.fetchers import CookieFetcher, BrowserFetcher, FetchResponse
from utils.logger import log


# ============================================================================
# Fetcher 实例管理
# ============================================================================

# 默认 Fetcher 实例（retries=0 表示失败直接降级，不重试）
# impersonate="chrome136" 模拟 Chrome TLS 指纹（curl_cffi 支持的最新版本）
_default_fetcher = CookieFetcher(retries=0, timeout=30, impersonate="chrome136")

# 浏览器直读 Fetcher 实例
_browser_fetcher = BrowserFetcher(timeout=20)

# Fetcher 注册表，便于按名称获取
_fetcher_registry = {
    "cookie": _default_fetcher,
    "browser": _browser_fetcher,
}


def get_fetcher(name: str = "cookie"):
    """获取指定名称的 Fetcher

    Args:
        name: Fetcher 名称 ("cookie" 或 "browser")

    Returns:
        BaseFetcher: Fetcher 实例
    """
    fetcher = _fetcher_registry.get(name)
    if not fetcher:
        raise ValueError(f"Unknown fetcher: {name}. Available: {list(_fetcher_registry.keys())}")
    return fetcher


def register_fetcher(name: str, fetcher):
    """注册自定义 Fetcher

    Args:
        name: Fetcher 名称
        fetcher: Fetcher 实例
    """
    _fetcher_registry[name] = fetcher
    log.info(f"[ProxyService] 注册 Fetcher: {name}")


# ============================================================================
# 域名特殊规则配置
# ============================================================================

# 需要使用浏览器直读的域名列表
# 当 Cookie 复用方式对某些站点完全失效时，可将域名添加到此列表
BROWSER_DIRECT_DOMAINS = [
    # "example.com",  # 示例：取消注释以启用
]


def _should_use_browser(hostname: str) -> bool:
    """判断是否应该使用浏览器直读"""
    for domain in BROWSER_DIRECT_DOMAINS:
        if domain in hostname:
            return True
    return False


# ============================================================================
# 主要接口
# ============================================================================

def proxy_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    fetcher: Optional[str] = None,
    data_encoding: Optional[str] = None,
    auto_fallback: bool = True,
    proxy: Optional[str] = None,
    body_type: Optional[str] = None,
    wait_for: Optional[str] = None,
) -> Union[FetchResponse, Any]:
    """代理请求核心接口

    Args:
        url: 目标 URL
        method: HTTP 方法
        headers: 请求头
        data: 表单数据
        json: JSON 数据
        fetcher: 指定使用的 Fetcher ("cookie" 或 "browser")，
                 默认根据域名规则自动选择
        data_encoding: POST data 编码，如 "gbk"、"gb2312"，默认自动检测
        auto_fallback: CookieFetcher 失败后是否自动降级到 BrowserFetcher
        proxy: 代理地址
        body_type: 请求体类型 ("form" / "json" / "raw")，用于设置 Content-Type
        wait_for: 浏览器模式下等待指定元素出现

    Returns:
        FetchResponse: 响应对象
    """
    headers = headers or {}

    # 解析域名
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""

    # 自动检测编码（如果未指定）
    if data_encoding is None and data and method.upper() in ["POST", "PUT", "PATCH"]:
        from config import get_encoding_for_domain
        data_encoding = get_encoding_for_domain(hostname)
        if data_encoding:
            log.info(f"[ProxyService] 自动检测编码: {hostname} -> {data_encoding}")

    # 选择 Fetcher
    if fetcher:
        # 显式指定 fetcher，但代理模式下 cookie 改用 browser（TLS 指纹不一致问题）
        if proxy and fetcher == "cookie":
            # 使用代理时，直接用 BrowserFetcher（避免 TLS 指纹不一致导致的失败）
            selected_fetcher = _browser_fetcher
            use_fallback = False
            log.info(f"[ProxyService] 代理模式下 cookie fetcher 改用 BrowserFetcher")
        else:
            selected_fetcher = get_fetcher(fetcher)
            # cookie 模式仍支持自动降级，browser 模式不降级
            use_fallback = auto_fallback and fetcher == "cookie"
    elif proxy:
        # 使用代理时，直接用 BrowserFetcher（避免 TLS 指纹不一致导致的失败）
        selected_fetcher = _browser_fetcher
        use_fallback = False
        log.info(f"[ProxyService] 使用代理模式，直接使用 BrowserFetcher")
    elif _should_use_browser(hostname):
        # 域名白名单匹配，直接使用浏览器
        selected_fetcher = _browser_fetcher
        use_fallback = False
        log.info(f"[ProxyService] 域名 {hostname} 匹配浏览器直读规则")
    else:
        # 默认使用 Cookie 方式，支持自动降级
        selected_fetcher = _default_fetcher
        use_fallback = auto_fallback

    log.info(f"[ProxyService] 使用 {selected_fetcher.name} 处理请求: {url}")

    # 执行请求
    try:
        response = selected_fetcher.fetch(
            url=url,
            method=method,
            headers=headers,
            data=data,
            json=json,
            data_encoding=data_encoding,
            proxy=proxy,
            body_type=body_type,
            wait_for=wait_for,
        )

        # 检查是否被拦截（即使返回了响应）
        if use_fallback and _is_response_blocked(response):
            log.warning(f"[ProxyService] CookieFetcher 返回被拦截，降级到 BrowserFetcher")
            return _fallback_to_browser(url, method, headers, data, json, proxy=proxy)

        return response

    except Exception as e:
        # CookieFetcher 异常，尝试降级
        if use_fallback:
            log.warning(f"[ProxyService] CookieFetcher 异常: {e}，降级到 BrowserFetcher")
            return _fallback_to_browser(url, method, headers, data, json, proxy=proxy)
        raise


def _is_response_blocked(resp: FetchResponse) -> bool:
    """检查响应是否被拦截"""
    if resp.status_code in [403, 503, 429]:
        return True

    # 检查页面内容特征
    check_text = resp.text[:10000] if len(resp.text) > 10000 else resp.text
    blocked_patterns = [
        "cf-turnstile",
        "challenge-platform",
        "_cf_chl_opt",
        "challenges.cloudflare.com/turnstile",
    ]
    for pattern in blocked_patterns:
        if pattern in check_text:
            return True

    return False


def _fallback_to_browser(
    url: str,
    method: str,
    headers: Optional[Dict[str, str]],
    data: Optional[Dict[str, Any]],
    json: Optional[Dict[str, Any]],
    proxy: Optional[str] = None,
) -> FetchResponse:
    """降级到浏览器直读

    支持 GET 和 POST 请求。POST 请求通过 JavaScript 表单提交实现。
    """
    proxy_info = f", proxy={proxy}" if proxy else ""
    log.info(f"[ProxyService] 降级使用 BrowserFetcher 处理请求: {url} (method={method}{proxy_info})")
    return _browser_fetcher.fetch(
        url=url,
        method=method,
        headers=headers or {},
        data=data,
        proxy=proxy,
    )


# ============================================================================
# 兼容性接口 (保持与旧代码的兼容)
# ============================================================================

def get_credentials(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """获取凭证 (兼容旧接口)

    推荐使用 services.cache_service.credential_cache.get_credentials()
    """
    from services.cache_service import credential_cache
    return credential_cache.get_credentials(url, force_refresh)
