"""
缓存服务 - 管理 Cloudflare 过盾凭证的缓存

提供凭证 (Cookie + User-Agent) 的缓存管理，避免重复过盾。

特性:
- 按域名缓存凭证
- 支持过期时间配置
- 支持强制刷新
- 线程安全
"""

import time
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from config import settings
from core.solver import solve_turnstile
from utils.logger import log


class CredentialCache:
    """凭证缓存管理器

    管理 Cloudflare 过盾后获取的 Cookie 和 User-Agent，
    按域名进行缓存，支持过期自动刷新。
    """

    def __init__(self, expire_seconds: Optional[int] = None):
        """
        Args:
            expire_seconds: 缓存过期时间 (秒)，默认使用配置文件中的值
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.expire_seconds = expire_seconds or settings.COOKIE_EXPIRE_SECONDS

    def get_credentials(
        self, url: str, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """获取指定 URL 的凭证

        Args:
            url: 目标 URL
            force_refresh: 是否强制刷新缓存

        Returns:
            dict: {"cookies": dict, "ua": str}
        """
        domain = urlparse(url).netloc
        now = time.time()

        with self._lock:
            cached = self._cache.get(domain)

            # 检查缓存是否有效
            if not force_refresh and cached and cached["expire"] > now:
                log.info(f"[Cache] 命中缓存: {domain}")
                return cached["data"]

        # 缓存无效，需要重新过盾
        log.info(f"[Cache] 启动过盾流程: {domain}")
        creds = solve_turnstile(url)

        # 写入缓存
        with self._lock:
            self._cache[domain] = {
                "data": creds,
                "expire": now + self.expire_seconds,
            }

        return creds

    def invalidate(self, domain: str) -> bool:
        """使指定域名的缓存失效

        Args:
            domain: 域名

        Returns:
            bool: 是否成功删除缓存
        """
        with self._lock:
            if domain in self._cache:
                del self._cache[domain]
                log.info(f"[Cache] 已清除缓存: {domain}")
                return True
            return False

    def invalidate_all(self) -> int:
        """清除所有缓存

        Returns:
            int: 清除的缓存数量
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            log.info(f"[Cache] 已清除所有缓存，共 {count} 条")
            return count

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息

        Returns:
            dict: 缓存统计信息
        """
        with self._lock:
            now = time.time()
            valid_count = sum(
                1 for v in self._cache.values() if v["expire"] > now
            )
            return {
                "total": len(self._cache),
                "valid": valid_count,
                "expired": len(self._cache) - valid_count,
                "domains": list(self._cache.keys()),
            }


# 全局单例
credential_cache = CredentialCache()
