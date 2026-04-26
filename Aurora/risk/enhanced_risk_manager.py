#!/usr/bin/env python3
"""
增强版风险管理模块
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import Dict, List, Optional
from risk.risk_management import RiskManager

class EnhancedRiskManager(RiskManager):
    """
    增强版风险管理模块
    - 市场状态风控
    - 基于凯利公式的仓位管理
    - 动态止损止盈
    - 实时风险监控
    - 压力测试
    """
    
    def __init__(self, confidence_level: float = 0.95, config=None):
        """
        初始化增强版风险管理模块
        
        Args:
            confidence_level: 置信水平
            config: 配置参数
        """
        super().__init__(confidence_level)
        
        if config is None:
            config = {}
        
        # 市场状态风控参数
        self.regime_risk_params = {
            0: {  # 低波动趋势市
                'max_position_pct': 0.95,
                'stop_loss_pct': 0.05,
                'take_profit_pct': 0.15,
                'max_var_pct': 0.05,
                'leverage': 1.5
            },
            1: {  # 高波动震荡市
                'max_position_pct': 0.6,
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.10,
                'max_var_pct': 0.03,
                'leverage': 1.0
            },
            2: {  # 危机模式
                'max_position_pct': 0.1,
                'stop_loss_pct': 0.02,
                'take_profit_pct': 0.05,
                'max_var_pct': 0.01,
                'leverage': 0.5
            }
        }
        
        # 凯利公式参数
        self.edge = config.get('edge', 0.05)  # 预期优势
        self.odds = config.get('odds', 1.5)  # 赔率
        self.max_kelly_pct = config.get('max_kelly_pct', 0.3)  # 最大凯利仓位比例
        
        # 动态止损止盈参数
        self.trailing_stop_pct = config.get('trailing_stop_pct', 0.08)
        self.moving_take_profit_pct = config.get('moving_take_profit_pct', 0.05)
        
        # 风险监控参数
        self.risk_check_interval = config.get('risk_check_interval', 60)  # 风险检查间隔（秒）
        self.max_drawdown_limit = config.get('max_drawdown_limit', 0.15)  # 最大回撤限制
        self.max_daily_loss = config.get('max_daily_loss', 0.02)  # 单日最大亏损
        
        # 压力测试参数
        self.stress_scenarios = {
            'flash_crash': {'returns': -0.05, 'probability': 0.01},
            'market_correction': {'returns': -0.10, 'probability': 0.05},
            'black_swan': {'returns': -0.20, 'probability': 0.001}
        }
    
    def calculate_kelly_position(self, account_balance: float, win_rate: float, win_loss_ratio: float) -> float:
        """
        基于凯利公式计算最优持仓
        
        Args:
            account_balance: 账户余额
            win_rate: 胜率
            win_loss_ratio: 盈亏比
            
        Returns:
            最优持仓金额
        """
        # 计算凯利比率
        kelly_pct = win_rate - (1 - win_rate) / win_loss_ratio
        kelly_pct = max(0, min(kelly_pct, self.max_kelly_pct))
        
        # 计算最优持仓金额
        optimal_position = account_balance * kelly_pct
        
        return optimal_position
    
    def get_regime_based_risk_params(self, regime: int) -> Dict[str, float]:
        """
        根据市场状态获取风险参数
        
        Args:
            regime: 市场状态
            
        Returns:
            风险参数
        """
        return self.regime_risk_params.get(regime, self.regime_risk_params[1])
    
    def calculate_position_size(self, account_balance: float, regime: int, win_rate: float = 0.5, win_loss_ratio: float = 1.0) -> float:
        """
        计算基于市场状态和凯利公式的最优持仓大小
        
        Args:
            account_balance: 账户余额
            regime: 市场状态
            win_rate: 胜率
            win_loss_ratio: 盈亏比
            
        Returns:
            最优持仓大小
        """
        # 获取市场状态对应的风险参数
        params = self.get_regime_based_risk_params(regime)
        
        # 基于凯利公式计算最优持仓
        kelly_position = self.calculate_kelly_position(account_balance, win_rate, win_loss_ratio)
        
        # 基于市场状态的最大持仓限制
        max_position = account_balance * params['max_position_pct']
        
        # 取两者中的较小值
        optimal_position = min(kelly_position, max_position)
        
        # 应用杠杆
        optimal_position *= params['leverage']
        
        return optimal_position
    
    def calculate_stop_loss_take_profit(self, entry_price: float, regime: int, current_price: float = None) -> Dict[str, float]:
        """
        计算止损止盈价格
        
        Args:
            entry_price: 入场价格
            regime: 市场状态
            current_price: 当前价格（用于移动止盈）
            
        Returns:
            止损止盈价格
        """
        # 获取市场状态对应的风险参数
        params = self.get_regime_based_risk_params(regime)
        
        # 计算固定止损价格
        stop_loss_price = entry_price * (1 - params['stop_loss_pct'])
        
        # 计算止盈价格
        if current_price and current_price > entry_price:
            # 移动止盈
            take_profit_price = current_price * (1 - self.moving_take_profit_pct)
        else:
            # 固定止盈
            take_profit_price = entry_price * (1 + params['take_profit_pct'])
        
        return {
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price
        }
    
    def calculate_trailing_stop(self, highest_price: float, current_price: float) -> float:
        """
        计算移动止损价格
        
        Args:
            highest_price: 最高价格
            current_price: 当前价格
            
        Returns:
            移动止损价格
        """
        return highest_price * (1 - self.trailing_stop_pct)
    
    def check_regime_based_risk(self, position_size: float, account_balance: float, regime: int, returns: pd.Series) -> Dict[str, bool]:
        """
        根据市场状态检查风险
        
        Args:
            position_size: 持仓大小
            account_balance: 账户余额
            regime: 市场状态
            returns: 收益率序列
            
        Returns:
            风险检查结果
        """
        # 获取市场状态对应的风险参数
        params = self.get_regime_based_risk_params(regime)
        
        # 计算VaR
        var = self.calculate_var_historical(returns)
        
        # 检查持仓限制
        max_position = account_balance * params['max_position_pct']
        position_ok = position_size <= max_position
        
        # 检查VaR限制
        var_ok = var <= account_balance * params['max_var_pct']
        
        # 检查杠杆限制
        leverage_ok = position_size <= account_balance * params['leverage']
        
        return {
            'position_ok': position_ok,
            'var_ok': var_ok,
            'leverage_ok': leverage_ok,
            'overall_ok': position_ok and var_ok and leverage_ok
        }
    
    def calculate_stress_test(self, portfolio_value: float, returns: pd.Series) -> Dict[str, float]:
        """
        压力测试
        
        Args:
            portfolio_value: 组合价值
            returns: 收益率序列
            
        Returns:
            压力测试结果
        """
        results = {}
        
        for scenario_name, scenario in self.stress_scenarios.items():
            # 计算场景下的损失
            loss = portfolio_value * abs(scenario['returns'])
            
            # 计算期望损失
            expected_loss = loss * scenario['probability']
            
            results[scenario_name] = {
                'loss': loss,
                'expected_loss': expected_loss,
                'probability': scenario['probability']
            }
        
        # 计算整体风险价值
        var = self.calculate_var_historical(returns)
        es = self.calculate_es_historical(returns)
        
        results['risk_metrics'] = {
            'var': var,
            'es': es,
            'max_drawdown': self.calculate_max_drawdown(returns)
        }
        
        return results
    
    def calculate_max_drawdown(self, returns: pd.Series) -> float:
        """
        计算最大回撤
        
        Args:
            returns: 收益率序列
            
        Returns:
            最大回撤
        """
        cumulative_returns = (1 + returns).cumprod()
        peak = cumulative_returns.expanding(min_periods=1).max()
        drawdown = (cumulative_returns - peak) / peak
        max_drawdown = drawdown.min()
        
        return abs(max_drawdown)
    
    def check_drawdown_limit(self, current_value: float, peak_value: float) -> bool:
        """
        检查回撤限制
        
        Args:
            current_value: 当前价值
            peak_value: 峰值价值
            
        Returns:
            是否超过回撤限制
        """
        drawdown = (peak_value - current_value) / peak_value
        return drawdown <= self.max_drawdown_limit
    
    def check_daily_loss_limit(self, daily_pnl: float, account_balance: float) -> bool:
        """
        检查单日亏损限制
        
        Args:
            daily_pnl: 单日盈亏
            account_balance: 账户余额
            
        Returns:
            是否超过单日亏损限制
        """
        daily_loss_pct = abs(daily_pnl) / account_balance if daily_pnl < 0 else 0
        return daily_loss_pct <= self.max_daily_loss
    
    def get_risk_score(self, position_size: float, account_balance: float, regime: int, returns: pd.Series) -> float:
        """
        计算风险评分（0-100，越高风险越大）
        
        Args:
            position_size: 持仓大小
            account_balance: 账户余额
            regime: 市场状态
            returns: 收益率序列
            
        Returns:
            风险评分
        """
        # 获取市场状态对应的风险参数
        params = self.get_regime_based_risk_params(regime)
        
        # 计算各项风险指标
        position_ratio = position_size / account_balance
        var = self.calculate_var_historical(returns)
        var_ratio = var / account_balance
        max_drawdown = self.calculate_max_drawdown(returns)
        
        # 计算风险评分
        score = 0
        
        # 持仓比例评分（0-30分）
        position_score = min(30, (position_ratio / params['max_position_pct']) * 30)
        score += position_score
        
        # VaR评分（0-30分）
        var_score = min(30, (var_ratio / params['max_var_pct']) * 30)
        score += var_score
        
        # 回撤评分（0-20分）
        drawdown_score = min(20, (max_drawdown / self.max_drawdown_limit) * 20)
        score += drawdown_score
        
        # 市场状态评分（0-20分）
        regime_score = regime * 10  # 0: 0分, 1: 10分, 2: 20分
        score += regime_score
        
        # 确保评分在0-100之间
        score = max(0, min(100, score))
        
        return score
