#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略参数管理器
提供策略参数的自动保存、加载、版本管理功能
集成 DatabaseManager 实现持久化
"""

import json
import hashlib
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

# 确保可以导入父目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database_manager import get_db_manager


class StrategyParamManager:
    """策略参数管理器"""

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.db = get_db_manager()
        self._param_cache = None
        self._cache_timestamp = None

    def save_params(self, params: Dict[str, Any],
                   descriptions: Dict[str, str] = None,
                   version_tag: str = None) -> bool:
        """
        保存策略参数

        Args:
            params: 参数字典
            descriptions: 参数描述
            version_tag: 版本标签（可选）

        Returns:
            是否成功
        """
        # 计算参数哈希作为版本标识
        param_hash = self._compute_hash(params)

        # 保存到数据库
        success = self.db.save_strategy_params(
            self.strategy_name, params, descriptions
        )

        if success and version_tag:
            # 保存版本标签到配置
            self.db.set_config(
                f"param_version_{self.strategy_name}",
                version_tag,
                f"策略 {self.strategy_name} 参数版本"
            )

        # 保存参数哈希
        if success:
            self.db.set_config(
                f"param_hash_{self.strategy_name}",
                param_hash,
                f"策略 {self.strategy_name} 参数哈希"
            )

        # 清除缓存
        self._param_cache = None
        self._cache_timestamp = None

        return success

    def load_params(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        加载策略参数

        Args:
            use_cache: 是否使用缓存

        Returns:
            参数字典
        """
        if use_cache and self._param_cache is not None:
            return self._param_cache

        params = self.db.load_strategy_params(self.strategy_name)

        self._param_cache = params
        self._cache_timestamp = datetime.now()

        return params

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        获取单个参数值

        Args:
            key: 参数名
            default: 默认值

        Returns:
            参数值
        """
        params = self.load_params()
        return params.get(key, default)

    def update_param(self, key: str, value: Any,
                    description: str = None) -> bool:
        """
        更新单个参数

        Args:
            key: 参数名
            value: 参数值
            description: 参数描述

        Returns:
            是否成功
        """
        return self.save_params(
            {key: value},
            {key: description} if description else None
        )

    def get_param_hash(self) -> Optional[str]:
        """
        获取当前参数哈希

        Returns:
            哈希值
        """
        return self.db.get_config(f"param_hash_{self.strategy_name}")

    def get_param_version(self) -> Optional[str]:
        """
        获取参数版本标签

        Returns:
            版本标签
        """
        return self.db.get_config(f"param_version_{self.strategy_name}")

    def has_params(self) -> bool:
        """
        检查是否有保存的参数

        Returns:
            是否有参数
        """
        params = self.load_params()
        return len(params) > 0

    def delete_params(self) -> bool:
        """
        删除所有参数

        Returns:
            是否成功
        """
        self._param_cache = None
        return self.db.delete_strategy_params(self.strategy_name)

    def export_params_to_json(self, filepath: str = None) -> Optional[str]:
        """
        导出参数到JSON文件

        Args:
            filepath: 文件路径（可选）

        Returns:
            文件路径
        """
        params = self.load_params()
        if not params:
            return None

        if filepath is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"params_{self.strategy_name}_{timestamp}.json"

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'strategy_name': self.strategy_name,
                'params': params,
                'exported_at': datetime.now().isoformat(),
                'version': self.get_param_version()
            }, f, ensure_ascii=False, indent=2)

        return filepath

    def import_params_from_json(self, filepath: str) -> bool:
        """
        从JSON文件导入参数

        Args:
            filepath: 文件路径

        Returns:
            是否成功
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            params = data.get('params', {})
            if not params:
                return False

            return self.save_params(
                params,
                version_tag=data.get('version')
            )
        except Exception as e:
            print(f"[StrategyParamManager] 导入参数失败: {e}")
            return False

    def get_param_history(self) -> List[Dict]:
        """
        获取参数变更历史（通过性能指标追踪）

        Returns:
            历史记录列表
        """
        metrics = self.db.get_performance_metrics(
            self.strategy_name,
            metric_name='param_update',
            limit=50
        )
        return metrics

    @staticmethod
    def _compute_hash(params: Dict[str, Any]) -> str:
        """计算参数哈希"""
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(param_str.encode()).hexdigest()[:12]

    @staticmethod
    def get_all_strategies_with_params() -> List[str]:
        """获取所有有参数存储的策略"""
        db = get_db_manager()
        return db.get_all_strategies()


# 便捷函数
def get_strategy_param_manager(strategy_name: str) -> StrategyParamManager:
    """获取策略参数管理器实例"""
    return StrategyParamManager(strategy_name)


def auto_load_params(strategy_name: str, default_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    自动加载策略参数，如果没有则使用默认参数并保存

    Args:
        strategy_name: 策略名称
        default_params: 默认参数

    Returns:
        参数字典
    """
    manager = StrategyParamManager(strategy_name)

    if manager.has_params():
        loaded = manager.load_params()
        print(f"[StrategyParamManager] 已加载策略 '{strategy_name}' 的保存参数")
        return loaded
    else:
        print(f"[StrategyParamManager] 策略 '{strategy_name}' 无保存参数，使用默认参数")
        manager.save_params(default_params)
        return default_params


if __name__ == '__main__':
    # 测试策略参数管理器
    print("=" * 60)
    print("策略参数管理器测试")
    print("=" * 60)

    # 测试自动加载
    default_params = {
        'grid_levels': 100,
        'grid_spacing': 0.0015,
        'stop_loss': 0.008,
        'take_profit': 0.015,
        'use_ml': True,
        'ml_model': 'lstm',
        'max_position_size': 0.1
    }

    params = auto_load_params('TestStrategy', default_params)
    print(f"\n加载的参数: {params}")

    # 测试参数管理器
    manager = StrategyParamManager('TestStrategy')
    print(f"参数哈希: {manager.get_param_hash()}")
    print(f"是否有参数: {manager.has_params()}")

    # 测试更新单个参数
    manager.update_param('grid_levels', 150, '网格层数')
    updated = manager.load_params(use_cache=False)
    print(f"\n更新后参数: {updated}")

    # 测试导出
    export_path = manager.export_params_to_json()
    print(f"\n导出到: {export_path}")

    # 测试获取所有策略
    strategies = StrategyParamManager.get_all_strategies_with_params()
    print(f"\n有参数存储的策略: {strategies}")

    print("\n✅ 策略参数管理器测试完成！")
