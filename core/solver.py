import time
from core.browser_pool import browser_pool
from utils.logger import log


def solve_turnstile(url: str):
    """
    核心过盾逻辑
    返回: {"cookies": dict, "ua": str}
    """
    # 从浏览器池获取实例
    instance = browser_pool.acquire(timeout=60)
    if not instance:
        raise Exception("无法获取浏览器实例，池已满")

    page = instance.page

    try:
        log.info(f"🕵️ 正在访问: {url} (浏览器 PID: {instance.pid})")

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
            log.error("❌ 验证超时")
            raise Exception("Cloudflare Bypass Timeout")

        # 3. 提取凭证
        raw_cookies = page.cookies()

        cookie_dict = {}

        # 通用一点的兼容处理：
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
            except Exception as e:
                log.error(f"⚠️ cookie 解析失败: {e}")
                cookie_dict = {}

        ua = page.user_agent

        log.info(f"[solver] raw_cookies 类型: {type(raw_cookies)}")
        log.info(f"[solver] 提取后的 cookie_dict: {cookie_dict}")
        log.info(f"[solver] 提取到的 UA: {ua}")

        return {
            "cookies": cookie_dict,
            "ua": ua
        }

    except Exception as e:
        log.error(f"💥 过盾过程异常: {e}")
        raise e

    finally:
        # 无论成功失败，都归还浏览器到池中
        browser_pool.release(instance)
