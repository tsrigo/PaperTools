"""
配置模块测试
"""

import os
import pytest


class TestConfig:
    """测试配置模块"""

    def test_config_import(self):
        """测试配置模块可以导入"""
        from src.utils.config import (
            ARXIV_PAPER_DIR,
            DOMAIN_PAPER_DIR,
            SUMMARY_DIR,
            WEBPAGES_DIR,
            CACHE_DIR,
        )
        assert ARXIV_PAPER_DIR == "arxiv_paper"
        assert DOMAIN_PAPER_DIR == "domain_paper"
        assert SUMMARY_DIR == "summary"
        assert WEBPAGES_DIR == "webpages"
        assert CACHE_DIR == "cache"

    def test_config_constants(self):
        """测试配置常量有效"""
        from src.utils.config import (
            TEMPERATURE,
            REQUEST_TIMEOUT,
            REQUEST_DELAY,
            MAX_WORKERS,
            CACHE_EXPIRY_DAYS,
        )
        assert 0 <= TEMPERATURE <= 2
        assert REQUEST_TIMEOUT > 0
        assert REQUEST_DELAY > 0
        assert MAX_WORKERS > 0
        assert CACHE_EXPIRY_DAYS > 0

    def test_crawl_categories(self):
        """测试爬取类别配置"""
        from src.utils.config import CRAWL_CATEGORIES
        assert isinstance(CRAWL_CATEGORIES, list)
        assert len(CRAWL_CATEGORIES) > 0
        for category in CRAWL_CATEGORIES:
            assert isinstance(category, str)
            assert "." in category  # 应该是 cs.AI 这样的格式

    def test_paper_filter_prompt(self):
        """测试论文筛选 Prompt 模板"""
        from src.utils.config import PAPER_FILTER_PROMPT
        assert isinstance(PAPER_FILTER_PROMPT, str)
        assert "{title}" in PAPER_FILTER_PROMPT
        assert "{summary}" in PAPER_FILTER_PROMPT
