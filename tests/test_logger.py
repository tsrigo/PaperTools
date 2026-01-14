"""
日志模块测试
"""

import os
import logging
import pytest


class TestLogger:
    """测试日志模块"""

    def test_logger_import(self):
        """测试日志模块可以导入"""
        from src.utils.logger import setup_logger, get_logger, ProgressLogger
        assert setup_logger is not None
        assert get_logger is not None
        assert ProgressLogger is not None

    def test_setup_logger(self):
        """测试设置日志器"""
        from src.utils.logger import setup_logger
        logger = setup_logger(name="test_logger", console_output=True, file_output=False)
        assert logger is not None
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO

    def test_get_logger(self):
        """测试获取日志器"""
        from src.utils.logger import get_logger
        logger1 = get_logger("test_get_logger")
        logger2 = get_logger("test_get_logger")
        # 应该返回同一个实例
        assert logger1 is logger2

    def test_progress_logger(self):
        """测试进度日志器"""
        from src.utils.logger import ProgressLogger
        progress = ProgressLogger(name="test_progress", description="Test Task")
        assert progress.description == "Test Task"
        assert progress.step_count == 0

    def test_progress_logger_step(self):
        """测试进度日志器步骤记录"""
        from src.utils.logger import ProgressLogger
        progress = ProgressLogger(name="test_progress_step", description="Test")
        progress.step("Step 1")
        assert progress.step_count == 1
        progress.step("Step 2")
        assert progress.step_count == 2

    def test_logger_levels(self):
        """测试不同日志级别"""
        from src.utils.logger import setup_logger
        # 测试 DEBUG 级别
        debug_logger = setup_logger(
            name="test_debug_logger",
            level=logging.DEBUG,
            console_output=False,
            file_output=False
        )
        assert debug_logger.level == logging.DEBUG
