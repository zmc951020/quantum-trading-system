#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StrategyPerformanceTracker — 策略级绩效归因系统
=============================================
增益性优化模块，不修改现有策略代码，通过依赖注入提供完整的绩效追踪能力。

设计目标：
  1. 记录每笔交易的完整上下文（市场状态、信号置信度、风险评分等）
  2. 计算滚动绩效指标（夏普比率、卡玛比率、索提诺比率、盈亏比、胜率）
  3. 支持按策略、时间范围、市场状态维度查询
  4. 与 database_manager 集成，持久化到 trading_system.db

使用方式：
  tracker = StrategyPerformanceTracker()
  tracker.enabled = True
  tracker.record_trade(trade_data)
  metrics = tracker.get_rolling_metrics(strategy_name, window=20)

回滚方式：
  tracker.enabled = False  # 停止记录，不影响现有交易逻辑
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
import logging
import json
import math

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """单笔交易记录"""
    timestamp: str
    strategy: str
    action: str  # 'buy' or 'sell'
    quantity: float
    price: float
    market_regime: str = "unknown"
    signal_confidence: float = 0.0
    risk_score: float = 0.0
    portfolio_value_before: float = 0.0
    portfolio_value_after: float = 0.0
    reason_code: str = ""
    slippage: float = 0.0
    fee: float = 0.0
    profit: float = 0.0
    symbol: str = ""


@dataclass
class RollingMetrics:
    """滚动绩效指标"""
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_loss_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    avg_holding_period: float = 0.0
    return_decay_rate: float = 0.0


class StrategyPerformanceTracker:
    """
    策略级绩效归因系统

    单例模式，全局唯一实例，默认关闭。
    记录每笔交易的完整上下文，计算滚动绩效指标。
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_buffer_size: int = 10000):
        if self._initialized:
            return
        self._initialized = True

        self.enabled = False
        self.max_buffer_size = max_buffer_size

        # 按策略分组的交易缓冲区（内存缓存）
        self._trade_buffers: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_buffer_size)
        )

        # 按策略分组的滚动指标缓存
        self._metrics_cache: Dict[str, Dict[int, RollingMetrics]] = defaultdict(dict)

        # 数据库管理器（延迟加载）
        self._db = None

        # 回测历史记录（供 record_backtest 使用）
        self._backtest_history: Dict[str, list] = defaultdict(list)

        # 统计计数器
        self._total_trades_recorded = 0
        self._db_write_errors = 0

        logger.info("[StrategyPerformanceTracker] 初始化完成，默认关闭")

    @property
    def db(self):
        """延迟加载数据库管理器"""
        if self._db is None:
            try:
                from utils.database_manager import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"[StrategyPerformanceTracker] 数据库管理器加载失败: {e}")
        return self._db

    # ==================== 核心接口 ====================

    def record_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        记录一笔交易

        Args:
            trade_data: 交易数据字典，包含:
                - strategy: 策略名称
                - action: 交易动作 ('buy'/'sell')
                - quantity: 数量
                - price: 价格
                - timestamp: 时间戳（可选，默认当前时间）
                - market_regime: 市场状态（可选）
                - signal_confidence: 信号置信度（可选）
                - risk_score: 风险评分（可选）
                - portfolio_value_before: 交易前组合价值（可选）
                - portfolio_value_after: 交易后组合价值（可选）
                - reason_code: 原因代码（可选）
                - slippage: 滑点（可选）
                - fee: 手续费（可选）
                - profit: 盈亏（可选）
                - symbol: 交易标的（可选）

        Returns:
            是否成功
        """
        if not self.enabled:
            return False

        try:
            # 构建交易记录
            record = TradeRecord(
                timestamp=trade_data.get('timestamp', datetime.now().isoformat()),
                strategy=trade_data.get('strategy', 'unknown'),
                action=trade_data.get('action', ''),
                quantity=trade_data.get('quantity', 0.0),
                price=trade_data.get('price', 0.0),
                market_regime=trade_data.get('market_regime', 'unknown'),
                signal_confidence=trade_data.get('signal_confidence', 0.0),
                risk_score=trade_data.get('risk_score', 0.0),
                portfolio_value_before=trade_data.get('portfolio_value_before', 0.0),
                portfolio_value_after=trade_data.get('portfolio_value_after', 0.0),
                reason_code=trade_data.get('reason_code', ''),
                slippage=trade_data.get('slippage', 0.0),
                fee=trade_data.get('fee', 0.0),
                profit=trade_data.get('profit', 0.0),
                symbol=trade_data.get('symbol', ''),
            )

            # 写入内存缓冲区
            strategy = record.strategy
            self._trade_buffers[strategy].append(record)
            self._total_trades_recorded += 1

            # 写入数据库
            if self.db:
                db_success = self._write_to_db(record)
                if not db_success:
                    self._db_write_errors += 1

            # 清除过期的指标缓存
            self._metrics_cache[strategy] = {}

            return True

        except Exception as e:
            logger.error(f"[StrategyPerformanceTracker] 记录交易失败: {e}")
            return False

    def get_rolling_metrics(self, strategy_name: str,
                           window: int = 20) -> RollingMetrics:
        """
        获取滚动绩效指标

        Args:
            strategy_name: 策略名称
            window: 滚动窗口大小（交易笔数）

        Returns:
            滚动绩效指标
        """
        if not self.enabled:
            return RollingMetrics()

        # 检查缓存
        if window in self._metrics_cache.get(strategy_name, {}):
            return self._metrics_cache[strategy_name][window]

        # 从缓冲区获取交易记录
        trades = list(self._trade_buffers.get(strategy_name, []))
        if len(trades) < 2:
            return RollingMetrics()

        # 取最近 window 笔交易
        recent_trades = trades[-window:] if len(trades) > window else trades

        metrics = self._calculate_metrics(recent_trades)

        # 缓存结果
        self._metrics_cache[strategy_name][window] = metrics

        return metrics

    def get_all_strategy_metrics(self, window: int = 20) -> Dict[str, RollingMetrics]:
        """
        获取所有策略的绩效指标

        Args:
            window: 滚动窗口大小

        Returns:
            策略名称到绩效指标的映射
        """
        result = {}
        for strategy in self._trade_buffers:
            result[strategy] = self.get_rolling_metrics(strategy, window)
        return result

    def get_trade_history(self, strategy_name: str = None,
                         limit: int = 100) -> List[Dict]:
        """
        获取交易历史

        Args:
            strategy_name: 策略名称（可选，None表示所有策略）
            limit: 返回数量

        Returns:
            交易历史列表
        """
        if strategy_name:
            trades = list(self._trade_buffers.get(strategy_name, []))
        else:
            trades = []
            for buf in self._trade_buffers.values():
                trades.extend(buf)

        # 按时间戳降序排列
        trades.sort(key=lambda t: t.timestamp, reverse=True)

        return [self._trade_to_dict(t) for t in trades[:limit]]

    def get_performance_summary(self, strategy_name: str) -> Dict:
        """
        获取绩效摘要

        Args:
            strategy_name: 策略名称

        Returns:
            绩效摘要字典
        """
        trades = list(self._trade_buffers.get(strategy_name, []))
        if not trades:
            return {}

        profits = [t.profit for t in trades if t.profit != 0]
        winning = [p for p in profits if p > 0]
        losing = [p for p in profits if p < 0]

        summary = {
            'total_trades': len(trades),
            'total_profit': sum(profits),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': len(winning) / len(profits) if profits else 0,
            'avg_profit': np.mean(profits) if profits else 0,
            'avg_win': np.mean(winning) if winning else 0,
            'avg_loss': np.mean(losing) if losing else 0,
            'profit_loss_ratio': abs(np.mean(winning) / np.mean(losing)) if winning and losing else 0,
            'max_profit': max(profits) if profits else 0,
            'max_loss': min(profits) if profits else 0,
            'std_profit': np.std(profits) if len(profits) > 1 else 0,
        }

        # 计算最大回撤
        if len(trades) > 1:
            portfolio_values = [t.portfolio_value_after for t in trades
                              if t.portfolio_value_after > 0]
            if portfolio_values:
                peak = portfolio_values[0]
                max_dd = 0
                for v in portfolio_values:
                    if v > peak:
                        peak = v
                    dd = (peak - v) / peak
                    if dd > max_dd:
                        max_dd = dd
                summary['max_drawdown'] = max_dd

        return summary

    def get_trades_by_regime(self, strategy_name: str) -> Dict[str, List[Dict]]:
        """
        按市场状态分组获取交易

        Args:
            strategy_name: 策略名称

        Returns:
            市场状态到交易列表的映射
        """
        trades = list(self._trade_buffers.get(strategy_name, []))
        result = defaultdict(list)

        for t in trades:
            result[t.market_regime].append(self._trade_to_dict(t))

        return dict(result)

    def get_trades_by_reason(self, strategy_name: str) -> Dict[str, List[Dict]]:
        """
        按原因代码分组获取交易

        Args:
            strategy_name: 策略名称

        Returns:
            原因代码到交易列表的映射
        """
        trades = list(self._trade_buffers.get(strategy_name, []))
        result = defaultdict(list)

        for t in trades:
            result[t.reason_code].append(self._trade_to_dict(t))

        return dict(result)

    def record_backtest(self,
                       strategy_name: str,
                       annual_return: float = 0.0,
                       sharpe_ratio: float = 0.0,
                       max_drawdown: float = 0.0,
                       win_rate: float = 0.0,
                       total_trades: int = 0) -> bool:
        """
        记录回测结果（供 shepherd_five_line_optimizer 调用）

        Args:
            strategy_name: 策略名称
            annual_return: 年化收益率
            sharpe_ratio: 夏普比率
            max_drawdown: 最大回撤（正值）
            win_rate: 胜率
            total_trades: 总交易次数

        Returns:
            是否成功记录
        """
        if not self.enabled:
            return False

        try:
            record = {
                'strategy_name': strategy_name,
                'annual_return': annual_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'timestamp': datetime.now().isoformat(),
            }

            # 记录到回测历史
            self._backtest_history[strategy_name].append(record)

            # 限制历史长度
            if len(self._backtest_history[strategy_name]) > 100:
                self._backtest_history[strategy_name] = \
                    self._backtest_history[strategy_name][-100:]

            self._total_trades_recorded += 1
            logger.info(
                f"[PerfTracker] 回测记录已保存: "
                f"策略={strategy_name}, "
                f"年化={annual_return:.2%}, "
                f"夏普={sharpe_ratio:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"[PerfTracker] 记录回测失败: {e}")
            return False

    # ==================== 内部方法 ====================

    def _calculate_metrics(self, trades: List[TradeRecord]) -> RollingMetrics:
        """计算滚动绩效指标"""
        if len(trades) < 2:
            return RollingMetrics()

        metrics = RollingMetrics()
        metrics.total_trades = len(trades)

        # 提取盈亏序列
        profits = np.array([t.profit for t in trades if t.profit != 0])
        if len(profits) < 2:
            return metrics

        metrics.total_profit = float(np.sum(profits))

        # 胜率
        winning = profits[profits > 0]
        losing = profits[profits < 0]
        metrics.win_rate = float(len(winning) / len(profits)) if len(profits) > 0 else 0.0

        # 盈亏比
        avg_win = float(np.mean(winning)) if len(winning) > 0 else 0.0
        avg_loss = float(abs(np.mean(losing))) if len(losing) > 0 else 1.0
        metrics.profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        # 夏普比率（假设无风险利率为0）
        if np.std(profits) > 0:
            metrics.sharpe_ratio = float(
                np.mean(profits) / np.std(profits) * np.sqrt(252)
            )

        # 索提诺比率（仅考虑下行波动）
        downside = profits[profits < 0]
        if len(downside) > 0 and np.std(downside) > 0:
            metrics.sortino_ratio = float(
                np.mean(profits) / np.std(downside) * np.sqrt(252)
            )

        # 最大回撤
        portfolio_values = [t.portfolio_value_after for t in trades
                          if t.portfolio_value_after > 0]
        if portfolio_values:
            peak = portfolio_values[0]
            max_dd = 0.0
            for v in portfolio_values:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak
                if dd > max_dd:
                    max_dd = dd
            metrics.max_drawdown = max_dd

            # 卡玛比率
            if max_dd > 0:
                total_return = (portfolio_values[-1] - portfolio_values[0]) / portfolio_values[0]
                metrics.calmar_ratio = total_return / max_dd

        # 收益衰减率（最近N笔收益 / 总收益）
        if len(profits) >= 20:
            recent_profits = profits[-10:]
            total_abs = float(np.sum(np.abs(profits)))
            if total_abs > 0:
                metrics.return_decay_rate = float(np.sum(recent_profits)) / total_abs

        return metrics

    def _write_to_db(self, record: TradeRecord) -> bool:
        """写入数据库"""
        try:
            if self.db:
                return self.db.save_performance_metric(
                    strategy_name=record.strategy,
                    metric_name='trade_record',
                    metric_value=record.profit,
                    symbol=record.symbol,
                    period=record.timestamp
                )
            return False
        except Exception as e:
            logger.warning(f"[StrategyPerformanceTracker] 数据库写入失败: {e}")
            return False

    def _trade_to_dict(self, trade: TradeRecord) -> Dict:
        """将 TradeRecord 转换为字典"""
        return {
            'timestamp': trade.timestamp,
            'strategy': trade.strategy,
            'action': trade.action,
            'quantity': trade.quantity,
            'price': trade.price,
            'market_regime': trade.market_regime,
            'signal_confidence': trade.signal_confidence,
            'risk_score': trade.risk_score,
            'portfolio_value_before': trade.portfolio_value_before,
            'portfolio_value_after': trade.portfolio_value_after,
            'reason_code': trade.reason_code,
            'slippage': trade.slippage,
            'fee': trade.fee,
            'profit': trade.profit,
            'symbol': trade.symbol,
        }

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict:
        """获取跟踪器统计信息"""
        return {
            'enabled': self.enabled,
            'total_trades_recorded': self._total_trades_recorded,
            'db_write_errors': self._db_write_errors,
            'active_strategies': list(self._trade_buffers.keys()),
            'buffer_sizes': {
                s: len(buf) for s, buf in self._trade_buffers.items()
            },
            'max_buffer_size': self.max_buffer_size,
        }

    def reset(self, strategy_name: str = None):
        """
        重置交易数据

        Args:
            strategy_name: 策略名称（可选，None表示重置所有）
        """
        if strategy_name:
            self._trade_buffers[strategy_name].clear()
            self._metrics_cache[strategy_name] = {}
        else:
            self._trade_buffers.clear()
            self._metrics_cache.clear()
            self._total_trades_recorded = 0
            self._db_write_errors = 0


# ==================== 全局单例 ====================

_global_tracker = None


def get_performance_tracker() -> StrategyPerformanceTracker:
    """获取全局性能跟踪器实例"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = StrategyPerformanceTracker()
    return _global_tracker


# ==================== 便捷函数 ====================

def record_trade(trade_data: Dict[str, Any]) -> bool:
    """便捷函数：记录一笔交易"""
    tracker = get_performance_tracker()
    return tracker.record_trade(trade_data)


def get_metrics(strategy_name: str, window: int = 20) -> RollingMetrics:
    """便捷函数：获取滚动绩效指标"""
    tracker = get_performance_tracker()
    return tracker.get_rolling_metrics(strategy_name, window)


# ==================== 自测 ====================

if __name__ == '__main__':
    # 启用跟踪器
    tracker = get_performance_tracker()
    tracker.enabled = True

    print("=" * 60)
    print("StrategyPerformanceTracker 自测")
    print("=" * 60)

    # 模拟交易记录
    import random
    base_price = 100.0
    portfolio = 100000.0

    for i in range(100):
        price = base_price + random.uniform(-5, 5)
        action = 'buy' if random.random() > 0.5 else 'sell'
        quantity = random.randint(10, 100)
        profit = random.uniform(-50, 80)

        trade = {
            'strategy': 'TestStrategy',
            'action': action,
            'quantity': quantity,
            'price': price,
            'profit': profit,
            'portfolio_value_before': portfolio,
            'portfolio_value_after': portfolio + profit,
            'market_regime': random.choice(['range_bound', 'trending_up', 'trending_down']),
            'signal_confidence': random.uniform(0.5, 1.0),
            'risk_score': random.uniform(0, 50),
            'reason_code': random.choice(['grid_buy', 'grid_sell', 'trend_follow', 'mean_reversion']),
            'symbol': '000001.SH',
        }
        tracker.record_trade(trade)
        portfolio += profit

    # 获取指标
    metrics = tracker.get_rolling_metrics('TestStrategy', window=50)
    print(f"\n滚动绩效指标 (window=50):")
    print(f"  总交易数: {metrics.total_trades}")
    print(f"  总盈亏: {metrics.total_profit:.2f}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  盈亏比: {metrics.profit_loss_ratio:.2f}")
    print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"  索提诺比率: {metrics.sortino_ratio:.2f}")
    print(f"  卡玛比率: {metrics.calmar_ratio:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")

    # 获取摘要
    summary = tracker.get_performance_summary('TestStrategy')
    print(f"\n绩效摘要:")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # 按市场状态分组
    by_regime = tracker.get_trades_by_regime('TestStrategy')
    print(f"\n按市场状态分组:")
    for regime, trades in by_regime.items():
        print(f"  {regime}: {len(trades)} 笔交易")

    # 统计信息
    stats = tracker.get_stats()
    print(f"\n跟踪器统计:")
    print(f"  启用: {stats['enabled']}")
    print(f"  总记录数: {stats['total_trades_recorded']}")
    print(f"  活跃策略: {stats['active_strategies']}")

    print("\n✅ StrategyPerformanceTracker 自测完成！")
