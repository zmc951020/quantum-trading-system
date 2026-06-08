#!/usr/bin/env python3
"""
技术分析模块（Technical Analysis Module）

核心能力：
  1. K线数据处理与指标计算
  2. 技术指标库（RSI、MACD、布林带、均线等）
  3. 因子分析（Alpha因子库）
  4. 信号生成与策略规则

技术指标：
  - 均线类：MA、EMA、SMA、WMA
  - 震荡类：RSI、KDJ、CCI
  - 趋势类：MACD、ATR、ADX
  - 波动率：布林带、ATR、HV
  - 量能类：OBV、VWAP
"""

import os
import sys
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import pandas as pd
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    pd = None

# ============================================================
# 技术指标结果
# ============================================================

@dataclass
class IndicatorResult:
    name: str
    values: List[float]
    signals: List[str] = None
    params: Dict = None

# ============================================================
# 技术分析引擎
# ============================================================

class TechnicalAnalysisEngine:
    """技术分析引擎"""
    
    def __init__(self):
        self._indicators = {
            'ma': self._calculate_ma,
            'ema': self._calculate_ema,
            'rsi': self._calculate_rsi,
            'macd': self._calculate_macd,
            'bollinger': self._calculate_bollinger,
            'atr': self._calculate_atr,
            'kdj': self._calculate_kdj,
            'obv': self._calculate_obv,
        }
    
    def calculate_indicator(self, prices: List[float], indicator: str, 
                            params: Dict = None) -> IndicatorResult:
        """计算技术指标"""
        params = params or {}
        
        if indicator.lower() in self._indicators:
            return self._indicators[indicator.lower()](prices, params)
        
        return IndicatorResult(name=indicator, values=[], signals=[], params=params)
    
    def calculate_all(self, prices: List[float], volumes: List[float] = None) -> Dict[str, IndicatorResult]:
        """计算所有技术指标"""
        results = {}
        
        results['MA5'] = self._calculate_ma(prices, {'period': 5})
        results['MA10'] = self._calculate_ma(prices, {'period': 10})
        results['MA20'] = self._calculate_ma(prices, {'period': 20})
        results['MA60'] = self._calculate_ma(prices, {'period': 60})
        
        results['EMA12'] = self._calculate_ema(prices, {'period': 12})
        results['EMA26'] = self._calculate_ema(prices, {'period': 26})
        
        results['RSI'] = self._calculate_rsi(prices, {'period': 14})
        
        results['MACD'] = self._calculate_macd(prices)
        
        results['BOLL'] = self._calculate_bollinger(prices)
        
        results['ATR'] = self._calculate_atr(prices)
        
        results['KDJ'] = self._calculate_kdj(prices)
        
        if volumes:
            results['OBV'] = self._calculate_obv(prices, {'volumes': volumes})
            results['VOLUME_RATIO'] = self._calculate_volume_ratio(volumes)
            results['MONEY_FLOW'] = self._calculate_money_flow(prices, volumes)
            results['VOL_DEVIATION'] = self._calculate_volume_deviation(volumes)
        
        return results
    
    def generate_signals(self, indicators: Dict[str, IndicatorResult]) -> List[Dict]:
        """根据指标生成交易信号"""
        signals = []
        
        # RSI信号
        if 'RSI' in indicators:
            rsi_values = indicators['RSI'].values
            if rsi_values:
                last_rsi = rsi_values[-1]
                if last_rsi < 30:
                    signals.append({'type': 'buy', 'indicator': 'RSI', 'value': last_rsi, 
                                   'reason': 'RSI超卖，建议买入'})
                elif last_rsi > 70:
                    signals.append({'type': 'sell', 'indicator': 'RSI', 'value': last_rsi, 
                                   'reason': 'RSI超买，建议卖出'})
        
        # MACD信号: values 是 (macd_line, signal_line) tuple 列表
        if 'MACD' in indicators:
            macd_values = indicators['MACD'].values
            if len(macd_values) >= 2:
                try:
                    current_tuple = macd_values[-1]
                    prev_tuple = macd_values[-2]
                    # 取第一条线（MACD线）作为判断依据
                    current = current_tuple[0] if isinstance(current_tuple, tuple) else current_tuple
                    prev = prev_tuple[0] if isinstance(prev_tuple, tuple) else prev_tuple
                    if prev is not None and current is not None:
                        if prev < 0 and current > 0:
                            signals.append({'type': 'buy', 'indicator': 'MACD', 'value': current,
                                           'reason': 'MACD金叉，建议买入'})
                        elif prev > 0 and current < 0:
                            signals.append({'type': 'sell', 'indicator': 'MACD', 'value': current,
                                           'reason': 'MACD死叉，建议卖出'})
                except (TypeError, IndexError):
                    pass

        # 布林带信号: values 是 (lower, mid, upper) tuple 列表
        if 'BOLL' in indicators:
            boll_values = indicators['BOLL'].values
            if boll_values:
                try:
                    last = boll_values[-1]
                    if isinstance(last, tuple) and len(last) >= 3:
                        lower, middle, upper = last[0], last[1], last[2]
                        if lower and middle and upper and lower > 0 and middle > 0 and upper > 0:
                            signals.append({'type': 'info', 'indicator': 'BOLL',
                                           'value': f'{lower:.2f}/{middle:.2f}/{upper:.2f}',
                                           'reason': f'布林带宽度: {(upper-lower)/middle*100:.2f}%'})
                except (TypeError, IndexError):
                    pass
        
        # 均线信号
        if all(k in indicators for k in ['MA5', 'MA10', 'MA20']):
            ma5 = indicators['MA5'].values
            ma10 = indicators['MA10'].values
            ma20 = indicators['MA20'].values
            if ma5 and ma10 and ma20:
                if ma5[-1] > ma10[-1] > ma20[-1]:
                    signals.append({'type': 'buy', 'indicator': 'MA', 
                                   'value': f'{ma5[-1]:.2f}>{ma10[-1]:.2f}>{ma20[-1]:.2f}',
                                   'reason': '均线多头排列，趋势向上'})
                elif ma5[-1] < ma10[-1] < ma20[-1]:
                    signals.append({'type': 'sell', 'indicator': 'MA', 
                                   'value': f'{ma5[-1]:.2f}<{ma10[-1]:.2f}<{ma20[-1]:.2f}',
                                   'reason': '均线空头排列，趋势向下'})
        
        return signals
    
    def analyze_stock(self, symbol: str, prices: List[float], volumes: List[float] = None) -> Dict:
        """完整分析一只股票"""
        indicators = self.calculate_all(prices, volumes)
        signals = self.generate_signals(indicators)

        # 计算统计指标
        stats = {
            'avg_price': sum(prices[-30:]) / min(len(prices), 30) if prices else 0,
            'max_price': max(prices) if prices else 0,
            'min_price': min(prices) if prices else 0,
            'volatility': self._calculate_volatility(prices),
            'trend': self._detect_trend(prices),
            'momentum': self._calculate_momentum(prices),
        }

        return {
            'symbol': symbol,
            'indicators': indicators,
            'signals': signals,
            'stats': stats,
            'analysis_time': datetime.now().isoformat()
        }

    # --------------------------------------------------------
    # 数据总线集成
    # --------------------------------------------------------

    def analyze_from_bus(self, symbol: str, period: str = "daily", days: int = 500) -> Dict:
        """通过统一数据总线获取数据并分析

        Args:
            symbol: 股票代码
            period: 数据周期
            days: 获取天数

        Returns:
            dict: {success, data_source, raw_data, analysis}
        """
        try:
            from core.data_bus import get_data_bus
            bus = get_data_bus()

            # 1. 从总线获取K线
            kline = bus.get_kline(symbol, period=period, days=days)
            if kline is None or not kline.get("closes"):
                return {
                    "success": False,
                    "symbol": symbol,
                    "error": "无法获取K线数据",
                    "data_source": None,
                    "raw_data": None,
                    "analysis": None
                }

            closes = [float(c) for c in kline["closes"]]
            volumes = [float(v) for v in kline.get("volumes", [])] if kline.get("volumes") else None

            # 2. 执行技术分析
            analysis = self.analyze_stock(symbol, closes, volumes)

            return {
                "success": True,
                "symbol": symbol,
                "data_source": kline.get("source", "unknown"),
                "raw_data": kline,
                "analysis": analysis,
                "data_count": len(closes)
            }

        except Exception as e:
            print(f"[TechnicalAnalysisEngine] analyze_from_bus 异常: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "data_source": None,
                "raw_data": None,
                "analysis": None
            }

    # ---------- 指标计算实现 ----------
    
    def _calculate_ma(self, prices: List[float], params: Dict) -> IndicatorResult:
        """计算简单移动平均线"""
        period = params.get('period', 20)
        values = []
        
        for i in range(len(prices)):
            if i >= period - 1:
                values.append(sum(prices[i-period+1:i+1]) / period)
            else:
                values.append(None)
        
        return IndicatorResult(name=f'MA{period}', values=values, params={'period': period})
    
    def _calculate_ema(self, prices: List[float], params: Dict) -> IndicatorResult:
        """计算指数移动平均线"""
        period = params.get('period', 12)
        values = []
        
        if not prices:
            return IndicatorResult(name=f'EMA{period}', values=[], params={'period': period})
        
        alpha = 2 / (period + 1)
        values.append(prices[0])
        
        for i in range(1, len(prices)):
            values.append(alpha * prices[i] + (1 - alpha) * values[-1])
        
        return IndicatorResult(name=f'EMA{period}', values=values, params={'period': period})
    
    def _calculate_rsi(self, prices: List[float], params: Dict) -> IndicatorResult:
        """计算相对强弱指标"""
        period = params.get('period', 14)
        values = []
        
        if len(prices) < period + 1:
            return IndicatorResult(name='RSI', values=[], params={'period': period})
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        if avg_loss == 0:
            values.append(100)
        else:
            rs = avg_gain / avg_loss
            values.append(100 - (100 / (1 + rs)))
        
        for i in range(period, len(gains)):
            avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
            
            if avg_loss == 0:
                values.append(100)
            else:
                rs = avg_gain / avg_loss
                values.append(100 - (100 / (1 + rs)))
        
        # 前面补None
        return IndicatorResult(name='RSI', values=[None] + values, params={'period': period})
    
    def _calculate_macd(self, prices: List[float]) -> IndicatorResult:
        """计算MACD"""
        ema12 = self._calculate_ema(prices, {'period': 12}).values
        ema26 = self._calculate_ema(prices, {'period': 26}).values
        
        macd = []
        for i in range(len(prices)):
            if ema12[i] is not None and ema26[i] is not None:
                macd.append(ema12[i] - ema26[i])
            else:
                macd.append(None)
        
        # 信号线（MACD的9日EMA）
        signal = self._calculate_ema([m for m in macd if m is not None], {'period': 9}).values
        
        # 对齐长度
        result = []
        signal_idx = 0
        for i, m in enumerate(macd):
            if m is not None and signal_idx < len(signal):
                result.append((m, signal[signal_idx]))
                signal_idx += 1
            else:
                result.append((None, None))
        
        return IndicatorResult(name='MACD', values=result, params={'fast': 12, 'slow': 26, 'signal': 9})
    
    def _calculate_bollinger(self, prices: List[float], params: Dict = None) -> IndicatorResult:
        """计算布林带"""
        period = params.get('period', 20) if params else 20
        std_dev = params.get('std_dev', 2) if params else 2
        
        values = []
        
        for i in range(len(prices)):
            if i >= period - 1:
                window = prices[i-period+1:i+1]
                mean = sum(window) / period
                variance = sum((p - mean) ** 2 for p in window) / period
                std = math.sqrt(variance)
                values.append((mean - std_dev * std, mean, mean + std_dev * std))
            else:
                values.append((None, None, None))
        
        return IndicatorResult(name='Bollinger', values=values, params={'period': period, 'std_dev': std_dev})
    
    def _calculate_atr(self, prices: List[float], params: Dict = None) -> IndicatorResult:
        """计算平均真实波动范围"""
        period = params.get('period', 14) if params else 14
        
        values = []
        
        if len(prices) < 2:
            return IndicatorResult(name='ATR', values=[], params={'period': period})
        
        # 简化计算：用价格波动代替高低价
        tr_values = []
        for i in range(1, len(prices)):
            tr_values.append(abs(prices[i] - prices[i-1]))
        
        for i in range(len(tr_values)):
            if i >= period - 1:
                values.append(sum(tr_values[i-period+1:i+1]) / period)
            else:
                values.append(None)
        
        return IndicatorResult(name='ATR', values=[None] + values, params={'period': period})
    
    def _calculate_kdj(self, prices: List[float], params: Dict = None) -> IndicatorResult:
        """计算KDJ指标"""
        period = params.get('period', 9) if params else 9
        
        values = []
        
        for i in range(len(prices)):
            if i >= period - 1:
                window = prices[i-period+1:i+1]
                high = max(window)
                low = min(window)
                close = prices[i]
                
                rsv = (close - low) / (high - low) * 100 if high != low else 50
                
                if i == period - 1:
                    k = rsv
                    d = rsv
                else:
                    prev_k, prev_d, _ = values[-1] if values else (50, 50, 0)
                    k = (2 * prev_k + rsv) / 3
                    d = (2 * prev_d + k) / 3
                
                j = 3 * k - 2 * d
                values.append((k, d, j))
            else:
                values.append((None, None, None))
        
        return IndicatorResult(name='KDJ', values=values, params={'period': period})
    
    def _calculate_obv(self, prices: List[float], params: Dict) -> IndicatorResult:
        """计算能量潮指标"""
        volumes = params.get('volumes', [])
        
        values = []
        obv = 0
        
        for i in range(len(prices)):
            if i == 0:
                obv = volumes[i] if i < len(volumes) else 0
            else:
                if prices[i] > prices[i-1]:
                    obv += volumes[i] if i < len(volumes) else 0
                elif prices[i] < prices[i-1]:
                    obv -= volumes[i] if i < len(volumes) else 0
            
            values.append(obv)
        
        return IndicatorResult(name='OBV', values=values, params={})

    def _calculate_volume_ratio(self, volumes: List[float]) -> IndicatorResult:
        """计算量比指标（Volume Ratio）
        
        量比 = 当日成交量 / 过去5日平均成交量
        """
        values = []
        for i in range(len(volumes)):
            if i < 5:
                values.append(1.0)  # 数据不足用1.0作为中性
            else:
                avg_5d = sum(volumes[i-5:i]) / 5
                if avg_5d > 0:
                    values.append(round(volumes[i] / avg_5d, 3))
                else:
                    values.append(1.0)
        return IndicatorResult(name='VOLUME_RATIO', values=values, params={'window': 5})

    def _calculate_money_flow(self, prices: List[float], volumes: List[float]) -> IndicatorResult:
        """计算资金流向（简化版MFI - Money Flow Index）
        
        资金流向 = sum(收盘价上涨日的成交额) - sum(收盘价下跌日的成交额)
        """
        values = []
        cum_flow = 0  # 累计资金流
        n = min(len(prices), len(volumes))
        
        for i in range(n):
            if i == 0:
                values.append(0)
            else:
                # 当日资金流 = 涨跌幅方向 × 成交量 × 价格
                price_change = prices[i] - prices[i-1]
                daily_flow = price_change * volumes[i]  # 简化版
                cum_flow += daily_flow
                values.append(round(cum_flow, 0))
        
        return IndicatorResult(name='MONEY_FLOW', values=values, params={})

    def _calculate_volume_deviation(self, volumes: List[float]) -> IndicatorResult:
        """计算成交量异动（成交量偏离20日均线的标准差）
        
        返回值：z-score，正数表示放量，负数表示缩量
        """
        values = []
        for i in range(len(volumes)):
            if i < 20:
                values.append(0.0)
            else:
                window = volumes[i-20:i]
                avg = sum(window) / 20
                variance = sum((v - avg) ** 2 for v in window) / 20
                std = variance ** 0.5 if variance > 0 else 1
                z_score = (volumes[i] - avg) / std if std > 0 else 0
                values.append(round(z_score, 3))
        
        return IndicatorResult(name='VOL_DEVIATION', values=values, params={'window': 20})
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """计算波动率"""
        if len(prices) < 2:
            return 0
        
        returns = []
        for i in range(1, len(prices)):
            returns.append((prices[i] - prices[i-1]) / prices[i-1])
        
        if not returns:
            return 0
        
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return math.sqrt(variance) * math.sqrt(252) * 100  # 年化波动率(%)
    
    def _detect_trend(self, prices: List[float]) -> str:
        """检测趋势方向"""
        if len(prices) < 30:
            return 'unknown'
        
        # 用最近30天和之前30天比较
        recent = prices[-30:]
        earlier = prices[-60:-30] if len(prices) >= 60 else prices[:-30] if len(prices) > 30 else []
        
        if not earlier:
            return 'unknown'
        
        recent_mean = sum(recent) / len(recent)
        earlier_mean = sum(earlier) / len(earlier)
        
        change = (recent_mean - earlier_mean) / earlier_mean * 100
        
        if change > 5:
            return 'up'
        elif change < -5:
            return 'down'
        else:
            return 'sideways'
    
    def _calculate_momentum(self, prices: List[float]) -> float:
        """计算动量"""
        if len(prices) < 14:
            return 0
        
        return (prices[-1] - prices[-14]) / prices[-14] * 100

# ============================================================
# 因子分析引擎
# ============================================================

class FactorAnalysisEngine:
    """因子分析引擎 - 基于量价数据计算Alpha因子"""
    
    def __init__(self):
        self._factors = {
            'momentum_1d': self._factor_momentum_1d,
            'momentum_5d': self._factor_momentum_5d,
            'momentum_20d': self._factor_momentum_20d,
            'momentum_60d': self._factor_momentum_60d,
            'volatility_20d': self._factor_volatility_20d,
            'rsi_14d': self._factor_rsi_14d,
            'bollinger_width': self._factor_bollinger_width,
            'macd_signal': self._factor_macd_signal,
            'atr_ratio': self._factor_atr_ratio,
            'obv_change': self._factor_obv_change,
            'ma_slope_20d': self._factor_ma_slope_20d,
            'volume_ratio': self._factor_volume_ratio,
        }
    
    def calculate_factor(self, symbol: str, prices: List[float], volumes: List[float] = None) -> Dict[str, float]:
        """计算所有因子"""
        results = {}
        for name, func in self._factors.items():
            try:
                results[name] = func(prices, volumes)
            except Exception:
                results[name] = 0.0
        return results
    
    def get_factor_descriptions(self) -> Dict[str, str]:
        """获取因子描述"""
        return {
            'momentum_1d': '1日动量',
            'momentum_5d': '5日动量',
            'momentum_20d': '20日动量',
            'momentum_60d': '60日动量',
            'volatility_20d': '20日波动率',
            'rsi_14d': 'RSI(14)',
            'bollinger_width': '布林带宽度',
            'macd_signal': 'MACD信号',
            'atr_ratio': 'ATR比率',
            'obv_change': 'OBV变化率',
            'ma_slope_20d': '20日均线斜率',
            'volume_ratio': '量比',
        }
    
    def _factor_momentum_1d(self, prices: List[float], volumes: List) -> float:
        if len(prices) < 2:
            return 0
        return (prices[-1] - prices[-2]) / prices[-2] * 100
    
    def _factor_momentum_5d(self, prices: List[float], volumes: List) -> float:
        if len(prices) < 6:
            return 0
        return (prices[-1] - prices[-6]) / prices[-6] * 100
    
    def _factor_momentum_20d(self, prices: List[float], volumes: List) -> float:
        if len(prices) < 21:
            return 0
        return (prices[-1] - prices[-21]) / prices[-21] * 100
    
    def _factor_momentum_60d(self, prices: List[float], volumes: List) -> float:
        if len(prices) < 61:
            return 0
        return (prices[-1] - prices[-61]) / prices[-61] * 100
    
    def _factor_volatility_20d(self, prices: List[float], volumes: List) -> float:
        if len(prices) < 20:
            return 0
        window = prices[-20:]
        mean = sum(window) / 20
        variance = sum((p - mean) ** 2 for p in window) / 20
        return math.sqrt(variance) / mean * 100
    
    def _factor_rsi_14d(self, prices: List[float], volumes: List) -> float:
        engine = TechnicalAnalysisEngine()
        rsi = engine._calculate_rsi(prices, {'period': 14})
        return rsi.values[-1] if rsi.values and rsi.values[-1] else 50
    
    def _factor_bollinger_width(self, prices: List[float], volumes: List) -> float:
        engine = TechnicalAnalysisEngine()
        boll = engine._calculate_bollinger(prices)
        if boll.values and boll.values[-1] and all(v is not None for v in boll.values[-1]):
            lower, mid, upper = boll.values[-1]
            return (upper - lower) / mid * 100
        return 0
    
    def _factor_macd_signal(self, prices: List[float], volumes: List) -> float:
        engine = TechnicalAnalysisEngine()
        macd = engine._calculate_macd(prices)
        if macd.values and macd.values[-1] and all(v is not None for v in macd.values[-1]):
            macd_val, signal_val = macd.values[-1]
            return macd_val - signal_val
        return 0
    
    def _factor_atr_ratio(self, prices: List[float], volumes: List) -> float:
        engine = TechnicalAnalysisEngine()
        atr = engine._calculate_atr(prices)
        if atr.values and atr.values[-1]:
            return atr.values[-1] / prices[-1] * 100 if prices else 0
        return 0
    
    def _factor_obv_change(self, prices: List[float], volumes: List) -> float:
        if not volumes or len(volumes) < 2:
            return 0
        return (volumes[-1] - volumes[-2]) / volumes[-2] * 100
    
    def _factor_ma_slope_20d(self, prices: List[float], volumes: List) -> float:
        engine = TechnicalAnalysisEngine()
        ma = engine._calculate_ma(prices, {'period': 20})
        if len(ma.values) >= 10:
            recent = ma.values[-1]
            earlier = ma.values[-10]
            if earlier and earlier != 0:
                return (recent - earlier) / earlier * 100
        return 0
    
    def _factor_volume_ratio(self, prices: List[float], volumes: List) -> float:
        if not volumes or len(volumes) < 6:
            return 100
        recent = volumes[-1]
        avg_5d = sum(volumes[-6:-1]) / 5
        return recent / avg_5d * 100

# ============================================================
# 全局单例
# ============================================================

_ta_engine = None
_factor_engine = None

def get_ta_engine() -> TechnicalAnalysisEngine:
    global _ta_engine
    if _ta_engine is None:
        _ta_engine = TechnicalAnalysisEngine()
    return _ta_engine

def get_factor_engine() -> FactorAnalysisEngine:
    global _factor_engine
    if _factor_engine is None:
        _factor_engine = FactorAnalysisEngine()
    return _factor_engine

# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":
    # 生成模拟数据
    prices = [10.0]
    for i in range(100):
        prices.append(prices[-1] * (1 + random.uniform(-0.03, 0.03)))
    
    volumes = [random.randint(10000, 50000) for _ in range(101)]
    
    # 技术分析
    ta = get_ta_engine()
    analysis = ta.analyze_stock('000001', prices, volumes)
    
    print("技术分析结果:")
    print(f"  波动率: {analysis['stats']['volatility']:.2f}%")
    print(f"  趋势: {analysis['stats']['trend']}")
    print(f"  动量: {analysis['stats']['momentum']:.2f}%")
    print(f"  信号: {len(analysis['signals'])} 个")
    for sig in analysis['signals']:
        print(f"    [{sig['type']}] {sig['indicator']}: {sig['reason']}")
    
    # 因子分析
    factor = get_factor_engine()
    factors = factor.calculate_factor('000001', prices, volumes)
    
    print("\n因子值:")
    desc = factor.get_factor_descriptions()
    for name, value in factors.items():
        print(f"  {desc[name]}: {value:.2f}")