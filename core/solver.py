import time
from core.browser import browser_manager
from utils.logger import log

def solve_turnstile(url: str):
    """
    核心过盾逻辑
    返回: {"cookies": dict, "ua": str}
    """
    page = browser_manager.get_browser()
    
    try:
        log.info(f"🕵️ 正在访问: {url}")
        
        with browser_manager._lock:
            page.get(url)
            
            start_time = time.time()
            success = False
            
            while time.time() - start_time < 20:  # 最多等待20秒
                title = page.title.lower()
                
                # 1. 尝试点击验证 (如果存在)
                try:
                    box = page.ele("@name=cf-turnstile-response", timeout=1)
                    if box:
                        wrapper = box.parent()
                        iframe = wrapper.shadow_root.ele("tag:iframe")
                        cb = iframe.ele("tag:body").shadow_root.ele("tag:input")
                        if cb:
                            log.info("👆 发现验证码，点击中...")
                            cb.click()
                except:
                    pass

                # 2. 判断成功条件
                if "just a moment" not in title and "cloudflare" not in title:
                    log.success(f"✅ 过盾成功，当前标题: {title}")
                    success = True
                    break
                
                time.sleep(1)
            
            if not success:
                err_img = page.get_screenshot(as_base64=True)
                log.error("❌ 验证超时")
                raise Exception("Cloudflare Bypass Timeout")

            # 3. 提取凭证 —— 这里用同步 API，就不要 await 了
            # 3. 提取凭证
            raw_cookies = page.cookies()  # DrissionPage 返回的很可能是 list

            cookie_dict = {}

            # 通用一点的兼容处理：
            if isinstance(raw_cookies, dict):
                # 已经是 dict 了，直接用
                cookie_dict = raw_cookies
            elif isinstance(raw_cookies, list):
                # list 里通常是 dict 或 (name, value) 形式
                for c in raw_cookies:
                    if isinstance(c, dict) and "name" in c and "value" in c:
                        cookie_dict[c["name"]] = c["value"]
                    elif isinstance(c, (list, tuple)) and len(c) >= 2:
                        cookie_dict[c[0]] = c[1]
            else:
                # 万一是 CookieJar 之类的东西
                try:
                    cookie_dict = dict(raw_cookies)
                except Exception as e:
                    log.error(f"⚠️ cookie 解析失败: {e}")
                    cookie_dict = {}

            ua = page.user_agent

            # 🔍 这里是新增的日志，方便你看浏览器里到底拿到了什么
            log.info(f"[solver] raw_cookies 类型: {type(raw_cookies)}")
            log.info(f"[solver] 提取后的 cookie_dict: {cookie_dict}")
            log.info(f"[solver] 提取到的 UA: {ua}")

            return {
                "cookies": cookie_dict,
                "ua": ua
            }


    except Exception as e:
        log.error(f"💥 过盾过程异常: {e}")
        browser_manager.restart()
        raise e
