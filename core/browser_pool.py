"""
浏览器对象池 - 支持高并发过盾

特性:
- 维护多个浏览器实例
- 自动扩缩容
- 空闲超时回收
- 线程安全
"""

import threading
import time
import sys
from typing import Optional
from queue import Queue, Empty

from DrissionPage import ChromiumOptions, ChromiumPage
from config import settings
from utils.fingerprint import get_fingerprint_script, get_webrtc_disable_script
from utils.logger import log

# Linux下启动虚拟显示器
if sys.platform.startswith("linux"):
    from pyvirtualdisplay import Display
    _display = Display(visible=0, size=(1920, 1080))
    _display.start()


class BrowserInstance:
    """浏览器实例包装类"""

    def __init__(self, page: ChromiumPage):
        self.page = page
        self.pid = page.process_id
        self.created_at = time.time()
        self.last_used_at = time.time()
        self.use_count = 0
        self.in_use = False

    def mark_used(self):
        """标记为使用中"""
        self.in_use = True
        self.last_used_at = time.time()
        self.use_count += 1

    def mark_free(self):
        """标记为空闲"""
        self.in_use = False
        self.last_used_at = time.time()


class BrowserPool:
    """浏览器对象池

    管理多个浏览器实例，支持高并发过盾。
    """

    def __init__(
        self,
        min_size: int = 1,
        max_size: int = 3,
        idle_timeout: int = 300,
    ):
        """
        Args:
            min_size: 最小浏览器数量
            max_size: 最大浏览器数量
            idle_timeout: 空闲超时时间 (秒)，超时后回收
        """
        self.min_size = min_size
        self.max_size = max_size
        self.idle_timeout = idle_timeout

        self._pool: Queue[BrowserInstance] = Queue()
        self._all_instances: list[BrowserInstance] = []
        self._lock = threading.Lock()
        self._initialized = False

    def _create_browser(self) -> BrowserInstance:
        """创建新的浏览器实例"""
        log.info("[BrowserPool] 创建新浏览器实例...")

        co = ChromiumOptions()
        if sys.platform.startswith("linux"):
            co.set_browser_path("/usr/bin/google-chrome")

        for arg in settings.BROWSER_ARGS:
            co.set_argument(arg)

        co.headless(settings.HEADLESS)
        page = ChromiumPage(co)

        # 注入指纹脚本
        if settings.FINGERPRINT_ENABLED:
            try:
                page.add_init_js(get_fingerprint_script())
                page.add_init_js(get_webrtc_disable_script())
            except Exception as e:
                log.warning(f"[BrowserPool] 指纹脚本注入失败: {e}")

        instance = BrowserInstance(page)
        log.info(f"[BrowserPool] 浏览器已创建, PID: {instance.pid}")

        return instance

    def _init_pool(self):
        """初始化浏览器池"""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            log.info(f"[BrowserPool] 初始化浏览器池 (min={self.min_size}, max={self.max_size})")

            for _ in range(self.min_size):
                try:
                    instance = self._create_browser()
                    self._pool.put(instance)
                    self._all_instances.append(instance)
                except Exception as e:
                    log.error(f"[BrowserPool] 初始化浏览器失败: {e}")

            self._initialized = True
            log.info(f"[BrowserPool] 初始化完成, 当前数量: {len(self._all_instances)}")

    def acquire(self, timeout: float = 30.0) -> Optional[BrowserInstance]:
        """获取一个浏览器实例

        Args:
            timeout: 等待超时时间 (秒)

        Returns:
            BrowserInstance 或 None (超时)
        """
        self._init_pool()

        try:
            # 尝试从池中获取
            instance = self._pool.get(timeout=timeout)

            # 检查浏览器是否还活着
            if not instance.page.process_id:
                log.warning(f"[BrowserPool] 浏览器已崩溃, 创建新实例")
                with self._lock:
                    self._all_instances.remove(instance)
                instance = self._create_browser()
                with self._lock:
                    self._all_instances.append(instance)

            instance.mark_used()
            log.debug(f"[BrowserPool] 获取浏览器 PID: {instance.pid}")
            return instance

        except Empty:
            # 池为空，尝试创建新实例
            with self._lock:
                if len(self._all_instances) < self.max_size:
                    try:
                        instance = self._create_browser()
                        self._all_instances.append(instance)
                        instance.mark_used()
                        return instance
                    except Exception as e:
                        log.error(f"[BrowserPool] 创建浏览器失败: {e}")

            log.warning("[BrowserPool] 获取浏览器超时，池已满")
            return None

    def release(self, instance: BrowserInstance):
        """归还浏览器实例到池中

        Args:
            instance: 要归还的浏览器实例
        """
        instance.mark_free()
        self._pool.put(instance)
        log.debug(f"[BrowserPool] 归还浏览器 PID: {instance.pid}")

    def destroy(self, instance: BrowserInstance):
        """销毁损坏的浏览器实例并创建新实例补充池

        Args:
            instance: 要销毁的浏览器实例
        """
        pid = instance.pid
        log.warning(f"[BrowserPool] 销毁损坏浏览器 PID: {pid}")

        # 1. 尝试关闭浏览器进程
        try:
            instance.page.quit()
        except Exception as e:
            log.debug(f"[BrowserPool] 关闭浏览器失败 (可能已崩溃): {e}")

        # 2. 从实例列表中移除
        with self._lock:
            try:
                self._all_instances.remove(instance)
            except ValueError:
                pass  # 已经不在列表中

            # 3. 如果低于最小数量，创建新实例补充
            if len(self._all_instances) < self.min_size:
                try:
                    new_instance = self._create_browser()
                    self._all_instances.append(new_instance)
                    self._pool.put(new_instance)
                    log.info(f"[BrowserPool] 已创建新实例补充池, 新 PID: {new_instance.pid}")
                except Exception as e:
                    log.error(f"[BrowserPool] 创建补充实例失败: {e}")

    def cleanup_idle(self) -> int:
        """清理空闲超时的浏览器

        Returns:
            清理的数量
        """
        cleaned = 0
        now = time.time()

        with self._lock:
            # 保留最小数量
            if len(self._all_instances) <= self.min_size:
                return 0

            to_remove = []
            for instance in self._all_instances:
                if not instance.in_use and (now - instance.last_used_at) > self.idle_timeout:
                    if len(self._all_instances) - len(to_remove) > self.min_size:
                        to_remove.append(instance)

            for instance in to_remove:
                try:
                    instance.page.quit()
                    self._all_instances.remove(instance)
                    cleaned += 1
                    log.info(f"[BrowserPool] 回收空闲浏览器 PID: {instance.pid}")
                except Exception as e:
                    log.warning(f"[BrowserPool] 回收浏览器失败 PID {instance.pid}: {e}")
                    # 仍然从列表中移除，避免泄漏
                    try:
                        self._all_instances.remove(instance)
                    except ValueError:
                        pass

        return cleaned

    def shutdown(self):
        """关闭所有浏览器"""
        log.info("[BrowserPool] 关闭所有浏览器...")

        with self._lock:
            for instance in self._all_instances:
                try:
                    instance.page.quit()
                    log.debug(f"[BrowserPool] 已关闭浏览器 PID: {instance.pid}")
                except Exception as e:
                    log.warning(f"[BrowserPool] 关闭浏览器失败 PID {instance.pid}: {e}")
            self._all_instances.clear()
            self._initialized = False

    def get_stats(self) -> dict:
        """获取池状态"""
        with self._lock:
            in_use = sum(1 for i in self._all_instances if i.in_use)
            return {
                "total": len(self._all_instances),
                "in_use": in_use,
                "available": len(self._all_instances) - in_use,
                "min_size": self.min_size,
                "max_size": self.max_size,
            }

    def get_memory_usage_mb(self) -> float:
        """获取所有浏览器进程的内存使用量 (MB)"""
        import subprocess
        total_kb = 0

        with self._lock:
            for instance in self._all_instances:
                if not instance.pid:
                    continue
                try:
                    # 获取主进程及其子进程的内存总和
                    result = subprocess.run(
                        ["ps", "-o", "rss=", "--ppid", str(instance.pid)],
                        capture_output=True, text=True, timeout=5
                    )
                    child_mem = sum(int(x) for x in result.stdout.split() if x.isdigit())

                    # 加上主进程内存
                    result = subprocess.run(
                        ["ps", "-o", "rss=", "-p", str(instance.pid)],
                        capture_output=True, text=True, timeout=5
                    )
                    main_mem = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0

                    total_kb += child_mem + main_mem
                except Exception:
                    pass

        return total_kb / 1024.0

    def restart_high_memory_browsers(self, limit_mb: float) -> int:
        """重启内存超限的浏览器

        Args:
            limit_mb: 内存限制 (MB)

        Returns:
            重启的数量
        """
        import subprocess
        restarted = 0

        with self._lock:
            for instance in self._all_instances:
                if instance.in_use or not instance.pid:
                    continue

                try:
                    # 获取该浏览器的内存使用
                    result = subprocess.run(
                        ["ps", "-o", "rss=", "-p", str(instance.pid)],
                        capture_output=True, text=True, timeout=5
                    )
                    mem_kb = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
                    mem_mb = mem_kb / 1024.0

                    if mem_mb > limit_mb:
                        log.warning(f"[BrowserPool] 浏览器 PID {instance.pid} 内存超限 ({mem_mb:.1f}MB > {limit_mb}MB)，重启中...")
                        try:
                            instance.page.quit()
                        except Exception:
                            pass

                        # 创建新实例替换
                        new_instance = self._create_browser()
                        idx = self._all_instances.index(instance)
                        self._all_instances[idx] = new_instance
                        self._pool.put(new_instance)
                        restarted += 1
                except Exception as e:
                    log.debug(f"[BrowserPool] 检查内存失败: {e}")

        return restarted


# 全局浏览器池
browser_pool = BrowserPool(
    min_size=settings.BROWSER_POOL_MIN,
    max_size=settings.BROWSER_POOL_MAX,
    idle_timeout=settings.BROWSER_POOL_IDLE_TIMEOUT,
)
