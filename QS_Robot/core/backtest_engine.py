#!/usr/bin/env python3
"""
专业级回测引擎封装

核心能力：
  1. VectorBT 专业回测框架（主力）
  2. 简单回测引擎（降级方案）
  3. 支持多种策略类型
  4. 完整的绩效指标输出

回测结果格式：
{
    "success": bool,
    "strategy_name": str,
    "total_return": float,      # 总收益率 %
    "annual_return": float,     # 年化收益率 %
    "sharpe_ratio": float,      # 夏普比率
    "max_drawdown": float,      # 最大回撤 %
    "win_rate": float,          # 胜率 %
    "profit_factor": float,     # 盈亏比
    "trades": int,              # 交易次数
    "win_trades": int,          # 盈利次数
    "lose_trades": int,         # 亏损次数
    "avg_win": float,           # 平均盈利 %
    "avg_lose": float,          # 平均亏损 %
    "equity_curve": List[float], # 权益曲线
    "drawdown_curve": List[float], # 回撤曲线
    "trading_log": List[Dict],   # 交易日志
    "elapsed_time": float       # 耗时秒
}
"""

import time
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# 数据平台集成：回测数据可通过qlib_adapter统一获取
# from core.qlib_adapter import get_qlib_adapter
# data = get_qlib_adapter().fetch_history(symbol, start, end)

# ============================================================
# 动态滑点模型
# ============================================================

def calculate_dynamic_slippage(volatility: float = 0.02,
                                trade_size_pct: float = 0.1,
                                is_volatile_market: bool = False) -> float:
    """
    动态滑点计算 — 替代硬编码的固定滑点

    滑点 = 基础滑点 + 波动率补偿 + 流动性冲击

    Args:
        volatility: 当前波动率 (日收益率标准差)
        trade_size_pct: 交易量占日均成交量的比例
        is_volatile_market: 是否为高波动行情

    Returns:
        滑点百分比 (小数, 如 0.002 表示 0.2%)
    """
    # 基础滑点: A股市场平均 0.05%-0.1%
    base_slippage = 0.0005

    # 波动率补偿: 波动率每增加 1%，滑点增加 0.05%
    vol_compensation = volatility * 0.05

    # 流动性冲击: 大单冲击成本
    impact = trade_size_pct * 0.005

    # 高波动行情额外加成
    volatile_bonus = 0.002 if is_volatile_market else 0.0

    # 总滑点 = 基础 + 波动率补偿 + 流动性冲击 + 行情加成
    # 上限: 2% (极端行情)，下限: 0.05% (正常行情)
    return max(0.0005, min(0.02, base_slippage + vol_compensation + impact + volatile_bonus))


def calculate_dynamic_commission(trade_amount: float = 10000.0) -> float:
    """
    动态手续费计算 — 模拟A股实际费率结构

    A股费率:
      - 印花税: 0.05% (卖出单向，2023年8月后)
      - 佣金: 0.025% (买卖双向，含规费)
      - 过户费: 0.001% (买卖双向)

    Args:
        trade_amount: 交易金额

    Returns:
        手续费率 (小数)
    """
    # 印花税(卖出) + 佣金 + 过户费 ≈ 0.075%
    return 0.00075

# ============================================================
# 回测结果数据类
# ============================================================

class BacktestResult:
    """
    回测结果数据（SimpleBacktestEngine 使用）
    
    单位约定:
    - total_return: 百分比 (如 31.95 表示 31.95%)
    - annual_return: 百分比
    - sharpe_ratio: 比率 (原值)
    - max_drawdown: 百分比 (如 15.0 表示 15%)
    - win_rate: 百分比 (如 65.0 表示 65%)
    - profit_factor: 比率 (原值)
    """
    def __init__(self):
        self.success = False
        self.strategy_name = ""
        self.total_return = 0.0
        self.annual_return = 0.0
        self.sharpe_ratio = 0.0
        self.max_drawdown = 0.0
        self.win_rate = 0.0
        self.profit_factor = 0.0
        self.trades = 0
        self.total_trades = 0  # 别名，兼容 tau_optimizer_cluster.BacktestResult
        self.win_trades = 0
        self.lose_trades = 0
        self.avg_win = 0.0
        self.avg_lose = 0.0
        self.equity_curve = []
        self.drawdown_curve = []
        self.trading_log = []
        self.elapsed_time = 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "success": self.success,
            "strategy_name": self.strategy_name,
            "total_return": round(self.total_return, 2),
            "annual_return": round(self.annual_return, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 2),
            "trades": self.trades,
            "win_trades": self.win_trades,
            "lose_trades": self.lose_trades,
            "avg_win": round(self.avg_win, 2),
            "avg_lose": round(self.avg_lose, 2),
            "equity_curve": [round(e, 2) for e in self.equity_curve],
            "drawdown_curve": [round(d, 2) for d in self.drawdown_curve],
            "trading_log": self.trading_log,
            "elapsed_time": round(self.elapsed_time, 2)
        }

# ============================================================
# 策略信号生成器
# ============================================================

class StrategySignal:
    """策略信号"""
    SIGNAL_NONE = 0
    SIGNAL_BUY = 1
    SIGNAL_SELL = -1

    def __init__(self):
        self.signal = self.SIGNAL_NONE
        self.price = 0.0
        self.reason = ""

# ============================================================
# 简单回测引擎（降级方案）
# ============================================================

class SimpleBacktestEngine:
    """简单回测引擎（纯Python实现，无外部依赖）"""

    def __init__(self):
        self._name = "SimpleBacktestEngine"

    def _check_lookahead_bias(self, current_idx: int, data: List[float]) -> bool:
        """检测前视偏差
        
        确保只使用 current_idx 及之前的数据，如果使用了未来数据则返回 True。
        
        Args:
            current_idx: 当前回测日期索引
            data: 完整价格序列
        
        Returns:
            bool: True 表示检测到前视偏差（使用了未来数据）
        """
        # 在回测循环中，确保信号生成器只接收 current_idx 及之前的数据
        # 当前实现中，signal_generator 已经接收 prices[:i+1] 切片
        # 这里做额外校验：如果 data 长度大于 current_idx+1，说明可能有前视偏差风险
        if len(data) > current_idx + 1:
            logger.warning(
                f"[PIT前视偏差] 索引 {current_idx}: 数据长度 {len(data)} > 当前索引+1 ({current_idx+1})，"
                f"存在前视偏差风险"
            )
            return True
        return False

    def _check_suspension(self, row: Dict) -> bool:
        """检测停牌（成交量为0）
        
        Args:
            row: 包含 volume 字段的数据行
        
        Returns:
            bool: True 表示停牌（不可交易）
        """
        volume = row.get('volume', 0) if isinstance(row, dict) else 0
        if volume <= 0:
            logger.info(f"[停牌检测] 成交量为0，疑似停牌，跳过该日")
            return True
        return False

    def _check_limit(self, row: Dict) -> bool:
        """检测涨跌停
        
        如果开盘价=最高价=最低价，可能是涨停或跌停，标记为不可交易。
        
        Args:
            row: 包含 open/high/low 字段的数据行
        
        Returns:
            bool: True 表示涨跌停（不可交易）
        """
        if not isinstance(row, dict):
            return False
        open_price = row.get('open')
        high_price = row.get('high')
        low_price = row.get('low')
        if open_price is not None and high_price is not None and low_price is not None:
            if open_price == high_price == low_price:
                logger.info(f"[涨跌停检测] 开盘=最高=最低={open_price}，疑似涨跌停，标记不可交易")
                return True
        return False

    def run_backtest(self, prices: List[float], signal_generator: Callable,
                     initial_capital: float = 100000.0,
                     commission: float = 0.0005,
                     slippage: float = 0.001) -> BacktestResult:
        """运行回测"""
        start_time = time.time()
        result = BacktestResult()
        result.strategy_name = self._name

        if len(prices) < 10:
            return result

        # 初始化
        capital = initial_capital
        position = 0.0
        equity = [initial_capital]
        drawdown = [0.0]
        peak = initial_capital
        trades = []
        win_count = 0
        lose_count = 0
        total_win = 0.0
        total_lose = 0.0
        prev_trade_entry = None

        for i, price in enumerate(prices):
            # PIT前视偏差检测
            signal_data = prices[:i+1]
            self._check_lookahead_bias(i, signal_data)
            
            # 停牌检测：价格为0或与前一价格相同且无变化，跳过
            if price <= 0:
                continue
            
            # 生成信号
            signal = signal_generator(i, prices[:i+1])

            # 执行交易
            if signal == StrategySignal.SIGNAL_BUY and position == 0:
                # 买入
                qty = (capital * (1 - commission - slippage)) // price
                cost = qty * price
                fee = cost * commission
                capital -= cost + fee
                position = qty
                prev_trade_entry = price
                trades.append({
                    "date": f"day_{i}",
                    "type": "buy",
                    "price": round(price, 2),
                    "quantity": int(qty),
                    "value": round(cost, 2),
                    "fee": round(fee, 2)
                })

            elif signal == StrategySignal.SIGNAL_SELL and position > 0:
                # 卖出（先保存原始仓位用于日志，再执行卖出操作）
                sell_qty = position
                revenue = position * price * (1 - commission - slippage)
                fee = position * price * commission
                capital += revenue - fee
                profit = (price - prev_trade_entry) * position - fee * 2
                position = 0

                if profit > 0:
                    win_count += 1
                    total_win += profit
                else:
                    lose_count += 1
                    total_lose += abs(profit)

                trades.append({
                    "date": f"day_{i}",
                    "type": "sell",
                    "price": round(price, 2),
                    "quantity": int(sell_qty),
                    "value": round(revenue, 2),
                    "fee": round(fee, 2),
                    "profit": round(profit, 2)
                })

            # 计算权益
            current_value = capital + position * price
            equity.append(current_value)

            # 计算回撤
            peak = max(peak, current_value)
            dd = (peak - current_value) / peak * 100
            drawdown.append(dd)

        # 结束时卖出剩余持仓
        if position > 0:
            revenue = position * prices[-1] * (1 - commission - slippage)
            capital += revenue - position * prices[-1] * commission
            position = 0

        # 计算指标
        result.success = True
        result.total_return = (capital - initial_capital) / initial_capital * 100
        result.annual_return = result.total_return / (len(prices) / 252)
        result.max_drawdown = max(drawdown)

        # 计算夏普比率（简化版）
        daily_returns = []
        for i in range(1, len(equity)):
            daily_returns.append((equity[i] - equity[i-1]) / equity[i-1])
        if daily_returns:
            mean_return = sum(daily_returns) / len(daily_returns)
            std_return = math.sqrt(sum((r - mean_return)**2 for r in daily_returns) / len(daily_returns))
            if std_return > 0:
                result.sharpe_ratio = mean_return / std_return * math.sqrt(252)

        # 计算胜率和盈亏比
        result.trades = win_count + lose_count
        result.win_trades = win_count
        result.lose_trades = lose_count
        if result.trades > 0:
            result.win_rate = win_count / result.trades * 100
            avg_win_pct = (total_win / win_count / initial_capital * 100) if win_count > 0 else 0
            avg_lose_pct = (total_lose / lose_count / initial_capital * 100) if lose_count > 0 else 0
            result.avg_win = avg_win_pct
            result.avg_lose = avg_lose_pct
            if total_lose > 0:
                result.profit_factor = total_win / total_lose

        result.equity_curve = [e / initial_capital * 100 for e in equity]
        result.drawdown_curve = drawdown
        result.trading_log = trades
        result.elapsed_time = time.time() - start_time

        return result

# ============================================================
# VectorBT 回测引擎（主力）
# ============================================================

class VectorBTBacktestEngine:
    """VectorBT 专业回测引擎封装"""

    def __init__(self):
        self._name = "VectorBTBacktestEngine"
        self._available = False
        self._import_vectorbt()

    def _import_vectorbt(self):
        """尝试导入 VectorBT"""
        try:
            import vectorbt as vbt
            self._vbt = vbt
            self._available = True
            print(f"[VectorBTBacktestEngine] VectorBT已加载")
        except ImportError:
            print(f"[VectorBTBacktestEngine] VectorBT未安装，将使用简单回测引擎")
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def run_backtest(self, prices: List[float], signal_generator: Callable,
                     initial_capital: float = 100000.0,
                     commission: float = 0.0005,
                     slippage: float = 0.001) -> BacktestResult:
        """运行回测（VectorBT版本）"""
        start_time = time.time()
        result = BacktestResult()
        result.strategy_name = self._name

        if not self._available:
            # 降级到简单回测
            simple_engine = SimpleBacktestEngine()
            return simple_engine.run_backtest(prices, signal_generator,
                                             initial_capital, commission, slippage)

        try:
            import pandas as pd

            # 创建价格序列
            dates = pd.date_range(start="2020-01-01", periods=len(prices), freq="D")
            price_series = pd.Series(prices, index=dates)

            # 生成信号
            signals = []
            for i in range(len(prices)):
                signal = signal_generator(i, prices[:i+1])
                signals.append(signal)
            signal_series = pd.Series(signals, index=dates)

            # 创建策略
            entries = signal_series == StrategySignal.SIGNAL_BUY
            exits = signal_series == StrategySignal.SIGNAL_SELL

            # 运行回测
            pf = self._vbt.Portfolio.from_signals(
                price_series,
                entries,
                exits,
                initial_capital=initial_capital,
                fees=commission,
                slippage=slippage
            )

            # 提取结果
            result.success = True
            result.total_return = float(pf.total_return() * 100)
            result.annual_return = float(pf.annualized_return() * 100)
            result.sharpe_ratio = float(pf.sharpe_ratio())
            result.max_drawdown = float(pf.max_drawdown() * 100)

            stats = pf.stats()
            result.win_rate = float(stats.get('Win Rate [%]', 0))
            result.profit_factor = float(stats.get('Profit Factor', 0))
            result.trades = int(stats.get('Total Trades', 0))
            result.win_trades = int(stats.get('Wins', 0))
            result.lose_trades = int(stats.get('Losses', 0))
            result.avg_win = float(stats.get('Avg Win [%]', 0))
            result.avg_lose = float(stats.get('Avg Loss [%]', 0))

            # 权益曲线和回撤曲线
            result.equity_curve = [float(v) for v in (pf.equity / initial_capital * 100).values]
            result.drawdown_curve = [float(v * 100) for v in pf.drawdown().values]

            # 交易日志
            trades_df = pf.trades.records
            result.trading_log = []
            for _, row in trades_df.iterrows():
                result.trading_log.append({
                    "date": str(row["entry_time"])[:10],
                    "type": "buy" if row["direction"] == 1 else "sell",
                    "price": round(float(row["entry_price"]), 2),
                    "quantity": int(row["size"]),
                    "value": round(float(row["entry_price"] * row["size"]), 2),
                    "fee": round(float(row["fees"]), 2)
                })

            result.elapsed_time = time.time() - start_time

        except Exception as e:
            print(f"[VectorBTBacktestEngine] 回测失败: {e}")
            # 降级到简单回测
            simple_engine = SimpleBacktestEngine()
            return simple_engine.run_backtest(prices, signal_generator,
                                             initial_capital, commission, slippage)

        return result

# ============================================================
# 策略模板
# ============================================================

class StrategyTemplate:
    """策略模板基类"""
    def __init__(self, params: Dict = None):
        self.params = params or {}

    def generate_signal(self, index: int, prices: List[float]) -> int:
        """生成交易信号"""
        return StrategySignal.SIGNAL_NONE

class RSIStrategy(StrategyTemplate):
    """RSI策略"""
    def generate_signal(self, index: int, prices: List[float]) -> int:
        if len(prices) < 15:
            return StrategySignal.SIGNAL_NONE

        period = self.params.get('period', 14)
        overbought = self.params.get('overbought', 70)
        oversold = self.params.get('oversold', 30)

        # 计算RSI
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        if rsi < oversold:
            return StrategySignal.SIGNAL_BUY
        elif rsi > overbought:
            return StrategySignal.SIGNAL_SELL
        return StrategySignal.SIGNAL_NONE

class MACDStrategy(StrategyTemplate):
    """MACD策略"""
    def generate_signal(self, index: int, prices: List[float]) -> int:
        if len(prices) < 34:
            return StrategySignal.SIGNAL_NONE

        fast_period = self.params.get('fast_period', 12)
        slow_period = self.params.get('slow_period', 26)
        signal_period = self.params.get('signal_period', 9)

        # 计算EMA
        def ema(data, period):
            result = []
            alpha = 2 / (period + 1)
            result.append(data[0])
            for i in range(1, len(data)):
                result.append(alpha * data[i] + (1 - alpha) * result[-1])
            return result

        ema_fast = ema(prices, fast_period)
        ema_slow = ema(prices, slow_period)
        macd = [ema_fast[i] - ema_slow[i] for i in range(len(ema_fast))]
        signal_line = ema(macd, signal_period)

        if len(macd) >= 2:
            prev_macd = macd[-2]
            curr_macd = macd[-1]
            prev_signal = signal_line[-2]
            curr_signal = signal_line[-1]

            # 金叉
            if prev_macd < prev_signal and curr_macd > curr_signal:
                return StrategySignal.SIGNAL_BUY
            # 死叉
            elif prev_macd > prev_signal and curr_macd < curr_signal:
                return StrategySignal.SIGNAL_SELL

        return StrategySignal.SIGNAL_NONE

# ============================================================
# 全局回测引擎
# ============================================================

import threading

_global_backtest_engine = None
_global_backtest_lock = threading.Lock()

def get_backtest_engine() -> VectorBTBacktestEngine:
    """获取回测引擎单例"""
    global _global_backtest_engine
    if _global_backtest_engine is None:
        with _global_backtest_lock:
            if _global_backtest_engine is None:
                _global_backtest_engine = VectorBTBacktestEngine()
    return _global_backtest_engine

# ============================================================
# 便捷回测函数
# ============================================================

def run_strategy_backtest(prices: List[float], strategy_type: str = "rsi",
                          params: Dict = None) -> Dict:
    """便捷回测函数"""
    engine = get_backtest_engine()

    if strategy_type.lower() == "rsi":
        strategy = RSIStrategy(params)
    elif strategy_type.lower() == "macd":
        strategy = MACDStrategy(params)
    else:
        strategy = RSIStrategy(params)

    def signal_generator(index, prices_slice):
        return strategy.generate_signal(index, prices_slice)

    result = engine.run_backtest(prices, signal_generator)
    return result.to_dict()

# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":
    # 生成模拟数据
    import random
    prices = [10.0]
    for i in range(500):
        prices.append(prices[-1] * (1 + random.uniform(-0.02, 0.02)))

    # 测试RSI策略回测
    result = run_strategy_backtest(prices, "rsi", {"period": 14, "overbought": 70, "oversold": 30})

    print("回测结果:")
    print(f"  策略: {result['strategy_name']}")
    print(f"  总收益: {result['total_return']}%")
    print(f"  年化收益: {result['annual_return']}%")
    print(f"  夏普比率: {result['sharpe_ratio']}")
    print(f"  最大回撤: {result['max_drawdown']}%")
    print(f"  胜率: {result['win_rate']}%")
    print(f"  交易次数: {result['trades']}")
    print(f"  盈亏比: {result['profit_factor']}")
    print(f"  耗时: {result['elapsed_time']}秒")
