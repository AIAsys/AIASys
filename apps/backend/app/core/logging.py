"""
日志配置
"""

import logging
import sys

from app.core.config import DEBUG, LOGS_DIR


def setup_logging():
    """配置日志系统"""
    # 确保日志目录存在
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 日志级别
    level = logging.DEBUG if DEBUG else logging.INFO

    # 根日志器配置
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            # 控制台输出
            logging.StreamHandler(sys.stdout),
            # 文件输出
            logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8"),
        ],
    )

    # 第三方库日志级别调整
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器"""
    return logging.getLogger(name)
