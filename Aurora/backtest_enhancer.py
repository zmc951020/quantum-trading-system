# coding: utf-8
"""
回测增强增益模块 — 手续费/滑点/未来函数/实盘一致性
======================================================
增益性补充，插入现有回测循环中。
不修改原有 main.py:run_backtest() 代码。

功能：
  - A股真实手续费模型（佣金0.025%+印花税0.05%卖出+过户费0.001%）
  - 滑点模型（固定+比例）
  - 未来函数检测（特征计算日期 ≤ 信号生成日期）
  - 回测vs实盘偏差监控
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── A股交易费率 ──
# 佣金: 万分之2.5 (双边，最低5元)
# 印花税: 千分之0.5 (仅卖出，2024年起)
# 过户费: 十万分之1 (双边)
COMMISSION_RATE  = 0.00025
STAMP_TAX_RATE   = 0.0005   # 卖出
TRANSFER_FEE_RATE = 0.00001

# 佣金最低收费
MIN_COMMISSION = 5.0


def calc_a_share_cost(side: str, quantity: int, price: float) -> float:
    """
    计算A股单笔交易手续费

    Args:
        side: 'buy' | 'sell'
        quantity: 成交数量（股）
        price: 成交均价

    Returns:
        手续费总额
    """
    turnover = quantity * price
    # 佣金
    commission = max(turnover * COMMISSION_RATE, MIN_COMMISSION)
    # 印花税（仅卖出）
    stamp_tax = 0.0
    if side == "sell":
        stamp_tax = turnover * STAMP_TAX_RATE
    # 过户费
    transfer_fee = turnover * TRANSFER_FEE_RATE
    total = commission + stamp_tax + transfer_fee
    return round(total, 2)


def apply_slippage(price: float, side: str, slippage_bps: float = 1.0) -> float:
    """
    应用滑点

    Args:
        price: 信号价格
        side: 'buy' | 'sell'（买入向上滑，卖出向下滑）
        slippage_bps: 滑点基点（默认1bps=0.01%）
    Returns:
        含滑点的成交价
    """
    factor = 1 + (slippage_bps / 10000)
    if side == "buy":
        return round(price * factor, 2)
    else:
        return round(price / factor, 2)


class FutureFunctionDetector:
    """
    未来函数检测器

    检测规则：
    1. 特征计算所用数据的最大日期 ≤ 信号生成日期
    2. 交易执行日期 > 信号生成日期
    3. 禁止信号日期当天使用当天最高/最低价（实盘中不可得）
    """

    def __init__(self):
        self.violations: List[Dict[str, Any]] = []

    def check_signal_timing(
        self,
        signal_date: date,
        feature_data_max_date: date,
        strategy_name: str = ""
    ) -> bool:
        """
        检查信号是否存在未来函数

        Returns:
            True — 有未来函数违规
            False — 无问题
        """
        if feature_data_max_date > signal_date:
            violation = {
                "strategy": strategy_name,
                "signal_date": signal_date.isoformat(),
                "feature_max_date": feature_data_max_date.isoformat(),
                "reason": "特征数据日期晚于信号生成日期，疑似未来函数",
                "severity": "critical",
            }
            self.violations.append(violation)
            logger.critical(
                "未来函数检测! %s: 特征日期%s > 信号日期%s",
                strategy_name or "未知策略",
                feature_data_max_date, signal_date
            )
            return True
        return False

    def check_intraday_peek(
        self,
        signal_date: date,
        used_fields: List[str],
        strategy_name: str = ""
    ) -> bool:
        """
        检查信号生成是否使用了当日最高/最低价（实盘中不可获得）

        Returns:
            True — 违规
        """
        peek_fields = {"high", "low", "日内最高", "日内最低"}
        used_set = {f.lower() for f in used_fields}
        suspicious = peek_fields & used_set
        if suspicious:
            violation = {
                "strategy": strategy_name,
                "signal_date": signal_date.isoformat(),
                "used_fields": list(suspicious),
                "reason": "信号生成使用当日最高/最低价，实盘中不可得",
                "severity": "warning",
            }
            self.violations.append(violation)
            logger.warning(
                "可能未来函数: %s 使用了 %s（当日不可得）",
                strategy_name or "未知策略", suspicious
            )
            return True
        return False

    def get_report(self) -> Dict[str, Any]:
        return {
            "total_violations": len(self.violations),
            "violations": self.violations[-50:],
        }


def check_backtest_live_consistency(
    backtest_metrics: Dict[str, float],
    live_metrics: Dict[str, float],
    tolerance_pct: float = 0.15
) -> Dict[str, Any]:
    """
    检查回测与实盘偏差

    Args:
        backtest_metrics: {'sharpe': 1.5, 'win_rate': 0.55, ...}
        live_metrics:      {'sharpe': 1.2, 'win_rate': 0.50, ...}
        tolerance_pct:     偏差容忍度

    Returns:
        {'ok': bool, 'deviations': [...]}
    """
    deviations = []
    for key in set(backtest_metrics.keys()) & set(live_metrics.keys()):
        bt_val = backtest_metrics.get(key, 0)
        live_val = live_metrics.get(key, 0)
        if bt_val == 0:
            continue
        dev = abs(live_val - bt_val) / abs(bt_val)
        if dev > tolerance_pct:
            deviations.append({
                "metric": key,
                "backtest": round(bt_val, 4),
                "live": round(live_val, 4),
                "deviation_pct": round(dev * 100, 1),
                "alert": dev > 0.3,
            })
    return {
        "ok": len(deviations) == 0,
        "deviations": deviations,
    }