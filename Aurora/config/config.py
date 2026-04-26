#!/usr/bin/env python3
"""
系统配置文件
"""

import os
from dotenv import load_dotenv
from typing import Dict, Any

# 加载环境变量
load_dotenv()

class Config:
    """
    系统配置类
    """
    
    def __init__(self):
        """
        初始化配置
        """
        # 交易参数
        self.initial_balance = float(os.getenv("INITIAL_BALANCE", "100000"))
        self.trade_interval = int(os.getenv("TRADE_INTERVAL", "1"))
        
        # 模型参数
        self.model_type = os.getenv("MODEL_TYPE", "LSTM")
        self.model_training_frequency = int(os.getenv("MODEL_TRAINING_FREQUENCY", "1"))
        
        # 策略参数
        self.grid_spacing = float(os.getenv("GRID_SPACING", "0.01"))
        self.grid_levels = int(os.getenv("GRID_LEVELS", "10"))
        self.ma_short_window = int(os.getenv("MA_SHORT_WINDOW", "10"))
        self.ma_medium_window = int(os.getenv("MA_MEDIUM_WINDOW", "20"))
        self.ma_long_window = int(os.getenv("MA_LONG_WINDOW", "30"))
        self.rsi_window = int(os.getenv("RSI_WINDOW", "14"))
        self.rsi_overbought = int(os.getenv("RSI_OVERBOUGHT", "70"))
        self.rsi_oversold = int(os.getenv("RSI_OVERSOLD", "30"))
        
        # 风险管理参数
        self.confidence_level = float(os.getenv("CONFIDENCE_LEVEL", "0.95"))
        self.max_loss_per_trade = float(os.getenv("MAX_LOSS_PER_TRADE", "0.01"))
        self.max_var = float(os.getenv("MAX_VAR", "0.05"))
        
        # 数据参数
        self.data_source = os.getenv("DATA_SOURCE", "yfinance")
        self.data_frequency = os.getenv("DATA_FREQUENCY", "1m")
        self.lookback_period = int(os.getenv("LOOKBACK_PERIOD", "252"))
        
        # 机器学习参数
        self.train_test_split = float(os.getenv("TRAIN_TEST_SPLIT", "0.8"))
        self.n_estimators = int(os.getenv("N_ESTIMATORS", "100"))
        self.max_depth = int(os.getenv("MAX_DEPTH", "10"))
        
        # 日志参数
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = os.getenv("LOG_FILE", "logs/aurora.log")
        
        # 西部宽客API配置
        self.xbk_api_key = os.getenv("XBK_API_KEY", "")
        self.xbk_api_secret = os.getenv("XBK_API_SECRET", "")
        self.xbk_api_url = os.getenv("XBK_API_URL", "https://api.westquant.cn/sim")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将配置转换为字典
        
        Returns:
            配置字典
        """
        return {
            "initial_balance": self.initial_balance,
            "trade_interval": self.trade_interval,
            "model_type": self.model_type,
            "model_training_frequency": self.model_training_frequency,
            "grid_spacing": self.grid_spacing,
            "grid_levels": self.grid_levels,
            "ma_short_window": self.ma_short_window,
            "ma_medium_window": self.ma_medium_window,
            "ma_long_window": self.ma_long_window,
            "rsi_window": self.rsi_window,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
            "confidence_level": self.confidence_level,
            "max_loss_per_trade": self.max_loss_per_trade,
            "max_var": self.max_var,
            "data_source": self.data_source,
            "data_frequency": self.data_frequency,
            "lookback_period": self.lookback_period,
            "train_test_split": self.train_test_split,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "xbk_api_key": self.xbk_api_key,
            "xbk_api_secret": self.xbk_api_secret,
            "xbk_api_url": self.xbk_api_url
        }

# 创建全局配置实例
config = Config()
