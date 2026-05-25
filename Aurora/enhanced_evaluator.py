#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强评估器 - Aurora系统性能与质量评估
提供多维度的策略评估和性能分析
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EvaluationMetrics:
    """评估指标"""
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    annual_return: float = 0.0
    volatility: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_trades: int = 0
    avg_holding_days: float = 0.0


class EnhancedEvaluator:
    """增强评估器 - 多维度策略评估"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.risk_free_rate = self.config.get("risk_free_rate", 0.03)
        self.benchmark_returns = self.config.get("benchmark_returns", [])
        self.evaluation_history: List[Dict[str, Any]] = []

    def evaluate_strategy(
        self,
        returns: List[float],
        trades: List[Dict[str, Any]],
        benchmark: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """评估策略表现"""
        metrics = self._calculate_metrics(returns, trades)
        alpha, beta = self._calculate_alpha_beta(returns, benchmark or self.benchmark_returns)

        result = {
            "metrics": {
                "sharpe_ratio": round(metrics.sharpe_ratio, 4),
                "max_drawdown": round(metrics.max_drawdown, 4),
                "win_rate": round(metrics.win_rate, 4),
                "profit_factor": round(metrics.profit_factor, 4),
                "annual_return": round(metrics.annual_return, 4),
                "volatility": round(metrics.volatility, 4),
                "calmar_ratio": round(metrics.calmar_ratio, 4),
                "sortino_ratio": round(metrics.sortino_ratio, 4),
                "total_trades": metrics.total_trades,
                "avg_holding_days": round(metrics.avg_holding_days, 2),
            },
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "information_ratio": round(self._calc_information_ratio(returns, benchmark), 4),
            "grade": self._assign_grade(metrics),
            "evaluated_at": datetime.now().isoformat(),
        }

        self.evaluation_history.append(result)
        return result

    def _calculate_metrics(self, returns: List[float], trades: List[Dict]) -> EvaluationMetrics:
        """计算核心评估指标"""
        import math

        metrics = EvaluationMetrics()
        if not returns:
            return metrics

        n = len(returns)
        mean_return = sum(returns) / n
        std_return = math.sqrt(sum((r - mean_return) ** 2 for r in returns) / max(n - 1, 1))

        metrics.annual_return = mean_return * 252 if mean_return else 0
        metrics.volatility = std_return * math.sqrt(252) if std_return else 0

        # 夏普比率
        if metrics.volatility > 0:
            metrics.sharpe_ratio = (metrics.annual_return - self.risk_free_rate) / metrics.volatility

        # 索提诺比率（下行波动）
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_std = math.sqrt(sum(r**2 for r in downside_returns) / len(downside_returns))
            if downside_std > 0:
                metrics.sortino_ratio = (metrics.annual_return - self.risk_free_rate) / (downside_std * math.sqrt(252))

        # 最大回撤
        cumulative = [1.0]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r))
        peak = cumulative[0]
        max_dd = 0.0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        metrics.max_drawdown = max_dd

        # 卡尔玛比率
        if max_dd > 0:
            metrics.calmar_ratio = metrics.annual_return / max_dd

        # 交易统计
        if trades:
            winning_trades = [t for t in trades if t.get("profit", 0) > 0]
            losing_trades = [t for t in trades if t.get("profit", 0) <= 0]
            metrics.total_trades = len(trades)
            metrics.win_rate = len(winning_trades) / len(trades) if trades else 0

            total_profit = sum(t.get("profit", 0) for t in winning_trades)
            total_loss = abs(sum(t.get("profit", 0) for t in losing_trades))
            metrics.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        return metrics

    def _calculate_alpha_beta(self, returns: List[float], benchmark: Optional[List[float]]) -> Tuple[float, float]:
        """计算Alpha和Beta"""
        if not benchmark or len(returns) != len(benchmark):
            return 0.0, 1.0

        n = len(returns)
        mean_r = sum(returns) / n
        mean_b = sum(benchmark) / n

        cov = sum((returns[i] - mean_r) * (benchmark[i] - mean_b) for i in range(n)) / (n - 1)
        var_b = sum((b - mean_b) ** 2 for b in benchmark) / (n - 1)

        beta = cov / var_b if var_b > 0 else 1.0
        alpha = mean_r - self.risk_free_rate / 252 - beta * (mean_b - self.risk_free_rate / 252)

        return alpha * 252, beta

    def _calc_information_ratio(self, returns: List[float], benchmark: Optional[List[float]]) -> float:
        """计算信息比率"""
        if not benchmark or len(returns) != len(benchmark):
            return 0.0
        diffs = [returns[i] - benchmark[i] for i in range(len(returns))]
        mean_diff = sum(diffs) / len(diffs)
        import math
        std_diff = math.sqrt(sum((d - mean_diff) ** 2 for d in diffs) / max(len(diffs) - 1, 1))
        return mean_diff / std_diff if std_diff > 0 else 0.0

    def _assign_grade(self, metrics: EvaluationMetrics) -> str:
        """综合评分"""
        score = 0
        if metrics.sharpe_ratio > 2.0:
            score += 3
        elif metrics.sharpe_ratio > 1.0:
            score += 2
        elif metrics.sharpe_ratio > 0.5:
            score += 1

        if metrics.win_rate > 0.6:
            score += 2
        elif metrics.win_rate > 0.5:
            score += 1

        if metrics.profit_factor > 2.0:
            score += 3
        elif metrics.profit_factor > 1.5:
            score += 2
        elif metrics.profit_factor > 1.0:
            score += 1

        if metrics.max_drawdown < 0.1:
            score += 2
        elif metrics.max_drawdown < 0.2:
            score += 1

        if score >= 8:
            return "A+"
        elif score >= 6:
            return "A"
        elif score >= 4:
            return "B"
        elif score >= 2:
            return "C"
        else:
            return "D"

    def compare_strategies(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """比较多个策略"""
        if not results:
            return {"error": "未提供策略结果"}

        best_sharpe = max(results, key=lambda r: r.get("metrics", {}).get("sharpe_ratio", 0))
        best_winrate = max(results, key=lambda r: r.get("metrics", {}).get("win_rate", 0))
        best_drawdown = min(results, key=lambda r: r.get("metrics", {}).get("max_drawdown", 1))

        return {
            "compared_count": len(results),
            "best_sharpe": {"name": best_sharpe.get("name", "unknown"), "sharpe": best_sharpe["metrics"]["sharpe_ratio"]},
            "best_win_rate": {"name": best_winrate.get("name", "unknown"), "win_rate": best_winrate["metrics"]["win_rate"]},
            "best_drawdown": {"name": best_drawdown.get("name", "unknown"), "max_drawdown": best_drawdown["metrics"]["max_drawdown"]},
            "compared_at": datetime.now().isoformat(),
        }


__all__ = ["EnhancedEvaluator", "EvaluationMetrics"]