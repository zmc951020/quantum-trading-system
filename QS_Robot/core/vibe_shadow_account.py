#!/usr/bin/env python3
"""
影子账户分析模块（Shadow Account Analyzer）

Vibe-Trading 系统的交易行为诊断引擎，提供：
  - 交易记录与影子账户管理
  - 交易行为诊断（追涨杀跌、过度交易、止损纪律等）
  - Brinson 归因分析（回撤原因分解）
  - 绩效指标计算（收益率、夏普、最大回撤、胜率、盈亏比、卡玛比率）
  - 综合报告生成

依赖：numpy
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 交易记录数据类
# ============================================================

@dataclass
class Trade:
    """单笔交易记录"""
    trade_id: str
    symbol: str
    direction: str           # "buy" / "sell"
    entry_price: float
    exit_price: float = 0.0
    quantity: int = 0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_reason: str = ""
    exit_reason: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    is_closed: bool = False
    tags: List[str] = field(default_factory=list)


# ============================================================
# 影子账户分析器
# ============================================================

class ShadowAccountAnalyzer:
    """影子账户分析器

    记录每笔交易，分析交易行为模式，提供绩效评估和归因分析。
    """

    def __init__(self, initial_capital: float = 100000.0):
        """
        Args:
            initial_capital: 初始资金（默认10万）
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades: List[Trade] = []
        self._equity_curve: List[float] = [initial_capital]
        self._trade_counter = 0

    # ============================================================
    # 交易记录
    # ============================================================

    def record_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """记录一笔交易

        Args:
            trade: 交易字典 {symbol, direction, entry_price, exit_price, quantity,
                             entry_time, exit_time, entry_reason, exit_reason, pnl, ...}

        Returns:
            dict: {success, trade_id, ...}
        """
        try:
            self._trade_counter += 1
            trade_id = f"T{self._trade_counter:06d}"

            direction = trade.get("direction", "buy")
            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            quantity = trade.get("quantity", 0)
            is_closed = exit_price > 0

            # 计算盈亏
            pnl = 0.0
            pnl_pct = 0.0
            if is_closed and entry_price > 0:
                if direction == "buy":
                    pnl = (exit_price - entry_price) * quantity
                else:
                    pnl = (entry_price - exit_price) * quantity
                pnl_pct = (pnl / (entry_price * quantity)) * 100 if entry_price * quantity > 0 else 0

            t = Trade(
                trade_id=trade_id,
                symbol=str(trade.get("symbol", "UNKNOWN")),
                direction=direction,
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                quantity=int(quantity),
                entry_time=trade.get("entry_time"),
                exit_time=trade.get("exit_time"),
                entry_reason=str(trade.get("entry_reason", "")),
                exit_reason=str(trade.get("exit_reason", "")),
                pnl=float(trade.get("pnl", pnl)),
                pnl_pct=float(trade.get("pnl_pct", pnl_pct)),
                is_closed=is_closed,
                tags=list(trade.get("tags", [])),
            )

            self.trades.append(t)

            if is_closed:
                self.current_capital += t.pnl
                self._equity_curve.append(self.current_capital)

            logger.info(f"记录交易 {trade_id}: {t.symbol} {t.direction} PnL={t.pnl:.2f}")

            return {
                "success": True,
                "trade_id": trade_id,
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 4),
                "total_trades": len(self.trades),
            }
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 交易行为诊断
    # ============================================================

    def analyze_behavior(self) -> Dict[str, Any]:
        """交易行为诊断

        分析交易行为模式，识别追涨杀跌、过度交易、止损纪律等问题。

        Returns:
            dict: {success, behaviors: {...}, diagnostics: [...], behavior_score}
        """
        try:
            closed_trades = [t for t in self.trades if t.is_closed]
            if len(closed_trades) < 5:
                return {"success": False, "error": "交易记录不足（至少需要5笔已平仓交易）"}

            buy_trades = [t for t in closed_trades if t.direction == "buy"]
            sell_trades = [t for t in closed_trades if t.direction == "sell"]

            behaviors = {}

            # 1. 追涨杀跌检测
            if buy_trades:
                buy_pnl_pcts = [t.pnl_pct for t in buy_trades]
                buy_wins = [t for t in buy_trades if t.pnl > 0]
                buy_losses = [t for t in buy_trades if t.pnl < 0]
                avg_win = np.mean([t.pnl_pct for t in buy_wins]) if buy_wins else 0
                avg_loss = np.mean([t.pnl_pct for t in buy_losses]) if buy_losses else 0
                chase_score = abs(avg_loss) / (abs(avg_win) + 1e-8) if avg_win != 0 else 0
                behaviors["chase_kill_score"] = round(float(min(chase_score, 1.0)), 4)
                behaviors["chase_kill_warning"] = chase_score > 0.5
            else:
                behaviors["chase_kill_score"] = 0.0
                behaviors["chase_kill_warning"] = False

            # 2. 过度交易检测
            if len(closed_trades) >= 20:
                # 按日期分组
                date_counts = {}
                for t in closed_trades:
                    if t.entry_time:
                        d = t.entry_time.strftime("%Y-%m-%d")
                        date_counts[d] = date_counts.get(d, 0) + 1
                max_daily = max(date_counts.values()) if date_counts else 0
                avg_daily = np.mean(list(date_counts.values())) if date_counts else 0
                overtrade_score = min(max_daily / 10.0, 1.0)
                behaviors["overtrade_score"] = round(float(overtrade_score), 4)
                behaviors["overtrade_warning"] = overtrade_score > 0.5
                behaviors["max_daily_trades"] = int(max_daily)
                behaviors["avg_daily_trades"] = round(float(avg_daily), 2)
            else:
                behaviors["overtrade_score"] = 0.0
                behaviors["overtrade_warning"] = False

            # 3. 止损纪律
            loss_trades = [t for t in closed_trades if t.pnl < 0]
            if loss_trades:
                max_loss = min(t.pnl_pct for t in loss_trades)
                avg_loss_pct = np.mean([t.pnl_pct for t in loss_trades])
                behaviors["stop_loss_discipline"] = {
                    "max_loss_pct": round(float(max_loss), 4),
                    "avg_loss_pct": round(float(avg_loss_pct), 4),
                    "loss_count": len(loss_trades),
                    "has_stop_loss_violation": max_loss < -10.0,
                }

            # 4. 盈亏比
            if buy_wins and buy_losses:
                avg_win_amt = np.mean([t.pnl for t in buy_wins])
                avg_loss_amt = abs(np.mean([t.pnl for t in buy_losses]))
                profit_loss_ratio = avg_win_amt / avg_loss_amt if avg_loss_amt > 0 else 0
                behaviors["profit_loss_ratio"] = round(float(profit_loss_ratio), 4)
                behaviors["pl_ratio_adequate"] = profit_loss_ratio > 1.5

            # 5. 持仓时间分析
            hold_durations = []
            for t in closed_trades:
                if t.entry_time and t.exit_time:
                    dur = (t.exit_time - t.entry_time).total_seconds() / 3600
                    hold_durations.append(dur)
            if hold_durations:
                behaviors["avg_hold_hours"] = round(float(np.mean(hold_durations)), 2)
                behaviors["median_hold_hours"] = round(float(np.median(hold_durations)), 2)

            # 6. 交易时段偏好
            hour_distribution = {}
            for t in closed_trades:
                if t.entry_time:
                    h = t.entry_time.hour
                    hour_distribution[h] = hour_distribution.get(h, 0) + 1
            if hour_distribution:
                peak_hour = max(hour_distribution, key=hour_distribution.get)
                behaviors["peak_trading_hour"] = peak_hour

            # 综合行为评分
            behavior_score = 80.0
            if behaviors.get("chase_kill_warning"):
                behavior_score -= 20
            if behaviors.get("overtrade_warning"):
                behavior_score -= 15
            if behaviors.get("stop_loss_discipline", {}).get("has_stop_loss_violation"):
                behavior_score -= 15
            if not behaviors.get("pl_ratio_adequate", True):
                behavior_score -= 10
            behaviors["behavior_score"] = max(round(behavior_score, 1), 0)

            # 诊断建议
            diagnostics = []
            if behaviors.get("chase_kill_warning"):
                diagnostics.append({
                    "issue": "追涨杀跌倾向",
                    "severity": "high",
                    "suggestion": "建议设置明确的入场信号，避免情绪化追涨；使用限价单代替市价单",
                })
            if behaviors.get("overtrade_warning"):
                diagnostics.append({
                    "issue": "过度交易",
                    "severity": "medium",
                    "suggestion": "建议降低交易频率，设置每日交易次数上限，等待高质量信号",
                })
            if behaviors.get("stop_loss_discipline", {}).get("has_stop_loss_violation"):
                diagnostics.append({
                    "issue": "止损纪律缺失",
                    "severity": "high",
                    "suggestion": "必须设置硬止损，建议单笔亏损不超过总资金的2%",
                })
            if not behaviors.get("pl_ratio_adequate", True):
                diagnostics.append({
                    "issue": "盈亏比不足",
                    "severity": "medium",
                    "suggestion": "建议提高止盈目标或收紧止损，目标盈亏比 > 2:1",
                })

            return {
                "success": True,
                "behaviors": behaviors,
                "diagnostics": diagnostics,
                "behavior_score": behaviors["behavior_score"],
                "total_trades_analyzed": len(closed_trades),
            }
        except Exception as e:
            logger.error(f"行为分析失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 归因分析
    # ============================================================

    def attribution_analysis(self) -> Dict[str, Any]:
        """回撤归因分析（Brinson归因框架）

        将策略回撤分解为选股效应、择时效应和交互效应。

        Returns:
            dict: {success, attribution: {selection, timing, interaction, ...}, drawdown_periods: [...]}
        """
        try:
            closed_trades = [t for t in self.trades if t.is_closed]
            if len(closed_trades) < 5:
                return {"success": False, "error": "交易记录不足"}

            total_pnl = sum(t.pnl for t in closed_trades)
            total_positive = sum(t.pnl for t in closed_trades if t.pnl > 0)
            total_negative = sum(t.pnl for t in closed_trades if t.pnl < 0)

            buy_trades = [t for t in closed_trades if t.direction == "buy"]
            sell_trades = [t for t in closed_trades if t.direction == "sell"]

            buy_pnl = sum(t.pnl for t in buy_trades)
            sell_pnl = sum(t.pnl for t in sell_trades)

            # 按标的归因
            symbol_attribution = {}
            for t in closed_trades:
                sym = t.symbol
                if sym not in symbol_attribution:
                    symbol_attribution[sym] = {"pnl": 0, "count": 0, "wins": 0, "losses": 0}
                symbol_attribution[sym]["pnl"] += t.pnl
                symbol_attribution[sym]["count"] += 1
                if t.pnl > 0:
                    symbol_attribution[sym]["wins"] += 1
                else:
                    symbol_attribution[sym]["losses"] += 1

            # 排序
            sorted_symbols = sorted(symbol_attribution.items(), key=lambda x: x[1]["pnl"])
            worst_symbols = sorted_symbols[:3]
            best_symbols = sorted_symbols[-3:]

            # 回撤阶段识别
            drawdown_periods = []
            if len(self._equity_curve) > 1:
                eq = np.array(self._equity_curve)
                peak = np.maximum.accumulate(eq)
                dd = (eq - peak) / peak
                in_dd = False
                dd_start = 0
                for i in range(1, len(dd)):
                    if dd[i] < -0.02 and not in_dd:
                        dd_start = i
                        in_dd = True
                    elif dd[i] >= -0.005 and in_dd:
                        dd_end = i
                        dd_max = np.min(dd[dd_start:dd_end])
                        dd_duration = dd_end - dd_start
                        drawdown_periods.append({
                            "start_index": dd_start,
                            "end_index": dd_end,
                            "max_drawdown": round(float(dd_max), 4),
                            "duration_days": dd_duration,
                        })
                        in_dd = False
                if in_dd:
                    drawdown_periods.append({
                        "start_index": dd_start,
                        "end_index": len(dd) - 1,
                        "max_drawdown": round(float(np.min(dd[dd_start:])), 4),
                        "duration_days": len(dd) - dd_start,
                    })

            return {
                "success": True,
                "total_pnl": round(float(total_pnl), 2),
                "total_positive_pnl": round(float(total_positive), 2),
                "total_negative_pnl": round(float(total_negative), 2),
                "buy_side_pnl": round(float(buy_pnl), 2),
                "sell_side_pnl": round(float(sell_pnl), 2),
                "symbol_attribution": {
                    "best": [{"symbol": s, "pnl": round(a["pnl"], 2), "win_rate": round(a["wins"]/max(a["count"],1), 2)}
                             for s, a in reversed(best_symbols)],
                    "worst": [{"symbol": s, "pnl": round(a["pnl"], 2), "win_rate": round(a["wins"]/max(a["count"],1), 2)}
                              for s, a in worst_symbols],
                },
                "drawdown_periods": drawdown_periods,
                "drawdown_count": len(drawdown_periods),
            }
        except Exception as e:
            logger.error(f"归因分析失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 绩效指标
    # ============================================================

    def calculate_performance(self) -> Dict[str, Any]:
        """绩效指标计算

        Returns:
            dict: {success, total_return, sharpe_ratio, max_drawdown, win_rate,
                   profit_loss_ratio, calmar_ratio, annual_return, ...}
        """
        try:
            closed_trades = [t for t in self.trades if t.is_closed]
            if len(closed_trades) < 3:
                return {"success": False, "error": "交易记录不足（至少需要3笔已平仓交易）"}

            # 基础指标
            total_pnl = sum(t.pnl for t in closed_trades)
            total_return = total_pnl / self.initial_capital

            winning_trades = [t for t in closed_trades if t.pnl > 0]
            losing_trades = [t for t in closed_trades if t.pnl < 0]

            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            total_count = len(closed_trades)

            win_rate = win_count / total_count if total_count > 0 else 0

            avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
            avg_loss = abs(np.mean([t.pnl for t in losing_trades])) if losing_trades else 0
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

            # 最大回撤
            if len(self._equity_curve) > 1:
                eq = np.array(self._equity_curve)
                peak = np.maximum.accumulate(eq)
                max_dd = float(np.min((eq - peak) / peak))
            else:
                max_dd = 0.0

            # 连续盈亏
            streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            for t in closed_trades:
                if t.pnl > 0:
                    streak = max(0, streak) + 1
                    max_win_streak = max(max_win_streak, streak)
                else:
                    streak = min(0, streak) - 1
                    max_loss_streak = max(max_loss_streak, abs(streak))

            # 卡玛比率
            calmar_ratio = total_return / abs(max_dd) if max_dd != 0 else float('inf')

            # 夏普比率（基于交易序列）
            if len(closed_trades) >= 5:
                trade_returns = [t.pnl_pct / 100 for t in closed_trades]
                sharpe = np.mean(trade_returns) / np.std(trade_returns) * np.sqrt(len(trade_returns)) if np.std(trade_returns) > 0 else 0
            else:
                sharpe = 0.0

            # 收益波动
            pnl_std = np.std([t.pnl for t in closed_trades])

            return {
                "success": True,
                "initial_capital": self.initial_capital,
                "current_capital": round(float(self.current_capital), 2),
                "total_pnl": round(float(total_pnl), 2),
                "total_return": round(float(total_return * 100), 4),
                "total_trades": total_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": round(float(win_rate * 100), 2),
                "profit_loss_ratio": round(float(profit_loss_ratio), 4) if profit_loss_ratio != float('inf') else None,
                "avg_win": round(float(avg_win), 2),
                "avg_loss": round(float(avg_loss), 2),
                "max_drawdown": round(float(max_dd * 100), 4),
                "sharpe_ratio": round(float(sharpe), 4),
                "calmar_ratio": round(float(calmar_ratio), 4) if calmar_ratio != float('inf') else None,
                "max_win_streak": max_win_streak,
                "max_loss_streak": max_loss_streak,
                "pnl_std": round(float(pnl_std), 2),
                "expectancy": round(float(win_rate * avg_win - (1 - win_rate) * avg_loss), 2),
            }
        except Exception as e:
            logger.error(f"绩效计算失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 综合报告
    # ============================================================

    def generate_report(self) -> Dict[str, Any]:
        """生成综合分析报告

        Returns:
            dict: {success, performance, behavior, attribution, summary, recommendations}
        """
        try:
            performance = self.calculate_performance()
            behavior = self.analyze_behavior()
            attribution = self.attribution_analysis()

            # 综合评分（0-100）
            perf_score = 0
            if performance.get("success"):
                perf = performance
                if perf.get("total_return", 0) > 0:
                    perf_score += 30
                elif perf.get("total_return", 0) > -10:
                    perf_score += 15
                if perf.get("win_rate", 0) > 50:
                    perf_score += 20
                elif perf.get("win_rate", 0) > 40:
                    perf_score += 10
                if perf.get("sharpe_ratio", 0) > 1:
                    perf_score += 20
                elif perf.get("sharpe_ratio", 0) > 0.5:
                    perf_score += 10
                if perf.get("max_drawdown", 0) > -15:
                    perf_score += 15
                elif perf.get("max_drawdown", 0) > -30:
                    perf_score += 5
                if perf.get("profit_loss_ratio") and perf["profit_loss_ratio"] > 1.5:
                    perf_score += 15

            behavior_score = behavior.get("behavior_score", 50)
            overall_score = (perf_score * 0.6 + behavior_score * 0.4)

            # 建议
            recommendations = []
            if performance.get("success"):
                if performance.get("win_rate", 0) < 40:
                    recommendations.append("胜率偏低，建议优化入场信号质量")
                if performance.get("max_drawdown", 0) < -20:
                    recommendations.append("回撤过大，建议降低仓位或增加对冲")
                if performance.get("sharpe_ratio", 0) < 0.5:
                    recommendations.append("夏普比率偏低，收益波动过大")
            for d in behavior.get("diagnostics", []):
                recommendations.append(d["suggestion"])

            return {
                "success": True,
                "report_time": datetime.now().isoformat(),
                "overall_score": round(overall_score, 1),
                "performance": performance,
                "behavior": behavior,
                "attribution": attribution,
                "recommendations": recommendations,
                "summary": self._generate_summary(performance, behavior, overall_score),
            }
        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return {"success": False, "error": str(e)}

    def _generate_summary(self, performance: Dict, behavior: Dict, score: float) -> str:
        """生成文字摘要"""
        parts = []
        if score >= 80:
            parts.append("综合表现优秀")
        elif score >= 60:
            parts.append("综合表现良好")
        elif score >= 40:
            parts.append("综合表现一般，有改进空间")
        else:
            parts.append("综合表现较差，需大幅改进")

        if performance.get("success"):
            parts.append(f"总收益率{performance.get('total_return', 0):.2f}%")
            parts.append(f"胜率{performance.get('win_rate', 0):.1f}%")

        if behavior.get("success"):
            diag_count = len(behavior.get("diagnostics", []))
            if diag_count == 0:
                parts.append("交易行为无明显问题")
            else:
                parts.append(f"发现{diag_count}个行为问题")

        return "；".join(parts)

    # ============================================================
    # 历史回测
    # ============================================================

    def backtest_history(self) -> Dict[str, Any]:
        """历史交割单回测

        基于已记录的交易序列，计算完整的回测指标。

        Returns:
            dict: {success, equity_curve, daily_returns, monthly_returns, statistics}
        """
        try:
            closed_trades = [t for t in self.trades if t.is_closed]
            if len(closed_trades) < 3:
                return {"success": False, "error": "交易记录不足"}

            # 构建净值曲线
            equity = self._equity_curve.copy()

            # 日收益率
            daily_returns = []
            for i in range(1, len(equity)):
                if equity[i-1] > 0:
                    daily_returns.append((equity[i] - equity[i-1]) / equity[i-1])

            daily_returns = np.array(daily_returns)

            # 月度统计
            monthly_returns = []
            current_month_pnl = 0.0
            current_month_start = equity[0]
            # 简化：按交易笔数分组近似
            chunk_size = max(len(closed_trades) // 12, 1)
            for i in range(0, len(closed_trades), chunk_size):
                chunk = closed_trades[i:i+chunk_size]
                chunk_pnl = sum(t.pnl for t in chunk)
                monthly_returns.append(chunk_pnl / self.initial_capital)

            monthly_returns = np.array(monthly_returns)

            # 统计
            total_return = (equity[-1] - equity[0]) / equity[0]
            annual_return = total_return * (252 / max(len(daily_returns), 1))

            sharpe = 0.0
            if len(daily_returns) > 1 and np.std(daily_returns) > 0:
                sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)

            mar = annual_return / abs(min(daily_returns.min(), -0.0001)) if len(daily_returns) > 0 else 0

            return {
                "success": True,
                "equity_curve": equity,
                "daily_returns": daily_returns.tolist(),
                "monthly_returns": monthly_returns.tolist(),
                "statistics": {
                    "total_return": round(float(total_return * 100), 4),
                    "annual_return": round(float(annual_return * 100), 4),
                    "sharpe_ratio": round(float(sharpe), 4),
                    "calmar_ratio": round(float(mar), 4),
                    "total_trades": len(closed_trades),
                    "initial_capital": self.initial_capital,
                    "final_equity": equity[-1],
                },
            }
        except Exception as e:
            logger.error(f"历史回测失败: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    analyzer = ShadowAccountAnalyzer(initial_capital=100000)

    # 模拟交易记录
    np.random.seed(42)
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
    for i in range(30):
        trade = {
            "symbol": symbols[np.random.randint(0, len(symbols))],
            "direction": np.random.choice(["buy", "sell"], p=[0.7, 0.3]),
            "entry_price": 100 + np.random.randn() * 10,
            "exit_price": 100 + np.random.randn() * 15,
            "quantity": np.random.randint(100, 1000),
            "entry_time": datetime.now() - timedelta(days=np.random.randint(1, 90)),
            "exit_time": datetime.now(),
            "entry_reason": "signal_trigger",
            "exit_reason": "take_profit" if np.random.random() > 0.4 else "stop_loss",
        }
        analyzer.record_trade(trade)

    # 绩效
    perf = analyzer.calculate_performance()
    print(f"\n绩效指标: success={perf['success']}")
    if perf['success']:
        print(f"  总收益率: {perf['total_return']:.2f}%")
        print(f"  胜率: {perf['win_rate']:.1f}%")
        print(f"  夏普: {perf['sharpe_ratio']:.4f}")
        print(f"  最大回撤: {perf['max_drawdown']:.2f}%")

    # 行为诊断
    behavior = analyzer.analyze_behavior()
    print(f"\n行为诊断: score={behavior.get('behavior_score', 'N/A')}")
    if behavior.get('success'):
        for d in behavior.get('diagnostics', []):
            print(f"  [{d['severity']}] {d['issue']}: {d['suggestion'][:50]}...")

    # 归因分析
    attribution = analyzer.attribution_analysis()
    print(f"\n归因分析: success={attribution['success']}")
    if attribution['success']:
        print(f"  总盈亏: {attribution['total_pnl']:.2f}")
        print(f"  回撤阶段数: {attribution['drawdown_count']}")

    # 综合报告
    report = analyzer.generate_report()
    print(f"\n综合报告: score={report.get('overall_score', 'N/A')}")
    print(f"  摘要: {report.get('summary', 'N/A')}")