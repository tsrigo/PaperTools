"""
Pytest 配置文件
"""

import os
import sys
import pytest

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture
def sample_paper():
    """提供一个测试用的论文数据"""
    return {
        "title": "Test Paper: A Study on Testing",
        "summary": "This paper explores testing methodologies for software systems.",
        "arxiv_id": "2401.00001",
        "link": "https://arxiv.org/abs/2401.00001",
        "date": "2024-01-01"
    }


@pytest.fixture
def temp_cache_dir(tmp_path):
    """提供一个临时缓存目录"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return str(cache_dir)
