#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块 - 统一管理所有配置
支持从环境变量和配置文件读取配置
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from paths import path_manager


class ConfigManager:
    """
    配置管理器，负责加载和管理所有配置
    """
    
    def __init__(self):
        self.config = {}
        self._load_env()
        self._load_config_files()
    
    def _load_env(self):
        """
        从环境变量加载配置
        """
        # 系统配置
        self.config['initial_balance'] = float(os.getenv('INITIAL_BALANCE', 3000000))
        self.config['base_price'] = float(os.getenv('BASE_PRICE', 100))
        self.config['trade_interval'] = int(os.getenv('TRADE_INTERVAL', 1))
        self.config['data_frequency'] = os.getenv('DATA_FREQUENCY', '1m')
        
        # 服务器配置
        self.config['host'] = os.getenv('HOST', '0.0.0.0')
        self.config['port'] = int(os.getenv('PORT', 5000))
        self.config['flask_env'] = os.getenv('FLASK_ENV', 'development')
        self.config['flask_app'] = os.getenv('FLASK_APP', 'visualization.py')
        
        # 风险管理
        self.config['confidence_level'] = float(os.getenv('CONFIDENCE_LEVEL', 0.95))
        self.config['max_drawdown'] = float(os.getenv('MAX_DRAWDOWN', 0.15))
        self.config['max_position_size'] = float(os.getenv('MAX_POSITION_SIZE', 0.3))
        
        # 数据配置
        self.config['data_source'] = os.getenv('DATA_SOURCE', 'simulation')
        self.config['api_key'] = os.getenv('API_KEY', '')
        
        # 路径配置
        self.config['config_dir'] = os.getenv('CONFIG_DIR', 'config')
        self.config['data_dir'] = os.getenv('DATA_DIR', 'data')
        self.config['logs_dir'] = os.getenv('LOGS_DIR', 'logs')
        
        # 策略配置
        self.config['default_strategy'] = os.getenv('DEFAULT_STRATEGY', 'huijin_value')
        self.config['strategies'] = os.getenv('STRATEGIES', 'final_market_adaptive,ml_range_grid,fourier_rl,huijin_value').split(',')
        
        # 回测配置
        self.config['backtest_days'] = int(os.getenv('BACKTEST_DAYS', 250))
        self.config['risk_free_rate'] = float(os.getenv('RISK_FREE_RATE', 0.03))
        self.config['initial_capital'] = float(os.getenv('INITIAL_CAPITAL', 3000000))
        
        # 数据库配置
        self.config['db_host'] = os.getenv('DB_HOST', 'localhost')
        self.config['db_port'] = int(os.getenv('DB_PORT', 27017))
        self.config['db_name'] = os.getenv('DB_NAME', 'quantum_trading')
        self.config['db_user'] = os.getenv('DB_USER', '')
        self.config['db_password'] = os.getenv('DB_PASSWORD', '')
        
        # Redis配置
        self.config['redis_host'] = os.getenv('REDIS_HOST', 'localhost')
        self.config['redis_port'] = int(os.getenv('REDIS_PORT', 6379))
        self.config['redis_password'] = os.getenv('REDIS_PASSWORD', '')
        
        # 邮件配置
        self.config['email_enabled'] = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
        self.config['email_server'] = os.getenv('EMAIL_SERVER', 'smtp.gmail.com')
        self.config['email_port'] = int(os.getenv('EMAIL_PORT', 587))
        self.config['email_username'] = os.getenv('EMAIL_USERNAME', '')
        self.config['email_password'] = os.getenv('EMAIL_PASSWORD', '')
        self.config['email_recipients'] = os.getenv('EMAIL_RECIPIENTS', '').split(',')
        
        # 日志配置
        self.config['log_level'] = os.getenv('LOG_LEVEL', 'INFO')
        self.config['log_format'] = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 监控配置
        self.config['monitor_enabled'] = os.getenv('MONITOR_ENABLED', 'true').lower() == 'true'
        self.config['monitor_interval'] = int(os.getenv('MONITOR_INTERVAL', 60))
        
        # 安全配置
        self.config['secret_key'] = os.getenv('SECRET_KEY', 'quantum_trading_secret_key')
        self.config['debug'] = os.getenv('DEBUG', 'false').lower() == 'true'
        
        # 量化交易特定配置
        self.config['huijin_strategy_config'] = os.getenv('HUIJIN_STRATEGY_CONFIG', 'strategy_config.json')
        self.config['market_scan_interval'] = int(os.getenv('MARKET_SCAN_INTERVAL', 60))
        self.config['max_positions'] = int(os.getenv('MAX_POSITIONS', 5))
        self.config['position_size'] = float(os.getenv('POSITION_SIZE', 150000))
    
    def _load_config_files(self):
        """
        从配置文件加载配置
        """
        # 加载策略配置文件
        huijin_config_path = path_manager.get_config_path(self.config['huijin_strategy_config'])
        if huijin_config_path.exists():
            try:
                with open(huijin_config_path, 'r', encoding='utf-8') as f:
                    huijin_config = json.load(f)
                self.config['huijin_config'] = huijin_config
            except Exception as e:
                print(f"加载汇金策略配置失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键名
            default: 默认值
            
        Returns:
            配置值
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        设置配置值
        
        Args:
            key: 配置键名
            value: 配置值
        """
        self.config[key] = value
    
    def get_config_dir(self) -> Path:
        """
        获取配置目录路径
        
        Returns:
            配置目录路径
        """
        return path_manager.get_path(self.config['config_dir'])
    
    def get_data_dir(self) -> Path:
        """
        获取数据目录路径
        
        Returns:
            数据目录路径
        """
        return path_manager.get_path(self.config['data_dir'])
    
    def get_logs_dir(self) -> Path:
        """
        获取日志目录路径
        
        Returns:
            日志目录路径
        """
        return path_manager.get_path(self.config['logs_dir'])
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """
        获取策略配置
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            策略配置
        """
        if strategy_name == 'huijin_value' and 'huijin_config' in self.config:
            return self.config['huijin_config']
        return {}
    
    def to_dict(self) -> Dict[str, Any]:
        """
        返回配置字典
        
        Returns:
            配置字典
        """
        return self.config.copy()
    
    def to_string(self) -> str:
        """
        返回配置的字符串表示
        
        Returns:
            配置的字符串表示
        """
        config_str = "配置管理\n"
        config_str += "=" * 50 + "\n"
        
        for key, value in self.config.items():
            if isinstance(value, (str, int, float, bool)):
                config_str += f"{key}: {value}\n"
            elif isinstance(value, list):
                config_str += f"{key}: {', '.join(str(item) for item in value)}\n"
            elif isinstance(value, dict):
                config_str += f"{key}: {{...}}\n"
        
        config_str += "=" * 50
        return config_str


# 全局配置管理器实例
config_manager = ConfigManager()


if __name__ == "__main__":
    print("配置管理器初始化完成")
    print(config_manager.to_string())
    print("\n测试配置获取:")
    print(f"初始资金: {config_manager.get('initial_balance')}")
    print(f"默认策略: {config_manager.get('default_strategy')}")
    print(f"支持的策略: {config_manager.get('strategies')}")
    print(f"配置目录: {config_manager.get_config_dir()}")
    print(f"数据目录: {config_manager.get_data_dir()}")
    print(f"日志目录: {config_manager.get_logs_dir()}")