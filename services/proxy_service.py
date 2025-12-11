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

# 默认 Fetcher 实例
_default_fetcher = CookieFetcher(retries=1, timeout=30, impersonate=None)

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

    Returns:
        FetchResponse: 响应对象
    """
    headers = headers or {}

    # 解析域名
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""

    # 选择 Fetcher
    if fetcher:
        # 显式指定
        selected_fetcher = get_fetcher(fetcher)
    elif _should_use_browser(hostname):
        # 域名规则匹配
        selected_fetcher = _browser_fetcher
        log.info(f"[ProxyService] 域名 {hostname} 匹配浏览器直读规则")
    else:
        # 默认使用 Cookie 方式
        selected_fetcher = _default_fetcher

    log.info(f"[ProxyService] 使用 {selected_fetcher.name} 处理请求: {url}")

    # 执行请求
    response = selected_fetcher.fetch(
        url=url,
        method=method,
        headers=headers,
        data=data,
        json=json,
    )

    return response


# ============================================================================
# 兼容性接口 (保持与旧代码的兼容)
# ============================================================================

def get_credentials(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """获取凭证 (兼容旧接口)

    推荐使用 services.cache_service.credential_cache.get_credentials()
    """
    from services.cache_service import credential_cache
    return credential_cache.get_credentials(url, force_refresh)
