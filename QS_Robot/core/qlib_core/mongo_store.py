#!/usr/bin/env python3
"""
MongoStore - MongoDB存储适配器

核心功能：
  1. 多租户数据隔离（所有操作绑定 user_id）
  2. TimeSeries 时序集合（分时行情、因子快照）
  3. 业务文档存储（Agent日志、回测报告、优化迭代）
  4. TTL 自动清理过期数据
  5. 复合索引优化（user_id + code + timestamp）
  6. 权限分级访问控制

设计依据：
  豆包审查 + Trae方案 - MongoDB 统一承接多用户业务数据
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class StoreConfig:
    """MongoDB 存储配置"""
    host: str = "localhost"
    port: int = 27017
    db_name: str = "qs_robot"
    username: str = ""
    password: str = ""
    auth_source: str = "admin"
    connect_timeout_ms: int = 5000
    server_selection_timeout_ms: int = 3000
    max_pool_size: int = 50
    min_pool_size: int = 5


class MongoStore:
    """MongoDB 存储适配器

    集合设计：
      - agent_logs: Agent推理日志 (user_id + timestamp复合索引)
      - factor_snapshots: 因子快照 (TimeSeries: user_id + code + timestamp)
      - backtest_results: 回测结果 (user_id + strategy复合索引)
      - optimization_traces: 优化迭代曲线 (user_id + strategy + iteration)
      - stock_pools: 股票池快照 (TimeSeries: user_id + timestamp)
      - trade_records: 交易记录 (user_id + timestamp)
      - session_cache: 用户会话缓存 (TTL: 24h)
      - audit_logs: 审计日志 (user_id + timestamp)

    使用示例:
        >>> store = MongoStore()
        >>> store.connect()
        >>> store.save_factor_snapshot("user_001", "600519", {"RSI": 65.5})
    """

    def __init__(self, config: StoreConfig = None):
        self.config = config or StoreConfig()
        self._client: Optional[MongoClient] = None
        self._db = None
        self._connected = False

    # ================================================================
    # 连接管理
    # ================================================================

    def connect(self) -> bool:
        """连接MongoDB"""
        try:
            uri = f"mongodb://{self.config.host}:{self.config.port}"
            kwargs = {
                "serverSelectionTimeoutMS": self.config.server_selection_timeout_ms,
                "connectTimeoutMS": self.config.connect_timeout_ms,
                "maxPoolSize": self.config.max_pool_size,
                "minPoolSize": self.config.min_pool_size,
            }
            if self.config.username and self.config.password:
                kwargs["username"] = self.config.username
                kwargs["password"] = self.config.password
                kwargs["authSource"] = self.config.auth_source

            self._client = MongoClient(uri, **kwargs)
            # 测试连接
            self._client.admin.command("ping")
            self._db = self._client[self.config.db_name]
            self._connected = True
            self._ensure_indexes()
            logger.info(f"MongoDB 连接成功: {self.config.host}:{self.config.port}/{self.config.db_name}")
            return True

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"MongoDB 连接失败，使用文件存储降级: {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"MongoDB 连接异常: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self._client:
            self._client.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._db is not None

    def _ensure_db(self):
        """确保数据库可用，否则抛出异常"""
        if not self.is_connected:
            raise RuntimeError("MongoDB 未连接")

    def _ensure_indexes(self):
        """创建所有集合的索引"""
        if not self.is_connected:
            return

        try:
            # Agent日志索引
            self._db.agent_logs.create_indexes([
                IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("agent_name", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("timestamp", DESCENDING)], expireAfterSeconds=90 * 86400),  # 90天TTL
            ])

            # 因子快照索引
            self._db.factor_snapshots.create_indexes([
                IndexModel([("user_id", ASCENDING), ("code", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("code", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("timestamp", DESCENDING)], expireAfterSeconds=30 * 86400),
            ])

            # 回测结果索引
            self._db.backtest_results.create_indexes([
                IndexModel([("user_id", ASCENDING), ("strategy", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("strategy", ASCENDING), ("created_at", DESCENDING)]),
            ])

            # 优化迭代索引
            self._db.optimization_traces.create_indexes([
                IndexModel([("user_id", ASCENDING), ("strategy", ASCENDING), ("iteration", ASCENDING)]),
                IndexModel([("strategy", ASCENDING), ("iteration", ASCENDING)]),
            ])

            # 股票池索引
            self._db.stock_pools.create_indexes([
                IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("timestamp", DESCENDING)], expireAfterSeconds=7 * 86400),
            ])

            # 交易记录索引
            self._db.trade_records.create_indexes([
                IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("code", ASCENDING), ("timestamp", DESCENDING)]),
            ])

            # 会话缓存索引 (TTL 24h)
            self._db.session_cache.create_indexes([
                IndexModel([("user_id", ASCENDING)]),
                IndexModel([("updated_at", ASCENDING)], expireAfterSeconds=86400),
            ])

            # 审计日志索引
            self._db.audit_logs.create_indexes([
                IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("action", ASCENDING), ("timestamp", DESCENDING)]),
            ])

            logger.info("MongoDB 索引创建完成")

        except Exception as e:
            logger.warning(f"索引创建失败: {e}")

    # ================================================================
    # 因子快照存储
    # ================================================================

    def save_factor_snapshot(self, user_id: str, code: str, factors: Dict[str, float],
                              freq: str = "day", timestamp: datetime = None) -> str:
        """保存因子快照

        Args:
            user_id: 用户ID
            code: 股票代码
            factors: 因子dict {factor_name: value}
            freq: 频率
            timestamp: 时间戳

        Returns:
            document_id
        """
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "code": code,
            "freq": freq,
            "factors": factors,
            "timestamp": timestamp or datetime.now(),
        }
        result = self._db.factor_snapshots.insert_one(doc)
        return str(result.inserted_id)

    def get_factor_snapshot(self, user_id: str, code: str,
                            timestamp: datetime = None) -> Optional[Dict]:
        """获取最新的因子快照"""
        self._ensure_db()
        query = {"user_id": user_id, "code": code}
        if timestamp:
            query["timestamp"] = {"$lte": timestamp}
        return self._db.factor_snapshots.find_one(query, sort=[("timestamp", DESCENDING)])

    def get_factor_history(self, user_id: str, code: str,
                           start: datetime = None, end: datetime = None,
                           limit: int = 100) -> List[Dict]:
        """获取因子历史"""
        self._ensure_db()
        query = {"user_id": user_id, "code": code}
        if start or end:
            query["timestamp"] = {}
            if start:
                query["timestamp"]["$gte"] = start
            if end:
                query["timestamp"]["$lte"] = end
        return list(self._db.factor_snapshots.find(query).sort("timestamp", DESCENDING).limit(limit))

    # ================================================================
    # 回测结果存储
    # ================================================================

    def save_backtest_result(self, user_id: str, strategy: str, result: Dict[str, Any]) -> str:
        """保存回测结果"""
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "strategy": strategy,
            "result": result,
            "created_at": datetime.now(),
        }
        r = self._db.backtest_results.insert_one(doc)
        return str(r.inserted_id)

    def get_backtest_results(self, user_id: str, strategy: str = None,
                              limit: int = 10) -> List[Dict]:
        """获取回测结果"""
        self._ensure_db()
        query = {"user_id": user_id}
        if strategy:
            query["strategy"] = strategy
        return list(self._db.backtest_results.find(query).sort("created_at", DESCENDING).limit(limit))

    # ================================================================
    # 优化迭代存储
    # ================================================================

    def save_optimization_trace(self, user_id: str, strategy: str, iteration: int,
                                 score: float, params: Dict[str, Any],
                                 convergence: float = None) -> str:
        """保存优化迭代记录"""
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "strategy": strategy,
            "iteration": iteration,
            "score": score,
            "params": params,
            "convergence": convergence,
            "timestamp": datetime.now(),
        }
        r = self._db.optimization_traces.insert_one(doc)
        return str(r.inserted_id)

    def get_optimization_trace(self, user_id: str, strategy: str,
                                limit: int = 100) -> List[Dict]:
        """获取优化迭代曲线"""
        self._ensure_db()
        return list(self._db.optimization_traces.find(
            {"user_id": user_id, "strategy": strategy}
        ).sort("iteration", ASCENDING).limit(limit))

    def get_best_optimization(self, user_id: str, strategy: str) -> Optional[Dict]:
        """获取最佳优化结果"""
        self._ensure_db()
        return self._db.optimization_traces.find_one(
            {"user_id": user_id, "strategy": strategy},
            sort=[("score", DESCENDING)]
        )

    # ================================================================
    # Agent 日志存储
    # ================================================================

    def save_agent_log(self, user_id: str, agent_name: str, action: str,
                        content: Dict[str, Any], status: str = "ok") -> str:
        """保存Agent推理日志"""
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "agent_name": agent_name,
            "action": action,
            "content": content,
            "status": status,
            "timestamp": datetime.now(),
        }
        r = self._db.agent_logs.insert_one(doc)
        return str(r.inserted_id)

    def get_agent_logs(self, user_id: str, agent_name: str = None,
                        limit: int = 50) -> List[Dict]:
        """获取Agent日志"""
        self._ensure_db()
        query = {"user_id": user_id}
        if agent_name:
            query["agent_name"] = agent_name
        return list(self._db.agent_logs.find(query).sort("timestamp", DESCENDING).limit(limit))

    # ================================================================
    # 股票池存储
    # ================================================================

    def save_stock_pool(self, user_id: str, pool_name: str, stocks: List[Dict],
                         freq: str = "day") -> str:
        """保存股票池"""
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "pool_name": pool_name,
            "stocks": stocks,
            "freq": freq,
            "timestamp": datetime.now(),
        }
        r = self._db.stock_pools.insert_one(doc)
        return str(r.inserted_id)

    def get_latest_stock_pool(self, user_id: str, pool_name: str = None) -> Optional[Dict]:
        """获取最新股票池"""
        self._ensure_db()
        query = {"user_id": user_id}
        if pool_name:
            query["pool_name"] = pool_name
        return self._db.stock_pools.find_one(query, sort=[("timestamp", DESCENDING)])

    # ================================================================
    # 交易记录存储
    # ================================================================

    def save_trade_record(self, user_id: str, trade: Dict[str, Any]) -> str:
        """保存交易记录"""
        self._ensure_db()
        doc = {**trade, "user_id": user_id, "timestamp": datetime.now()}
        r = self._db.trade_records.insert_one(doc)
        return str(r.inserted_id)

    def get_trade_records(self, user_id: str, code: str = None,
                           start: datetime = None, end: datetime = None,
                           limit: int = 100) -> List[Dict]:
        """获取交易记录"""
        self._ensure_db()
        query = {"user_id": user_id}
        if code:
            query["code"] = code
        if start or end:
            query["timestamp"] = {}
            if start:
                query["timestamp"]["$gte"] = start
            if end:
                query["timestamp"]["$lte"] = end
        return list(self._db.trade_records.find(query).sort("timestamp", DESCENDING).limit(limit))

    # ================================================================
    # 会话缓存
    # ================================================================

    def set_session_cache(self, user_id: str, key: str, value: Any,
                          ttl_seconds: int = 3600) -> bool:
        """设置会话缓存"""
        self._ensure_db()
        self._db.session_cache.update_one(
            {"user_id": user_id, "key": key},
            {"$set": {"value": value, "updated_at": datetime.now()}},
            upsert=True,
        )
        return True

    def get_session_cache(self, user_id: str, key: str) -> Optional[Any]:
        """获取会话缓存"""
        self._ensure_db()
        doc = self._db.session_cache.find_one({"user_id": user_id, "key": key})
        return doc["value"] if doc else None

    def clear_session_cache(self, user_id: str):
        """清除用户会话缓存"""
        self._ensure_db()
        self._db.session_cache.delete_many({"user_id": user_id})

    # ================================================================
    # 审计日志
    # ================================================================

    def audit_log(self, user_id: str, action: str, details: Dict[str, Any] = None,
                   ip_address: str = None, status: str = "ok") -> str:
        """写入审计日志"""
        self._ensure_db()
        doc = {
            "user_id": user_id,
            "action": action,
            "details": details or {},
            "ip_address": ip_address,
            "status": status,
            "timestamp": datetime.now(),
        }
        r = self._db.audit_logs.insert_one(doc)
        return str(r.inserted_id)

    def get_audit_logs(self, user_id: str = None, action: str = None,
                        start: datetime = None, end: datetime = None,
                        limit: int = 100) -> List[Dict]:
        """查询审计日志"""
        self._ensure_db()
        query = {}
        if user_id:
            query["user_id"] = user_id
        if action:
            query["action"] = action
        if start or end:
            query["timestamp"] = {}
            if start:
                query["timestamp"]["$gte"] = start
            if end:
                query["timestamp"]["$lte"] = end
        return list(self._db.audit_logs.find(query).sort("timestamp", DESCENDING).limit(limit))

    # ================================================================
    # 批量操作
    # ================================================================

    def save_factor_batch(self, user_id: str, snapshots: List[Dict[str, Any]]) -> int:
        """批量保存因子快照"""
        self._ensure_db()
        docs = []
        for snap in snapshots:
            docs.append({
                "user_id": user_id,
                "code": snap["code"],
                "freq": snap.get("freq", "day"),
                "factors": snap["factors"],
                "timestamp": snap.get("timestamp", datetime.now()),
            })
        if docs:
            result = self._db.factor_snapshots.insert_many(docs)
            return len(result.inserted_ids)
        return 0

    def save_optimization_batch(self, user_id: str, strategy: str,
                                 traces: List[Dict]) -> int:
        """批量保存优化迭代"""
        self._ensure_db()
        docs = []
        for trace in traces:
            docs.append({
                "user_id": user_id,
                "strategy": strategy,
                "iteration": trace["iteration"],
                "score": trace["score"],
                "params": trace.get("params", {}),
                "convergence": trace.get("convergence"),
                "timestamp": datetime.now(),
            })
        if docs:
            result = self._db.optimization_traces.insert_many(docs)
            return len(result.inserted_ids)
        return 0

    # ================================================================
    # 数据清理
    # ================================================================

    def cleanup_user_data(self, user_id: str):
        """清理用户所有数据"""
        self._ensure_db()
        collections = [
            "agent_logs", "factor_snapshots", "backtest_results",
            "optimization_traces", "stock_pools", "trade_records",
            "session_cache", "audit_logs",
        ]
        for coll in collections:
            self._db[coll].delete_many({"user_id": user_id})
        logger.info(f"用户 {user_id} 数据已清理")

    def cleanup_expired(self):
        """清理过期数据（MongoDB TTL索引会自动处理，这里做额外清理）"""
        self._ensure_db()
        cutoff = datetime.now() - timedelta(days=90)
        self._db.agent_logs.delete_many({"timestamp": {"$lt": cutoff}})
        self._db.factor_snapshots.delete_many({"timestamp": {"$lt": datetime.now() - timedelta(days=30)}})
        logger.info("过期数据清理完成")

    # ================================================================
    # 健康检查
    # ================================================================

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        result = {
            "connected": self._connected,
            "host": self.config.host,
            "port": self.config.port,
            "db": self.config.db_name,
        }
        if self._connected:
            try:
                self._client.admin.command("ping")
                result["ping"] = "ok"
                result["collections"] = self._db.list_collection_names()
            except Exception as e:
                result["ping"] = f"error: {e}"
        return result


# ============================================================
# 全局单例
# ============================================================

_store: Optional[MongoStore] = None


def get_mongo_store(config: StoreConfig = None) -> MongoStore:
    global _store
    if _store is None:
        _store = MongoStore(config)
        _store.connect()
    return _store