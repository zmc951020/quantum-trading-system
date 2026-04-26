#!/usr/bin/env python3
"""
ARMA 模型实现
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from typing import Tuple, Optional

class ARMA_Model:
    """
    ARMA (Autoregressive Moving Average) 模型
    """
    
    def __init__(self, p: int = 1, q: int = 1, params: list = [0.01, 0.05, 0.2]):
        """
        初始化 ARMA 模型
        
        Args:
            p: AR 阶数
            q: MA 阶数
            params: 模型参数 [alpha, beta, gamma]
        """
        self.p = p
        self.q = q
        self.params = params
        self.model = None
        self.fitted = False
    
    def fit(self, data: pd.Series) -> None:
        """
        拟合 ARMA 模型
        
        Args:
            data: 时间序列数据
        """
        try:
            self.model = ARIMA(data, order=(self.p, 0, self.q))
            self.model = self.model.fit()
            self.fitted = True
        except Exception as e:
            raise Exception(f"ARMA 模型拟合失败: {str(e)}")
    
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
            return {"p": self.p, "q": self.q, "params": self.params}
        
        return {
            "p": self.p,
            "q": self.q,
            "params": self.params,
            "model_params": self.model.params.tolist()
        }
