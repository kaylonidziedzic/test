"""
Cookie Fetcher - 基于 Cookie 复用的页面获取器

工作流程:
1. 浏览器访问目标站点，完成 Cloudflare 等验证
2. 提取浏览器的 Cookie 和 User-Agent
3. 使用 HTTP 库 (curl_cffi) 携带 Cookie 发起请求

优点:
- 高效，浏览器只需过盾一次，后续请求复用 Cookie
- 支持高并发

缺点:
- 某些站点可能检测 TLS 指纹与 Cookie 的一致性
- Cookie 有过期时间，需要定期刷新

TLS 指纹方案说明:
- 方案1 (当前): 不使用 impersonate，使用 curl_cffi 默认指纹
- 方案2 (备选): 使用标准 requests 库
- 方案3 (备选): 使用 impersonate 模拟特定浏览器版本
"""

from typing import Any, Dict, Optional

from curl_cffi import requests as curl_requests
# 方案2备选: 使用标准 requests
# import requests as std_requests

from .base import BaseFetcher, FetchResponse
from core.solver import solve_turnstile
from services.cache_service import credential_cache
from services.proxy_manager import proxy_manager
from utils.logger import log


class CookieFetcher(BaseFetcher):
    """基于 Cookie 复用的 Fetcher

    这是默认的获取策略，适用于大多数 Cloudflare 保护的站点。
    """

    def __init__(
        self,
        retries: int = 1,
        timeout: int = 30,
        impersonate: Optional[str] = None,
    ):
        """
        Args:
            retries: 失败重试次数
            timeout: 请求超时时间 (秒)
            impersonate: TLS 指纹模拟 (None=不模拟, "chrome120"=模拟 Chrome 120)
        """
        self.retries = retries
        self.timeout = timeout
        self.impersonate = impersonate

    @property
    def name(self) -> str:
        return "CookieFetcher"

    def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data_encoding: Optional[str] = None,
        proxy: Optional[str] = None,
        **kwargs
    ) -> FetchResponse:
        """使用 Cookie 复用方式获取页面"""
        headers = headers or {}

        for attempt in range(self.retries + 1):
            force_refresh = attempt > 0

            # 1. 获取凭证 (Cookie + UA)
            creds = credential_cache.get_credentials(url, force_refresh=force_refresh)

            # 2. 构造安全的请求头
            safe_headers = self._build_safe_headers(headers, creds["ua"], url, method)

            # 3. 获取代理 (优先使用指定代理)
            use_proxy = proxy or proxy_manager.get_proxy()
            if use_proxy:
                log.info(f"[{self.name}] 使用代理: {use_proxy}")
            else:
                log.info(f"[{self.name}] 不使用代理 (直连)")

            # 4. 发起请求
            log.info(f"[{self.name}] 发起请求: {url} (尝试 {attempt + 1}/{self.retries + 1})")

            try:
                resp = self._do_request(
                    url=url,
                    method=method,
                    headers=safe_headers,
                    cookies=creds["cookies"],
                    data=data,
                    json=json,
                    data_encoding=data_encoding,
                    proxy=use_proxy,
                )

                # 5. 检查是否被拦截
                if self._is_blocked(resp):
                    if attempt < self.retries:
                        log.warning(f"[{self.name}] 被拦截，刷新缓存重试...")
                        continue
                    else:
                        log.error(f"[{self.name}] 重试后仍被拦截")

                return resp

            except Exception as e:
                log.error(f"[{self.name}] 请求异常: {e}")
                if attempt == self.retries:
                    raise

        # 不应该到达这里
        raise Exception("Unexpected error in CookieFetcher")

    def _build_safe_headers(
        self, headers: Dict[str, str], ua: str, url: str, method: str
    ) -> Dict[str, str]:
        """构造安全的请求头，过滤可能冲突的字段"""
        blocked_headers = {
            "host",
            "content-length",
            "user-agent",
            "accept-encoding",
            "cookie",
        }
        safe = {k: v for k, v in headers.items() if k.lower() not in blocked_headers}
        safe["User-Agent"] = ua

        # 对于 POST/PUT/PATCH 等修改性请求，添加必要的浏览器请求头
        if method.upper() in ["POST", "PUT", "PATCH", "DELETE"]:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"

            # 添加 Referer（通常是同域名的首页或当前URL）
            if "referer" not in {k.lower() for k in safe.keys()}:
                safe["Referer"] = url

            # 添加 Origin
            if "origin" not in {k.lower() for k in safe.keys()}:
                safe["Origin"] = origin

            # 添加 Accept
            if "accept" not in {k.lower() for k in safe.keys()}:
                safe["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"

        return safe

    def _do_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        cookies: Dict[str, str],
        data: Optional[Dict[str, Any]],
        json: Optional[Dict[str, Any]],
        data_encoding: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> FetchResponse:
        """执行实际的 HTTP 请求"""
        # 处理 data 编码（如 GBK）
        request_data = data
        if data and data_encoding:
            from urllib.parse import urlencode, parse_qs
            if isinstance(data, dict):
                # dict 直接编码
                encoded_str = urlencode(data, encoding=data_encoding)
                request_data = encoded_str
                log.info(f"[{self.name}] 使用 {data_encoding} 编码 POST 数据 (dict)")
            elif isinstance(data, str):
                # 字符串需要先解析再重新编码
                parsed = parse_qs(data, keep_blank_values=True)
                # parse_qs 返回 {key: [value]} 格式，转为 {key: value}
                flat_dict = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
                encoded_str = urlencode(flat_dict, encoding=data_encoding)
                request_data = encoded_str
                log.info(f"[{self.name}] 使用 {data_encoding} 编码 POST 数据 (str -> re-encode)")

        request_kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
            "cookies": cookies,
            "data": request_data,
            "json": json,
            "timeout": self.timeout,
            "allow_redirects": True,
        }

        if proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        # 方案3: 如果指定了 impersonate，添加到请求参数
        if self.impersonate:
            request_kwargs["impersonate"] = self.impersonate

        resp = curl_requests.request(**request_kwargs)

        # 转换为统一的 FetchResponse
        return FetchResponse(
            status_code=resp.status_code,
            content=resp.content,
            text=resp.text,
            headers=dict(resp.headers),
            cookies=resp.cookies.get_dict() if hasattr(resp.cookies, 'get_dict') else dict(resp.cookies),
            url=str(resp.url),
            encoding=resp.encoding or "utf-8",
        )

    def _is_blocked(self, resp: FetchResponse) -> bool:
        """检查响应是否被 Cloudflare 或其他反爬机制拦截"""
        log.info(f"[{self.name}] 检查拦截: status={resp.status_code}, content_length={len(resp.text)}")

        # 1. 检查状态码
        if resp.status_code in [403, 503, 429]:
            log.warning(f"[{self.name}] 状态码 {resp.status_code} 表示被拦截")
            # Cloudflare 特征
            if "Just a moment" in resp.text or "Cloudflare" in resp.text:
                log.warning(f"[{self.name}] 检测到 Cloudflare 拦截页面")
                return True
            # 通用拦截特征
            if "cf-ray" in resp.headers.get("cf-ray", "").lower():
                return True
            # 即使没有明确特征，403/503/429 也视为拦截
            return True

        # 2. 检查响应头中的 Cloudflare 标记
        if resp.headers.get("cf-mitigated") == "challenge":
            log.warning(f"[{self.name}] 检测到 cf-mitigated=challenge 响应头")
            return True

        # 3. 检查页面内容特征（即使状态码是 200）
        # 只检查页面前 10000 字符，避免大页面性能问题
        check_text = resp.text[:10000] if len(resp.text) > 10000 else resp.text
        if resp.status_code == 200:
            blocked_patterns = [
                "cf-turnstile",  # Cloudflare Turnstile
                "challenge-platform",  # Cloudflare 挑战
                "_cf_chl_opt",  # Cloudflare 挑战选项
                "challenges.cloudflare.com/turnstile",  # Turnstile 脚本
            ]
            for pattern in blocked_patterns:
                if pattern in check_text:
                    log.warning(f"[{self.name}] 检测到拦截特征: {pattern}")
                    return True

        log.info(f"[{self.name}] 未检测到拦截特征，请求成功")
        return False
