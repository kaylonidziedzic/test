import sys
from loguru import logger

# 移除默认 handler
logger.remove()

# 添加控制台输出 (Info级别)
logger.add(sys.stderr, level="INFO")

# 添加文件输出 (每天轮转，最多保留7天，压缩)
logger.add(
    "logs/server.log",
    rotation="00:00", 
    retention="7 days", 
    compression="zip", 
    level="INFO",
    enqueue=True
)

# 导出 logger 供全局使用
log = logger
