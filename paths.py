#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径管理模块 - 统一管理所有路径配置
解决不同环境下的路径问题，支持跨平台兼容性
"""

import os
import sys
from pathlib import Path


class PathManager:
    """
    路径管理器，负责生成和管理所有项目路径
    """
    
    def __init__(self):
        # 获取当前文件所在目录
        self.current_dir = Path(__file__).parent.absolute()
        # 项目根目录
        self.root_dir = self._find_root_dir()
        
        # 初始化所有路径
        self._init_paths()
    
    def _find_root_dir(self):
        """
        查找项目根目录
        """
        current = self.current_dir
        # 向上查找，直到找到包含 .git 的目录
        for _ in range(10):  # 最多向上查找10层
            if (current / ".git").exists():
                return current
            if current.parent == current:  # 已经到根目录
                break
            current = current.parent
        return self.current_dir
    
    def _init_paths(self):
        """
        初始化所有路径
        """
        # 核心目录
        self.src_dir = self.root_dir / "src" if (self.root_dir / "src").exists() else self.root_dir
        self.config_dir = self.root_dir / "config" if (self.root_dir / "config").exists() else self.root_dir / "config"
        self.data_dir = self.root_dir / "data" if (self.root_dir / "data").exists() else self.root_dir / "data"
        self.logs_dir = self.root_dir / "logs" if (self.root_dir / "logs").exists() else self.root_dir / "logs"
        self.temp_dir = self.root_dir / "temp" if (self.root_dir / "temp").exists() else self.root_dir / "temp"
        
        # 策略相关路径
        self.strategies_dir = self.root_dir / "strategies" if (self.root_dir / "strategies").exists() else self.src_dir / "strategies"
        self.models_dir = self.root_dir / "models" if (self.root_dir / "models").exists() else self.src_dir / "models"
        
        # 汇金策略路径
        self.huijin_dir = self.root_dir / "汇金价值AI轮动策略" if (self.root_dir / "汇金价值AI轮动策略").exists() else None
        
        # 确保所有目录存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """
        确保所有必要的目录存在
        """
        directories = [
            self.config_dir,
            self.data_dir,
            self.logs_dir,
            self.temp_dir,
            self.strategies_dir,
            self.models_dir
        ]
        
        for directory in directories:
            if directory and not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
    
    def get_path(self, relative_path):
        """
        获取相对路径对应的绝对路径
        
        Args:
            relative_path: 相对路径
            
        Returns:
            绝对路径
        """
        if isinstance(relative_path, str):
            relative_path = Path(relative_path)
        
        # 如果已经是绝对路径，直接返回
        if relative_path.is_absolute():
            return relative_path
        
        # 相对于根目录的路径
        full_path = self.root_dir / relative_path
        return full_path.absolute()
    
    def get_config_path(self, config_file):
        """
        获取配置文件路径
        
        Args:
            config_file: 配置文件名
            
        Returns:
            配置文件的绝对路径
        """
        return self.config_dir / config_file
    
    def get_data_path(self, data_file):
        """
        获取数据文件路径
        
        Args:
            data_file: 数据文件名
            
        Returns:
            数据文件的绝对路径
        """
        return self.data_dir / data_file
    
    def get_log_path(self, log_file):
        """
        获取日志文件路径
        
        Args:
            log_file: 日志文件名
            
        Returns:
            日志文件的绝对路径
        """
        return self.logs_dir / log_file
    
    def get_strategy_path(self, strategy_file):
        """
        获取策略文件路径
        
        Args:
            strategy_file: 策略文件名
            
        Returns:
            策略文件的绝对路径
        """
        return self.strategies_dir / strategy_file
    
    def get_model_path(self, model_file):
        """
        获取模型文件路径
        
        Args:
            model_file: 模型文件名
            
        Returns:
            模型文件的绝对路径
        """
        return self.models_dir / model_file
    
    def to_string(self):
        """
        返回路径配置的字符串表示
        """
        paths = {
            "Root Directory": str(self.root_dir),
            "Source Directory": str(self.src_dir),
            "Config Directory": str(self.config_dir),
            "Data Directory": str(self.data_dir),
            "Logs Directory": str(self.logs_dir),
            "Strategies Directory": str(self.strategies_dir),
            "Models Directory": str(self.models_dir)
        }
        
        if self.huijin_dir:
            paths["Huijin Strategy Directory"] = str(self.huijin_dir)
        
        return "\n".join([f"{k}: {v}" for k, v in paths.items()])


# 全局路径管理器实例
path_manager = PathManager()


if __name__ == "__main__":
    print("路径管理器初始化完成")
    print("=" * 50)
    print(path_manager.to_string())
    print("=" * 50)
    print("\n测试路径解析:")
    print(f"相对路径 'config/config.json': {path_manager.get_path('config/config.json')}")
    print(f"配置文件 'strategy_config.json': {path_manager.get_config_path('strategy_config.json')}")
    print(f"数据文件 'market_data.csv': {path_manager.get_data_path('market_data.csv')}")
    print(f"策略文件 'huijin_value_strategy.py': {path_manager.get_strategy_path('huijin_value_strategy.py')}")
    print(f"模型文件 'trend_model.pkl': {path_manager.get_model_path('trend_model.pkl')}")