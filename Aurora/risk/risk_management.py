#!/usr/bin/env python3
"""
风险管理模块实现
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import Dict, List, Optional

class RiskManager:
    """
    风险管理模块
    """
    
    def __init__(self, confidence_level: float = 0.95):
        """
        初始化风险管理模块
        
        Args:
            confidence_level: 置信水平
        """
        self.confidence_level = confidence_level
    
    def calculate_var_historical(self, returns: pd.Series, lookback: int = 252) -> float:
        """
        计算历史VaR (Value at Risk)
        
        Args:
            returns: 收益率序列
            lookback: 回溯期
            
        Returns:
            VaR值
        """
        # 获取最近的收益率数据
        recent_returns = returns.tail(lookback)
        
        # 计算历史VaR
        var = -np.percentile(recent_returns, (1 - self.confidence_level) * 100)
        
        return var
    
    def calculate_var_parametric(self, returns: pd.Series) -> float:
        """
        计算参数法VaR
        
        Args:
            returns: 收益率序列
            
        Returns:
            VaR值
        """
        # 计算均值和标准差
        mean = returns.mean()
        std = returns.std()
        
        # 计算参数法VaR
        var = - (mean + std * norm.ppf(1 - self.confidence_level))
        
        return var
    
    def calculate_es_historical(self, returns: pd.Series, lookback: int = 252) -> float:
        """
        计算历史ES (Expected Shortfall)
        
        Args:
            returns: 收益率序列
            lookback: 回溯期
            
        Returns:
            ES值
        """
        # 获取最近的收益率数据
        recent_returns = returns.tail(lookback)
        
        # 计算历史VaR
        var = self.calculate_var_historical(returns, lookback)
        
        # 计算ES
        es = -recent_returns[recent_returns <= -var].mean()
        
        return es
    
    def calculate_es_parametric(self, returns: pd.Series) -> float:
        """
        计算参数法ES
        
        Args:
            returns: 收益率序列
            
        Returns:
            ES值
        """
        # 计算均值和标准差
        mean = returns.mean()
        std = returns.std()
        
        # 计算参数法ES
        var = self.calculate_var_parametric(returns)
        es = - (mean + std * norm.pdf(norm.ppf(1 - self.confidence_level)) / (1 - self.confidence_level))
        
        return es
    
    def calculate_greeks(self, option_price: float, underlying_price: float, 
                       strike_price: float, time_to_expiry: float, 
                       risk_free_rate: float, volatility: float) -> Dict[str, float]:
        """
        计算期权希腊字母
        
        Args:
            option_price: 期权价格
            underlying_price: 标的资产价格
            strike_price: 行权价格
            time_to_expiry: 到期时间（年）
            risk_free_rate: 无风险利率
            volatility: 波动率
            
        Returns:
            希腊字母字典
        """
        # 计算d1和d2
        d1 = (np.log(underlying_price / strike_price) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / \
             (volatility * np.sqrt(time_to_expiry))
        d2 = d1 - volatility * np.sqrt(time_to_expiry)
        
        # 计算Delta
        delta = norm.cdf(d1)
        
        # 计算Gamma
        gamma = norm.pdf(d1) / (underlying_price * volatility * np.sqrt(time_to_expiry))
        
        # 计算Theta
        theta = - (underlying_price * norm.pdf(d1) * volatility) / (2 * np.sqrt(time_to_expiry)) - \
                risk_free_rate * strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        
        # 计算Vega
        vega = underlying_price * norm.pdf(d1) * np.sqrt(time_to_expiry)
        
        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega
        }
    
    def get_position_size(self, account_balance: float, var: float, max_loss_per_trade: float = 0.01) -> float:
        """
        计算最优持仓大小
        
        Args:
            account_balance: 账户余额
            var: 风险价值
            max_loss_per_trade: 每笔交易最大损失比例
            
        Returns:
            最优持仓大小
        """
        # 计算最大损失金额
        max_loss_amount = account_balance * max_loss_per_trade
        
        # 计算最优持仓大小
        position_size = max_loss_amount / var
        
        return position_size
    
    def check_risk_limits(self, position_size: float, var: float, account_balance: float, 
                         max_position: float = None, max_var: float = 0.05) -> Dict[str, bool]:
        """
        检查风险限制
        
        Args:
            position_size: 持仓大小
            var: 风险价值
            account_balance: 账户余额
            max_position: 最大持仓限制
            max_var: 最大VaR限制（占账户余额的比例）
            
        Returns:
            风险检查结果
        """
        # 检查持仓限制
        position_ok = True
        if max_position and position_size > max_position:
            position_ok = False
        
        # 检查VaR限制
        var_ok = True
        if var > account_balance * max_var:
            var_ok = False
        
        return {
            "position_ok": position_ok,
            "var_ok": var_ok,
            "overall_ok": position_ok and var_ok
        }
