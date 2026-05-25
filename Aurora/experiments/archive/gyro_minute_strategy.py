#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵·自适应演进交易策略（分钟级专业版）
核心逻辑：刚体进动动力学 + 李雅普诺夫稳态 + 分钟级高频交易优化
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
# 分钟级交易参数配置
# ==============================
TARGET_SHARPE_MIN = 2.0
TARGET_SHARPE_MAX = 4.0
TARGET_KRATIO = 3.0
TARGET_MAX_DD = 0.10
TARGET_CAP_UTIL = 0.90
LYAPUNOV_THRESHOLD = -0.01
OMEGA_EIGEN_THRESHOLD = 0.0

MAX_LEVERAGE = 3.0
SINGLE_ASSET_MAX = 0.3
DT = 1 / (252 * 24 * 60)  # 分钟级时间步

# 分钟级窗口配置
MINUTE_WINDOW_SHORT = 60     # 1小时
MINUTE_WINDOW_MEDIUM = 180   # 3小时
MINUTE_WINDOW_LONG = 720     # 12小时
MINUTE_WINDOW_VLONG = 1440   # 24小时

# ==============================
# 数据结构定义
# ==============================
@dataclass
class GyroState:
    S: np.ndarray          # 状态向量 [动量,波动,相关性]
    Omega: np.ndarray      # 3×3自旋矩阵
    omega: np.ndarray      # [ω1,ω2,ω3]三维进动速度
    F: np.ndarray          # 市场扰动力矩
    lyapunov: float        # 李雅普诺夫指数
    energy_diff: float     # 能量耗散率 dE/dt

@dataclass
class TradeAdjust:
    main_pos: float        # ω1主轴趋势头寸
    hedge_pos: float       # ω2跨资产对冲头寸
    time_arb_pos: float    # ω3时序套利头寸

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
# 分钟级指标计算工具
# ==============================
class GyroIndicator:
    @staticmethod
    def calc_momentum_minute(price_series, window=60):
        if len(price_series) < window:
            return 0
        recent = price_series[-window:]
        return np.mean(np.diff(recent)) / recent[-1]

    @staticmethod
    def calc_volatility_minute(price_series, window=60):
        if len(price_series) < window:
            return 0.01
        recent = price_series[-window:]
        return np.std(np.diff(recent)) * np.sqrt(60)

    @staticmethod
    def calc_atr_minute(high, low, close, window=60):
        if len(close) < window:
            return 0.01
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

# ==============================
# 陀螺动力学核心引擎（分钟级优化）
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

    def build_spin_matrix(self, momentum, vol, corr_mat, a=0.6, b=0.2, c=0.2):
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
        if f_norm > 3.0:
            delta_P = delta_P * 1.5
        elif f_norm < 0.3:
            delta_P = delta_P * 0.3

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
            metrics.sortino_ratio >= 2.0,
            metrics.omega_ratio >= 1.5,
            metrics.rolling_sharpe_stability <= 0.5,
            metrics.max_consecutive_losses <= 3,
            metrics.tail_ratio >= 1.5,
        ]
        return all(conditions), conditions

# ==============================
# SAC强化学习自动演进模块（分钟级优化）
# ==============================
class GyroEvolve:
    def __init__(self):
        self.omega = np.array([0.3, 0.5, 0.7])
        self.omega_history = deque(maxlen=500)
        self.reward_history = deque(maxlen=100)
        self.learning_rate = 5e-5
        self.gamma = 0.995

    def get_reward(self, metrics: StrategyMetrics, position_change):
        reward = 0.0

        if TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX:
            reward += metrics.sharpe_ratio * 15
        else:
            reward -= abs(metrics.sharpe_ratio - 3.0) * 8

        if metrics.k_ratio > TARGET_KRATIO:
            reward += metrics.k_ratio * 8

        reward -= metrics.max_dd * 30
        reward -= abs(metrics.lyapunov) * 40

        if metrics.sortino_ratio >= 2.0:
            reward += metrics.sortino_ratio * 5
        if metrics.omega_ratio >= 1.5:
            reward += metrics.omega_ratio * 3

        reward -= metrics.max_consecutive_losses * 5
        reward -= position_change * 2

        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())

        exploration_noise = np.random.normal(0, 0.02, 3)
        gradient = np.random.normal(0, self.learning_rate, 3)

        if self.reward_history and reward > np.mean(self.reward_history):
            gradient *= 1.3
        else:
            gradient *= -0.4

        new_omega = self.omega + gradient + exploration_noise
        self.omega = np.clip(new_omega, 0.1, 1.5)

        return self.omega

# ==============================
# 组合凸优化风控模块（分钟级优化）
# ==============================
class GyroPortfolioOpt:
    def __init__(self):
        self.max_lev = MAX_LEVERAGE
        self.max_single = SINGLE_ASSET_MAX

    def objective(self, w, ret, cov, dE, cvar, metrics):
        profit = -np.sum(w * ret) * 1.5
        risk = 0.5 * np.sqrt(w.T @ cov @ w)
        steady = 0.3 * dE
        tail_risk = 0.2 * cvar
        turnover_penalty = 0.1 * np.sum(np.abs(w))
        return profit + risk + steady + tail_risk + turnover_penalty

    def optimize(self, ret, cov, dE, cvar, metrics):
        n = len(ret)
        w0 = np.ones(n) / n
        bounds = [(-self.max_single, self.max_single) for _ in range(n)]
        cons = ({"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - self.max_lev})
        res = minimize(self.objective, w0, args=(ret, cov, dE, cvar, metrics), 
                      bounds=bounds, constraints=cons, method='SLSQP')
        return res.x if res.success else w0

# ==============================
# 分钟级完整策略主类
# ==============================
class GyroMinuteStrategy:
    def __init__(self):
        self.dynamics = GyroDynamics()
        self.evolver = GyroEvolve()
        self.opt = GyroPortfolioOpt()
        self.state_prev = None
        self.omega_prev = np.array([0.3, 0.5, 0.7])
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
            cap_util=min(len(self.trade_history) * 0.02, 1.0),
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

    def should_trade(self, adjust, price_window, min_holding_minutes=30):
        if np.abs(adjust.main_pos) < 0.001:
            return False
        
        if self.position_since is not None:
            holding_time = len(price_window)
            if holding_time < min_holding_minutes:
                return False
        
        momentum = self.dynamics.indicator.calc_momentum_minute(price_window)
        if np.abs(momentum) < 0.0005:
            return False
        
        volatility = self.dynamics.indicator.calc_volatility_minute(price_window)
        if volatility < 0.0001:
            return False
        
        return True

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
            'final_score': 0.0,
            'grade': 'D',
        }

        equity = initial_capital
        max_equity = initial_capital
        current_weights = np.array([0.5, 0.3, 0.2])
        position = 0
        last_position = 0

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
            cvar = self.dynamics.indicator.calc_cvar(ret, 0.95)
            
            mom = self.dynamics.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_MEDIUM)
            vol = self.dynamics.indicator.calc_volatility_minute(price_window, MINUTE_WINDOW_SHORT)
            
            corr_mat = np.eye(3) * 0.3
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

            if self.should_trade(adjust, short_window, min_holding_minutes=30):
                position = np.sum(weights) * (equity / prices[i])
                
                if i > 0 and last_position != 0:
                    daily_return = (prices[i] - prices[i-1]) / prices[i-1] * last_position / (equity / prices[i])
                    equity *= (1 + daily_return)
                    max_equity = max(max_equity, equity)
                    
                    if daily_return < 0:
                        self.consecutive_losses += 1
                        if self.position_since is not None:
                            self.holding_periods.append(i - self.position_since)
                            self.position_since = None
                    else:
                        self.consecutive_losses = 0
                    
                    self.trade_history.append({
                        'time': data.index[i],
                        'price': prices[i],
                        'position': position,
                        'return': daily_return,
                        'omega': new_omega.copy(),
                    })
                last_position = position
                if self.position_since is None:
                    self.position_since = i

            self.state_prev = state_curr
            self.omega_prev = new_omega.copy()

            results['equity_curve'].append(equity)
            results['weights'].append(weights)
            results['metrics'].append(metrics)
            results['omega_history'].append(new_omega.copy())

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
# 测试分钟级策略
# ==============================
if __name__ == "__main__":
    print("="*90)
    print("陀螺恒稳进动矩阵·分钟级自适应演进交易策略")
    print("="*90)
    
    np.random.seed(42)
    n_minutes = 5000
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='min')
    
    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    for i in range(1, n_minutes):
        hour_of_day = i % 1440 / 1440
        if hour_of_day < 0.25:
            dr = np.random.normal(0.0001, 0.001)
        elif hour_of_day < 0.5:
            dr = np.random.normal(0.0002, 0.0015)
        elif hour_of_day < 0.75:
            dr = np.random.normal(0.00015, 0.0012)
        else:
            dr = np.random.normal(0.00005, 0.0008)
        prices[i] = prices[i-1] * (1 + dr)
    
    test_data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0005),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0005)) * (1 + np.random.rand(n_minutes) * 0.001),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0005)) * (1 - np.random.rand(n_minutes) * 0.001),
        'Close': prices,
        'Volume': np.random.randint(10000, 100000, n_minutes)
    }, index=dates)
    
    print(f"\n测试数据: {n_minutes}分钟 ({n_minutes/1440:.1f}天)")
    
    strategy = GyroMinuteStrategy()
    result = strategy.run_backtest(test_data, 100000)
    
    print("\n" + "="*90)
    print("[回测结果] 分钟级回测结果")
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
    
    print("\n" + "="*90)
    print("分钟级策略测试完成！")
    print("="*90)