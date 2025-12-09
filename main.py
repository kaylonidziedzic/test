import asyncio
import random
import os
import uvicorn
from fastapi import FastAPI, Body
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

app = FastAPI()

# ==========================================
# 1. 核心补丁：CDP 坐标修复 + WebGL 显卡伪装
# ==========================================
# 我们把所有 JS 补丁整合在一起，确保在 stealth 之后执行
js_patches = """
(() => {
    console.log('[Stealth] Apply Custom Patches...');

    // --- Patch 1: Fix CDP MouseEvent screenX/Y ---
    try {
        const getScreenX = Object.getOwnPropertyDescriptor(MouseEvent.prototype, 'screenX').get;
        const getScreenY = Object.getOwnPropertyDescriptor(MouseEvent.prototype, 'screenY').get;
        Object.defineProperty(MouseEvent.prototype, 'screenX', {
            get: function() {
                if (this.isTrusted && getScreenX.call(this) === 0) return this.clientX + (window.screenX || 0);
                return getScreenX.call(this);
            }
        });
        Object.defineProperty(MouseEvent.prototype, 'screenY', {
            get: function() {
                if (this.isTrusted && getScreenY.call(this) === 0) return this.clientY + (window.screenY || 0);
                return getScreenY.call(this);
            }
        });
    } catch (e) { console.error(e); }

    // --- Patch 2: WebGL Vendor Spoofing (Docker Fix) ---
    // 伪装成普通的 Intel 集成显卡，掩盖 llvmpipe (虚拟渲染)
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // 37445: UNMASKED_VENDOR_WEBGL
            // 37446: UNMASKED_RENDERER_WEBGL
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics'; 
            return getParameter(parameter);
        };
        
        // 同时处理 WebGL2
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
            return getParameter2(parameter);
        };
    } catch (e) { console.error(e); }
})();
"""

playwright = None
browser = None

# 必须使用 Linux UA，因为 Docker 是 Linux 环境
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
]

@app.on_event("startup")
async def startup_event():
    global playwright, browser
    playwright = await async_playwright().start()
    
    # 启动参数精简优化
    browser = await playwright.chromium.launch(
        headless=False, # 配合 Xvfb
        args=[
            "--no-sandbox",
            "--disable-infobars",
            "--window-size=1920,1080",
            "--window-position=0,0",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled", 
            "--lang=en-US"
        ]
    )
    print("[Init] Browser launched.")

@app.on_event("shutdown")
async def shutdown_event():
    if browser: await browser.close()
    if playwright: await playwright.stop()

async def human_click(page, box):
    if not box: return False
    try:
        target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
        target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
        await page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()
        return True
    except:
        return False

async def solve_turnstile(page):
    try:
        # 遍历所有 Frame 寻找 checkbox
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                checkbox = frame.locator("input[type='checkbox']").first
                if await checkbox.count() > 0 and await checkbox.is_visible():
                    print("[Shield] Found checkbox, clicking...")
                    await human_click(page, await checkbox.bounding_box())
                    return True
                
                # 有时候是 shadow dom 里的 button
                # 盲点 Frame 中心
                body = frame.locator("body").first
                box = await body.bounding_box()
                if box:
                    # 只有当高度看起来像个 widget 时才点 (避免误点全屏 iframe)
                    if box['height'] < 200: 
                        print("[Shield] Blind clicking frame center...")
                        await human_click(page, box)
                        return True
    except Exception:
        pass
    return False

@app.post("/v1/bypass")
async def bypass_cloudflare(url: str = Body(..., embed=True)):
    context = None
    page = None
    try:
        ua = random.choice(USER_AGENTS)
        print(f"[Req] Processing: {url}")

        context = await browser.new_context(
            user_agent=ua,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            device_scale_factor=1
        )
        page = await context.new_page()
        
        # 1. 应用 playwright-stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        # 2. 注入我们的 WebGL + CDP 补丁
        await page.add_init_script(js_patches)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        except:
            pass

        success = False
        
        # 增加检测次数到 30次 (有的站点验证很慢)
        for i in range(30):
            title = await page.title()
            content = await page.content()
            cookies = await context.cookies()
            
            # 判定成功
            cf_cookie = next((c for c in cookies if c['name'] == 'cf_clearance'), None)
            if cf_cookie:
                print("[Req] Success: Cookie obtained.")
                success = True
                break
            
            # nowsecure.in 成功后标题通常不变，但内容会变
            if "OH NO" in content: # nowsecure 特有失败标志
                print("[Req] Failed: Detected 'OH NO' (Fingerprint detected).")
                break
                
            if "sc-bsatqv" in content or "hysteria" in content: # nowsecure 成功后的某些 CSS 类名
                print("[Req] Success: Content looks valid.")
                success = True
                break

            # 如果还在盾页面
            if "Just a moment" in title or "challenges.cloudflare.com" in content:
                # 只有在前几次尝试点击，后面主要是等待验证结果
                if i < 5: 
                    await solve_turnstile(page)
                if i % 5 == 0:
                    print(f"[Req] Verifying... ({i}/30)")
            else:
                # 既没盾，也没cookie，可能是没加载完，也可能是成功了
                # 截图判断比较准，但这里先假设多等几次
                pass
            
            await asyncio.sleep(1)

        if success:
            return {
                "status": "ok",
                "cookies": {c['name']: c['value'] for c in await context.cookies()},
                "user_agent": ua,
                "html": (await page.content())[:200]
            }
        else:
            await page.screenshot(path="debug_fail.png")
            return {"status": "fail", "message": "Verification Timeout or Failed"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if page: await page.close()
        if context: await context.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
