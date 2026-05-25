#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵·V6增强优化版
核心改进：使用V6增强优化器优化陀螺参数矩阵
保留原核心逻辑，添加优化因子，谨慎处理自适应止损
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
from v6_enhanced_optimizer import V6EnhancedOptimizer

# ==============================
# 参数配置
# ==============================
TARGET_SHARPE_MIN = 2.0
TARGET_SHARPE_MAX = 4.0
TARGET_KRATIO = 3.0
TARGET_MAX_DD = 0.10
LYAPUNOV_THRESHOLD = -0.01

MAX_LEVERAGE = 3.0
SINGLE_ASSET_MAX = 0.3
DT = 1 / (252 * 24 * 60)

MINUTE_WINDOW_SHORT = 60
MINUTE_WINDOW_MEDIUM = 180
MINUTE_WINDOW_LONG = 720
MINUTE_WINDOW_VLONG = 1440

# 优化因子配置
OPTIMIZATION_FACTORS = {
    'omega_scaling': 0.8,      # 进动速度缩放因子
    'momentum_sensitivity': 1.2,  # 动量敏感度
    'volatility_weight': 0.7,  # 波动率权重
    'correlation_threshold': 0.3,  # 相关性阈值
    'stop_loss_multiplier': 1.5,   # 止损乘数
    'take_profit_multiplier': 1.8, # 止盈乘数
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
        if len(close) < window + 1:
            return 0.01
        tr1 = high[-window:] - low[-window:]
        tr2 = np.abs(high[-window:] - close[-window-1:-1])
        tr3 = np.abs(low[-window:] - close[-window-1:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        return np.mean(tr)

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

# ==============================
# 陀螺动力学核心引擎（保留原逻辑）
# ==============================
class GyroDynamics:
    def __init__(self, factors=None):
        self.dt = DT
        self.indicator = GyroIndicator()
        self.evaluator = EnhancedFinancialEvaluator()
        self.factors = factors if factors is not None else OPTIMIZATION_FACTORS

    def build_skew_matrix(self, omega):
        w1, w2, w3 = omega * self.factors['omega_scaling']
        J = np.array([
            [0, -w3, w2],
            [w3, 0, -w1],
            [-w2, w1, 0]
        ], dtype=np.float32)
        return J

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

    def is_converged(self, metrics, Omega):
        eigen_vals = eigvals(Omega)
        eigen_real = np.real(eigen_vals)
        
        conditions = [
            TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX,
            metrics.k_ratio >= TARGET_KRATIO,
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
# 稳健自适应止损机制（避免坑）
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
        """
        稳健的自适应止损计算方法
        - ATR基础止损
        - 趋势强度调整
        - 波动率保护
        """
        # 基于ATR的动态止损（避免噪声触发）
        stop_loss = self.base_stop + atr * 1.5
        take_profit = self.base_take + atr * 2.0
        
        # 趋势强时放宽止损（避免过早被止损）
        if trend_strength > 0.6:
            stop_loss = min(stop_loss * 1.3, self.max_stop)
            take_profit = min(take_profit * 1.2, self.max_take)
        elif trend_strength < 0.3:
            stop_loss = max(stop_loss * 0.8, self.min_stop)
            take_profit = max(take_profit * 0.9, self.min_take)
        
        # 高波动时增加止损宽度
        if volatility > 0.015:
            stop_loss = min(stop_loss * 1.2, self.max_stop)
        
        return stop_loss, take_profit

# ==============================
# V6优化版策略主类
# ==============================
class GyroMinuteStrategyV6Optimized:
    def __init__(self):
        self.factors = OPTIMIZATION_FACTORS.copy()
        self.dynamics = GyroDynamics(factors=self.factors)
        self.stop_loss_manager = RobustStopLoss()
        
        self.state_prev = None
        self.omega_prev = np.array([0.3, 0.5, 0.7])
        self.trade_history = []
        self.metrics_history = []
        self.consecutive_losses = 0
        self.holding_periods = []
        self.current_position = 0
        self.position_since = None
        self.entry_price = None
        self.current_stop_loss = None
        self.current_take_profit = None

    def calculate_all_metrics(self, returns):
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

        avg_holding = np.mean(self.holding_periods) if self.holding_periods else 0

        return StrategyMetrics(
            sharpe_ratio=sharpe,
            k_ratio=k_ratio,
            max_dd=max_dd,
            cap_util=min(len(self.trade_history) * 0.02, 1.0),
            sortino_ratio=sortino,
            omega_ratio=omega,
            rolling_sharpe_stability=rolling_stability,
            information_ratio=0,
            market_correlation=0.5,
            tail_ratio=tail_ratio,
            trade_frequency=len(self.trade_history) / max(len(returns)/(252*24*60), 1),
            max_consecutive_losses=self.consecutive_losses,
            avg_holding_period=avg_holding,
            recovery_time=0.0,
            lyapunov=0.0
        )

    def should_trade(self, adjust, price_window):
        if np.abs(adjust.main_pos) < 0.001:
            return False
        
        if self.position_since is not None:
            holding_time = len(price_window)
            if holding_time < 30:
                return False
        
        momentum = self.dynamics.indicator.calc_momentum_minute(price_window)
        if np.abs(momentum) < 0.0005:
            return False
        
        return True

    def run_backtest(self, data, initial_capital=100000):
        prices = data['Close'].values
        high = data['High'].values
        low = data['Low'].values
        
        results = {
            'equity_curve': [],
            'metrics': [],
            'trades': [],
            'omega_history': [],
            'final_score': 0.0,
            'grade': 'D',
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
                except:
                    pass

            Omega = self.dynamics.build_spin_matrix(mom, vol, corr_mat)
            state_curr = np.array([mom, vol, np.mean(corr_mat)])
            F = self.dynamics.calc_torque(state_curr, self.state_prev if self.state_prev is not None else state_curr)
            
            lyap = self.dynamics.calc_lyapunov(np.array([self.omega_prev]))
            dE = self.dynamics.calc_energy_diff(self.omega_prev, self.omega_prev)
            adjust = self.dynamics.gyro_response(F, self.omega_prev, Omega)

            current_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
            metrics = self.calculate_all_metrics(current_returns)
            metrics.lyapunov = lyap
            self.metrics_history.append(metrics)

            # 检查止损止盈
            if self.current_position != 0 and self.entry_price is not None:
                stop_price = self.entry_price * (1 - self.current_stop_loss * np.sign(self.current_position))
                take_price = self.entry_price * (1 + self.current_take_profit * np.sign(self.current_position))
                
                if self.current_position > 0:
                    if prices[i] <= stop_price:
                        # 止损
                        ret = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret)
                        self.consecutive_losses += 1
                        self.trade_history.append({'return': ret, 'reason': 'stop_loss'})
                        self.current_position = 0
                        self.position_since = None
                        self.entry_price = None
                    elif prices[i] >= take_price:
                        # 止盈
                        ret = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret)
                        self.consecutive_losses = 0
                        self.trade_history.append({'return': ret, 'reason': 'take_profit'})
                        self.current_position = 0
                        self.position_since = None
                        self.entry_price = None
                else:
                    if prices[i] >= stop_price:
                        ret = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret)
                        self.consecutive_losses += 1
                        self.trade_history.append({'return': ret, 'reason': 'stop_loss'})
                        self.current_position = 0
                        self.position_since = None
                        self.entry_price = None
                    elif prices[i] <= take_price:
                        ret = (prices[i] - self.entry_price) / self.entry_price
                        equity *= (1 + ret)
                        self.consecutive_losses = 0
                        self.trade_history.append({'return': ret, 'reason': 'take_profit'})
                        self.current_position = 0
                        self.position_since = None
                        self.entry_price = None

            max_equity = max(max_equity, equity)

            # 信号开仓
            if self.current_position == 0 and self.should_trade(adjust, short_window):
                trend_strength = min(abs(mom) * 100, 1.0)
                self.current_stop_loss, self.current_take_profit = self.stop_loss_manager.calculate(
                    atr, trend_strength, vol
                )
                
                position_size = np.sign(adjust.main_pos) * min(1.0, abs(adjust.main_pos) * 20) * (equity / prices[i])
                self.current_position = position_size
                self.entry_price = prices[i]
                self.position_since = i

            # 持仓期间更新权益
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

    def optimize_with_v6(self, data, iterations=20):
        """使用V6增强优化器优化策略参数"""
        
        param_bounds = [
            (0.5, 1.5),   # omega_scaling
            (0.8, 1.8),   # momentum_sensitivity
            (0.5, 1.2),   # volatility_weight
            (0.1, 0.5),   # correlation_threshold
            (1.0, 2.0),   # stop_loss_multiplier
            (1.5, 2.5),   # take_profit_multiplier
        ]
        
        initial_params = np.array([
            self.factors['omega_scaling'],
            self.factors['momentum_sensitivity'],
            self.factors['volatility_weight'],
            self.factors['correlation_threshold'],
            self.factors['stop_loss_multiplier'],
            self.factors['take_profit_multiplier'],
        ])
        
        print(f"\n=== 开始参数优化 ({iterations}次迭代) ===")
        best_score = -np.inf
        best_params = None
        
        for i in range(iterations):
            noise = np.random.normal(0, 0.05, len(initial_params))
            trial_params = np.clip(initial_params + noise, 
                                  [b[0] for b in param_bounds], 
                                  [b[1] for b in param_bounds])
            
            self.factors = {
                'omega_scaling': trial_params[0],
                'momentum_sensitivity': trial_params[1],
                'volatility_weight': trial_params[2],
                'correlation_threshold': trial_params[3],
                'stop_loss_multiplier': trial_params[4],
                'take_profit_multiplier': trial_params[5],
            }
            self.dynamics = GyroDynamics(factors=self.factors)
            
            result = self.run_backtest(data)
            current_score = result['final_score']
            
            if current_score > best_score:
                best_score = current_score
                best_params = trial_params.copy()
                initial_params = trial_params.copy()
            
            print(f"迭代 {i+1}/{iterations}: 评分 = {current_score:.2f}")
        
        if best_params is not None:
            self.factors = {
                'omega_scaling': best_params[0],
                'momentum_sensitivity': best_params[1],
                'volatility_weight': best_params[2],
                'correlation_threshold': best_params[3],
                'stop_loss_multiplier': best_params[4],
                'take_profit_multiplier': best_params[5],
            }
            self.dynamics = GyroDynamics(factors=self.factors)
            print(f"\n优化完成！最佳评分: {best_score:.2f}")
            print(f"优化后参数: {self.factors}")
        
        return best_score

# ==============================
# 测试优化版策略
# ==============================
if __name__ == "__main__":
    print("="*90)
    print("陀螺恒稳进动矩阵·V6优化版")
    print("改进: V6增强优化器 + 优化因子 + 稳健自适应止损")
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
    
    # 先测试原始版本
    strategy = GyroMinuteStrategyV6Optimized()
    result_before = strategy.run_backtest(test_data, 100000)
    
    print("\n" + "="*90)
    print("[优化前] 原始策略表现")
    print("="*90)
    print(f"综合评分: {result_before['final_score']:.2f} ({result_before['grade']})")
    print(f"总收益率: {result_before['total_return_pct']:.2f}%")
    print(f"夏普比率: {result_before['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result_before['max_drawdown_pct']:.2f}%")
    print(f"交易次数: {result_before['total_trades']}")
    
    # 使用V6优化器优化
    strategy2 = GyroMinuteStrategyV6Optimized()
    best_score = strategy2.optimize_with_v6(test_data, iterations=10)
    
    # 测试优化后版本
    result_after = strategy2.run_backtest(test_data, 100000)
    
    print("\n" + "="*90)
    print("[优化后] V6优化器优化后表现")
    print("="*90)
    print(f"综合评分: {result_after['final_score']:.2f} ({result_after['grade']})")
    print(f"总收益率: {result_after['total_return_pct']:.2f}%")
    print(f"夏普比率: {result_after['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result_after['max_drawdown_pct']:.2f}%")
    print(f"交易次数: {result_after['total_trades']}")
    
    print("\n" + "="*90)
    print("优化对比:")
    print(f"评分提升: {result_before['final_score']:.2f} -> {result_after['final_score']:.2f} (+{result_after['final_score']-result_before['final_score']:.2f})")
    print(f"收益率变化: {result_before['total_return_pct']:.2f}% -> {result_after['total_return_pct']:.2f}%")
    print(f"最大回撤变化: {result_before['max_drawdown_pct']:.2f}% -> {result_after['max_drawdown_pct']:.2f}%")
    print("="*90)
