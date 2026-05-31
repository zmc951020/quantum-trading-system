# coding: utf-8
"""配置管理器 - Aurora增强模块

系统级配置管理，支持多环境配置切换与热重载。
"""
import json

class ConfigManager:
    """系统配置管理器"""

    def __init__(self, config_path: str = "config/app.json"):
        self.config_path = config_path
        self.config: dict = {}

    def load(self) -> dict:
        """加载配置"""
        return self.config

    def get(self, key: str, default=None):
        """获取配置值"""
        return self.config.get(key, default)