import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 服务配置
    API_TITLE: str = "CF-Gateway-Pro"
    API_KEY: str = "change_me_please"  # 简单的鉴权密钥
    PORT: int = 8000
    
    # 浏览器配置
    HEADLESS: bool = False  # Linux下通常需要配合xvfb，DrissionPage建议False以过盾
    BROWSER_ARGS: list = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--lang=en-US,en",
        # 反检测参数
        "--disable-blink-features=AutomationControlled",  # 关键：禁用自动化控制特征
        "--disable-infobars",  # 禁用信息栏
        "--disable-extensions",  # 禁用扩展
        "--disable-default-apps",  # 禁用默认应用
        "--disable-component-extensions-with-background-pages",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=TranslateUI",
        "--metrics-recording-only",
        "--no-first-run",
        "--password-store=basic",
        "--use-mock-keychain",
        # 窗口大小（模拟真实用户）
        "--window-size=1920,1080",
        "--start-maximized",
    ]

    # 缓存配置
    COOKIE_EXPIRE_SECONDS: int = 1800  # Cookie 30分钟过期
    CACHE_DB_PATH: str = "data/cache.db"  # SQLite 数据库路径

    # 内存看门狗配置
    MEMORY_LIMIT_MB: int = 1500  # 浏览器内存超过此值则重启 (MB)
    WATCHDOG_INTERVAL: int = 300  # 看门狗检查间隔 (秒)

    # 指纹随机化配置
    FINGERPRINT_ENABLED: bool = True  # 是否启用 Canvas/WebGL 指纹随机化

    # 浏览器池配置
    BROWSER_POOL_MIN: int = 1  # 最小浏览器数量
    BROWSER_POOL_MAX: int = 3  # 最大浏览器数量
    BROWSER_POOL_IDLE_TIMEOUT: int = 300  # 空闲超时回收时间 (秒)

    class Config:
        env_file = ".env"

settings = Settings()

# 域名编码映射表：用于自动编码 POST 请求数据
# 格式: "域名关键词": "编码"
DOMAIN_ENCODING_MAP = {
    "69shuba": "gbk",
    "69shu": "gbk",
    # 其他 GBK 编码的小说站
    "biquge": "gbk",
    "xbiquge": "gbk",
    "biquwu": "gbk",
    "23us": "gbk",
    "23wx": "gbk",
    "xxbiquge": "gbk",
    "shuquge": "gbk",
    "qu.la": "gbk",
    "qula": "gbk",
    "biqiuge": "gbk",
    "ibiquge": "gbk",
}


def get_encoding_for_domain(hostname: str) -> str:
    """根据域名获取编码，默认返回 None（使用 UTF-8）"""
    hostname_lower = hostname.lower()
    for domain_key, encoding in DOMAIN_ENCODING_MAP.items():
        if domain_key in hostname_lower:
            return encoding
    return None
