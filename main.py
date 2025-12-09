import time
import sys
import os
from DrissionPage import ChromiumPage, ChromiumOptions

# 判断是否在 Docker/Linux 环境下运行
IS_LINUX = sys.platform.startswith("linux")

if IS_LINUX:
    from pyvirtualdisplay import Display
    # 启动虚拟显示器
    display = Display(visible=0, size=(1920, 1080))
    display.start()
    print("🖥️  虚拟显示器已启动")

def get_turnstile_token(page):
    """
    逻辑来源: cwwn/cf-rg
    功能: 穿透 Shadow DOM 点击 Cloudflare 验证框
    """
    print("🔄 正在检测 Turnstile 验证...")
    
    # 1. 检查是否已经自动通过
    try:
        token = page.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
        if token:
            print("✅ [自动通过] 检测到 Token！")
            return token
    except:
        pass

    # 2. 如果没有通过，开始尝试点击
    try:
        # === 修复点：直接使用 page.ele 并带 timeout 参数 ===
        # 等待元素出现（最多10秒）
        challenge_solution = page.ele("@name=cf-turnstile-response", timeout=10)
        
        if challenge_solution:
            print("👁️  发现验证组件，正在定位点击位置...")
            challenge_wrapper = challenge_solution.parent()
            
            # 穿透 Shadow DOM
            iframe = challenge_wrapper.shadow_root.ele("tag:iframe")
            checkbox = iframe.ele("tag:body").shadow_root.ele("tag:input")
            
            if checkbox:
                print("👆 正在点击验证框...")
                time.sleep(0.5)
                checkbox.click()
                
                print("⏳ 点击完成，等待 3 秒验证结果...")
                time.sleep(3)
                
                # 再次检查
                token = page.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
                if token:
                    print("✅ [点击通过] 验证成功！Token 已获取。")
                    return token
        else:
            print("⚠️ 未找到 Turnstile 元素，可能已通过或页面结构改变。")
            
    except Exception as e:
        print(f"❌ 尝试过盾时发生异常: {e}")

    return None

def main():
    co = ChromiumOptions()
    
    # 路径设置
    if IS_LINUX:
        co.set_browser_path('/usr/bin/google-chrome')
    
    # 参数配置
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=en-US') 
    
    # === 关键：关闭 Headless ===
    co.headless(False)

    page = ChromiumPage(co)

    try:
        target_url = 'https://nowsecure.in'
        print(f"🚀 正在访问: {target_url}")
        page.get(target_url)
        
        # 等待页面加载
        time.sleep(2)
        
        # 执行过盾逻辑
        token = get_turnstile_token(page)
        
        # 截图保存
        print("📸 正在截图保存状态...")
        page.get_screenshot(path='result.png', name='bypass_result.png')
        
        # === 修复点：更严格的成功判断 ===
        # Cloudflare 的标题通常是 "Just a moment..." 或 "Attention Required!"
        # nowsecure.in 成功后的页面通常包含 "OH YEAH, you passed!"
        
        title = page.title
        content = page.html
        
        if "Just a moment" in title:
            print(f"❌ 失败：依然停留在 Cloudflare 等待界面 (Title: {title})")
        elif "OH YEAH" in content or "Security Check" not in title:
            print(f"🎉 成功！当前标题: {title}")
        else:
            print(f"❓ 状态未知，标题: {title}")

    except Exception as e:
        print(f"💥 程序崩溃: {e}")
    finally:
        page.quit()
        if IS_LINUX:
            display.stop()

if __name__ == "__main__":
    main()
