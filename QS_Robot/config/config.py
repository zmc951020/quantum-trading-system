
import os
import json

class QSConfig:
    """QS Robot配置管理器"""
    
    def __init__(self, config_path=None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认在当前目录下的 config.json
        """
        if config_path is None:
            # 默认配置文件路径
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.config_path = os.path.join(current_dir, "config.json")
        else:
            self.config_path = config_path
        
        self._config = self._load_default_config()
        self._load_config()
    
    def _load_default_config(self):
        """加载默认配置"""
        return {
            "llm_providers": {
                "ollama": {
                    "enabled": True,
                    "api_base": "http://localhost:11434",
                    "default_model": "qwen2.5-coder:1.5b"
                }
            },
            "aurora_system": {
                "base_path": r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora",
                "web_api_base": "http://localhost:5000",
                "auto_connect": False
            },
            "ui": {
                "theme": "dark",
                "font_size": 14,
                "float_position": "bottom_right"
            },
            "extensions": {
                "tools": [],
                "hooks": [],
                "capabilities": [],
                "data_sources": []
            },
            "memory": {
                "enabled": True,
                "auto_save": True,
                "save_interval": 60
            }
        }
    
    def _load_config(self):
        """从文件加载配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并配置
                    self._merge_dict(self._config, loaded)
                print(f"[OK] 配置已从 {self.config_path} 加载")
            except Exception as e:
                print(f"[WARNING] 配置加载失败，使用默认配置: {e}")
    
    def _merge_dict(self, target, source):
        """递归合并字典"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_dict(target[key], value)
            else:
                target[key] = value
    
    def save_config(self):
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            print(f"[OK] 配置已保存到 {self.config_path}")
        except Exception as e:
            print(f"[ERROR] 配置保存失败: {e}")
    
    def get(self, path, default=None):
        """
        获取配置值
        
        Args:
            path: 配置路径，如 "llm_providers.ollama.enabled"
            default: 默认值
        
        Returns:
            Any: 配置值
        """
        parts = path.split('.')
        value = self._config
        try:
            for part in parts:
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, path, value, save=True):
        """
        设置配置值
        
        Args:
            path: 配置路径
            value: 值
            save: 是否立即保存
        """
        parts = path.split('.')
        target = self._config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
        
        if save:
            self.save_config()
    
    @property
    def config(self):
        """获取完整配置字典"""
        return self._config


# 全局配置实例
config = QSConfig()

