#!/usr/bin/env python3
"""
交易监控和性能评估模块
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from typing import Dict, List, Optional

class TradeMonitor:
    """
    交易监控器
    """
    
    def __init__(self):
        """
        初始化交易监控器
        """
        self.trades = []
        self.balance_history = []
        self.position_history = []
        self.timestamps = []
    
    def record_trade(self, timestamp: datetime, action: str, quantity: float, 
                    price: float, balance: float, position: float):
        """
        记录交易
        
        Args:
            timestamp: 交易时间
            action: 交易动作（buy, sell, hold）
            quantity: 交易数量
            price: 交易价格
            balance: 账户余额
            position: 持仓
        """
        self.trades.append({
            "timestamp": timestamp,
            "action": action,
            "quantity": quantity,
            "price": price,
            "balance": balance,
            "position": position
        })
        
        self.balance_history.append(balance)
        self.position_history.append(position)
        self.timestamps.append(timestamp)
    
    def get_trades(self) -> pd.DataFrame:
        """
        获取交易记录
        
        Returns:
            交易记录DataFrame
        """
        return pd.DataFrame(self.trades)
    
    def get_balance_history(self) -> pd.DataFrame:
        """
        获取余额历史
        
        Returns:
            余额历史DataFrame
        """
        return pd.DataFrame({
            "timestamp": self.timestamps,
            "balance": self.balance_history,
            "position": self.position_history
        })

class PerformanceEvaluator:
    """
    性能评估器
    """
    
    def __init__(self):
        """
        初始化性能评估器
        """
        pass
    
    def calculate_returns(self, balance_history: pd.Series) -> pd.Series:
        """
        计算收益率
        
        Args:
            balance_history: 余额历史
            
        Returns:
            收益率序列
        """
        returns = balance_history.pct_change()
        return returns.dropna()
    
    def calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        计算夏普比率
        
        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            
        Returns:
            夏普比率
        """
        excess_returns = returns - risk_free_rate / 252  # 假设一年252个交易日
        sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252)
        return sharpe_ratio
    
    def calculate_max_drawdown(self, balance_history: pd.Series) -> float:
        """
        计算最大回撤
        
        Args:
            balance_history: 余额历史
            
        Returns:
            最大回撤
        """
        cumulative_max = balance_history.cummax()
        drawdown = (balance_history - cumulative_max) / cumulative_max
        max_drawdown = drawdown.min()
        return max_drawdown
    
    def calculate_win_rate(self, trades: pd.DataFrame) -> float:
        """
        计算胜率
        
        Args:
            trades: 交易记录
            
        Returns:
            胜率
        """
        # 简化实现，实际需要计算每笔交易的盈亏
        win_trades = len(trades[trades['action'].isin(['buy', 'sell'])])
        total_trades = len(trades)
        if total_trades == 0:
            return 0
        return win_trades / total_trades
    
    def evaluate(self, balance_history: pd.Series, trades: pd.DataFrame) -> Dict[str, float]:
        """
        评估策略性能
        
        Args:
            balance_history: 余额历史
            trades: 交易记录
            
        Returns:
            性能指标
        """
        returns = self.calculate_returns(balance_history)
        
        metrics = {
            "total_return": (balance_history.iloc[-1] / balance_history.iloc[0] - 1) * 100,
            "sharpe_ratio": self.calculate_sharpe_ratio(returns),
            "max_drawdown": self.calculate_max_drawdown(balance_history) * 100,
            "win_rate": self.calculate_win_rate(trades),
            "total_trades": len(trades),
            "average_return": returns.mean() * 100,
            "volatility": returns.std() * 100
        }
        
        return metrics
    
    def plot_performance(self, balance_history: pd.Series, returns: pd.Series):
        """
        绘制性能图表
        
        Args:
            balance_history: 余额历史
            returns: 收益率序列
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # 绘制余额曲线
        ax1.plot(balance_history.index, balance_history.values)
        ax1.set_title('Account Balance')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Balance')
        
        # 绘制收益率直方图
        sns.histplot(returns, ax=ax2)
        ax2.set_title('Returns Distribution')
        ax2.set_xlabel('Return')
        ax2.set_ylabel('Frequency')
        
        plt.tight_layout()
        plt.show()

class ReportGenerator:
    """
    报告生成器
    """
    
    def __init__(self):
        """
        初始化报告生成器
        """
        pass
    
    def generate_report(self, metrics: Dict[str, float], trades: pd.DataFrame, 
                       balance_history: pd.DataFrame, file_path: str):
        """
        生成性能报告
        
        Args:
            metrics: 性能指标
            trades: 交易记录
            balance_history: 余额历史
            file_path: 报告文件路径
        """
        report = f"""
# Aurora 量化交易系统性能报告

## 基本信息
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 性能指标

| 指标 | 值 |
|------|----|
| 总收益率 | {metrics['total_return']:.2f}% |
| 夏普比率 | {metrics['sharpe_ratio']:.2f} |
| 最大回撤 | {metrics['max_drawdown']:.2f}% |
| 胜率 | {metrics['win_rate']:.2f} |
| 总交易次数 | {metrics['total_trades']} |
| 平均收益率 | {metrics['average_return']:.2f}% |
| 波动率 | {metrics['volatility']:.2f}% |

## 交易记录
{trades.to_string(index=False)}

## 余额历史
{balance_history.to_string(index=False)}
        """
        
        with open(file_path, 'w') as f:
            f.write(report)
        
        print(f"报告已生成: {file_path}")
