import os
import sys
import time
from typing import Dict, Optional

from DrissionPage import ChromiumOptions, ChromiumPage
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

IS_LINUX = sys.platform.startswith("linux")

if IS_LINUX:
    from pyvirtualdisplay import Display


class BypassResult(BaseModel):
    success: bool
    title: str
    token: Optional[str]
    message: str
    screenshot_path: str


app = FastAPI(title="Turnstile Bypass Service", version="1.0.0")


def get_turnstile_token(page: ChromiumPage) -> Optional[str]:
    """
    逻辑来源: cwwn/cf-rg
    功能: 穿透 Shadow DOM 点击 Cloudflare 验证框
    """
    print("🔄 正在检测 Turnstile 验证...")

    try:
        token = page.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
        if token:
            print("✅ [自动通过] 检测到 Token！")
            return token
    except Exception:
        pass

    try:
        challenge_solution = page.ele("@name=cf-turnstile-response", timeout=10)

        if challenge_solution:
            print("👁️ 发现验证组件，正在定位点击位置...")
            challenge_wrapper = challenge_solution.parent()

            iframe = challenge_wrapper.shadow_root.ele("tag:iframe")
            checkbox = iframe.ele("tag:body").shadow_root.ele("tag:input")

            if checkbox:
                print("👆 正在点击验证框...")
                time.sleep(0.5)
                checkbox.click()

                print("⏳ 点击完成，等待 3 秒验证结果...")
                time.sleep(3)

                token = page.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
                if token:
                    print("✅ [点击通过] 验证成功！Token 已获取。")
                    return token
        else:
            print("⚠️ 未找到 Turnstile 元素，可能已通过或页面结构改变。")

    except Exception as e:
        print(f"❌ 尝试过盾时发生异常: {e}")

    return None


def create_page() -> Dict[str, Optional[object]]:
    display = None

    if IS_LINUX:
        display = Display(visible=0, size=(1920, 1080))
        display.start()
        print("🖥️  虚拟显示器已启动")

    co = ChromiumOptions()

    if IS_LINUX:
        co.set_browser_path("/usr/bin/google-chrome")

    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--lang=en-US")

    co.headless(False)

    page = ChromiumPage(co)

    return {"page": page, "display": display}


def bypass_turnstile(target_url: str = "https://nowsecure.in") -> BypassResult:
    resources = create_page()
    page = resources["page"]
    display = resources["display"]

    try:
        print(f"🚀 正在访问: {target_url}")
        page.get(target_url)

        time.sleep(2)

        token = get_turnstile_token(page)

        print("📸 正在截图保存状态...")
        screenshot_path = os.path.join(os.getcwd(), "bypass_result.png")
        page.get_screenshot(path=os.path.dirname(screenshot_path), name=os.path.basename(screenshot_path))

        title = page.title
        content = page.html

        if "Just a moment" in title:
            message = f"❌ 失败：依然停留在 Cloudflare 等待界面 (Title: {title})"
            success = False
        elif "OH YEAH" in content or "Security Check" not in title:
            message = f"🎉 成功！当前标题: {title}"
            success = True
        else:
            message = f"❓ 状态未知，标题: {title}"
            success = False

        return BypassResult(
            success=success,
            title=title,
            token=token,
            message=message,
            screenshot_path=screenshot_path,
        )
    except Exception as e:
        print(f"💥 程序崩溃: {e}")
        raise
    finally:
        page.quit()
        if display:
            display.stop()


@app.post("/bypass", response_model=BypassResult)
def bypass_endpoint(target_url: str = "https://nowsecure.in") -> BypassResult:
    try:
        return bypass_turnstile(target_url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
