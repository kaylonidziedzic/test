import sys
from contextvars import ContextVar
from loguru import logger

_user_ctx: ContextVar[str] = ContextVar("user", default="system")


def set_user(user: str):
    """设置当前上下文的用户，用于日志标记"""
    if user:
        _user_ctx.set(str(user))
    else:
        _user_ctx.set("unknown")


def _inject_user(record):
    record["extra"]["user"] = _user_ctx.get()
    return record


# 移除默认 handler
logger.remove()

fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | [user:{extra[user]}] {message}"

# 添加控制台输出 (Info级别)
logger.add(sys.stderr, level="INFO", format=fmt)

# 添加文件输出 (每天轮转，最多保留7天，压缩)
logger.add(
    "logs/server.log",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    level="INFO",
    enqueue=True,
    format=fmt,
)

# 默认 extra
logger.configure(extra={"user": "system"})
# 为每条日志注入 user
logger = logger.patch(_inject_user)

# 导出 logger 供全局使用
log = logger
