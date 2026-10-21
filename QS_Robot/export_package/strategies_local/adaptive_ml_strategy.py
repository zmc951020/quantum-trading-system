# -*- coding: utf-8 -*-
"""
【机构终极版】市场自动切换 + 机器学习永久传承策略
横盘赚大钱 | 上涨赚趋势 | 下跌防御反转 | 永不丢失学习成果
"""

import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

# ===================== 【顶层目标】预设收益&夏普 =====================
TARGET_PROFIT = {
    "RANGE":       0.20,  # 横盘：月化20%（核心收益）
    "STRONG_UP":   0.30,  # 上涨：月化30%
    "STRONG_DOWN": 0.02,  # 下跌：保本微利
    "PANIC":       0.0
}
TARGET_SHARPE = {
    "RANGE":       3.0,
    "STRONG_UP":   2.5,
    "STRONG_DOWN": 0.5,
    "PANIC":       0.0
}

# ===================== 风险与成本 =====================
INIT_CAPITAL = 100000.0
FEE_RATE = 0.00015
SLIPPAGE = 0.0001
SINGLE_RISK = 0.005    # 单笔风险0.5%
MAX_DRAW_DOWN = 0.08   # 最大回撤8%
ML_FILE = "ml_permanent_memory.json"

# ===================== 指标工具（机构标准） =====================
def EMA(series, period):
    return series.ewm(span=period, adjust=False).mean()

def ATR(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def ADX(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * np.maximum(high.diff(), 0).rolling(period).mean() / (atr + 1e-8)
    minus_di = 100 * np.maximum(-low.diff(), 0).rolling(period).mean() / (atr + 1e-8)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-8)
    return dx.rolling(period).mean()

def RSI(series, period=14):
    diff = series.diff()
    gain = diff.clip(lower=0).rolling(period).mean()
    loss = -diff.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-8)
    return 100 - 100 / (1 + rs)

# ===================== 【核心1】机器学习永久传承模块 =====================
class MLPersistentLearner:
    def __init__(self):
        self.data = self.load()

    def load(self):
        if os.path.exists(ML_FILE):
            with open(ML_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "best_step":     {"RANGE":0.8, "STRONG_UP":1.0, "STRONG_DOWN":0.4},
            "best_position": {"RANGE":0.8, "STRONG_UP":0.7, "STRONG_DOWN":0.2},
            "market_return": {},
            "last_update": str(datetime.now())
        }

    def save(self):
        self.data["last_update"] = str(datetime.now())
        with open(ML_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    def get_optimal_step(self, market_type, atr):
        step_coef = self.data["best_step"].get(market_type, 0.5)
        return step_coef * atr

    def update_market_result(self, market_type, ret, sharpe):
        if market_type not in self.data["market_return"]:
            self.data["market_return"][market_type] = []
        self.data["market_return"][market_type].append({
            "return": round(ret,4),
            "sharpe": round(sharpe,4),
            "time": str(datetime.now())
        })
        self.save()

# ===================== 【核心2】市场自动精准分类 =====================
def auto_classify_market(df):
    close = df.close
    high = df.high
    low = df.low
    ema20 = EMA(close,20)
    ema60 = EMA(close,60)
    adx = ADX(high,low,close)
    vol = close.pct_change().rolling(30).std()
    rsi = RSI(close)
    atr = ATR(high, low, close).iloc[-1]

    trend = (ema20.iloc[-1] - ema60.iloc[-1]) / (ema60.iloc[-1] + 1e-8)
    adx_last = adx.iloc[-1]
    vol_last = vol.iloc[-1]
    rsi_last = rsi.iloc[-1]

    atr_ratio = atr / (close.iloc[-1] + 1e-8)
    trend_threshold = max(0.005, atr_ratio * 0.5)
    vol_threshold = max(0.05, atr_ratio * 10)

    if adx_last > 25 and trend > trend_threshold:
        return "STRONG_UP"
    if adx_last > 25 and trend < -trend_threshold:
        return "STRONG_DOWN"
    if vol_last > vol_threshold:
        return "PANIC"
    return "RANGE"

# ===================== 【核心3】策略自动切换 =====================
# 可配置信号阈值（供参数优化使用）
SIGNAL_THRESHOLDS = {
    "range_atr_mult": 0.1,     # 横盘ATR倍数
    "range_rsi_buy": 40,       # 横盘RSI买入阈值
    "range_rsi_sell": 60,      # 横盘RSI卖出阈值
    "trend_rsi_max": 75,       # 趋势RSI上限
    "down_rsi_buy": 30,        # 下跌RSI买入阈值
    "down_rsi_sell": 70,       # 下跌RSI卖出阈值
}

def auto_strategy_signal(df, market, thresholds=None):
    if thresholds is None:
        thresholds = SIGNAL_THRESHOLDS
    close = df.close.values
    atr = ATR(df.high, df.low, df.close).iloc[-1]
    rsi = RSI(df.close).iloc[-1]
    last = close[-1]
    ema20 = EMA(df.close, 20).iloc[-1]
    ema60 = EMA(df.close, 60).iloc[-1]

    if market == "PANIC":
        return 0

    # 横盘：ATR动态网格
    if market == "RANGE":
        ma20 = np.mean(close[-20:])
        if last < ma20 - thresholds["range_atr_mult"] * atr and rsi < thresholds["range_rsi_buy"]:
            return 1
        if last > ma20 + thresholds["range_atr_mult"] * atr and rsi > thresholds["range_rsi_sell"]:
            return -1

    # 上涨：趋势跟随
    if market == "STRONG_UP":
        if last > close[-2] and close[-2] > close[-3] and rsi < thresholds["trend_rsi_max"] and last > ema20:
            return 1

    # 下跌：支撑压力
    if market == "STRONG_DOWN":
        if last < np.min(close[-10:]) and rsi < thresholds["down_rsi_buy"]:
            return 1
        if last > np.max(close[-10:]) and rsi > thresholds["down_rsi_sell"]:
            return -1
    return 0

# ===================== 【核心4】ML优化仓位&步长 =====================
def ml_optimized_position(market, capital, price, atr):
    mul = {
        "RANGE": 0.9, "STRONG_UP": 0.8,
        "STRONG_DOWN": 0.3, "PANIC": 0.0
    }.get(market, 0.4)

    risk_amount = capital * SINGLE_RISK
    stop = 1.5 * atr
    pos = risk_amount / stop if stop > 0 else 0
    pos = min(pos, capital * mul / price)
    return max(0.0, pos)

# ===================== 【核心5】交易执行引擎 =====================
class AdaptiveMLStrategy:
    def __init__(self, initial_balance=100000):
        self.ml = MLPersistentLearner()
        self.capital = initial_balance
        self.pos = 0
        self.cost_price = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.equity_curve = [initial_balance]
        self.initial_balance = initial_balance
        self._signal_thresholds = dict(SIGNAL_THRESHOLDS)
        self._atr_multiplier = 1.5

    def net_value(self, price):
        return self.capital + self.pos * price

    def close_all(self, price):
        if self.pos == 0:
            return
        if self.pos > 0:
            pnl = self.pos * (price - self.cost_price) - self.pos * price * FEE_RATE
            self.capital += self.pos * price - self.pos * price * FEE_RATE
        else:
            pnl = (-self.pos) * (self.cost_price - price) - (-self.pos) * price * FEE_RATE
            self.capital += (-self.pos)*self.cost_price - (-self.pos)*price - (-self.pos)*price*FEE_RATE
        if pnl > 0:
            self.win_count += 1
        self.pos = 0
        self.cost_price = 0
        self.trade_count += 1

    def open_long(self, price, qty):
        cost = qty * price * (1 + FEE_RATE)
        if cost > self.capital:
            return
        self.capital -= cost
        self.pos = qty
        self.cost_price = price
        self.trade_count += 1

    def _downtrend_block(self, data) -> bool:
        """日线趋势闸门：近20根bar累计下跌超过2%则阻止买入（震荡/上涨放行）。
        复用策略已收到的data.close，不需要外部额外传入日线数据。"""
        try:
            closes = data.close.values
        except Exception:
            return False
        if len(closes) < 21:
            return False
        return closes[-21] > closes[-1] * 1.02

    def update_price(self, current_price, data):
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据
            
        Returns:
            交易结果
        """
        # 计算净值
        nv = self.net_value(current_price)
        self.equity_curve.append(nv)

        # 回撤风控
        max_equity = max(self.equity_curve)
        drawdown = (max_equity - nv) / max_equity
        if drawdown > MAX_DRAW_DOWN:
            self.close_all(current_price)
            return {
                "action": "sell",
                "quantity": self.pos,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": "risk_control"
            }

        # 自动分类 + 自动策略
        market = auto_classify_market(data)
        signal = auto_strategy_signal(data, market, self._signal_thresholds)
        atr = ATR(data.high, data.low, data.close).iloc[-1]
        pos_size = ml_optimized_position(market, self.capital, current_price, atr)

        # 执行交易（买入前加日线趋势闸门：单边下跌>2%时不开多）
        if signal == 1 and self.pos <= 0 and not self._downtrend_block(data):
            self.close_all(current_price)
            self.open_long(current_price, pos_size)
            return {
                "action": "buy",
                "quantity": pos_size,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": f"{market}_buy"
            }
        elif signal == -1 and self.pos >= 0:
            self.close_all(current_price)
            return {
                "action": "sell",
                "quantity": self.pos,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": f"{market}_sell"
            }

        # ML 永久学习
        ret = (nv - self.initial_balance) / self.initial_balance
        self.ml.update_market_result(market, ret, 0.5)

        return {
            "action": "hold",
            "balance": self.capital,
            "position": self.pos,
            "market_type": market
        }

    def save_model(self, filepath):
        data = {
            'ml_data': self.ml.data,
            'capital': self.capital,
            'trade_count': self.trade_count,
            'win_count': self.win_count,
            'equity_curve': self.equity_curve[-1000:] if len(self.equity_curve) > 1000 else self.equity_curve
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_model(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.ml.data = data.get('ml_data', self.ml.data)
        self.capital = data.get('capital', self.capital)
        self.trade_count = data.get('trade_count', self.trade_count)
        self.win_count = data.get('win_count', self.win_count)
        self.equity_curve = data.get('equity_curve', [self.initial_balance])

    def get_param_space(self):
        return {
            'SINGLE_RISK': {'min': 0.001, 'max': 0.02, 'step': 0.001, 'default': SINGLE_RISK},
            'MAX_DRAW_DOWN': {'min': 0.02, 'max': 0.20, 'step': 0.01, 'default': MAX_DRAW_DOWN},
            'ATR_MULTIPLIER': {'min': 0.5, 'max': 3.0, 'step': 0.1, 'default': 1.5},
            'market_types': list(TARGET_PROFIT.keys()),
            'position_mult': {'RANGE': (0.5, 1.0), 'STRONG_UP': (0.4, 0.9), 'STRONG_DOWN': (0.1, 0.5), 'PANIC': (0.0, 0.1)},
            'step_coef': {'RANGE': (0.3, 1.2), 'STRONG_UP': (0.5, 1.5), 'STRONG_DOWN': (0.2, 0.8)},
            'range_atr_mult': [0.05, 0.08, 0.10, 0.12, 0.15],
            'range_rsi_buy': [30, 35, 40, 45, 50],
            'range_rsi_sell': [50, 55, 60, 65, 70],
            'trend_rsi_max': [60, 65, 70, 75, 80],
            'down_rsi_buy': [20, 25, 30, 35, 40],
            'down_rsi_sell': [55, 60, 65, 70, 75],
        }

    def get_adaptive_params(self, market_state=None, atr=None, volatility=None):
        params = {
            'RANGE': {'single_risk': SINGLE_RISK, 'max_drawdown': MAX_DRAW_DOWN, 'atr_multiplier': 1.5, 'position_mult': 0.9},
            'STRONG_UP': {'single_risk': SINGLE_RISK * 1.2, 'max_drawdown': MAX_DRAW_DOWN * 0.8, 'atr_multiplier': 1.2, 'position_mult': 0.8},
            'STRONG_DOWN': {'single_risk': SINGLE_RISK * 0.5, 'max_drawdown': MAX_DRAW_DOWN * 1.5, 'atr_multiplier': 2.0, 'position_mult': 0.3},
            'PANIC': {'single_risk': 0.0, 'max_drawdown': MAX_DRAW_DOWN * 2.0, 'atr_multiplier': 3.0, 'position_mult': 0.0}
        }
        if market_state and market_state in params:
            result = params[market_state].copy()
            if atr is not None:
                result['atr_multiplier'] = max(0.5, min(3.0, atr / (self.cost_price or 100) * 100))
            if volatility is not None and volatility > 0.03:
                result['single_risk'] *= 0.7
                result['position_mult'] *= 0.7
            return result
        return params

    def apply_adaptive_params(self, params):
        if 'single_risk' in params:
            global SINGLE_RISK
            SINGLE_RISK = params['single_risk']
        if 'atr_multiplier' in params:
            self._atr_multiplier = params['atr_multiplier']
        # 信号阈值参数
        for key in ['range_atr_mult', 'range_rsi_buy', 'range_rsi_sell',
                     'trend_rsi_max', 'down_rsi_buy', 'down_rsi_sell']:
            if key in params:
                self._signal_thresholds[key] = params[key]
        if 'position_mult' in params:
            self._position_mult = params['position_mult']

    def update_model_parameters(self):
        """根据近期表现动态调整市场分类参数"""
        market_returns = self.ml.data.get("market_return", {})
        for mkt in ["RANGE", "STRONG_UP", "STRONG_DOWN"]:
            records = market_returns.get(mkt, [])
            if len(records) < 5:
                continue
            recent = records[-5:]
            avg_ret = sum(r["return"] for r in recent) / len(recent)
            current_step = self.ml.data["best_step"].get(mkt, 0.5)
            current_pos = self.ml.data["best_position"].get(mkt, 0.5)
            if avg_ret > 0.02:
                self.ml.data["best_step"][mkt] = min(1.0, current_step * 1.05)
                self.ml.data["best_position"][mkt] = min(1.0, current_pos * 1.05)
            elif avg_ret < -0.01:
                self.ml.data["best_step"][mkt] = max(0.1, current_step * 0.95)
                self.ml.data["best_position"][mkt] = max(0.1, current_pos * 0.95)
        self.ml.save()

    def get_performance(self):
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        final_value = self.net_value(0) if self.pos == 0 else self.net_value(self.cost_price)
        total_return = (final_value - self.initial_balance) / self.initial_balance
        win_rate = self.win_count / (self.trade_count + 1e-8)
        
        return {
            "initial_balance": self.initial_balance,
            "final_balance": final_value,
            "total_return": total_return * 100,
            "trade_count": self.trade_count,
            "win_rate": win_rate * 100,
            "max_drawdown": max([(max(self.equity_curve[:i+1]) - self.equity_curve[i]) / max(self.equity_curve[:i+1]) for i in range(1, len(self.equity_curve))], default=0) * 100
        }

# ===================== 回测入口 =====================
if __name__ == "__main__":
    # 生成模拟数据
    dates = pd.date_range("2024-01-01", periods=28800, freq="5min")
    df = pd.DataFrame({
        "datetime": dates,
        "open":  np.random.uniform(76.56,132.39,28800),
        "high":  np.random.uniform(76.56,132.39,28800),
        "low":   np.random.uniform(76.56,132.39,28800),
        "close": np.random.uniform(76.56,132.39,28800),
        "volume": np.random.randint(500,50000,28800)
    })

    # 初始化策略
    strategy = AdaptiveMLStrategy()
    
    # 运行回测
    for i in range(120, len(df)):
        strategy.update_price(df.close.iloc[i], df.iloc[:i])

    # 获取性能指标
    performance = strategy.get_performance()

    # 输出结果
    print("="*60)
    print("【机构终极版】市场自动切换 + ML永久传承策略")
    print(f"初始资金：{performance['initial_balance']:.0f}")
    print(f"最终净值：{performance['final_balance']:.2f}")
    print(f"总收益率：{performance['total_return']:.2f}%")
    print(f"交易次数：{performance['trade_count']}")
    print(f"胜率：{performance['win_rate']:.2f}%")
    print(f"最大回撤：{performance['max_drawdown']:.2f}%")
    print(f"机器学习：已永久保存 → {ML_FILE}")
    print("="*60)
