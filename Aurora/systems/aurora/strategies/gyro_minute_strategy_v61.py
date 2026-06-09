#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵策略 - V6.1 稳定版
增益性改造：
1. 参数矩阵收敛机制（保留）
2. 强化学习经验回放（保守化）
3. 自适应止损止盈（ATR+波动率）
4. 多周期信号确认（严格化）
5. 改进的奖励函数设计
6. 保留原陀螺动力学核心
重点：稳健性优于激进性
"""

import sys, os
aurora_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if aurora_root not in sys.path:
    sys.path.insert(0, aurora_root)

import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.linalg import eigvals
from scipy.optimize import minimize
from collections import deque
import random


# ==============================
# V6.1稳定版参数配置
# ==============================
TARGET_SHARPE_MIN = 2.0
TARGET_SHARPE_MAX = 4.0
TARGET_KRATIO = 3.0
TARGET_MAX_DD = 0.10
TARGET_CAP_UTIL = 0.90
LYAPUNOV_THRESHOLD = -0.01
OMEGA_EIGEN_THRESHOLD = 0.0

MAX_LEVERAGE = 2.0  # 降低杠杆
SINGLE_ASSET_MAX = 0.3
DT = 1 / (252 * 24 * 60)

MINUTE_WINDOW_SHORT = 30
MINUTE_WINDOW_MEDIUM = 90
MINUTE_WINDOW_LONG = 180
MINUTE_WINDOW_VLONG = 720

# 强化学习经验回放
REPLAY_BUFFER_SIZE = 2000
BATCH_SIZE = 32
TARGET_UPDATE_FREQ = 50

# 本地简化评估器（fallback，避免依赖 experiments/archive/enhanced_evaluator.py）
class LocalEnhancedEvaluator:
    def __init__(self):
        pass
    def evaluate(self, result):
        try:
            metrics = getattr(result, 'metrics', None)
            if metrics and hasattr(metrics, '__dict__'):
                md = metrics.__dict__
                score = md.get('sharpe_ratio', 0) * 0.4 + md.get('k_ratio', 0) * 0.3 - abs(md.get('max_dd', 0)) * 0.3
                grade = 'A' if score > 1 else ('B' if score > 0 else 'C')
                return {'score': score, 'grade': grade}
            return {'score': 0.0, 'grade': 'C'}
        except Exception:
            return {'score': 0.0, 'grade': 'C'}
    def get_grade(self, score):
        if score > 1.5: return 'A'
        if score > 0.5: return 'B'
        return 'C'
try:
    from enhanced_evaluator import EnhancedFinancialEvaluator as _Eval
    Evaluator = _Eval
except ImportError:
    Evaluator = LocalEnhancedEvaluator

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
    market_state: int

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

class Experience:
    def __init__(self, state, action, reward, next_state, done):
        self.state = state
        self.action = action
        self.reward = reward
        self.next_state = next_state
        self.done = done

# ==============================
# V6.1指标计算工具
# ==============================
class GyroIndicatorV61:
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
        if len(close) < window + 1:
            return 0.008
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

    @staticmethod
    def classify_market_state(price_series, vol_series):
        if len(price_series) < 90:
            return 0
        mom = np.mean(np.diff(price_series[-60:])) / price_series[-1]
        vol = np.mean(vol_series[-30:]) if len(vol_series) >= 30 else 0.01
        if abs(mom) > 0.001:
            return 1
        elif vol > 0.015:
            return 2
        else:
            return 0

# ==============================
# V6.1参数矩阵收敛器
# ==============================
class ParamMatrixConvergence:
    def __init__(self, target_grade=9.0):
        self.target_grade = target_grade
        self.param_history = deque(maxlen=500)
        self.score_history = deque(maxlen=500)
        self.best_params = None
        self.best_score = 0.0
        self.convergence_window = 20

    def update(self, params, score):
        self.param_history.append(params.copy())
        self.score_history.append(score)
        
        if score > self.best_score:
            self.best_score = score
            self.best_params = params.copy()
            return True
        return False

    def get_convergence_state(self):
        if len(self.score_history) < self.convergence_window:
            return False, 0.0
        recent_scores = list(self.score_history)[-self.convergence_window:]
        score_mean = np.mean(recent_scores)
        score_std = np.std(recent_scores)
        if score_std < 0.1 and score_mean > 8.0:
            return True, score_mean
        return False, score_mean

    def get_converged_params(self):
        if self.best_params is not None:
            return self.best_params
        elif len(self.param_history) > 0:
            return np.mean(np.array(self.param_history), axis=0)
        else:
            return np.array([0.5, 0.3, 0.2])

# ==============================
# V6.1强化学习演进器（保守版）
# ==============================
class GyroEvolveV61:
    def __init__(self, initial_omega=None):
        if initial_omega is None:
            self.omega = np.array([0.45, 0.35, 0.20])
        else:
            self.omega = initial_omega.copy()
        self.omega_history = deque(maxlen=500)
        self.reward_history = deque(maxlen=200)
        self.learning_rate = 5e-5
        self.gamma = 0.99
        self.exploration_rate = 0.15
        self.exploration_decay = 0.998
        self.min_exploration = 0.03
        
        self.replay_buffer = deque(maxlen=REPLAY_BUFFER_SIZE)
        self.target_omega = self.omega.copy()
        self.target_update_counter = 0

    def add_experience(self, state, action, reward, next_state):
        experience = Experience(state, action, reward, next_state, False)
        self.replay_buffer.append(experience)

    def get_reward(self, metrics, position_change):
        """保守版奖励函数 - 侧重风险控制"""
        reward = 0.0
        
        # 1. Sortino比率激励（重点）
        if metrics.sortino_ratio >= 2.0:
            reward += metrics.sortino_ratio * 12
        elif metrics.sortino_ratio >= 1.5:
            reward += metrics.sortino_ratio * 8
        else:
            reward -= (1.5 - metrics.sortino_ratio) * 8
        
        # 2. 夏普比率
        if TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX:
            reward += metrics.sharpe_ratio * 8
        elif metrics.sharpe_ratio >= TARGET_SHARPE_MIN:
            reward += metrics.sharpe_ratio * 5
        else:
            reward -= abs(metrics.sharpe_ratio - TARGET_SHARPE_MIN) * 4
        
        # 3. 最大回撤惩罚（重点）
        reward -= metrics.max_dd * 50
        
        # 4. 李雅普诺夫惩罚
        reward -= abs(metrics.lyapunov) * 25
        
        # 5. Omega比率
        if metrics.omega_ratio >= 1.5:
            reward += metrics.omega_ratio * 4
        
        # 6. 尾部比率
        if metrics.tail_ratio >= 1.5:
            reward += metrics.tail_ratio * 3
        
        # 7. 连续亏损严厉惩罚
        if metrics.max_consecutive_losses > 2:
            reward -= 15
        elif metrics.max_consecutive_losses > 4:
            reward -= 30
        
        # 8. 稳定性激励
        if metrics.rolling_sharpe_stability < 0.5:
            reward += 10
        
        # 9. 低换手率奖励
        reward -= position_change * 3
        
        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())
        
        self.exploration_rate = max(self.min_exploration, 
                                     self.exploration_rate * self.exploration_decay)
        
        if random.random() < self.exploration_rate:
            exploration_noise = np.random.normal(0, 0.015, 3)
            new_omega = self.omega + exploration_noise
        else:
            gradient = np.random.normal(0, self.learning_rate, 3)
            if self.reward_history and reward > np.mean(self.reward_history):
                gradient *= 1.2
            elif self.reward_history and reward < np.mean(self.reward_history) - np.std(self.reward_history):
                gradient *= -0.4
            
            new_omega = self.omega + gradient
        
        self.target_update_counter += 1
        if self.target_update_counter >= TARGET_UPDATE_FREQ:
            self.target_omega = self.omega.copy() * 0.95 + new_omega * 0.05
            self.target_update_counter = 0
        
        self.omega = np.clip(new_omega, 0.1, 1.2)
        
        self.omega = self.omega / np.sum(self.omega) * 1.0
        
        return self.omega

# ==============================
# V6.1组合优化器
# ==============================
class GyroPortfolioOptV61:
    def __init__(self):
        self.max_lev = MAX_LEVERAGE
        self.max_single = SINGLE_ASSET_MAX

    def objective(self, w, ret, cov, dE, cvar, metrics):
        profit = -np.sum(w * ret) * 1.0
        risk = 0.5 * np.sqrt(w.T @ cov @ w)
        steady = 0.25 * dE
        tail_risk = 0.25 * cvar
        turnover_penalty = 0.2 * np.sum(np.abs(w))
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

# ==============================
# V6.1自适应风险管理器
# ==============================
class AdaptiveRiskManager:
    def __init__(self):
        self.base_stop_loss = 0.012
        self.base_take_profit = 0.025
        self.atr_multiplier = 1.5
        self.volatility_adjust = 1.0

    def calculate_risk_params(self, atr, volatility_level, trend_strength):
        stop_loss = self.base_stop_loss + atr * self.atr_multiplier * self.volatility_adjust
        take_profit = self.base_take_profit + atr * self.atr_multiplier * 1.6
        
        if trend_strength > 0.7:
            stop_loss *= 1.3
            take_profit *= 1.2
        elif trend_strength < 0.3:
            stop_loss *= 0.8
            take_profit *= 0.9
        
        stop_loss = np.clip(stop_loss, 0.007, 0.025)
        take_profit = np.clip(take_profit, 0.012, 0.05)
        
        return stop_loss, take_profit

# ==============================
# V6.1陀螺动力学（保留原核心）
# ==============================
class GyroDynamicsV61:
    def __init__(self):
        self.dt = DT
        self.indicator = GyroIndicatorV61()
        self.evaluator = Evaluator()

    def build_skew_matrix(self, omega):
        w1, w2, w3 = omega
        J = np.array([
            [0, -w3, w2],
            [w3, 0, -w1],
            [-w2, w1, 0]
        ], dtype=np.float32)
        return J

    def build_spin_matrix(self, momentum, vol, corr_mat, a=0.55, b=0.25, c=0.2):
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
        return np.mean(np.log(np.abs(diff) + 1e-10))

    def calc_energy_diff(self, omega_curr, omega_prev):
        return np.sum(np.square(omega_curr)) - np.sum(np.square(omega_prev))

    def gyro_response(self, F, omega, Omega):
        J = self.build_skew_matrix(omega)
        delta_P = J @ F * self.dt

        f_norm = np.linalg.norm(F)
        if f_norm > 2.5:
            delta_P = delta_P * 1.15
        elif f_norm < 0.4:
            delta_P = delta_P * 0.7

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
# V6.1完整策略主类
# ==============================
class GyroMinuteStrategyV61:
    def __init__(self):
        self.dynamics = GyroDynamicsV61()
        self.evolver = GyroEvolveV61()
        self.opt = GyroPortfolioOptV61()
        self.risk_manager = AdaptiveRiskManager()
        self.convergence = ParamMatrixConvergence(target_grade=9.0)
        
        self.state_prev = None
        self.omega_prev = np.array([0.45, 0.35, 0.20])
        self.trade_history = []
        self.metrics_history = []
        self.equity_curve = []
        self.current_equity = 100000.0
        self.max_equity = 100000.0
        self.consecutive_losses = 0
        self.holding_periods = []
        self.current_position = 0
        self.position_since = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.volatility_history = deque(maxlen=100)

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
        max_e = np.maximum.accumulate(equity)
        drawdown = (equity - max_e) / max_e
        max_dd = np.min(drawdown)

        returns_std = np.std(returns)
        sharpe = np.mean(returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
        k_ratio = (np.mean(returns) / returns_std) / np.abs(max_dd) if np.abs(max_dd) > 0 and returns_std > 0 else 0

        sortino = self.dynamics.indicator.calc_sortino(returns)
        omega = self.dynamics.indicator.calc_omega(returns)
        tail_ratio = self.dynamics.indicator.calc_tail_ratio(returns)
        rolling_stability = self.dynamics.indicator.calc_rolling_sharpe_stability(returns, window=30)
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

    def should_trade_multicycle(self, adjust, price_window, signal_threshold, current_idx):
        total_signal = adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos
        
        if abs(total_signal) < signal_threshold:
            return False, signal_threshold
        
        if self.position_since is not None:
            holding_time = current_idx - self.position_since
            if holding_time < 30:
                return False, signal_threshold
        
        mom_15 = self.dynamics.indicator.calc_momentum_minute(price_window, 15)
        mom_30 = self.dynamics.indicator.calc_momentum_minute(price_window, 30)
        mom_90 = self.dynamics.indicator.calc_momentum_minute(price_window, 90)
        
        signals = [np.sign(mom_15), np.sign(mom_30), np.sign(mom_90)]
        agreement = sum(1 for s in signals if s == np.sign(total_signal))
        
        if agreement >= 2:
            return True, signal_threshold
        
        return False, signal_threshold

    def close_position(self, current_price, equity, reason, current_idx):
        if self.current_position == 0 or self.entry_price is None:
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
            'reason': reason,
            'omega': self.evolver.omega.copy()
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
            'convergence_history': [],
            'final_score': 0.0,
            'grade': 'D'
        }

        equity = initial_capital
        max_equity = initial_capital

        for i in range(MINUTE_WINDOW_LONG, len(prices)):
            price_window = prices[max(0, i-MINUTE_WINDOW_VLONG):i]
            high_window = high[max(0, i-MINUTE_WINDOW_VLONG):i]
            low_window = low[max(0, i-MINUTE_WINDOW_VLONG):i]
            close_window = prices[max(0, i-MINUTE_WINDOW_VLONG):i]
            
            mom = self.dynamics.indicator.calc_momentum_minute(price_window, MINUTE_WINDOW_SHORT)
            vol = self.dynamics.indicator.calc_volatility_minute(price_window, MINUTE_WINDOW_SHORT)
            atr = self.dynamics.indicator.calc_atr_minute(high_window, low_window, close_window)
            trend_strength = self.dynamics.indicator.calc_trend_strength(price_window)
            self.volatility_history.append(vol)
            market_state = self.dynamics.indicator.classify_market_state(price_window, list(self.volatility_history))
            
            signal_threshold = max(0.0003, min(0.0007, 0.0005 + vol * 0.015))
            
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
            
            gyro_state = GyroState(
                S=state_curr,
                Omega=Omega,
                omega=self.evolver.omega,
                F=F,
                lyapunov=lyap,
                energy_diff=dE,
                atr=atr,
                trend_strength=trend_strength,
                volatility_level=vol,
                market_state=market_state
            )
            
            should_stop, reason = False, None
            if self.current_position != 0:
                stop_loss, take_profit = self.risk_manager.calculate_risk_params(
                    atr, vol, trend_strength
                )
                
                stop_price = self.entry_price * (1 - stop_loss * np.sign(self.current_position))
                take_profit_price = self.entry_price * (1 + take_profit * np.sign(self.current_position))
                
                if self.current_position > 0:
                    if prices[i] <= stop_price:
                        should_stop, reason = True, 'stop_loss'
                    elif prices[i] >= take_profit_price:
                        should_stop, reason = True, 'take_profit'
                elif self.current_position < 0:
                    if prices[i] >= stop_price:
                        should_stop, reason = True, 'stop_loss'
                    elif prices[i] <= take_profit_price:
                        should_stop, reason = True, 'take_profit'
            
            if should_stop:
                equity, _ = self.close_position(prices[i], equity, reason, i)
                max_equity = max(max_equity, equity)
            
            current_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
            metrics = self.calculate_all_metrics(current_returns)
            metrics.lyapunov = lyap
            self.metrics_history.append(metrics)
            
            converged, _ = self.dynamics.is_converged(metrics, Omega)
            
            position_change = abs(adjust.main_pos + adjust.hedge_pos + adjust.time_arb_pos)
            reward = self.evolver.get_reward(metrics, position_change)
            
            prev_state = self.state_prev if self.state_prev is not None else state_curr
            self.evolver.add_experience(prev_state, self.omega_prev, reward, state_curr)
            
            if not converged:
                new_omega = self.evolver.evolve_omega(state_curr, reward)
            else:
                new_omega = self.evolver.omega
            
            self.convergence.update(new_omega, 7.5 + min(2.0, reward / 15))
            results['convergence_history'].append({
                'gen': i,
                'score': 7.5 + min(2.0, reward / 15),
                'omega': new_omega.copy()
            })
            
            should_open, threshold_used = self.should_trade_multicycle(
                adjust, price_window, signal_threshold, i
            )
            
            if should_open:
                if self.current_position != 0:
                    equity, _ = self.close_position(prices[i], equity, 'switch', i)
                    max_equity = max(max_equity, equity)
                
                signal_strength = abs(adjust.main_pos) + 0.35 * abs(adjust.hedge_pos) + 0.15 * abs(adjust.time_arb_pos)
                position_size = np.sign(adjust.main_pos) * min(1.0, signal_strength * 12) * (equity / prices[i])
                
                self.current_position = position_size
                self.entry_price = prices[i]
                self.position_since = i
            
            if i > 0 and self.current_position != 0 and self.entry_price is not None and self.position_since is not None and self.position_since < i:
                price_change = (prices[i] - prices[i-1]) / prices[i-1]
                equity *= (1 + price_change * np.sign(self.current_position))
                max_equity = max(max_equity, equity)
            
            self.state_prev = state_curr
            self.omega_prev = new_omega.copy()
            results['equity_curve'].append(equity)
            results['metrics'].append(metrics)
        
        all_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
        total_return = (equity - initial_capital) / initial_capital * 100
        max_dd = (max_equity - equity) / max_equity * 100 if max_equity > 0 else 0
        
        result_for_eval = {
            'returns': all_returns,
            'days': len(data) / 1440,
            'total_return_pct': total_return,
            'sharpe_ratio': np.mean(all_returns) / np.std(all_returns) * np.sqrt(252*24*60) if len(all_returns) > 0 and np.std(all_returns) > 0 else 0,
            'max_drawdown_pct': max_dd,
            'total_trades': len(self.trade_history),
            'profit_factor': np.sum(all_returns[all_returns > 0]) / np.abs(np.sum(all_returns[all_returns < 0])) if len(all_returns) > 0 and np.sum(all_returns[all_returns < 0]) != 0 else 0,
            'win_rate_pct': len(all_returns[all_returns > 0]) / len(all_returns) * 100 if len(all_returns) > 0 else 0,
        }
        
        eval_result = self.dynamics.evaluator.evaluate(result_for_eval)
        if isinstance(eval_result, tuple):
            score, metric_scores, details = eval_result
        else:
            score = eval_result.get('score', 0.0)
            metric_scores = {}
            details = eval_result
        results.update({
            'final_score': score,
            'grade': self.dynamics.evaluator.get_grade(score),
            'total_return_pct': total_return,
            'max_drawdown_pct': max_dd,
            'total_trades': len(self.trade_history),
            'metric_scores': metric_scores
        })
        
        return results

    def update_price(self, current_price: float, data=None):
        return {"action": "hold", "balance": getattr(self, "current_balance", 100000.0), "position": getattr(self, "current_position", 0), "signal": getattr(self, "last_signal", "neutral")}

    def get_performance(self):
        return {"total_trades": getattr(self, "total_trades", 0), "winning_trades": getattr(self, "winning_trades", 0), "sharpe_ratio": getattr(self, "sharpe_ratio", 0.0), "annual_return": getattr(self, "annual_return", 0.0), "max_drawdown": getattr(self, "max_drawdown", 0.0), "win_rate": getattr(self, "win_rate", 0.0)}

    def set_active(self, active: bool):
        self.is_active = active
        self.total_trades = getattr(self, 'total_trades', 0)
        self.winning_trades = getattr(self, 'winning_trades', 0)
        self.sharpe_ratio = getattr(self, 'sharpe_ratio', 0.0)
        self.annual_return = getattr(self, 'annual_return', 0.0)
        self.max_drawdown = getattr(self, 'max_drawdown', 0.0)
        self.win_rate = getattr(self, 'win_rate', 0.0)
        self.current_balance = getattr(self, 'current_balance', 100000.0)
        self.current_position = getattr(self, 'current_position', 0)
        self.last_signal = getattr(self, 'last_signal', 'neutral')

def main():
    print("="*90)
    print("陀螺恒稳进动矩阵策略 - V6.1 稳定版")
    print("改进：参数矩阵收敛 + 强化学习(保守) + 自适应风控 + 多周期确认")
    print("="*90)
    
    np.random.seed(42)
    n_minutes = 5000
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='min')
    
    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    for i in range(1, n_minutes):
        hour_of_day = i % 1440 / 1440
        if hour_of_day < 0.25:
            dr = np.random.normal(0.00012, 0.0012)
        elif hour_of_day < 0.5:
            dr = np.random.normal(0.00025, 0.0018)
        elif hour_of_day < 0.75:
            dr = np.random.normal(0.00018, 0.0015)
        else:
            dr = np.random.normal(0.00006, 0.0009)
        prices[i] = prices[i-1] * (1 + dr)
    
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0004),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 + np.random.rand(n_minutes) * 0.001),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 - np.random.rand(n_minutes) * 0.001),
        'Close': prices,
        'Volume': np.random.randint(12000, 90000, n_minutes)
    }, index=dates)
    
    print(f"\n测试数据：{n_minutes}分钟 ({n_minutes/1440:.1f}天)")
    
    strategy = GyroMinuteStrategyV61()
    result = strategy.run_backtest(data, 100000)
    
    print("\n" + "="*90)
    print("V6.1稳定版回测结果")
    print("="*90)
    print(f"综合评分：{result['final_score']:.2f} ({result['grade']})")
    print(f"总收益率：{result['total_return_pct']:.2f}%")
    print(f"最大回撤：{result['max_drawdown_pct']:.2f}%")
    print(f"交易次数：{result['total_trades']}")
    print(f"平均持仓：{np.mean(strategy.holding_periods):.0f}分钟" if strategy.holding_periods else "")
    
    print("\n指标得分：")
    for k, v in sorted(result['metric_scores'].items(), key=lambda x: x[1], reverse=True):
        status = "[OK]" if v >= 8 else "[WARN]" if v >= 6 else "[FAIL]"
        print(f"{status} {k:<25}: {v:.1f}")
    
    converged, avg_score = strategy.convergence.get_convergence_state()
    print(f"\n参数收敛状态：{'已收敛' if converged else '未收敛'}")
    print(f"平均收敛分数：{avg_score:.2f}")
    print(f"最优参数：{strategy.convergence.best_params}" if strategy.convergence.best_params is not None else "")
    
    print("\n" + "="*90)
    print("V6.1稳定版测试完成！")
    print("="*90)

if __name__ == "__main__":
    main()
