
"""
缓存服务 - 管理 Cloudflare 过盾凭证的缓存

提供凭证 (Cookie + User-Agent) 的缓存管理，避免重复过盾。
支持 SQLite (本地) 和 Redis (分布式/Serverless) 两种后端。
"""

import json
import os
import sqlite3
import time
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from urllib.parse import urlparse

import redis
from config import settings
from core.solver import solve_turnstile
from utils.logger import log


class BaseCache(ABC):
    """缓存接口基类"""

    def __init__(self, expire_seconds: int):
        self.expire_seconds = expire_seconds

    @abstractmethod
    def get_credentials(self, url: str, force_refresh: bool = False, proxy: str = None) -> Dict[str, Any]:
        """获取凭证，proxy 参数会传递给过盾流程"""
        pass

    @abstractmethod
    def invalidate(self, domain: str) -> bool:
        pass

    @abstractmethod
    def invalidate_all(self) -> int:
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        pass
    
    def _extract_domain(self, url: str) -> str:
        return urlparse(url).netloc


class SQLiteCache(BaseCache):
    """SQLite 缓存实现 (单机模式)"""

    def __init__(self, expire_seconds: int, db_path: str):
        super().__init__(expire_seconds)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            log.info(f"[Cache:SQLite] 创建数据目录: {db_dir}")

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
                log.info(f"[Cache:SQLite] 数据库已初始化: {self.db_path}")
            finally:
                conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_credentials(self, url: str, force_refresh: bool = False, proxy: str = None) -> Dict[str, Any]:
        domain = self._extract_domain(url)
        now = time.time()

        if not force_refresh:
            with self._lock:
                conn = self._get_conn()
                try:
                    cursor = conn.execute(
                        "SELECT cookies, ua, expire_at FROM credentials WHERE domain = ?",
                        (domain,)
                    )
                    row = cursor.fetchone()
                    if row and row[2] > now:
                        log.info(f"[Cache:SQLite] 命中缓存: {domain}")
                        return {"cookies": json.loads(row[0]), "ua": row[1]}
                finally:
                    conn.close()

        # 缓存无效，需要重新过盾
        log.info(f"[Cache:SQLite] 启动过盾流程: {domain}")
        creds = solve_turnstile(url, proxy=proxy)

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
                log.info(f"[Cache:SQLite] 凭证已持久化: {domain}")
            finally:
                conn.close()

        return creds

    def invalidate(self, domain: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("DELETE FROM credentials WHERE domain = ?", (domain,))
                conn.commit()
                if cursor.rowcount > 0:
                    log.info(f"[Cache:SQLite] 已清除缓存: {domain}")
                    return True
                return False
            finally:
                conn.close()

    def invalidate_all(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM credentials")
                count = cursor.fetchone()[0]
                conn.execute("DELETE FROM credentials")
                conn.commit()
                log.info(f"[Cache:SQLite] 已清除所有缓存，共 {count} 条")
                return count
            finally:
                conn.close()

    def cleanup_expired(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                now = time.time()
                cursor = conn.execute("DELETE FROM credentials WHERE expire_at < ?", (now,))
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    log.info(f"[Cache:SQLite] 已清理过期缓存: {count} 条")
                return count
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
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
                    "type": "sqlite",
                    "total": total,
                    "valid": valid,
                    "expired": total - valid,
                    "domains": domains,
                    "db_path": self.db_path,
                }
            finally:
                conn.close()


class RedisCache(BaseCache):
    """Redis 缓存实现 (分布式模式)"""

    def __init__(self, expire_seconds: int, redis_url: str):
        super().__init__(expire_seconds)
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.prefix = "cred:"
        log.info(f"[Cache:Redis] 已连接到 Redis: {redis_url}")

    def _get_key(self, domain: str) -> str:
        return f"{self.prefix}{domain}"

    def get_credentials(self, url: str, force_refresh: bool = False, proxy: str = None) -> Dict[str, Any]:
        domain = self._extract_domain(url)
        key = self._get_key(domain)

        if not force_refresh:
            try:
                data = self.redis_client.get(key)
                if data:
                    log.info(f"[Cache:Redis] 命中缓存: {domain}")
                    return json.loads(data)
            except redis.RedisError as e:
                log.error(f"[Cache:Redis] 读取失败: {e}")

        # 缓存无效，过盾
        log.info(f"[Cache:Redis] 启动过盾流程: {domain}")
        creds = solve_turnstile(url, proxy=proxy)

        # 写入 Redis
        try:
            # 存储格式: {"cookies": ..., "ua": ...}
            # 设置过期时间
            self.redis_client.setex(
                key,
                self.expire_seconds,
                json.dumps(creds)
            )
            log.info(f"[Cache:Redis] 凭证已缓存: {domain} (TTL={self.expire_seconds}s)")
        except redis.RedisError as e:
            log.error(f"[Cache:Redis] 写入失败: {e}")

        return creds

    def invalidate(self, domain: str) -> bool:
        key = self._get_key(domain)
        try:
            return bool(self.redis_client.delete(key))
        except redis.RedisError as e:
            log.error(f"[Cache:Redis] 删除失败: {e}")
            return False

    def invalidate_all(self) -> int:
        try:
            keys = self.redis_client.keys(f"{self.prefix}*")
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except redis.RedisError as e:
            log.error(f"[Cache:Redis] 批量删除失败: {e}")
            return 0

    def cleanup_expired(self) -> int:
        # Redis 自动处理过期，无需手动清理
        return 0

    def get_stats(self) -> Dict[str, Any]:
        try:
            keys = self.redis_client.keys(f"{self.prefix}*")
            return {
                "type": "redis",
                "total": len(keys),
                "valid": len(keys),  # Redis 中存在的 keys 都是未过期的
                "expired": 0,
                "domains": [k.replace(self.prefix, "") for k in keys],
            }
        except redis.RedisError as e:
            log.error(f"[Cache:Redis] 获取统计失败: {e}")
            return {"type": "redis", "error": str(e)}


# 工厂函数
def create_cache() -> BaseCache:
    expire = settings.COOKIE_EXPIRE_SECONDS
    
    # 优先使用 Redis (如果配置了 REDIS_URL 且不仅仅是默认值) -> 实际上 docker-compose 里都有默认值
    # 我们可以引入一个新的配置项 CACHE_TYPE 或者简单判断
    redis_url = getattr(settings, "REDIS_URL", None)
    
    # 简单的判断策略: 如果环境变量显式设置了 USE_REDIS_CACHE=true 或者检测到 REDIS_URL 非空
    # 这里我们复用 settings.REDIS_URL。如果用户没配，可能会报错，所以要注意。
    # 现有的 config.py 给 REDIS_URL 默认值了吗？检查一下。
    # 在 config.py 中: REDIS_URL: str = "redis://localhost:6379"
    
    # 我们通过检测是否能连接 Redis 或者通过显式开关来决定
    # 为了稳健，我们尝试连接一次 Redis，如果失败则回退到 SQLite? 
    # 或者如果不希望自动回退（为了避免隐式行为），我们硬编码目前使用 Redis 类。
    
    if redis_url and "localhost" not in redis_url and "127.0.0.1" not in redis_url:
        # 生产环境通常不会是 localhost，或者我们在 docker-compose 里设置为 redis://redis:6379
        return RedisCache(expire, redis_url)
    
    # 在 Docker 环境下，REDIS_URL 是 redis://redis:6379 (hostname 不含 localhost)
    if redis_url and "redis" in redis_url: 
         return RedisCache(expire, redis_url)

    # 默认回退到 SQLite (本地开发方便)
    # 但由于本次任务明确是迁移到 Redis，我们强制优先尝试 Redis
    try:
        if redis_url:
            cache = RedisCache(expire, redis_url)
            # 测试连接
            cache.redis_client.ping()
            return cache
    except Exception as e:
        log.warning(f"[Cache] Redis 连接失败 ({e})，降级到 SQLite")

    return SQLiteCache(expire, settings.CACHE_DB_PATH)


# 全局单例
credential_cache = create_cache()
