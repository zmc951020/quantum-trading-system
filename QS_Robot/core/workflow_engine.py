#!/usr/bin/env python3
"""
一键选股自动化工作流引擎
========================
整合韬策略引擎 + 熵韬收敛优化器集群 + 自适应策略层的完整自动化工作流。

工作流阶段：
  1. 策略发现与注册 → 2. 参数优化 → 3. 回测验证 → 4. 股票池匹配
  → 5. 自适应策略选择 → 6. 信号生成 → 7. 交易配置输出

调用方式:
  from core.workflow_engine import get_workflow_engine
  engine = get_workflow_engine()
  result = engine.run_oneclick()  # 一键执行全流程
"""

import os
import sys
import time
import json
import logging
import threading
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class WorkflowStage:
    """工作流阶段状态"""
    name: str
    status: str = "pending"     # pending / running / success / failed / skipped
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class WorkflowResult:
    """一次完整工作流执行结果"""
    workflow_id: str
    workflow_name: str
    status: str = "pending"     # pending / running / success / failed / cancelled
    started_at: str = ""
    completed_at: str = ""
    total_elapsed: float = 0
    stages: List[WorkflowStage] = field(default_factory=list)
    final_stock_pool: List[Dict] = field(default_factory=list)
    final_signals: List[Dict] = field(default_factory=list)
    best_strategy: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================
# 工作流引擎
# ============================================================

class OneClickWorkflowEngine:
    """一键选股自动化工作流引擎

    整合 TauClusterEngine + Optimizer + AdaptationEngine + IntegrationBus
    提供端到端的自动化工作流执行。
    """

    def __init__(self):
        self._history: deque = deque(maxlen=50)
        self._current: Optional[WorkflowResult] = None
        self._running: bool = False
        self._lock = threading.RLock()
        self._callbacks: List[Callable] = []

        # 延迟导入的模块引用
        self._tau_engine = None
        self._integration_bus = None
        self._adaptation_engine = None
        self._strategy_manager = None

    # ============================================================
    # 公共 API — 一键执行
    # ============================================================

    def run_oneclick(self,
                     stock_pool: List[str] = None,
                     strategy_names: List[str] = None,
                     fast_mode: bool = False,
                     batch_mode: bool = False) -> WorkflowResult:
        """一键执行完整工作流

        优先使用 integration_bus.auto_full_workflow() 完整链路，
        （含 Vibe 分析、断点续算、风控评估、交易配置）
        若不可用则降级为手动 8 阶段流程。

        Args:
            stock_pool: 指定股票池，None 则使用全市场
            strategy_names: 指定策略，None 则自动发现
            fast_mode: 快速模式（跳过部分优化，使用缓存结果）
            batch_mode: 批量模式（不中断，优化所有策略后对比排名）

        Returns:
            WorkflowResult 完整执行结果
        """
        with self._lock:
            if self._running:
                result = WorkflowResult(
                    workflow_id="rejected",
                    workflow_name="一键选股",
                    status="failed",
                    errors=["已有工作流正在执行中，请等待完成"]
                )
                return result

            self._running = True
            workflow_id = f"WF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="一键选股自动化",
                started_at=datetime.now().isoformat(),
                status="running",
            )
            self._current = result

        try:
            self._ensure_modules()

            strategies = strategy_names or self._discover_strategies()
            if not strategies:
                result.status = "failed"
                result.errors.append("未发现任何策略")
                return result

            # 尝试使用 integration_bus.auto_full_workflow 完整链路
            if self._integration_bus and strategies:
                self._run_full_workflow(result, strategies, stock_pool, fast_mode, batch_mode)
            else:
                self._run_manual_workflow(result, strategies, stock_pool, fast_mode)

            result.status = "success"

        except Exception as e:
            logger.error(f"[Workflow] 一键执行失败: {e}")
            traceback.print_exc()
            result.status = "failed"
            result.errors.append(str(e))

        finally:
            result.completed_at = datetime.now().isoformat()
            result.total_elapsed = time.time() - self._get_start_time(result)
            with self._lock:
                self._running = False
                self._history.append(result)

            for cb in self._callbacks:
                try:
                    cb(result)
                except Exception:
                    pass

        return result

    def _run_full_workflow(self, result: WorkflowResult,
                           strategies: List[str],
                           stock_pool: List[str] = None,
                           fast_mode: bool = False,
                           batch_mode: bool = False):
        """使用 integration_bus.auto_full_workflow() 完整链路

        包含: Vibe分析 → 优化 → 持久化 → 股票池匹配 → 流转 → 风控 → 交易配置

        batch_mode=True 时不中断，优化所有策略后对比排名选出最佳。
        """
        strategy_results = []  # 批量模式收集所有策略结果

        for name in strategies:
            # 阶段0: Vibe 市场环境分析
            self._run_stage(result, "Vibe市场分析", self._stage_vibe_analysis, name)

            # 阶段1-6: 使用集成总线的完整流程
            self._run_stage(result, "完整自动化流程", self._stage_integration_full,
                           name, stock_pool=stock_pool, fast_mode=fast_mode)

            # 阶段7: 自适应策略
            self._run_stage(result, "自适应策略", self._stage_adapt)

            # 阶段8: 信号生成
            self._run_stage(result, "信号生成", self._stage_signals)

            last_stage = result.stages[-1] if result.stages else None
            if last_stage and last_stage.status == "success":
                if batch_mode:
                    strategy_results.append({
                        "name": name,
                        "score": (last_stage.data.get("optimized", [{}])[0].get("score", 0)
                                  if last_stage.data.get("optimized") else 0),
                    })
                    continue  # 批量模式：继续下一个策略
                else:
                    result.best_strategy = name
                    break  # 默认模式：第一个成功的策略即为最佳

        # 批量模式：对比排名选出最佳
        if batch_mode and strategy_results:
            strategy_results.sort(key=lambda x: x["score"], reverse=True)
            result.best_strategy = strategy_results[0]["name"]
            result.data["batch_ranking"] = strategy_results
            logger.info(f"[Workflow] 批量模式完成: {len(strategy_results)}个策略, "
                       f"最佳={result.best_strategy}")

    def _run_manual_workflow(self, result: WorkflowResult,
                             strategies: List[str],
                             stock_pool: List[str] = None,
                             fast_mode: bool = False):
        """降级手动 8 阶段流程（integration_bus 不可用时）"""
        # 阶段0: Vibe 市场环境分析
        self._run_stage(result, "Vibe市场分析", self._stage_vibe_analysis,
                       strategies[0] if strategies else "unknown")

        # 阶段1: 策略发现与注册
        self._run_stage(result, "策略发现", self._stage_discover, strategies)

        # 阶段2: 参数优化
        self._run_stage(result, "参数优化", self._stage_optimize, fast_mode=fast_mode)

        # 阶段3: 回测验证
        self._run_stage(result, "回测验证", self._stage_backtest)

        # 阶段4: 股票池匹配
        self._run_stage(result, "股票池匹配", self._stage_match_stocks,
                       stock_pool=stock_pool)

        # 阶段5: 自适应策略选择
        self._run_stage(result, "自适应策略", self._stage_adapt)

        # 阶段6: 信号生成
        self._run_stage(result, "信号生成", self._stage_signals)

        # 阶段7: 交易配置输出
        self._run_stage(result, "交易配置", self._stage_trading_config)

    def run_step(self, step_name: str) -> WorkflowStage:
        """执行单个步骤"""
        step_map = {
            "vibe": self._stage_vibe_analysis,
            "discover": self._stage_discover,
            "optimize": self._stage_optimize,
            "backtest": self._stage_backtest,
            "match": self._stage_match_stocks,
            "adapt": self._stage_adapt,
            "signals": self._stage_signals,
            "trading": self._stage_trading_config,
            "full": self._stage_integration_full,
        }

        stage = WorkflowStage(name=step_name, status="running",
                             started_at=datetime.now().isoformat())
        try:
            self._ensure_modules()
            if step_name in step_map:
                if step_name in ("vibe", "full"):
                    strategies = self._discover_strategies()
                    if strategies:
                        step_map[step_name](stage, strategies[0])
                    else:
                        stage.status = "skipped"
                        stage.message = "无可用策略"
                else:
                    step_map[step_name](stage)
            stage.status = "success"
        except Exception as e:
            stage.status = "failed"
            stage.error = str(e)
        finally:
            stage.completed_at = datetime.now().isoformat()
        return stage

    def _discover_strategies(self) -> List[str]:
        """自动发现策略名称列表"""
        try:
            from core.strategy_auto_discovery import get_auto_discovery
            discovery = get_auto_discovery(
                strategy_manager=self._strategy_manager,
                tau_engine=self._tau_engine,
                integration_bus=self._integration_bus,
            )
            scan_result = discovery.run_once()
            return scan_result.get("discovered", [])
        except Exception:
            if self._integration_bus:
                return self._integration_bus._get_all_strategy_names()
            return []

    # ============================================================
    # 阶段实现（完整链路版）
    # ============================================================

    def _stage_vibe_analysis(self, stage: WorkflowStage, strategy_name: str):
        """阶段0: Vibe 市场环境分析 + 因子初筛"""
        stage.message = "正在分析市场环境..."

        try:
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()

            # 市场环境标签
            market_env = {}
            if hasattr(vibe, 'analyze_market_environment'):
                market_env = vibe.analyze_market_environment()
            stage.data["market_env"] = market_env

            # 因子初筛股票池
            factor_stocks = []
            if hasattr(vibe, 'get_factor_screened_stocks'):
                factor_result = vibe.get_factor_screened_stocks(strategy_name)
                factor_stocks = factor_result.get("stocks", []) if isinstance(factor_result, dict) else []
            stage.data["vibe_factor_stocks"] = factor_stocks

            stage.message = (f"Vibe分析: regime={market_env.get('regime', '未知')}, "
                            f"因子初筛={len(factor_stocks)}只")
        except ImportError:
            stage.message = "Vibe 模块不可用，跳过"
        except Exception as e:
            logger.warning(f"[Workflow] Vibe分析失败: {e}")
            stage.message = f"Vibe分析异常: {e}"

    def _stage_integration_full(self, stage: WorkflowStage, strategy_name: str,
                                stock_pool: List[str] = None, fast_mode: bool = False):
        """阶段1-6: 使用集成总线完整流程"""
        stage.message = f"正在执行完整流程: {strategy_name}..."

        if not self._integration_bus:
            stage.status = "skipped"
            stage.message = "集成总线不可用"
            return

        try:
            result = self._integration_bus.auto_full_workflow(
                strategy_name,
                stock_pool=stock_pool,
                fast_mode=fast_mode,
            )

            if result.get("success"):
                stage.data["full_workflow"] = result
                stage.data["optimized"] = [{
                    "name": strategy_name,
                    "score": result.get("best_score", 0),
                    "params": result.get("best_params", {}),
                }]
                stage.data["trading_config"] = result.get("trading_config", {})
                stage.data["matched"] = result.get("pool_report", {})

                trading_cfg = result.get("trading_config", {})
                ready = trading_cfg.get("ready_to_trade", False)
                stage.message = (f"完整流程完成: {strategy_name}, "
                                f"ready_to_trade={ready}")

                # 永久继承优化结果
                if result.get("best_score"):
                    self._save_optimization_profiles([{
                        "name": strategy_name,
                        "score": result["best_score"],
                        "params": result.get("best_params", {}),
                    }])
            else:
                stage.status = "failed"
                stage.error = result.get("error", "未知错误")
                stage.message = f"流程失败: {stage.error}"
        except Exception as e:
            stage.status = "failed"
            stage.error = str(e)

    # ============================================================
    # 阶段实现（降级版）
    # ============================================================

    def _stage_discover(self, stage: WorkflowStage, strategy_names: List[str] = None):
        """阶段1: 策略发现与注册"""
        stage.message = "正在扫描策略目录..."

        if strategy_names:
            stage.data["strategies"] = strategy_names
            stage.message = f"使用指定策略: {len(strategy_names)}个"
            logger.info(f"[Workflow] 使用指定策略: {strategy_names}")
            return

        # 自动发现策略
        try:
            from core.strategy_auto_discovery import get_auto_discovery
            discovery = get_auto_discovery(
                strategy_manager=self._strategy_manager,
                tau_engine=self._tau_engine,
                integration_bus=self._integration_bus,
            )
            scan_result = discovery.run_once()
            discovered = scan_result.get("discovered", [])
            stage.data["strategies"] = discovered
            stage.data["scan_result"] = scan_result
            stage.message = f"发现 {len(discovered)} 个策略"
        except ImportError:
            # 降级：使用 integration_bus 获取策略列表
            if self._integration_bus:
                strategy_names = self._integration_bus._get_all_strategy_names()
                stage.data["strategies"] = strategy_names
                stage.message = f"使用已注册策略: {len(strategy_names)}个"

    def _stage_optimize(self, stage: WorkflowStage, fast_mode: bool = False):
        """阶段2: 参数优化"""
        strategies = stage.data.get("strategies", [])
        if not strategies:
            stage.status = "skipped"
            stage.message = "无策略需要优化"
            return

        stage.message = f"正在优化 {len(strategies)} 个策略..."

        optimized = []
        total = len(strategies)
        for i, name in enumerate(strategies):
            try:
                if self._integration_bus:
                    result = self._integration_bus.auto_optimize_strategy(
                        name, use_warm_start=True,
                    )
                    if result.get("success"):
                        optimized.append({
                            "name": name,
                            "score": result.get("best_score", 0),
                            "params": result.get("best_params", {}),
                        })
                stage.message = f"优化中... ({i + 1}/{total})"
            except Exception as e:
                logger.warning(f"[Workflow] 优化 {name} 失败: {e}")

        stage.data["optimized"] = optimized
        stage.message = f"优化完成: {len(optimized)}/{total} 成功"

        # 永久继承：保存优化结果到画像存储
        if optimized:
            self._save_optimization_profiles(optimized)

    def _stage_backtest(self, stage: WorkflowStage):
        """阶段3: 回测验证"""
        optimized = stage.data.get("optimized", [])
        if not optimized:
            stage.status = "skipped"
            stage.message = "无优化结果需要回测"
            return

        stage.message = f"正在回测 {len(optimized)} 个策略..."

        verified = []
        for item in optimized:
            name = item["name"]
            try:
                if self._integration_bus:
                    result = self._integration_bus.auto_backtest_strategy(name)
                else:
                    result = {"success": False, "error": "integration_bus 不可用"}

                if result.get("success"):
                    sharpe = result.get("sharpe", 0)
                    drawdown = result.get("max_drawdown", 0)
                    win_rate = result.get("win_rate", 0)

                    # 验证阈值
                    if sharpe > 1.0 and abs(drawdown) < 0.2 and win_rate > 0.45:
                        verified.append({
                            "name": name,
                            "sharpe": sharpe,
                            "drawdown": drawdown,
                            "win_rate": win_rate,
                            "status": "passed",
                        })
                    else:
                        verified.append({
                            "name": name,
                            "sharpe": sharpe,
                            "drawdown": drawdown,
                            "win_rate": win_rate,
                            "status": "failed",
                            "reason": "未达验证阈值",
                        })
            except Exception as e:
                logger.warning(f"[Workflow] 回测 {name} 失败: {e}")

        stage.data["verified"] = verified
        passed = sum(1 for v in verified if v.get("status") == "passed")
        stage.message = f"回测完成: {passed}/{len(verified)} 通过验证"

    def _stage_match_stocks(self, stage: WorkflowStage,
                            stock_pool: List[str] = None):
        """阶段4: 股票池匹配"""
        verified = stage.data.get("verified", [])
        passed = [v for v in verified if v.get("status") == "passed"]
        if not passed:
            stage.status = "skipped"
            stage.message = "无通过验证的策略需要匹配"
            return

        stage.message = f"正在匹配股票池..."

        matched = []
        for item in passed:
            name = item["name"]
            try:
                if self._integration_bus:
                    result = self._integration_bus.auto_match_stock_pool(
                        name, stock_pool=stock_pool
                    )
                    if result.get("success"):
                        matched.append({
                            "strategy": name,
                            "stocks": result.get("stocks", []),
                            "pool": result.get("pool", "candidate"),
                        })
            except Exception as e:
                logger.warning(f"[Workflow] 匹配 {name} 股票池失败: {e}")

        stage.data["matched"] = matched
        if matched:
            stage.data["final_stock_pool"] = list(set(
                s for m in matched for s in m.get("stocks", [])
            ))
        stage.message = f"匹配完成: {len(matched)} 个策略, {len(stage.data.get('final_stock_pool', []))} 只股票"

    def _stage_adapt(self, stage: WorkflowStage):
        """阶段5: 自适应策略选择"""
        matched = stage.data.get("matched", [])
        if not matched:
            stage.status = "skipped"
            stage.message = "无匹配结果需要自适应"
            return

        stage.message = "正在执行自适应策略选择..."

        try:
            if self._adaptation_engine:
                self._adaptation_engine.apply_adaptation()
                health = self._adaptation_engine.get_health_report()
                stage.data["adaptation"] = health
                stage.message = f"自适应完成: regime={health.get('market_state', {}).get('regime_label', 'unknown')}"
            else:
                stage.message = "自适应引擎不可用，使用默认权重"
        except Exception as e:
            logger.warning(f"[Workflow] 自适应策略失败: {e}")

    def _stage_signals(self, stage: WorkflowStage):
        """阶段6: 信号生成"""
        final_pool = stage.data.get("final_stock_pool", [])
        if not final_pool:
            stage.status = "skipped"
            stage.message = "无股票需要生成信号"
            return

        stage.message = f"正在生成 {len(final_pool)} 只股票信号..."

        signals = []
        try:
            if self._tau_engine:
                for symbol in final_pool[:20]:  # 限制数量
                    try:
                        decision = self._tau_engine.evaluate(price_data={
                            "symbol": symbol,
                        })
                        if decision and hasattr(decision, 'to_dict'):
                            signals.append(decision.to_dict())
                    except Exception:
                        pass

                stage.data["signals"] = signals
                stage.message = f"信号生成完成: {len(signals)} 条"
            else:
                stage.message = "集群引擎不可用"
        except Exception as e:
            logger.warning(f"[Workflow] 信号生成失败: {e}")

    def _stage_trading_config(self, stage: WorkflowStage):
        """阶段7: 交易配置输出"""
        signals = stage.data.get("signals", [])
        if not signals:
            stage.status = "completed"
            stage.message = "无交易信号，跳过交易配置"
            return

        stage.message = "正在生成交易配置..."

        config = {
            "generated_at": datetime.now().isoformat(),
            "total_signals": len(signals),
            "buy_signals": sum(1 for s in signals if s.get("direction", 0) > 0),
            "sell_signals": sum(1 for s in signals if s.get("direction", 0) < 0),
            "signals": signals[:10],  # 最多10条
            "risk_warnings": [],
            "mode": "paper_trading",  # 默认模拟盘
        }

        stage.data["trading_config"] = config
        stage.message = (f"交易配置生成完成: {config['buy_signals']}买/"
                         f"{config['sell_signals']}卖/{config['total_signals']}总")

    # ============================================================
    # 永久继承
    # ============================================================

    def _save_optimization_profiles(self, optimized: List[Dict]):
        """将优化结果永久保存到 StrategyProfileStore"""
        try:
            from core.adaptive_market_regime import StrategyProfileStore, \
                StrategyPerformanceProfile, BacktestProfileBuilder

            store = StrategyProfileStore()
            builder = BacktestProfileBuilder(profile_store=store)

            for item in optimized:
                profile = builder._create_default_profile(item["name"])
                profile.convergence_score = item.get("score", 0.5)
                profile.backtest_date = datetime.now().strftime("%Y-%m-%d")
                store.add_profile(profile)

            logger.info(f"[Workflow] 已永久保存 {len(optimized)} 个策略画像")
        except Exception as e:
            logger.warning(f"[Workflow] 保存画像失败: {e}")

    # ============================================================
    # 状态查询
    # ============================================================

    def get_status(self) -> Dict[str, Any]:
        """获取当前工作流状态"""
        with self._lock:
            current = self._current
            running = self._running

        status = {
            "running": running,
            "history_count": len(self._history),
        }

        if current:
            stages = []
            for s in current.stages:
                stages.append({
                    "name": s.name,
                    "status": s.status,
                    "message": s.message,
                    "elapsed": s.elapsed_seconds,
                })
            status.update({
                "workflow_id": current.workflow_id,
                "status": current.status,
                "started_at": current.started_at,
                "total_elapsed": current.total_elapsed,
                "stages": stages,
                "best_strategy": current.best_strategy,
                "final_stock_count": len(current.final_stock_pool),
                "signal_count": len(current.final_signals),
                "warnings": current.warnings,
                "errors": current.errors,
            })

        return status

    def get_history(self, limit: int = 10) -> List[Dict]:
        """获取历史工作流记录"""
        history = []
        for r in list(self._history)[-limit:]:
            history.append({
                "workflow_id": r.workflow_id,
                "status": r.status,
                "started_at": r.started_at,
                "total_elapsed": r.total_elapsed,
                "stages_ok": sum(1 for s in r.stages if s.status == "success"),
                "stages_total": len(r.stages),
                "best_strategy": r.best_strategy,
                "stock_count": len(r.final_stock_pool),
            })
        return history

    def on_complete(self, callback: Callable):
        """注册工作流完成回调"""
        self._callbacks.append(callback)

    # ============================================================
    # 内部方法
    # ============================================================

    def _ensure_modules(self):
        """延迟加载各模块"""
        if self._tau_engine is None:
            try:
                from core.tau_cluster_engine import TauClusterEngine
                self._tau_engine = TauClusterEngine()
                logger.info("[Workflow] TauClusterEngine 已加载")
            except ImportError:
                logger.warning("[Workflow] TauClusterEngine 不可用")

        if self._integration_bus is None:
            try:
                from core.integration_bus import IntegrationBus
                self._integration_bus = IntegrationBus()
                logger.info("[Workflow] IntegrationBus 已加载")
            except ImportError:
                logger.warning("[Workflow] IntegrationBus 不可用")

        if self._adaptation_engine is None:
            try:
                from core.adaptive_market_regime import get_adaptation_engine
                self._adaptation_engine = get_adaptation_engine(
                    tau_engine=self._tau_engine,
                    integration_bus=self._integration_bus,
                )
                logger.info("[Workflow] AdaptationEngine 已加载")
            except ImportError:
                logger.warning("[Workflow] AdaptationEngine 不可用")

        if self._strategy_manager is None:
            try:
                from core.enhanced_strategy_manager import EnhancedStrategyManager
                self._strategy_manager = EnhancedStrategyManager()
                logger.info("[Workflow] StrategyManager 已加载")
            except ImportError:
                logger.warning("[Workflow] StrategyManager 不可用")

    def _run_stage(self, result: WorkflowResult, name: str,
                   func: Callable, **kwargs):
        """执行单个阶段并记录"""
        stage = WorkflowStage(name=name, status="running",
                             started_at=datetime.now().isoformat())
        start = time.time()
        try:
            func(stage, **kwargs)
            if stage.status != "skipped":
                stage.status = "success"
        except Exception as e:
            stage.status = "failed"
            stage.error = str(e)
            logger.error(f"[Workflow] 阶段 {name} 失败: {e}")
            traceback.print_exc()
        stage.elapsed_seconds = round(time.time() - start, 2)
        stage.completed_at = datetime.now().isoformat()
        result.stages.append(stage)

    def _get_start_time(self, result: WorkflowResult) -> float:
        if result.stages:
            return datetime.fromisoformat(result.stages[0].started_at).timestamp()
        return time.time()


# ============================================================
# 全局单例
# ============================================================

_workflow_engine: Optional[OneClickWorkflowEngine] = None
_engine_lock = threading.Lock()


def get_workflow_engine() -> OneClickWorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        with _engine_lock:
            if _workflow_engine is None:
                _workflow_engine = OneClickWorkflowEngine()
    return _workflow_engine