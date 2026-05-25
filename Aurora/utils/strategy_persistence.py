#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略持久化集成模块
为现有策略类提供非侵入式的参数持久化、回测结果存储、性能指标追踪功能
通过混入类（Mixin）和装饰器实现，无需修改策略核心代码
"""

import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable

# 确保可以导入父目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.strategy_param_manager import StrategyParamManager, auto_load_params
from utils.database_manager import get_db_manager


class StrategyPersistenceMixin:
    """
    策略持久化混入类
    为策略类添加参数持久化、回测结果存储、性能指标追踪功能
    使用方式：class MyStrategy(StrategyPersistenceMixin, BaseStrategy):
    """

    def __init__(self, *args, **kwargs):
        # 获取策略名称（子类应设置 self.strategy_name）
        if not hasattr(self, 'strategy_name'):
            self.strategy_name = self.__class__.__name__

        # 初始化参数管理器
        self._param_manager = StrategyParamManager(self.strategy_name)
        self._db = get_db_manager()

        # 参数变更追踪
        self._param_change_log = []

        # 调用父类初始化
        super().__init__(*args, **kwargs)

    # ==================== 参数持久化 ====================

    def persist_params(self, params: Dict[str, Any],
                      descriptions: Dict[str, str] = None,
                      version_tag: str = None) -> bool:
        """
        持久化策略参数

        Args:
            params: 参数字典
            descriptions: 参数描述
            version_tag: 版本标签

        Returns:
            是否成功
        """
        return self._param_manager.save_params(params, descriptions, version_tag)

    def load_persisted_params(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        加载持久化的参数

        Args:
            use_cache: 是否使用缓存

        Returns:
            参数字典
        """
        return self._param_manager.load_params(use_cache)

    def has_persisted_params(self) -> bool:
        """检查是否有持久化的参数"""
        return self._param_manager.has_params()

    def auto_load_params(self, default_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        自动加载参数，优先使用持久化的参数

        Args:
            default_params: 默认参数

        Returns:
            最终使用的参数
        """
        return auto_load_params(self.strategy_name, default_params)

    def apply_params(self, params: Dict[str, Any]) -> int:
        """
        将参数字典应用到策略实例的属性上

        Args:
            params: 参数字典

        Returns:
            应用的参数数量
        """
        count = 0
        for key, value in params.items():
            if hasattr(self, key):
                old_value = getattr(self, key)
                setattr(self, key, value)
                self._param_change_log.append({
                    'key': key,
                    'old_value': old_value,
                    'new_value': value,
                    'timestamp': datetime.now().isoformat()
                })
                count += 1
        return count

    def get_param(self, key: str, default: Any = None) -> Any:
        """获取单个参数值"""
        return self._param_manager.get_param(key, default)

    def update_param(self, key: str, value: Any,
                    description: str = None) -> bool:
        """更新单个参数并持久化"""
        if hasattr(self, key):
            setattr(self, key, value)
        return self._param_manager.update_param(key, value, description)

    # ==================== 回测结果存储 ====================

    def save_backtest_result(self, result_dict: Dict) -> bool:
        """
        保存回测结果

        Args:
            result_dict: 回测结果字典

        Returns:
            是否成功
        """
        result_dict['strategy_name'] = self.strategy_name
        return self._db.save_backtest_result(result_dict)

    def get_backtest_history(self, limit: int = 10) -> List[Dict]:
        """
        获取历史回测结果

        Args:
            limit: 返回数量

        Returns:
            回测结果列表
        """
        return self._db.get_backtest_results(self.strategy_name, limit)

    def get_best_backtest(self, metric: str = 'total_return') -> Optional[Dict]:
        """
        获取最佳回测结果

        Args:
            metric: 评估指标

        Returns:
            最佳回测结果
        """
        return self._db.get_best_backtest_result(self.strategy_name, metric)

    # ==================== 性能指标追踪 ====================

    def track_metric(self, metric_name: str, metric_value: float,
                    symbol: str = None, period: str = None) -> bool:
        """
        追踪性能指标

        Args:
            metric_name: 指标名称
            metric_value: 指标值
            symbol: 交易标的
            period: 时间周期

        Returns:
            是否成功
        """
        return self._db.save_performance_metric(
            self.strategy_name, metric_name, metric_value, symbol, period
        )

    def get_metric_history(self, metric_name: str = None,
                          limit: int = 100) -> List[Dict]:
        """
        获取指标历史

        Args:
            metric_name: 指标名称
            limit: 返回数量

        Returns:
            指标历史列表
        """
        return self._db.get_performance_metrics(
            self.strategy_name, metric_name, limit
        )

    def get_metric_summary(self) -> Dict:
        """
        获取指标摘要

        Returns:
            指标摘要
        """
        return self._db.get_performance_summary(self.strategy_name)

    # ==================== 交易记录 ====================

    def save_trade(self, symbol: str, order_type: str, direction: str,
                  price: float, quantity: float, amount: float,
                  status: str = 'open', profit: float = None) -> bool:
        """
        保存交易记录

        Args:
            symbol: 交易标的
            order_type: 订单类型
            direction: 方向
            price: 价格
            quantity: 数量
            amount: 金额
            status: 状态
            profit: 盈亏

        Returns:
            是否成功
        """
        self._db.insert_trade_record(
            self.strategy_name, symbol, order_type, direction,
            price, quantity, amount, status, profit
        )
        return True

    def get_trade_stats(self) -> Dict:
        """
        获取交易统计

        Returns:
            交易统计
        """
        return self._db.get_trade_statistics(self.strategy_name)

    # ==================== 数据质量日志 ====================

    def log_data_quality(self, check_type: str, data_source: str,
                        status: str, score: float = None,
                        issues: str = None, symbol: str = None) -> bool:
        """
        记录数据质量

        Args:
            check_type: 校验类型
            data_source: 数据源
            status: 状态
            score: 评分
            issues: 问题
            symbol: 标的

        Returns:
            是否成功
        """
        return self._db.log_data_quality(
            check_type, data_source, status, score, issues, symbol
        )

    # ==================== 便捷方法 ====================

    def track_trade_result(self, profit: float, symbol: str = None) -> None:
        """
        追踪交易结果（自动记录盈亏和胜率）

        Args:
            profit: 盈亏金额
            symbol: 交易标的
        """
        self.track_metric('trade_profit', profit, symbol)
        if profit > 0:
            self.track_metric('winning_trade', 1, symbol)
        else:
            self.track_metric('losing_trade', 1, symbol)

    def track_daily_performance(self, daily_return: float,
                               sharpe: float = None,
                               max_dd: float = None) -> None:
        """
        追踪每日表现

        Args:
            daily_return: 日收益率
            sharpe: 夏普比率
            max_dd: 最大回撤
        """
        self.track_metric('daily_return', daily_return)
        if sharpe is not None:
            self.track_metric('sharpe_ratio', sharpe)
        if max_dd is not None:
            self.track_metric('max_drawdown', max_dd)

    def export_params(self, filepath: str = None) -> Optional[str]:
        """导出参数到JSON文件"""
        return self._param_manager.export_params_to_json(filepath)

    def import_params(self, filepath: str) -> bool:
        """从JSON文件导入参数"""
        return self._param_manager.import_params_from_json(filepath)


# ==================== 便捷函数 ====================

def enable_strategy_persistence(strategy_class, strategy_name: str = None) -> None:
    """
    为现有策略类启用持久化功能（猴子补丁方式）
    无需修改策略类定义即可添加持久化能力

    Args:
        strategy_class: 策略类
        strategy_name: 策略名称（默认使用类名）
    """
    if strategy_name is None:
        strategy_name = strategy_class.__name__

    # 创建参数管理器实例
    param_manager = StrategyParamManager(strategy_name)
    db = get_db_manager()

    # 添加持久化方法到类
    def _persist_params(self, params, descriptions=None, version_tag=None):
        return param_manager.save_params(params, descriptions, version_tag)

    def _load_persisted_params(self, use_cache=True):
        return param_manager.load_params(use_cache)

    def _has_persisted_params(self):
        return param_manager.has_params()

    def _auto_load_params(self, default_params):
        return auto_load_params(strategy_name, default_params)

    def _apply_params(self, params):
        count = 0
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)
                count += 1
        return count

    def _save_backtest_result(self, result_dict):
        result_dict['strategy_name'] = strategy_name
        return db.save_backtest_result(result_dict)

    def _get_backtest_history(self, limit=10):
        return db.get_backtest_results(strategy_name, limit)

    def _track_metric(self, metric_name, metric_value, symbol=None, period=None):
        return db.save_performance_metric(
            strategy_name, metric_name, metric_value, symbol, period
        )

    def _save_trade(self, symbol, order_type, direction, price,
                   quantity, amount, status='open', profit=None):
        db.insert_trade_record(
            strategy_name, symbol, order_type, direction,
            price, quantity, amount, status, profit
        )
        return True

    def _get_trade_stats(self):
        return db.get_trade_statistics(strategy_name)

    # 绑定方法到类
    strategy_class.persist_params = _persist_params
    strategy_class.load_persisted_params = _load_persisted_params
    strategy_class.has_persisted_params = _has_persisted_params
    strategy_class.auto_load_params = _auto_load_params
    strategy_class.apply_params = _apply_params
    strategy_class.save_backtest_result = _save_backtest_result
    strategy_class.get_backtest_history = _get_backtest_history
    strategy_class.track_metric = _track_metric
    strategy_class.save_trade = _save_trade
    strategy_class.get_trade_stats = _get_trade_stats

    print(f"[StrategyPersistence] 已为 {strategy_name} 启用持久化功能")


if __name__ == '__main__':
    print("=" * 60)
    print("策略持久化集成模块测试")
    print("=" * 60)

    # 测试混入类
    class TestStrategy(StrategyPersistenceMixin):
        def __init__(self):
            self.strategy_name = 'TestPersistStrategy'
            self.grid_levels = 100
            self.grid_spacing = 0.0015
            self.stop_loss = 0.008
            self.take_profit = 0.015
            self.use_ml = True
            super().__init__()

    strategy = TestStrategy()

    # 测试参数持久化
    params = {
        'grid_levels': 100,
        'grid_spacing': 0.0015,
        'stop_loss': 0.008,
        'take_profit': 0.015,
        'use_ml': True
    }
    descriptions = {
        'grid_levels': '网格层数',
        'grid_spacing': '网格间距',
        'stop_loss': '止损阈值',
        'take_profit': '止盈阈值',
        'use_ml': '是否使用机器学习'
    }

    # 保存参数
    strategy.persist_params(params, descriptions, 'v1.0')
    print(f"\n参数已保存")

    # 加载参数
    loaded = strategy.load_persisted_params()
    print(f"加载的参数: {loaded}")

    # 应用参数到策略实例
    count = strategy.apply_params(loaded)
    print(f"已应用 {count} 个参数到策略实例")

    # 测试回测结果存储
    result = {
        'symbol': '000001.SH',
        'start_date': '2026-01-01',
        'end_date': '2026-05-18',
        'initial_balance': 100000,
        'final_balance': 112500,
        'total_return': 0.125,
        'sharpe_ratio': 1.8,
        'win_rate': 0.62,
        'total_trades': 150,
        'winning_trades': 93,
        'losing_trades': 57
    }
    strategy.save_backtest_result(result)
    history = strategy.get_backtest_history()
    print(f"\n回测历史记录数: {len(history)}")

    # 测试性能指标追踪
    strategy.track_metric('sharpe_ratio', 1.8)
    strategy.track_metric('win_rate', 0.62)
    strategy.track_metric('daily_return', 0.0025)
    summary = strategy.get_metric_summary()
    print(f"性能摘要: {summary}")

    # 测试交易记录
    strategy.save_trade('000001.SH', 'market', 'buy', 10.5, 100, 1050)
    strategy.save_trade('000001.SH', 'market', 'sell', 10.8, 100, 1080, 'closed', 30)
    stats = strategy.get_trade_stats()
    print(f"交易统计: {stats}")

    # 测试猴子补丁方式
    print("\n--- 测试猴子补丁方式 ---")

    class SimpleStrategy:
        def __init__(self):
            self.grid_levels = 50
            self.grid_spacing = 0.002

    enable_strategy_persistence(SimpleStrategy, 'SimpleStrategy')
    simple = SimpleStrategy()
    simple.persist_params({'grid_levels': 50, 'grid_spacing': 0.002})
    loaded_simple = simple.load_persisted_params()
    print(f"猴子补丁 - 加载参数: {loaded_simple}")

    print("\n✅ 策略持久化集成模块测试完成！")
