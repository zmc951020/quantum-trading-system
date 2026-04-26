#!/usr/bin/env python3
"""
SARIMA 模型实现
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from typing import Tuple, Optional

class SARIMA_Model:
    """
    SARIMA (Seasonal Autoregressive Integrated Moving Average) 模型
    """
    
    def __init__(self, p: int = 1, d: int = 1, q: int = 1, 
                 P: int = 1, D: int = 1, Q: int = 1, 
                 seasonal_period: int = 12, 
                 params: list = [0.5, 0.25, 0.1]):
        """
        初始化 SARIMA 模型
        
        Args:
            p: AR 阶数
            d: 差分阶数
            q: MA 阶数
            P: 季节性 AR 阶数
            D: 季节性差分阶数
            Q: 季节性 MA 阶数
            seasonal_period: 季节性周期
            params: 模型参数 [alpha, beta, gamma]
        """
        self.p = p
        self.d = d
        self.q = q
        self.P = P
        self.D = D
        self.Q = Q
        self.seasonal_period = seasonal_period
        self.params = params
        self.model = None
        self.fitted = False
    
    def fit(self, data: pd.Series) -> None:
        """
        拟合 SARIMA 模型
        
        Args:
            data: 时间序列数据
        """
        try:
            self.model = SARIMAX(
                data,
                order=(self.p, self.d, self.q),
                seasonal_order=(self.P, self.D, self.Q, self.seasonal_period)
            )
            self.model = self.model.fit()
            self.fitted = True
        except Exception as e:
            raise Exception(f"SARIMA 模型拟合失败: {str(e)}")
    
    def predict(self, steps: int = 1) -> np.ndarray:
        """
        预测未来值
        
        Args:
            steps: 预测步数
            
        Returns:
            预测值数组
        """
        if not self.fitted:
            raise Exception("模型未拟合")
        
        return self.model.forecast(steps=steps).values
    
    def get_params(self) -> dict:
        """
        获取模型参数
        
        Returns:
            模型参数字典
        """
        if not self.fitted:
            return {
                "p": self.p,
                "d": self.d,
                "q": self.q,
                "P": self.P,
                "D": self.D,
                "Q": self.Q,
                "seasonal_period": self.seasonal_period,
                "params": self.params
            }
        
        return {
            "p": self.p,
            "d": self.d,
            "q": self.q,
            "P": self.P,
            "D": self.D,
            "Q": self.Q,
            "seasonal_period": self.seasonal_period,
            "params": self.params,
            "model_params": self.model.params.tolist()
        }
