#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 回测引擎
=============================
严格时序回测 + 金融级指标

Phase 1: 步进式模拟 + 指标计算（当前）
Phase 2: VectorBT 集成回测（后续）
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

from strategies.smart_rotate_ppo.config import ETF_CODES, StrategyConfig
from strategies.smart_rotate_ppo.env.trading_env import SmartRotateTradingEnv
from strategies.smart_rotate_ppo.risk_guard import RiskGuard

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str = "smart_rotate_ppo"
    start_date: str = ""
    end_date: str = ""
    initial_balance: float = 1_000_000.0
    final_balance: float = 1_000_000.0
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    avg_turnover: float = 0.0
    kill_switch_events: int = 0
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    weight_history: List[List[float]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    pass_reason: str = ""


class BacktestEngine:
    """
    回测引擎：步进式模拟 + 指标计算

    用法:
        engine = BacktestEngine(cfg)
        result = engine.run(model, env, test_df)
        engine.save_report(result, "reports/backtest_20260528.json")
    """

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.risk_guard = RiskGuard(cfg)

    def run(
        self,
        model: PPO,
        env: SmartRotateTradingEnv,
        df: pd.DataFrame,
    ) -> BacktestResult:
        """
        执行回测

        Args:
            model: 训练好的 PPO 模型
            env: 交易环境
            df: 回测数据

        Returns:
            BacktestResult 完整回测结果
        """
        logger.info(f"开始回测: {len(df)} 行数据")

        # 重置环境
        obs, _ = env.reset()

        balances: List[float] = [env.initial_balance]
        daily_returns: List[float] = []
        weights_history: List[np.ndarray] = []
        trades: List[Dict[str, Any]] = []
        prev_weights = np.zeros(self.cfg.N)
        kill_switch_count = 0

        done = False
        step = 0

        while not done:
            # 模型预测
            action, _ = model.predict(obs, deterministic=True)

            # 执行
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated

            # 记录
            balances.append(info["balance"])
            if "portfolio_return" in info:
                daily_returns.append(info["portfolio_return"])
            weights = np.array(info.get("weights", []))
            weights_history.append(weights)

            # 交易记录
            turnover = np.sum(np.abs(weights - prev_weights)) / 2
            if turnover > 0.001:
                trades.append({
                    "step": step,
                    "turnover": turnover,
                    "weights": weights.tolist() if len(weights) > 0 else [],
                    "balance": info["balance"],
                })

            if info.get("kill_switch"):
                kill_switch_count += 1

            prev_weights = weights.copy()
            step += 1

            if step >= len(df) - 1:
                done = True

        # 计算指标
        result = self._compute_metrics(
            balances, daily_returns, weights_history,
            trades, kill_switch_count, df,
        )

        logger.info(
            f"回测完成: 收益率={result.total_return:.2%}, "
            f"夏普={result.sharpe_ratio:.2f}, "
            f"最大回撤={result.max_drawdown:.2%}"
        )
        return result

    # ========================================================================
    # 指标计算
    # ========================================================================
    def _compute_metrics(
        self,
        balances: List[float],
        daily_returns: List[float],
        weight_history: List[np.ndarray],
        trades: List[Dict[str, Any]],
        kill_switch_count: int,
        df: pd.DataFrame,
    ) -> BacktestResult:
        """计算金融级回测指标"""
        result = BacktestResult()
        result.strategy_name = "smart_rotate_ppo"
        result.initial_balance = self.cfg.initial_balance

        if "date" in df.columns:
            result.start_date = str(df["date"].iloc[0]) if len(df) > 0 else ""
            result.end_date = str(df["date"].iloc[-1]) if len(df) > 0 else ""

        if len(balances) == 0:
            result.pass_reason = "无回测数据"
            return result

        result.final_balance = balances[-1]

        # 总收益率
        result.total_return = (result.final_balance / result.initial_balance - 1.0)

        # 年化收益率
        years = len(daily_returns) / 252
        if years > 0:
            result.annual_return = (result.final_balance / result.initial_balance) ** (1 / years) - 1

        # 每日收益率序列
        returns = np.array(daily_returns)
        result.daily_returns = returns.tolist()
        result.equity_curve = balances

        if len(returns) >= 2:
            daily_rf = self.cfg.risk_free_rate / 252

            # 夏普比率
            excess = returns - daily_rf
            mean_excess = np.mean(excess)
            std_excess = np.std(excess) + 1e-10
            result.sharpe_ratio = float(mean_excess / std_excess * np.sqrt(252))

            # 索提诺比率（仅下行波动）
            downside = returns[returns < 0]
            if len(downside) >= 2:
                downside_std = np.std(downside) + 1e-10
                result.sortino_ratio = float(mean_excess / downside_std * np.sqrt(252))
            else:
                result.sortino_ratio = result.sharpe_ratio

            # 最大回撤
            peak = np.maximum.accumulate(np.array(balances))
            drawdowns = (peak - np.array(balances)) / peak
            result.max_drawdown = float(np.max(drawdowns))

            # 最大回撤持续时间
            in_dd = False
            dd_start = 0
            max_dd_duration = 0
            for i, dd in enumerate(drawdowns):
                if dd > 0.01 and not in_dd:
                    in_dd = True
                    dd_start = i
                elif dd < 0.01 and in_dd:
                    in_dd = False
                    max_dd_duration = max(max_dd_duration, i - dd_start)
            result.max_drawdown_duration = max_dd_duration

            # 卡尔马比率
            if result.max_drawdown > 1e-6:
                result.calmar_ratio = float(result.annual_return / result.max_drawdown)
            else:
                result.calmar_ratio = result.sharpe_ratio

            # 胜率
            wins = returns[returns > 0]
            result.total_trades = len(returns)
            result.win_rate = float(len(wins) / max(len(returns), 1))

            # 盈亏比
            avg_win = np.mean(wins) if len(wins) > 0 else 0
            losses = returns[returns < 0]
            avg_loss = np.abs(np.mean(losses)) if len(losses) > 0 else 1e-10
            result.profit_loss_ratio = float(avg_win / max(avg_loss, 1e-10))

        # 平均换手率
        turnovers = [t["turnover"] for t in trades if "turnover" in t]
        result.avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0

        # Kill Switch 事件
        result.kill_switch_events = kill_switch_count

        # 权重历史
        result.weight_history = [w.tolist() if isinstance(w, np.ndarray) else w for w in weight_history]
        result.trades = trades[-50:]  # 最近 50 笔交易

        # 过不过线判断
        result.passed = (
            result.sharpe_ratio >= self.cfg.backtest_min_sharpe
            and result.max_drawdown <= self.cfg.backtest_max_drawdown
            and result.annual_return > 0
        )
        if result.passed:
            result.pass_reason = (
                f"夏普 {result.sharpe_ratio:.2f} >= {self.cfg.backtest_min_sharpe}, "
                f"回撤 {result.max_drawdown:.2%} <= {self.cfg.backtest_max_drawdown:.2%}"
            )
        else:
            reasons = []
            if result.sharpe_ratio < self.cfg.backtest_min_sharpe:
                reasons.append(f"夏普 {result.sharpe_ratio:.2f} < {self.cfg.backtest_min_sharpe}")
            if result.max_drawdown > self.cfg.backtest_max_drawdown:
                reasons.append(f"回撤 {result.max_drawdown:.2%} > {self.cfg.backtest_max_drawdown:.2%}")
            result.pass_reason = "; ".join(reasons) or "未达标"

        # 摘要
        result.summary = {
            "total_return": f"{result.total_return:.2%}",
            "annual_return": f"{result.annual_return:.2%}",
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "sortino_ratio": round(result.sortino_ratio, 2),
            "calmar_ratio": round(result.calmar_ratio, 2),
            "max_drawdown": f"{result.max_drawdown:.2%}",
            "max_drawdown_duration": result.max_drawdown_duration,
            "win_rate": f"{result.win_rate:.2%}",
            "profit_loss_ratio": round(result.profit_loss_ratio, 2),
            "total_trades": result.total_trades,
            "avg_turnover": f"{result.avg_turnover:.4f}",
            "kill_switch_events": result.kill_switch_events,
            "passed": result.passed,
        }

        return result

    # ========================================================================
    # 报告输出
    # ========================================================================
    def save_report(
        self,
        result: BacktestResult,
        output_path: Optional[str] = None,
    ) -> str:
        """保存回测报告为 JSON"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"strategies/smart_rotate_ppo/reports/backtest_{timestamp}.json"

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        report: Dict[str, Any] = {
            "strategy": result.strategy_name,
            "timestamp": datetime.now().isoformat(),
            "config": self.cfg.to_dict(),
            "result": {
                "start_date": result.start_date,
                "end_date": result.end_date,
                "initial_balance": result.initial_balance,
                "final_balance": round(result.final_balance, 2),
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "calmar_ratio": result.calmar_ratio,
                "max_drawdown": result.max_drawdown,
                "max_drawdown_duration": result.max_drawdown_duration,
                "win_rate": result.win_rate,
                "profit_loss_ratio": result.profit_loss_ratio,
                "total_trades": result.total_trades,
                "avg_turnover": result.avg_turnover,
                "kill_switch_events": result.kill_switch_events,
                "passed": result.passed,
                "pass_reason": result.pass_reason,
            },
            "equity_curve": result.equity_curve[-100:] if len(result.equity_curve) > 100 else result.equity_curve,
            "trades_summary": result.summary,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"回测报告已保存: {output_path}")
        return output_path

    def print_summary(self, result: BacktestResult) -> None:
        """打印回测摘要"""
        print("\n" + "=" * 60)
        print(f"  📊 智能标的轮动策略 — 回测报告")
        print("=" * 60)
        print(f"  策略:         {result.strategy_name}")
        print(f"  区间:         {result.start_date} → {result.end_date}")
        print(f"  初始资金:     {result.initial_balance:,.0f}")
        print(f"  最终资金:     {result.final_balance:,.0f}")
        print(f"  总收益率:     {result.total_return:+.2%}")
        print(f"  年化收益率:   {result.annual_return:+.2%}")
        print(f"  夏普比率:     {result.sharpe_ratio:.2f}")
        print(f"  索提诺比率:   {result.sortino_ratio:.2f}")
        print(f"  卡尔马比率:   {result.calmar_ratio:.2f}")
        print(f"  最大回撤:     {result.max_drawdown:.2%} (持续{result.max_drawdown_duration}天)")
        print(f"  胜率:         {result.win_rate:.2%}")
        print(f"  盈亏比:       {result.profit_loss_ratio:.2f}")
        print(f"  交易次数:     {result.total_trades}")
        print(f"  平均换手率:   {result.avg_turnover:.4f}")
        print(f"  Kill Switch:  {result.kill_switch_events} 次")
        print(f"  {'✅ 达标' if result.passed else '❌ 未达标'}: {result.pass_reason}")
        print("=" * 60 + "\n")


__all__ = ["BacktestEngine", "BacktestResult"]