#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺策略V3 - 缺陷优化版本
基于V1但添加了自适应止损、自适应信号、优化强化学习等功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.linalg import eigvals
from scipy.optimize import minimize
from collections import deque

from enhanced_evaluator import EnhancedFinancialEvaluator

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
            return 0.008
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

class AdaptiveParamManager:
    def __init__(self):
        self.vol_history = deque(maxlen=100)
    
    def get_params(self, prices):
        vol = GyroIndicator.calc_volatility_minute(prices, 30)
        self.vol_history.append(vol)
        avg_vol = np.mean(self.vol_history) if self.vol_history else vol
        
        signal_threshold = max(0.0001, min(0.0004, 0.0002 + (vol - avg_vol) * 0.1))
        min_holding = max(20, min(80, 40 + int((avg_vol - vol) * 500)))
        stop_loss = max(0.005, min(0.02, 0.008 + vol * 0.3))
        take_profit = max(0.01, min(0.04, 0.015 + vol * 0.6))
        
        return signal_threshold, min_holding, stop_loss, take_profit

class GyroDynamics:
    def __init__(self):
        self.dt = 1 / (252 * 24 * 60)
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
            delta_P = delta_P * 1.2
        elif f_norm < 0.4:
            delta_P = delta_P * 0.5

        return TradeAdjust(
            main_pos=delta_P[0],
            hedge_pos=delta_P[1],
            time_arb_pos=delta_P[2]
        )

class GyroEvolve:
    def __init__(self):
        self.omega = np.array([0.55, 0.30, 0.15])
        self.omega_history = deque(maxlen=500)
        self.reward_history = deque(maxlen=150)
        self.learning_rate = 1.5e-4
        self.gamma = 0.99

    def get_reward(self, metrics, position_change):
        reward = 0.0

        if metrics.sharpe_ratio >= 1.2:
            reward += metrics.sharpe_ratio * 12
        else:
            reward -= abs(metrics.sharpe_ratio - 1.2) * 2

        if metrics.sortino_ratio >= 1.5:
            reward += metrics.sortino_ratio * 8
        
        reward -= metrics.max_dd * 25
        reward -= abs(metrics.lyapunov) * 20

        reward -= metrics.max_consecutive_losses * 4
        reward -= position_change * 1.5

        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())

        exploration_noise = np.random.normal(0, 0.025, 3)
        
        if self.reward_history:
            avg_reward = np.mean(self.reward_history)
            if reward > avg_reward + np.std(self.reward_history) * 0.5:
                gradient = np.random.normal(0, self.learning_rate * 1.5, 3)
            elif reward < avg_reward - np.std(self.reward_history) * 0.3:
                gradient = -np.random.normal(0, self.learning_rate, 3)
            else:
                gradient = np.random.normal(0, self.learning_rate * 0.8, 3)
        else:
            gradient = np.random.normal(0, self.learning_rate, 3)

        new_omega = self.omega + gradient + exploration_noise
        self.omega = np.clip(new_omega, 0.1, 1.8)
        
        if np.sum(self.omega) > 0.1:
            self.omega = self.omega / np.sum(self.omega) * 1.0

        return self.omega

class GyroPortfolioOpt:
    def __init__(self):
        self.max_lev = 3.5
        self.max_single = 0.35

    def objective(self, w, ret, cov, dE, cvar, metrics):
        profit = -np.sum(w * ret) * 1.3
        risk = 0.4 * np.sqrt(w.T @ cov @ w)
        steady = 0.2 * dE
        tail_risk = 0.15 * cvar
        turnover_penalty = 0.1 * np.sum(np.abs(w))
        return profit + risk + steady + tail_risk + turnover_penalty

    def optimize(self, ret, cov, dE, cvar, metrics):
        n = len(ret)
        w0 = np.array([0.5, 0.35, 0.15])
        bounds = [(-self.max_single, self.max_single) for _ in range(n)]
        cons = ({"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - self.max_lev})
        try:
            res = minimize(self.objective, w0, args=(ret, cov, dE, cvar, metrics), 
                          bounds=bounds, constraints=cons, method='SLSQP')
            return res.x if res.success else w0
        except:
            return w0

class GyroMinuteStrategyV3:
    def __init__(self):
        self.dynamics = GyroDynamics()
        self.evolver = GyroEvolve()
        self.opt = GyroPortfolioOpt()
        self.param_manager = AdaptiveParamManager()
        
        self.state_prev = None
        self.omega_prev = np.array([0.55, 0.30, 0.15])
        self.trade_history = []
        self.metrics_history = []
        self.equity_curve = [1.0]
        self.current_equity = 1.0
        self.max_equity = 1.0
        self.consecutive_losses = 0
        self.holding_periods = []
        self.current_position = 0
        self.position_since = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None

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

    def should_trade(self, adjust, price_window, signal_threshold, min_holding, current_idx):
        total_signal = adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos
        if abs(total_signal) < 0.0004:
            return False

        if self.position_since is not None:
            holding_time = current_idx - self.position_since
            if holding_time < min_holding:
                return False

        momentum = self.dynamics.indicator.calc_momentum_minute(price_window, 30)
        if abs(momentum) < signal_threshold:
            return False

        return True

    def check_stop_loss_take_profit(self, current_price):
        if self.position_since is None or self.entry_price is None or self.current_position == 0:
            return None

        if self.stop_loss_level is not None:
            if self.current_position > 0 and current_price <= self.stop_loss_level:
                return 'stop_loss'
            if self.current_position < 0 and current_price >= self.stop_loss_level:
                return 'stop_loss'

        if self.take_profit_level is not None:
            if self.current_position > 0 and current_price >= self.take_profit_level:
                return 'take_profit'
            if self.current_position < 0 and current_price <= self.take_profit_level:
                return 'take_profit'

        return None

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
            'return': ret,
            'reason': reason
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
            'metrics': [],
            'trades': [],
            'final_score': 0.0,
            'grade': 'D',
        }

        equity = initial_capital
        max_equity = initial_capital

        for i in range(720, len(prices)):
            price_window = prices[max(0, i-720):i]
            
            signal_threshold, min_holding, stop_loss, take_profit = self.param_manager.get_params(price_window)

            close_reason = self.check_stop_loss_take_profit(prices[i])
            if close_reason is not None:
                equity, old_pos = self.close_position(prices[i], equity, close_reason, i)
                max_equity = max(max_equity, equity)

            if len(price_window) >= 30:
                p_slice = price_window[-30:]
                ret = np.diff(p_slice) / p_slice[:-1]
            else:
                ret = np.array([0.0001, 0.0001, 0.0001])
            ret = np.resize(ret, 3)

            if len(price_window) >= 90:
                try:
                    cov = np.cov(np.resize(price_window[-90:], (3, 30)))
                except:
                    cov = np.eye(3) * 0.0001
            else:
                cov = np.eye(3) * 0.0001
            cvar = self.dynamics.indicator.calc_cvar(ret, 0.95)

            mom = self.dynamics.indicator.calc_momentum_minute(price_window, 30)
            vol = self.dynamics.indicator.calc_volatility_minute(price_window, 30)

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

            position_change = abs(adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos)
            reward = self.evolver.get_reward(metrics, position_change)
            new_omega = self.evolver.evolve_omega(state_curr, reward)

            weights = self.opt.optimize(ret, cov, dE, cvar, metrics)

            if self.should_trade(adjust, price_window, signal_threshold, min_holding, i):
                if self.current_position != 0:
                    equity, old_pos = self.close_position(prices[i], equity, 'normal_close', i)
                    max_equity = max(max_equity, equity)

                signal_strength = abs(adjust.main_pos) + 0.4 * abs(adjust.hedge_pos) + 0.2 * abs(adjust.time_arb_pos)
                position_size = np.sign(adjust.main_pos) * min(1.3, signal_strength * 15) * (equity / prices[i])
                self.current_position = position_size
                self.entry_price = prices[i]
                self.position_since = i

                sl_multiplier = np.sign(position_size) if position_size != 0 else 1
                self.stop_loss_level = prices[i] - (stop_loss * sl_multiplier * prices[i])
                self.take_profit_level = prices[i] + (take_profit * sl_multiplier * prices[i])

            if i > 0 and self.current_position != 0 and self.entry_price is not None:
                price_change = (prices[i] - prices[i-1]) / prices[i-1]
                equity *= (1 + price_change * np.sign(self.current_position))
                max_equity = max(max_equity, equity)

            self.state_prev = state_curr
            self.omega_prev = new_omega.copy()

            results['equity_curve'].append(equity)
            results['metrics'].append(metrics)

        total_return = (equity - initial_capital) / initial_capital * 100
        max_dd = (max_equity - equity) / max_equity * 100 if max_equity > 0 else 0

        all_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
        returns_std = np.std(all_returns) if len(all_returns) > 0 else 0
        sharpe = np.mean(all_returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0

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

def main():
    print("="*90)
    print("陀螺策略V3 - 缺陷优化版本")
    print("改进: 自适应止损/止盈、自适应信号阈值、优化强化学习、动态持仓")
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
    
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0004),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 + np.random.rand(n_minutes) * 0.0008),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 - np.random.rand(n_minutes) * 0.0008),
        'Close': prices,
        'Volume': np.random.randint(12000, 90000, n_minutes)
    }, index=dates)
    
    print(f"\n测试数据: {n_minutes}分钟 ({n_minutes/1440:.1f}天)")
    
    strategy = GyroMinuteStrategyV3()
    result = strategy.run_backtest(data, 100000)
    
    print("\n" + "="*90)
    print("[回测结果] V3缺陷优化版本")
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
    
    print(f"\n最终omega: [{strategy.evolver.omega[0]:.3f}, {strategy.evolver.omega[1]:.3f}, {strategy.evolver.omega[2]:.3f}]")
    
    print("\n" + "="*90)
    print("V3缺陷优化版本测试完成！")
    print("="*90)

if __name__ == "__main__":
    main()
