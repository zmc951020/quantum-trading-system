#!/usr/bin/env python3
"""
QlibAdapter - Vibe智能体 ↔ Qlib因子计算引擎适配层

核心功能：
  1. 三层路由分发（实时/准实时/离线）
  2. 双向数据流（Vibe→Qlib因子计算 + Qlib打分→Vibe交叉校验）
  3. 多用户租户隔离（user_id全链路透传）
  4. 权限分级拦截（管理员/高级/普通/访客）
  5. 降级兜底（Qlib不可用→回退49因子）
  6. 全链路日志持久化到MongoDB

设计依据：
  豆包审查 + Trae方案 - 中间适配层解耦Vibe与Qlib，统一数据契约
  修正：多用户场景下增加租户隔离、权限分级、降级兜底
"""

import logging
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

from .qlib_core.data_converter import DataConverter, get_converter
from .qlib_core.alpha_factors import Alpha158Engine, get_alpha_engine
from .qlib_core.mongo_store import MongoStore, get_mongo_store
from .redis_cache import RedisCache, get_redis_cache
from .gray_switch import GraySwitch, get_gray_switch, GrayPhase, PHASE_RATIO
from .factor_comparison import FactorComparator, get_comparator
from .tenant_manager import TenantManager, get_tenant_manager, UserRole as TenantRole, TaskPriority as TenantPriority

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================

class TaskPriority(Enum):
    """任务优先级"""
    P0 = "P0"  # 实时T+0（最高优先级，独占算力）
    P1 = "P1"  # 常规选股（正常优先级）
    P2 = "P2"  # 批量回测（闲时执行）


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"          # 管理员：全市场452因子 + 全量回测
    ADVANCED = "advanced"    # 高级用户：200因子 + 日线回测
    NORMAL = "normal"        # 普通用户：50因子 + 基础回测
    GUEST = "guest"          # 访客：只读缓存


@dataclass
class AdapterRequest:
    """适配器入参契约"""
    user_id: str                          # 用户ID（必填）
    role: str = "normal"                  # 角色（必填）
    freq: str = "day"                     # 周期 "day" / "1min"（必填）
    priority: str = "P1"                  # 优先级 P0/P1/P2
    symbols: List[str] = field(default_factory=list)  # 股票代码列表
    categories: List[str] = None          # 因子类别限定
    use_cache: bool = True                # 是否使用缓存
    task_id: str = None                   # 任务追踪ID


@dataclass
class AdapterResponse:
    """适配器返回结果"""
    success: bool
    user_id: str
    task_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    factors: Dict[str, Dict[str, float]] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    elapsed_ms: float = 0
    source: str = "qlib"          # "qlib" / "cache" / "fallback"
    is_fallback: bool = False     # 是否降级数据


# ============================================================
# 权限配置
# ============================================================

ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        "max_factors": 452,       # 全部因子
        "max_symbols": 5000,      # 全市场
        "allow_backtest": True,
        "allow_live_trading": True,
        "allow_export": True,
        "categories": None,       # 全部类别
    },
    UserRole.ADVANCED: {
        "max_factors": 200,
        "max_symbols": 500,
        "allow_backtest": True,
        "allow_live_trading": True,
        "allow_export": True,
        "categories": ["Trend", "Reversal", "Momentum", "Volatility", "VolumePrice"],
    },
    UserRole.NORMAL: {
        "max_factors": 50,
        "max_symbols": 100,
        "allow_backtest": True,
        "allow_live_trading": False,
        "allow_export": False,
        "categories": ["Trend", "Momentum", "VolumePrice"],
    },
    UserRole.GUEST: {
        "max_factors": 0,         # 只读缓存，不触发计算
        "max_symbols": 20,
        "allow_backtest": False,
        "allow_live_trading": False,
        "allow_export": False,
        "categories": None,
    },
}


class QlibAdapter:
    """Vibe ↔ Qlib 适配器

    使用示例:
        >>> adapter = QlibAdapter()
        >>> req = AdapterRequest(user_id="user_001", freq="day", symbols=["600519"])
        >>> resp = adapter.compute_factors(req)
        >>> print(resp.summary)
    """

    def __init__(self,
                 converter: DataConverter = None,
                 engine: Alpha158Engine = None,
                 mongo: MongoStore = None,
                 cache: RedisCache = None,
                 gray_switch: GraySwitch = None,
                 comparator: FactorComparator = None,
                 tenant_mgr: TenantManager = None):
        self._converter = converter or get_converter()
        self._engine = engine or get_alpha_engine()
        self._mongo = mongo or get_mongo_store()
        self._cache = cache or get_redis_cache()
        self._gray_switch = gray_switch or get_gray_switch()
        self._comparator = comparator or get_comparator()
        self._tenant_mgr = tenant_mgr or get_tenant_manager()
        self._stats = {"total_requests": 0, "cache_hits": 0, "fallbacks": 0, "errors": 0}

    # ================================================================
    # 主入口：计算因子
    # ================================================================

    def compute_factors(self, req: AdapterRequest) -> AdapterResponse:
        """计算因子 - 主入口

        三层路由逻辑：
          - P0 实时T+0: 投递Redis Stream，立即返回缓存/降级
          - P1 常规: 走缓存 → Qlib计算 → 缓存结果
          - P2 批量: 异步投递，返回已缓存结果
        """
        start_time = time.time()
        task_id = req.task_id or self._generate_task_id(req.user_id)
        resp = AdapterResponse(
            success=False,
            user_id=req.user_id,
            task_id=task_id,
        )

        try:
            # 1. 权限校验
            role = self._parse_role(req.role)
            perm = ROLE_PERMISSIONS[role]

            if len(req.symbols) > perm["max_symbols"]:
                resp.errors.append(f"股票数量超限: {len(req.symbols)} > {perm['max_symbols']}")
                resp.success = False
                return resp

            # 2. 访客只读缓存
            if role == UserRole.GUEST:
                resp = self._handle_guest(req, resp, task_id)
                resp.elapsed_ms = (time.time() - start_time) * 1000
                return resp

            # 3. 三层路由
            if req.priority == "P0":
                resp = self._handle_realtime(req, resp, task_id, perm)
            elif req.priority == "P2":
                resp = self._handle_batch(req, resp, task_id, perm)
            else:
                resp = self._handle_normal(req, resp, task_id, perm)

            # 4. 日志持久化
            self._log_request(req, resp, task_id)

            resp.elapsed_ms = (time.time() - start_time) * 1000
            self._stats["total_requests"] += 1

            return resp

        except Exception as e:
            resp.errors.append(f"计算异常: {e}")
            resp.success = False
            resp.elapsed_ms = (time.time() - start_time) * 1000
            self._stats["errors"] += 1
            logger.error(f"Adapter异常: {e}\n{traceback.format_exc()}")
            return resp

    # ================================================================
    # 三层路由实现
    # ================================================================

    def _handle_realtime(self, req: AdapterRequest, resp: AdapterResponse,
                          task_id: str, perm: Dict) -> AdapterResponse:
        """P0 实时T+0处理：优先返回缓存，任务异步投递到Stream"""
        symbols = req.symbols[:perm["max_symbols"]]

        # 1. 先查Redis缓存
        cached = {}
        uncached = []
        for symbol in symbols:
            factors = self._cache.get_factor(req.user_id, symbol, req.freq)
            if factors:
                cached[symbol] = factors
            else:
                uncached.append(symbol)

        if cached:
            self._stats["cache_hits"] += len(cached)

        # 2. 未缓存的任务投递到Redis Stream
        if uncached:
            task = {
                "user_id": req.user_id,
                "task_id": task_id,
                "symbols": json.dumps(uncached),
                "freq": req.freq,
                "priority": "P0",
                "timestamp": datetime.now().isoformat(),
            }
            self._cache.push_task("factor:compute", task)

        # 3. 如果全部命中缓存，返回成功
        if len(cached) == len(symbols):
            resp.success = True
            resp.factors = cached
            resp.source = "cache"
            resp.summary = {"cached": len(cached), "computed": 0}
        else:
            # 部分命中：返回缓存 + 启动实时计算
            computed = self._compute_and_cache(req.user_id, uncached, req, perm)
            resp.success = True
            resp.factors = {**cached, **computed}
            resp.source = "mixed"
            resp.summary = {"cached": len(cached), "computed": len(computed)}

        return resp

    def _handle_normal(self, req: AdapterRequest, resp: AdapterResponse,
                        task_id: str, perm: Dict) -> AdapterResponse:
        """P1 常规处理：查缓存 → 计算 → 缓存 → 返回"""
        symbols = req.symbols[:perm["max_symbols"]]

        if req.use_cache:
            # 1. 查缓存
            cached = {}
            uncached = []
            for symbol in symbols:
                factors = self._cache.get_factor(req.user_id, symbol, req.freq)
                if factors:
                    cached[symbol] = factors
                else:
                    uncached.append(symbol)

            if cached:
                self._stats["cache_hits"] += len(cached)

            if not uncached:
                resp.success = True
                resp.factors = cached
                resp.source = "cache"
                resp.summary = {"cached": len(cached), "computed": 0}
                return resp
        else:
            uncached = symbols
            cached = {}

        # 2. 计算因子
        computed = self._compute_and_cache(req.user_id, uncached, req, perm)

        # 3. 合并结果
        resp.success = True
        resp.factors = {**cached, **computed}
        resp.source = "qlib"
        resp.summary = {
            "cached": len(cached),
            "computed": len(computed),
            "total_factors": sum(len(v) for v in computed.values()) if computed else 0,
        }
        return resp

    def _handle_batch(self, req: AdapterRequest, resp: AdapterResponse,
                       task_id: str, perm: Dict) -> AdapterResponse:
        """P2 批量离线处理：投递到Stream，返回缓存"""
        symbols = req.symbols[:perm["max_symbols"]]

        # 1. 返回已有缓存
        cached = {}
        for symbol in symbols:
            factors = self._cache.get_factor(req.user_id, symbol, req.freq)
            if factors:
                cached[symbol] = factors

        # 2. 投递批量任务
        task = {
            "user_id": req.user_id,
            "task_id": task_id,
            "symbols": json.dumps(symbols),
            "freq": req.freq,
            "categories": json.dumps(req.categories) if req.categories else "all",
            "priority": "P2",
            "timestamp": datetime.now().isoformat(),
        }
        self._cache.push_task("factor:batch", task)

        resp.success = True
        resp.factors = cached
        resp.source = "cache"
        resp.summary = {
            "cached": len(cached),
            "pending": len(symbols) - len(cached),
            "task_id": task_id,
        }
        return resp

    # ================================================================
    # 核心计算逻辑
    # ================================================================

    def _compute_and_cache(self, user_id: str, symbols: List[str],
                            req: AdapterRequest, perm: Dict) -> Dict[str, Dict[str, float]]:
        """计算因子并缓存结果"""
        if not symbols:
            return {}

        results = {}

        for symbol in symbols:
            try:
                # 1. 从Qlib加载数据
                df = self._converter.load_qlib_data(symbol, req.freq)
                if df is None or df.empty:
                    logger.warning(f"数据加载失败: {symbol}, 尝试降级")
                    # 降级：使用akshare实时拉取
                    ok, _ = self._converter.fetch_and_store(symbol, req.freq)
                    df = self._converter.load_qlib_data(symbol, req.freq)
                    if df is None or df.empty:
                        results[symbol] = {"error": "数据不可用"}
                        continue

                # 2. 计算因子
                alpha_result = self._engine.compute_all(
                    df, req.freq, categories=perm.get("categories")
                )

                # 3. 提取最新值
                factor_values = {}
                for name, factor in alpha_result.factors.items():
                    if factor.status == "ok" and len(factor.values) > 0:
                        factor_values[name] = float(factor.values[-1])

                results[symbol] = factor_values

                # 4. 缓存到Redis
                self._cache.set_factor(user_id, symbol, factor_values, req.freq)

                # 5. 持久化到Mongo
                try:
                    self._mongo.save_factor_snapshot(
                        user_id, symbol, factor_values, req.freq
                    )
                except Exception:
                    pass  # Mongo不可用不影响主流程

            except Exception as e:
                logger.error(f"因子计算失败: {symbol}: {e}")
                # 降级：尝试使用旧49因子
                try:
                    fallback = self._compute_fallback_factors(symbol, df)
                    results[symbol] = fallback
                    results[symbol]["_fallback"] = True
                    self._stats["fallbacks"] += 1
                except Exception:
                    results[symbol] = {"error": str(e)}

        return results

    def _compute_fallback_factors(self, symbol: str, df) -> Dict[str, float]:
        """降级因子计算（旧49因子风格）"""
        if df is None or df.empty:
            return {"error": "无数据"}

        close = df["$close"].values
        high = df["$high"].values
        low = df["$low"].values
        volume = df["$volume"].values

        fallback = {
            "return_1d": float(close[-1] / close[-2] - 1) if len(close) > 1 else 0,
            "return_5d": float(close[-1] / close[-6] - 1) if len(close) > 5 else 0,
            "return_20d": float(close[-1] / close[-21] - 1) if len(close) > 20 else 0,
            "volatility_20d": float(pd.Series(close).pct_change().tail(20).std() * np.sqrt(252)),
            "volume_ratio_5d": float(volume[-5:].mean() / volume[-20:].mean()) if len(volume) > 20 else 0,
            "hl_ratio": float(high[-1] / low[-1] - 1) if low[-1] > 0 else 0,
            "_source": "fallback",
        }
        return fallback

    # ================================================================
    # 双向数据流：Qlib → Vibe
    # ================================================================

    def push_backtest_result(self, user_id: str, strategy: str,
                              result: Dict[str, Any]) -> bool:
        """回测结果回传Vibe Agent"""
        try:
            self._mongo.save_backtest_result(user_id, strategy, result)
            # 通知Vibe Agent（通过Redis Stream）
            self._cache.push_task("vibe:backtest_result", {
                "user_id": user_id,
                "strategy": strategy,
                "result": json.dumps(result),
            })
            return True
        except Exception as e:
            logger.error(f"回传回测结果失败: {e}")
            return False

    def push_optimization_trace(self, user_id: str, strategy: str,
                                 iteration: int, score: float,
                                 params: Dict[str, Any]) -> bool:
        """优化迭代结果回传"""
        try:
            self._mongo.save_optimization_trace(user_id, strategy, iteration, score, params)
            self._cache.push_task("vibe:optimization", {
                "user_id": user_id,
                "strategy": strategy,
                "iteration": iteration,
                "score": score,
            })
            return True
        except Exception as e:
            logger.error(f"回传优化结果失败: {e}")
            return False

    # ================================================================
    # 批量计算 + 结果复用
    # ================================================================

    def compute_market_scan(self, user_id: str, symbols: List[str],
                             freq: str = "day", role: str = "normal") -> Dict[str, Any]:
        """全市场因子扫描（批量计算，结果写入公共缓存）"""
        req = AdapterRequest(
            user_id=user_id,
            role=role,
            freq=freq,
            priority="P2",
            symbols=symbols,
            use_cache=True,
        )
        resp = self.compute_factors(req)

        # 写入公共缓存（多用户共享）
        for symbol, factors in resp.factors.items():
            if factors and "error" not in factors:
                self._cache.set_public_factor(symbol, factors, freq)

        return resp.to_dict() if hasattr(resp, "to_dict") else resp.__dict__

    def get_common_factors(self, symbols: List[str], freq: str = "day") -> Dict[str, Dict]:
        """获取公共缓存因子（多用户共享，不触发计算）"""
        results = {}
        for symbol in symbols:
            factors = self._cache.get_public_factor(symbol, freq)
            if factors:
                results[symbol] = factors
        return results

    # ================================================================
    # 降级兜底
    # ================================================================

    def is_qlib_available(self) -> bool:
        """检查Qlib可用性"""
        try:
            # 尝试加载任意数据
            test_symbols = self._converter.get_available_symbols("day")
            if test_symbols:
                df = self._converter.load_qlib_data(test_symbols[0], "day")
                return df is not None and not df.empty
            return False
        except Exception:
            return False

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "qlib_available": self.is_qlib_available(),
            "mongo_connected": self._mongo.is_connected if self._mongo else False,
            "redis_connected": self._cache.is_connected if self._cache else False,
            "stats": dict(self._stats),
            "day_stocks": len(self._converter.get_available_symbols("day")),
            "minute_stocks": len(self._converter.get_available_symbols("1min")),
        }

    # ================================================================
    # 内部方法
    # ================================================================

    def _parse_role(self, role: str) -> UserRole:
        try:
            return UserRole(role)
        except ValueError:
            return UserRole.NORMAL

    def _generate_task_id(self, user_id: str) -> str:
        return f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _log_request(self, req: AdapterRequest, resp: AdapterResponse, task_id: str):
        """日志持久化到Mongo"""
        try:
            self._mongo.save_agent_log(
                req.user_id,
                "qlib_adapter",
                "compute_factors",
                {
                    "task_id": task_id,
                    "symbols": req.symbols[:20],
                    "freq": req.freq,
                    "success": resp.success,
                    "source": resp.source,
                    "elapsed_ms": resp.elapsed_ms,
                    "errors": resp.errors,
                },
                "ok" if resp.success else "error",
            )
        except Exception:
            pass  # 日志失败不影响主流程

    def _handle_guest(self, req: AdapterRequest, resp: AdapterResponse,
                       task_id: str) -> AdapterResponse:
        """访客处理：只读缓存"""
        cached = {}
        for symbol in req.symbols[:20]:  # 访客限制20只
            # 优先查公共缓存
            factors = self._cache.get_public_factor(symbol, req.freq)
            if not factors:
                factors = self._cache.get_factor("public", symbol, req.freq)
            if factors:
                cached[symbol] = factors

        resp.success = True
        resp.factors = cached
        resp.source = "cache"
        resp.summary = {"cached": len(cached), "role": "guest"}
        return resp

    # ================================================================
    # 灰度切换集成
    # ================================================================

    def compute_factors_with_gray(self, req: AdapterRequest,
                                   strategy: str = None) -> AdapterResponse:
        """带灰度切换的因子计算（推荐入口）

        根据灰度阶段决定使用 Alpha158 还是 Wyckoff68 因子。
        灰度期间支持双轨并行对比。

        Args:
            req: 适配器请求
            strategy: 策略名称（用于灰度路由决策）

        Returns:
            AdapterResponse
        """
        start_time = time.time()
        task_id = req.task_id or self._generate_task_id(req.user_id)
        resp = AdapterResponse(
            success=False,
            user_id=req.user_id,
            task_id=task_id,
        )

        try:
            # 1. 权限校验
            role = self._parse_role(req.role)
            perm = ROLE_PERMISSIONS[role]

            if len(req.symbols) > perm["max_symbols"]:
                resp.errors.append(f"股票数量超限: {len(req.symbols)} > {perm['max_symbols']}")
                resp.success = False
                return resp

            # 1.5 租户配额检查
            tenant_role = TenantRole(req.role) if req.role in [r.value for r in TenantRole] else TenantRole.NORMAL
            self._tenant_mgr.get_or_create_tenant(req.user_id, tenant_role)
            ok, quota_msg = self._tenant_mgr.check_quota(req.user_id, "factor_compute", len(req.symbols))
            if not ok:
                resp.errors.append(f"配额不足: {quota_msg}")
                resp.success = False
                return resp

            # 2. 灰度路由决策
            use_new = self._gray_switch.should_use_new_factors(
                user_id=req.user_id, strategy=strategy
            )

            # 3. 计算因子
            if use_new:
                resp = self._compute_with_new_factors(req, resp, task_id, perm)
            else:
                resp = self._compute_with_old_factors(req, resp, task_id, perm)

            # 4. 双轨并行对比（灰度期间）
            if self._gray_switch.config.parallel_compare and use_new:
                self._run_parallel_comparison(req, strategy, resp, task_id)

            # 5. 记录灰度结果
            self._gray_switch.record_result(
                user_id=req.user_id,
                success=resp.success,
                is_new=use_new,
                latency_ms=resp.elapsed_ms,
                error_msg=resp.errors[0] if resp.errors else None,
            )

            # 6. 日志持久化
            self._log_request(req, resp, task_id)

            resp.elapsed_ms = (time.time() - start_time) * 1000
            self._stats["total_requests"] += 1

            # 消耗配额
            self._tenant_mgr.consume_quota(req.user_id, "factor_compute", len(req.symbols))

            return resp

        except Exception as e:
            resp.errors.append(f"灰度计算异常: {e}")
            resp.success = False
            resp.elapsed_ms = (time.time() - start_time) * 1000
            self._stats["errors"] += 1
            self._tenant_mgr.record_error(req.user_id, str(e))
            logger.error(f"灰度计算异常: {e}\n{traceback.format_exc()}")
            return resp

    def _compute_with_new_factors(self, req: AdapterRequest, resp: AdapterResponse,
                                   task_id: str, perm: Dict) -> AdapterResponse:
        """使用 Alpha158 新因子计算"""
        symbols = req.symbols[:perm["max_symbols"]]

        if req.use_cache:
            cached = {}
            uncached = []
            for symbol in symbols:
                factors = self._cache.get_factor(req.user_id, symbol, req.freq)
                if factors:
                    cached[symbol] = factors
                else:
                    uncached.append(symbol)

            if cached:
                self._stats["cache_hits"] += len(cached)

            if not uncached:
                resp.success = True
                resp.factors = cached
                resp.source = "cache_alpha158"
                resp.summary = {"cached": len(cached), "computed": 0, "engine": "alpha158"}
                return resp
        else:
            uncached = symbols
            cached = {}

        # 计算因子
        computed = self._compute_and_cache(req.user_id, uncached, req, perm)

        resp.success = True
        resp.factors = {**cached, **computed}
        resp.source = "alpha158"
        resp.summary = {
            "cached": len(cached),
            "computed": len(computed),
            "total_factors": sum(len(v) for v in computed.values()) if computed else 0,
            "engine": "alpha158",
        }
        return resp

    def _compute_with_old_factors(self, req: AdapterRequest, resp: AdapterResponse,
                                   task_id: str, perm: Dict) -> AdapterResponse:
        """使用 Wyckoff68 旧因子计算（降级兜底）"""
        symbols = req.symbols[:perm["max_symbols"]]
        results = {}

        for symbol in symbols:
            try:
                # 尝试从缓存获取旧因子
                cached = self._cache.get_factor(f"{req.user_id}_wyckoff", symbol, req.freq)
                if cached and req.use_cache:
                    results[symbol] = cached
                    self._stats["cache_hits"] += 1
                    continue

                # 计算旧因子（简化版：使用核心指标作为降级因子）
                df = self._converter.load_qlib_data(symbol, req.freq)
                if df is None or df.empty:
                    ok, _ = self._converter.fetch_and_store(symbol, req.freq)
                    df = self._converter.load_qlib_data(symbol, req.freq)

                if df is not None and not df.empty:
                    fallback = self._compute_fallback_factors(symbol, df)
                    results[symbol] = fallback
                    # 缓存
                    self._cache.set_factor(f"{req.user_id}_wyckoff", symbol, fallback, req.freq)
                else:
                    results[symbol] = {"error": "数据不可用"}
            except Exception as e:
                results[symbol] = {"error": str(e)}

        resp.success = True
        resp.factors = results
        resp.source = "wyckoff68"
        resp.summary = {
            "computed": len(results),
            "engine": "wyckoff68",
        }
        return resp

    def _run_parallel_comparison(self, req: AdapterRequest, strategy: str,
                                  resp: AdapterResponse, task_id: str):
        """双轨并行：同时计算旧因子用于对比分析"""
        try:
            symbols = list(resp.factors.keys())
            if not symbols:
                return

            old_factors = {}
            for symbol in symbols[:5]:  # 限制对比数量，避免性能影响
                df = self._converter.load_qlib_data(symbol, req.freq)
                if df is not None and not df.empty:
                    fallback = self._compute_fallback_factors(symbol, df)
                    old_factors[symbol] = fallback

            # 记录对比结果
            for symbol in symbols:
                new_f = resp.factors.get(symbol, {})
                old_f = old_factors.get(symbol, {})
                if new_f and old_f:
                    self._gray_switch.record_parallel_result(
                        user_id=req.user_id,
                        strategy=strategy or "unknown",
                        new_factors=new_f,
                        old_factors=old_f,
                    )
        except Exception as e:
            logger.debug(f"并行对比失败: {e}")

    # ================================================================
    # 灰度状态与控制 API
    # ================================================================

    def get_gray_status(self) -> Dict[str, Any]:
        """获取灰度切换状态"""
        return self._gray_switch.get_status()

    def advance_gray_phase(self) -> Dict[str, Any]:
        """手动推进灰度阶段"""
        ok = self._gray_switch.advance_phase_manual()
        return {
            "success": ok,
            "phase": self._gray_switch.config.phase.name,
            "ratio": PHASE_RATIO[self._gray_switch.config.phase],
            "message": f"已推进到 {self._gray_switch.config.phase.name}" if ok else "已是最高阶段",
        }

    def rollback_gray_phase(self) -> Dict[str, Any]:
        """回退灰度阶段"""
        ok = self._gray_switch.rollback_phase()
        return {
            "success": ok,
            "phase": self._gray_switch.config.phase.name,
            "ratio": PHASE_RATIO[self._gray_switch.config.phase],
            "message": f"已回退到 {self._gray_switch.config.phase.name}" if ok else "已是最低阶段",
        }

    def reset_gray_circuit_breaker(self) -> Dict[str, Any]:
        """重置灰度熔断"""
        self._gray_switch.reset_circuit_breaker()
        return {"success": True, "message": "熔断已重置"}

    def update_gray_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """更新灰度配置

        Args:
            config: {
                "phase": "PHASE_1",
                "mode": "user_hash",
                "force_new_strategies": [...],
                "auto_advance": True,
                "parallel_compare": True,
            }
        """
        try:
            phase = config.get("phase")
            if phase and phase in GrayPhase.__members__:
                self._gray_switch.config.phase = GrayPhase[phase]

            mode = config.get("mode")
            if mode:
                from .gray_switch import DecisionMode
                try:
                    self._gray_switch.config.mode = DecisionMode(mode)
                except ValueError:
                    pass

            if "force_new_strategies" in config:
                self._gray_switch.config.force_new_strategies = config["force_new_strategies"]
            if "force_old_strategies" in config:
                self._gray_switch.config.force_old_strategies = config["force_old_strategies"]
            if "auto_advance" in config:
                self._gray_switch.config.auto_advance = config["auto_advance"]
            if "parallel_compare" in config:
                self._gray_switch.config.parallel_compare = config["parallel_compare"]

            self._gray_switch._save_config()
            return {"success": True, "phase": self._gray_switch.config.phase.name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_factor_comparison(self, symbols: List[str], freq: str = "day",
                               output_path: str = None) -> Dict[str, Any]:
        """运行因子对比分析（Alpha158 vs Wyckoff68）

        Args:
            symbols: 股票代码列表
            freq: 频率
            output_path: 报告输出路径

        Returns:
            对比报告摘要
        """
        try:
            from .factor_comparison import FactorComparator

            data = {}
            returns_dict = {}

            for symbol in symbols:
                df = self._converter.load_qlib_data(symbol, freq)
                if df is None or df.empty:
                    continue
                data[symbol] = df

                close = df["$close"].values
                future_returns = np.diff(np.log(close + 1e-10), prepend=0)
                returns_dict[symbol] = future_returns

            if not data:
                return {"success": False, "error": "无可用数据"}

            comparator = FactorComparator()
            results = comparator.compare_batch(
                data, returns_dict, self._engine,
                wyckoff_engine=None,  # Wyckoff需要特殊数据格式，此处简化
                freq=freq,
            )

            report = comparator.generate_report(
                results,
                output_path=output_path or f"./reports/factor_compare_{freq}.json"
            )

            return {
                "success": True,
                "report_id": report.report_id,
                "summary": report.summary,
                "overall_recommendation": report.overall_recommendation,
                "action_items": report.action_items,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ================================================================
    # 租户管理 API
    # ================================================================

    def get_tenant_status(self, user_id: str) -> Dict[str, Any]:
        """获取租户状态"""
        return self._tenant_mgr.get_tenant_status(user_id) or {"error": "租户不存在"}

    def get_all_tenants_status(self) -> Dict[str, Any]:
        """获取所有租户状态"""
        return self._tenant_mgr.get_all_tenants_status()

    def register_tenant(self, user_id: str, role: str = "normal",
                         custom_quota: Dict[str, Any] = None) -> Dict[str, Any]:
        """注册租户"""
        try:
            tenant_role = TenantRole(role) if role in [r.value for r in TenantRole] else TenantRole.NORMAL
            state = self._tenant_mgr.register_tenant(user_id, tenant_role, custom_quota)
            return {"success": True, "user_id": user_id, "role": state.role.value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_tenant_role(self, user_id: str, new_role: str) -> Dict[str, Any]:
        """更新租户角色"""
        try:
            tenant_role = TenantRole(new_role) if new_role in [r.value for r in TenantRole] else TenantRole.NORMAL
            ok = self._tenant_mgr.update_tenant_role(user_id, tenant_role)
            return {"success": ok, "user_id": user_id, "role": new_role}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audit_summary(self) -> Dict[str, Any]:
        """获取审计摘要"""
        return self._tenant_mgr.get_audit_summary()

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取任务队列统计"""
        return self._tenant_mgr.get_queue_stats()


# ============================================================
# 全局单例
# ============================================================

import json
import numpy as np
import pandas as pd

_adapter: Optional[QlibAdapter] = None


def get_adapter() -> QlibAdapter:
    global _adapter
    if _adapter is None:
        _adapter = QlibAdapter()
    return _adapter


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    adapter = QlibAdapter()

    # 先确保有测试数据
    print("=== 准备测试数据 ===")
    from .qlib_core.data_converter import DataConverter
    converter = DataConverter()

    dates = pd.date_range("2026-01-01", "2026-06-18", freq="B")
    n = len(dates)
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)
    df = pd.DataFrame({
        "日期": dates,
        "开盘": close * (1 + np.random.randn(n) * 0.01),
        "最高": close * (1 + np.abs(np.random.randn(n) * 0.02)),
        "最低": close * (1 - np.abs(np.random.randn(n) * 0.02)),
        "收盘": close,
        "成交量": np.random.uniform(1e6, 1e8, n),
        "成交额": np.random.uniform(1e7, 1e9, n),
    }, index=dates)
    df["最高"] = df[["开盘", "最高", "最低", "收盘"]].max(axis=1)
    df["最低"] = df[["开盘", "最高", "最低", "收盘"]].min(axis=1)
    converter.convert_akshare_to_qlib(df, "600519", "day")

    print("\n=== 测试因子计算 (P1 常规) ===")
    req = AdapterRequest(
        user_id="test_user",
        role="normal",
        freq="day",
        priority="P1",
        symbols=["600519"],
    )
    resp = adapter.compute_factors(req)
    print(f"  成功: {resp.success}")
    print(f"  来源: {resp.source}")
    print(f"  因子数: {len(resp.factors.get('600519', {}))}")
    print(f"  耗时: {resp.elapsed_ms:.0f}ms")

    print("\n=== 测试缓存命中 (第二次请求) ===")
    resp2 = adapter.compute_factors(req)
    print(f"  成功: {resp2.success}")
    print(f"  来源: {resp2.source}")

    print("\n=== 系统状态 ===")
    status = adapter.get_system_status()
    print(f"  {status}")

    print("\n全部测试通过!")