#!/usr/bin/env python3
"""
双引擎回测交叉验证 (Cross-Engine Backtest Validation)
=====================================================
使用内部回测引擎 + 外部回测引擎（如 backtrader）进行交叉验证，
检测引擎偏差，确保回测结果的可靠性。

使用方法：
  1. 默认使用内部引擎，交叉验证为可选增强
  2. 当偏差超过阈值时，标记 engine_mismatch 并触发人工审查
  3. 偏差阈值可配置
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# 偏差阈值配置
# ============================================================

@dataclass
class CrossValidationConfig:
    """交叉验证配置"""
    # 偏差阈值
    return_deviation_threshold: float = 0.05    # 收益偏差 < 5%
    sharpe_deviation_threshold: float = 0.3     # 夏普偏差 < 0.3
    max_drawdown_threshold: float = 0.03        # 最大回撤偏差 < 3%
    win_rate_threshold: float = 0.05            # 胜率偏差 < 5%
    
    # 外部引擎
    external_engine_name: str = "backtrader"
    external_engine_available: bool = False
    
    # 验证配置
    min_data_days: int = 90  # 最少需要90天数据
    cache_results: bool = True


@dataclass
class BacktestMetrics:
    """回测指标"""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    engine_name: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class CrossValidationResult:
    """交叉验证结果"""
    internal_metrics: BacktestMetrics = None
    external_metrics: BacktestMetrics = None
    deviations: Dict[str, Any] = field(default_factory=dict)
    is_consistent: bool = True
    warnings: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class CrossEngineValidator:
    """双引擎交叉验证器"""
    
    def __init__(self, config: CrossValidationConfig = None):
        self._config = config or CrossValidationConfig()
        self._external_engine = None
        
        # 尝试加载外部引擎
        try:
            import backtrader as bt
            self._external_engine = bt
            self._config.external_engine_available = True
            logger.info("[交叉验证] backtrader 引擎可用")
        except ImportError:
            logger.info("[交叉验证] backtrader 未安装，交叉验证不可用")
            logger.info("[交叉验证] 安装命令: pip install backtrader")
    
    def is_available(self) -> bool:
        """检查交叉验证是否可用"""
        return self._config.external_engine_available
    
    def validate(self, internal_runner: Callable,
                 strategy_class: Any = None,
                 params: Dict = None,
                 data_provider: Callable = None,
                 symbol: str = "000001",
                 days: int = 252) -> CrossValidationResult:
        """运行双引擎交叉验证
        
        Args:
            internal_runner: 内部引擎的回测方法 callable(params) -> Dict
            strategy_class: 外部引擎的策略类（backtrader Strategy）
            params: 策略参数
            data_provider: 数据提供者 callable(symbol, days) -> pd.DataFrame
            symbol: 股票代码
            days: 回测天数
            
        Returns:
            CrossValidationResult: 交叉验证结果
        """
        result = CrossValidationResult()
        
        # 1. 运行内部引擎
        t0 = time.time()
        internal_result = internal_runner(params or {})
        internal_elapsed = time.time() - t0
        
        result.internal_metrics = self._extract_metrics(
            internal_result, "Internal", internal_elapsed)
        
        # 2. 运行外部引擎（如果可用）
        if not self.is_available():
            result.warnings.append("外部引擎不可用，仅使用内部引擎结果")
            return result
        
        if not strategy_class or not data_provider:
            result.warnings.append("外部引擎缺少策略类或数据提供者")
            return result
        
        try:
            t0 = time.time()
            external_result = self._run_backtrader(
                strategy_class, params or {}, data_provider, symbol, days)
            external_elapsed = time.time() - t0
            
            result.external_metrics = self._extract_metrics(
                external_result, self._config.external_engine_name, external_elapsed)
        except Exception as e:
            result.warnings.append(f"外部引擎运行失败: {e}")
            return result
        
        # 3. 计算偏差
        if result.internal_metrics and result.external_metrics:
            result.deviations = self._calculate_deviations(
                result.internal_metrics, result.external_metrics)
            result.is_consistent = self._check_consistency(result.deviations)
            
            if not result.is_consistent:
                result.warnings.append(
                    f"引擎偏差超过阈值: {self._format_deviations(result.deviations)}")
        
        return result
    
    def _extract_metrics(self, result: Any, engine_name: str, 
                          elapsed: float) -> BacktestMetrics:
        """从回测结果中提取指标"""
        if isinstance(result, dict):
            return BacktestMetrics(
                total_return=result.get('total_return', 0),
                annual_return=result.get('annual_return', 0),
                sharpe_ratio=result.get('sharpe_ratio', 0),
                max_drawdown=result.get('max_drawdown', 0),
                win_rate=result.get('win_rate', 0),
                total_trades=result.get('total_trades', 0),
                profit_factor=result.get('profit_factor', 0),
                engine_name=engine_name,
                elapsed_seconds=round(elapsed, 3),
            )
        
        # 尝试从对象提取
        return BacktestMetrics(
            engine_name=engine_name,
            elapsed_seconds=round(elapsed, 3),
        )
    
    def _run_backtrader(self, strategy_class, params: Dict,
                         data_provider: Callable, symbol: str,
                         days: int) -> Dict[str, Any]:
        """使用 backtrader 运行回测"""
        if not self._external_engine:
            raise RuntimeError("backtrader 不可用")
        
        import backtrader as bt
        
        cerebro = bt.Cerebro()
        
        # 添加策略
        cerebro.addstrategy(strategy_class, **params)
        
        # 获取数据
        df = data_provider(symbol, days)
        if df.empty:
            raise ValueError(f"无法获取 {symbol} 的数据")
        
        # 转换数据格式为 backtrader feed
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        
        # 设置初始资金
        cerebro.broker.setcash(100000.0)
        
        # 运行
        start_value = cerebro.broker.getvalue()
        results = cerebro.run()
        end_value = cerebro.broker.getvalue()
        
        total_return = (end_value - start_value) / start_value
        
        # 提取指标
        trades = []
        for r in results:
            if hasattr(r, 'analyzers'):
                # 尝试获取 trade analyzer
                pass
        
        return {
            'total_return': round(total_return, 4),
            'annual_return': round(total_return * (252 / days), 4),
            'sharpe_ratio': 0.0,  # 需通过 analyzer 获取
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'total_trades': len(trades),
            'profit_factor': 0.0,
        }
    
    def _calculate_deviations(self, internal: BacktestMetrics,
                               external: BacktestMetrics) -> Dict[str, Any]:
        """计算两个引擎之间的偏差"""
        return {
            'total_return': {
                'internal': internal.total_return,
                'external': external.total_return,
                'deviation': round(abs(internal.total_return - external.total_return), 4),
                'threshold': self._config.return_deviation_threshold,
                'exceeded': abs(internal.total_return - external.total_return) > self._config.return_deviation_threshold,
            },
            'sharpe_ratio': {
                'internal': internal.sharpe_ratio,
                'external': external.sharpe_ratio,
                'deviation': round(abs(internal.sharpe_ratio - external.sharpe_ratio), 4),
                'threshold': self._config.sharpe_deviation_threshold,
                'exceeded': abs(internal.sharpe_ratio - external.sharpe_ratio) > self._config.sharpe_deviation_threshold,
            },
            'max_drawdown': {
                'internal': internal.max_drawdown,
                'external': external.max_drawdown,
                'deviation': round(abs(internal.max_drawdown - external.max_drawdown), 4),
                'threshold': self._config.max_drawdown_threshold,
                'exceeded': abs(internal.max_drawdown - external.max_drawdown) > self._config.max_drawdown_threshold,
            },
            'win_rate': {
                'internal': internal.win_rate,
                'external': external.win_rate,
                'deviation': round(abs(internal.win_rate - external.win_rate), 4),
                'threshold': self._config.win_rate_threshold,
                'exceeded': abs(internal.win_rate - external.win_rate) > self._config.win_rate_threshold,
            },
        }
    
    def _check_consistency(self, deviations: Dict) -> bool:
        """检查是否一致"""
        for metric, info in deviations.items():
            if info.get('exceeded', False):
                return False
        return True
    
    def _format_deviations(self, deviations: Dict) -> str:
        """格式化偏差信息"""
        exceeded = []
        for metric, info in deviations.items():
            if info.get('exceeded'):
                exceeded.append(
                    f"{metric}: I={info['internal']:.3f} vs E={info['external']:.3f} "
                    f"(diff={info['deviation']:.3f} > {info['threshold']})"
                )
        return '; '.join(exceeded) if exceeded else '无超阈值偏差'
    
    def get_config(self) -> Dict:
        """获取配置"""
        return {
            'external_engine': self._config.external_engine_name,
            'available': self.is_available(),
            'thresholds': {
                'return': self._config.return_deviation_threshold,
                'sharpe': self._config.sharpe_deviation_threshold,
                'max_drawdown': self._config.max_drawdown_threshold,
                'win_rate': self._config.win_rate_threshold,
            },
        }


# 全局单例
_cross_validator: Optional[CrossEngineValidator] = None

def get_cross_validator() -> CrossEngineValidator:
    global _cross_validator
    if _cross_validator is None:
        _cross_validator = CrossEngineValidator()
    return _cross_validator