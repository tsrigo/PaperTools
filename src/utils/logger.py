"""
日志模块 - 提供统一的日志记录功能
Logger module for unified logging functionality
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional


# 日志目录
LOG_DIR = "logs"

# 默认日志配置
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_BACKUP_COUNT = 5


def setup_logger(
    name: str = "papertools",
    level: int = DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = None,
    console_output: bool = True,
    file_output: bool = True,
) -> logging.Logger:
    """
    设置并返回一个配置好的 logger 实例

    Args:
        name: logger 名称
        level: 日志级别 (logging.DEBUG, logging.INFO, etc.)
        log_file: 日志文件名 (默认为 papertools.log)
        console_output: 是否输出到控制台
        file_output: 是否输出到文件

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)

    # 如果 logger 已经配置过，直接返回
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)

    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件处理器
    if file_output:
        os.makedirs(LOG_DIR, exist_ok=True)
        if log_file is None:
            log_file = f"{name}.log"
        log_path = os.path.join(LOG_DIR, log_file)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "papertools") -> logging.Logger:
    """
    获取已存在的 logger，如果不存在则创建一个新的

    Args:
        name: logger 名称

    Returns:
        logger 实例
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


class ProgressLogger:
    """
    进度日志记录器 - 替代原有的 ProgressTracker，提供更好的日志支持
    """

    def __init__(self, name: str = "papertools", description: str = ""):
        self.logger = get_logger(name)
        self.description = description
        self.start_time = datetime.now()
        self.step_count = 0

    def start(self, message: str = "") -> None:
        """开始任务"""
        self.start_time = datetime.now()
        msg = message or f"开始: {self.description}"
        self.logger.info(msg)

    def step(self, message: str) -> None:
        """记录步骤"""
        self.step_count += 1
        elapsed = datetime.now() - self.start_time
        self.logger.info(f"[步骤 {self.step_count}] [{elapsed}] {message}")

    def success(self, message: str = "") -> None:
        """记录成功"""
        elapsed = datetime.now() - self.start_time
        msg = message or f"完成: {self.description}"
        self.logger.info(f"✓ {msg} (耗时: {elapsed})")

    def warning(self, message: str) -> None:
        """记录警告"""
        self.logger.warning(f"⚠ {message}")

    def error(self, message: str, exc_info: bool = False) -> None:
        """记录错误"""
        self.logger.error(f"✗ {message}", exc_info=exc_info)

    def debug(self, message: str) -> None:
        """记录调试信息"""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """记录信息"""
        self.logger.info(message)


# 创建默认 logger 实例
logger = setup_logger()
