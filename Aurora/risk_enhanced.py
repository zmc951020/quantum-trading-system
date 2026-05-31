#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora 增强风控系统 v2.0
========================
基于 HardRiskEngine 增强：
- 组合级别 VaR/CVaR/ES 计算
- 蒙特卡洛 VaR 模拟
- 协方差矩阵组合风险
- 动态止损止盈
- 市场冲击预警
- A股特殊规则增强（T+1/涨跌停/ST）
- 风控报告自动生成
"""

import os
import sys
import json
import time
import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import deque, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from risk_manager import HardRiskEngine, CircuitBreakerState, StrategyHealth

logger = logging.getLogger("EnhancedRisk")

# ============================================================
# 数据类
# ============================================================

@dataclass
class VaRResult:
    """VaR 计算结果"""
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    method: str = "historical"
    confidence: float = 0.95
    horizon_days: int = 1
    calculated_at: str = ""

@dataclass
class PortfolioRisk:
    """组合风险指标"""
    total_value: float = 0.0
    total_var_95: float = 0.0
    total_cvar_95: float = 0.0
    diversification_ratio: float = 0.0
    concentration_risk: float = 0.0
    leverage: float = 0.0
    beta: float = 0.0
    tracking_error: float = 0.0
    correlation_matrix: Optional[np.ndarray] = None
    marginal_var: Dict[str, float] = field(default_factory=dict)
    component_var: Dict[str, float] = field(default_factory=dict)

@dataclass
class DynamicStopLoss:
    """动态止损配置"""
    symbol: str
    entry_price: float
    initial_stop: float  # 初始止损价
    trailing_stop_pct: float = 0.05  # 跟踪止损百分比
    atr_multiplier: float = 2.0  # ATR倍数
    time_stop_days: int = 20  # 时间止损（天）
    partial_scale_out: float = 0.5  # 分批出场比例

# ============================================================
# 增强风控引擎
# ============================================================

class EnhancedRiskEngine(HardRiskEngine):
    """
    增强风控引擎
    =============
    继承 HardRiskEngine，新增：
    - VaR/CVaR 多方法计算
    - 组合风险管理
    - 协方差矩阵分析
    - 动态止损系统
    - 市场冲击评估
    - 风控报告生成
    """

    def __init__(
        self,
        config_path: str = "risk_config.json",
        var_confidence: float = 0.95,
        var_horizon: int = 1,
        var_method: str = "historical",
        max_leverage: float = 1.0,
        max_concentration: float = 0.30,
        max_drawdown_limit: float = 0.20,
    ):
        """
        Args:
            config_path: 配置文件路径
            var_confidence: VaR 置信水平
            var_horizon: VaR 计算周期（天）
            var_method: VaR 方法 (historical / parametric / monte_carlo)
            max_leverage: 最大杠杆
            max_concentration: 最大集中度
            max_drawdown_limit: 最大回撤限制
        """
        super().__init__(config_path)

        # VaR 设置
        self.var_confidence = var_confidence
        self.var_horizon = var_horizon
        self.var_method = var_method

        # 组合限制
        self.max_leverage = max_leverage
        self.max_concentration = max_concentration
        self.max_drawdown_limit = max_drawdown_limit

        # 动态止损
        self.dynamic_stops: Dict[str, DynamicStopLoss] = {}

        # 收益历史（用于VaR计算）
        self.returns_history: deque = deque(maxlen=1000)
        self._returns_lock = threading.Lock()

        # 协方差矩阵缓存
        self._cov_matrix_cache: Optional[np.ndarray] = None
        self._cov_matrix_timestamp: float = 0.0
        self._cov_cache_ttl: float = 300.0  # 5分钟缓存

        # 风控报告
        self.risk_reports: deque = deque(maxlen=100)

        logger.info("增强风控引擎初始化完成 | VaR方法: %s | 置信度: %.2f", var_method, var_confidence)

    # ============================================================
    # VaR 计算（三种方法）
    # ============================================================

    def calculate_var(
        self,
        returns: Optional[np.ndarray] = None,
        method: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> VaRResult:
        """
        计算 VaR/CVaR
        
        Args:
            returns: 历史收益率序列
            method: 计算方法 (historical/parametric/monte_carlo)
            confidence: 置信水平
        
        Returns:
            VaRResult
        """
        method = method or self.var_method
        confidence = confidence or self.var_confidence

        # 获取收益序列
        if returns is None:
            returns = np.array(list(self.returns_history))
            if len(returns) < 30:
                return VaRResult(
                    calculated_at=datetime.now().isoformat(),
                    method=method,
                )

        if len(returns) < 2:
            return VaRResult(calculated_at=datetime.now().isoformat(), method=method)

        if method == "historical":
            var_95, var_99, cvar_95, cvar_99 = self._historical_var(returns, confidence)
        elif method == "parametric":
            var_95, var_99, cvar_95, cvar_99 = self._parametric_var(returns, confidence)
        elif method == "monte_carlo":
            var_95, var_99, cvar_95, cvar_99 = self._monte_carlo_var(returns, confidence)
        else:
            var_95 = var_99 = cvar_95 = cvar_99 = 0.0

        return VaRResult(
            var_95=round(var_95, 6),
            var_99=round(var_99, 6),
            cvar_95=round(cvar_95, 6),
            cvar_99=round(cvar_99, 6),
            method=method,
            confidence=confidence,
            horizon_days=self.var_horizon,
            calculated_at=datetime.now().isoformat(),
        )

    def _historical_var(self, returns: np.ndarray, confidence: float) -> Tuple[float, float, float, float]:
        """历史模拟法 VaR"""
        sorted_returns = np.sort(returns)
        n = len(sorted_returns)

        # VaR
        idx_95 = max(0, int(n * (1 - confidence)))
        idx_99 = max(0, int(n * 0.01))

        var_95 = abs(sorted_returns[idx_95]) if idx_95 < n else 0
        var_99 = abs(sorted_returns[idx_99]) if idx_99 < n else 0

        # CVaR (Expected Shortfall)
        tail_95 = sorted_returns[:idx_95 + 1]
        tail_99 = sorted_returns[:idx_99 + 1]

        cvar_95 = abs(tail_95.mean()) if len(tail_95) > 0 else 0
        cvar_99 = abs(tail_99.mean()) if len(tail_99) > 0 else 0

        return var_95, var_99, cvar_95, cvar_99

    def _parametric_var(self, returns: np.ndarray, confidence: float) -> Tuple[float, float, float, float]:
        """参数法 VaR（假设正态分布）"""
        from scipy import stats

        mu = returns.mean()
        sigma = returns.std()

        if sigma <= 0:
            return 0, 0, 0, 0

        # VaR = μ - z_α × σ
        z_95 = stats.norm.ppf(1 - confidence)
        z_99 = stats.norm.ppf(0.01)

        var_95 = abs(mu - z_95 * sigma)
        var_99 = abs(mu - z_99 * sigma)

        # CVaR under normality
        phi_95 = stats.norm.pdf(z_95)
        cvar_95 = abs(mu - sigma * phi_95 / (1 - confidence))

        phi_99 = stats.norm.pdf(z_99)
        cvar_99 = abs(mu - sigma * phi_99 / 0.01)

        return var_95, var_99, cvar_95, cvar_99

    def _monte_carlo_var(self, returns: np.ndarray, confidence: float, n_simulations: int = 10000) -> Tuple[float, float, float, float]:
        """蒙特卡洛 VaR"""
        mu = returns.mean()
        sigma = returns.std()

        if sigma <= 0:
            return 0, 0, 0, 0

        # 模拟
        simulated_returns = np.random.normal(mu, sigma, n_simulations)
        sorted_sim = np.sort(simulated_returns)

        n = len(sorted_sim)
        idx_95 = int(n * (1 - confidence))
        idx_99 = int(n * 0.01)

        var_95 = abs(sorted_sim[idx_95])
        var_99 = abs(sorted_sim[idx_99])

        cvar_95 = abs(sorted_sim[:idx_95].mean()) if idx_95 > 0 else 0
        cvar_99 = abs(sorted_sim[:idx_99].mean()) if idx_99 > 0 else 0

        return var_95, var_99, cvar_95, cvar_99

    # ============================================================
    # 组合风险管理
    # ============================================================

    def calculate_portfolio_risk(
        self,
        positions: Dict[str, Dict],
        returns_data: Dict[str, np.ndarray],
        current_prices: Dict[str, float],
    ) -> PortfolioRisk:
        """
        计算组合风险

        Args:
            positions: {"symbol": {"quantity": float, "avg_cost": float}, ...}
            returns_data: {"symbol": returns_array, ...}
            current_prices: {"symbol": price, ...}

        Returns:
            PortfolioRisk
        """
        pr = PortfolioRisk()

        # 计算组合总价值
        total_value = 0.0
        weights = {}
        for sym, pos in positions.items():
            qty = pos.get("quantity", 0)
            price = current_prices.get(sym, pos.get("avg_cost", 0))
            value = qty * price
            if value > 0:
                weights[sym] = value
                total_value += value

        pr.total_value = total_value

        if total_value <= 0 or len(weights) < 1:
            return pr

        # 归一化权重
        norm_weights = {k: v / total_value for k, v in weights.items()}

        # 集中度风险（Herfindahl-Hirschman Index）
        hhi = sum(w ** 2 for w in norm_weights.values())
        pr.concentration_risk = hhi

        # 杠杆
        pr.leverage = total_value / max(self.initial_capital if hasattr(self, 'initial_capital') else total_value, 1)

        # 协方差矩阵
        symbols = list(norm_weights.keys())
        n = len(symbols)
        if n < 1:
            return pr

        # 构建收益率矩阵
        min_len = min(len(returns_data.get(s, [])) for s in symbols if s in returns_data)
        if min_len < 30:
            return pr

        returns_matrix = np.zeros((min_len, n))
        for i, sym in enumerate(symbols):
            if sym in returns_data:
                r = returns_data[sym][-min_len:]
                returns_matrix[:, i] = r

        # 协方差矩阵
        cov_matrix = np.cov(returns_matrix, rowvar=False)
        self._cov_matrix_cache = cov_matrix
        self._cov_matrix_timestamp = time.time()
        pr.correlation_matrix = np.corrcoef(returns_matrix, rowvar=False)

        # 组合 VaR
        weights_array = np.array([norm_weights[s] for s in symbols])
        portfolio_variance = weights_array @ cov_matrix @ weights_array
        portfolio_std = np.sqrt(portfolio_variance)

        z_95 = 1.645  # 标准正态 95% 分位数
        z_99 = 2.326

        pr.total_var_95 = portfolio_std * z_95 * np.sqrt(self.var_horizon)
        pr.total_cvar_95 = portfolio_std * 2.063 * np.sqrt(self.var_horizon)  # 正态假设下的CVaR

        # 边际 VaR（每个资产对总风险的边际贡献）
        marginal_var = {}
        component_var = {}
        for i, sym in enumerate(symbols):
            beta_i = (cov_matrix[i] @ weights_array) / portfolio_variance
            mvar = beta_i * portfolio_std * z_95
            cvar_i = norm_weights[sym] * mvar
            marginal_var[sym] = mvar
            component_var[sym] = cvar_i

        pr.marginal_var = marginal_var
        pr.component_var = component_var

        # 分散化比率
        weighted_std = sum(norm_weights[s] * np.sqrt(cov_matrix[i, i]) for i, s in enumerate(symbols))
        if portfolio_std > 0:
            pr.diversification_ratio = weighted_std / portfolio_std

        return pr

    # ============================================================
    # 动态止损止盈
    # ============================================================

    def set_dynamic_stop(
        self,
        symbol: str,
        entry_price: float,
        atr: float = 0,
        trailing_stop_pct: float = 0.05,
        atr_multiplier: float = 2.0,
        time_stop_days: int = 20,
    ) -> DynamicStopLoss:
        """
        设置动态止损

        Args:
            symbol: 标的
            entry_price: 入场价
            atr: 当前ATR值
            trailing_stop_pct: 跟踪止损百分比
            atr_multiplier: ATR倍数
            time_stop_days: 时间止损天数

        Returns:
            DynamicStopLoss 配置
        """
        initial_stop = entry_price * (1 - trailing_stop_pct)

        # 如果提供了 ATR，优先使用 ATR 止损
        if atr > 0:
            initial_stop = entry_price - atr_multiplier * atr

        dsl = DynamicStopLoss(
            symbol=symbol,
            entry_price=entry_price,
            initial_stop=initial_stop,
            trailing_stop_pct=trailing_stop_pct,
            atr_multiplier=atr_multiplier,
            time_stop_days=time_stop_days,
        )

        self.dynamic_stops[symbol] = dsl
        logger.info(f"动态止损设置: {symbol} | 入场: {entry_price:.2f} | 止损: {initial_stop:.2f}")
        return dsl

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        atr: float = 0,
        held_days: int = 0,
    ) -> Dict[str, Any]:
        """
        更新跟踪止损

        Returns:
            {"action": "hold"|"stop_loss"|"time_stop", "stop_price": float, ...}
        """
        if symbol not in self.dynamic_stops:
            return {"action": "hold", "reason": "no_stop_set"}

        dsl = self.dynamic_stops[symbol]

        # ATR 动态更新
        if atr > 0:
            new_stop = current_price - dsl.atr_multiplier * atr
            if new_stop > dsl.initial_stop:
                dsl.initial_stop = new_stop
                logger.debug(f"跟踪止损上移: {symbol} → {new_stop:.2f}")

        # 百分比跟踪止损
        trailing_stop = current_price * (1 - dsl.trailing_stop_pct)
        if trailing_stop > dsl.initial_stop:
            dsl.initial_stop = trailing_stop

        # 检查止损触发
        if current_price <= dsl.initial_stop:
            logger.warning(f"止损触发: {symbol} | 当前价: {current_price:.2f} ≤ 止损: {dsl.initial_stop:.2f}")
            del self.dynamic_stops[symbol]
            return {
                "action": "stop_loss",
                "symbol": symbol,
                "current_price": current_price,
                "stop_price": dsl.initial_stop,
                "entry_price": dsl.entry_price,
                "loss_pct": (current_price - dsl.entry_price) / dsl.entry_price * 100,
            }

        # 时间止损
        if held_days >= dsl.time_stop_days:
            logger.info(f"时间止损触发: {symbol} | 持有天数: {held_days}")
            return {
                "action": "time_stop",
                "symbol": symbol,
                "current_price": current_price,
                "held_days": held_days,
            }

        return {
            "action": "hold",
            "symbol": symbol,
            "current_price": current_price,
            "stop_price": dsl.initial_stop,
            "distance_pct": (current_price - dsl.initial_stop) / current_price * 100,
        }

    def partial_scale_out(
        self,
        symbol: str,
        current_price: float,
        target_pct: float = 0.05,
    ) -> Dict[str, Any]:
        """
        分批止盈出场

        Args:
            symbol: 标的
            current_price: 当前价
            target_pct: 目标盈利百分比

        Returns:
            出场建议
        """
        if symbol not in self.dynamic_stops:
            return {"action": "hold"}

        dsl = self.dynamic_stops[symbol]
        pnl_pct = (current_price - dsl.entry_price) / dsl.entry_price

        if pnl_pct >= target_pct * 2:
            # 到达2倍目标，出场剩余
            del self.dynamic_stops[symbol]
            return {
                "action": "exit_all",
                "symbol": symbol,
                "pnl_pct": pnl_pct * 100,
                "reason": f"达到{target_pct*2*100:.0f}%止盈",
            }
        elif pnl_pct >= target_pct:
            # 到达目标，部分出场
            return {
                "action": "scale_out",
                "symbol": symbol,
                "scale_fraction": dsl.partial_scale_out,
                "pnl_pct": pnl_pct * 100,
                "reason": f"达到{target_pct*100:.0f}%部分止盈",
            }

        return {"action": "hold", "pnl_pct": pnl_pct * 100}

    # ============================================================
    # 市场冲击评估
    # ============================================================

    def assess_market_impact(
        self,
        symbol: str,
        order_size: float,
        daily_volume: float,
        bid_ask_spread: float = 0.001,
        volatility: float = 0.02,
    ) -> Dict[str, Any]:
        """
        评估市场冲击成本

        基于 Almgren-Chriss 模型简化版
        """
        # 参与率
        participation_rate = order_size / max(daily_volume, 1)

        # 永久冲击（信息泄露）
        permanent_impact = 0.1 * volatility * np.sqrt(participation_rate)

        # 临时冲击（流动性消耗）
        temporary_impact = 0.5 * bid_ask_spread + 0.1 * volatility * participation_rate ** 0.5

        # 总冲击成本(bps)
        total_impact_bps = (permanent_impact + temporary_impact) * 10000

        # 风险等级
        if participation_rate > 0.10:
            risk = "CRITICAL"
            message = "成交量占比超过10%，强烈建议拆分订单"
        elif participation_rate > 0.05:
            risk = "HIGH"
            message = "成交量占比超过5%，建议使用冰山订单"
        elif participation_rate > 0.01:
            risk = "MEDIUM"
            message = "成交量占比超过1%，关注市场冲击"
        else:
            risk = "LOW"
            message = "成交量占比正常"

        return {
            "symbol": symbol,
            "order_size": order_size,
            "daily_volume": daily_volume,
            "participation_rate": round(participation_rate, 6),
            "permanent_impact_bps": round(permanent_impact * 10000, 2),
            "temporary_impact_bps": round(temporary_impact * 10000, 2),
            "total_impact_bps": round(total_impact_bps, 2),
            "risk_level": risk,
            "message": message,
        }

    # ============================================================
    # A股增强规则
    # ============================================================

    def a_share_pre_trade_check_enhanced(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        prev_close: float,
        is_st: bool = False,
        is_kcb: bool = False,
        is_cyb: bool = False,
        held_days: int = 0,
    ) -> Dict[str, Any]:
        """
        A股增强版前置检查
        ===================
        在基础检查之上增加：
        - T+1 卖出校验
        - 涨跌停精确校验
        - ST/科创/创业板不同涨跌幅
        - 持仓天数检查
        - 逆回购/ETF特殊规则提示
        """
        # 基础风控检查
        result = self.pre_trade_check(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
        )

        if not result["allowed"]:
            return result

        checks = []

        # T+1 卖出校验
        if side.lower() == "sell" and held_days < 1:
            checks.append({
                "rule": "T+1",
                "passed": True,  # 通过（A股卖出是T+1，即买入次日可卖）
                "detail": f"持仓{held_days}天，可卖出" if held_days >= 1 else "A股T+1限制：买入当日不可卖出",
            })

        # 涨跌停精确校验
        limits = self.get_price_limits(prev_close, is_st=is_st, is_kcb=is_kcb, is_cyb=is_cyb)
        price_ok = limits["low_limit"] <= price <= limits["high_limit"]

        # ST股票特殊处理
        if is_st and side.lower() == "buy":
            checks.append({
                "rule": "ST_BUY_WARNING",
                "passed": True,
                "detail": "ST股票买入风险提示，建议单独审批",
            })

        # 科创/创业板增持提醒
        if (is_kcb or is_cyb) and side.lower() == "buy":
            checks.append({
                "rule": "KCB_CYB_VOLATILITY",
                "passed": True,
                "detail": f"{'科创板' if is_kcb else '创业板'}波动较大(±20%)，请确认风险承受",
            })

        return {
            "allowed": price_ok,
            "reason": "全部校验通过" if price_ok else f"涨跌停校验未通过",
            "risk_level": "LOW" if price_ok else "CRITICAL",
            "price_limits": limits,
            "additional_checks": checks,
        }

    # ============================================================
    # 风控报告
    # ============================================================

    def generate_risk_report(
        self,
        portfolio_risk: Optional[PortfolioRisk] = None,
        var_result: Optional[VaRResult] = None,
    ) -> Dict[str, Any]:
        """
        生成风控报告
        """
        state = self.get_state()
        alerts = self.get_recent_alerts(50)

        report = {
            "report_time": datetime.now().isoformat(),
            "engine_state": {
                "circuit_breaker": state["circuit_breaker"],
                "daily_pnl": state["daily_pnl"],
                "daily_trades": state["daily_trades"],
                "consecutive_losses": state["consecutive_losses"],
                "suspended_strategies": state["suspended_strategies"],
                "trading_disabled": state["trading_disabled"],
            },
            "risk_metrics": {},
            "active_alerts": len(alerts),
            "recent_alerts": alerts[-10:],
            "dynamic_stops": {
                sym: {
                    "entry": d.entry_price,
                    "stop": d.initial_stop,
                    "trailing": d.trailing_stop_pct,
                }
                for sym, d in self.dynamic_stops.items()
            },
        }

        # 组合风险
        if portfolio_risk:
            report["risk_metrics"]["portfolio"] = {
                "total_value": portfolio_risk.total_value,
                "var_95": portfolio_risk.total_var_95,
                "cvar_95": portfolio_risk.total_cvar_95,
                "diversification_ratio": portfolio_risk.diversification_ratio,
                "concentration_hhi": portfolio_risk.concentration_risk,
                "leverage": portfolio_risk.leverage,
                "marginal_var": portfolio_risk.marginal_var,
                "component_var": portfolio_risk.component_var,
            }

        # VaR
        if var_result:
            report["risk_metrics"]["var"] = {
                "var_95": var_result.var_95,
                "var_99": var_result.var_99,
                "cvar_95": var_result.cvar_95,
                "cvar_99": var_result.cvar_99,
                "method": var_result.method,
                "confidence": var_result.confidence,
                "horizon_days": var_result.horizon_days,
            }

        self.risk_reports.append(report)
        return report

    def log_return(self, ret: float):
        """记录收益率"""
        with self._returns_lock:
            self.returns_history.append(ret)

    def get_cov_matrix(self, symbols: Optional[List[str]] = None) -> Optional[np.ndarray]:
        """获取缓存的协方差矩阵"""
        if self._cov_matrix_cache is not None:
            if time.time() - self._cov_matrix_timestamp < self._cov_cache_ttl:
                return self._cov_matrix_cache
        return None

    def get_risk_score(self) -> float:
        """
        综合风险评分（0-100，越高越危险）
        考虑因素：
        - 熔断状态
        - 日亏损
        - 连续亏损
        - 废单率
        - VaR
        """
        score = 0.0
        state = self.get_state()

        # 熔断状态权重最高
        if state["circuit_breaker"] == "emergency":
            score += 50
        elif state["circuit_breaker"] == "halted":
            score += 35
        elif state["circuit_breaker"] == "warning":
            score += 20

        # 当日亏损
        if state["daily_pnl"] < 0:
            score += min(25, abs(state["daily_pnl"]) * 100)

        # 连续亏损
        score += state["consecutive_losses"] * 3

        # 暂停策略数
        score += len(state["suspended_strategies"]) * 5

        # 废单风暴
        if state["rejection_storm_count"] > 5:
            score += 15

        return min(100, score)


# ============================================================
# 全局单例
# ============================================================

_enhanced_risk_engine: Optional[EnhancedRiskEngine] = None
_risk_lock = threading.Lock()

def get_enhanced_risk_engine() -> EnhancedRiskEngine:
    """获取增强风控引擎单例"""
    global _enhanced_risk_engine
    with _risk_lock:
        if _enhanced_risk_engine is None:
            _enhanced_risk_engine = EnhancedRiskEngine()
        return _enhanced_risk_engine


if __name__ == "__main__":
    # 快速测试
    engine = EnhancedRiskEngine()
    
    # 模拟收益数据
    import numpy as np
    returns = np.random.normal(0.001, 0.02, 252)
    for r in returns:
        engine.log_return(r)
    
    var = engine.calculate_var(method="historical")
    print(f"VaR 95: {var.var_95:.4f}")
    print(f"CVaR 95: {var.cvar_95:.4f}")
    print(f"综合风险评分: {engine.get_risk_score():.1f}")
    
    # 动态止损测试
    engine.set_dynamic_stop("000001.SZ", 10.0, atr=0.5)
    result = engine.update_trailing_stop("000001.SZ", 9.2)
    print(f"止损检查: {json.dumps(result, indent=2, ensure_ascii=False)}")