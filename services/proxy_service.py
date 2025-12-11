"""Proxy service layer wrapping curl_cffi and browser-based fallbacks.

尽量保持原有行为不变，仅增加类型标注与注释，便于维护和阅读。

=============================================================================
TLS 指纹与 Cookie 复用方案说明 (针对 69书吧 等 Cloudflare 防护站点)
=============================================================================

问题背景:
  - 浏览器过盾后获取 cookie，再用 HTTP 库二次请求
  - 某些站点 (如 69书吧) 会检测 TLS 指纹与 cookie 的一致性

已测试方案:

  【方案1】不使用 impersonate (当前采用) ✅
    - curl_cffi 不指定 impersonate 参数，使用默认 TLS 指纹
    - 测试结果: 69书吧正文页可正常访问
    - 优点: 简单，不需要匹配浏览器版本
    - 缺点: 某些严格检测 TLS 指纹的站点可能失败

  【方案2】使用普通 requests 库 (备选)
    - 将 curl_cffi 替换为标准 requests 库
    - 适用场景: 如果方案1失败，可尝试此方案
    - 修改方式: 将 "from curl_cffi import requests" 改为 "import requests"
    - 注意: 需要同时移除 impersonate 参数

  【方案3】匹配浏览器版本的 impersonate (备选)
    - 根据实际 Chrome 版本设置对应的 impersonate
    - 例如: Chrome 143 对应 impersonate="chrome120" (curl_cffi 最新支持版本)
    - 适用场景: 站点严格检测 TLS 指纹时
    - 注意: curl_cffi 的 impersonate 版本可能落后于实际 Chrome 版本

  【方案4】浏览器直读 (最后手段)
    - 完全不用 HTTP 库，直接从浏览器获取页面 HTML
    - 优点: 100% 绕过 TLS 指纹检测
    - 缺点: 资源消耗大，并发能力差
    - 代码位置: 下方 "69shuba.com" 特殊处理块 (已禁用)

=============================================================================
"""

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from curl_cffi import requests  # 支持 TLS 指纹模拟的 requests
# 【方案2备选】如需使用标准 requests，取消下行注释并注释上行:
# import requests

from config import settings
from core.browser import browser_manager
from core.solver import solve_turnstile
from utils.logger import log

# 内存缓存
CACHE: Dict[str, Dict[str, Any]] = {}


def get_credentials(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """获取经过 Cloudflare 过盾后的 cookie 与 UA.

    ⚠️ 行为必须保持一致：缓存判定、浏览器过盾调用顺序不做任何改动。
    """

    from urllib.parse import urlparse

    domain = urlparse(url).netloc

    now = time.time()
    cached = CACHE.get(domain)

    # 1. 检查缓存
    if not force_refresh and cached and cached["expire"] > now:
        log.info(f"💾 命中缓存: {domain}")
        return cached["data"]

    # 2. 调用浏览器过盾
    log.info(f"⚡ 启动过盾流程: {domain}")
    creds = solve_turnstile(url)

    # 3. 写入缓存
    CACHE[domain] = {
        "data": creds,
        "expire": now + settings.COOKIE_EXPIRE_SECONDS,
    }
    return creds


def proxy_request(
    url: str,
    method: str,
    headers: Dict[str, str],
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
):
    """代理请求核心逻辑 (集成指纹模拟).

    ⚠️ 不允许变更任何请求顺序、重试策略或特殊站点处理逻辑。
    """
    retries = 1
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # ============================
    # 【方案4】浏览器直读 (已禁用，仅作为最后手段保留)
    #
    # 适用场景: 当 cookie 复用方式完全失效时，可启用此方案
    # 启用方式: 将 "if False and" 改为 "if"
    #
    # 注意事项:
    #   - 资源消耗大，每次请求都需要浏览器渲染
    #   - 并发能力差，浏览器实例有限
    #   - 仅建议对特定域名启用，不要全局使用
    # ============================
    if False and "69shuba.com" in hostname:
        try:
            log.info(f"[proxy-69] 使用浏览器直接获取页面: {url} method={method}")

            # 对 69 我们不再依赖 curl_cffi 过 CF，而是直接用 solve_turnstile + 浏览器页面
            # solve_turnstile 内部已经会：
            #   - 调用 page.get(url)
            #   - 等待 CF / Turnstile 通过
            solve_turnstile(url)

            # 过盾成功后，浏览器此时就在目标章节页面上
            page = browser_manager.get_browser()
            html = page.html  # DrissionPage 当前页面完整 HTML

            # 构造一个“类 Response”对象，满足上层 _make_html_response 的使用
            class FakeResp:
                pass

            resp = FakeResp()
            resp.content = html.encode("utf-8", errors="ignore")
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.apparent_encoding = "utf-8"
            resp.encoding = "utf-8"

            log.info("[proxy-69] 浏览器获取成功，返回 FakeResp")
            return resp

        except Exception as e:
            log.error(f"[proxy-69] 浏览器直接获取失败: {e}")
            # 对 69，失败就直接抛，让上层看到 500 / 错误信息
            raise

    # ============================
    # 默认路径：浏览器过盾 + cookie 复用 + curl_cffi
    # ============================
    for i in range(retries + 1):
        force = i > 0
        creds = get_credentials(url, force_refresh=force)

        # 构造请求头
        # 注意：curl_cffi 会自动管理大部分 header，我们只需保留关键的
        # [CHANGED] 这里额外过滤掉 cookie，避免上游 headers 里残留的 Cookie 和 creds['cookies'] 冲突
        safe_headers = {
            k: v
            for k, v in headers.items()
            if k.lower()
            not in [
                "host",
                "content-length",
                "user-agent",
                "accept-encoding",
                "cookie",  # [CHANGED] 永远只用 solve_turnstile 拿到的 cookies
            ]
        }

        # ✅ 使用浏览器过盾时的 UA，保证 cookie 与 UA 一致
        safe_headers["User-Agent"] = creds["ua"]

        # 调试日志：看清楚实际用到的 cookie 和 headers
        log.info(f"[proxy] 即将请求 URL: {url} method={method}")
        log.info(f"[proxy] 使用 creds cookies: {creds.get('cookies')}")
        log.info(f"[proxy] 最终 safe_headers: {safe_headers}")

        try:
            log.info(f"🚀 发起请求: {url}")

            # ============================
            # 【方案1】当前采用: 不使用 impersonate
            # ============================
            resp = requests.request(
                method=method,
                url=url,
                cookies=creds["cookies"],
                headers=safe_headers,
                data=data,
                json=json,
                timeout=30,
                allow_redirects=True,
                # 【方案3备选】如需启用 TLS 指纹模拟，取消下行注释:
                # impersonate="chrome120",  # 可选值: chrome110, chrome120, safari15_5 等
            )

            # 增强 403/503 调试信息：打印一点内容预览
            if resp.status_code in [403, 503]:
                preview = resp.text[:200].replace("\n", " ")
                log.warning(
                    f"[proxy] 收到状态码 {resp.status_code}，内容预览: {preview!r}"
                )

                # 检查是否依然被 Cloudflare 等盾拦截
                if "Just a moment" in resp.text or "Cloudflare" in resp.text:
                    if i < retries:
                        log.warning(
                            f"🛡️ 依然被拦截 (尝试 {i+1}/{retries})，正在重试并刷新缓存..."
                        )
                        continue
                    else:
                        log.error("❌ 重试后依然失败")

            return resp

        except Exception as e:
            log.error(f"网络请求异常: {e}")
            # 如果是最后一次尝试，抛出异常
            if i == retries:
                raise e
