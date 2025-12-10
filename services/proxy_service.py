import time
from urllib.parse import urlparse  # [CHANGED] 根据域名做特殊逻辑
from curl_cffi import requests  # ✅ 使用支持指纹模拟的 requests
from core.solver import solve_turnstile
from utils.logger import log
from config import settings
from core.browser import browser_manager  # [CHANGED] 为 69 直接用浏览器拿页面做准备

# 内存缓存
CACHE = {}


def get_credentials(url: str, force_refresh: bool = False):
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
    headers: dict,
    data: dict = None,
    json: dict = None,
):
    """
    代理请求核心逻辑 (集成指纹模拟)
    """
    retries = 1
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # ============================
    # [CHANGED-69] 69书吧特例：
    #  - 从日志可以看到：solver 返回的 cookie 没有任何 Cloudflare 通行证
    #  - curl_cffi impersonate 直接请求也仍然是 CF 的 Just a moment 403
    #  - 说明目前只有浏览器（DrissionPage）真正通过了 CF + Turnstile
    #  - 所以这里直接用浏览器拿页面 HTML，绕过 curl_cffi
    # ============================
    if "69shuba.com" in hostname:
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
            log.info(f"🚀 发起请求 (impersonate='chrome110'): {url}")

            # 使用 curl_cffi 的 requests
            resp = requests.request(
                method=method,
                url=url,
                cookies=creds["cookies"],
                headers=safe_headers,
                data=data,
                json=json,
                timeout=30,
                allow_redirects=True,
                impersonate="chrome110",  # 模拟 Chrome 110+ 版本
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
