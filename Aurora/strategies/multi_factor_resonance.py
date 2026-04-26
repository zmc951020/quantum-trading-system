#!/usr/bin/env python3
"""
多因子共振趋势策略
融合趋势跟踪 + 动量择时 + 波动率风控 + 资金管理
"""

import numpy as np
import pandas as pd
import talib as ta
from typing import Dict, List, Optional, Any


class MultiFactorResonanceStrategy:
    """
    多因子共振趋势策略
    融合趋势跟踪+动量择时+波动率风控+资金管理
    """
    
    def __init__(self, initial_balance: float = 100000, risk_per_trade: float = 0.02,
                 ma_fast: int = 20, ma_medium: int = 50, ma_slow: int = 120,
                 rsi_period: int = 14, atr_period: int = 14, bb_period: int = 20, bb_std: float = 2):
        """
        初始化多因子共振策略
        
        Args:
            initial_balance: 初始资金
            risk_per_trade: 单笔交易风险比例
            ma_fast: 快速移动平均线周期
            ma_medium: 中速移动平均线周期
            ma_slow: 慢速移动平均线周期
            rsi_period: RSI周期
            atr_period: ATR周期
            bb_period: 布林带周期
            bb_std: 布林带标准差
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        
        # 策略参数
        self.ma_fast = ma_fast
        self.ma_medium = ma_medium
        self.ma_slow = ma_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        
        # 持仓状态
        self.position = 0  # 0: 空仓, >0: 持有多单数量
        self.entry_price = 0
        self.stop_loss = 0
        self.trades = []
        self.price_history = []
        self.equity_curve = []
    
    def calculate_indicators(self, df: pd.Series) -> pd.DataFrame:
        """
        计算所有技术指标
        
        Args:
            df: 价格数据
            
        Returns:
            包含技术指标的DataFrame
        """
        # 转换为DataFrame
        if isinstance(df, pd.Series):
            df = pd.DataFrame({'close': df})
        
        # 计算OHLC数据（如果只有收盘价）
        if 'open' not in df.columns:
            df['open'] = df['close']
        if 'high' not in df.columns:
            df['high'] = df['close']
        if 'low' not in df.columns:
            df['low'] = df['close']
        if 'volume' not in df.columns:
            df['volume'] = 1.0
        
        # 移动平均线
        df['ma_fast'] = ta.SMA(df['close'], timeperiod=self.ma_fast)
        df['ma_medium'] = ta.SMA(df['close'], timeperiod=self.ma_medium)
        df['ma_slow'] = ta.SMA(df['close'], timeperiod=self.ma_slow)
        
        # RSI
        df['rsi'] = ta.RSI(df['close'], timeperiod=self.rsi_period)
        
        # ATR
        df['atr'] = ta.ATR(df['high'], df['low'], df['close'], timeperiod=self.atr_period)
        
        # 布林带
        df['bb_mid'], df['bb_upper'], df['bb_lower'] = ta.BBANDS(
            df['close'], timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std
        )
        
        # OBV
        df['obv'] = ta.OBV(df['close'], df['volume'])
        df['obv_ma'] = ta.SMA(df['obv'], timeperiod=self.ma_fast)
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = ta.MACD(df['close'])
        
        return df.dropna()
    
    def generate_signals(self, df: pd.Series) -> pd.DataFrame:
        """
        生成交易信号
        
        Args:
            df: 价格数据
            
        Returns:
            包含交易信号的DataFrame
        """
        df = self.calculate_indicators(df)
        
        # 买入因子
        factor_trend = (df['ma_fast'] > df['ma_medium']) & (df['ma_medium'] > df['ma_slow'])
        factor_momentum = (df['rsi'] > 50) & (df['rsi'] < 70)
        factor_volatility = (df['close'] > df['bb_mid']) & (df['close'] < df['bb_upper'])
        factor_volume = df['obv'] > df['obv_ma']
        
        # 共振买入信号：4选3
        df['buy_signal'] = (factor_trend.astype(int) + 
                           factor_momentum.astype(int) + 
                           factor_volatility.astype(int) + 
                           factor_volume.astype(int)) >= 3

        # 卖出基础信号
        df['sell_base'] = (
            (df['ma_fast'] < df['ma_medium']) |
            (df['rsi'] > 75) |
            (df['close'] < df['bb_lower'])
        )
        
        df['sell_signal'] = False
        return df
    
    def calculate_position_size(self, atr: float, current_price: float) -> float:
        """
        根据风险计算仓位大小
        
        Args:
            atr: 平均真实波幅
            current_price: 当前价格
            
        Returns:
            仓位大小
        """
        if atr <= 0 or current_price <= 0:
            return 0
        risk_amount = self.current_balance * self.risk_per_trade
        risk_per_unit = 2 * atr
        position_size = risk_amount / risk_per_unit
        max_units = self.current_balance / current_price * 0.95  # 留5%资金缓冲
        return max(0, min(position_size, max_units))
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 历史价格数据
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 计算当前权益
        if self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance
        self.equity_curve.append({'price': current_price, 'equity': current_equity})
        
        # 生成交易信号
        if data is not None and len(data) >= max(self.ma_slow, self.rsi_period, self.atr_period, self.bb_period):
            df = self.generate_signals(data)
            latest = df.iloc[-1]
            
            # 空仓：检查买入
            if self.position == 0:
                if latest['buy_signal']:
                    pos_size = self.calculate_position_size(latest['atr'], current_price)
                    if pos_size > 0:
                        self.position = pos_size
                        self.entry_price = current_price
                        self.stop_loss = current_price - 2 * latest['atr']
                        self.current_balance -= pos_size * current_price
                        
                        self.trades.append({
                            'type': 'BUY',
                            'price': current_price,
                            'size': pos_size,
                            'stop_loss': self.stop_loss
                        })
                        
                        return {
                            "action": "buy",
                            "quantity": pos_size,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position
                        }
            # 持仓：检查卖出/止损
            else:
                stop_triggered = current_price < self.stop_loss
                sell_signal = latest['sell_base']
                if sell_signal or stop_triggered:
                    profit = self.position * (current_price - self.entry_price)
                    self.current_balance += self.position * current_price  # 卖出仓位
                    reason = "止损" if stop_triggered else "信号卖出"
                    
                    self.trades.append({
                        'type': 'SELL',
                        'price': current_price,
                        'profit': profit,
                        'reason': reason
                    })
                    
                    position = self.position
                    self.position = 0
                    self.entry_price = 0
                    self.stop_loss = 0
                    
                    return {
                        "action": "sell",
                        "quantity": position,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "profit": profit,
                        "reason": reason
                    }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self, current_price: float = None) -> Dict[str, float]:
        """
        获取策略性能
        
        Args:
            current_price: 当前价格
            
        Returns:
            性能指标
        """
        # 计算当前权益
        if current_price is not None and self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance
        
        # 计算绩效指标
        total_return = (current_equity - self.initial_balance) / self.initial_balance
        
        # 计算最大回撤
        max_drawdown = 0
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            if len(equity_df) > 1:
                rolling_max = equity_df['equity'].cummax()
                drawdown = (equity_df['equity'] - rolling_max) / rolling_max
                max_drawdown = drawdown.min()
        
        # 计算胜率
        win_rate = 0
        profits = [t['profit'] for t in self.trades if t['type'] == 'SELL']
        if profits:
            win_rate = sum(1 for p in profits if p > 0) / len(profits)
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "total_value": current_equity,
            "pnl": current_equity - self.initial_balance,
            "return": total_return,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(profits)
        }
