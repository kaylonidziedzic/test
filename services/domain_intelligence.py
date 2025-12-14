"""
域名智能学习服务 - Domain Intelligence Service

跟踪各域名的请求成功率，自动判断最佳访问策略：
- 记录 Cookie 模式和 Browser 模式的成功/失败次数
- 当 Cookie 模式失败率过高时，自动推荐切换到 Browser 模式
- 支持统计数据导出和手动重置
"""

import json
import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

from utils.logger import log

# 阈值配置
FAILURE_THRESHOLD = 0.5  # 失败率超过 50% 则推荐切换模式
MIN_SAMPLES = 5  # 至少需要 5 次请求才做判断
STATS_EXPIRE_HOURS = 24  # 统计数据保留 24 小时


@dataclass
class DomainStats:
    """域名统计数据"""
    domain: str
    cookie_success: int = 0
    cookie_failure: int = 0
    browser_success: int = 0
    browser_failure: int = 0
    last_updated: float = field(default_factory=time.time)
    recommended_mode: str = "cookie"  # cookie 或 browser

    @property
    def cookie_total(self) -> int:
        return self.cookie_success + self.cookie_failure

    @property
    def browser_total(self) -> int:
        return self.browser_success + self.browser_failure

    @property
    def cookie_failure_rate(self) -> float:
        if self.cookie_total == 0:
            return 0.0
        return self.cookie_failure / self.cookie_total

    @property
    def browser_failure_rate(self) -> float:
        if self.browser_total == 0:
            return 0.0
        return self.browser_failure / self.browser_total

    def update_recommendation(self):
        """根据统计数据更新推荐模式"""
        # 如果 Cookie 样本足够且失败率过高
        if self.cookie_total >= MIN_SAMPLES and self.cookie_failure_rate > FAILURE_THRESHOLD:
            self.recommended_mode = "browser"
            log.info(f"[DomainIntel] {self.domain} 推荐切换到 browser 模式 "
                     f"(Cookie 失败率: {self.cookie_failure_rate:.1%})")
        # 如果 Browser 模式表现良好且 Cookie 持续失败，保持 browser
        elif self.recommended_mode == "browser":
            # 检查是否可以恢复到 cookie 模式
            # 条件：最近没有 cookie 请求，或者 cookie 失败率已下降
            if self.cookie_total < MIN_SAMPLES or self.cookie_failure_rate <= FAILURE_THRESHOLD * 0.5:
                self.recommended_mode = "cookie"
                log.info(f"[DomainIntel] {self.domain} 恢复到 cookie 模式")


class DomainIntelligence:
    """域名智能学习服务"""

    def __init__(self):
        self._stats: Dict[str, DomainStats] = {}
        self._lock = threading.Lock()
        log.info("[DomainIntel] 域名智能学习服务已初始化")

    def _extract_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        return urlparse(url).netloc

    def record_request(self, url: str, mode: str, success: bool):
        """记录请求结果

        Args:
            url: 请求的 URL
            mode: 使用的模式 ("cookie" 或 "browser")
            success: 请求是否成功
        """
        domain = self._extract_domain(url)
        if not domain:
            return

        with self._lock:
            if domain not in self._stats:
                self._stats[domain] = DomainStats(domain=domain)

            stats = self._stats[domain]
            stats.last_updated = time.time()

            if mode == "cookie":
                if success:
                    stats.cookie_success += 1
                else:
                    stats.cookie_failure += 1
            elif mode == "browser":
                if success:
                    stats.browser_success += 1
                else:
                    stats.browser_failure += 1

            # 更新推荐模式
            stats.update_recommendation()

    def get_recommended_mode(self, url: str) -> str:
        """获取域名的推荐访问模式

        Args:
            url: 目标 URL

        Returns:
            str: "cookie" 或 "browser"
        """
        domain = self._extract_domain(url)
        with self._lock:
            if domain in self._stats:
                return self._stats[domain].recommended_mode
        return "cookie"  # 默认使用 cookie 模式

    def should_use_browser(self, url: str) -> bool:
        """判断是否应该使用浏览器模式"""
        return self.get_recommended_mode(url) == "browser"

    def get_domain_stats(self, url: str) -> Optional[Dict[str, Any]]:
        """获取指定域名的统计数据"""
        domain = self._extract_domain(url)
        with self._lock:
            if domain in self._stats:
                stats = self._stats[domain]
                return {
                    "domain": stats.domain,
                    "cookie": {
                        "success": stats.cookie_success,
                        "failure": stats.cookie_failure,
                        "total": stats.cookie_total,
                        "failure_rate": round(stats.cookie_failure_rate, 3),
                    },
                    "browser": {
                        "success": stats.browser_success,
                        "failure": stats.browser_failure,
                        "total": stats.browser_total,
                        "failure_rate": round(stats.browser_failure_rate, 3),
                    },
                    "recommended_mode": stats.recommended_mode,
                    "last_updated": stats.last_updated,
                }
        return None

    def get_all_stats(self) -> List[Dict[str, Any]]:
        """获取所有域名的统计数据"""
        with self._lock:
            result = []
            for domain, stats in self._stats.items():
                result.append({
                    "domain": stats.domain,
                    "cookie_success": stats.cookie_success,
                    "cookie_failure": stats.cookie_failure,
                    "cookie_failure_rate": round(stats.cookie_failure_rate, 3),
                    "browser_success": stats.browser_success,
                    "browser_failure": stats.browser_failure,
                    "recommended_mode": stats.recommended_mode,
                })
            return sorted(result, key=lambda x: x["cookie_failure"] + x["browser_failure"], reverse=True)

    def reset_domain(self, url: str) -> bool:
        """重置指定域名的统计数据"""
        domain = self._extract_domain(url)
        with self._lock:
            if domain in self._stats:
                del self._stats[domain]
                log.info(f"[DomainIntel] 已重置域名统计: {domain}")
                return True
        return False

    def reset_all(self) -> int:
        """重置所有统计数据"""
        with self._lock:
            count = len(self._stats)
            self._stats.clear()
            log.info(f"[DomainIntel] 已重置所有域名统计，共 {count} 条")
            return count

    def cleanup_expired(self) -> int:
        """清理过期的统计数据"""
        expire_time = time.time() - STATS_EXPIRE_HOURS * 3600
        with self._lock:
            expired_domains = [
                domain for domain, stats in self._stats.items()
                if stats.last_updated < expire_time
            ]
            for domain in expired_domains:
                del self._stats[domain]
            if expired_domains:
                log.info(f"[DomainIntel] 清理了 {len(expired_domains)} 条过期统计")
            return len(expired_domains)


# 全局单例
domain_intel = DomainIntelligence()
