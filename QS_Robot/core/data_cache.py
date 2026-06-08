#!/usr/bin/env python3
"""
缓存管理器

支持多级缓存：
1. 内存缓存（最快，生命周期短）
2. 文件缓存（持久化，可配置TTL）

设计原则：
- 线程安全
- 自动过期（TTL机制）
- LRU淘汰策略
"""

import os
import json
import time
import hashlib
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Any


class DataCache:
    """统一缓存管理器"""

    def __init__(self, max_memory_items: int = 1000, file_cache_dir: str = None):
        self._max_memory = max_memory_items
        self._memory_cache: "OrderedDict[str, Dict]" = OrderedDict()
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0

        if file_cache_dir:
            self._file_cache_dir = file_cache_dir
        else:
            self._file_cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "bus_cache"
            )
        os.makedirs(self._file_cache_dir, exist_ok=True)
        print(f"[DataCache] 文件缓存目录: {self._file_cache_dir}")

    # --------------------------------------------------------
    # 缓存键生成
    # --------------------------------------------------------

    @staticmethod
    def _make_key(data_type: str, params: Dict[str, Any]) -> str:
        """生成缓存键"""
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        raw_key = f"{data_type}|{param_str}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()[:16]

    # --------------------------------------------------------
    # 内存缓存操作
    # --------------------------------------------------------

    def _get_from_memory(self, key: str) -> Optional[Dict]:
        """从内存缓存获取"""
        with self._lock:
            if key in self._memory_cache:
                item = self._memory_cache[key]
                now = time.time()
                if now < item.get("_expire_at", float("inf")):
                    self._memory_cache.move_to_end(key)
                    self._hit_count += 1
                    return item.get("data")
                else:
                    del self._memory_cache[key]
        return None

    def _set_to_memory(self, key: str, data: Dict, ttl: int = 3600):
        """写入内存缓存"""
        with self._lock:
            self._memory_cache[key] = {
                "data": data,
                "_expire_at": time.time() + ttl
            }
            self._memory_cache.move_to_end(key)

            # LRU淘汰
            while len(self._memory_cache) > self._max_memory:
                self._memory_cache.popitem(last=False)

    # --------------------------------------------------------
    # 文件缓存操作
    # --------------------------------------------------------

    def _get_from_file(self, key: str) -> Optional[Dict]:
        """从文件缓存获取"""
        path = os.path.join(self._file_cache_dir, f"{key}.json")
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                item = json.load(f)

            now = time.time()
            if now < item.get("_expire_at", float("inf")):
                return item.get("data")
            else:
                # 过期文件删除
                os.remove(path)
        except Exception:
            try:
                os.remove(path)
            except Exception:
                pass

        return None

    def _set_to_file(self, key: str, data: Dict, ttl: int = 3600):
        """写入文件缓存"""
        try:
            path = os.path.join(self._file_cache_dir, f"{key}.json")
            item = {
                "data": data,
                "_expire_at": time.time() + ttl,
                "_created_at": time.time()
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False)
        except Exception as e:
            print(f"[DataCache] 文件缓存写入失败: {e}")

    # --------------------------------------------------------
    # 统一接口
    # --------------------------------------------------------

    def get(self, data_type: str, params: Dict[str, Any]) -> Optional[Dict]:
        """获取缓存数据（先内存后文件）"""
        key = self._make_key(data_type, params)

        # 1. 内存缓存
        mem_data = self._get_from_memory(key)
        if mem_data is not None:
            return mem_data

        # 2. 文件缓存
        file_data = self._get_from_file(key)
        if file_data is not None:
            # 把文件缓存加载到内存
            self._set_to_memory(key, file_data, 1800)  # 内存缓存30分钟
            self._hit_count += 1
            return file_data

        self._miss_count += 1
        return None

    def set(self, data_type: str, params: Dict[str, Any],
            data: Dict[str, Any], ttl: int = 3600) -> bool:
        """写入缓存（内存+文件）"""
        key = self._make_key(data_type, params)
        try:
            self._set_to_memory(key, data, ttl)
            self._set_to_file(key, data, ttl)
            return True
        except Exception as e:
            print(f"[DataCache] 缓存写入失败: {e}")
            return False

    def clear(self, data_type: str = None):
        """清空缓存"""
        with self._lock:
            if data_type:
                # 只清空指定类型（需要遍历）
                keys_to_remove = []
                for k in self._memory_cache:
                    if k.startswith(data_type):
                        keys_to_remove.append(k)
                for k in keys_to_remove:
                    del self._memory_cache[k]
            else:
                self._memory_cache.clear()

    def get_hit_count(self) -> int:
        return self._hit_count

    def get_miss_count(self) -> int:
        return self._miss_count

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0
        return {
            "memory_items": len(self._memory_cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": round(hit_rate, 2)
        }


# ============================================================
# 单例模式
# ============================================================

_global_cache: Optional[DataCache] = None
_global_cache_lock = threading.Lock()


def get_cache_manager() -> DataCache:
    """获取缓存管理器单例"""
    global _global_cache
    if _global_cache is None:
        with _global_cache_lock:
            if _global_cache is None:
                _global_cache = DataCache()
    return _global_cache
