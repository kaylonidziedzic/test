"""
配置持久化服务 - 将运行时配置保存到文件
"""
import json
import os
from typing import Dict, Any

from config import settings
from utils.logger import log

CONFIG_FILE = "data/config.json"


def init_config():
    """启动时加载持久化配置"""
    if not os.path.exists(CONFIG_FILE):
        log.info("[ConfigStore] 配置文件不存在，使用默认配置")
        return

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 应用配置到 settings
        if "cookie_expire_seconds" in config:
            settings.COOKIE_EXPIRE_SECONDS = config["cookie_expire_seconds"]
        if "memory_limit_mb" in config:
            settings.MEMORY_LIMIT_MB = config["memory_limit_mb"]
        if "watchdog_interval" in config:
            settings.WATCHDOG_INTERVAL = config["watchdog_interval"]
        if "fingerprint_enabled" in config:
            settings.FINGERPRINT_ENABLED = config["fingerprint_enabled"]
        if "browser_pool_min" in config:
            settings.BROWSER_POOL_MIN = config["browser_pool_min"]
        if "browser_pool_max" in config:
            settings.BROWSER_POOL_MAX = config["browser_pool_max"]
        if "browser_pool_idle_timeout" in config:
            settings.BROWSER_POOL_IDLE_TIMEOUT = config["browser_pool_idle_timeout"]

        log.info(f"[ConfigStore] 已加载持久化配置: {config}")
    except Exception as e:
        log.error(f"[ConfigStore] 加载配置失败: {e}")


def save_config(config: Dict[str, Any]):
    """保存配置到文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        log.info(f"[ConfigStore] 配置已保存到 {CONFIG_FILE}")
    except Exception as e:
        log.error(f"[ConfigStore] 保存配置失败: {e}")


def load_config() -> Dict[str, Any]:
    """读取配置文件"""
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"[ConfigStore] 读取配置失败: {e}")
        return {}
