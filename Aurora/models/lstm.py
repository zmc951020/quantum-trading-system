#!/usr/bin/env python3
"""
LSTM 模型实现
"""

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from typing import Tuple, Optional

class LSTM_Model:
    """
    LSTM (Long Short-Term Memory) 模型
    """
    
    def __init__(self, sequence_length: int = 10, 
                 lstm_layer_size: int = 50, 
                 dropout: float = 0.2, 
                 params: list = [0.1, 0.05, 0.2]):
        """
        初始化 LSTM 模型
        
        Args:
            sequence_length: 序列长度
            lstm_layer_size: LSTM 层大小
            dropout:  dropout 率
            params: 模型参数 [learning_rate, beta_1, beta_2]
        """
        self.sequence_length = sequence_length
        self.lstm_layer_size = lstm_layer_size
        self.dropout = dropout
        self.params = params
        self.model = None
        self.fitted = False
    
    def _create_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        创建输入序列和目标值
        
        Args:
            data: 时间序列数据
            
        Returns:
            (输入序列, 目标值)
        """
        X, y = [], []
        for i in range(len(data) - self.sequence_length):
            X.append(data[i:i+self.sequence_length])
            y.append(data[i+self.sequence_length])
        return np.array(X), np.array(y)
    
    def fit(self, data: pd.Series, epochs: int = 50, batch_size: int = 32) -> None:
        """
        拟合 LSTM 模型
        
        Args:
            data: 时间序列数据
            epochs: 训练轮数
            batch_size: 批量大小
        """
        try:
            # 保存数据
            self.data = data
            # 准备数据
            data_array = data.values.reshape(-1, 1)
            X, y = self._create_sequences(data_array)
            
            # 创建模型
            self.model = Sequential([
                LSTM(self.lstm_layer_size, return_sequences=True, input_shape=(self.sequence_length, 1)),
                Dropout(self.dropout),
                LSTM(self.lstm_layer_size),
                Dropout(self.dropout),
                Dense(1)
            ])
            
            # 编译模型
            optimizer = Adam(
                learning_rate=self.params[0],
                beta_1=self.params[1],
                beta_2=self.params[2]
            )
            self.model.compile(optimizer=optimizer, loss='mse')
            
            # 训练模型
            self.model.fit(X, y, epochs=epochs, batch_size=batch_size, verbose=0)
            self.fitted = True
        except Exception as e:
            raise Exception(f"LSTM 模型拟合失败: {str(e)}")
    
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
        
        # 使用最后一个序列进行预测
        last_sequence = self.data[-self.sequence_length:].values.reshape(1, self.sequence_length, 1)
        predictions = []
        
        for _ in range(steps):
            pred = self.model.predict(last_sequence, verbose=0)[0][0]
            predictions.append(pred)
            # 更新序列
            last_sequence = np.roll(last_sequence, -1, axis=1)
            last_sequence[0, -1, 0] = pred
        
        return np.array(predictions)
    
    def get_params(self) -> dict:
        """
        获取模型参数
        
        Returns:
            模型参数字典
        """
        return {
            "sequence_length": self.sequence_length,
            "lstm_layer_size": self.lstm_layer_size,
            "dropout": self.dropout,
            "params": self.params
        }
