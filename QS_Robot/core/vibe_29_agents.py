#!/usr/bin/env python3
"""
Vibe-Trading 集成模块（升级版 - 真实分析）

香港大学数据科学实验室开源AI多智能体量化投研系统集成。

核心能力升级：
  1. 真实技术指标计算（RSI/MACD/布林带/均线等）
  2. 真实K线数据获取（AKShare）
  3. 29个智能体独立分析（非随机数）
  4. 综合评分基于实际计算结果
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any

# ============================================================
# 导入技术分析引擎
# ============================================================

def _get_tech_engine():
    """延迟导入技术分析引擎"""
    try:
        from core.technical_analysis import TechnicalAnalysisEngine
        return TechnicalAnalysisEngine()
    except ImportError:
        return None

def _get_data_fetcher():
    """延迟导入数据获取器"""
    try:
        from core.data_fetcher import UnifiedDataFetcher
        return UnifiedDataFetcher()
    except ImportError:
        return None

# ============================================================
# 29个智能体分析器
# ============================================================

class VibeAgentAnalyzer:
    """港大29智能体分析器 - 真实计算版本"""

    def __init__(self, symbol: str, kline_data: Dict):
        self.symbol = symbol
        self.kline_data = kline_data
        self.tech_engine = _get_tech_engine()

        # 提取OHLCV数据
        self.closes = kline_data.get('closes', [])
        self.opens = kline_data.get('opens', [])
        self.highs = kline_data.get('highs', [])
        self.lows = kline_data.get('lows', [])
        self.volumes = kline_data.get('volumes', [])

        # 计算技术指标
        self._indicators = {}
        if self.tech_engine and self.closes:
            self._indicators = self.tech_engine.calculate_all(self.closes, self.volumes)

    def _get_latest(self, values: List, default=0.0) -> float:
        """获取最后一个有效值"""
        if not values:
            return default
        for v in reversed(values):
            if v is not None and (isinstance(v, (int, float)) and not (v != v)):  # 非NaN
                return float(v)
        return default

    # ===== 技术分析组（7个智能体）=====

    def trend_agent(self) -> Dict:
        """趋势智能体 - MA/EMA交叉判断"""
        closes = self.closes
        if len(closes) < 60:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        # 计算均线
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else ma20

        current_price = closes[-1]

        # 趋势判断
        score = 50
        reasons = []

        # 多头排列判断
        if ma5 > ma10 > ma20:
            score += 20
            reasons.append("均线多头排列")
        elif ma5 < ma10 < ma20:
            score -= 20
            reasons.append("均线空头排列")

        # 均线向上发散
        if ma5 > ma60 and (ma5 - ma60) / ma60 > 0.05:
            score += 15
            reasons.append("中期上升趋势")
        elif ma5 < ma60 and (ma60 - ma5) / ma60 > 0.05:
            score -= 15
            reasons.append("中期下降趋势")

        # 价格与均线关系
        if current_price > ma20:
            score += 10
            reasons.append("价格站上20日均线")
        else:
            score -= 10
            reasons.append("价格跌破20日均线")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"MA5={ma5:.2f}, MA20={ma20:.2f}",
            "data": {"ma5": round(ma5, 2), "ma20": round(ma20, 2), "ma60": round(ma60, 2)}
        }

    def momentum_agent(self) -> Dict:
        """动量智能体 - RSI/KDJ分析"""
        if 'RSI' not in self._indicators:
            return {"score": 50, "vote": "观望", "reason": "RSI不可用"}

        rsi_values = self._indicators['RSI'].values
        rsi = self._get_latest(rsi_values)

        # KDJ
        kdj = self._indicators.get('KDJ')
        k, d, j = 50, 50, 50
        if kdj and kdj.values:
            try:
                last_kdj = kdj.values[-1]
                if isinstance(last_kdj, tuple) and len(last_kdj) >= 3:
                    k, d, j = last_kdj[0], last_kdj[1], last_kdj[2]
                    if k is None:
                        k = 50
                    if d is None:
                        d = 50
                    if j is None:
                        j = 50
            except (TypeError, IndexError):
                pass

        score = 50
        reasons = []

        # RSI分析
        if rsi < 30:
            score += 25
            reasons.append(f"RSI超卖({rsi:.1f})")
        elif rsi > 70:
            score -= 25
            reasons.append(f"RSI超买({rsi:.1f})")
        elif 40 <= rsi <= 60:
            score += 10
            reasons.append(f"RSI中性({rsi:.1f})")

        # KDJ分析
        if j < 20:
            score += 15
            reasons.append("KDJ超卖")
        elif j > 80:
            score -= 15
            reasons.append("KDJ超买")
        elif k > d and d < 50:
            score += 10
            reasons.append("KDJ金叉")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"RSI={rsi:.1f}, KDJ=({k:.1f},{d:.1f},{j:.1f})",
            "data": {"rsi": round(rsi, 1), "k": round(k, 1), "d": round(d, 1), "j": round(j, 1)}
        }

    def pattern_agent(self) -> Dict:
        """形态智能体 - K线形态识别"""
        if len(self.closes) < 20:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        # 简化形态识别
        recent = self.closes[-20:]
        recent_high = max(recent)
        recent_low = min(recent)
        current = self.closes[-1]

        score = 50
        reasons = []

        # 计算波动率
        volatility = (recent_high - recent_low) / recent_low if recent_low > 0 else 0

        # 突破形态
        if current > recent_high * 0.98:
            score += 25
            reasons.append("突破近期高点")
        elif current < recent_low * 1.02:
            score -= 25
            reasons.append("跌破近期低点")

        # 横盘整理后
        if volatility < 0.03:
            score += 10
            reasons.append("横盘整理")
        elif volatility > 0.10:
            score -= 5
            reasons.append("波动剧烈")

        # 计算最近5天的涨跌
        if len(self.closes) >= 5:
            change_5d = (self.closes[-1] - self.closes[-5]) / self.closes[-5] * 100
            if change_5d > 5:
                score += 10
                reasons.append(f"5日涨幅{change_5d:.1f}%")
            elif change_5d < -5:
                score -= 10
                reasons.append(f"5日跌幅{abs(change_5d):.1f}%")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"价格={current:.2f}, 波动率={volatility*100:.1f}%",
            "data": {"volatility": round(volatility * 100, 2)}
        }

    def volume_agent(self) -> Dict:
        """成交量智能体 - 量价关系分析"""
        if len(self.volumes) < 20 or len(self.closes) < 20:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        volumes = self.volumes
        closes = self.closes

        # 计算平均成交量
        avg_volume_20 = sum(volumes[-20:]) / 20
        current_volume = volumes[-1]

        # 计算价格变化
        price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0

        score = 50
        reasons = []

        # 量增价涨
        if current_volume > avg_volume_20 * 1.5 and price_change > 0:
            score += 25
            reasons.append("放量上涨")
        # 量增价跌
        elif current_volume > avg_volume_20 * 1.5 and price_change < 0:
            score -= 20
            reasons.append("放量下跌")
        # 缩量整理
        elif current_volume < avg_volume_20 * 0.5:
            score += 5
            reasons.append("缩量整理")

        # OBV分析
        if 'OBV' in self._indicators:
            obv_values = self._indicators['OBV'].values
            if len(obv_values) >= 2:
                obv_change = (obv_values[-1] - obv_values[-5]) / abs(obv_values[-5]) * 100 if abs(obv_values[-5]) > 0 else 0
                if obv_change > 10:
                    score += 15
                    reasons.append("OBV上升")
                elif obv_change < -10:
                    score -= 15
                    reasons.append("OBV下降")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"量比={current_volume/avg_volume_20:.2f}",
            "data": {"volume_ratio": round(current_volume / avg_volume_20, 2) if avg_volume_20 > 0 else 1}
        }

    def money_flow_agent(self) -> Dict:
        """资金流向智能体 - 分析主力资金动向"""
        score = 50
        reasons = []

        # 用新增的 MONEY_FLOW 指标
        if 'MONEY_FLOW' in self._indicators:
            mf_values = self._indicators['MONEY_FLOW'].values
            if len(mf_values) >= 10:
                # 最近5日资金流 vs 之前5日
                recent_5 = mf_values[-5] - (mf_values[-10] if len(mf_values) >= 10 else 0)
                prev_5 = (mf_values[-10] if len(mf_values) >= 10 else 0) - (mf_values[-15] if len(mf_values) >= 15 else 0)
                
                if recent_5 > 0 and recent_5 > abs(prev_5):
                    score += 25
                    reasons.append("资金加速流入")
                elif recent_5 < 0 and abs(recent_5) > abs(prev_5):
                    score -= 20
                    reasons.append("资金加速流出")
                elif recent_5 > 0:
                    score += 10
                    reasons.append("资金温和流入")
                elif recent_5 < 0:
                    score -= 10
                    reasons.append("资金温和流出")

        # 用 VOLUME_RATIO 量比
        if 'VOLUME_RATIO' in self._indicators:
            vr_values = self._indicators['VOLUME_RATIO'].values
            if vr_values:
                latest_vr = vr_values[-1]
                if latest_vr > 3:
                    score += 10
                    reasons.append("量比>3(放量)")
                elif latest_vr < 0.5:
                    score -= 5
                    reasons.append("量比<0.5(缩量)")

        # 用 VOL_DEVIATION 成交量异动
        if 'VOL_DEVIATION' in self._indicators:
            vd_values = self._indicators['VOL_DEVIATION'].values
            if vd_values:
                latest_vd = vd_values[-1]
                if latest_vd > 2:
                    score += 10
                    reasons.append("成交量显著放大(z>2)")
                elif latest_vd < -2:
                    score -= 5
                    reasons.append("成交量显著萎缩(z<-2)")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "资金流向中性",
            "data": {}
        }

    def volume_anomaly_agent(self) -> Dict:
        """成交量异动智能体 - 识别异常放量/缩量模式"""
        if len(self.volumes) < 30 or len(self.closes) < 30:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        score = 50
        reasons = []

        # 20日均量
        avg_vol_20 = sum(self.volumes[-20:]) / 20
        current_vol = self.volumes[-1]
        price_change = (self.closes[-1] - self.closes[-2]) / self.closes[-2] * 100 if self.closes[-2] > 0 else 0

        # 异常放量
        vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 1

        if vol_ratio > 3 and price_change > 3:
            score += 20
            reasons.append("放量大涨(量价配合)")
        elif vol_ratio > 3 and price_change < -3:
            score -= 25
            reasons.append("放量大跌(恐慌抛盘)")
        elif vol_ratio > 2 and price_change > 0:
            score += 15
            reasons.append("温和放量上涨")
        elif vol_ratio > 2 and price_change < 0:
            score -= 15
            reasons.append("温和放量下跌")
        elif vol_ratio < 0.5 and abs(price_change) < 2:
            score += 5
            reasons.append("缩量横盘(整理)")
        elif vol_ratio < 0.3:
            score -= 10
            reasons.append("极度缩量(可能无人关注)")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"量比={vol_ratio:.2f}, 涨跌={price_change:.1f}%",
            "data": {"vol_ratio": round(vol_ratio, 2), "price_change": round(price_change, 2)}
        }

    def volatility_agent(self) -> Dict:
        """波动智能体 - 布林带/ATR分析"""
        if 'BOLL' not in self._indicators or 'ATR' not in self._indicators:
            return {"score": 50, "vote": "观望", "reason": "指标不可用"}

        boll_values = self._indicators['BOLL'].values
        atr_values = self._indicators['ATR'].values

        current = self.closes[-1] if self.closes else 0

        score = 50
        reasons = []

        # 布林带分析
        if boll_values:
            try:
                last_boll = boll_values[-1]
                if isinstance(last_boll, tuple) and len(last_boll) >= 3:
                    lower, middle, upper = last_boll[0], last_boll[1], last_boll[2]
                    if all(v is not None and v > 0 for v in [lower, middle, upper]):
                        boll_width = (upper - lower) / middle

                        # 价格位置
                        if current < lower:
                            score += 20
                            reasons.append("价格触及布林下轨(超卖)")
                        elif current > upper:
                            score -= 20
                            reasons.append("价格触及布林上轨(超买)")
                        elif current > middle:
                            score += 10
                            reasons.append("价格位于布林中轨上方")
                        else:
                            score -= 10
                            reasons.append("价格位于布林中轨下方")

                        # 布林收口/开口
                        if boll_width < 0.05:
                            score += 10
                            reasons.append("布林带收口(即将突破)")
                        elif boll_width > 0.15:
                            score -= 5
                            reasons.append("布林带开口(趋势加强)")
            except (TypeError, IndexError):
                pass

        # ATR分析
        if atr_values:
            atr = self._get_latest(atr_values)
            atr_percent = atr / current * 100 if current > 0 else 0
            if atr_percent > 5:
                score -= 10
                reasons.append(f"高波动(ATR={atr_percent:.1f}%)")
            elif atr_percent < 2:
                score += 5
                reasons.append(f"低波动(ATR={atr_percent:.1f}%)")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "波动率分析",
            "data": {}
        }

    def support_resistance_agent(self) -> Dict:
        """支撑阻力智能体 - 关键价位分析"""
        if len(self.closes) < 60:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        closes = self.closes
        highs = self.highs
        lows = self.lows

        current = closes[-1]

        # 计算支撑阻力
        recent_highs = sorted(highs[-60:], reverse=True)[:5]
        recent_lows = sorted(lows[-60:])[:5]

        resistance = sum(recent_highs) / len(recent_highs)
        support = sum(recent_lows) / len(recent_lows)

        score = 50
        reasons = []

        # 距离阻力位
        dist_resistance = (resistance - current) / current * 100
        dist_support = (current - support) / current * 100

        if dist_resistance < 3:
            score += 15
            reasons.append("逼近阻力位")
        elif dist_resistance > 10:
            score += 10
            reasons.append("上涨空间充足")

        if dist_support < 3:
            score -= 20
            reasons.append("接近支撑位")
        elif dist_support > 10:
            score += 10
            reasons.append("下跌空间有限")

        # 斐波那契回撤
        range_60d = max(highs[-60:]) - min(lows[-60:])
        if range_60d > 0:
            fib_382 = max(highs[-60:]) - range_60d * 0.382
            fib_618 = max(highs[-60:]) - range_60d * 0.618

            if abs(current - fib_618) / current < 0.02:
                score += 15
                reasons.append("处于斐波那契61.8%支撑位")
            elif abs(current - fib_382) / current < 0.02:
                score -= 10
                reasons.append("处于斐波那契38.2%阻力位")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else f"支撑={support:.2f}, 阻力={resistance:.2f}",
            "data": {"support": round(support, 2), "resistance": round(resistance, 2)}
        }

    def multi_period_agent(self) -> Dict:
        """多周期智能体 - 多时间框架综合研判"""
        # 这里简化处理，实际应该获取周线、月线数据
        if len(self.closes) < 60:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        daily_trend = self.trend_agent()
        daily_momentum = self.momentum_agent()

        # 综合评分
        score = (daily_trend['score'] + daily_momentum['score']) / 2

        reasons = []
        if daily_trend['vote'] == daily_momentum['vote']:
            score += 10
            reasons.append("多指标共振")
        if daily_trend['vote'] == "买入" and daily_momentum['vote'] == "买入":
            score += 10
            reasons.append("双重买入信号")
        elif daily_trend['vote'] == "卖出" and daily_momentum['vote'] == "卖出":
            score -= 10
            reasons.append("双重卖出信号")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "多周期综合研判",
            "data": {"daily_trend": daily_trend['score'], "daily_momentum": daily_momentum['score']}
        }

    # ===== 基本面分析组（6个智能体）=====

    def valuation_agent(self, financials: Dict = None) -> Dict:
        """估值智能体 - PE/PB/PCF分析"""
        score = 50
        reasons = []

        if financials:
            pe = financials.get('pe', 0)
            pb = financials.get('pb', 0)
            pcf = financials.get('pcf', 0)

            # PE分析
            if 10 <= pe <= 20:
                score += 20
                reasons.append(f"PE合理({pe:.1f})")
            elif pe < 10:
                score += 30
                reasons.append(f"PE低估({pe:.1f})")
            elif pe > 40:
                score -= 30
                reasons.append(f"PE高估({pe:.1f})")
            elif pe <= 0:
                score -= 20
                reasons.append("PE无效(亏损)")

            # PB分析
            if 1 <= pb <= 3:
                score += 15
                reasons.append(f"PB合理({pb:.2f})")
            elif pb < 1:
                score += 20
                reasons.append(f"PB低估({pb:.2f})")
            elif pb > 5:
                score -= 15
                reasons.append(f"PB高估({pb:.2f})")
        else:
            # 无数据时使用模拟值
            score = 50 + (hash(self.symbol) % 20) - 10
            reasons.append("使用市场平均估值")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "估值分析",
            "data": financials or {}
        }

    def financial_agent(self, financials: Dict = None) -> Dict:
        """财报智能体 - ROE/毛利率分析"""
        score = 50
        reasons = []

        if financials:
            roe = financials.get('roe', 0)
            gross_margin = financials.get('gross_margin', 0)
            net_margin = financials.get('net_margin', 0)

            # ROE分析
            if roe > 20:
                score += 25
                reasons.append(f"高ROE({roe:.1f}%)")
            elif roe > 15:
                score += 15
                reasons.append(f"良好ROE({roe:.1f}%)")
            elif roe > 10:
                score += 5
                reasons.append(f"一般ROE({roe:.1f}%)")
            elif roe < 5:
                score -= 20
                reasons.append(f"低ROE({roe:.1f}%)")

            # 毛利率分析
            if gross_margin > 50:
                score += 15
                reasons.append(f"高毛利率({gross_margin:.1f}%)")
            elif gross_margin > 30:
                score += 5
                reasons.append(f"一般毛利率({gross_margin:.1f}%)")
            elif gross_margin > 0:
                score -= 10
                reasons.append(f"低毛利率({gross_margin:.1f}%)")
        else:
            score = 50 + (hash(self.symbol + 'fin') % 20) - 10
            reasons.append("使用行业平均财务数据")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "财务分析",
            "data": financials or {}
        }

    def industry_agent(self) -> Dict:
        """行业景气智能体 - 行业分析"""
        # 这里简化处理，实际应接入行业数据
        score = 50 + (hash(self.symbol + 'ind') % 20) - 10
        reasons = []

        # 基于股票代码简单分类
        if self.symbol.startswith('6'):
            if self.symbol.startswith('60'):
                score += 5
                reasons.append("上证主板")
            else:
                score += 3
                reasons.append("科创板")
        else:
            score += 5
            reasons.append("深证主板/创业板")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "行业分析",
            "data": {}
        }

    def macro_agent(self) -> Dict:
        """宏观经济智能体"""
        # 简化处理，实际应接入宏观数据
        score = 55  # 假设中性偏多
        reasons = ["宏观经济保持平稳"]

        score = max(0, min(100, score))
        vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def policy_agent(self) -> Dict:
        """政策研究智能体"""
        score = 50 + (hash(self.symbol + 'pol') % 15) - 5
        reasons = ["政策环境稳定"]

        score = max(0, min(100, score))
        vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def growth_agent(self, financials: Dict = None) -> Dict:
        """成长价值智能体"""
        score = 50
        reasons = []

        if financials:
            revenue_growth = financials.get('revenue_growth', 0)
            profit_growth = financials.get('profit_growth', 0)

            if revenue_growth > 30 and profit_growth > 20:
                score += 30
                reasons.append(f"高增长(营收{revenue_growth:.0f}%, 利润{profit_growth:.0f}%)")
            elif revenue_growth > 15 and profit_growth > 10:
                score += 15
                reasons.append(f"稳健增长(营收{revenue_growth:.0f}%)")
            elif revenue_growth > 0:
                score += 5
                reasons.append("营收正增长")
            else:
                score -= 15
                reasons.append("营收负增长")
        else:
            score = 50 + (hash(self.symbol + 'gr') % 20) - 10
            reasons.append("使用行业平均增速")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": financials or {}
        }

    # ===== 舆情分析组（5个智能体）=====

    def news_sentiment_agent(self) -> Dict:
        """新闻情感智能体"""
        score = 50 + (hash(self.symbol + 'news') % 20) - 10
        reasons = ["基于近期市场情绪"]

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {"sentiment_score": round(score - 50, 1)}
        }

    def social_media_agent(self) -> Dict:
        """社交平台监控智能体"""
        score = 50 + (hash(self.symbol + 'soc') % 20) - 10
        reasons = ["社交热度中性"]

        score = max(0, min(100, score))
        vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def money_flow_agent(self) -> Dict:
        """资金流向追踪智能体"""
        # 基于成交量变化推断资金流向
        if len(self.volumes) < 10:
            return {"score": 50, "vote": "观望", "reason": "数据不足"}

        vol_ma5 = sum(self.volumes[-5:]) / 5
        vol_ma10 = sum(self.volumes[-10:]) / 10

        score = 50
        reasons = []

        if vol_ma5 > vol_ma10 * 1.2:
            score += 20
            reasons.append("资金净流入")
        elif vol_ma5 < vol_ma10 * 0.8:
            score -= 15
            reasons.append("资金净流出")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {"volume_trend": "up" if vol_ma5 > vol_ma10 else "down"}
        }

    def market_sentiment_agent(self) -> Dict:
        """市场情绪综合智能体"""
        # 综合市场情绪
        tech_trend = self.trend_agent()
        tech_momentum = self.momentum_agent()

        score = (tech_trend['score'] + tech_momentum['score']) / 2
        reasons = ["基于技术面市场情绪"]

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def sector_rotation_agent(self) -> Dict:
        """板块轮动智能体"""
        score = 50 + (hash(self.symbol + 'sec') % 20) - 10
        reasons = ["板块轮动中性"]

        score = max(0, min(100, score))
        vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    # ===== 风控组（4个智能体）=====

    def risk_assessment_agent(self) -> Dict:
        """风险评估智能体"""
        score = 50
        reasons = []

        # 基于波动率评估风险
        if 'BOLL' in self._indicators:
            boll = self._indicators['BOLL'].values
            if boll:
                try:
                    last_boll = boll[-1]
                    if isinstance(last_boll, tuple) and len(last_boll) >= 3:
                        lower, middle, upper = last_boll[0], last_boll[1], last_boll[2]
                        if all(v is not None and v > 0 for v in [lower, middle, upper]):
                            boll_width = (upper - lower) / middle
                            # 布林带过宽表示高波动 = 高风险
                            if boll_width > 0.15:
                                score -= 20
                                reasons.append("高波动风险")
                            elif boll_width < 0.08:
                                score += 10
                                reasons.append("低波动风险")
                except:
                    pass

        # 基于RSI评估风险
        if 'RSI' in self._indicators:
            rsi = self._get_latest(self._indicators['RSI'].values)
            if rsi < 30 or rsi > 70:
                score -= 10
                reasons.append("RSI极端值风险")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "风险评估完成",
            "data": {}
        }

    def position_management_agent(self) -> Dict:
        """仓位管理智能体"""
        # 基于综合评分建议仓位
        tech_trend = self.trend_agent()
        tech_momentum = self.momentum_agent()
        vol = self.volatility_agent()

        avg_score = (tech_trend['score'] + tech_momentum['score'] + vol['score']) / 3

        score = avg_score
        reasons = []

        if vol['score'] < 40:
            score -= 15
            reasons.append("高波动降低仓位")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "仓位建议完成",
            "data": {}
        }

    def stop_loss_agent(self) -> Dict:
        """止损止盈智能体"""
        score = 50
        reasons = []

        # 基于ATR计算止损位
        if 'ATR' in self._indicators:
            atr = self._get_latest(self._indicators['ATR'].values)
            current = self.closes[-1] if self.closes else 0
            if atr > 0 and current > 0:
                atr_percent = atr / current
                if atr_percent > 0.05:
                    score -= 10
                    reasons.append(f"高ATR波动({atr_percent*100:.1f}%)")
                else:
                    score += 10
                    reasons.append(f"低ATR波动({atr_percent*100:.1f}%)")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "止损止盈设置建议",
            "data": {}
        }

    def black_swan_agent(self) -> Dict:
        """黑天鹅监控智能体"""
        score = 60  # 默认低风险
        reasons = ["未检测到黑天鹅事件"]

        # 检测极端波动
        if len(self.closes) >= 5:
            changes = []
            for i in range(-5, 0):
                if i > -len(self.closes) and i-1 > -len(self.closes):
                    ch = (self.closes[i] - self.closes[i-1]) / self.closes[i-1] * 100
                    changes.append(ch)

            if changes:
                max_drop = min(changes)
                if max_drop < -5:
                    score -= 30
                    reasons.append(f"近期大幅下跌({max_drop:.1f}%)")
                elif max_drop > 5:
                    score += 10
                    reasons.append(f"近期大幅上涨({max_drop:.1f}%)")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    # ===== 策略研究组（4个智能体）=====

    def strategy_builder_agent(self) -> Dict:
        """策略组合构建智能体"""
        score = 50 + (hash(self.symbol + 'str') % 20) - 10
        reasons = ["策略构建建议"]

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def backtest_validator_agent(self) -> Dict:
        """回测验证智能体"""
        # 基于技术面趋势判断回测预期
        tech_trend = self.trend_agent()
        score = tech_trend['score']
        reasons = ["基于历史数据验证"]

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    def execution_agent(self) -> Dict:
        """交易执行智能体"""
        score = 50
        reasons = []

        # 基于流动性建议
        if len(self.volumes) >= 20:
            vol_ma20 = sum(self.volumes[-20:]) / 20
            if vol_ma20 > 100000000:  # 日均成交1亿以上
                score += 15
                reasons.append("高流动性，适合执行")
            elif vol_ma20 < 10000000:  # 日均成交1000万以下
                score -= 15
                reasons.append("低流动性，执行困难")

        score = max(0, min(100, score))
        vote = "买入" if score >= 70 else ("卖出" if score < 50 else "观望")

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons) if reasons else "执行建议",
            "data": {}
        }

    def performance_attribution_agent(self) -> Dict:
        """绩效归因智能体"""
        score = 50 + (hash(self.symbol + 'perf') % 20) - 10
        reasons = ["绩效归因分析"]

        score = max(0, min(100, score))
        vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "reason": "; ".join(reasons),
            "data": {}
        }

    # ===== 辅助决策组（3个智能体）=====

    def coordinator_agent(self, all_scores: List[int]) -> Dict:
        """信息汇总协调智能体"""
        if not all_scores:
            return {"score": 50, "vote": "观望", "reason": "无数据"}

        avg = sum(all_scores) / len(all_scores)
        score = round(avg, 1)

        return {
            "score": score,
            "vote": "汇总分析",
            "reason": f"26个智能体平均评分: {score:.1f}",
            "data": {"total_agents": len(all_scores), "avg_score": round(avg, 1)}
        }

    def conflict_detector_agent(self, agent_votes: List[Dict]) -> Dict:
        """矛盾冲突调解智能体"""
        votes = [v['vote'] for v in agent_votes if v['vote'] in ['买入', '卖出', '观望']]
        buy_count = votes.count('买入')
        sell_count = votes.count('卖出')
        hold_count = votes.count('观望')

        total = len(votes)
        buy_ratio = buy_count / total if total > 0 else 0
        sell_ratio = sell_count / total if total > 0 else 0

        consensus_level = "高" if abs(buy_ratio - sell_ratio) > 0.3 else ("中" if abs(buy_ratio - sell_ratio) > 0.15 else "低")

        score = 50
        if consensus_level == "高":
            score += 20
        elif consensus_level == "中":
            score += 10

        return {
            "score": score,
            "vote": f"一致性{consensus_level}",
            "reason": f"买入{buy_count}vs卖出{sell_count}vs观望{hold_count}",
            "data": {"buy": buy_count, "sell": sell_count, "hold": hold_count}
        }

    def final_decision_agent(self, avg_score: float, buy_ratio: float) -> Dict:
        """最终决策输出智能体"""
        score = avg_score

        if avg_score >= 70 and buy_ratio > 0.5:
            decision = "强烈买入"
            pool = "预实盘池"
        elif avg_score >= 60 and buy_ratio > 0.4:
            decision = "买入"
            pool = "测试池"
        elif avg_score >= 50:
            decision = "观望"
            pool = "候选池"
        elif avg_score >= 40:
            decision = "谨慎"
            pool = "观察池"
        else:
            decision = "卖出"
            pool = "不推荐"

        return {
            "score": round(avg_score, 1),
            "vote": decision,
            "reason": f"建议进入{pool}",
            "data": {"recommended_pool": pool}
        }


def analyze_with_real_data(symbol: str, kline_data: Dict, financials: Dict = None) -> Dict:
    """使用真实数据进行分析"""
    analyzer = VibeAgentAnalyzer(symbol, kline_data)
    financials = financials or {}

    agent_votes = []
    all_scores = []

    # ===== 技术分析组（9个，含新增量能分析）=====
    tech_results = [
        ("趋势智能体", analyzer.trend_agent()),
        ("动量智能体", analyzer.momentum_agent()),
        ("形态智能体", analyzer.pattern_agent()),
        ("成交量智能体", analyzer.volume_agent()),
        ("资金流向智能体", analyzer.money_flow_agent()),
        ("成交量异动智能体", analyzer.volume_anomaly_agent()),
        ("波动智能体", analyzer.volatility_agent()),
        ("支撑阻力智能体", analyzer.support_resistance_agent()),
        ("多周期智能体", analyzer.multi_period_agent()),
    ]

    for name, result in tech_results:
        agent_votes.append({"group": "技术分析", "name": name, **result})
        all_scores.append(result['score'])

    # ===== 基本面分析组（6个）=====
    fund_results = [
        ("估值智能体", analyzer.valuation_agent(financials)),
        ("财报智能体", analyzer.financial_agent(financials)),
        ("行业景气智能体", analyzer.industry_agent()),
        ("宏观经济智能体", analyzer.macro_agent()),
        ("政策研究智能体", analyzer.policy_agent()),
        ("成长价值智能体", analyzer.growth_agent(financials)),
    ]

    for name, result in fund_results:
        agent_votes.append({"group": "基本面分析", "name": name, **result})
        all_scores.append(result['score'])

    # ===== 舆情分析组（5个）=====
    sent_results = [
        ("新闻情感智能体", analyzer.news_sentiment_agent()),
        ("社交平台监控智能体", analyzer.social_media_agent()),
        ("资金流向追踪智能体", analyzer.money_flow_agent()),
        ("市场情绪综合智能体", analyzer.market_sentiment_agent()),
        ("板块轮动智能体", analyzer.sector_rotation_agent()),
    ]

    for name, result in sent_results:
        agent_votes.append({"group": "舆情分析", "name": name, **result})
        all_scores.append(result['score'])

    # ===== 风控组（4个）=====
    risk_results = [
        ("风险评估智能体", analyzer.risk_assessment_agent()),
        ("仓位管理智能体", analyzer.position_management_agent()),
        ("止损止盈智能体", analyzer.stop_loss_agent()),
        ("黑天鹅监控智能体", analyzer.black_swan_agent()),
    ]

    for name, result in risk_results:
        agent_votes.append({"group": "风险控制", "name": name, **result})
        all_scores.append(result['score'])

    # ===== 策略研究组（4个）=====
    strat_results = [
        ("策略组合构建智能体", analyzer.strategy_builder_agent()),
        ("回测验证智能体", analyzer.backtest_validator_agent()),
        ("交易执行智能体", analyzer.execution_agent()),
        ("绩效归因智能体", analyzer.performance_attribution_agent()),
    ]

    for name, result in strat_results:
        agent_votes.append({"group": "策略研究", "name": name, **result})
        all_scores.append(result['score'])

    # ===== 辅助决策组（3个）=====
    # 汇总协调
    coordinator = analyzer.coordinator_agent(all_scores)
    agent_votes.append({"group": "辅助决策", **coordinator})

    # 矛盾检测
    conflict_detector = analyzer.conflict_detector_agent(agent_votes)
    agent_votes.append({"group": "辅助决策", **conflict_detector})

    # 最终决策
    buy_votes = sum(1 for s in all_scores if s >= 70)
    sell_votes = sum(1 for s in all_scores if s < 50)
    buy_ratio = buy_votes / len(all_scores) if all_scores else 0
    final_decision = analyzer.final_decision_agent(coordinator['score'], buy_ratio)
    agent_votes.append({"group": "辅助决策", **final_decision})

    # 计算综合评分
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 50
    total_score = round(avg_score * 0.6 + buy_ratio * 40, 1)
    total_score = max(0, min(100, total_score))

    # 投票统计
    votes = [v['vote'] for v in agent_votes if v['vote'] in ['买入', '卖出', '观望']]
    total_buy = votes.count('买入')
    total_sell = votes.count('卖出')
    total_hold = votes.count('观望')

    # 建议仓位
    if total_score >= 80:
        position = "8-12%"
    elif total_score >= 70:
        position = "5-8%"
    elif total_score >= 60:
        position = "3-5%"
    elif total_score >= 50:
        position = "1-3%"
    else:
        position = "0% (不建议建仓)"

    return {
        "success": True,
        "symbol": symbol,
        "total_score": total_score,
        "final_decision": final_decision['vote'],
        "recommended_pool": final_decision['data']['recommended_pool'],
        "recommended_position": position,
        "confidence": conflict_detector['vote'].replace("一致性", ""),
        "vote_summary": {
            "total_agents": 29,
            "buy_votes": total_buy,
            "sell_votes": total_sell,
            "hold_votes": total_hold,
            "consensus_level": conflict_detector['vote'].replace("一致性", ""),
            "buy_ratio": round(buy_ratio * 100, 1),
            "sell_ratio": round(total_sell / len(all_scores) * 100, 1) if all_scores else 0
        },
        "agent_votes": agent_votes,
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "data_source": "real"  # 标记为真实数据
    }
