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
        
        # 计算各指标得分
        sharpe_score = min(100, max(0, sharpe * 40))  # 夏普>2.5得满分
        dd_score = min(100, max(0, 100 - max_drawdown * 3))  # 回撤>33%得0分
        win_score = min(100, max(0, (win_rate - 30) * 2.5))  # 胜率>70%得满分
        pf_score = min(100, max(0, profit_factor * 50)) if profit_factor > 0 else 50
        
        # 策略稳定性得分（交易次数越多越稳定）
        stability_score = min(100, total_trades * 0.5)
        
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
        
        # 计算得分
        vol_score = min(100, max(0, 100 - volatility * 200))  # 波动率<0.5得满分
        beta_score = min(100, max(0, 100 - abs(beta - 1) * 50))  # beta=1得满分
        corr_score = min(100, max(0, 50 + correlation * 50))  # 适度相关最好
        
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
        
        # 计算得分
        slippage_score = min(100, max(0, 100 - avg_slippage * 50000))
        liquidity_score = min(100, liquidity * 50)  # 流动性>2亿得满分
        cost_score = min(100, max(0, 100 - execution_cost * 50000))
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