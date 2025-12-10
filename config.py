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
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--lang=en-US"
    ]

    # 缓存配置
    COOKIE_EXPIRE_SECONDS: int = 1800  # Cookie 30分钟过期

    class Config:
        env_file = ".env"

settings = Settings()
