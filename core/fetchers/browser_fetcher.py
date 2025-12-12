"""
Browser Fetcher - 浏览器直读页面获取器

工作流程:
1. 浏览器访问目标站点，完成 Cloudflare 等验证
2. 直接从浏览器获取渲染后的页面 HTML

优点:
- 100% 绕过 TLS 指纹检测
- 可以获取 JavaScript 渲染后的内容
- 兼容性最好

缺点:
- 资源消耗大，每次请求都需要浏览器渲染
- 并发能力差，浏览器实例有限
- 速度较慢

适用场景:
- Cookie 复用方式完全失效的站点
- 需要 JavaScript 渲染的页面
- 对性能要求不高的场景
"""

from typing import Any, Dict, Optional

from .base import BaseFetcher, FetchResponse
from core.browser_pool import browser_pool
from utils.logger import log


class BrowserFetcher(BaseFetcher):
    """浏览器直读 Fetcher

    直接使用浏览器获取页面内容，绕过所有 TLS 指纹检测。
    注意: 此方式资源消耗大，仅建议在其他方式失效时使用。
    """

    def __init__(self, timeout: int = 30):
        """
        Args:
            timeout: 页面加载超时时间 (秒)
        """
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "BrowserFetcher"

    def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> FetchResponse:
        """使用浏览器直接获取页面

        注意: 此方法忽略 method, headers, data, json 参数，
        因为浏览器只能模拟 GET 请求。
        """
        if method.upper() != "GET":
            log.warning(f"[{self.name}] 浏览器直读仅支持 GET 请求，忽略 method={method}")

        log.info(f"[{self.name}] 使用浏览器直接获取: {url}")

        # 从浏览器池获取实例
        instance = browser_pool.acquire(timeout=60)
        if not instance:
            raise Exception("无法获取浏览器实例，池已满")

        try:
            page = instance.page

            # 1. 访问目标页面
            log.info(f"[{self.name}] 正在访问: {url} (浏览器 PID: {instance.pid})")
            page.get(url)

            # 2. 等待页面加载并处理 Cloudflare 验证
            import time
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                title = page.title.lower()

                # 尝试点击 Cloudflare 验证码
                try:
                    box = page.ele("@name=cf-turnstile-response", timeout=1)
                    if box:
                        wrapper = box.parent()
                        iframe = wrapper.shadow_root.ele("tag:iframe")
                        cb = iframe.ele("tag:body").shadow_root.ele("tag:input")
                        if cb:
                            log.info(f"[{self.name}] 发现验证码，点击中...")
                            cb.click()
                except Exception:
                    pass

                # 检查是否过盾成功
                if "just a moment" not in title and "cloudflare" not in title:
                    log.success(f"[{self.name}] 页面加载成功，标题: {title}")
                    time.sleep(1)  # 等待页面完全渲染
                    break

                time.sleep(1)
            else:
                raise Exception(f"页面加载超时 ({self.timeout}秒)")

            # 3. 获取页面内容
            html = page.html
            current_url = page.url

            # 4. 获取页面 cookies
            raw_cookies = page.cookies()
            cookies = self._parse_cookies(raw_cookies)

            log.info(f"[{self.name}] 浏览器获取成功，内容长度: {len(html)}")

            return FetchResponse(
                status_code=200,
                content=html.encode("utf-8", errors="ignore"),
                text=html,
                headers={"Content-Type": "text/html; charset=utf-8"},
                cookies=cookies,
                url=current_url,
                encoding="utf-8",
            )

        except Exception as e:
            log.error(f"[{self.name}] 浏览器获取失败: {e}")
            raise

        finally:
            # 归还浏览器到池中
            browser_pool.release(instance)

    def _parse_cookies(self, raw_cookies) -> Dict[str, str]:
        """解析浏览器返回的 cookies"""
        cookie_dict = {}

        if isinstance(raw_cookies, dict):
            cookie_dict = raw_cookies
        elif isinstance(raw_cookies, list):
            for c in raw_cookies:
                if isinstance(c, dict) and "name" in c and "value" in c:
                    cookie_dict[c["name"]] = c["value"]
                elif isinstance(c, (list, tuple)) and len(c) >= 2:
                    cookie_dict[c[0]] = c[1]
        else:
            try:
                cookie_dict = dict(raw_cookies)
            except Exception:
                pass

        return cookie_dict
