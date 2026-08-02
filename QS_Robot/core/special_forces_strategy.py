#!/usr/bin/env python3
"""
特种兵・威科夫量价自适应趋势震荡统一策略
==========================================
Special Forces Wyckoff Adaptive Strategy (自演进版)

策略架构：
  MultiTimeframePipeline → WyckoffFactorEngine → WyckoffPhaseDetector → SignalGenerator
       (数据管道)              (68维因子)            (阶段判定)            (信号输出)

核心特性：
  1. 威科夫三定律为底层逻辑
  2. 四级周期共振（周线→日线→60分钟→15分钟）
  3. 68维量价结构因子为特征输入
  4. 自演进参数优化（对接EntropyTauOptimizer）
  5. 按标的独立实例化，参数隔离

用法：
  strategy = SpecialForcesStrategy(symbol="510300")
  strategy.load_data()
  signals = strategy.generate_signals()
  backtest_result = strategy.run_backtest()
"""

import os
import sys
import time
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# 路径设置
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.multi_timeframe_pipeline import MultiTimeframePipeline, AlignedData
from core.wyckoff_factors import WyckoffFactorEngine, ALL_FACTOR_NAMES
from core.wyckoff_phase_detector import (
    WyckoffPhaseDetector, SignalGenerator,
    WyckoffPhase, SignalType, PhaseResult, TradeSignal
)


# ============================================================
# 策略参数配置
# ============================================================

@dataclass
class StrategyParams:
    """特种兵策略可优化参数"""
    # 信号阈值
    spring_threshold: float = 0.25
    sos_threshold: float = 0.20
    joc_threshold: float = 0.20
    lps_threshold: float = 0.20
    ut_threshold: float = 0.20
    sow_threshold: float = 0.20
    supply_exhausted_threshold: float = 0.35
    demand_exhausted_threshold: float = 0.35

    # 止损止盈
    stop_loss_atr_mult: float = 2.0
    take_profit_rr: float = 2.5
    trailing_stop_pct: float = 0.03

    # 仓位管理
    base_position_pct: float = 0.20
    max_position_pct: float = 0.35
    market_risk_cut: float = 0.60       # 市场风险超过此值减半仓
    market_risk_skip: float = 0.80      # 市场风险超过此值不开仓

    # 多周期共振
    mtf_confirm_required: bool = True
    mtf_min_confirm_count: int = 2

    # 信号过滤
    min_signal_confidence: float = 0.60
    min_bar_interval: int = 4           # 最小信号间隔（15分钟bar数）

    def to_dict(self) -> Dict[str, float]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> "StrategyParams":
        p = cls()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p


# ============================================================
# 回测结果
# ============================================================

@dataclass
class SFBacktestResult:
    """特种兵策略回测结果"""
    symbol: str
    total_return: float          # 总收益率（小数）
    annual_return: float         # 年化收益率（小数）
    sharpe_ratio: float          # 夏普比率
    max_drawdown: float          # 最大回撤（小数）
    win_rate: float              # 胜率（小数）
    profit_factor: float         # 盈亏比
    total_trades: int            # 总交易次数
    win_trades: int              # 盈利次数
    lose_trades: int             # 亏损次数
    avg_win: float               # 平均盈利（小数）
    avg_lose: float              # 平均亏损（小数）
    equity_curve: List[float] = field(default_factory=list)
    trade_log: List[Dict] = field(default_factory=list)
    signals: List[TradeSignal] = field(default_factory=list)
    phase_distribution: Dict[str, int] = field(default_factory=dict)
    elapsed_time: float = 0.0
    params: Dict[str, float] = field(default_factory=dict)

    def to_compatible_result(self):
        """转换为与现有BacktestResult兼容的格式"""
        from core.tau_optimizer_cluster import BacktestResult as TOCResult
        return TOCResult(
            strategy_name=f"special_forces_{self.symbol}",
            params=self.params,
            total_return=self.total_return,
            sharpe_ratio=self.sharpe_ratio,
            max_drawdown=self.max_drawdown,
            win_rate=self.win_rate,
            total_trades=self.total_trades,
            confidence=1.0,
        )


# ============================================================
# 特种兵策略主类
# ============================================================

class SpecialForcesStrategy:
    """
    特种兵・威科夫量价自适应策略

    每个标的独立实例化，参数隔离。
    自演进：通过参数优化接口，自动寻找最优参数。
    """

    name = "special_forces_wyckoff"
    label = "特种兵・威科夫量价自适应"
    category = "trend"
    description = "以威科夫三定律为底层逻辑，以四级周期共振为趋势骨架，以68维量价结构因子为特征输入，以强化学习+约束优化为自动寻优引擎"

    # 可优化参数范围（供优化器使用）
    PARAM_RANGES = {
        "spring_threshold": (0.10, 0.50),
        "sos_threshold": (0.10, 0.40),
        "joc_threshold": (0.10, 0.40),
        "lps_threshold": (0.10, 0.40),
        "ut_threshold": (0.10, 0.40),
        "sow_threshold": (0.10, 0.40),
        "supply_exhausted_threshold": (0.20, 0.60),
        "demand_exhausted_threshold": (0.20, 0.60),
        "stop_loss_atr_mult": (1.0, 4.0),
        "take_profit_rr": (1.5, 4.0),
        "trailing_stop_pct": (0.01, 0.08),
        "base_position_pct": (0.10, 0.40),
        "max_position_pct": (0.20, 0.50),
        "market_risk_cut": (0.40, 0.75),
        "market_risk_skip": (0.60, 0.90),
        "min_signal_confidence": (0.40, 0.80),
        "min_bar_interval": (2.0, 12.0),
    }

    def __init__(self, symbol: str = "510300",
                 params: StrategyParams = None,
                 force_refresh: bool = False):
        """
        Args:
            symbol: 股票代码
            params: 策略参数（不传则使用默认值）
            force_refresh: 是否强制刷新数据
        """
        self.symbol = symbol
        self.params = params or StrategyParams()
        self.force_refresh = force_refresh

        # 组件初始化
        self._pipeline = MultiTimeframePipeline()
        self._factor_engine = WyckoffFactorEngine()
        self._phase_detector = WyckoffPhaseDetector()
        self._signal_generator = SignalGenerator(
            stop_loss_atr_mult=self.params.stop_loss_atr_mult,
            take_profit_rr=self.params.take_profit_rr,
            base_position_pct=self.params.base_position_pct,
        )

        # 数据缓存
        self._aligned: Optional[AlignedData] = None
        self._factor_result: Optional[Dict] = None
        self._signals: List[TradeSignal] = []
        self._loaded = False

        # 实盘状态
        self._position: float = 0.0       # 当前持仓
        self._entry_price: float = 0.0    # 入场价
        self._highest_since_entry: float = 0.0  # 入场后最高价

    # --------------------------------------------------------
    # 数据加载
    # --------------------------------------------------------

    def load_data(self) -> bool:
        """加载多周期数据并计算因子"""
        print(f"[SpecialForces] 加载 {self.symbol} 数据...")
        t0 = time.time()

        self._aligned = self._pipeline.fetch_aligned(self.symbol, self.force_refresh)
        if self._aligned.count < 60:
            print(f"[SpecialForces] 数据不足: {self._aligned.count} bars")
            return False

        self._factor_result = self._factor_engine.compute_all(self._aligned)
        self._loaded = True

        print(f"[SpecialForces] {self.symbol} 数据加载完成 ({time.time()-t0:.1f}s)")
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    # --------------------------------------------------------
    # 信号生成
    # --------------------------------------------------------

    def generate_signals(self) -> List[TradeSignal]:
        """生成全部信号序列"""
        if not self._loaded:
            self.load_data()

        self._signals = []
        self._signal_generator.reset()

        matrix = self._factor_result["factor_matrix"]
        n = matrix.shape[0]

        # 计算ATR（用于止损）
        atr = self._calc_atr(self._aligned, 14)

        for i in range(n):
            # 获取多周期因子
            m15_factor = matrix[i]
            h60_factor = self._get_parent_factor(matrix, self._aligned.m15_to_h60, i)
            daily_factor = self._get_parent_factor(matrix, self._aligned.m15_to_daily, i)

            price = self._aligned.m15_closes[i] if i < len(self._aligned.m15_closes) else 0
            atr_val = atr[i] if i < len(atr) else None

            signal = self._signal_generator.generate(
                factor_vector=m15_factor,
                price=price,
                atr=atr_val,
                m15_factor=m15_factor,
                h60_factor=h60_factor,
                daily_factor=daily_factor,
            )

            # 信号过滤
            if self._should_filter_signal(signal, i):
                signal.signal_type = SignalType.NO_SIGNAL
                signal.confidence = 0.0

            self._signals.append(signal)

        # 统计
        buy_count = sum(1 for s in self._signals
                        if s.signal_type in (SignalType.BUY, SignalType.STRONG_BUY))
        sell_count = sum(1 for s in self._signals
                         if s.signal_type in (SignalType.SELL, SignalType.STRONG_SELL))
        print(f"[SpecialForces] {self.symbol} 信号生成完成: "
              f"买{buy_count} 卖{sell_count} / {n} bars")

        return self._signals

    def _should_filter_signal(self, signal: TradeSignal, bar_idx: int) -> bool:
        """信号过滤"""
        if signal.signal_type == SignalType.NO_SIGNAL:
            return False

        # 置信度过滤
        if signal.confidence < self.params.min_signal_confidence:
            return True

        # 最小间隔过滤
        if self.params.min_bar_interval > 0:
            for j in range(max(0, bar_idx - self.params.min_bar_interval), bar_idx):
                if j < len(self._signals) and self._signals[j].signal_type != SignalType.NO_SIGNAL:
                    return True

        return False

    def _get_parent_factor(self, matrix: np.ndarray,
                            mapping: List[int], m15_idx: int) -> Optional[np.ndarray]:
        """获取父周期因子向量"""
        if m15_idx < len(mapping):
            parent_idx = mapping[m15_idx]
            if parent_idx >= 0:
                # 日线因子：需要从矩阵中反查（因为矩阵是15分钟级别的）
                # 对于日线因子，取该日线对应的第一个15分钟bar的因子
                for i in range(m15_idx, -1, -1):
                    if i < len(mapping) and mapping[i] == parent_idx:
                        if i < matrix.shape[0]:
                            return matrix[i]
                # 如果没找到，使用当前bar的前一个日线的因子
                if parent_idx > 0:
                    for i in range(m15_idx, -1, -1):
                        if i < len(mapping) and mapping[i] == parent_idx - 1:
                            if i < matrix.shape[0]:
                                return matrix[i]
        return None

    def _calc_atr(self, aligned: AlignedData, window: int = 14) -> np.ndarray:
        """计算ATR"""
        highs = np.array(aligned.m15_highs)
        lows = np.array(aligned.m15_lows)
        closes = np.array(aligned.m15_closes)
        n = len(closes)

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
        tr[0] = highs[0] - lows[0]

        atr = np.zeros(n)
        atr[0] = tr[0]
        for i in range(1, n):
            atr[i] = (atr[i-1] * (window - 1) + tr[i]) / window

        return atr

    # --------------------------------------------------------
    # 回测
    # --------------------------------------------------------

    def run_backtest(self,
                     initial_capital: float = 100000.0,
                     commission: float = 0.00075,
                     slippage: float = 0.001) -> SFBacktestResult:
        """
        运行回测

        Args:
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点率

        Returns:
            SFBacktestResult: 回测结果
        """
        if not self._signals:
            self.generate_signals()

        t0 = time.time()

        capital = initial_capital
        position = 0.0           # 持仓数量
        entry_price = 0.0
        equity = [initial_capital]
        trades = []
        drawdowns = [0.0]
        peak_equity = initial_capital

        closes = self._aligned.m15_closes
        n = len(closes)

        for i in range(n):
            signal = self._signals[i] if i < len(self._signals) else None
            price = closes[i] if i < len(closes) else 0
            if price <= 0:
                continue

            # 处理买入信号
            if signal and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                if position <= 0:
                    # 计算买入数量
                    buy_amount = capital * signal.position_pct
                    exec_price = price * (1 + slippage)
                    position = buy_amount / exec_price
                    entry_price = exec_price
                    capital -= buy_amount * (1 + commission)
                    trades.append({
                        "type": "buy", "bar": i, "price": exec_price,
                        "amount": buy_amount, "position": position,
                        "confidence": signal.confidence,
                        "reason": signal.reason,
                    })

            # 处理卖出信号
            elif signal and signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                if position > 0:
                    exec_price = price * (1 - slippage)
                    sell_amount = position * exec_price * (1 - commission)
                    profit = sell_amount - position * entry_price
                    capital += sell_amount
                    trades.append({
                        "type": "sell", "bar": i, "price": exec_price,
                        "amount": sell_amount, "profit": profit,
                        "profit_pct": profit / (position * entry_price) if position > 0 and entry_price > 0 else 0,
                        "confidence": signal.confidence,
                        "reason": signal.reason,
                    })
                    position = 0.0
                    entry_price = 0.0

            # 移动止损
            if position > 0 and entry_price > 0:
                current_high = price
                self._highest_since_entry = max(self._highest_since_entry if hasattr(self, '_highest_since_entry') else current_high, current_high)
                trailing_stop = self._highest_since_entry * (1 - self.params.trailing_stop_pct)
                if price <= trailing_stop:
                    exec_price = trailing_stop * (1 - slippage)
                    sell_amount = position * exec_price * (1 - commission)
                    profit = sell_amount - position * entry_price
                    capital += sell_amount
                    trades.append({
                        "type": "sell_trailing", "bar": i, "price": exec_price,
                        "amount": sell_amount, "profit": profit,
                        "profit_pct": profit / (position * entry_price) if position > 0 and entry_price > 0 else 0,
                        "reason": "trailing_stop",
                    })
                    position = 0.0
                    entry_price = 0.0

            # 更新权益
            current_equity = capital + position * price
            equity.append(current_equity)
            peak_equity = max(peak_equity, current_equity)
            dd = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
            drawdowns.append(dd)

        # 强制平仓
        if position > 0 and n > 0:
            final_price = closes[-1]
            capital += position * final_price * (1 - commission - slippage)
            position = 0.0

        final_equity = capital
        total_return = (final_equity - initial_capital) / initial_capital

        # 计算回测指标（仅统计平仓交易：sell / sell_trailing）
        closed_trades = [t for t in trades if t.get("type", "").startswith("sell")]
        win_trades = [t for t in closed_trades if t.get("profit", 0) > 0]
        lose_trades = [t for t in closed_trades if t.get("profit", 0) <= 0]
        total_trades = len(closed_trades)

        win_rate = len(win_trades) / total_trades if total_trades > 0 else 0
        avg_win = np.mean([t["profit"] for t in win_trades]) if win_trades else 0
        avg_lose = abs(np.mean([t["profit"] for t in lose_trades])) if lose_trades else 0

        # 盈亏比
        total_wins = sum(t["profit"] for t in win_trades)
        total_losses = abs(sum(t["profit"] for t in lose_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else (999 if total_wins > 0 else 0)

        # 年化收益率
        bars_per_year = 16 * 252  # 15分钟bar，每年约252个交易日
        years = n / bars_per_year if n > 0 else 1
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        # 夏普比率
        equity_arr = np.array(equity)
        daily_returns = np.diff(equity_arr) / equity_arr[:-1]
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(bars_per_year) if np.std(daily_returns) > 0 else 0

        # 最大回撤
        max_dd = max(drawdowns) if drawdowns else 0

        # 阶段分布
        phase_dist = {}
        for s in self._signals:
            if s.signal_type != SignalType.NO_SIGNAL:
                # 从因子中获取阶段
                phase_labels = {0: "吸筹", 1: "拉升", 2: "派发", 3: "下跌"}
                # 简化：统计信号类型
                label = "BUY" if s.signal_type in (SignalType.BUY, SignalType.STRONG_BUY) else "SELL"
                phase_dist[label] = phase_dist.get(label, 0) + 1

        elapsed = time.time() - t0

        result = SFBacktestResult(
            symbol=self.symbol,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            win_trades=len(win_trades),
            lose_trades=len(lose_trades),
            avg_win=avg_win,
            avg_lose=avg_lose,
            equity_curve=equity,
            trade_log=trades,
            signals=self._signals,
            phase_distribution=phase_dist,
            elapsed_time=elapsed,
            params=self.params.to_dict(),
        )

        print(f"[SpecialForces] {self.symbol} 回测完成 ({elapsed:.1f}s): "
              f"收益={total_return:.2%} 夏普={sharpe:.2f} "
              f"回撤={max_dd:.2%} 胜率={win_rate:.1%} "
              f"交易={total_trades}次")

        return result

    # --------------------------------------------------------
    # 实时信号（实盘接口）
    # --------------------------------------------------------

    def get_live_signal(self, aligned: AlignedData = None) -> Optional[TradeSignal]:
        """
        获取最新实时信号（实盘使用）

        Args:
            aligned: 可选，实时更新的AlignedData

        Returns:
            TradeSignal: 最新信号，无信号时返回NO_SIGNAL
        """
        if aligned is not None:
            self._aligned = aligned
            self._factor_result = self._factor_engine.compute_all(self._aligned)

        if not self._loaded or self._aligned is None:
            return None

        matrix = self._factor_result["factor_matrix"]
        if matrix.shape[0] == 0:
            return None

        last_idx = matrix.shape[0] - 1
        price = self._aligned.m15_closes[last_idx]

        signal = self._signal_generator.generate(
            factor_vector=matrix[last_idx],
            price=price,
            atr=self._calc_atr(self._aligned)[last_idx],
            m15_factor=matrix[last_idx],
            h60_factor=self._get_parent_factor(matrix, self._aligned.m15_to_h60, last_idx),
            daily_factor=self._get_parent_factor(matrix, self._aligned.m15_to_daily, last_idx),
        )

        return signal

    # --------------------------------------------------------
    # 参数优化接口
    # --------------------------------------------------------

    def apply_params(self, params: Dict[str, float]):
        """应用优化参数"""
        for k, v in params.items():
            if hasattr(self.params, k):
                setattr(self.params, k, v)

        # 更新信号生成器
        self._signal_generator = SignalGenerator(
            stop_loss_atr_mult=self.params.stop_loss_atr_mult,
            take_profit_rr=self.params.take_profit_rr,
            base_position_pct=self.params.base_position_pct,
        )

        # 更新阶段判定器
        self._phase_detector = WyckoffPhaseDetector(thresholds={
            "acc_spring": self.params.spring_threshold,
            "mup_sos": self.params.sos_threshold,
            "mup_joc": self.params.joc_threshold,
            "mup_lps": self.params.lps_threshold,
            "dis_ut": self.params.ut_threshold,
            "mdn_sow": self.params.sow_threshold,
            "acc_supply_ex": self.params.supply_exhausted_threshold,
            "dis_demand_ex": self.params.demand_exhausted_threshold,
        })

        # 清除缓存，重新计算
        self._signals = []
        self._factor_result = None

    def get_param_ranges(self) -> Dict[str, Tuple[float, float]]:
        """获取参数范围（供优化器使用）"""
        return self.PARAM_RANGES.copy()

    def get_param_groups(self) -> Dict[str, List[str]]:
        """参数分组"""
        return {
            "signal_thresholds": [
                "spring_threshold", "sos_threshold", "joc_threshold",
                "lps_threshold", "ut_threshold", "sow_threshold",
                "supply_exhausted_threshold", "demand_exhausted_threshold",
            ],
            "risk_management": [
                "stop_loss_atr_mult", "take_profit_rr", "trailing_stop_pct",
            ],
            "position_sizing": [
                "base_position_pct", "max_position_pct",
                "market_risk_cut", "market_risk_skip",
            ],
            "signal_filter": [
                "min_signal_confidence", "min_bar_interval",
            ],
        }

    def estimate_quality(self, params: Dict[str, float]) -> float:
        """
        快速估算参数质量（用于优化器粗筛）

        返回: 0-1 的质量评分
        """
        score = 0.5

        # 止损不应太大
        sl = params.get("stop_loss_atr_mult", 2.0)
        if 1.5 <= sl <= 3.0:
            score += 0.1
        elif sl < 1.0 or sl > 4.0:
            score -= 0.1

        # 盈亏比应合理
        rr = params.get("take_profit_rr", 2.5)
        if 2.0 <= rr <= 3.5:
            score += 0.1

        # 仓位应合理
        bp = params.get("base_position_pct", 0.2)
        if 0.15 <= bp <= 0.30:
            score += 0.1

        # 信号阈值应在合理范围
        spring = params.get("spring_threshold", 0.25)
        if 0.15 <= spring <= 0.40:
            score += 0.1

        # 置信度阈值合理
        conf = params.get("min_signal_confidence", 0.60)
        if 0.50 <= conf <= 0.75:
            score += 0.1

        return max(0.0, min(1.0, score))


# ============================================================
# 策略工厂
# ============================================================

_strategy_instances: Dict[str, SpecialForcesStrategy] = {}


def get_special_forces_strategy(symbol: str = "510300",
                                 params: Dict[str, float] = None,
                                 force_refresh: bool = False) -> SpecialForcesStrategy:
    """
    获取特种兵策略实例（按标的缓存）

    Args:
        symbol: 股票代码
        params: 策略参数
        force_refresh: 是否强制刷新

    Returns:
        SpecialForcesStrategy: 策略实例
    """
    key = f"{symbol}_{hash(frozenset(params.items())) if params else 'default'}"
    if key not in _strategy_instances or force_refresh:
        p = StrategyParams.from_dict(params) if params else StrategyParams()
        _strategy_instances[key] = SpecialForcesStrategy(
            symbol=symbol, params=p, force_refresh=force_refresh
        )
    return _strategy_instances[key]