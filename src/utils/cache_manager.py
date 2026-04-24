#!/usr/bin/env python3
"""
缓存管理模块
Cache management module for academic paper processing
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# 导入配置
try:
    from src.utils.config import CACHE_DIR, ENABLE_CACHE, CACHE_EXPIRY_DAYS
except ImportError:
    CACHE_DIR = "cache"
    ENABLE_CACHE = True
    CACHE_EXPIRY_DAYS = 30

from src.utils.io import save_json


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = CACHE_DIR, summary_namespace: str = ""):
        self.cache_dir = cache_dir
        self.enabled = ENABLE_CACHE
        self.expiry_days = CACHE_EXPIRY_DAYS
        self.summary_namespace = summary_namespace

        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            # 创建子目录
            os.makedirs(os.path.join(self.cache_dir, "papers"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "documents"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "summaries"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "webpages"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "crawl"), exist_ok=True)
    
    def _generate_key(self, data: str) -> str:
        """生成缓存键"""
        return hashlib.md5(data.encode('utf-8')).hexdigest()
    
    def _get_cache_file(self, cache_type: str, key: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, cache_type, f"{key}.json")

    def _write_cache_file(self, cache_file: str, cache_data: Dict[str, Any]) -> None:
        """Atomically persist cache content."""
        cache_dir = os.path.dirname(cache_file)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        if not save_json(cache_file, cache_data):
            raise IOError(f"无法写入缓存文件: {cache_file}")
    
    def _is_cache_valid(self, cache_file: str) -> bool:
        """检查缓存是否有效（未过期）"""
        if not os.path.exists(cache_file):
            return False
        
        try:
            cache_time = os.path.getmtime(cache_file)
            cache_datetime = datetime.fromtimestamp(cache_time)
            expiry_datetime = datetime.now() - timedelta(days=self.expiry_days)
            return cache_datetime > expiry_datetime
        except Exception:
            return False
    
    def get_paper_cache(self, paper_url: str) -> Optional[Dict[str, Any]]:
        """获取论文缓存"""
        if not self.enabled:
            return None
        
        key = self._generate_key(paper_url)
        cache_file = self._get_cache_file("papers", key)
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 读取论文缓存失败: {e}")
            return None
    
    def set_paper_cache(self, paper_url: str, paper_data: Dict[str, Any]) -> None:
        """设置论文缓存"""
        if not self.enabled:
            return
        
        key = self._generate_key(paper_url)
        cache_file = self._get_cache_file("papers", key)
        
        try:
            cache_data = {
                "url": paper_url,
                "data": paper_data,
                "cached_at": datetime.now().isoformat()
            }
            self._write_cache_file(cache_file, cache_data)
        except Exception as e:
            print(f"⚠️ 保存论文缓存失败: {e}")

    def get_document_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取统一文档提取缓存。"""
        if not self.enabled:
            return None

        key = self._generate_key(cache_key)
        cache_file = self._get_cache_file("documents", key)

        if not self._is_cache_valid(cache_file):
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 读取文档缓存失败: {e}")
            return None

    def set_document_cache(self, cache_key: str, document_data: Dict[str, Any]) -> None:
        """设置统一文档提取缓存。"""
        if not self.enabled:
            return

        key = self._generate_key(cache_key)
        cache_file = self._get_cache_file("documents", key)

        try:
            cache_data = {
                "cache_key": cache_key,
                "data": document_data,
                "cached_at": datetime.now().isoformat()
            }
            self._write_cache_file(cache_file, cache_data)
        except Exception as e:
            print(f"⚠️ 保存文档缓存失败: {e}")
    
    def get_summary_cache(self, paper_title: str, paper_content: str) -> Optional[str]:
        """获取总结缓存"""
        if not self.enabled:
            return None
        
        # 使用标题和内容的组合生成键
        key = self._generate_key(f"{self.summary_namespace}:{paper_title}:{paper_content[:1000]}")
        cache_file = self._get_cache_file("summaries", key)
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get("summary")
        except Exception as e:
            print(f"⚠️ 读取总结缓存失败: {e}")
            return None
    
    def set_summary_cache(self, paper_title: str, paper_content: str, summary: str) -> None:
        """设置总结缓存"""
        if not self.enabled:
            return
        
        key = self._generate_key(f"{self.summary_namespace}:{paper_title}:{paper_content[:1000]}")
        cache_file = self._get_cache_file("summaries", key)
        
        try:
            cache_data = {
                "title": paper_title,
                "summary": summary,
                "cached_at": datetime.now().isoformat()
            }
            self._write_cache_file(cache_file, cache_data)
        except Exception as e:
            print(f"⚠️ 保存总结缓存失败: {e}")
    
    def get_webpage_cache(self, paper_title: str, content_hash: str) -> Optional[str]:
        """获取网页缓存"""
        if not self.enabled:
            return None
        
        key = self._generate_key(f"{paper_title}:{content_hash}")
        cache_file = self._get_cache_file("webpages", key)
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get("webpage_content")
        except Exception as e:
            print(f"⚠️ 读取网页缓存失败: {e}")
            return None
    
    def set_webpage_cache(self, paper_title: str, content_hash: str, webpage_content: str) -> None:
        """设置网页缓存"""
        if not self.enabled:
            return
        
        key = self._generate_key(f"{paper_title}:{content_hash}")
        cache_file = self._get_cache_file("webpages", key)
        
        try:
            cache_data = {
                "title": paper_title,
                "content_hash": content_hash,
                "webpage_content": webpage_content,
                "cached_at": datetime.now().isoformat()
            }
            self._write_cache_file(cache_file, cache_data)
        except Exception as e:
            print(f"⚠️ 保存网页缓存失败: {e}")

    def get_crawl_cache(self, category: str, date: str) -> Optional[List[Dict[str, Any]]]:
        """获取爬取缓存

        Args:
            category: 论文类别，如 'cs.AI'
            date: 日期字符串，格式为 'YYYY-MM-DD'

        Returns:
            缓存的论文列表，如果没有缓存则返回 None
        """
        if not self.enabled:
            return None

        key = self._generate_key(f"crawl:{category}:{date}")
        cache_file = self._get_cache_file("crawl", key)

        if not self._is_cache_valid(cache_file):
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get("papers")
        except Exception as e:
            print(f"⚠️ 读取爬取缓存失败: {e}")
            return None

    def set_crawl_cache(self, category: str, date: str, papers: List[Dict[str, Any]]) -> None:
        """设置爬取缓存

        Args:
            category: 论文类别
            date: 日期字符串
            papers: 论文列表
        """
        if not self.enabled:
            return

        key = self._generate_key(f"crawl:{category}:{date}")
        cache_file = self._get_cache_file("crawl", key)

        try:
            cache_data = {
                "category": category,
                "date": date,
                "papers": papers,
                "paper_count": len(papers),
                "cached_at": datetime.now().isoformat()
            }
            self._write_cache_file(cache_file, cache_data)
        except Exception as e:
            print(f"⚠️ 保存爬取缓存失败: {e}")

    def clean_expired_cache(self) -> None:
        """清理过期缓存"""
        if not self.enabled:
            return
        
        print("🧹 清理过期缓存...")
        cleaned_count = 0
        
        for cache_type in ["papers", "documents", "summaries", "webpages", "crawl"]:
            cache_type_dir = os.path.join(self.cache_dir, cache_type)
            if not os.path.exists(cache_type_dir):
                continue

            for cache_file in os.listdir(cache_type_dir):
                cache_path = os.path.join(cache_type_dir, cache_file)
                if not self._is_cache_valid(cache_path):
                    try:
                        os.remove(cache_path)
                        cleaned_count += 1
                    except Exception as e:
                        print(f"⚠️ 删除缓存文件失败 {cache_path}: {e}")
        
        if cleaned_count > 0:
            print(f"✅ 已清理 {cleaned_count} 个过期缓存文件")
        else:
            print("✅ 没有过期缓存文件需要清理")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        if not self.enabled:
            return {"papers": 0, "documents": 0, "summaries": 0, "webpages": 0, "crawl": 0, "total": 0}

        stats = {}
        total = 0

        for cache_type in ["papers", "documents", "summaries", "webpages", "crawl"]:
            cache_type_dir = os.path.join(self.cache_dir, cache_type)
            if os.path.exists(cache_type_dir):
                count = len([f for f in os.listdir(cache_type_dir) if f.endswith('.json')])
                stats[cache_type] = count
                total += count
            else:
                stats[cache_type] = 0
        
        stats["total"] = total
        return stats


def create_time_based_directory(base_dir: str, date_str: Optional[str] = None) -> str:
    """
    创建按时间划分的目录结构
    
    Args:
        base_dir: 基础目录
        date_str: 日期字符串，如果不提供则使用当前日期
    
    Returns:
        创建的时间目录路径
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    time_dir = os.path.join(base_dir, date_str)
    os.makedirs(time_dir, exist_ok=True)
    return time_dir


def get_available_dates(base_dir: str) -> List[str]:
    """
    获取可用的日期列表
    
    Args:
        base_dir: 基础目录
    
    Returns:
        日期字符串列表，按降序排列
    """
    if not os.path.exists(base_dir):
        return []
    
    dates = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            # 检查是否是有效的日期格式
            try:
                datetime.strptime(item, "%Y-%m-%d")
                dates.append(item)
            except ValueError:
                continue
    
    return sorted(dates, reverse=True)


if __name__ == "__main__":
    # 测试缓存管理器
    cache_manager = CacheManager()
    
    # 显示缓存统计
    stats = cache_manager.get_cache_stats()
    print("📊 缓存统计:")
    for cache_type, count in stats.items():
        print(f"  {cache_type}: {count}")
    
    # 清理过期缓存
    cache_manager.clean_expired_cache()
