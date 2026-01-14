"""
IO 工具模块 - 提供常用的文件读写操作
IO utilities module for common file operations
"""

import json
import os
from typing import Any, Dict, List, Optional, Union

from src.utils.logger import get_logger

logger = get_logger("io")


def load_json(filepath: str, default: Optional[Any] = None) -> Optional[Any]:
    """
    安全地加载 JSON 文件

    Args:
        filepath: JSON 文件路径
        default: 加载失败时返回的默认值

    Returns:
        解析后的 JSON 数据，失败时返回 default
    """
    if not os.path.exists(filepath):
        logger.warning(f"文件不存在: {filepath}")
        return default

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误 {filepath}: {e}")
        return default
    except IOError as e:
        logger.error(f"读取文件失败 {filepath}: {e}")
        return default


def save_json(
    filepath: str,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False
) -> bool:
    """
    安全地保存 JSON 文件

    Args:
        filepath: 保存路径
        data: 要保存的数据
        indent: 缩进空格数
        ensure_ascii: 是否转义非 ASCII 字符

    Returns:
        是否保存成功
    """
    try:
        # 确保目录存在
        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        return True
    except IOError as e:
        logger.error(f"保存文件失败 {filepath}: {e}")
        return False
    except (TypeError, ValueError) as e:
        logger.error(f"JSON 序列化错误: {e}")
        return False


def load_papers(filepath: str) -> List[Dict[str, Any]]:
    """
    加载论文列表

    Args:
        filepath: 论文 JSON 文件路径

    Returns:
        论文列表，失败时返回空列表
    """
    papers = load_json(filepath, default=[])
    if not isinstance(papers, list):
        logger.warning(f"论文数据格式错误，期望列表，得到 {type(papers)}")
        return []
    return papers


def save_papers(filepath: str, papers: List[Dict[str, Any]]) -> bool:
    """
    保存论文列表

    Args:
        filepath: 保存路径
        papers: 论文列表

    Returns:
        是否保存成功
    """
    return save_json(filepath, papers)


def ensure_directory(path: str) -> bool:
    """
    确保目录存在

    Args:
        path: 目录路径

    Returns:
        是否成功创建或已存在
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError as e:
        logger.error(f"创建目录失败 {path}: {e}")
        return False


def file_exists(filepath: str) -> bool:
    """检查文件是否存在"""
    return os.path.exists(filepath)
