"""
缓存服务 - 管理 Cloudflare 过盾凭证的缓存

提供凭证 (Cookie + User-Agent) 的缓存管理，避免重复过盾。

特性:
- 按域名缓存凭证
- 支持过期时间配置
- 支持强制刷新
- 线程安全
- SQLite 持久化存储（重启不丢失）
"""

import json
import os
import sqlite3
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
    使用 SQLite 持久化存储，服务重启后缓存不丢失。
    """

    def __init__(self, expire_seconds: Optional[int] = None, db_path: Optional[str] = None):
        """
        Args:
            expire_seconds: 缓存过期时间 (秒)，默认使用配置文件中的值
            db_path: SQLite 数据库路径，默认使用配置文件中的值
        """
        self._lock = threading.Lock()
        self.expire_seconds = expire_seconds or settings.COOKIE_EXPIRE_SECONDS
        self.db_path = db_path or settings.CACHE_DB_PATH
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        # 确保数据目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            log.info(f"[Cache] 创建数据目录: {db_dir}")

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS credentials (
                        domain TEXT PRIMARY KEY,
                        cookies TEXT NOT NULL,
                        ua TEXT NOT NULL,
                        expire_at REAL NOT NULL,
                        created_at REAL NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_expire ON credentials(expire_at)")
                conn.commit()
                log.info(f"[Cache] SQLite 数据库已初始化: {self.db_path}")
            finally:
                conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（每个线程独立连接）"""
        return sqlite3.connect(self.db_path)

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

        if not force_refresh:
            # 尝试从数据库读取缓存
            with self._lock:
                conn = self._get_conn()
                try:
                    cursor = conn.execute(
                        "SELECT cookies, ua, expire_at FROM credentials WHERE domain = ?",
                        (domain,)
                    )
                    row = cursor.fetchone()
                    if row and row[2] > now:
                        log.info(f"[Cache] 命中缓存: {domain}")
                        return {"cookies": json.loads(row[0]), "ua": row[1]}
                finally:
                    conn.close()

        # 缓存无效，需要重新过盾
        log.info(f"[Cache] 启动过盾流程: {domain}")
        creds = solve_turnstile(url)

        # 写入数据库
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO credentials (domain, cookies, ua, expire_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    domain,
                    json.dumps(creds["cookies"]),
                    creds["ua"],
                    now + self.expire_seconds,
                    now
                ))
                conn.commit()
                log.info(f"[Cache] 凭证已持久化: {domain}")
            finally:
                conn.close()

        return creds

    def invalidate(self, domain: str) -> bool:
        """使指定域名的缓存失效

        Args:
            domain: 域名

        Returns:
            bool: 是否成功删除缓存
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("DELETE FROM credentials WHERE domain = ?", (domain,))
                conn.commit()
                if cursor.rowcount > 0:
                    log.info(f"[Cache] 已清除缓存: {domain}")
                    return True
                return False
            finally:
                conn.close()

    def invalidate_all(self) -> int:
        """清除所有缓存

        Returns:
            int: 清除的缓存数量
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM credentials")
                count = cursor.fetchone()[0]
                conn.execute("DELETE FROM credentials")
                conn.commit()
                log.info(f"[Cache] 已清除所有缓存，共 {count} 条")
                return count
            finally:
                conn.close()

    def cleanup_expired(self) -> int:
        """清理过期的缓存记录

        Returns:
            int: 清理的记录数量
        """
        with self._lock:
            conn = self._get_conn()
            try:
                now = time.time()
                cursor = conn.execute("DELETE FROM credentials WHERE expire_at < ?", (now,))
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    log.info(f"[Cache] 已清理过期缓存: {count} 条")
                return count
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息

        Returns:
            dict: 缓存统计信息
        """
        with self._lock:
            conn = self._get_conn()
            try:
                now = time.time()
                cursor = conn.execute("SELECT COUNT(*) FROM credentials")
                total = cursor.fetchone()[0]
                cursor = conn.execute("SELECT COUNT(*) FROM credentials WHERE expire_at > ?", (now,))
                valid = cursor.fetchone()[0]
                cursor = conn.execute("SELECT domain FROM credentials")
                domains = [row[0] for row in cursor.fetchall()]
                return {
                    "total": total,
                    "valid": valid,
                    "expired": total - valid,
                    "domains": domains,
                    "db_path": self.db_path,
                }
            finally:
                conn.close()


# 全局单例
credential_cache = CredentialCache()
