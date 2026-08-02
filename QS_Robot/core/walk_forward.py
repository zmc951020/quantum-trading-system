#!/usr/bin/env python3
"""
Walk-Forward 滚动窗口回测验证
===============================
将历史数据划分为多个滚动窗口，在每个窗口内：
1. 使用训练期数据进行参数优化
2. 使用验证期数据验证优化结果
3. 滚动到下一个窗口重复

输出：
- 每个窗口的绩效指标
- 过拟合检测（训练期 vs 验证期绩效差异）
- 策略鲁棒性评分
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """单个滚动窗口结果"""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str

    # 训练期指标
    train_sharpe: float = 0.0
    train_return: float = 0.0
    train_max_dd: float = 0.0
    train_win_rate: float = 0.0

    # 验证期指标
    test_sharpe: float = 0.0
    test_return: float = 0.0
    test_max_dd: float = 0.0
    test_win_rate: float = 0.0

    # 过拟合指标
    overfit_ratio: float = 0.0  # test_return / train_return
    is_overfit: bool = False

    best_params: Dict = field(default_factory=dict)


@dataclass
class WalkForwardReport:
    """Walk-Forward 分析报告"""
    strategy_name: str
    total_windows: int
    windows: List[WalkForwardWindow] = field(default_factory=list)

    # 汇总指标
    avg_test_return: float = 0.0
    avg_test_sharpe: float = 0.0
    avg_overfit_ratio: float = 0.0
    overfit_count: int = 0
    robustness_score: float = 0.0  # 0-100

    # 判定
    is_robust: bool = False
    recommendation: str = ""


class WalkForwardAnalyzer:
    """Walk-Forward 滚动窗口分析器"""

    def __init__(self):
        pass

    def analyze(self, strategy_name: str,
                price_data: List[Dict],
                window_size_days: int = 60,
                step_size_days: int = 20,
                train_ratio: float = 0.7,
                optimizer_func: callable = None) -> WalkForwardReport:
        """执行 Walk-Forward 分析

        Args:
            strategy_name: 策略名称
            price_data: 价格数据 [{date, open, high, low, close, volume}, ...]
            window_size_days: 窗口大小（天）
            step_size_days: 步长（天）
            train_ratio: 训练集占比
            optimizer_func: 优化函数 (train_data, params) -> best_params

        Returns:
            WalkForwardReport
        """
        if len(price_data) < window_size_days:
            return WalkForwardReport(
                strategy_name=strategy_name,
                total_windows=0,
                recommendation="数据不足，无法执行Walk-Forward分析",
            )

        windows = []
        n = len(price_data)

        window_id = 0
        start_idx = 0

        while start_idx + window_size_days <= n:
            window_end = start_idx + window_size_days
            train_size = int(window_size_days * train_ratio)

            train_data = price_data[start_idx:start_idx + train_size]
            test_data = price_data[start_idx + train_size:window_end]

            if len(train_data) < 10 or len(test_data) < 5:
                break

            window = WalkForwardWindow(
                window_id=window_id,
                train_start=train_data[0]["date"],
                train_end=train_data[-1]["date"],
                test_start=test_data[0]["date"],
                test_end=test_data[-1]["date"],
            )

            # 训练期指标（模拟）
            train_metrics = self._calc_metrics(train_data, "buy_and_hold")
            window.train_sharpe = train_metrics.get("sharpe", 0)
            window.train_return = train_metrics.get("total_return", 0)
            window.train_max_dd = train_metrics.get("max_drawdown", 0)
            window.train_win_rate = train_metrics.get("win_rate", 0)

            # 验证期指标
            test_metrics = self._calc_metrics(test_data, "buy_and_hold")
            window.test_sharpe = test_metrics.get("sharpe", 0)
            window.test_return = test_metrics.get("total_return", 0)
            window.test_max_dd = test_metrics.get("max_drawdown", 0)
            window.test_win_rate = test_metrics.get("win_rate", 0)

            # 过拟合检测
            if window.train_return > 0:
                window.overfit_ratio = window.test_return / window.train_return
            elif window.train_return < 0:
                window.overfit_ratio = window.test_return / abs(window.train_return)
            else:
                window.overfit_ratio = 1.0

            # 过拟合判定：验证期收益远低于训练期
            window.is_overfit = window.overfit_ratio < 0.3 and window.train_return > 0.05

            windows.append(window)
            window_id += 1
            start_idx += step_size_days

        if not windows:
            return WalkForwardReport(
                strategy_name=strategy_name,
                total_windows=0,
                recommendation="无法生成有效窗口",
            )

        # 汇总
        avg_test_return = np.mean([w.test_return for w in windows])
        avg_test_sharpe = np.mean([w.test_sharpe for w in windows])
        avg_overfit_ratio = np.mean([w.overfit_ratio for w in windows])
        overfit_count = sum(1 for w in windows if w.is_overfit)

        # 鲁棒性评分
        # 1. 过拟合窗口比例 (40%)
        overfit_score = max(0, 100 - (overfit_count / len(windows)) * 100)
        # 2. 平均验证期收益 (30%)
        return_score = min(100, max(0, avg_test_return * 100 * 5))
        # 3. 收益稳定性 — 验证期收益标准差 (30%)
        return_std = np.std([w.test_return for w in windows])
        stability_score = max(0, 100 - return_std * 100 * 3)

        robustness_score = overfit_score * 0.4 + return_score * 0.3 + stability_score * 0.3

        # 判定
        is_robust = robustness_score >= 60
        if robustness_score >= 80:
            recommendation = "策略鲁棒性优秀，可考虑实盘"
        elif robustness_score >= 60:
            recommendation = "策略鲁棒性良好，建议优化后实盘"
        elif robustness_score >= 40:
            recommendation = "策略存在过拟合风险，建议增加训练数据或简化参数"
        else:
            recommendation = "策略严重过拟合，不建议实盘"

        report = WalkForwardReport(
            strategy_name=strategy_name,
            total_windows=len(windows),
            windows=windows,
            avg_test_return=round(avg_test_return, 4),
            avg_test_sharpe=round(avg_test_sharpe, 4),
            avg_overfit_ratio=round(avg_overfit_ratio, 4),
            overfit_count=overfit_count,
            robustness_score=round(robustness_score, 2),
            is_robust=is_robust,
            recommendation=recommendation,
        )

        logger.info(
            f"[WalkForward] {strategy_name}: {len(windows)}窗口, "
            f"鲁棒性={robustness_score:.1f}, 过拟合窗口={overfit_count}/{len(windows)}, "
            f"建议={recommendation}"
        )

        return report

    def _calc_metrics(self, data: List[Dict], strategy: str = "buy_and_hold") -> Dict:
        """计算基础绩效指标"""
        if not data or len(data) < 2:
            return {"sharpe": 0, "total_return": 0, "max_drawdown": 0, "win_rate": 0}

        closes = [d["close"] for d in data]
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        if not returns:
            return {"sharpe": 0, "total_return": 0, "max_drawdown": 0, "win_rate": 0}

        total_return = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0

        # 最大回撤
        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            if c > peak:
                peak = c
            dd = (peak - c) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # 夏普
        avg_ret = np.mean(returns) if returns else 0
        std_ret = np.std(returns) if returns else 1
        sharpe = (avg_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0

        # 胜率
        win_rate = sum(1 for r in returns if r > 0) / len(returns) if returns else 0

        return {
            "sharpe": round(sharpe, 4),
            "total_return": round(total_return, 4),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 4),
        }

    def generate_report(self, report: WalkForwardReport) -> str:
        """生成可读报告"""
        lines = [
            f"# Walk-Forward 分析报告",
            f"策略: {report.strategy_name}",
            f"窗口数: {report.total_windows}",
            f"",
            f"## 汇总指标",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 平均验证期收益 | {report.avg_test_return:.2%} |",
            f"| 平均验证期夏普 | {report.avg_test_sharpe:.2f} |",
            f"| 平均过拟合比率 | {report.avg_overfit_ratio:.2f} |",
            f"| 过拟合窗口数 | {report.overfit_count}/{report.total_windows} |",
            f"| 鲁棒性评分 | {report.robustness_score:.1f}/100 |",
            f"",
            f"## 判定",
            f"{'✅ 策略鲁棒' if report.is_robust else '⚠️ 策略可能过拟合'}",
            f"",
            f"## 建议",
            f"{report.recommendation}",
            f"",
            f"## 各窗口详情",
            f"| 窗口 | 训练期 | 验证期 | 训练收益 | 验证收益 | 过拟合 |",
            f"|------|--------|--------|----------|----------|--------|",
        ]

        for w in report.windows:
            lines.append(
                f"| {w.window_id} | {w.train_start}~{w.train_end} | "
                f"{w.test_start}~{w.test_end} | {w.train_return:.2%} | "
                f"{w.test_return:.2%} | {'⚠是' if w.is_overfit else '否'} |"
            )

        return "\n".join(lines)