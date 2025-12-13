
"""
代理管理服务 - 负责 IP 轮换逻辑
"""
import random
import os
from typing import Optional, List
from config import settings
from utils.logger import log

class ProxyManager:
    def __init__(self):
        self._proxies: List[str] = []
        self.reload()

    def reload(self):
        """重新加载代理列表"""
        # 1. 尝试从文件加载
        if os.path.exists(settings.PROXIES_FILE):
            try:
                with open(settings.PROXIES_FILE, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
                    self._proxies = lines
                    log.info(f"[ProxyManager] Loaded {len(self._proxies)} proxies from file")
            except Exception as e:
                log.error(f"[ProxyManager] Failed to load proxies from file: {e}")
        
        # 2. 尝试从环境变量加载 (PROXIES="p1,p2")
        env_proxies = os.getenv("PROXIES", "")
        if env_proxies:
            proxies = [p.strip() for p in env_proxies.split(",") if p.strip()]
            self._proxies.extend(proxies)
            log.info(f"[ProxyManager] Loaded {len(proxies)} proxies from ENV")

        # Normalize and Deduplicate
        self._proxies = [self._normalize(p) for p in self._proxies]
        self._proxies = list(set(self._proxies))
        log.info(f"[ProxyManager] Total proxies available: {len(self._proxies)}")

    def _normalize(self, proxy: str) -> str:
        """标准化代理格式"""
        proxy = proxy.strip()
        if "://" not in proxy:
            return f"http://{proxy}"
        return proxy

    def get_proxy(self) -> Optional[str]:
        """获取一个代理 (随机策略)"""
        if not self._proxies:
            return None
        return random.choice(self._proxies)

    def get_all(self) -> List[str]:
        return self._proxies

# 全局单例
proxy_manager = ProxyManager()
