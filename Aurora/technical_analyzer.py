#!/usr/bin/env python3
"""
技术分析工具类
实现常用的技术指标计算
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

class TechnicalAnalyzer:
    """
    技术分析工具类
    """

    @staticmethod
    def calculate_ma(data: List[float], period: int) -> List[float]:
        """计算移动平均线"""
        if not data or period is None or period <= 0:
            return [None] * len(data) if data else []

        if len(data) < period:
            return [None] * len(data)

        ma = []
        for i in range(len(data)):
            if i < period - 1:
                ma.append(None)
            else:
                slice_data = data[i - period + 1:i + 1]
                valid_data = [x for x in slice_data if x is not None]
                if len(valid_data) < period:
                    ma.append(None)
                else:
                    ma_value = sum(valid_data) / period
                    ma.append(ma_value)
        return ma

    @staticmethod
    def calculate_ema(data: List[float], period: int) -> List[float]:
        """计算指数移动平均线"""
        if not data or period is None or period <= 0:
            return [None] * len(data) if data else []

        valid_data = [x for x in data if x is not None]
        if len(valid_data) < period:
            return [None] * len(data)

        ema = []
        multiplier = 2 / (period + 1)

        initial_ema = sum(valid_data[:period]) / period
        ema.extend([None] * (period - 1))
        ema.append(initial_ema)

        valid_idx = period - 1
        for i in range(period, len(data)):
            if data[i] is None:
                ema.append(None)
            else:
                current_ema = (data[i] - ema[-1]) * multiplier + ema[-1]
                ema.append(current_ema)

        return ema

    @staticmethod
    def calculate_macd(data: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, List[float]]:
        """计算MACD指标"""
        if len(data) < slow_period + signal_period:
            return {'macd': [None] * len(data), 'signal': [None] * len(data), 'histogram': [None] * len(data)}

        fast_ema = TechnicalAnalyzer.calculate_ema(data, fast_period)
        slow_ema = TechnicalAnalyzer.calculate_ema(data, slow_period)

        macd = []
        for f, s in zip(fast_ema, slow_ema):
            if f is not None and s is not None:
                macd.append(f - s)
            else:
                macd.append(None)

        signal = TechnicalAnalyzer.calculate_ema([x for x in macd if x is not None], signal_period)
        signal = [None] * (len(macd) - len(signal)) + signal

        histogram = []
        for m, s in zip(macd, signal):
            if m is not None and s is not None:
                histogram.append(m - s)
            else:
                histogram.append(None)

        return {'macd': macd, 'signal': signal, 'histogram': histogram}

    @staticmethod
    def calculate_rsi(data: List[float], period: int = 14) -> List[float]:
        """计算RSI指标"""
        if len(data) < period + 1:
            return [None] * len(data)

        rsi = []
        gains = []
        losses = []

        for i in range(1, period + 1):
            change = data[i] - data[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi_value = 100
        else:
            rs = avg_gain / avg_loss
            rsi_value = 100 - (100 / (1 + rs))

        rsi.extend([None] * period)
        rsi.append(rsi_value)

        for i in range(period + 1, len(data)):
            change = data[i] - data[i - 1]

            if change > 0:
                current_gain = change
                current_loss = 0
            else:
                current_gain = 0
                current_loss = abs(change)

            avg_gain = (avg_gain * (period - 1) + current_gain) / period
            avg_loss = (avg_loss * (period - 1) + current_loss) / period

            if avg_loss == 0:
                rsi_value = 100
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))

            rsi.append(rsi_value)

        return rsi

    @staticmethod
    def calculate_kdj(data: List[float], period: int = 9, k_period: int = 3, d_period: int = 3) -> Dict[str, List[float]]:
        """计算KDJ指标"""
        if len(data) < period:
            return {'k': [None] * len(data), 'd': [None] * len(data), 'j': [None] * len(data)}

        rsv = []
        for i in range(len(data)):
            if i < period - 1:
                rsv.append(None)
            else:
                highest = max(data[i - period + 1:i + 1])
                lowest = min(data[i - period + 1:i + 1])
                if highest == lowest:
                    rsv_value = 50
                else:
                    rsv_value = (data[i] - lowest) / (highest - lowest) * 100
                rsv.append(rsv_value)

        k = []
        for i, r in enumerate(rsv):
            if i < period - 1:
                k.append(None)
            elif i == period - 1:
                k.append(50)
            else:
                k_value = (2/3) * k[-1] + (1/3) * r
                k.append(k_value)

        d = []
        for i, k_val in enumerate(k):
            if i < period - 1:
                d.append(None)
            elif i == period - 1:
                d.append(50)
            else:
                d_value = (2/3) * d[-1] + (1/3) * k_val
                d.append(d_value)

        j = []
        for k_val, d_val in zip(k, d):
            if k_val is not None and d_val is not None:
                j_value = 3 * k_val - 2 * d_val
                j.append(j_value)
            else:
                j.append(None)

        return {'k': k, 'd': d, 'j': j}

    @staticmethod
    def calculate_bollinger_bands(data: List[float], period: int = 20, std_dev: float = 2) -> Dict[str, List[float]]:
        """计算布林带"""
        if len(data) < period:
            return {'upper': [None] * len(data), 'middle': [None] * len(data), 'lower': [None] * len(data)}

        upper = []
        middle = []
        lower = []

        for i in range(len(data)):
            if i < period - 1:
                upper.append(None)
                middle.append(None)
                lower.append(None)
            else:
                window = data[i - period + 1:i + 1]
                ma = sum(window) / period
                std = np.std(window)

                middle.append(ma)
                upper.append(ma + std_dev * std)
                lower.append(ma - std_dev * std)

        return {'upper': upper, 'middle': middle, 'lower': lower}

    @staticmethod
    def calculate_atr(data: List[float], high: List[float], low: List[float], period: int = 14) -> List[float]:
        """计算ATR指标"""
        if len(data) < period:
            return [None] * len(data)

        true_range = []
        for i in range(len(data)):
            if i == 0:
                true_range.append(high[i] - low[i])
            else:
                tr1 = high[i] - low[i]
                tr2 = abs(high[i] - data[i - 1])
                tr3 = abs(low[i] - data[i - 1])
                true_range.append(max(tr1, tr2, tr3))

        atr = []
        for i in range(len(true_range)):
            if i < period - 1:
                atr.append(None)
            elif i == period - 1:
                atr.append(sum(true_range[:period]) / period)
            else:
                atr_value = (atr[-1] * (period - 1) + true_range[i]) / period
                atr.append(atr_value)

        return atr

    @staticmethod
    def calculate_ma_crossover(data: List[float], short_period: int = 10, long_period: int = 20) -> List[str]:
        """计算MA金叉死叉信号"""
        short_ma = TechnicalAnalyzer.calculate_ma(data, short_period)
        long_ma = TechnicalAnalyzer.calculate_ma(data, long_period)

        signals = [None] * len(data)

        for i in range(1, len(data)):
            if short_ma[i] is not None and long_ma[i] is not None and short_ma[i-1] is not None and long_ma[i-1] is not None:
                if short_ma[i-1] < long_ma[i-1] and short_ma[i] > long_ma[i]:
                    signals[i] = 'golden'
                elif short_ma[i-1] > long_ma[i-1] and short_ma[i] < long_ma[i]:
                    signals[i] = 'death'

        return signals

    @staticmethod
    def calculate_obv(close_prices: List[float], volumes: List[float]) -> List[float]:
        """计算OBV（能量潮指标）"""
        if len(close_prices) != len(volumes) or len(close_prices) < 2:
            return [None] * len(close_prices)

        obv = [0]
        for i in range(1, len(close_prices)):
            if close_prices[i] > close_prices[i-1]:
                obv.append(obv[-1] + volumes[i])
            elif close_prices[i] < close_prices[i-1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])

        return obv

    @staticmethod
    def calculate_adx(high_prices: List[float], low_prices: List[float], close_prices: List[float], period: int = 14) -> Dict[str, List[float]]:
        """计算ADX（平均趋向指数）"""
        if len(high_prices) != len(low_prices) or len(high_prices) != len(close_prices):
            return {'adx': [None] * len(close_prices), 'plus_di': [None] * len(close_prices), 'minus_di': [None] * len(close_prices)}

        if len(close_prices) < period * 2:
            return {'adx': [None] * len(close_prices), 'plus_di': [None] * len(close_prices), 'minus_di': [None] * len(close_prices)}

        tr_list = []
        plus_dm = []
        minus_dm = []

        for i in range(1, len(close_prices)):
            high_diff = high_prices[i] - high_prices[i-1]
            low_diff = low_prices[i-1] - low_prices[i]

            tr = max(high_prices[i] - low_prices[i], abs(high_prices[i] - close_prices[i-1]), abs(low_prices[i] - close_prices[i-1]))
            tr_list.append(tr)

            if high_diff > low_diff and high_diff > 0:
                plus_dm.append(high_diff)
            else:
                plus_dm.append(0)

            if low_diff > high_diff and low_diff > 0:
                minus_dm.append(low_diff)
            else:
                minus_dm.append(0)

        atr = TechnicalAnalyzer._smoothed_average(tr_list, period)
        plus_di = TechnicalAnalyzer._smoothed_average(plus_dm, period)
        minus_di = TechnicalAnalyzer._smoothed_average(minus_dm, period)

        adx = []
        for i in range(len(atr)):
            if i < period * 2 - 1:
                adx.append(None)
            else:
                dx = 0
                if atr[i] is not None and atr[i] > 0 and plus_di[i] is not None and minus_di[i] is not None:
                    dx = abs(plus_di[i] - minus_di[i]) / atr[i] * 100
                if len(adx) == 0 or adx[-1] is None:
                    adx.append(dx)
                else:
                    adx.append((adx[-1] * (period - 1) + dx) / period)

        return {'adx': [None] * (period * 2 - 1) + adx, 'plus_di': [None] * (period - 1) + plus_di, 'minus_di': [None] * (period - 1) + minus_di}

    @staticmethod
    def _smoothed_average(data: List[float], period: int) -> List[float]:
        """计算平滑移动平均"""
        if len(data) < period:
            return [None] * len(data)

        smoothed = [None] * (period - 1)
        sma = sum(data[:period]) / period
        smoothed.append(sma)

        for i in range(period, len(data)):
            sma = (sma * (period - 1) + data[i]) / period
            smoothed.append(sma)

        return smoothed

    @staticmethod
    def calculate_cci(high_prices: List[float], low_prices: List[float], close_prices: List[float], period: int = 14) -> List[float]:
        """计算CCI（顺势指标）"""
        if len(high_prices) != len(low_prices) or len(high_prices) != len(close_prices):
            return [None] * len(close_prices)

        tp = [(high_prices[i] + low_prices[i] + close_prices[i]) / 3 for i in range(len(close_prices))]
        cci = [None] * (period - 1)

        for i in range(period - 1, len(tp)):
            window = tp[i - period + 1:i + 1]
            sma = sum(window) / period
            mean_dev = sum(abs(tp[j] - sma) for j in range(i - period + 1, i + 1)) / period

            if mean_dev > 0:
                cci_value = (tp[i] - sma) / (0.015 * mean_dev)
                cci.append(cci_value)
            else:
                cci.append(0)

        return cci

    @staticmethod
    def calculate_roc(close_prices: List[float], period: int = 12) -> List[float]:
        """计算ROC（变动率指标）"""
        if len(close_prices) < period:
            return [None] * len(close_prices)

        roc = [None] * period
        for i in range(period, len(close_prices)):
            if close_prices[i - period] != 0:
                roc_value = ((close_prices[i] - close_prices[i - period]) / close_prices[i - period]) * 100
                roc.append(roc_value)
            else:
                roc.append(0)

        return roc

    @staticmethod
    def calculate_donchian(high_prices: List[float], low_prices: List[float], period: int = 20) -> Dict[str, List[float]]:
        """计算唐奇安通道（Donchian Channel）"""
        if len(high_prices) != len(low_prices):
            return {'upper': [None] * len(high_prices), 'middle': [None] * len(high_prices), 'lower': [None] * len(high_prices)}

        upper = []
        middle = []
        lower = []

        for i in range(len(high_prices)):
            if i < period - 1:
                upper.append(None)
                middle.append(None)
                lower.append(None)
            else:
                window_high = max(high_prices[i - period + 1:i + 1])
                window_low = min(low_prices[i - period + 1:i + 1])
                upper.append(window_high)
                lower.append(window_low)
                middle.append((window_high + window_low) / 2)

        return {'upper': upper, 'middle': middle, 'lower': lower}

    @staticmethod
    def detect_candlestick_patterns(open_prices: List[float], high_prices: List[float], low_prices: List[float], close_prices: List[float]) -> List[str]:
        """识别K线形态"""
        patterns = [None] * len(close_prices)

        for i in range(1, len(close_prices)):
            if i < 2:
                continue

            body_length = abs(close_prices[i] - open_prices[i])
            total_length = high_prices[i] - low_prices[i]

            if close_prices[i] > open_prices[i]:
                upper_shadow = high_prices[i] - close_prices[i]
                lower_shadow = open_prices[i] - low_prices[i]
            else:
                upper_shadow = high_prices[i] - open_prices[i]
                lower_shadow = close_prices[i] - low_prices[i]

            if body_length < total_length * 0.3 and lower_shadow > total_length * 0.6:
                patterns[i] = 'hammer'
            elif body_length < total_length * 0.3 and upper_shadow > total_length * 0.6:
                patterns[i] = 'inverted_hammer'
            elif body_length < total_length * 0.1:
                patterns[i] = 'doji'
            elif close_prices[i] > open_prices[i] and close_prices[i-1] < open_prices[i-1]:
                if close_prices[i] > open_prices[i-1] and open_prices[i] < close_prices[i-1]:
                    patterns[i] = 'bullish_engulfing'
            elif close_prices[i] < open_prices[i] and close_prices[i-1] > open_prices[i-1]:
                if close_prices[i] < open_prices[i-1] and open_prices[i] > close_prices[i-1]:
                    patterns[i] = 'bearish_engulfing'

        return patterns

    @staticmethod
    def detect_advanced_candlestick_patterns(open_prices: List[float], high_prices: List[float], low_prices: List[float], close_prices: List[float]) -> List[Dict]:
        """识别高级K线形态"""
        patterns = []

        for i in range(len(close_prices)):
            pattern = {
                'pattern': None,
                'signal': 'neutral',
                'strength': 0,
                'description': ''
            }

            if i < 2:
                patterns.append(pattern)
                continue

            body = abs(close_prices[i] - open_prices[i])
            total_range = high_prices[i] - low_prices[i] if high_prices[i] != low_prices[i] else 1

            if close_prices[i] > open_prices[i]:
                upper_shadow = high_prices[i] - close_prices[i]
                lower_shadow = open_prices[i] - low_prices[i]
            else:
                upper_shadow = high_prices[i] - open_prices[i]
                lower_shadow = close_prices[i] - low_prices[i]

            if i >= 2:
                prev_body = abs(close_prices[i-1] - open_prices[i-1])

                if (close_prices[i-1] < open_prices[i-1] and prev_body > total_range * 0.5 and close_prices[i] > open_prices[i] and close_prices[i] > (open_prices[i-1] + close_prices[i-1]) / 2):
                    pattern['pattern'] = 'morning_star'
                    pattern['signal'] = 'bullish'
                    pattern['strength'] = 0.8
                    pattern['description'] = '早晨之星 - 潜在反转信号'

            if i >= 2:
                prev_body = abs(close_prices[i-1] - open_prices[i-1])

                if (close_prices[i-1] > open_prices[i-1] and prev_body > total_range * 0.5 and close_prices[i] < open_prices[i] and close_prices[i] < (open_prices[i-1] + close_prices[i-1]) / 2):
                    pattern['pattern'] = 'evening_star'
                    pattern['signal'] = 'bearish'
                    pattern['strength'] = 0.8
                    pattern['description'] = '黄昏之星 - 潜在反转信号'

            if upper_shadow > body * 2 and upper_shadow > total_range * 0.6:
                pattern['pattern'] = 'shooting_star'
                pattern['signal'] = 'bearish'
                pattern['strength'] = 0.6
                pattern['description'] = '射击之星 - 潜在看跌信号'

            if lower_shadow > body * 2 and lower_shadow > total_range * 0.6:
                pattern['pattern'] = 'hammer'
                pattern['signal'] = 'bullish'
                pattern['strength'] = 0.6
                pattern['description'] = '锤子线 - 潜在看涨信号'

            if body < total_range * 0.1:
                pattern['pattern'] = 'doji'
                pattern['signal'] = 'neutral'
                pattern['strength'] = 0.3
                pattern['description'] = '十字星 - 市场犹豫'

            if i >= 2:
                if (close_prices[i] < close_prices[i-1] < close_prices[i-2] and close_prices[i] < open_prices[i] and close_prices[i-1] < open_prices[i-1] and close_prices[i-2] < open_prices[i-2]):
                    pattern['pattern'] = 'three_black_crows'
                    pattern['signal'] = 'bearish'
                    pattern['strength'] = 0.7
                    pattern['description'] = '三乌鸦 - 连续下跌'

            if i >= 2:
                if (close_prices[i] > close_prices[i-1] > close_prices[i-2] and close_prices[i] > open_prices[i] and close_prices[i-1] > open_prices[i-1] and close_prices[i-2] > open_prices[i-2]):
                    pattern['pattern'] = 'three_white_soldiers'
                    pattern['signal'] = 'bullish'
                    pattern['strength'] = 0.7
                    pattern['description'] = '三白兵 - 连续上涨'

            patterns.append(pattern)

        return patterns

    @staticmethod
    def calculate_all_indicators(price_data: List[Dict]) -> Dict[str, List[float]]:
        """计算所有技术指标"""
        if not price_data:
            return {}

        close_prices = [item['price'] for item in price_data]
        high_prices = [item.get('high', item['price']) for item in price_data]
        low_prices = [item.get('low', item['price']) for item in price_data]
        open_prices = [item.get('open', item['price']) for item in price_data]
        volume_data = [item.get('volume', 0) for item in price_data]

        indicators = {}

        indicators['ma5'] = TechnicalAnalyzer.calculate_ma(close_prices, 5)
        indicators['ma10'] = TechnicalAnalyzer.calculate_ma(close_prices, 10)
        indicators['ma20'] = TechnicalAnalyzer.calculate_ma(close_prices, 20)
        indicators['ma50'] = TechnicalAnalyzer.calculate_ma(close_prices, 50)

        indicators['ema12'] = TechnicalAnalyzer.calculate_ema(close_prices, 12)
        indicators['ema26'] = TechnicalAnalyzer.calculate_ema(close_prices, 26)

        macd = TechnicalAnalyzer.calculate_macd(close_prices)
        indicators.update(macd)

        indicators['rsi14'] = TechnicalAnalyzer.calculate_rsi(close_prices, 14)

        kdj = TechnicalAnalyzer.calculate_kdj(close_prices)
        indicators.update(kdj)

        bollinger = TechnicalAnalyzer.calculate_bollinger_bands(close_prices)
        indicators.update(bollinger)

        indicators['atr14'] = TechnicalAnalyzer.calculate_atr(close_prices, high_prices, low_prices, 14)

        indicators['ma_crossover'] = TechnicalAnalyzer.calculate_ma_crossover(close_prices)

        indicators['candlestick_patterns'] = TechnicalAnalyzer.detect_candlestick_patterns(open_prices, high_prices, low_prices, close_prices)

        indicators['obv'] = TechnicalAnalyzer.calculate_obv(close_prices, volume_data)

        adx = TechnicalAnalyzer.calculate_adx(high_prices, low_prices, close_prices, 14)
        indicators.update(adx)

        indicators['cci'] = TechnicalAnalyzer.calculate_cci(high_prices, low_prices, close_prices, 14)

        indicators['roc'] = TechnicalAnalyzer.calculate_roc(close_prices, 12)

        donchian = TechnicalAnalyzer.calculate_donchian(high_prices, low_prices, 20)
        indicators.update(donchian)

        indicators['volume_ma5'] = TechnicalAnalyzer.calculate_ma(volume_data, 5)
        indicators['volume_ma20'] = TechnicalAnalyzer.calculate_ma(volume_data, 20)

        return indicators

    @staticmethod
    def calculate_volume_indicators(volume_data: List[float]) -> Dict[str, List[float]]:
        """计算成交量指标"""
        if not volume_data:
            return {}

        indicators = {}

        indicators['volume_ma5'] = TechnicalAnalyzer.calculate_ma(volume_data, 5)
        indicators['volume_ma20'] = TechnicalAnalyzer.calculate_ma(volume_data, 20)

        volume_change = [None]
        for i in range(1, len(volume_data)):
            if volume_data[i-1] > 0:
                change = (volume_data[i] - volume_data[i-1]) / volume_data[i-1]
                volume_change.append(change)
            else:
                volume_change.append(0)
        indicators['volume_change'] = volume_change

        return indicators

    @staticmethod
    def get_market_signals(indicators: Dict[str, List[float]]) -> List[Dict]:
        """根据技术指标生成市场信号"""
        signals = []

        if 'rsi14' in indicators and 'macd' in indicators and 'ma_crossover' in indicators:
            rsi = indicators['rsi14']
            macd = indicators['macd']
            ma_crossover = indicators['ma_crossover']

            for i in range(len(rsi)):
                signal = {'buy': False, 'sell': False, 'hold': False, 'reason': []}

                if rsi[i] is not None and macd[i] is not None:
                    if rsi[i] < 30:
                        signal['buy'] = True
                        signal['reason'].append('RSI超卖')
                    elif rsi[i] > 70:
                        signal['sell'] = True
                        signal['reason'].append('RSI超买')

                    if i > 0 and macd[i] is not None and macd[i-1] is not None:
                        if macd[i-1] < 0 and macd[i] > 0:
                            signal['buy'] = True
                            signal['reason'].append('MACD金叉')
                        elif macd[i-1] > 0 and macd[i] < 0:
                            signal['sell'] = True
                            signal['reason'].append('MACD死叉')

                    if ma_crossover[i] == 'golden':
                        signal['buy'] = True
                        signal['reason'].append('MA金叉')
                    elif ma_crossover[i] == 'death':
                        signal['sell'] = True
                        signal['reason'].append('MA死叉')

                    if not signal['buy'] and not signal['sell']:
                        signal['hold'] = True

                signals.append(signal)

        return signals
