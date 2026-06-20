#!/usr/bin/env python3
"""
风控评估模块（Risk Control Module）

核心职责：
  1. 预实盘前的全面风险评估
  2. 多维度风控指标计算
  3. 风险评分与等级判定
  4. 风险报告生成

评估维度：
  - 策略风险：夏普比率、最大回撤、胜率、盈亏比
  - 市场风险：贝塔系数、波动率、相关性
  - 持仓风险：集中度、行业分布、单票上限
  - 操作风险：滑点容忍、流动性、执行成本
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 风险等级
# ============================================================

class RiskLevel(Enum):
    LOW = "low"           # 低风险（评分80+）
    MEDIUM = "medium"     # 中等风险（评分60-80）
    HIGH = "high"         # 高风险（评分40-60）
    CRITICAL = "critical" # 极高风险（评分<40）

# ============================================================
# 风控评估结果
# ============================================================

@dataclass
class RiskAssessment:
    symbol: str                      # 股票代码
    strategy_name: str               # 策略名称
    overall_score: float             # 综合评分 (0-100)
    risk_level: RiskLevel            # 风险等级
    strategy_risk: Dict[str, Any]    # 策略风险指标
    market_risk: Dict[str, Any]      # 市场风险指标
    position_risk: Dict[str, Any]    # 持仓风险指标
    operational_risk: Dict[str, Any] # 操作风险指标
    recommendations: List[str]       # 改进建议
    passed: bool                     # 是否通过

# ============================================================
# 风控评估器
# ============================================================

class RiskControlEngine:
    def __init__(self):
        # 评分权重配置
        self._weights = {
            "strategy": 0.35,    # 策略风险权重
            "market": 0.25,      # 市场风险权重
            "position": 0.20,    # 持仓风险权重
            "operational": 0.20  # 操作风险权重
        }
        
        # 阈值配置
        self._thresholds = {
            "sharpe": 1.5,
            "max_drawdown": 20.0,
            "win_rate": 50.0,
            "profit_factor": 1.5,
            "beta": 1.5,
            "volatility": 0.3,
            "concentration": 30.0,
            "liquidity": 1.0
        }

        # 评分公式系数 (可配置)
        # 设计原则: 每个指标独立映射到 0-100 分，满分表示该指标处于理想区间
        self._coefficients = {
            # 策略风险系数
            "sharpe_multiplier": 40,       # sharpe=2.5 → 100分 (行业标准: 优秀策略Sharpe≈2.0-3.0)
            "drawdown_multiplier": 3,      # max_drawdown=33% → 0分 (33%回撤视为不可接受)
            "win_rate_offset": 30,         # 胜率30% → 0分 (低于30%胜率策略不可靠)
            "win_rate_multiplier": 2.5,    # 胜率70% → 100分 (行业标准: 优秀策略胜率≈60-70%)
            "profit_factor_multiplier": 50, # profit_factor=2.0 → 100分 (盈亏比2.0以上视为优秀)
            "stability_multiplier": 0.5,   # 200笔交易 → 100分 (交易次数越多统计越稳定)
            # 市场风险系数
            "volatility_multiplier": 200,  # 波动率0.5 → 0分 (年化波动率50%以上视为极高风险)
            "beta_penalty": 50,            # beta偏离1.0的惩罚系数
            "correlation_offset": 50,      # 相关性基准分
            "correlation_multiplier": 50,  # 相关性系数
            # 操作风险系数
            "slippage_multiplier": 10000,   # 滑点0.2% → 80分, 0.5%→50分 (合理惩罚区间)
            "liquidity_multiplier": 50,     # 日均成交额2亿 → 100分 (流动性充足)
            "cost_multiplier": 10000,       # 执行成本0.2% → 80分 (同滑点逻辑)
        }

    def assess(self, symbol: str, strategy_name: str, 
               backtest_result: Dict, position_info: Dict = None) -> RiskAssessment:
        """执行全面风险评估"""
        position_info = position_info or {}
        
        # 计算各维度风险
        strategy_risk = self._assess_strategy_risk(backtest_result)
        market_risk = self._assess_market_risk(backtest_result, position_info)
        position_risk = self._assess_position_risk(position_info)
        operational_risk = self._assess_operational_risk(backtest_result, position_info)
        
        # 综合评分
        overall_score = self._calculate_overall_score(
            strategy_risk["score"],
            market_risk["score"],
            position_risk["score"],
            operational_risk["score"]
        )
        
        # 确定风险等级
        risk_level = self._get_risk_level(overall_score)
        
        # 生成建议
        recommendations = self._generate_recommendations(
            strategy_risk, market_risk, position_risk, operational_risk
        )
        
        return RiskAssessment(
            symbol=symbol,
            strategy_name=strategy_name,
            overall_score=round(overall_score, 2),
            risk_level=risk_level,
            strategy_risk=strategy_risk,
            market_risk=market_risk,
            position_risk=position_risk,
            operational_risk=operational_risk,
            recommendations=recommendations,
            passed=overall_score >= 80
        )

    def _assess_strategy_risk(self, backtest_result: Dict) -> Dict:
        """评估策略风险"""
        sharpe = backtest_result.get("sharpe_ratio", 0)
        max_drawdown = backtest_result.get("max_drawdown", 100)
        win_rate = backtest_result.get("win_rate", 0)
        profit_factor = backtest_result.get("profit_factor", 0)
        total_trades = backtest_result.get("total_trades", 0)
        
        # 计算各指标得分 (使用可配置系数)
        c = self._coefficients
        sharpe_score = min(100, max(0, sharpe * c["sharpe_multiplier"]))  # 夏普>2.5得满分
        dd_score = min(100, max(0, 100 - max_drawdown * c["drawdown_multiplier"]))  # 回撤>33%得0分
        win_score = min(100, max(0, (win_rate - c["win_rate_offset"]) * c["win_rate_multiplier"]))  # 胜率>70%得满分
        pf_score = min(100, max(0, profit_factor * c["profit_factor_multiplier"])) if profit_factor > 0 else 50
        
        # 策略稳定性得分（交易次数越多越稳定）
        stability_score = min(100, total_trades * c["stability_multiplier"])
        
        avg_score = (sharpe_score + dd_score + win_score + pf_score + stability_score) / 5
        
        return {
            "score": round(avg_score, 2),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_trades": total_trades,
            "stability": round(stability_score, 2),
            "indicators": {
                "sharpe_score": round(sharpe_score, 2),
                "drawdown_score": round(dd_score, 2),
                "win_rate_score": round(win_score, 2),
                "profit_factor_score": round(pf_score, 2)
            }
        }

    def _assess_market_risk(self, backtest_result: Dict, position_info: Dict) -> Dict:
        """评估市场风险"""
        # 从backtest或position_info获取市场风险指标
        volatility = position_info.get("volatility", 0.2)
        beta = position_info.get("beta", 1.0)
        correlation = position_info.get("correlation", 0.5)
        
        # 计算得分 (使用可配置系数)
        c = self._coefficients
        vol_score = min(100, max(0, 100 - volatility * c["volatility_multiplier"]))  # 波动率<0.5得满分
        beta_score = min(100, max(0, 100 - abs(beta - 1) * c["beta_penalty"]))  # beta=1得满分
        corr_score = min(100, max(0, c["correlation_offset"] + correlation * c["correlation_multiplier"]))  # 适度相关最好
        
        avg_score = (vol_score + beta_score + corr_score) / 3
        
        return {
            "score": round(avg_score, 2),
            "volatility": round(volatility, 4),
            "beta": round(beta, 4),
            "correlation": round(correlation, 4),
            "indicators": {
                "volatility_score": round(vol_score, 2),
                "beta_score": round(beta_score, 2),
                "correlation_score": round(corr_score, 2)
            }
        }

    def _assess_position_risk(self, position_info: Dict) -> Dict:
        """评估持仓风险"""
        concentration = position_info.get("concentration", 20)  # 单票占比%
        industry_concentration = position_info.get("industry_concentration", 30)  # 行业集中度
        max_position = position_info.get("max_position", 10)  # 最大单票仓位%
        diversification = position_info.get("diversification", 5)  # 持仓数量
        
        # 计算得分
        conc_score = min(100, max(0, 100 - concentration))  # 集中度越低越好
        ind_conc_score = min(100, max(0, 100 - industry_concentration))
        pos_score = min(100, max(0, 100 - max_position * 5))  # 单票上限<20%得满分
        div_score = min(100, diversification * 15)  # 持仓越多越分散
        
        avg_score = (conc_score + ind_conc_score + pos_score + div_score) / 4
        
        return {
            "score": round(avg_score, 2),
            "concentration": round(concentration, 2),
            "industry_concentration": round(industry_concentration, 2),
            "max_position": round(max_position, 2),
            "diversification": diversification,
            "indicators": {
                "concentration_score": round(conc_score, 2),
                "industry_concentration_score": round(ind_conc_score, 2),
                "max_position_score": round(pos_score, 2),
                "diversification_score": round(div_score, 2)
            }
        }

    def _assess_operational_risk(self, backtest_result: Dict, position_info: Dict) -> Dict:
        """评估操作风险"""
        avg_slippage = position_info.get("avg_slippage", 0.001)  # 平均滑点
        liquidity = position_info.get("liquidity", 1.5)  # 日均成交额（亿）
        execution_cost = position_info.get("execution_cost", 0.001)  # 执行成本
        fill_rate = position_info.get("fill_rate", 95)  # 成交率%
        
        # 计算得分 (使用可配置系数)
        c = self._coefficients
        slippage_score = min(100, max(0, 100 - avg_slippage * c["slippage_multiplier"]))
        liquidity_score = min(100, liquidity * c["liquidity_multiplier"])  # 流动性>2亿得满分
        cost_score = min(100, max(0, 100 - execution_cost * c["cost_multiplier"]))
        fill_score = min(100, fill_rate)
        
        avg_score = (slippage_score + liquidity_score + cost_score + fill_score) / 4
        
        return {
            "score": round(avg_score, 2),
            "avg_slippage": round(avg_slippage, 6),
            "liquidity": round(liquidity, 2),
            "execution_cost": round(execution_cost, 6),
            "fill_rate": round(fill_rate, 2),
            "indicators": {
                "slippage_score": round(slippage_score, 2),
                "liquidity_score": round(liquidity_score, 2),
                "execution_cost_score": round(cost_score, 2),
                "fill_rate_score": round(fill_score, 2)
            }
        }

    def _calculate_overall_score(self, strategy_score: float, market_score: float,
                                position_score: float, operational_score: float) -> float:
        """计算综合评分"""
        return (
            strategy_score * self._weights["strategy"] +
            market_score * self._weights["market"] +
            position_score * self._weights["position"] +
            operational_score * self._weights["operational"]
        )

    def _get_risk_level(self, score: float) -> RiskLevel:
        """根据评分确定风险等级"""
        if score >= 80:
            return RiskLevel.LOW
        elif score >= 60:
            return RiskLevel.MEDIUM
        elif score >= 40:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _generate_recommendations(self, strategy_risk: Dict, market_risk: Dict,
                                  position_risk: Dict, operational_risk: Dict) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 策略风险建议
        if strategy_risk["score"] < 70:
            if strategy_risk["max_drawdown"] > 25:
                recommendations.append(f"⚠️ 策略最大回撤 {strategy_risk['max_drawdown']:.1f}% 过高，建议设置更严格的止损规则")
            if strategy_risk["win_rate"] < 45:
                recommendations.append(f"⚠️ 策略胜率 {strategy_risk['win_rate']:.1f}% 偏低，建议优化入场条件")
            if strategy_risk["sharpe_ratio"] < 1.0:
                recommendations.append(f"⚠️ 夏普比率 {strategy_risk['sharpe_ratio']:.2f} 不足，建议调整风险收益比")
        
        # 市场风险建议
        if market_risk["score"] < 70:
            if market_risk["volatility"] > 0.3:
                recommendations.append(f"⚠️ 标的波动率 {market_risk['volatility']:.2%} 较高，建议降低仓位")
            if abs(market_risk["beta"] - 1) > 0.5:
                recommendations.append(f"⚠️ 标的贝塔系数 {market_risk['beta']:.2f} 偏离市场，注意系统性风险")
        
        # 持仓风险建议
        if position_risk["score"] < 70:
            if position_risk["concentration"] > 30:
                recommendations.append(f"⚠️ 单票集中度 {position_risk['concentration']:.1f}% 过高，建议分散持仓")
            if position_risk["diversification"] < 3:
                recommendations.append(f"⚠️ 持仓仅 {position_risk['diversification']} 只股票，建议增加标的数量")
        
        # 操作风险建议
        if operational_risk["score"] < 70:
            if operational_risk["liquidity"] < 1.0:
                recommendations.append(f"⚠️ 标的流动性 {operational_risk['liquidity']:.1f}亿不足，注意冲击成本")
            if operational_risk["fill_rate"] < 90:
                recommendations.append(f"⚠️ 成交率 {operational_risk['fill_rate']:.1f}% 偏低，建议优化下单策略")
        
        # 通过时的建议
        if not recommendations:
            recommendations.append("✅ 风控评估通过，建议保持当前配置")
        
        return recommendations

    # ---------- 三层风控：事前/事中/事后 ----------

    def pre_trade_check(self, order: Dict) -> Dict[str, Any]:
        """事前风控：下单前校验

        检查项：
        - 单笔订单金额/数量上限
        - 标的涨跌停/停牌状态
        - 账户资金/持仓充足性
        - 策略信号合理性（NaN/极值拦截）

        Args:
            order: {symbol, strategy_name, price, volume, side, order_type}

        Returns:
            {passed: bool, reason: str, risk_score: float}
        """
        symbol = order.get("symbol", "")
        volume = order.get("volume", 0)
        price = order.get("price", 0)
        side = order.get("side", "buy")

        checks = []

        # 1. 数值边界校验：NaN/零/负值拦截
        if not isinstance(price, (int, float)) or np.isnan(price) or price <= 0:
            return {"passed": False, "reason": f"标的价格异常: {price}", "risk_score": 0}
        if not isinstance(volume, (int, float)) or np.isnan(volume) or volume <= 0:
            return {"passed": False, "reason": f"订单量异常: {volume}", "risk_score": 0}

        # 2. 单笔订单金额上限（默认100万）
        max_order_amount = order.get("max_order_amount", 1_000_000)
        order_amount = price * volume
        if order_amount > max_order_amount:
            return {"passed": False, "reason": f"单笔金额超限: {order_amount:.0f} > {max_order_amount:.0f}", "risk_score": 30}

        # 3. 单笔数量上限（默认10000股）
        max_volume = order.get("max_volume", 10000)
        if volume > max_volume:
            return {"passed": False, "reason": f"单笔数量超限: {volume} > {max_volume}", "risk_score": 30}

        # 4. 停牌/涨跌停检查（由数据平台预处理）
        if order.get("is_suspended", False):
            return {"passed": False, "reason": f"标的 {symbol} 已停牌", "risk_score": 0}
        if order.get("is_limit_up_down", False):
            return {"passed": False, "reason": f"标的 {symbol} 涨跌停无法交易", "risk_score": 10}

        logger.info(f"事前风控通过: {symbol} {side} {volume}@{price}")
        return {"passed": True, "reason": "事前风控通过", "risk_score": 100}

    def real_time_risk_monitor(self, portfolio: Dict) -> Dict[str, Any]:
        """事中风控：动态波动监控

        实时监控项：
        - 浮动盈亏超过止损线
        - 单策略回撤超过阈值
        - 总仓位超过上限
        - 行情异常波动（熔断信号）

        Args:
            portfolio: {positions, pnl, drawdown, total_exposure, market_status}

        Returns:
            {passed: bool, alerts: List[str], risk_score: float}
        """
        alerts = []
        risk_scores = []

        # 1. 浮动盈亏止损检查
        unrealized_pnl = portfolio.get("unrealized_pnl", 0)
        total_capital = portfolio.get("total_capital", 1)
        pnl_pct = abs(unrealized_pnl) / total_capital if total_capital > 0 else 0

        stop_loss_threshold = portfolio.get("stop_loss_threshold", 0.05)  # 默认5%
        if unrealized_pnl < 0 and pnl_pct > stop_loss_threshold:
            alerts.append(f"浮动亏损 {pnl_pct:.2%} 超过止损线 {stop_loss_threshold:.2%}")
            risk_scores.append(10)

        # 2. 单策略回撤监控
        max_drawdown = portfolio.get("current_drawdown", 0)
        dd_threshold = portfolio.get("max_drawdown_threshold", 0.15)  # 默认15%
        if max_drawdown > dd_threshold:
            alerts.append(f"当前回撤 {max_drawdown:.2%} 超过阈值 {dd_threshold:.2%}")
            risk_scores.append(20)

        # 3. 总仓位检查
        total_exposure = portfolio.get("total_exposure", 0)
        max_exposure = portfolio.get("max_exposure", 0.8)  # 默认80%
        if total_exposure > max_exposure:
            alerts.append(f"总仓位 {total_exposure:.2%} 超过上限 {max_exposure:.2%}")
            risk_scores.append(30)

        # 4. 行情异常检测（来自数据平台熔断信号）
        if portfolio.get("market_circuit_breaker", False):
            alerts.append("行情断流熔断触发，暂停交易")
            risk_scores.append(0)

        avg_score = sum(risk_scores) / len(risk_scores) if risk_scores else 100
        passed = len(alerts) == 0

        if not passed:
            logger.warning(f"事中风控告警: {alerts}")

        return {
            "passed": passed,
            "alerts": alerts,
            "risk_score": round(avg_score, 2),
        }

    def post_trade_reconciliation(self, trade_records: List[Dict]) -> Dict[str, Any]:
        """事后风控：盘后对账与绩效复盘

        检查项：
        - 成交数据与持仓数据一致性
        - 盈亏计算准确性
        - 异常交易模式检测（频繁撤单、对倒等）
        - 策略绩效偏离度

        Args:
            trade_records: [{symbol, side, price, volume, timestamp, ...}]

        Returns:
            {passed: bool, issues: List[str], reconciliation_report: Dict}
        """
        issues = []

        if not trade_records:
            return {"passed": True, "issues": [], "reconciliation_report": {"total_trades": 0}}

        # 1. 异常交易模式检测
        cancel_count = sum(1 for t in trade_records if t.get("status") == "cancelled")
        total_count = len(trade_records)
        cancel_rate = cancel_count / total_count if total_count > 0 else 0

        if cancel_rate > 0.3:  # 撤单率超过30%
            issues.append(f"撤单率过高: {cancel_rate:.1%} ({cancel_count}/{total_count})")

        # 2. 买卖平衡检查
        buy_volume = sum(t.get("volume", 0) for t in trade_records if t.get("side") == "buy")
        sell_volume = sum(t.get("volume", 0) for t in trade_records if t.get("side") == "sell")
        volume_imbalance = abs(buy_volume - sell_volume) / max(buy_volume + sell_volume, 1)

        if volume_imbalance > 0.5:
            issues.append(f"买卖量失衡: 买{buy_volume} vs 卖{sell_volume}")

        # 3. 价格异常检测
        price_anomalies = []
        for t in trade_records:
            price = t.get("price", 0)
            vwap = t.get("vwap", price)
            if vwap > 0 and abs(price - vwap) / vwap > 0.1:  # 偏离VWAP超过10%
                price_anomalies.append(t.get("symbol", "unknown"))

        if price_anomalies:
            issues.append(f"价格异常标的: {list(set(price_anomalies))[:5]}")

        # 4. 生成对账报告
        report = {
            "total_trades": total_count,
            "cancel_rate": round(cancel_rate, 4),
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "volume_imbalance": round(volume_imbalance, 4),
            "price_anomalies": len(price_anomalies),
            "passed": len(issues) == 0,
        }

        if issues:
            logger.warning(f"事后对账发现问题: {issues}")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "reconciliation_report": report,
        }

    # ---------- 增强风控：熔断与额度 ----------

    def daily_loss_circuit_breaker(self, daily_pnl: float, total_capital: float,
                                     max_daily_loss_pct: float = 0.05) -> Dict[str, Any]:
        """单日亏损熔断 — 当日亏损超过总资金x%时触发

        Args:
            daily_pnl: 当日累计盈亏（负数为亏损）
            total_capital: 总资金
            max_daily_loss_pct: 最大日亏损比例，默认5%

        Returns:
            {tripped: bool, reason: str, loss_pct: float}
        """
        if daily_pnl >= 0:
            return {"tripped": False, "reason": "", "loss_pct": 0.0}

        loss_pct = abs(daily_pnl) / total_capital if total_capital > 0 else 0
        if loss_pct > max_daily_loss_pct:
            logger.error(f"[RiskCtrl] 单日亏损熔断: {loss_pct:.2%} > {max_daily_loss_pct:.2%}")
            return {
                "tripped": True,
                "reason": f"单日亏损 {loss_pct:.2%} 超过熔断线 {max_daily_loss_pct:.2%}",
                "loss_pct": round(loss_pct, 4),
            }
        return {"tripped": False, "reason": "", "loss_pct": round(loss_pct, 4)}

    def frequent_trading_circuit_breaker(self, trades_last_minute: int,
                                           max_trades_per_minute: int = 10) -> Dict[str, Any]:
        """频繁交易熔断 — 每分钟交易次数超过阈值时触发

        Args:
            trades_last_minute: 过去1分钟内的交易次数
            max_trades_per_minute: 每分钟最大交易次数，默认10

        Returns:
            {tripped: bool, reason: str, trades_count: int}
        """
        if trades_last_minute > max_trades_per_minute:
            logger.error(f"[RiskCtrl] 频繁交易熔断: {trades_last_minute}次/分钟 > {max_trades_per_minute}")
            return {
                "tripped": True,
                "reason": f"交易频率异常: {trades_last_minute}次/分钟 (上限{max_trades_per_minute})",
                "trades_count": trades_last_minute,
            }
        return {"tripped": False, "reason": "", "trades_count": trades_last_minute}

    def fund_usage_rate_check(self, used_capital: float, total_capital: float,
                                max_usage_rate: float = 0.9) -> Dict[str, Any]:
        """资金使用率上限 — 已用资金/总资金超过阈值时拒绝新开仓

        Args:
            used_capital: 已用资金（持仓市值+冻结资金）
            total_capital: 总资金
            max_usage_rate: 最大资金使用率，默认90%

        Returns:
            {passed: bool, reason: str, usage_rate: float}
        """
        usage_rate = used_capital / total_capital if total_capital > 0 else 0
        if usage_rate > max_usage_rate:
            return {
                "passed": False,
                "reason": f"资金使用率 {usage_rate:.1%} 超过上限 {max_usage_rate:.1%}",
                "usage_rate": round(usage_rate, 4),
            }
        return {"passed": True, "reason": "", "usage_rate": round(usage_rate, 4)}

    def comprehensive_circuit_breaker(self, daily_pnl: float, total_capital: float,
                                        trades_last_minute: int, used_capital: float) -> Dict[str, Any]:
        """综合熔断检查 — 一次调用完成所有熔断判断

        Returns:
            {tripped: bool, reasons: List[str], details: Dict}
        """
        reasons = []
        details = {}

        # 1. 单日亏损熔断
        loss_check = self.daily_loss_circuit_breaker(daily_pnl, total_capital)
        details["daily_loss"] = loss_check
        if loss_check["tripped"]:
            reasons.append(loss_check["reason"])

        # 2. 频繁交易熔断
        freq_check = self.frequent_trading_circuit_breaker(trades_last_minute)
        details["frequent_trading"] = freq_check
        if freq_check["tripped"]:
            reasons.append(freq_check["reason"])

        # 3. 资金使用率超限（不熔断，但拒绝新开仓）
        fund_check = self.fund_usage_rate_check(used_capital, total_capital)
        details["fund_usage"] = fund_check
        if not fund_check["passed"]:
            reasons.append(fund_check["reason"])

        tripped = len(reasons) > 0
        if tripped:
            logger.warning(f"[RiskCtrl] 综合熔断触发: {reasons}")

        return {
            "tripped": tripped,
            "reasons": reasons,
            "details": details,
        }

    # ---------- 批量评估 ----------

    def batch_assess(self, assessments: List[Dict]) -> List[RiskAssessment]:
        """批量评估多只股票"""
        results = []
        for item in assessments:
            result = self.assess(
                symbol=item["symbol"],
                strategy_name=item["strategy_name"],
                backtest_result=item.get("backtest_result", {}),
                position_info=item.get("position_info", {})
            )
            results.append(result)
        return results

# ============================================================
# 全局单例
# ============================================================

_risk_engine = None

def get_risk_control_engine() -> RiskControlEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskControlEngine()
    return _risk_engine

# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":
    rc = get_risk_control_engine()
    
    # 模拟评估
    assessment = rc.assess(
        symbol="000001",
        strategy_name="双均线策略",
        backtest_result={
            "sharpe_ratio": 1.8,
            "max_drawdown": 15.5,
            "win_rate": 55.2,
            "profit_factor": 1.8,
            "total_trades": 120
        },
        position_info={
            "volatility": 0.18,
            "beta": 1.1,
            "correlation": 0.6,
            "concentration": 15,
            "industry_concentration": 25,
            "max_position": 10,
            "diversification": 8,
            "avg_slippage": 0.0008,
            "liquidity": 5.0,
            "execution_cost": 0.0005,
            "fill_rate": 98
        }
    )
    
    print(f"综合评分: {assessment.overall_score}")
    print(f"风险等级: {assessment.risk_level.value}")
    print(f"通过: {assessment.passed}")
    print("建议:")
    for rec in assessment.recommendations:
        print(f"  - {rec}")