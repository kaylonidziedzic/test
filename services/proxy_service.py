import time
import requests
from core.solver import solve_turnstile
from utils.logger import log
from config import settings

# 内存缓存: { "domain": { "data": {...}, "expire": timestamp } }
CACHE = {}

def get_credentials(url: str, force_refresh: bool = False):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    
    now = time.time()
    cached = CACHE.get(domain)

    # 1. 检查缓存是否有效
    if not force_refresh and cached and cached['expire'] > now:
        log.info(f"💾 命中缓存: {domain}")
        return cached['data']
    
    # 2. 调用浏览器过盾
    log.info(f"⚡ 启动过盾流程: {domain}")
    creds = solve_turnstile(url)
    
    # 3. 写入缓存
    CACHE[domain] = {
        "data": creds,
        "expire": now + settings.COOKIE_EXPIRE_SECONDS
    }
    return creds

def proxy_request(url: str, method: str, headers: dict, data: dict = None, json: dict = None):
    """代理请求核心逻辑"""
    retries = 1
    for i in range(retries + 1):
        # 首次尝试用缓存，重试时强制刷新
        force = (i > 0)
        creds = get_credentials(url, force_refresh=force)
        
        # 构造请求头 (必须使用过盾时的 UA)
        # 移除可能导致冲突的 headers
        safe_headers = {k: v for k, v in headers.items() if k.lower() not in ['host', 'content-length', 'user-agent']}
        safe_headers['User-Agent'] = creds['ua']
        
        try:
            resp = requests.request(
                method=method,
                url=url,
                cookies=creds['cookies'],
                headers=safe_headers,
                data=data,
                json=json,
                timeout=30,
                allow_redirects=True # 让requests自动处理跳转
            )
            
            # 检查是否依然被拦截 (反爬工程师的直觉)
            if resp.status_code in [403, 503]:
                if "Just a moment" in resp.text or "Cloudflare" in resp.text:
                    if i < retries:
                        log.warning("🛡️ 依然被拦截，正在重试并刷新缓存...")
                        continue
                    else:
                        log.error("❌ 重试后依然失败")
            
            return resp
            
        except Exception as e:
            log.error(f"网络请求异常: {e}")
            raise e
