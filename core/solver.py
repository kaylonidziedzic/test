import time
from config import settings
from core.browser_pool import browser_pool
from utils.logger import log

# 过盾超时时间（秒），可通过配置覆盖
SOLVE_TIMEOUT = getattr(settings, 'SOLVE_TIMEOUT', 30)


def solve_turnstile(url: str, proxy: str = None):
    """
    核心过盾逻辑
    返回: {"cookies": dict, "ua": str}

    Args:
        url: 目标 URL
        proxy: 代理地址，None 表示不使用代理，"pool" 表示从代理池获取
    """
    # 从浏览器池获取实例，传递代理参数
    instance = browser_pool.acquire(timeout=60, proxy=proxy)
    if not instance:
        raise Exception("无法获取浏览器实例，池已满")

    page = instance.page

    try:
        log.info(f"🕵️ 正在访问: {url} (浏览器 PID: {instance.pid})")

        page.get(url)

        start_time = time.time()
        success = False
        click_count = 0
        last_click_time = 0

        while time.time() - start_time < SOLVE_TIMEOUT:
            title = page.title.lower()

            # 1. 尝试点击验证 (支持多次验证)
            try:
                box = page.ele("@name=cf-turnstile-response", timeout=0.5)
                if box:
                    wrapper = box.parent()
                    iframe = wrapper.shadow_root.ele("tag:iframe")
                    cb = iframe.ele("tag:body").shadow_root.ele("tag:input")
                    # 避免频繁点击，至少间隔1.5秒
                    if cb and (time.time() - last_click_time) > 1.5:
                        click_count += 1
                        log.info(f"👆 发现验证码，第 {click_count} 次点击...")
                        cb.click()
                        last_click_time = time.time()
            except Exception as e:
                # 只记录非预期的异常
                if "timeout" not in str(e).lower() and "not found" not in str(e).lower():
                    log.debug(f"[solver] 验证码检测异常: {e}")

            # 2. 判断成功条件：标题正常且没有验证码
            if "just a moment" not in title and "cloudflare" not in title:
                # 额外检查：确保没有验证码元素
                try:
                    still_has_turnstile = page.ele("@name=cf-turnstile-response", timeout=0.3)
                    if still_has_turnstile:
                        log.debug("[solver] 标题已变但验证码仍存在，继续等待...")
                        time.sleep(0.5)
                        continue
                except Exception:
                    pass  # 没有验证码元素，说明真的过盾了

                log.success(f"✅ 过盾成功，当前标题: {title} (点击次数: {click_count})")
                # 等待 cf_clearance Cookie 设置完成
                time.sleep(1)
                success = True
                break

            time.sleep(0.5)

        if not success:
            log.error(f"❌ 验证超时 ({SOLVE_TIMEOUT}秒)，点击次数: {click_count}")
            raise Exception(f"Cloudflare Bypass Timeout after {click_count} clicks")

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

        # 检查是否有 cf_clearance（Cloudflare 验证通过的关键 Cookie）
        if "cf_clearance" not in cookie_dict:
            log.warning("[solver] ⚠️ 未检测到 cf_clearance Cookie，可能过盾不完整")

        return {
            "cookies": cookie_dict,
            "ua": ua
        }

    except Exception as e:
        import traceback
        error_msg = str(e) if str(e) else type(e).__name__
        log.error(f"💥 过盾过程异常: {error_msg}")
        log.error(f"💥 异常堆栈:\n{traceback.format_exc()}")
        # 标记浏览器实例为损坏，需要销毁而非归还
        instance._is_broken = True
        raise

    finally:
        # 检查浏览器是否损坏
        is_broken = getattr(instance, '_is_broken', False)
        if is_broken:
            # 损坏的实例需要销毁并从池中移除
            log.warning(f"[solver] 浏览器实例已损坏，销毁 PID: {instance.pid}")
            browser_pool.destroy(instance)
        else:
            # 归还前清理页面状态，避免复用时出现问题
            try:
                page.get("about:blank")
            except Exception:
                pass
            # 正常归还到池中
            browser_pool.release(instance)
