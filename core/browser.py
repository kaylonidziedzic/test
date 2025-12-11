import os
import subprocess
import threading
import sys

from DrissionPage import ChromiumOptions, ChromiumPage
from config import settings
from utils.logger import log

# Linux下启动虚拟显示器
if sys.platform.startswith("linux"):
    from pyvirtualdisplay import Display
    _display = Display(visible=0, size=(1920, 1080))
    _display.start()


class BrowserManager:
    _instance = None
    _lock = threading.Lock()
    page = None
    _managed_pid = None  # 记录当前管理的浏览器进程 PID

    @classmethod
    def get_browser(cls):
        """获取浏览器实例（懒加载）"""
        with cls._lock:
            if cls.page is None or not cls.page.process_id:
                log.info("🖥️ 初始化 Chromium 浏览器...")
                try:
                    co = ChromiumOptions()
                    if sys.platform.startswith("linux"):
                        co.set_browser_path("/usr/bin/google-chrome")

                    for arg in settings.BROWSER_ARGS:
                        co.set_argument(arg)

                    co.headless(settings.HEADLESS)
                    cls.page = ChromiumPage(co)
                    cls._managed_pid = cls.page.process_id
                    log.info(f"[Browser] 浏览器进程 PID: {cls._managed_pid}")
                except Exception as e:
                    log.error(f"❌ 浏览器启动失败: {e}")
                    raise e
            return cls.page

    @classmethod
    def restart(cls):
        """强制重启浏览器（用于处理崩溃或内存泄漏）"""
        with cls._lock:
            if cls.page:
                try:
                    cls.page.quit()
                except:
                    pass
                cls.page = None
                cls._managed_pid = None
            log.warning("🔄 浏览器已重置")

    @classmethod
    def get_memory_usage_mb(cls) -> float:
        """获取当前浏览器进程的内存使用量 (MB)"""
        if not cls._managed_pid:
            return 0.0
        try:
            # 获取主进程及其子进程的内存总和
            result = subprocess.run(
                ["ps", "-o", "rss=", "--ppid", str(cls._managed_pid)],
                capture_output=True, text=True, timeout=5
            )
            child_mem = sum(int(x) for x in result.stdout.split() if x.isdigit())

            # 加上主进程内存
            result = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(cls._managed_pid)],
                capture_output=True, text=True, timeout=5
            )
            main_mem = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0

            total_kb = child_mem + main_mem
            return total_kb / 1024.0
        except Exception as e:
            log.debug(f"[Browser] 获取内存失败: {e}")
            return 0.0

    @classmethod
    def cleanup_zombie_browsers(cls) -> int:
        """清理僵尸 Chrome 进程（状态为 Z 的进程）"""
        if not sys.platform.startswith("linux"):
            return 0

        killed = 0
        try:
            # 查找所有 chrome 进程
            result = subprocess.run(
                ["pgrep", "-f", "chrome"],
                capture_output=True, text=True, timeout=10
            )
            pids = [int(p) for p in result.stdout.split() if p.isdigit()]

            for pid in pids:
                # 跳过当前管理的进程及其子进程
                if cls._managed_pid:
                    if pid == cls._managed_pid or cls._is_child_of(pid, cls._managed_pid):
                        continue

                # 只清理真正的僵尸进程（状态为 Z）
                try:
                    result = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(pid)],
                        capture_output=True, text=True, timeout=5
                    )
                    stat = result.stdout.strip()
                    if 'Z' in stat:
                        os.kill(pid, 9)
                        killed += 1
                        log.info(f"[Browser] 清理僵尸进程: PID {pid} (状态: {stat})")
                except (ProcessLookupError, PermissionError):
                    pass
        except Exception as e:
            log.debug(f"[Browser] 清理僵尸进程失败: {e}")

        return killed

    @classmethod
    def _is_child_of(cls, pid: int, parent_pid: int) -> bool:
        """检查 pid 是否是 parent_pid 的子进程"""
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5
            )
            ppid = result.stdout.strip()
            return ppid.isdigit() and int(ppid) == parent_pid
        except:
            return False


browser_manager = BrowserManager()
