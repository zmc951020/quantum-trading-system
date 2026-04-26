#!/usr/bin/env python3
"""
趋势交易相切换策略实现
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional

class MovingAveragesStrategy:
    """
    移动平均线策略
    """
    
    def __init__(self, short_window: int = 10, 
                 medium_window: int = 20, 
                 long_window: int = 30):
        """
        初始化移动平均线策略
        
        Args:
            short_window: 短期移动平均线窗口
            medium_window: 中期移动平均线窗口
            long_window: 长期移动平均线窗口
        """
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
    
    def calculate_indicators(self, data: pd.Series) -> pd.DataFrame:
        """
        计算移动平均线指标
        
        Args:
            data: 价格数据
            
        Returns:
            包含指标的DataFrame
        """
        df = pd.DataFrame(data, columns=['price'])
        df['MA10'] = df['price'].rolling(window=self.short_window).mean()
        df['MA20'] = df['price'].rolling(window=self.medium_window).mean()
        df['MA30'] = df['price'].rolling(window=self.long_window).mean()
        return df
    
    def generate_signals(self, data: pd.Series) -> pd.DataFrame:
        """
        生成交易信号
        
        Args:
            data: 价格数据
            
        Returns:
            包含信号的DataFrame
        """
        df = self.calculate_indicators(data)
        
        # 生成信号
        df['signal'] = 0
        
        # 短期均线上穿中期均线且中期均线上穿长期均线 - 买入信号
        df.loc[(df['MA10'] > df['MA20']) & (df['MA20'] > df['MA30']), 'signal'] = 1
        
        # 短期均线下穿中期均线且中期均线下穿长期均线 - 卖出信号
        df.loc[(df['MA10'] < df['MA20']) & (df['MA20'] < df['MA30']), 'signal'] = -1
        
        return df
    
    def get_signal(self, data: pd.Series) -> int:
        """
        获取当前交易信号
        
        Args:
            data: 价格数据
            
        Returns:
            交易信号 (-1: 卖出, 0: 持有, 1: 买入)
        """
        df = self.generate_signals(data)
        return df['signal'].iloc[-1]

class RSIStrategy:
    """
    相对强弱指数策略
    """
    
    def __init__(self, window: int = 14, 
                 overbought_threshold: int = 70, 
                 oversold_threshold: int = 30):
        """
        初始化RSI策略
        
        Args:
            window: RSI计算窗口
            overbought_threshold: 超买阈值
            oversold_threshold: 超卖阈值
        """
        self.window = window
        self.overbought_threshold = overbought_threshold
        self.oversold_threshold = oversold_threshold
    
    def calculate_rsi(self, data: pd.Series) -> pd.Series:
        """
        计算RSI指标
        
        Args:
            data: 价格数据
            
        Returns:
            RSI序列
        """
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def generate_signals(self, data: pd.Series) -> pd.DataFrame:
        """
        生成交易信号
        
        Args:
            data: 价格数据
            
        Returns:
            包含信号的DataFrame
        """
        df = pd.DataFrame(data, columns=['price'])
        df['RSI'] = self.calculate_rsi(data)
        
        # 生成信号
        df['signal'] = 0
        
        # RSI低于超卖阈值 - 买入信号
        df.loc[df['RSI'] < self.oversold_threshold, 'signal'] = 1
        
        # RSI高于超买阈值 - 卖出信号
        df.loc[df['RSI'] > self.overbought_threshold, 'signal'] = -1
        
        return df
    
    def get_signal(self, data: pd.Series) -> int:
        """
        获取当前交易信号
        
        Args:
            data: 价格数据
            
        Returns:
            交易信号 (-1: 卖出, 0: 持有, 1: 买入)
        """
        df = self.generate_signals(data)
        return df['signal'].iloc[-1]

class TrendSwitchingStrategy:
    """
    趋势交易相切换策略
    """
    
    def __init__(self):
        """
        初始化趋势交易相切换策略
        """
        self.ma_strategy = MovingAveragesStrategy()
        self.rsi_strategy = RSIStrategy()
    
    def get_combined_signal(self, data: pd.Series) -> int:
        """
        获取组合交易信号
        
        Args:
            data: 价格数据
            
        Returns:
            交易信号 (-1: 卖出, 0: 持有, 1: 买入)
        """
        ma_signal = self.ma_strategy.get_signal(data)
        rsi_signal = self.rsi_strategy.get_signal(data)
        
        # 组合信号
        if ma_signal == 1 and rsi_signal == 1:
            return 1  # 强买入信号
        elif ma_signal == -1 and rsi_signal == -1:
            return -1  # 强卖出信号
        elif ma_signal == 1:
            return 1  # 买入信号
        elif ma_signal == -1:
            return -1  # 卖出信号
        else:
            return 0  # 持有信号
    
    def switch_strategy(self, data: pd.Series) -> str:
        """
        根据市场趋势切换策略
        
        Args:
            data: 价格数据
            
        Returns:
            推荐策略
        """
        signal = self.get_combined_signal(data)
        
        if signal == 1:
            return "trend_following"  # 趋势跟踪策略
        elif signal == -1:
            return "mean_reversion"  # 均值回归策略
        else:
            return "grid_trading"  # 网格化交易策略
