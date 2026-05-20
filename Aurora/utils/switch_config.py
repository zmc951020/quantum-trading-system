#!/usr/bin/env python3
"""
切换配置模块
管理系统切换相关的可配置参数，支持热加载和持久化

配置项包括：
- 数据源优先级
- 策略-市场状态映射
- 切换冷却时间
- 故障转移超时
- 最大切换频率等
"""

import json
import os
from typing import Any, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SwitchConfig:
    """切换配置管理器"""
    
    DEFAULT_CONFIG = {
        # 自动切换开关
        'auto_failover': True,              # 数据源自动故障转移
        'auto_strategy_switch': True,       # 策略自动切换
        'auto_mode_switch': False,          # 模式自动切换（默认关闭，需手动触发）
        
        # 故障转移设置
        'failover_timeout': 5,              # 故障转移超时（秒）
        'failover_retry_count': 3,          # 故障转移重试次数
        'failover_retry_interval': 2,       # 重试间隔（秒）
        
        # 策略切换设置
        'strategy_warmup_bars': 100,        # 策略预热K线数
        'min_stable_periods': 10,           # 市场状态最小稳定周期
        'strategy_switch_cooldown': 300,    # 策略切换冷却时间（秒）
        
        # 切换频率限制
        'switch_cooldown': 60,              # 通用切换冷却时间（秒）
        'max_switches_per_hour': 10,        # 每小时最大切换次数
        'max_switches_per_day': 50,         # 每天最大切换次数
        
        # 数据源优先级
        'source_priority': [
            'eastmoney',                    # 东方财富（首选）
            'akshare',                      # AKShare（备用1）
            'tushare',                      # TuShare（备用2）
            'yahoo',                        # Yahoo Finance（备用3）
            'alpha',                        # Alpha Vantage（备用4）
        ],
        
        # 市场状态→策略映射
        'market_strategy_map': {
            'trending_up': 'trend_trading',
            'trending_down': 'downtrend_optimized',
            'range_bound': 'adaptive_range_grid',
            'volatile': 'fourier_rl_strategy',
            'unknown': 'ml_range_grid',
        },
        
        # 数据源健康检查设置
        'source_health_check_interval': 30,  # 数据源健康检查间隔（秒）
        'source_health_threshold': 3,        # 连续失败阈值（超过此值触发切换）
        
        # 日志和通知
        'log_switch_events': True,           # 记录切换事件
        'notify_on_switch': True,            # 切换时发送通知
        'notify_on_failover': True,          # 故障转移时发送通知
    }
    
    def __init__(self, config_path: str = None):
        """
        初始化切换配置
        
        Args:
            config_path: 配置文件路径（JSON格式）
        """
        self._config = dict(self.DEFAULT_CONFIG)
        self._config_path = config_path or 'switch_config.json'
        self._last_loaded = None
        self._load_from_file()
    
    def _load_from_file(self):
        """从文件加载配置"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                self._config.update(file_config)
                self._last_loaded = datetime.now()
                logger.info(f"[SwitchConfig] 从文件加载配置: {self._config_path}")
            except Exception as e:
                logger.warning(f"[SwitchConfig] 加载配置文件失败: {e}，使用默认配置")
        else:
            logger.info("[SwitchConfig] 配置文件不存在，使用默认配置")
    
    def save_to_file(self, path: str = None):
        """
        保存配置到文件
        
        Args:
            path: 保存路径，默认使用初始化时的路径
        """
        save_path = path or self._config_path
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"[SwitchConfig] 配置已保存到: {save_path}")
            return True
        except Exception as e:
            logger.error(f"[SwitchConfig] 保存配置失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        Args:
            key: 配置键（支持点号分隔的嵌套键，如 'source_priority'）
            default: 默认值
            
        Returns:
            配置值
        """
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any, auto_save: bool = True):
        """
        设置配置项
        
        Args:
            key: 配置键
            value: 配置值
            auto_save: 是否自动保存到文件
        
        Returns:
            bool: 是否设置成功
        """
        # 类型验证
        default_value = self.DEFAULT_CONFIG.get(key)
        if default_value is not None and not isinstance(value, type(default_value)):
            logger.warning(f"[SwitchConfig] 配置项 '{key}' 类型不匹配: "
                          f"期望 {type(default_value).__name__}, 实际 {type(value).__name__}")
            # 尝试类型转换
            try:
                value = type(default_value)(value)
            except (ValueError, TypeError):
                logger.error(f"[SwitchConfig] 无法将值转换为期望类型")
                return False
        
        self._config[key] = value
        
        if auto_save:
            self.save_to_file()
        
        logger.info(f"[SwitchConfig] 配置已更新: {key} = {value}")
        return True
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return dict(self._config)
    
    def reset(self, key: str = None):
        """
        重置配置
        
        Args:
            key: 要重置的配置键（None 则重置全部）
        """
        if key:
            if key in self.DEFAULT_CONFIG:
                self._config[key] = self.DEFAULT_CONFIG[key]
                logger.info(f"[SwitchConfig] 已重置配置: {key}")
        else:
            self._config = dict(self.DEFAULT_CONFIG)
            logger.info("[SwitchConfig] 已重置所有配置")
        
        self.save_to_file()
    
    def reload(self):
        """重新加载配置文件（热加载）"""
        self._load_from_file()
        logger.info("[SwitchConfig] 配置已重新加载")
    
    def export(self) -> Dict[str, Any]:
        """导出配置（用于API返回）"""
        return {
            'config': dict(self._config),
            'defaults': dict(self.DEFAULT_CONFIG),
            'last_loaded': self._last_loaded.isoformat() if self._last_loaded else None,
            'config_path': self._config_path
        }
    
    def import_config(self, config_dict: Dict[str, Any], overwrite: bool = True):
        """
        导入配置
        
        Args:
            config_dict: 配置字典
            overwrite: 是否覆盖现有配置
        
        Returns:
            int: 导入的配置项数量
        """
        count = 0
        for key, value in config_dict.items():
            if key in self._config:
                if overwrite:
                    self._config[key] = value
                    count += 1
                else:
                    logger.info(f"[SwitchConfig] 跳过已存在的配置: {key}")
            else:
                logger.warning(f"[SwitchConfig] 未知配置项: {key}")
        
        self.save_to_file()
        logger.info(f"[SwitchConfig] 已导入 {count} 个配置项")
        return count
    
    def get_source_priority(self) -> list:
        """获取数据源优先级列表"""
        return self._config.get('source_priority', self.DEFAULT_CONFIG['source_priority'])
    
    def get_strategy_for_market(self, market_regime: str) -> Optional[str]:
        """根据市场状态获取对应策略"""
        market_map = self._config.get('market_strategy_map', {})
        return market_map.get(market_regime)
    
    def __str__(self) -> str:
        return f"SwitchConfig(path={self._config_path}, items={len(self._config)})"


# 全局配置实例
_global_switch_config: Optional[SwitchConfig] = None


def get_switch_config() -> SwitchConfig:
    """获取全局切换配置实例（单例）"""
    global _global_switch_config
    if _global_switch_config is None:
        _global_switch_config = SwitchConfig()
    return _global_switch_config