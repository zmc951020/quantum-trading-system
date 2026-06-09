#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵·V6增强优化版 (Aurora StrategyBase 兼容版)
核心改进：使用V6增强优化器优化陀螺参数矩阵
保留原核心逻辑，添加优化因子，谨慎处理自适应止损

StrategyBase 兼容接口：
- update_price(current_price, data=None)  - 价格更新接口
- get_performance()                       - 性能指标接口
- run_backtest(data, initial_capital)     - 核心回测
- optimize_with_v6(data, iterations)      - 参数优化
"""

import sys
import os

aurora_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if aurora_root not in sys.path:
    sys.path.insert(0, aurora_root)

import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.linalg import eigvals
from collections import deque


# ==============================
# 本地简易评估器（避免依赖 experiments/archive/）
# ==============================
@dataclass
class MetricScore:
    name: str
    value: float
    score: float
    weight: float
    target: str
    status: str


class LocalEnhancedEvaluator:
    def __init__(self):
        self.weights = {
            'sharpe_ratio': 0.20, 'max_drawdown': 0.15, 'win_rate': 0.10,
            'profit_factor': 0.10, 'annual_return': 0.05,
        }
        self.targets = {
            'sharpe_ratio': '>=2.0', 'max_drawdown': '<=5%', 'win_rate': '>=50%',
            'profit_factor': '>=1.5', 'annual_return': '>=10%',
        }

    def _score_sharpe(self, s):
        if s >= 2.5: return 10.0
        elif s >= 2.0: return 9.0
        elif s >= 1.5: return 8.0
        elif s >= 1.0: return 7.0
        return max(0.0, s * 6)

    def _score_dd(self, d):
        if d <= 3: return 10.0
        elif d <= 5: return 9.0
        elif d <= 8: return 8.0
        elif d <= 10: return 7.0
        return max(0.0, 10 - (d - 10) * 0.3)

    def _score_wr(self, w):
        if w >= 70: return 10.0
        elif w >= 60: return 9.0
        elif w >= 50: return 8.0
        elif w >= 40: return 7.0
        return max(0.0, w * 0.14)

    def _score_pf(self, p):
        if p >= 3.0: return 10.0
        elif p >= 2.0: return 9.0
        elif p >= 1.5: return 8.0
        elif p >= 1.2: return 7.0
        return max(0.0, p * 5)

    def _score_annual(self, r):
        if r >= 50: return 10.0
        elif r >= 30: return 9.0
        elif r >= 20: return 8.0
        elif r >= 10: return 7.0
        return max(0.0, r * 0.5)

    def evaluate(self, result):
        sharpe = float(result.get('sharpe_ratio', 0))
        max_dd = abs(float(result.get('max_drawdown_pct', 0)))
        wr = float(result.get('win_rate_pct', 0))
        pf = float(result.get('profit_factor', 0))
        annual = float(result.get('total_return_pct', 0))
        scores = {
            'sharpe_ratio': self._score_sharpe(sharpe),
            'max_drawdown': self._score_dd(max_dd),
            'win_rate': self._score_wr(wr),
            'profit_factor': self._score_pf(pf),
            'annual_return': self._score_annual(annual),
        }
        details = {k: MetricScore(k, v, scores[k], self.weights.get(k, 0.1),
                                  self.targets.get(k, ''),
                                  'excellent' if scores[k] >= 9 else 'good' if scores[k] >= 7 else 'acceptable')
                   for k, v in {'sharpe_ratio': sharpe, 'max_drawdown': max_dd,
                                'win_rate': wr, 'profit_factor': pf, 'annual_return': annual}.items()}
        total = sum(scores[k] * self.weights.get(k, 0.1) for k in scores)
        return total, scores, details

    def get_grade(self, score):
        if score >= 9.5: return "S+ (卓越)"
        elif score >= 9.0: return "S (优秀)"
        elif score >= 8.0: return "A (良好)"
        elif score >= 7.0: return "B (合格)"
        elif score >= 6.0: return "C (一般)"
        return "D (不合格)"


# ==============================
# 参数配置
# ==============================
TARGET_SHARPE_MIN = 2.0
TARGET_SHARPE_MAX = 4.0
TARGET_K_RATIO = 3.0
TARGET_MAX_DD = 0.10
LYAPUNOV_THRESHOLD = -0.01
MAX_LEVERAGE = 3.0
SINGLE_ASSET_MAX = 0.3
DT = 1 / (252 * 24 * 60)
MINUTE_WINDOW_SHORT = 60
MINUTE_WINDOW_MEDIUM = 180
MINUTE_WINDOW_LONG = 720
MINUTE_WINDOW_VLONG = 1440

OPTIMIZATION_FACTORS = {
    'omega_scaling': 0.8, 'momentum_sensitivity': 1.2, 'volatility_weight': 0.7,
    'correlation_threshold': 0.3, 'stop_loss_multiplier': 1.5, 'take_profit_multiplier': 1.8,
}


@dataclass
class GyroState:
    S: np.ndarray
    Omega: np.ndarray
    omega: np.ndarray
    F: np.ndarray
    lyapunov: float
    energy_diff: float


@dataclass
class TradeAdjust:
    main_pos: float
    hedge_pos: float
    time_arb_pos: float


@dataclass
class StrategyMetrics:
    sharpe_ratio: float
    k_ratio: float
    max_dd: float
    cap_util: float
    sortino_ratio: float
    omega_ratio: float
    rolling_sharpe_stability: float
    information_ratio: float
    market_correlation: float
    tail_ratio: float
    trade_frequency: float
    max_consecutive_losses: int
    avg_holding_period: float
    recovery_time: float
    lyapunov: float = 0.0


# ==============================
# 指标计算工具
# ==============================
class GyroIndicator:
    @staticmethod
    def calc_momentum_minute(price_series, window=60):
        if len(price_series) < window: return 0
        recent = price_series[-window:]
        return np.mean(np.diff(recent)) / recent[-1]

    @staticmethod
    def calc_volatility_minute(price_series, window=60):
        if len(price_series) < window: return 0.01
        recent = price_series[-window:]
        return np.std(np.diff(recent)) * np.sqrt(60)

    @staticmethod
    def calc_atr_minute(high, low, close, window=60):
        if len(close) < window + 1: return 0.01
        tr1 = high[-window:] - low[-window:]
        tr2 = np.abs(high[-window:] - close[-window-1:-1])
        tr3 = np.abs(low[-window:] - close[-window-1:-1])
        return np.mean(np.maximum(tr1, np.maximum(tr2, tr3)))

    @staticmethod
    def calc_sortino(returns, target_return=0):
        if len(returns) == 0: return 0
        down = returns[returns < target_return]
        if len(down) == 0: return np.inf
        dev = np.sqrt(np.mean(down**2))
        if dev == 0: return np.inf
        return (np.mean(returns) - target_return) / dev

    @staticmethod
    def calc_omega(returns, threshold=0):
        if len(returns) == 0: return 1.0
        gains = returns[returns > threshold] - threshold
        losses = threshold - returns[returns <= threshold]
        if np.sum(losses) == 0: return np.inf
        return np.sum(gains) / np.sum(losses)

    @staticmethod
    def calc_tail_ratio(returns):
        if len(returns) < 10: return 1.0
        p5 = np.percentile(returns, 5)
        if p5 == 0: return 1.0
        return np.percentile(returns, 95) / np.abs(p5)

    @staticmethod
    def calc_rolling_sharpe_stability(returns, window=30):
        if len(returns) < window: return 1.0
        rs = pd.Series(returns).rolling(window).apply(
            lambda x: np.mean(x)/np.std(x)*np.sqrt(252*24*60) if np.std(x) > 0 else 0
        ).dropna()
        if len(rs) == 0: return 1.0
        m = np.mean(rs)
        if m == 0: return 1.0
        return np.std(rs) / m


# ==============================
# 陀螺动力学核心引擎
# ==============================
class GyroDynamics:
    def __init__(self, factors=None):
        self.dt = DT
        self.indicator = GyroIndicator()
        self.evaluator = LocalEnhancedEvaluator()
        self.factors = factors if factors is not None else OPTIMIZATION_FACTORS

    def build_skew_matrix(self, omega):
        w1, w2, w3 = omega * self.factors['omega_scaling']
        return np.array([[0, -w3, w2], [w3, 0, -w1], [-w2, w1, 0]], dtype=np.float32)

    def build_spin_matrix(self, momentum, vol, corr_mat, a=0.6, b=0.2, c=0.2):
        momentum = momentum * self.factors['momentum_sensitivity']
        vol = vol * self.factors['volatility_weight']
        M_mat = np.outer(np.ones(3)*momentum, np.ones(3))
        V_mat = np.eye(3) * vol
        O_mat = a * M_mat + b * V_mat + c * corr_mat
        if np.trace(O_mat) != 0:
            O_mat = O_mat / np.trace(O_mat) * 0.5
        return O_mat

    def calc_torque(self, state_curr, state_prev):
        return (state_curr - state_prev) / self.dt

    def calc_lyapunov(self, omega_series):
        if len(omega_series) < 2: return 0
        diff = np.diff(omega_series, axis=0)
        return np.mean(np.log(np.abs(diff + 1e-8)))

    def calc_energy_diff(self, omega_curr, omega_prev):
        return np.sum(np.square(omega_curr)) - np.sum(np.square(omega_prev))

    def gyro_response(self, F, omega, Omega):
        J = self.build_skew_matrix(omega)
        delta_P = J @ F * self.dt
        f_norm = np.linalg.norm(F)
        if f_norm > 3.0: delta_P = delta_P * 1.5
        elif f_norm < 0.3: delta_P = delta_P * 0.3
        return TradeAdjust(main_pos=delta_P[0], hedge_pos=delta_P[1], time_arb_pos=delta_P[2])

    def is_converged(self, metrics, Omega):
        eigen_real = np.real(eigvals(Omega))
        conditions = [
            TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX,
            metrics.k_ratio >= TARGET_K_RATIO,
            metrics.max_dd <= TARGET_MAX_DD,
            metrics.lyapunov <= LYAPUNOV_THRESHOLD,
            np.all(eigen_real <= 0.0),
            metrics.sortino_ratio >= 2.0,
            metrics.omega_ratio >= 1.5,
            metrics.rolling_sharpe_stability <= 0.5,
            metrics.max_consecutive_losses <= 3,
            metrics.tail_ratio >= 1.5,
        ]
        return all(conditions), conditions


# ==============================
# 稳健自适应止损
# ==============================
class RobustStopLoss:
    def __init__(self):
        self.base_stop = 0.015
        self.base_take = 0.03
        self.min_stop = 0.008
        self.max_stop = 0.03
        self.min_take = 0.015
        self.max_take = 0.06

    def calculate(self, atr, trend_strength, volatility):
        stop_loss = self.base_stop + atr * 1.5
        take_profit = self.base_take + atr * 2.0
        if trend_strength > 0.6:
            stop_loss = min(stop_loss * 1.3, self.max_stop)
            take_profit = min(take_profit * 1.2, self.max_take)
        elif trend_strength < 0.3:
            stop_loss = max(stop_loss * 0.8, self.min_stop)
            take_profit = max(take_profit * 0.9, self.min_take)
        if volatility > 0.015:
            stop_loss = min(stop_loss * 1.2, self.max_stop)
        return stop_loss, take_profit


# ==============================
# V6优化版策略主类（StrategyBase 兼容）
# ==============================
class GyroMinuteStrategyV6Optimized:
    """陀螺恒稳进动矩阵·V6增强优化版策略（Aurora StrategyBase 兼容）"""

    def __init__(self, base_price: float = 100.0, initial_balance: float = 100000.0):
        # StrategyBase 兼容字段
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.current_position = 0
        self.is_active = True
        self.last_price = base_price
        self.last_signal = "neutral"

        # 策略核心
        self.factors = OPTIMIZATION_FACTORS.copy()
        self.dynamics = GyroDynamics(factors=self.factors)
        self.stop_loss_manager = RobustStopLoss()

        self.state_prev = None
        self.omega_prev = np.array([0.3, 0.5, 0.7])
        self.trade_history = []
        self.metrics_history = []
        self.consecutive_losses = 0
        self.holding_periods = []
        self.entry_price = None
        self.current_stop_loss = None
        self.current_take_profit = None

        # 实时模式
        self._price_window = deque(maxlen=MINUTE_WINDOW_VLONG)
        self._tick_count = 0

    def calculate_all_metrics(self, returns):
        if len(returns) == 0:
            return StrategyMetrics(
                sharpe_ratio=0, k_ratio=0, max_dd=0, cap_util=0,
                sortino_ratio=0, omega_ratio=1.0, rolling_sharpe_stability=1.0,
                information_ratio=0, market_correlation=0.5, tail_ratio=1.0,
                trade_frequency=0, max_consecutive_losses=0, avg_holding_period=0,
                recovery_time=0, lyapunov=0
            )
        equity_curve = 1 + np.cumsum(returns)
        max_equity = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - max_equity) / max_equity
        max_dd = np.min(drawdown)
        returns_std = np.std(returns)
        sharpe = np.mean(returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
        k_ratio = (np.mean(returns) / returns_std) / np.abs(max_dd) if np.abs(max_dd) > 0 and returns_std > 0 else 0
        sortino = self.dynamics.indicator.calc_sortino(returns)
        omega = self.dynamics.indicator.calc_omega(returns)
        tail_ratio = self.dynamics.indicator.calc_tail_ratio(returns)
        rolling_stability = self.dynamics.indicator.calc_rolling_sharpe_stability(returns, window=60)
        avg_holding = np.mean(self.holding_periods) if self.holding_periods else 0
        return StrategyMetrics(
            sharpe_ratio=sharpe, k_ratio=k_ratio, max_dd=max_dd,
            cap_util=min(len(self.trade_history) * 0.02, 1.0),
            sortino_ratio=sortino, omega_ratio=omega,
            rolling_sharpe_stability=rolling_stability,
            information_ratio=0, market_correlation=0.5, tail_ratio=tail_ratio,
            trade_frequency=len(self.trade_history) / max(len(returns)/(252*24*60), 1),
            max_consecutive_losses=self.consecutive_losses,
            avg_holding_period=avg_holding, recovery_time=0.0, lyapunov=0.0
        )

    def should_trade(self, adjust, price_window):
        if np.abs(adjust.main_pos) < 0.001:
            return False
        if self.entry_price is not None:
            holding_time = len(price_window)
            if holding_time < 30:
                return False
        momentum = self.dynamics.indicator.calc_momentum_minute(price_window)
        if np.abs(momentum) < 0.0005:
            return False
        return True

    def run_backtest(self, data, initial_capital=100000):
        """核心回测"""
        prices = data['Close'].values
        high = data['High'].values
        low = data['Low'].values

        results = {
            'equity_curve': [], 'metrics': [], 'trades': [],
            'omega_history': [], 'final_score': 0.0, 'grade': 'D',
        }
        equity = initial_capital
        max_equity = initial_capital

        for i in range(MINUTE_WINDOW_LONG, len(prices)):
            price_window = prices[max(0, i-MINUTE_WINDOW_VLONG):i]
            short_window = prices[max(0, i-MINUTE_WINDOW_SHORT):i]
            if len(price_window) >= MINUTE_WINDOW_SHORT:
                p_slice = price_window[-MINUTE_WINDOW_SHORT:]
                ret = np.diff(p_slice) / p_slice[:-1]
            else:
                ret = np.array([0.0001, 0.0001, 0.0001])
            ret = np.resize(ret, 3)
            if len(price_window) >= MINUTE_WINDOW_MEDIUM:
                cov = np.cov(np.resize(price_window[-MINUTE_WINDOW_MEDIUM:], (3, int(MINUTE_WINDOW_MEDIUM/3))))
            else:
                cov = np.eye(3) * 0.0001
            mom = self.dynamics.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_MEDIUM)
            vol = self.dynamics.indicator.calc_volatility_minute(price_window, MINUTE_WINDOW_SHORT)
            atr = self.dynamics.indicator.calc_atr_minute(high, low, prices, MINUTE_WINDOW_SHORT)
            corr_mat = np.eye(3) * 0.3
            if len(price_window) >= 60:
                try:
                    corr_mat = np.corrcoef(np.resize(price_window[-60:], (3, 20)))
                except Exception:
                    pass
            Omega = self.dynamics.build_spin_matrix(mom, vol, corr_mat)
            state_curr = np.array([mom, vol, np.mean(corr_mat)])
            F = self.dynamics.calc_torque(state_curr, self.state_prev if self.state_prev is not None else state_curr)
            lyap = self.dynamics.calc_lyapunov(np.array([self.omega_prev]))
            adjust = self.dynamics.gyro_response(F, self.omega_prev, Omega)
            current_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
            metrics = self.calculate_all_metrics(current_returns)
            metrics.lyapunov = lyap
            self.metrics_history.append(metrics)

            if self.current_position != 0 and self.entry_price is not None:
                stop_price = self.entry_price * (1 - self.current_stop_loss * np.sign(self.current_position))
                take_price = self.entry_price * (1 + self.current_take_profit * np.sign(self.current_position))
                if self.current_position > 0:
                    if prices[i] <= stop_price:
                        ret_i = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret_i)
                        self.consecutive_losses += 1
                        self.trade_history.append({'return': ret_i, 'reason': 'stop_loss'})
                        self.current_position = 0
                        self.entry_price = None
                    elif prices[i] >= take_price:
                        ret_i = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret_i)
                        self.consecutive_losses = 0
                        self.trade_history.append({'return': ret_i, 'reason': 'take_profit'})
                        self.current_position = 0
                        self.entry_price = None
                else:
                    if prices[i] >= stop_price:
                        ret_i = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret_i)
                        self.consecutive_losses += 1
                        self.trade_history.append({'return': ret_i, 'reason': 'stop_loss'})
                        self.current_position = 0
                        self.entry_price = None
                    elif prices[i] <= take_price:
                        ret_i = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret_i)
                        self.consecutive_losses = 0
                        self.trade_history.append({'return': ret_i, 'reason': 'take_profit'})
                        self.current_position = 0
                        self.entry_price = None

            max_equity = max(max_equity, equity)
            if self.current_position == 0 and self.should_trade(adjust, short_window):
                trend_strength = min(abs(mom) * 100, 1.0)
                self.current_stop_loss, self.current_take_profit = self.stop_loss_manager.calculate(atr, trend_strength, vol)
                pos_size = np.sign(adjust.main_pos) * min(1.0, abs(adjust.main_pos) * 20) * (equity / prices[i])
                self.current_position = pos_size
                self.entry_price = prices[i]
            if self.current_position != 0 and i > 0:
                price_change = (prices[i] - prices[i-1]) / prices[i-1]
                equity *= (1 + price_change * np.sign(self.current_position))
            self.state_prev = state_curr
            results['equity_curve'].append(equity)
            results['metrics'].append(metrics)

        total_return = (equity - initial_capital) / initial_capital * 100
        max_dd = (max_equity - equity) / max_equity * 100
        all_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
        returns_std = np.std(all_returns)
        sharpe = np.mean(all_returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
        result_for_eval = {
            'returns': all_returns, 'days': len(data) / 1440,
            'total_return_pct': total_return, 'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd, 'total_trades': len(self.trade_history),
            'profit_factor': np.sum(all_returns[all_returns > 0]) / np.abs(np.sum(all_returns[all_returns < 0])) if np.sum(all_returns[all_returns < 0]) != 0 else 0,
            'win_rate_pct': len(all_returns[all_returns > 0]) / len(all_returns) * 100 if len(all_returns) > 0 else 0,
        }
        score, metric_scores, _ = self.dynamics.evaluator.evaluate(result_for_eval)
        results.update({
            'final_score': score, 'grade': self.dynamics.evaluator.get_grade(score),
            'total_return_pct': total_return, 'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd, 'total_trades': len(self.trade_history),
            'metric_scores': metric_scores,
        })
        self.current_balance = equity
        return results

    def optimize_with_v6(self, data, iterations=20):
        """参数优化：随机扰动+选择最优"""
        param_bounds = [(0.5, 1.5), (0.8, 1.8), (0.5, 1.2), (0.1, 0.5), (1.0, 2.0), (1.5, 2.5)]
        initial = np.array([self.factors[k] for k in ['omega_scaling', 'momentum_sensitivity', 'volatility_weight', 'correlation_threshold', 'stop_loss_multiplier', 'take_profit_multiplier']])
        best_score = -np.inf
        best_params = initial.copy()
        keys = ['omega_scaling', 'momentum_sensitivity', 'volatility_weight', 'correlation_threshold', 'stop_loss_multiplier', 'take_profit_multiplier']
        for i in range(iterations):
            trial = np.clip(initial + np.random.normal(0, 0.05, len(initial)),
                            [b[0] for b in param_bounds], [b[1] for b in param_bounds])
            self.factors = {k: v for k, v in zip(keys, trial)}
            self.dynamics = GyroDynamics(factors=self.factors)
            result = self.run_backtest(data)
            if result['final_score'] > best_score:
                best_score = result['final_score']
                best_params = trial.copy()
                initial = trial.copy()
        self.factors = {k: v for k, v in zip(keys, best_params)}
        self.dynamics = GyroDynamics(factors=self.factors)
        return best_score

    # ---------------- StrategyBase 接口 ----------------
    def update_price(self, current_price: float, data=None):
        """StrategyBase 接口：逐根K线更新"""
        if not self.is_active:
            return {"action": "hold", "balance": self.current_balance, "position": self.current_position, "signal": "neutral"}
        self.last_price = current_price
        self._price_window.append(current_price)
        self._tick_count += 1
        action, signal = "hold", "neutral"
        if len(self._price_window) >= MINUTE_WINDOW_SHORT:
            pa = np.array(self._price_window)
            mom = self.dynamics.indicator.calc_momentum_minute(pa, MINUTE_WINDOW_MEDIUM if len(pa) >= MINUTE_WINDOW_MEDIUM else MINUTE_WINDOW_SHORT)
            vol = self.dynamics.indicator.calc_volatility_minute(pa, MINUTE_WINDOW_SHORT)
            if mom > 0.0005 and vol > 0.001:
                signal = "buy"
                if self.current_position == 0:
                    action = "buy"
                    self.entry_price = current_price
                    self.current_stop_loss = 0.02
                    self.current_take_profit = 0.04
                    self.current_position = self.current_balance / current_price
            elif mom < -0.0005 and vol > 0.001:
                signal = "sell"
                if self.current_position != 0:
                    action = "sell"
                    ret = (current_price - (self.entry_price or current_price)) / (self.entry_price or current_price)
                    self.current_balance *= (1 + ret if self.current_position > 0 else (1 - ret))
                    self.trade_history.append({'return': ret, 'reason': 'realtime'})
                    self.current_position = 0
                    self.entry_price = None
        self.last_signal = signal
        return {"action": action, "balance": self.current_balance, "position": self.current_position, "signal": signal}

    def get_performance(self):
        """StrategyBase 接口：返回性能指标"""
        if self.metrics_history:
            latest = self.metrics_history[-1]
            total_trades = len(self.trade_history)
            winning = sum(1 for t in self.trade_history if t.get('return', 0) > 0)
            return {
                "total_trades": total_trades,
                "winning_trades": winning,
                "sharpe_ratio": getattr(latest, 'sharpe_ratio', 0.0),
                "annual_return": getattr(latest, 'k_ratio', 0.0),
                "max_drawdown": getattr(latest, 'max_dd', 0.0),
                "win_rate": (winning / total_trades) if total_trades > 0 else 0.0,
                "sortino_ratio": getattr(latest, 'sortino_ratio', 0.0),
                "omega_ratio": getattr(latest, 'omega_ratio', 1.0),
                "k_ratio": getattr(latest, 'k_ratio', 0.0),
                "tail_ratio": getattr(latest, 'tail_ratio', 1.0),
                "rolling_stability": getattr(latest, 'rolling_sharpe_stability', 1.0),
            }
        if self.trade_history:
            rs = np.array([t['return'] for t in self.trade_history])
            total = len(self.trade_history)
            winning = sum(1 for r in rs if r > 0)
            std = np.std(rs) if len(rs) > 1 else 0.0
            sharpe = np.mean(rs) / std * np.sqrt(252*24*60) if std > 0 else 0.0
            return {"total_trades": total, "winning_trades": winning,
                    "sharpe_ratio": sharpe, "annual_return": np.mean(rs) * 252 * 24 * 60,
                    "max_drawdown": 0.0, "win_rate": winning/total if total else 0.0}
        return {"total_trades": 0, "winning_trades": 0, "sharpe_ratio": 0.0,
                "annual_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0}

    def set_active(self, active: bool):
        self.is_active = active

    def get_balance(self) -> float:
        return self.current_balance

