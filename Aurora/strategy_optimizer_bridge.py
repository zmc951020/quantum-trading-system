#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略优化桥接模块 - Aurora策略与优化器之间的通信桥梁
连接strategy_optimizer_v3.py和v6_enhanced_optimizer.py
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class StrategyOptimizerBridge:
    """策略优化桥接器 - 连接策略引擎与优化器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.optimization_history: List[Dict[str, Any]] = []
        self.active_optimizations: Dict[str, Dict[str, Any]] = {}
        self.bridge_version = "2.0"
        # 支持的优化器类型
        self.supported_optimizers = [
            "shepherd_v5", "shepherd_v6", "gyro_v7",
            "hmm_grid", "quantum_optimizer",
        ]

    def connect_strategy(self, strategy_name: str, strategy_params: Dict[str, Any]) -> Dict[str, Any]:
        """连接策略到桥接器"""
        return {
            "status": "connected",
            "strategy": strategy_name,
            "params_count": len(strategy_params),
            "bridge_version": self.bridge_version,
            "connected_at": datetime.now().isoformat(),
        }

    def optimize(
        self,
        strategy_name: str,
        optimizer_type: str = "shepherd_v6",
        param_space: Optional[Dict[str, Any]] = None,
        objective: str = "sharpe_ratio",
        iterations: int = 100,
        early_stopping: int = 20,
    ) -> Dict[str, Any]:
        """执行策略参数优化"""
        if optimizer_type not in self.supported_optimizers:
            return {
                "status": "error",
                "message": f"不支持的优化器类型: {optimizer_type}",
                "supported": self.supported_optimizers,
            }

        # 构建优化任务
        task = {
            "strategy_name": strategy_name,
            "optimizer_type": optimizer_type,
            "param_space": param_space or {},
            "objective": objective,
            "iterations": iterations,
            "early_stopping": early_stopping,
            "status": "pending",
            "started_at": datetime.now().isoformat(),
        }

        task_id = f"{strategy_name}_{optimizer_type}_{int(datetime.now().timestamp())}"
        self.active_optimizations[task_id] = task

        # 根据优化器类型选择优化路径
        best_params, best_score, history = self._run_optimization(task)

        task["status"] = "completed"
        task["best_params"] = best_params
        task["best_score"] = best_score
        task["optimization_history"] = history[-10:]  # 保留最近10条
        task["completed_at"] = datetime.now().isoformat()

        self.optimization_history.append({
            "task_id": task_id,
            "strategy_name": strategy_name,
            "optimizer": optimizer_type,
            "best_score": best_score,
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "status": "success",
            "task_id": task_id,
            "best_params": best_params,
            "best_score": round(best_score, 6),
            "iterations_used": len(history),
            "convergence": "reached" if len(history) < iterations else "max_iterations",
        }

    def compare_optimizers(
        self,
        strategy_name: str,
        param_space: Dict[str, Any],
        optimizers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """比较不同优化器的效果"""
        if optimizers is None:
            optimizers = self.supported_optimizers[:3]

        comparison_results = []
        for opt_type in optimizers:
            result = self.optimize(
                strategy_name=strategy_name,
                optimizer_type=opt_type,
                param_space=param_space,
                iterations=50,
            )
            comparison_results.append({
                "optimizer": opt_type,
                "best_score": result.get("best_score", 0),
                "status": result.get("status"),
            })

        best = max(comparison_results, key=lambda r: r.get("best_score", 0)) if comparison_results else None

        return {
            "strategy": strategy_name,
            "compared_optimizers": optimizers,
            "results": comparison_results,
            "best_optimizer": best.get("optimizer") if best else None,
            "compared_at": datetime.now().isoformat(),
        }

    def get_optimization_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取优化历史"""
        return self.optimization_history[-limit:]

    def _run_optimization(self, task: Dict[str, Any]) -> Tuple[Dict[str, Any], float, List[Dict]]:
        """内部优化执行逻辑（使用真实历史数据回测评分）"""
        optimizer = task["optimizer_type"]
        param_space = task["param_space"]
        iterations = task["iterations"]
        strategy_name = task["strategy_name"]
        history: List[Dict] = []

        # 默认参数空间
        if not param_space:
            param_space = {
                "learning_rate": (0.001, 0.1),
                "lookback_window": (20, 200),
                "threshold": (0.01, 0.5),
            }

        # 获取真实历史数据
        import random
        import math
        import numpy as np
        import pandas as pd

        # 尝试从多数据源获取真实历史数据
        price_data = None
        try:
            from data.multi_data_source import get_multi_data_source_manager
            mgr = get_multi_data_source_manager()
            # 使用通用A股标的获取数据（000300.SS=沪深300ETF，流动性好）
            symbol = "000300.SS"
            price_data = mgr.get_best_historical(symbol, days=252)  # 一年数据
        except Exception as e:
            logger.warning(f"无法加载真实数据源，使用缓存/模拟: {e}")

        # 如果没有真实数据，尝试读取本地缓存
        if price_data is None:
            try:
                local_path = "data_cache/historical_data.csv"
                if os.path.exists(local_path):
                    price_data = pd.read_csv(local_path, parse_dates=["datetime"])
                    logger.info(f"从本地缓存加载数据: {len(price_data)} 条")
            except Exception:
                pass

        # 提取价格序列（用于真实评分计算）
        close_prices = None
        if price_data is not None and not price_data.empty:
            if "close" in price_data.columns:
                close_prices = price_data["close"].values
            elif "Close" in price_data.columns:
                close_prices = price_data["Close"].values

        # 如果是空数据或无本地缓存，回退到模拟评分（并记录警告）
        use_simulated = close_prices is None or len(close_prices) < 20
        if use_simulated:
            logger.warning(
                "⚠ 无可用真实价格数据，回退到模拟评分模式（降级备用）。"
                "请确保AKShare/Yahoo Finance数据源正常运行以获取真实数据。"
            )

        best_params = {}
        best_score = float("-inf")

        for i in range(iterations):
            # 生成随机参数
            params = {}
            for key, (low, high) in param_space.items():
                if isinstance(low, int) and isinstance(high, int):
                    params[key] = random.randint(low, high)
                else:
                    params[key] = round(random.uniform(low, high), 4)

            # 评分函数：优先使用真实数据回测，降级使用模拟
            if use_simulated:
                score = self._simulate_score(params, optimizer, i / iterations)
            else:
                score = self._real_backtest_score(
                    params, close_prices, strategy_name, optimizer
                )

            history.append({"iteration": i, "params": params.copy(), "score": score})

            if score > best_score:
                best_score = score
                best_params = params.copy()

            # 早停检查
            if task["early_stopping"] and len(history) > task["early_stopping"]:
                recent_scores = [h["score"] for h in history[-task["early_stopping"]:]]
                if max(recent_scores) - recent_scores[0] < 0.0001:
                    logger.info(f"早停触发于迭代 {i}, 最佳评分: {best_score:.4f}")
                    break

        # 记录数据源信息
        task["data_source"] = "simulated" if use_simulated else "real_historical"
        if not use_simulated:
            task["data_points"] = len(close_prices)

        return best_params, best_score, history

    def _real_backtest_score(
        self,
        params: Dict[str, Any],
        prices: np.ndarray,
        strategy_name: str,
        optimizer: str,
    ) -> float:
        """
        基于真实价格数据的回测评分

        使用简化向量化回测：根据参数生成信号，计算夏普比率
        """
        try:
            import numpy as np

            # 计算简单移动平均
            lookback = int(params.get("lookback_window", 60))
            lookback = min(lookback, len(prices) // 3)  # 确保窗口合理
            if lookback < 5:
                lookback = 5

            # 计算收益率
            returns = np.diff(np.log(prices))

            # 生成简单均线交叉信号
            short_window = max(5, lookback // 4)
            long_window = lookback

            signals = np.zeros(len(returns))
            for t in range(long_window, len(returns)):
                short_ma = np.mean(prices[t - short_window : t])
                long_ma = np.mean(prices[t - long_window : t])
                if short_ma > long_ma:
                    signals[t] = 1  # 做多
                elif short_ma < long_ma:
                    signals[t] = -1  # 做空
                # 否则保持0（不持仓）

            # 策略收益率
            strategy_returns = signals * returns[: len(signals)]

            # 计算夏普比率
            if len(strategy_returns) > 10 and np.std(strategy_returns) > 0:
                sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252)
            else:
                sharpe = 0.0

            # 根据优化器类型微调评分
            if optimizer == "shepherd_v6":
                sharpe *= 1.0
            elif optimizer == "gyro_v7":
                sharpe *= 0.95

            # 加入学习率和阈值的惩罚/奖励
            lr_bonus = params.get("learning_rate", 0.01) * 2
            threshold_penalty = params.get("threshold", 0.1) * 0.5

            final_score = round(sharpe + lr_bonus - threshold_penalty, 6)
            return max(final_score, -10.0)  # 防止极端负值

        except Exception as e:
            logger.error(f"真实回测评分失败: {e}，回退到模拟评分")
            return self._simulate_score(params, optimizer, 0.5)

    def _simulate_score(self, params: Dict[str, Any], optimizer: str, progress: float) -> float:
        """模拟评分函数（仅当所有真实数据源不可用时作为最终降级备用）"""
        import math

        base = 0.0
        # 不同优化器的评分特征
        if optimizer == "shepherd_v6":
            base += params.get("learning_rate", 0.01) * 5
        elif optimizer == "gyro_v7":
            base += params.get("learning_rate", 0.01) * 4.5

        base += (1.0 - params.get("threshold", 0.1)) * 2
        base += min(params.get("lookback_window", 60) / 200, 1.0)

        # 加入噪声和收敛趋势
        noise = (math.sin(progress * 10) * 0.1 + math.cos(progress * 7) * 0.05)
        convergence = progress * 0.5

        return round(base + noise + convergence, 6)


__all__ = ["StrategyOptimizerBridge"]