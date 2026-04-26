#!/usr/bin/env python3
"""
机器学习模型训练和动态网格步长优化
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from typing import Dict, List, Optional

class FeatureEngineer:
    """
    特征工程
    """
    
    def __init__(self):
        """
        初始化特征工程
        """
        pass
    
    def extract_features(self, data: pd.Series) -> pd.DataFrame:
        """
        从价格数据中提取特征
        
        Args:
            data: 价格数据
            
        Returns:
            特征DataFrame
        """
        df = pd.DataFrame(data, columns=['price'])
        
        # 基本特征
        df['return'] = df['price'].pct_change()
        df['log_return'] = np.log(df['price'] / df['price'].shift(1))
        
        # 移动平均线
        df['MA10'] = df['price'].rolling(window=10).mean()
        df['MA20'] = df['price'].rolling(window=20).mean()
        df['MA30'] = df['price'].rolling(window=30).mean()
        
        # 波动率
        df['volatility'] = df['return'].rolling(window=14).std()
        
        # RSI
        delta = df['price'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 动量
        df['momentum'] = df['price'] - df['price'].shift(10)
        
        # 移除NaN值
        df = df.dropna()
        
        return df

class GridStepOptimizer:
    """
    动态网格步长优化器
    """
    
    def __init__(self, model=None):
        """
        初始化网格步长优化器
        
        Args:
            model: 预测模型
        """
        self.model = model if model else RandomForestRegressor(n_estimators=100, random_state=42)
        self.feature_engineer = FeatureEngineer()
    
    def train(self, data: pd.Series, target: pd.Series) -> float:
        """
        训练模型
        
        Args:
            data: 价格数据
            target: 目标值
            
        Returns:
            模型性能指标
        """
        # 提取特征
        features = self.feature_engineer.extract_features(data)
        
        # 准备训练数据
        X = features.drop(['price', 'return'], axis=1)
        y = target.loc[features.index]
        
        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # 训练模型
        self.model.fit(X_train, y_train)
        
        # 评估模型
        y_pred = self.model.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)
        
        return mse
    
    def predict_volatility(self, data: pd.Series) -> float:
        """
        预测波动率
        
        Args:
            data: 价格数据
            
        Returns:
            预测的波动率
        """
        # 提取特征
        features = self.feature_engineer.extract_features(data)
        
        if features.empty:
            return 0.01  # 默认波动率
        
        # 获取最新特征
        latest_features = features.drop(['price', 'return'], axis=1).iloc[-1:]
        
        # 预测波动率
        volatility = self.model.predict(latest_features)[0]
        
        return max(volatility, 0.001)  # 确保波动率为正
    
    def calculate_optimal_grid_step(self, data: pd.Series, base_step: float = 0.01) -> float:
        """
        计算最优网格步长
        
        Args:
            data: 价格数据
            base_step: 基础网格步长
            
        Returns:
            最优网格步长
        """
        # 预测波动率
        volatility = self.predict_volatility(data)
        
        # 根据波动率调整网格步长
        optimal_step = base_step * (1 + volatility * 10)
        
        # 限制网格步长范围
        optimal_step = max(0.005, min(optimal_step, 0.05))
        
        return optimal_step

class MLBasedGridTrading:
    """
    基于机器学习的网格化交易
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化基于机器学习的网格化交易
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.grid_optimizer = GridStepOptimizer()
        self.grid_spacing = 0.01  # 初始网格间距
        self.grid_levels = 10
    
    def train_model(self, data: pd.Series):
        """
        训练模型
        
        Args:
            data: 价格数据
        """
        # 计算目标波动率
        target = data.pct_change().rolling(window=14).std().shift(-1)
        
        # 移除NaN值
        valid_data = data.loc[target.dropna().index]
        valid_target = target.dropna()
        
        if len(valid_data) < 100:  # 确保有足够的数据
            print("数据不足，使用默认模型")
            return
        
        # 训练模型
        mse = self.grid_optimizer.train(valid_data, valid_target)
        print(f"模型训练完成，MSE: {mse}")
    
    def update_price(self, current_price: float, data: pd.Series) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 历史价格数据
            
        Returns:
            交易结果
        """
        # 动态调整网格步长
        self.grid_spacing = self.grid_optimizer.calculate_optimal_grid_step(data)
        
        # 创建网格
        grids = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            grids.append(price)
        grids = sorted(grids)
        
        # 找到当前价格所在的网格区间
        for i in range(len(grids) - 1):
            if grids[i] <= current_price < grids[i + 1]:
                # 计算应该持有的仓位
                target_position = (i - self.grid_levels) * 10  # 每个网格10个单位
                position_change = target_position - self.position
                
                # 执行交易
                if position_change > 0:
                    # 买入
                    cost = position_change * current_price
                    if cost <= self.current_balance:
                        self.position = target_position
                        self.current_balance -= cost
                        return {
                            "action": "buy",
                            "quantity": position_change,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "grid_spacing": self.grid_spacing
                        }
                elif position_change < 0:
                    # 卖出
                    quantity = abs(position_change)
                    revenue = quantity * current_price
                    self.position = target_position
                    self.current_balance += revenue
                    return {
                        "action": "sell",
                        "quantity": quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "grid_spacing": self.grid_spacing
                    }
                break
        
        return {
            "action": "hold", 
            "balance": self.current_balance, 
            "position": self.position,
            "grid_spacing": self.grid_spacing
        }
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "pnl": self.current_balance - self.initial_balance,
            "return": (self.current_balance / self.initial_balance - 1) * 100
        }
