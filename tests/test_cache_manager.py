"""
缓存管理器测试
"""

import os
import json
import pytest
from datetime import datetime, timedelta


class TestCacheManager:
    """测试缓存管理器"""

    def test_cache_manager_import(self):
        """测试缓存管理器可以导入"""
        from src.utils.cache_manager import CacheManager
        assert CacheManager is not None

    def test_cache_manager_init(self, temp_cache_dir):
        """测试缓存管理器初始化"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)
        assert manager.cache_dir == temp_cache_dir
        assert manager.enabled is True

    def test_cache_manager_disabled(self, temp_cache_dir):
        """测试禁用缓存"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)
        manager.enabled = False
        assert manager.enabled is False

        # 禁用后获取缓存应该返回 None
        result = manager.get_paper_cache("http://test.url")
        assert result is None

    def test_set_and_get_paper_cache(self, temp_cache_dir):
        """测试设置和获取论文缓存"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)

        paper_url = "https://arxiv.org/abs/2401.00001"
        paper_data = "This is the paper content"

        # 设置缓存
        manager.set_paper_cache(paper_url, paper_data)

        # 获取缓存
        cached = manager.get_paper_cache(paper_url)
        assert cached is not None
        assert cached["data"] == paper_data
        assert cached["url"] == paper_url

    def test_cache_miss(self, temp_cache_dir):
        """测试缓存未命中"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)

        result = manager.get_paper_cache("https://nonexistent.url")
        assert result is None

    def test_generate_key(self, temp_cache_dir):
        """测试缓存键生成"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)

        key1 = manager._generate_key("test_data_1")
        key2 = manager._generate_key("test_data_2")
        key3 = manager._generate_key("test_data_1")

        # 相同输入应该生成相同的键
        assert key1 == key3
        # 不同输入应该生成不同的键
        assert key1 != key2

    def test_cache_directories_created(self, temp_cache_dir):
        """测试缓存目录被创建"""
        from src.utils.cache_manager import CacheManager
        manager = CacheManager(cache_dir=temp_cache_dir)

        # 设置一个缓存以触发目录创建
        manager.set_paper_cache("http://test.url", "test_data")

        papers_dir = os.path.join(temp_cache_dir, "papers")
        assert os.path.exists(papers_dir)
