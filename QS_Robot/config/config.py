
import os
import json
import time
import threading
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 配置Schema校验
# ============================================================

CONFIG_SCHEMA = {
    "port_allocation": {
        "type": dict,
        "required": True,
        "schema": {
            "aurora_kernel": {"type": int, "required": True, "min": 1024, "max": 65535},
            "qs_robot_shell": {"type": int, "required": True, "min": 1024, "max": 65535},
        }
    },
    "llm_providers": {
        "type": dict,
        "required": True,
        "schema": {
            "ollama": {
                "type": dict, "required": False,
                "schema": {
                    "enabled": {"type": bool, "required": False},
                    "api_base": {"type": str, "required": False},
                    "default_model": {"type": str, "required": False},
                }
            },
            "echobird": {
                "type": dict, "required": False,
                "schema": {
                    "enabled": {"type": bool, "required": False},
                    "api_base": {"type": str, "required": False},
                    "default_model": {"type": str, "required": False},
                    "api_key": {"type": str, "required": False},
                }
            },
        }
    },
    "aurora_system": {
        "type": dict, "required": True,
        "schema": {
            "base_path": {"type": str, "required": True},
            "web_api_base": {"type": str, "required": False},
            "auto_connect": {"type": bool, "required": False},
        }
    },
    "ui": {
        "type": dict, "required": False,
        "schema": {
            "theme": {"type": str, "required": False, "enum": ["dark", "light"]},
            "font_size": {"type": int, "required": False, "min": 8, "max": 32},
            "float_position": {"type": str, "required": False},
        }
    },
    "extensions": {
        "type": dict, "required": False,
        "schema": {
            "tools": {"type": list, "required": False},
            "hooks": {"type": list, "required": False},
            "capabilities": {"type": list, "required": False},
            "data_sources": {"type": list, "required": False},
        }
    },
    "memory": {
        "type": dict, "required": False,
        "schema": {
            "enabled": {"type": bool, "required": False},
            "auto_save": {"type": bool, "required": False},
            "save_interval": {"type": int, "required": False, "min": 10},
        }
    },
}


def validate_config_schema(config: dict, schema: dict = None, 
                           path: str = "") -> dict:
    """校验配置是否符合Schema定义
    
    Args:
        config: 待校验的配置字典
        schema: Schema定义（默认使用全局CONFIG_SCHEMA）
        path: 当前路径（用于错误报告）
        
    Returns:
        dict: {valid: bool, errors: List[str]}
    """
    if schema is None:
        schema = CONFIG_SCHEMA
    
    errors = []
    
    for key, rule in schema.items():
        current_path = f"{path}.{key}" if path else key
        
        # 检查必需字段
        if rule.get("required") and key not in config:
            errors.append(f"[{current_path}] 缺少必需字段")
            continue
        
        if key not in config:
            continue
        
        value = config[key]
        expected_type = rule.get("type")
        
        # 类型检查
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"[{current_path}] 类型错误: 期望 {expected_type.__name__}, "
                f"实际 {type(value).__name__}"
            )
            continue
        
        # 数值范围检查
        if isinstance(value, (int, float)):
            if "min" in rule and value < rule["min"]:
                errors.append(f"[{current_path}] 值 {value} 小于最小值 {rule['min']}")
            if "max" in rule and value > rule["max"]:
                errors.append(f"[{current_path}] 值 {value} 大于最大值 {rule['max']}")
        
        # 枚举检查
        if "enum" in rule and value not in rule["enum"]:
            errors.append(
                f"[{current_path}] 值 '{value}' 不在允许范围: {rule['enum']}"
            )
        
        # 嵌套Schema检查
        if "schema" in rule and isinstance(value, dict):
            nested_errors = validate_config_schema(value, rule["schema"], current_path)
            errors.extend(nested_errors["errors"])
    
    return {"valid": len(errors) == 0, "errors": errors}

class QSConfig:
    """QS Robot配置管理器（支持Schema校验 + 热加载 + 文件监控）"""
    
    def __init__(self, config_path=None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认在当前目录下的 config.json
        """
        if config_path is None:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.config_path = os.path.join(current_dir, "config.json")
        else:
            self.config_path = config_path
        
        self._config = self._load_default_config()
        self._loaded = False
        self._watch_thread = None
        self._watch_stop = threading.Event()
        self._on_change_callbacks = []
        self._load_config()
    
    def _load_default_config(self):
        """加载默认配置"""
        return {
            "port_allocation": {
                "aurora_kernel": 5000,
                "qs_robot_shell": 5001
            },
            "llm_providers": {
                "ollama": {
                    "enabled": True,
                    "api_base": "http://localhost:11434",
                    "default_model": "qwen2.5-coder:1.5b"
                },
                "echobird": {
                    "enabled": False,
                    "api_base": "http://localhost:8080/v1",
                    "default_model": "gpt-4o",
                    "api_key": ""
                }
            },
            "aurora_system": {
                "base_path": r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora",
                "web_api_base": "http://localhost:5003",
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
            },
            "ssl": {
                "enabled": False,
                "cert_path": "certs/cert.pem",
                "key_path": "certs/key.pem",
                "redirect_http": True
            }
        }
    
    def _load_config(self):
        """从文件加载配置（带Schema校验）"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                
                # Schema校验
                validation = validate_config_schema(loaded)
                if not validation["valid"]:
                    for err in validation["errors"]:
                        logger.warning(f"[配置校验] {err}")
                    logger.warning("[配置校验] 配置存在错误，已加载但部分值可能无效")
                
                self._merge_dict(self._config, loaded)
                self._loaded = True
                logger.info(f"[配置] 已从 {self.config_path} 加载")
            except Exception as e:
                logger.error(f"[配置] 加载失败: {e}")
                self._loaded = False
        else:
            logger.info(f"[配置] 配置文件不存在，使用默认配置: {self.config_path}")
            self._loaded = True
    
    def validate(self) -> dict:
        """校验当前配置"""
        return validate_config_schema(self._config)
    
    def reload(self) -> dict:
        """热加载配置（重新读取文件并合并）"""
        old_config = json.dumps(self._config, sort_keys=True)
        self._load_config()
        new_config = json.dumps(self._config, sort_keys=True)
        
        changed = old_config != new_config
        if changed:
            logger.info("[热加载] 配置已更新")
            # 触发回调
            for cb in self._on_change_callbacks:
                try:
                    cb(self._config)
                except Exception as e:
                    logger.error(f"[热加载] 回调异常: {e}")
        
        return {
            "success": True,
            "changed": changed,
            "config_path": self.config_path,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    def on_change(self, callback):
        """注册配置变更回调
        
        Args:
            callback: 回调函数 callback(config_dict)
        """
        self._on_change_callbacks.append(callback)
    
    def start_watch(self, interval_seconds: float = 5.0):
        """启动文件监控线程（检测配置文件变更并自动热加载）
        
        Args:
            interval_seconds: 检查间隔（秒）
        """
        if self._watch_thread and self._watch_thread.is_alive():
            logger.warning("[热加载] 监控线程已在运行")
            return
        
        self._watch_stop.clear()
        last_mtime = os.path.getmtime(self.config_path) if os.path.exists(self.config_path) else 0
        
        def _watch_loop():
            nonlocal last_mtime
            logger.info(f"[热加载] 启动文件监控，间隔 {interval_seconds}s")
            while not self._watch_stop.wait(interval_seconds):
                try:
                    if os.path.exists(self.config_path):
                        mtime = os.path.getmtime(self.config_path)
                        if mtime > last_mtime:
                            last_mtime = mtime
                            self.reload()
                except Exception as e:
                    logger.error(f"[热加载] 监控异常: {e}")
        
        self._watch_thread = threading.Thread(target=_watch_loop, daemon=True,
                                              name="config-watcher")
        self._watch_thread.start()
    
    def stop_watch(self):
        """停止文件监控"""
        if self._watch_thread:
            self._watch_stop.set()
            self._watch_thread.join(timeout=3)
            self._watch_thread = None
            logger.info("[热加载] 文件监控已停止")
    
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

