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
        proxy: str = None,
        wait_for: Optional[str] = None,
        **kwargs
    ) -> FetchResponse:
        """使用浏览器直接获取页面

        Args:
            method: HTTP 方法，支持 GET 和 POST
            data: POST 表单数据（字符串格式如 "key1=value1&key2=value2" 或 dict）
            proxy: 代理地址，None 表示不使用代理，"pool" 表示从代理池获取
            wait_for: 等待指定的 CSS 选择器元素出现后再采集
        """
        log.info(f"[{self.name}] 使用浏览器直接获取: {url} (method={method})")

        # 从浏览器池获取实例，传递代理参数
        instance = browser_pool.acquire(timeout=60, proxy=proxy)
        if not instance:
            raise Exception("无法获取浏览器实例，池已满")

        try:
            page = instance.page

            # 1. 访问目标页面或提交表单
            if method.upper() == "POST" and data:
                # POST 请求：通过 JavaScript 创建并提交表单
                log.info(f"[{self.name}] 使用 JS 表单提交 POST 请求: {url} (浏览器 PID: {instance.pid})")
                self._submit_form_via_js(page, url, data)
            else:
                # GET 请求：直接访问
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

                    # 如果指定了 wait_for，等待元素出现
                    if wait_for:
                        log.info(f"[{self.name}] 等待元素: {wait_for}")
                        try:
                            page.ele(wait_for, timeout=10)
                            log.success(f"[{self.name}] 元素已出现: {wait_for}")
                        except Exception as e:
                            log.warning(f"[{self.name}] 等待元素超时: {wait_for}, 继续采集")
                    else:
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

    def _submit_form_via_js(self, page, url: str, data) -> None:
        """通过 JavaScript 创建并提交表单实现 POST 请求

        Args:
            page: DrissionPage 页面对象
            url: 表单提交目标 URL
            data: 表单数据（字符串 "key1=value1&key2=value2" 或 dict）
        """
        from urllib.parse import parse_qs, urlparse

        # 解析表单数据
        form_data = {}
        if isinstance(data, dict):
            form_data = data
        elif isinstance(data, str):
            # 解析 URL 编码的字符串
            parsed = parse_qs(data, keep_blank_values=True)
            form_data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        log.info(f"[{self.name}] 表单数据: {form_data}")

        # 先访问目标域名的任意页面（确保在同域下执行 JS）
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        page.get(base_url)

        # 等待页面加载
        import time
        time.sleep(1)

        # 构建 JavaScript 代码创建并提交表单
        # 使用 JSON 传递数据避免转义问题
        import json
        form_data_json = json.dumps(form_data, ensure_ascii=False)

        js_code = f'''
        (function() {{
            var form = document.createElement('form');
            form.method = 'POST';
            form.action = '{url}';
            form.style.display = 'none';

            var formData = {form_data_json};
            for (var key in formData) {{
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = formData[key];
                form.appendChild(input);
            }}

            document.body.appendChild(form);
            form.submit();
        }})();
        '''

        page.run_js(js_code)
        log.info(f"[{self.name}] 表单已提交")

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
