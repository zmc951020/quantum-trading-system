#!/usr/bin/env python3
"""
RedisCache - Redis缓存层

核心功能：
  1. 因子快照缓存（减少Qlib重复计算）
  2. 公共缓存（全市场因子、行情基准，多用户共享）
  3. 私有缓存（用户选股条件、权重、布局）
  4. Redis Stream 任务队列
  5. 缓存时效管理（分钟因子1min过期，日线因子盘后刷新）

设计依据：
  豆包审查 + Trae方案 - 新增Redis缓冲层，缓存分钟最新因子打分
  修正：多用户场景下Redis是不可或缺的性能层
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union

import redis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis缓存层

    Key命名规范:
      - public:{type}:{key}  - 公共缓存（全市场因子、行情基准）
      - user:{user_id}:{type}:{key}  - 用户私有缓存
      - stream:{name}  - Redis Stream 任务队列
      - lock:{name}  - 分布式锁

    使用示例:
        >>> cache = RedisCache()
        >>> cache.set_factor("user_001", "600519", {"RSI_14": 65.5})
        >>> factors = cache.get_factor("user_001", "600519")
    """

    # 缓存时效配置
    TTL_FACTOR_1MIN = 60       # 分钟因子: 60秒
    TTL_FACTOR_DAY = 86400     # 日线因子: 24小时
    TTL_STOCK_POOL = 300       # 股票池: 5分钟
    TTL_SESSION = 86400        # 会话: 24小时
    TTL_PUBLIC = 3600          # 公共缓存: 1小时

    def __init__(self, host: str = "localhost", port: int = 6379,
                 db: int = 0, password: str = None,
                 decode_responses: bool = True):
        self.host = host
        self.port = port
        self.db = db
        self._client: Optional[redis.Redis] = None
        self._connected = False
        self._decode_responses = decode_responses
        self._connect_params = {
            "host": host,
            "port": port,
            "db": db,
            "password": password,
            "decode_responses": decode_responses,
            "socket_timeout": 5,
            "socket_connect_timeout": 3,
            "max_connections": 50,
        }

    # ================================================================
    # 连接管理
    # ================================================================

    def connect(self) -> bool:
        """连接Redis"""
        try:
            self._client = redis.Redis(**self._connect_params)
            self._client.ping()
            self._connected = True
            logger.info(f"Redis 连接成功: {self.host}:{self.port}")
            return True
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Redis 连接失败，使用内存缓存降级: {e}")
            self._connected = False
            self._fallback = {}
            return False
        except Exception as e:
            logger.error(f"Redis 连接异常: {e}")
            self._connected = False
            self._fallback = {}
            return False

    def disconnect(self):
        if self._client:
            self._client.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    # ================================================================
    # 因子快照缓存
    # ================================================================

    def set_factor(self, user_id: str, code: str, factors: Dict[str, float],
                   freq: str = "day") -> bool:
        """缓存因子快照

        Key: user:{user_id}:factor:{code}:{freq}
        """
        key = f"user:{user_id}:factor:{code}:{freq}"
        ttl = self.TTL_FACTOR_1MIN if freq == "1min" else self.TTL_FACTOR_DAY
        return self._set_json(key, factors, ttl)

    def get_factor(self, user_id: str, code: str, freq: str = "day") -> Optional[Dict]:
        """获取缓存的因子"""
        key = f"user:{user_id}:factor:{code}:{freq}"
        return self._get_json(key)

    def set_factor_batch(self, user_id: str, code_factors: Dict[str, Dict],
                          freq: str = "day") -> int:
        """批量缓存因子"""
        count = 0
        for code, factors in code_factors.items():
            if self.set_factor(user_id, code, factors, freq):
                count += 1
        return count

    def get_factor_batch(self, user_id: str, codes: List[str],
                          freq: str = "day") -> Dict[str, Optional[Dict]]:
        """批量获取因子"""
        return {code: self.get_factor(user_id, code, freq) for code in codes}

    # ================================================================
    # 公共缓存（全市场因子、行情基准）
    # ================================================================

    def set_public_factor(self, code: str, factors: Dict[str, float],
                           freq: str = "day") -> bool:
        """设置公共因子缓存（多用户共享）"""
        key = f"public:factor:{code}:{freq}"
        return self._set_json(key, factors, self.TTL_PUBLIC)

    def get_public_factor(self, code: str, freq: str = "day") -> Optional[Dict]:
        """获取公共因子缓存"""
        key = f"public:factor:{code}:{freq}"
        return self._get_json(key)

    def set_market_benchmark(self, name: str, data: Dict, ttl: int = 3600) -> bool:
        """设置行情基准"""
        key = f"public:benchmark:{name}"
        return self._set_json(key, data, ttl)

    def get_market_benchmark(self, name: str) -> Optional[Dict]:
        """获取行情基准"""
        key = f"public:benchmark:{name}"
        return self._get_json(key)

    # ================================================================
    # 用户私有缓存
    # ================================================================

    def set_user_session(self, user_id: str, key: str, value: Any,
                          ttl: int = None) -> bool:
        """设置用户会话数据"""
        redis_key = f"user:{user_id}:session:{key}"
        return self._set_json(redis_key, value, ttl or self.TTL_SESSION)

    def get_user_session(self, user_id: str, key: str) -> Optional[Any]:
        """获取用户会话数据"""
        redis_key = f"user:{user_id}:session:{key}"
        return self._get_json(redis_key)

    def set_user_preferences(self, user_id: str, preferences: Dict) -> bool:
        """设置用户偏好（选股条件、权重、布局）"""
        key = f"user:{user_id}:preferences"
        return self._set_json(key, preferences, self.TTL_SESSION * 7)  # 7天

    def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""
        key = f"user:{user_id}:preferences"
        return self._get_json(key)

    # ================================================================
    # 股票池缓存
    # ================================================================

    def set_stock_pool(self, user_id: str, pool_name: str,
                        stocks: List[Dict]) -> bool:
        """缓存股票池"""
        key = f"user:{user_id}:pool:{pool_name}"
        return self._set_json(key, stocks, self.TTL_STOCK_POOL)

    def get_stock_pool(self, user_id: str, pool_name: str) -> Optional[List[Dict]]:
        """获取股票池缓存"""
        key = f"user:{user_id}:pool:{pool_name}"
        return self._get_json(key)

    # ================================================================
    # Redis Stream 任务队列
    # ================================================================

    def push_task(self, stream_name: str, task: Dict[str, Any],
                   max_len: int = 10000) -> Optional[str]:
        """推送任务到 Stream 队列

        Args:
            stream_name: 队列名 (如 "factor:compute", "backtest:run")
            task: 任务数据
            max_len: 最大队列长度

        Returns:
            message_id
        """
        if not self.is_connected:
            return None
        try:
            msg_id = self._client.xadd(stream_name, task, maxlen=max_len)
            return msg_id
        except Exception as e:
            logger.error(f"任务推送失败: {e}")
            return None

    def pop_task(self, stream_name: str, consumer_group: str = "default",
                  consumer_name: str = "worker-1", count: int = 1,
                  block_ms: int = 5000) -> List[Dict]:
        """从 Stream 队列消费任务"""
        if not self.is_connected:
            return []
        try:
            # 确保消费组存在
            try:
                self._client.xgroup_create(stream_name, consumer_group, id="0", mkstream=True)
            except redis.ResponseError:
                pass  # 消费组已存在

            messages = self._client.xreadgroup(
                consumer_group, consumer_name,
                {stream_name: ">"}, count=count, block=block_ms,
            )
            results = []
            for stream, msgs in messages:
                for msg_id, data in msgs:
                    results.append({"id": msg_id, "data": data})
            return results
        except Exception as e:
            logger.error(f"任务消费失败: {e}")
            return []

    def ack_task(self, stream_name: str, consumer_group: str, message_id: str):
        """确认任务完成"""
        if not self.is_connected:
            return
        try:
            self._client.xack(stream_name, consumer_group, message_id)
        except Exception as e:
            logger.error(f"任务确认失败: {e}")

    def get_stream_length(self, stream_name: str) -> int:
        """获取队列长度"""
        if not self.is_connected:
            return 0
        try:
            return self._client.xlen(stream_name)
        except Exception:
            return 0

    # ================================================================
    # 分布式锁
    # ================================================================

    def acquire_lock(self, lock_name: str, ttl: int = 30) -> bool:
        """获取分布式锁"""
        if not self.is_connected:
            return True  # 降级：无Redis时总是获取锁
        try:
            return self._client.set(
                f"lock:{lock_name}", "1", nx=True, ex=ttl
            )
        except Exception:
            return True

    def release_lock(self, lock_name: str):
        """释放分布式锁"""
        if not self.is_connected:
            return
        try:
            self._client.delete(f"lock:{lock_name}")
        except Exception:
            pass

    # ================================================================
    # 通用KV操作
    # ================================================================

    def set(self, key: str, value: str, ttl: int = None) -> bool:
        if not self.is_connected:
            self._fallback[key] = value
            return True
        try:
            self._client.set(key, value, ex=ttl)
            return True
        except Exception:
            return False

    def get(self, key: str) -> Optional[str]:
        if not self.is_connected:
            return self._fallback.get(key)
        try:
            return self._client.get(key)
        except Exception:
            return self._fallback.get(key)

    def delete(self, key: str):
        if not self.is_connected:
            self._fallback.pop(key, None)
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        if not self.is_connected:
            return key in self._fallback
        try:
            return bool(self._client.exists(key))
        except Exception:
            return key in self._fallback

    def expire(self, key: str, ttl: int):
        if not self.is_connected:
            return
        try:
            self._client.expire(key, ttl)
        except Exception:
            pass

    # ================================================================
    # 内部方法
    # ================================================================

    def _set_json(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置JSON值"""
        if not self.is_connected:
            self._fallback[key] = value
            return True
        try:
            data = json.dumps(value, ensure_ascii=False, default=str)
            self._client.set(key, data, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis set失败: {key}: {e}")
            self._fallback[key] = value
            return False

    def _get_json(self, key: str) -> Optional[Any]:
        """获取JSON值"""
        if not self.is_connected:
            return self._fallback.get(key)
        try:
            data = self._client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get失败: {key}: {e}")
            return self._fallback.get(key)

    # ================================================================
    # 健康检查
    # ================================================================

    def health_check(self) -> Dict[str, Any]:
        result = {
            "connected": self._connected,
            "host": self.host,
            "port": self.port,
        }
        if self._connected and self._client:
            try:
                result["ping"] = self._client.ping()
                info = self._client.info("memory")
                result["used_memory_mb"] = info.get("used_memory_human", "N/A")
                result["connected_clients"] = info.get("connected_clients", 0)
            except Exception as e:
                result["ping"] = f"error: {e}"
        else:
            result["fallback_keys"] = len(getattr(self, "_fallback", {}))
        return result

    def clear_user_cache(self, user_id: str):
        """清除用户所有缓存"""
        if not self.is_connected:
            keys_to_del = [k for k in self._fallback if k.startswith(f"user:{user_id}:")]
            for k in keys_to_del:
                del self._fallback[k]
            return
        try:
            pattern = f"user:{user_id}:*"
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"清除用户缓存失败: {e}")


# ============================================================
# 全局单例
# ============================================================

_cache: Optional[RedisCache] = None


def get_redis_cache(host: str = "localhost", port: int = 6379) -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache(host=host, port=port)
        _cache.connect()
    return _cache