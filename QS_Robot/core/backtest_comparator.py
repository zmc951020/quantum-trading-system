#!/usr/bin/env python3
"""
回测报告多策略对比与归因分析
=============================
支持：
- 多策略同标的横向对比
- 绩效归因分析（收益拆解）
- 相关性矩阵
- 综合排名
- 最优策略推荐
"""
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    """回测指标"""
    strategy_name: str
    symbol: str = ""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    calmar: float = 0.0
    sortino: float = 0.0
    volatility: float = 0.0  # 年化波动率

    # 归因
    alpha: float = 0.0  # 超额收益
    beta: float = 0.0   # 市场敏感度
    info_ratio: float = 0.0

    # 元数据
    backtest_date: str = field(default_factory=lambda: datetime.now().isoformat())
    params: Dict = field(default_factory=dict)
    version: str = ""


@dataclass
class ComparisonReport:
    """对比报告"""
    strategies: List[BacktestMetrics] = field(default_factory=list)
    comparison_date: str = field(default_factory=lambda: datetime.now().isoformat())

    # 相关性矩阵
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # 排名
    rankings: Dict[str, Dict] = field(default_factory=dict)

    # 推荐
    best_strategy: str = ""
    best_score: float = 0.0
    recommendation: str = ""


class BacktestComparator:
    """多策略回测对比器"""

    def __init__(self):
        self._metrics: List[BacktestMetrics] = []

    def add_strategy(self, metrics: BacktestMetrics):
        self._metrics.append(metrics)

    def add_from_dict(self, strategy_name: str, result: Dict):
        """从回测结果字典添加"""
        metrics = BacktestMetrics(
            strategy_name=strategy_name,
            symbol=result.get("symbol", ""),
            total_return=result.get("total_return", 0),
            annual_return=result.get("annual_return", 0),
            sharpe=result.get("sharpe", 0),
            max_drawdown=result.get("max_drawdown", 0),
            win_rate=result.get("win_rate", 0),
            profit_factor=result.get("profit_factor", 0),
            total_trades=result.get("total_trades", 0),
            avg_win=result.get("avg_win", 0),
            avg_loss=result.get("avg_loss", 0),
            calmar=result.get("calmar", 0),
            sortino=result.get("sortino", 0),
            volatility=result.get("volatility", 0),
            params=result.get("params", {}),
            version=result.get("version", ""),
        )
        self._metrics.append(metrics)

    def compare(self) -> ComparisonReport:
        """执行全面对比分析"""
        if not self._metrics:
            return ComparisonReport(
                strategies=[],
                recommendation="无策略数据",
            )

        report = ComparisonReport(strategies=self._metrics)

        # 排名
        report.rankings = self._compute_rankings()

        # 相关性矩阵（基于指标向量）
        report.correlation_matrix = self._compute_correlation()

        # 最佳策略
        report.best_strategy, report.best_score = self._find_best()

        # 推荐
        report.recommendation = self._generate_recommendation(report)

        return report

    def _compute_rankings(self) -> Dict[str, Dict]:
        """多维度排名"""
        rankings = {}

        for metric_name in ["total_return", "sharpe", "max_drawdown", "win_rate",
                            "profit_factor", "calmar", "sortino"]:
            values = [(m.strategy_name, getattr(m, metric_name, 0)) for m in self._metrics]

            # max_drawdown 越小越好，其他越大越好
            reverse = metric_name == "max_drawdown"
            sorted_vals = sorted(values, key=lambda x: x[1], reverse=not reverse)

            rankings[metric_name] = {
                name: rank + 1 for rank, (name, _) in enumerate(sorted_vals)
            }

        # 综合排名
        composite = {}
        for m in self._metrics:
            total_rank = sum(
                rankings[metric].get(m.strategy_name, len(self._metrics))
                for metric in rankings
            )
            composite[m.strategy_name] = round(total_rank / len(rankings), 2)

        rankings["composite"] = composite

        return rankings

    def _compute_correlation(self) -> Dict[str, Dict[str, float]]:
        """计算策略间指标相关性（基于指标向量而非收益序列）"""
        if len(self._metrics) < 2:
            return {}

        feature_names = ["total_return", "sharpe", "max_drawdown", "win_rate",
                         "profit_factor", "calmar", "volatility"]

        # 构建策略-特征矩阵
        n = len(self._metrics)
        feature_matrix = np.zeros((n, len(feature_names)))

        for i, m in enumerate(self._metrics):
            for j, fn in enumerate(feature_names):
                feature_matrix[i, j] = getattr(m, fn, 0)

        # 归一化
        means = feature_matrix.mean(axis=0)
        stds = feature_matrix.std(axis=0)
        stds[stds == 0] = 1
        normalized = (feature_matrix - means) / stds

        corr = {}
        for i, m1 in enumerate(self._metrics):
            corr[m1.strategy_name] = {}
            for j, m2 in enumerate(self._metrics):
                if i == j:
                    corr[m1.strategy_name][m2.strategy_name] = 1.0
                else:
                    # 余弦相似度
                    dot = np.dot(normalized[i], normalized[j])
                    norm_i = np.linalg.norm(normalized[i])
                    norm_j = np.linalg.norm(normalized[j])
                    sim = dot / (norm_i * norm_j) if norm_i > 0 and norm_j > 0 else 0
                    corr[m1.strategy_name][m2.strategy_name] = round(float(sim), 4)

        return corr

    def _find_best(self) -> Tuple[str, float]:
        """综合评分找最佳策略"""
        if not self._metrics:
            return "", 0.0

        best = self._metrics[0]
        best_score = 0.0

        for m in self._metrics:
            # 综合评分 = 收益(25%) + 夏普(25%) + 低回撤(20%) + 胜率(15%) + 卡玛(15%)
            score = (
                self._normalize_score(m.total_return, "total_return") * 0.25 +
                self._normalize_score(m.sharpe, "sharpe") * 0.25 +
                (1 - self._normalize_score(m.max_drawdown, "max_drawdown")) * 0.20 +
                self._normalize_score(m.win_rate, "win_rate") * 0.15 +
                self._normalize_score(m.calmar, "calmar") * 0.15
            )

            if score > best_score:
                best_score = score
                best = m

        return best.strategy_name, round(best_score * 100, 2)

    def _normalize_score(self, value: float, metric: str) -> float:
        """归一化到 [0, 1]"""
        all_vals = [getattr(m, metric, 0) for m in self._metrics]
        min_val = min(all_vals)
        max_val = max(all_vals)

        if max_val == min_val:
            return 0.5  # 所有相同

        return (value - min_val) / (max_val - min_val)

    def _generate_recommendation(self, report: ComparisonReport) -> str:
        """生成推荐建议"""
        if not report.strategies:
            return "无策略数据"

        best = report.best_strategy
        best_m = next((m for m in report.strategies if m.strategy_name == best), None)

        if not best_m:
            return "无法确定最佳策略"

        parts = [f"推荐策略: **{best}** (综合评分: {report.best_score}/100)"]

        if best_m.sharpe > 2.0:
            parts.append("夏普比率优秀(>2.0)，风险调整后收益出色")
        elif best_m.sharpe > 1.0:
            parts.append("夏普比率良好(>1.0)，风险收益比合理")
        else:
            parts.append("夏普比率偏低(<1.0)，建议优化风险控制")

        if best_m.max_drawdown < 0.1:
            parts.append("最大回撤控制优秀(<10%)")
        elif best_m.max_drawdown < 0.2:
            parts.append("最大回撤在可接受范围(<20%)")
        else:
            parts.append("最大回撤偏高(>20%)，需关注风险")

        if best_m.win_rate > 0.6:
            parts.append("胜率较高(>60%)，策略信号质量好")

        # 相关策略提示
        if best in report.correlation_matrix:
            similar = []
            for name, corr in report.correlation_matrix[best].items():
                if name != best and corr > 0.8:
                    similar.append(name)
            if similar:
                parts.append(f"与 {', '.join(similar)} 高度相关，可考虑合并或去重")

        return "\n".join(f"- {p}" for p in parts)

    def generate_report(self, report: ComparisonReport) -> str:
        """生成Markdown格式报告"""
        lines = [
            "# 多策略回测对比报告",
            f"生成时间: {report.comparison_date}",
            f"策略数量: {len(report.strategies)}",
            "",
            "## 综合排名",
            "| 排名 | 策略 | 收益 | 夏普 | 最大回撤 | 胜率 | 卡玛 | 综合分 |",
            "|------|------|------|------|----------|------|------|--------|",
        ]

        # 按综合排名排序
        composite = report.rankings.get("composite", {})
        sorted_strategies = sorted(
            report.strategies,
            key=lambda m: composite.get(m.strategy_name, 999),
        )

        for i, m in enumerate(sorted_strategies, 1):
            comp = composite.get(m.strategy_name, "-")
            lines.append(
                f"| {i} | {m.strategy_name} | {m.total_return:.2%} | {m.sharpe:.2f} | "
                f"{m.max_drawdown:.2%} | {m.win_rate:.1%} | {m.calmar:.2f} | {comp} |"
            )

        lines.append("")
        lines.append("## 推荐")
        lines.append(report.recommendation)

        if report.correlation_matrix:
            lines.append("")
            lines.append("## 策略相关性矩阵")
            names = list(report.correlation_matrix.keys())
            header = "| | " + " | ".join(names) + " |"
            lines.append(header)
            lines.append("|" + "|".join(["-" * 8] * (len(names) + 1)) + "|")
            for n1 in names:
                row = f"| {n1} | " + " | ".join(
                    f"{report.correlation_matrix[n1].get(n2, 0):.2f}" for n2 in names
                ) + " |"
                lines.append(row)

        return "\n".join(lines)


# 便捷函数
def compare_backtests(results: Dict[str, Dict]) -> ComparisonReport:
    """快速对比多个策略的回测结果

    Args:
        results: {strategy_name: {total_return, sharpe, max_drawdown, ...}}
    """
    comparator = BacktestComparator()
    for name, result in results.items():
        comparator.add_from_dict(name, result)
    return comparator.compare()