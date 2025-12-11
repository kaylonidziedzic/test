"""
Fetchers 模块 - 页面获取策略

提供多种页面获取方式，可根据目标站点特性选择合适的策略：

- CookieFetcher: 浏览器过盾获取 cookie，HTTP 库复用 cookie 请求（默认，高效）
- BrowserFetcher: 浏览器直接获取页面内容（资源消耗大，但兼容性最好）

使用示例:
    from core.fetchers import CookieFetcher, BrowserFetcher

    # 默认方式
    fetcher = CookieFetcher()
    response = fetcher.fetch(url, method="GET", headers={})

    # 浏览器直读方式
    fetcher = BrowserFetcher()
    response = fetcher.fetch(url)
"""

from .base import BaseFetcher, FetchResponse
from .cookie_fetcher import CookieFetcher
from .browser_fetcher import BrowserFetcher

__all__ = [
    "BaseFetcher",
    "FetchResponse",
    "CookieFetcher",
    "BrowserFetcher",
]
