# -*- coding: utf-8 -*-
"""
智能体自动发现与注册系统
自动扫描目录，检测并注册新策略
"""

import os
import importlib.util
from pathlib import Path
from typing import List, Dict, Any
import inspect

class StrategyDiscovery:
    """
    智能体策略自动发现系统
    功能：
    1. 自动扫描策略目录
    2. 检测新策略文件
    3. 自动注册策略
    4. 智能分类
    """

    def __init__(self, strategies_dir: str = "strategies"):
        """
        初始化策略发现系统

        Args:
            strategies_dir: 策略目录路径
        """
        self.strategies_dir = strategies_dir
        self.known_strategies = set()
        self.discovered_strategies = []

    def scan_strategies(self) -> List[Dict[str, Any]]:
        """
        扫描策略目录，检测所有策略

        Returns:
            检测到的策略列表
        """
        print("[智能体发现系统] 正在扫描策略目录...")

        discovered = []
        strategies_path = Path(self.strategies_dir)

        if not strategies_path.exists():
            print(f"[智能体发现系统] 目录不存在: {self.strategies_dir}")
            return []

        for file_path in strategies_path.glob("*.py"):
            if file_path.name.startswith("_") or file_path.name.startswith("test_"):
                continue

            strategy_info = self._analyze_strategy_file(file_path)
            if strategy_info:
                discovered.append(strategy_info)

        self.discovered_strategies = discovered
        print(f"[智能体发现系统] 发现 {len(discovered)} 个策略")

        return discovered

    def _analyze_strategy_file(self, file_path: Path) -> Dict[str, Any]:
        """
        分析策略文件，提取策略信息

        Args:
            file_path: 策略文件路径

        Returns:
            策略信息字典
        """
        try:
            module_name = file_path.stem

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)

            try:
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"[智能体发现系统] 加载模块 {module_name} 失败: {e}")
                return None

            strategy_class = self._find_strategy_class(module)

            if strategy_class:
                return {
                    'name': strategy_class.__name__,
                    'file': str(file_path),
                    'type': self._classify_strategy(strategy_class.__name__),
                    'module': module_name,
                    'description': self._get_class_docstring(strategy_class)
                }

        except Exception as e:
            print(f"[智能体发现系统] 分析文件 {file_path} 失败: {e}")

        return None

    def _find_strategy_class(self, module) -> Any:
        """查找模块中的策略类"""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if hasattr(obj, '__init__'):
                params = inspect.signature(obj.__init__).parameters
                if any('balance' in p or 'strategy' in p.lower() for p in params.keys()):
                    return obj
        return None

    def _classify_strategy(self, class_name: str) -> str:
        """根据类名自动分类策略"""
        class_name_lower = class_name.lower()

        if 'ppo' in class_name_lower or 'rl' in class_name_lower or 'reinforce' in class_name_lower:
            return '强化学习'
        elif 'fourier' in class_name_lower:
            return '傅里叶分析'
        elif 'ml' in class_name_lower or 'machine' in class_name_lower:
            return '机器学习'
        elif 'grid' in class_name_lower:
            return '网格交易'
        elif 'trend' in class_name_lower or 'follow' in class_name_lower:
            return '趋势跟踪'
        elif 'value' in class_name_lower:
            return '价值投资'
        elif 'adaptive' in class_name_lower:
            return '自适应'
        else:
            return '其他'

    def _get_class_docstring(self, strategy_class) -> str:
        """获取类的文档字符串"""
        if hasattr(strategy_class, '__doc__') and strategy_class.__doc__:
            return strategy_class.__doc__.strip()
        return "无描述"

    def detect_new_strategies(self) -> List[Dict[str, Any]]:
        """
        检测新策略（相对于已注册策略）

        Returns:
            新策略列表
        """
        discovered = self.scan_strategies()

        new_strategies = []
        for strategy in discovered:
            if strategy['name'] not in self.known_strategies:
                new_strategies.append(strategy)
                self.known_strategies.add(strategy['name'])

        if new_strategies:
            print(f"[智能体发现系统] 🆕 发现 {len(new_strategies)} 个新策略:")
            for strategy in new_strategies:
                print(f"  - {strategy['name']} ({strategy['type']})")

        return new_strategies

    def auto_register_to_backtest_system(self, backtest_system) -> int:
        """
        自动注册新策略到回测系统

        Args:
            backtest_system: 回测系统实例

        Returns:
            注册的策略数量
        """
        new_strategies = self.detect_new_strategies()

        if not new_strategies:
            print("[智能体发现系统] ✅ 没有发现新策略")
            return 0

        print(f"[智能体发现系统] 🤖 正在注册 {len(new_strategies)} 个新策略到回测系统...")

        for strategy in new_strategies:
            backtest_system.register_strategy(
                name=strategy['name'],
                strategy_type=strategy['type'],
                file_path=strategy['file'],
                description=strategy['description']
            )
            print(f"[智能体发现系统] ✅ 已注册: {strategy['name']}")

        return len(new_strategies)


_strategy_discovery = None

def get_strategy_discovery() -> StrategyDiscovery:
    """获取策略发现系统实例"""
    global _strategy_discovery
    if _strategy_discovery is None:
        _strategy_discovery = StrategyDiscovery()
    return _strategy_discovery
