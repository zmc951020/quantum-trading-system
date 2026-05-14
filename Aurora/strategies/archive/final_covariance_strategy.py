# -*- coding: utf-8 -*-
"""
【机构终极版】
协变函数寻优 + 最大收益驻点 + 分市场机器学习 + 永久传承
最终优化版本
"""

import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

# ===================== 【机构标准】分市场目标 =====================
TARGET = {
    "RANGE":       {"sharpe": 3.0, "pos": 0.80, "step": 1.00, "stop": 1.50},
    "STRONG_UP":   {"sharpe": 2.5, "pos": 0.75, "step": 1.20, "stop": 2.00},
    "STRONG_DOWN": {"sharpe": 0.5, "pos": 0.25, "step": 0.60, "stop": 1.00},
    "PANIC":       {"sharpe": 0.0, "pos": 0.00, "step": 0.00, "stop": 0.00},
}

# ===================== 风险与成本 =====================
INIT_CAPITAL = 100000.0
FEE = 0.00015
SLIPPAGE = 0.0001
SINGLE_RISK = 0.005
MAX_DD = 0.08
ML_FILE = "ml_final_covariance_opt.json"

# ===================== 指标工具 =====================
def EMA(s, n):
    return s.ewm(span=n, adjust=False).mean()

def ATR(high, low, close, n=14):
    tr = np.maximum(high-low, abs(high-close.shift(1)), abs(low-close.shift(1)))
    return tr.rolling(n).mean()

def ADX(high, low, close, n=14):
    tr = np.maximum(high-low, abs(high-close.shift(1)), abs(low-close.shift(1)))
    atr = tr.rolling(n).mean()
    plus_di = 100 * np.maximum(high.diff(), 0).rolling(n).mean() / (atr + 1e-8)
    minus_di = 100 * np.maximum(-low.diff(), 0).rolling(n).mean() / (atr + 1e-8)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-8)
    return dx.rolling(n).mean()

def RSI(s, n=14):
    diff = s.diff()
    gain = diff.clip(lower=0).rolling(n).mean()
    loss = -diff.clip(upper=0).rolling(n).mean()
    rs = gain / (loss + 1e-8)
    return 100 - 100/(1+rs)

def BollingerBands(close, period=20, num_std=2):
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return upper, ma, lower

# ===================== 【核心】协变函数 + 最优驻点求解 =====================
class CovarianceML:
    def __init__(self):
        self.data = self.load()

    def load(self):
        if os.path.exists(ML_FILE):
            try:
                with open(ML_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # 如果JSON文件损坏，返回默认值
                return {
                    "opt_params": TARGET,
                    "cov_history": {},
                    "last_update": str(datetime.now())
                }
        return {
            "opt_params": TARGET,
            "cov_history": {},
            "last_update": str(datetime.now())
        }

    def save(self):
        self.data["last_update"] = str(datetime.now())
        with open(ML_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4)

    def optimal_params(self, market):
        return self.data["opt_params"].get(market, TARGET["RANGE"])

    # 【机构协变函数】求解最优驻点
    def update_optimal(self, market, ret, dd, trade_cnt, atr):
        if market not in self.data["cov_history"]:
            self.data["cov_history"][market] = []
        opt = self.data["opt_params"][market]
        sharpe = ret / (dd + 1e-3)

        # 非线性协变更新（核心）
        step = opt["step"] + 0.02 * (sharpe - opt["sharpe"])
        pos  = opt["pos"]  + 0.02 * (sharpe - opt["sharpe"]) * (1-dd*10)
        stop = opt["stop"] + 0.01 * (sharpe - opt["sharpe"])

        # 强约束（不越界）
        step = np.clip(step, 0.4, 1.4)
        pos  = np.clip(pos, 0.1, 0.9)
        stop = np.clip(stop, 0.8, 2.5)

        self.data["opt_params"][market] = {
            "sharpe": opt["sharpe"] + 0.05*(sharpe-opt["sharpe"]),
            "pos": round(pos,3),
            "step": round(step,3),
            "stop": round(stop,3)
        }
        self.data["cov_history"][market].append({
            "ret": round(ret,4), "dd": round(dd,4),
            "sharpe": round(sharpe,4), "time": str(datetime.now())
        })
        self.save()

# ===================== 市场分类 =====================
def get_market(df):
    close = df.close
    ema20 = EMA(close,20)
    ema60 = EMA(close,60)
    adx = ADX(df.high, df.low, close)
    vol = close.pct_change().rolling(30).std()
    trend = (ema20.iloc[-1]-ema60.iloc[-1])/(ema60.iloc[-1]+1e-8)
    if adx.iloc[-1]>20 and trend>0.005:
        return "STRONG_UP"
    if adx.iloc[-1]>20 and trend<-0.005:
        return "STRONG_DOWN"
    if vol.iloc[-1]>0.15:
        return "PANIC"
    return "RANGE"

# ===================== 策略信号 =====================
def signal(df, market, ml):
    close = df.close.values
    atr = ATR(df.high, df.low, df.close).iloc[-1]
    rsi = RSI(df.close).iloc[-1]
    last = close[-1]
    ema20 = EMA(df.close, 20).iloc[-1]
    ema60 = EMA(df.close, 60).iloc[-1]
    upper_band, middle_band, lower_band = BollingerBands(df.close)
    opt = ml.optimal_params(market)
    
    if market == "PANIC":
        return 0
    
    if market == "RANGE":
        ma20 = np.mean(close[-20:])
        if last < ma20 - 0.1*atr and rsi<45:
            return 1
        if last > ma20 + 0.1*atr and rsi>55:
            return -1
    
    if market == "STRONG_UP":
        if last > close[-2] and rsi<80:
            return 1
    
    if market == "STRONG_DOWN":
        if last < np.min(close[-10:]) and rsi<35:
            return 1
        if last > np.max(close[-10:]) and rsi>65:
            return -1
    
    return 0

# ===================== 交易引擎 =====================
class FinalCovarianceStrategy:
    def __init__(self, initial_balance=100000):
        self.ml = CovarianceML()
        self.capital = initial_balance
        self.pos = 0
        self.cost = 0
        self.equity = [initial_balance]
        self.trades = 0
        self.win_count = 0
        self.initial_balance = initial_balance
        self.market_type_analysis = {
            "RANGE": {"trades": 0, "wins": 0, "return": 0},
            "STRONG_UP": {"trades": 0, "wins": 0, "return": 0},
            "STRONG_DOWN": {"trades": 0, "wins": 0, "return": 0},
            "PANIC": {"trades": 0, "wins": 0, "return": 0}
        }

    def value(self, price):
        return self.capital + self.pos * price

    def close_all(self, price, market):
        if self.pos == 0:
            return
        initial_balance = self.capital + self.pos * self.cost
        if self.pos>0:
            pnl = self.pos * (price - self.cost) - self.pos * price * FEE
            self.capital += self.pos*price*(1-FEE)
        else:
            pnl = (-self.pos) * (self.cost - price) - (-self.pos) * price * FEE
            self.capital += (-self.pos)*(self.cost - price)*(1-FEE)
        if pnl > 0:
            self.win_count += 1
            if market in self.market_type_analysis:
                self.market_type_analysis[market]["wins"] += 1
        if market in self.market_type_analysis:
            self.market_type_analysis[market]["trades"] += 1
            self.market_type_analysis[market]["return"] += (self.capital - initial_balance)
        self.pos=0
        self.cost=0
        self.trades+=1

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
        val = self.value(current_price)
        self.equity.append(val)
        max_equity = max(self.equity)
        dd = (max_equity-val)/max_equity

        # 风控
        if dd > MAX_DD:
            self.close_all(current_price, "RISK_CONTROL")
            return {
                "action": "sell",
                "quantity": self.pos,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": "risk_control"
            }

        market = get_market(data)
        sig = signal(data, market, self.ml)
        opt = self.ml.optimal_params(market)
        atr = ATR(data.high, data.low, data.close).iloc[-1]

        # 仓位 = 协变最优
        risk_amt = self.capital * SINGLE_RISK
        qty = risk_amt / (opt["stop"]*atr + 1e-8) if atr>0 else 0
        qty = min(qty, self.capital*opt["pos"]/current_price)

        # 执行交易
        if sig == 1 and self.pos<=0:
            self.close_all(current_price, market)
            self.pos = qty
            self.cost = current_price
            self.capital -= qty*current_price*(1+FEE)
            return {
                "action": "buy",
                "quantity": qty,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": f"{market}_buy"
            }
        elif sig == -1 and self.pos>=0:
            self.close_all(current_price, market)
            return {
                "action": "sell",
                "quantity": self.pos,
                "price": current_price,
                "balance": self.capital,
                "position": self.pos,
                "reason": f"{market}_sell"
            }

        # 机器学习更新协变最优驻点
        ret = (val - self.equity[0])/self.equity[0]
        self.ml.update_optimal(market, ret, dd, self.trades, atr)

        return {
            "action": "hold",
            "balance": self.capital,
            "position": self.pos,
            "market_type": market
        }

    def get_performance(self):
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        final_value = self.value(0) if self.pos == 0 else self.value(self.cost)
        total_return = (final_value - self.initial_balance) / self.initial_balance
        win_rate = self.win_count / (self.trades + 1e-8)
        
        return {
            "initial_balance": self.initial_balance,
            "final_balance": final_value,
            "total_return": total_return * 100,
            "trade_count": self.trades,
            "win_rate": win_rate * 100,
            "max_drawdown": max([(max(self.equity[:i+1]) - self.equity[i]) / max(self.equity[:i+1]) for i in range(1, len(self.equity))], default=0) * 100,
            "market_type_analysis": self.market_type_analysis
        }

# ===================== 回测入口 =====================
if __name__ == "__main__":
    # 生成模拟数据（分钟级）
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
    strategy = FinalCovarianceStrategy()
    
    # 运行回测
    for i in range(120, len(df)):
        strategy.update_price(df.close.iloc[i], df.iloc[:i])

    # 获取性能指标
    performance = strategy.get_performance()

    # 输出结果
    print("="*60)
    print("【机构终极版】协变函数寻优 + 最大收益驻点 + ML永久传承")
    print(f"初始资金：{performance['initial_balance']:.0f}")
    print(f"最终净值：{performance['final_balance']:.2f}")
    print(f"总收益率：{performance['total_return']:.2f}%")
    print(f"交易次数：{performance['trade_count']}")
    print(f"胜率：{performance['win_rate']:.2f}%")
    print(f"最大回撤：{performance['max_drawdown']:.2f}%")
    print(f"学习文件：{ML_FILE} (永久保存最优参数)")
    print("="*60)
    
    # 输出各市场类型表现
    print("各市场类型表现分析:")
    print("市场类型                  交易次数       胜率          收益率")
    print("------------------------------------------------------------")
    
    for market_type, analysis in performance['market_type_analysis'].items():
        win_rate = (analysis["wins"] / analysis["trades"] * 100) if analysis["trades"] > 0 else 0
        return_rate = (analysis["return"] / performance['initial_balance'] * 100) if analysis["trades"] > 0 else 0
        print(f"{market_type:<24} {analysis['trades']:<10} {win_rate:<10.2f}% {return_rate:<10.2f}%")
    
    print("="*60)
    print("测试完成！")
