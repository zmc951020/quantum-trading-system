#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵·自适应演进交易策略（分钟级专业版V2）
缺陷优化：
1. 自适应止损（基于ATR动态）
2. 自适应信号阈值（基于波动率）
3. 优化强化学习奖励函数
4. 动态持仓管理
5. 多周期信号确认
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from scipy.linalg import eigvals
from scipy.optimize import minimize
from scipy.stats import norm
from collections import deque

from enhanced_evaluator import EnhancedFinancialEvaluator

# ==============================
# 分钟级交易参数配置（优化版）
# ==============================
TARGET_SHARPE_MIN = 1.5
TARGET_SHARPE_MAX = 5.0
TARGET_KRATIO = 2.0
TARGET_MAX_DD = 0.15
TARGET_CAP_UTIL = 0.85
LYAPUNOV_THRESHOLD = 0.01
OMEGA_EIGEN_THRESHOLD = 0.0

MAX_LEVERAGE = 4.0
SINGLE_ASSET_MAX = 0.35
DT = 1 / (252 * 24 * 60)

# 分钟级窗口配置（多周期）
MINUTE_WINDOW_SHORT = 30     # 30分钟
MINUTE_WINDOW_MEDIUM = 90   # 1.5小时
MINUTE_WINDOW_LONG = 180    # 3小时
MINUTE_WINDOW_VLONG = 720   # 12小时

# 自适应参数范围
MIN_SIGNAL_THRESHOLD = 0.00008
MAX_SIGNAL_THRESHOLD = 0.0006
MIN_HOLDING_MINUTES = 10
MAX_HOLDING_MINUTES = 45
MIN_STOP_LOSS = 0.003
MAX_STOP_LOSS = 0.025
MIN_TAKE_PROFIT = 0.006
MAX_TAKE_PROFIT = 0.05

# ==============================
# 数据结构定义
# ==============================
@dataclass
class GyroState:
    S: np.ndarray
    Omega: np.ndarray
    omega: np.ndarray
    F: np.ndarray
    lyapunov: float
    energy_diff: float
    atr: float
    trend_strength: float
    volatility_level: float

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

@dataclass
class AdaptiveParams:
    signal_threshold: float
    min_holding_minutes: int
    stop_loss: float
    take_profit: float

# ==============================
# 分钟级指标计算工具（优化版）
# ==============================
class GyroIndicator:
    @staticmethod
    def calc_momentum_minute(price_series, window=30):
        if len(price_series) < window:
            return 0
        recent = price_series[-window:]
        return np.mean(np.diff(recent)) / recent[-1]

    @staticmethod
    def calc_volatility_minute(price_series, window=30):
        if len(price_series) < window:
            return 0.01
        recent = price_series[-window:]
        return np.std(np.diff(recent)) * np.sqrt(60)

    @staticmethod
    def calc_atr_minute(high, low, close, window=30):
        if len(close) < window:
            return 0.005
        tr = np.maximum(high[-window:]-low[-window:], 
                        np.abs(high[-window:]-close[-window-1:-1]), 
                        np.abs(low[-window:]-close[-window-1:-1]))
        return np.mean(tr)

    @staticmethod
    def calc_cvar(returns, conf=0.95):
        if len(returns) == 0:
            return 0
        var = np.percentile(returns, (1-conf)*100)
        below_var = returns[returns <= var]
        return np.mean(below_var) if len(below_var) > 0 else var

    @staticmethod
    def calc_sortino(returns, target_return=0):
        if len(returns) == 0:
            return 0
        downside_returns = returns[returns < target_return]
        if len(downside_returns) == 0:
            return np.inf
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        if downside_deviation == 0:
            return np.inf
        return (np.mean(returns) - target_return) / downside_deviation

    @staticmethod
    def calc_omega(returns, threshold=0):
        if len(returns) == 0:
            return 1.0
        gains = returns[returns > threshold] - threshold
        losses = threshold - returns[returns <= threshold]
        if np.sum(losses) == 0:
            return np.inf
        return np.sum(gains) / np.sum(losses)

    @staticmethod
    def calc_tail_ratio(returns):
        if len(returns) < 10:
            return 1.0
        p5 = np.percentile(returns, 5)
        if p5 == 0:
            return 1.0
        return np.percentile(returns, 95) / np.abs(p5)

    @staticmethod
    def calc_rolling_sharpe_stability(returns, window=30):
        if len(returns) < window:
            return 1.0
        rolling_sharpe = pd.Series(returns).rolling(window).apply(
            lambda x: np.mean(x) / np.std(x) * np.sqrt(252*24*60) if np.std(x) > 0 else 0
        ).dropna()
        if len(rolling_sharpe) == 0:
            return 1.0
        mean_sharpe = np.mean(rolling_sharpe)
        if mean_sharpe == 0:
            return 1.0
        return np.std(rolling_sharpe) / mean_sharpe

    @staticmethod
    def calc_information_ratio(returns, benchmark_returns):
        if len(returns) == 0:
            return 0
        active_returns = returns - benchmark_returns
        tracking_error = np.std(active_returns)
        if tracking_error == 0:
            return np.inf
        return np.mean(active_returns) / tracking_error * np.sqrt(252*24*60)

    @staticmethod
    def calc_trend_strength(price_series, window=30):
        if len(price_series) < window:
            return 0.3
        x = np.arange(window)
        y = price_series[-window:]
        slope, _ = np.polyfit(x, y, 1)
        return min(max(abs(slope) * 100, 0.1), 1.0)

# ==============================
# 自适应参数管理器
# ==============================
class AdaptiveParamManager:
    def __init__(self):
        self.indicator = GyroIndicator()
        self.volatility_history = deque(maxlen=100)
        self.atr_history = deque(maxlen=100)

    def calculate_adaptive_params(self, price_window, high, low, close, current_idx):
        atr = self.indicator.calc_atr_minute(high, low, close)
        vol = self.indicator.calc_volatility_minute(price_window)
        trend_strength = self.indicator.calc_trend_strength(price_window)

        self.volatility_history.append(vol)
        self.atr_history.append(atr)

        avg_vol = np.mean(self.volatility_history) if self.volatility_history else vol

        signal_threshold = MIN_SIGNAL_THRESHOLD + (MAX_SIGNAL_THRESHOLD - MIN_SIGNAL_THRESHOLD) * (vol / avg_vol if avg_vol > 0 else 0.5)
        signal_threshold = np.clip(signal_threshold, MIN_SIGNAL_THRESHOLD, MAX_SIGNAL_THRESHOLD)

        if trend_strength > 0.7:
            min_holding = MAX_HOLDING_MINUTES
        elif trend_strength > 0.4:
            min_holding = (MIN_HOLDING_MINUTES + MAX_HOLDING_MINUTES) // 2
        else:
            min_holding = MIN_HOLDING_MINUTES

        stop_loss = np.clip(atr * 1.5, MIN_STOP_LOSS, MAX_STOP_LOSS)
        take_profit = np.clip(stop_loss * 2.5, MIN_TAKE_PROFIT, MAX_TAKE_PROFIT)

        return AdaptiveParams(
            signal_threshold=signal_threshold,
            min_holding_minutes=min_holding,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def get_multicycle_confirmation(self, price_window):
        if len(price_window) < MINUTE_WINDOW_LONG:
            return True

        mom_short = self.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_SHORT)
        mom_medium = self.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_MEDIUM)
        mom_long = self.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_LONG)

        short_positive = mom_short > 0.0001
        medium_positive = mom_medium > 0
        long_positive = mom_long > 0

        agreement = (short_positive == medium_positive) and (medium_positive == long_positive)
        return agreement

# ==============================
# 陀螺动力学核心引擎（优化版）
# ==============================
class GyroDynamics:
    def __init__(self):
        self.dt = DT
        self.indicator = GyroIndicator()
        self.evaluator = EnhancedFinancialEvaluator()

    def build_skew_matrix(self, omega):
        w1, w2, w3 = omega
        J = np.array([
            [0, -w3, w2],
            [w3, 0, -w1],
            [-w2, w1, 0]
        ], dtype=np.float32)
        return J

    def build_spin_matrix(self, momentum, vol, corr_mat, a=0.5, b=0.3, c=0.2):
        M_mat = np.outer(np.ones(3)*momentum, np.ones(3))
        V_mat = np.eye(3) * vol
        O_mat = a * M_mat + b * V_mat + c * corr_mat
        if np.trace(O_mat) != 0:
            O_mat = O_mat / np.trace(O_mat) * 0.5
        return O_mat

    def calc_torque(self, state_curr, state_prev):
        return (state_curr - state_prev) / self.dt

    def calc_lyapunov(self, omega_series):
        if len(omega_series) < 2:
            return 0
        diff = np.diff(omega_series, axis=0)
        return np.mean(np.log(np.abs(diff + 1e-8)))

    def calc_energy_diff(self, omega_curr, omega_prev):
        return np.sum(np.square(omega_curr)) - np.sum(np.square(omega_prev))

    def gyro_response(self, F, omega, Omega):
        J = self.build_skew_matrix(omega)
        delta_P = J @ F * self.dt

        f_norm = np.linalg.norm(F)
        if f_norm > 2.5:
            delta_P = delta_P * 1.3
        elif f_norm < 0.4:
            delta_P = delta_P * 0.4

        return TradeAdjust(
            main_pos=delta_P[0],
            hedge_pos=delta_P[1],
            time_arb_pos=delta_P[2]
        )

    def is_converged(self, metrics: StrategyMetrics, Omega):
        eigen_vals = eigvals(Omega)
        eigen_real = np.real(eigen_vals)

        conditions = [
            TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX,
            metrics.k_ratio >= TARGET_KRATIO,
            metrics.max_dd <= TARGET_MAX_DD,
            metrics.cap_util >= TARGET_CAP_UTIL,
            metrics.lyapunov <= LYAPUNOV_THRESHOLD,
            np.all(eigen_real <= OMEGA_EIGEN_THRESHOLD),
            metrics.sortino_ratio >= 1.5,
            metrics.omega_ratio >= 1.3,
            metrics.rolling_sharpe_stability <= 0.7,
            metrics.max_consecutive_losses <= 5,
            metrics.tail_ratio >= 1.2,
        ]
        return all(conditions), conditions

# ==============================
# SAC强化学习自动演进模块（优化版）
# ==============================
class GyroEvolve:
    def __init__(self):
        self.omega = np.array([0.65, 0.25, 0.10])
        self.omega_history = deque(maxlen=500)
        self.reward_history = deque(maxlen=150)
        self.learning_rate = 2e-4
        self.gamma = 0.985

    def get_reward(self, metrics: StrategyMetrics, position_change):
        reward = 0.0

        if metrics.sharpe_ratio >= 1.5:
            reward += metrics.sharpe_ratio * 12
        else:
            reward -= abs(metrics.sharpe_ratio - 1.5) * 3

        if metrics.k_ratio > TARGET_KRATIO:
            reward += metrics.k_ratio * 6

        reward -= metrics.max_dd * 25
        reward -= abs(metrics.lyapunov) * 25

        if metrics.sortino_ratio >= 1.5:
            reward += metrics.sortino_ratio * 8
        if metrics.omega_ratio >= 1.3:
            reward += metrics.omega_ratio * 4

        reward -= metrics.max_consecutive_losses * 4
        reward -= position_change * 1.5

        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())

        exploration_noise = np.random.normal(0, 0.03, 3)
        gradient = np.random.normal(0, self.learning_rate, 3)

        if self.reward_history:
            avg_reward = np.mean(self.reward_history)
            if reward > avg_reward:
                gradient *= 1.4
            elif reward < avg_reward - np.std(self.reward_history):
                gradient *= -0.5

        new_omega = self.omega + gradient + exploration_noise
        self.omega = np.clip(new_omega, 0.05, 2.0)

        return self.omega

# ==============================
# 组合凸优化风控模块（优化版）
# ==============================
class GyroPortfolioOpt:
    def __init__(self):
        self.max_lev = MAX_LEVERAGE
        self.max_single = SINGLE_ASSET_MAX

    def objective(self, w, ret, cov, dE, cvar, metrics):
        profit = -np.sum(w * ret) * 1.3
        risk = 0.4 * np.sqrt(w.T @ cov @ w)
        steady = 0.25 * dE
        tail_risk = 0.15 * cvar
        turnover_penalty = 0.15 * np.sum(np.abs(w))
        return profit + risk + steady + tail_risk + turnover_penalty

    def optimize(self, ret, cov, dE, cvar, metrics):
        n = len(ret)
        w0 = np.array([0.5, 0.35, 0.15])
        bounds = [(-self.max_single, self.max_single) for _ in range(n)]
        cons = ({"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - self.max_lev})
        res = minimize(self.objective, w0, args=(ret, cov, dE, cvar, metrics),
                      bounds=bounds, constraints=cons, method='SLSQP')
        return res.x if res.success else w0

# ==============================
# 分钟级完整策略主类（优化版V2）
# ==============================
class GyroMinuteStrategyV2:
    def __init__(self):
        self.dynamics = GyroDynamics()
        self.evolver = GyroEvolve()
        self.opt = GyroPortfolioOpt()
        self.param_manager = AdaptiveParamManager()

        self.state_prev = None
        self.omega_prev = np.array([0.65, 0.25, 0.10])
        self.trade_history = []
        self.metrics_history = []
        self.equity_curve = [1.0]
        self.current_equity = 1.0
        self.max_equity = 1.0
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.holding_periods = []
        self.current_position = 0
        self.position_since = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.adaptive_params = None

    def calculate_all_metrics(self, returns, benchmark_returns=None):
        if benchmark_returns is None:
            benchmark_returns = np.zeros_like(returns)

        if len(returns) == 0:
            return StrategyMetrics(
                sharpe_ratio=0, k_ratio=0, max_dd=0, cap_util=0,
                sortino_ratio=0, omega_ratio=1.0, rolling_sharpe_stability=1.0,
                information_ratio=0, market_correlation=0.5, tail_ratio=1.0,
                trade_frequency=0, max_consecutive_losses=0, avg_holding_period=0,
                recovery_time=0, lyapunov=0
            )

        equity = 1 + np.cumsum(returns)
        max_equity = np.maximum.accumulate(equity)
        drawdown = (equity - max_equity) / max_equity
        max_dd = np.min(drawdown)

        returns_std = np.std(returns)
        sharpe = np.mean(returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
        k_ratio = (np.mean(returns) / returns_std) / np.abs(max_dd) if np.abs(max_dd) > 0 and returns_std > 0 else 0

        sortino = self.dynamics.indicator.calc_sortino(returns)
        omega = self.dynamics.indicator.calc_omega(returns)
        tail_ratio = self.dynamics.indicator.calc_tail_ratio(returns)
        rolling_stability = self.dynamics.indicator.calc_rolling_sharpe_stability(returns, window=60)
        info_ratio = self.dynamics.indicator.calc_information_ratio(returns, benchmark_returns)

        avg_holding = np.mean(self.holding_periods) if self.holding_periods else 0

        return StrategyMetrics(
            sharpe_ratio=sharpe,
            k_ratio=k_ratio,
            max_dd=max_dd,
            cap_util=min(len(self.trade_history) * 0.015, 1.0),
            sortino_ratio=sortino,
            omega_ratio=omega,
            rolling_sharpe_stability=rolling_stability,
            information_ratio=info_ratio,
            market_correlation=0.5,
            tail_ratio=tail_ratio,
            trade_frequency=len(self.trade_history) / max(len(returns)/(252*24*60), 1),
            max_consecutive_losses=self.consecutive_losses,
            avg_holding_period=avg_holding,
            recovery_time=0.0,
            lyapunov=0.0
        )

    def should_trade(self, adjust, price_window, high, low, close, current_idx):
        if self.adaptive_params is None:
            self.adaptive_params = self.param_manager.calculate_adaptive_params(price_window, high, low, close, current_idx)

        total_signal = adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos
        if np.abs(total_signal) < 0.0003:
            return False

        if self.position_since is not None:
            holding_time = current_idx - self.position_since
            if holding_time < self.adaptive_params.min_holding_minutes:
                return False

        momentum = self.dynamics.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_SHORT)
        if np.abs(momentum) < self.adaptive_params.signal_threshold:
            return False

        volatility = self.dynamics.indicator.calc_volatility_minute(price_window, MINUTE_WINDOW_SHORT)
        if volatility < 0.00005:
            return False

        return True

    def check_stop_loss_take_profit(self, current_price, equity):
        if self.position_since is None or self.entry_price is None or self.current_position == 0:
            return None, equity

        if self.stop_loss_level is not None:
            if self.current_position > 0 and current_price <= self.stop_loss_level:
                return 'stop_loss', equity
            if self.current_position < 0 and current_price >= self.stop_loss_level:
                return 'stop_loss', equity

        if self.take_profit_level is not None:
            if self.current_position > 0 and current_price >= self.take_profit_level:
                return 'take_profit', equity
            if self.current_position < 0 and current_price <= self.take_profit_level:
                return 'take_profit', equity

        return None, equity

    def close_position(self, current_price, equity, reason, current_idx):
        if self.current_position == 0 or self.entry_price is None or self.entry_price == 0:
            return equity, 0

        position_sign = np.sign(self.current_position)
        ret = (current_price - self.entry_price) / self.entry_price * position_sign
        equity *= (1 + ret)

        if ret < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self.position_since is not None:
            self.holding_periods.append(current_idx - self.position_since)

        self.trade_history.append({
            'time': current_idx,
            'price': current_price,
            'position': 0,
            'return': ret,
            'reason': reason,
            'omega': self.evolver.omega.copy(),
        })

        old_position = self.current_position
        self.current_position = 0
        self.position_since = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None

        return equity, old_position

    def run_backtest(self, data, initial_capital=100000):
        prices = data['Close'].values
        high = data['High'].values
        low = data['Low'].values

        results = {
            'equity_curve': [],
            'weights': [],
            'metrics': [],
            'trades': [],
            'omega_history': [],
            'adaptive_params_history': [],
            'final_score': 0.0,
            'grade': 'D',
        }

        equity = initial_capital
        max_equity = initial_capital
        current_weights = np.array([0.5, 0.35, 0.15])
        last_position = 0

        for i in range(MINUTE_WINDOW_VLONG, len(prices)):
            price_window = prices[max(0, i-MINUTE_WINDOW_VLONG):i]
            short_window = prices[max(0, i-MINUTE_WINDOW_SHORT):i]
            high_window = high[max(0, i-MINUTE_WINDOW_VLONG):i]
            low_window = low[max(0, i-MINUTE_WINDOW_VLONG):i]
            close_window = prices[max(0, i-MINUTE_WINDOW_VLONG):i]

            self.adaptive_params = self.param_manager.calculate_adaptive_params(price_window, high_window, low_window, close_window, i)

            close_reason, equity = self.check_stop_loss_take_profit(prices[i], equity)
            if close_reason is not None:
                equity, old_pos = self.close_position(prices[i], equity, close_reason, i)
                last_position = 0
                max_equity = max(max_equity, equity)

            if len(price_window) >= MINUTE_WINDOW_SHORT:
                p_slice = price_window[-MINUTE_WINDOW_SHORT:]
                ret = np.diff(p_slice) / p_slice[:-1]
            else:
                ret = np.array([0.0001, 0.0001, 0.0001])
            ret = np.resize(ret, 3)

            if len(price_window) >= MINUTE_WINDOW_MEDIUM:
                try:
                    cov = np.cov(np.resize(price_window[-MINUTE_WINDOW_MEDIUM:], (3, int(MINUTE_WINDOW_MEDIUM/3))))
                except:
                    cov = np.eye(3) * 0.0001
            else:
                cov = np.eye(3) * 0.0001
            cvar = self.dynamics.indicator.calc_cvar(ret, 0.95)

            mom = self.dynamics.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_MEDIUM)
            vol = self.dynamics.indicator.calc_volatility_minute(price_window, MINUTE_WINDOW_SHORT)
            atr = self.dynamics.indicator.calc_atr_minute(high_window, low_window, close_window, MINUTE_WINDOW_SHORT)
            trend_strength = self.dynamics.indicator.calc_trend_strength(price_window, MINUTE_WINDOW_SHORT)

            corr_mat = np.eye(3) * 0.25
            if len(price_window) >= 60:
                try:
                    corr_mat = np.corrcoef(np.resize(price_window[-60:], (3, 20)))
                except:
                    pass

            Omega = self.dynamics.build_spin_matrix(mom, vol, corr_mat)
            state_curr = np.array([mom, vol, np.mean(corr_mat)])
            F = self.dynamics.calc_torque(state_curr, self.state_prev if self.state_prev is not None else state_curr)

            lyap = self.dynamics.calc_lyapunov(np.array([self.evolver.omega]))
            dE = self.dynamics.calc_energy_diff(self.evolver.omega, self.omega_prev)
            adjust = self.dynamics.gyro_response(F, self.evolver.omega, Omega)

            current_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
            metrics = self.calculate_all_metrics(current_returns)
            metrics.lyapunov = lyap
            self.metrics_history.append(metrics)

            converged, conditions = self.dynamics.is_converged(metrics, Omega)

            position_change = np.abs(adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos)

            if not converged:
                reward = self.evolver.get_reward(metrics, position_change)
                new_omega = self.evolver.evolve_omega(state_curr, reward)
            else:
                new_omega = self.evolver.omega

            weights = self.opt.optimize(ret, cov, dE, cvar, metrics)

            if self.should_trade(adjust, price_window, high_window, low_window, close_window, i):
                if self.current_position != 0:
                    equity, old_pos = self.close_position(prices[i], equity, 'normal_close', i)
                    last_position = 0
                    max_equity = max(max_equity, equity)

                signal_strength = np.abs(adjust.main_pos) + 0.5 * np.abs(adjust.hedge_pos) + 0.3 * np.abs(adjust.time_arb_pos)
                position_size = np.sign(adjust.main_pos) * min(1.5, signal_strength * 20) * (equity / prices[i])
                self.current_position = position_size
                self.entry_price = prices[i]
                self.position_since = i

                sl_multiplier = np.sign(position_size) if position_size != 0 else 1
                self.stop_loss_level = prices[i] - (self.adaptive_params.stop_loss * sl_multiplier * prices[i])
                self.take_profit_level = prices[i] + (self.adaptive_params.take_profit * sl_multiplier * prices[i])

                last_position = position_size

            if i > 0 and self.current_position != 0 and self.entry_price is not None and self.position_since is not None and self.position_since < i:
                price_change = (prices[i] - prices[i-1]) / prices[i-1]
                equity += equity * price_change * np.sign(self.current_position)
                max_equity = max(max_equity, equity)

            self.state_prev = state_curr
            self.omega_prev = new_omega.copy()

            results['equity_curve'].append(equity)
            results['weights'].append(weights)
            results['metrics'].append(metrics)
            results['omega_history'].append(new_omega.copy())
            results['adaptive_params_history'].append(self.adaptive_params)

        total_return = (equity - initial_capital) / initial_capital * 100
        max_dd = (max_equity - equity) / max_equity * 100

        all_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
        returns_std = np.std(all_returns)
        sharpe = np.mean(all_returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0

        final_metrics = self.calculate_all_metrics(all_returns)
        final_metrics.max_dd = max_dd / 100
        final_metrics.sharpe_ratio = sharpe

        result_for_eval = {
            'returns': all_returns,
            'days': len(data) / 1440,
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'total_trades': len(self.trade_history),
            'profit_factor': np.sum(all_returns[all_returns > 0]) / np.abs(np.sum(all_returns[all_returns < 0])) if np.sum(all_returns[all_returns < 0]) != 0 else 0,
            'win_rate_pct': len(all_returns[all_returns > 0]) / len(all_returns) * 100 if len(all_returns) > 0 else 0,
        }

        score, metric_scores, details = self.dynamics.evaluator.evaluate(result_for_eval)

        results.update({
            'final_score': score,
            'grade': self.dynamics.evaluator.get_grade(score),
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'total_trades': len(self.trade_history),
            'metric_scores': metric_scores,
        })

        return results

# ==============================
# 测试分钟级策略V2
# ==============================
if __name__ == "__main__":
    print("="*90)
    print("陀螺恒稳进动矩阵·分钟级自适应演进交易策略V2")
    print("缺陷优化：自适应止损、自适应信号阈值、优化强化学习、动态持仓")
    print("="*90)

    np.random.seed(42)
    n_minutes = 6000
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='min')

    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    for i in range(1, n_minutes):
        hour_of_day = i % 1440 / 1440
        if hour_of_day < 0.25:
            dr = np.random.normal(0.00012, 0.0009)
        elif hour_of_day < 0.5:
            dr = np.random.normal(0.00022, 0.0014)
        elif hour_of_day < 0.75:
            dr = np.random.normal(0.00018, 0.0011)
        else:
            dr = np.random.normal(0.00006, 0.0007)
        prices[i] = prices[i-1] * (1 + dr)

    test_data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0004),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 + np.random.rand(n_minutes) * 0.0008),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 - np.random.rand(n_minutes) * 0.0008),
        'Close': prices,
        'Volume': np.random.randint(12000, 90000, n_minutes)
    }, index=dates)

    print(f"\n测试数据: {n_minutes}分钟 ({n_minutes/1440:.1f}天)")

    strategy = GyroMinuteStrategyV2()
    result = strategy.run_backtest(test_data, 100000)

    print("\n" + "="*90)
    print("[回测结果] 分钟级策略V2回测结果")
    print("="*90)
    print(f"综合评分: {result['final_score']:.2f} ({result['grade']})")
    print(f"总收益率: {result['total_return_pct']:.2f}%")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
    print(f"交易次数: {result['total_trades']}")
    print(f"平均持仓时长: {np.mean(strategy.holding_periods):.0f}分钟" if strategy.holding_periods else "平均持仓时长: N/A")

    print("\n[指标得分] 各指标得分:")
    for k, v in sorted(result['metric_scores'].items(), key=lambda x: x[1], reverse=True):
        status = "[OK]" if v >= 8 else "[WARN]" if v >= 6 else "[FAIL]"
        print(f"{status} {k:<25}: {v:.1f}")

    if result['adaptive_params_history']:
        last_params = result['adaptive_params_history'][-1]
        print("\n[自适应参数] 最终自适应参数:")
        print(f"  信号阈值: {last_params.signal_threshold:.6f}")
        print(f"  最小持仓: {last_params.min_holding_minutes}分钟")
        print(f"  止损: {last_params.stop_loss:.4f}")
        print(f"  止盈: {last_params.take_profit:.4f}")

    print("\n" + "="*90)
    print("分钟级策略V2测试完成！")
    print("="*90)
