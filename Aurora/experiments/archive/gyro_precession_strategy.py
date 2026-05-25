# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵·自适应演进交易策略（金融级专业版）
核心逻辑：刚体进动动力学 + 李雅普诺夫稳态 + SAC自适应演进 + 16指标协同收敛
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
from enum import Enum

# 导入增强型评估器
from enhanced_evaluator import EnhancedFinancialEvaluator

# ==============================
# ==============================
# 市场状态枚举（P3：状态分类）
# ==============================
class MarketState(Enum):
    TRENDING_UP = 1       # 上涨趋势
    TRENDING_DOWN = 2     # 下跌趋势
    RANGING = 3           # 震荡
    HIGH_VOLATILITY = 4   # 高波动
    LOW_VOLATILITY = 5    # 低波动
    CRISIS = 6            # 危机/崩盘

# 全局稳态收敛超参（金融级标准）
# ==============================
TARGET_SHARPE_MIN = 2.0
TARGET_SHARPE_MAX = 3.0
TARGET_KRATIO = 2.5
TARGET_MAX_DD = 0.12
TARGET_CAP_UTIL = 0.85
LYAPUNOV_THRESHOLD = -0.01
OMEGA_EIGEN_THRESHOLD = 0.0

# 陀螺动力学物理约束
MAX_LEVERAGE = 2.5
SINGLE_ASSET_MAX = 0.2
DT = 1/252

# ==============================
# 陀螺八维状态结构体（P3：3→8维增强）（严格对应物理建模）
# ==============================
@dataclass
class GyroState:
    S: np.ndarray          # 状态向量 [动量,波动,相关性,atr,趋势强度,波动水平,成交量因子,市场状态]
    Omega: np.ndarray      # 3×3自旋矩阵
    omega: np.ndarray      # [ω1,ω2,ω3]三维进动速度
    F: np.ndarray          # 市场扰动力矩
    lyapunov: float        # 李雅普诺夫指数
    energy_diff: float     # 能量耗散率 dE/dt
    market_state: MarketState = MarketState.RANGING
    volume_factor: float = 0.0
    volatility_level: float = 0.0
    trend_strength: float = 0.0
    atr: float = 0.0

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
# 增强型指标计算工具（16个协同指标体系）
# ==============================
class GyroIndicator:
    @staticmethod
    def calc_momentum(price_series):
        return np.mean(np.diff(price_series)) / price_series[-1]

    @staticmethod
    def calc_volatility(price_series):
        return np.std(np.diff(price_series))

    @staticmethod
    def calc_atr(high, low, close):
        tr = np.maximum(high-low, np.abs(high-close), np.abs(low-close))
        return np.mean(tr[-20:])

    @staticmethod
    def calc_cvar(returns, conf=0.95):
        var = np.percentile(returns, (1-conf)*100)
        return np.mean(returns[returns <= var])

    @staticmethod
    def calc_sortino(returns, target_return=0):
        downside_returns = returns[returns < target_return]
        if len(downside_returns) == 0:
            return np.inf
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        if downside_deviation == 0:
            return np.inf
        return (np.mean(returns) - target_return) / downside_deviation

    @staticmethod
    def calc_omega(returns, threshold=0):
        gains = returns[returns > threshold] - threshold
        losses = threshold - returns[returns <= threshold]
        if np.sum(losses) == 0:
            return np.inf
        return np.sum(gains) / np.sum(losses)

    @staticmethod
    def calc_tail_ratio(returns):
        p5 = np.percentile(returns, 5)
        if p5 == 0:
            return 1.0
        return np.percentile(returns, 95) / np.abs(p5)

    @staticmethod
    def calc_rolling_sharpe_stability(returns, window=60):
        rolling_sharpe = pd.Series(returns).rolling(window).apply(
            lambda x: np.mean(x) / np.std(x) * np.sqrt(252) if np.std(x) > 0 else 0
        ).dropna()
        if len(rolling_sharpe) == 0:
            return 1.0
        return np.std(rolling_sharpe) / np.mean(rolling_sharpe) if np.mean(rolling_sharpe) != 0 else 1.0

    @staticmethod
    def calc_information_ratio(returns, benchmark_returns):
        active_returns = returns - benchmark_returns
        tracking_error = np.std(active_returns)
        if tracking_error == 0:
            return np.inf
        return np.mean(active_returns) / tracking_error * np.sqrt(252)

# ==============================
# 陀螺动力学核心引擎（100%物理建模）
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
        O_mat = O_mat / np.trace(O_mat) * 0.5 if np.trace(O_mat) != 0 else O_mat
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
        if f_norm > 2.0:
            delta_P = delta_P * 2.0
        elif f_norm < 0.5:
            delta_P = delta_P * 0.5

        return TradeAdjust(
            main_pos=delta_P[0],
            hedge_pos=delta_P[1],
            time_arb_pos=delta_P[2]
        )

    def is_converged(self, m: StrategyMetrics, Omega):
        # P5: 加权评分替代硬阈值
        score = 0.0
        if m.sharpe_ratio >= TARGET_SHARPE_MIN: score+=min(40.0,(m.sharpe_ratio-TARGET_SHARPE_MIN)*20)
        if m.k_ratio >= TARGET_KRATIO: score+=20.0
        if m.max_dd <= TARGET_MAX_DD: score+=20.0
        if m.lyapunov < LYAPUNOV_THRESHOLD: score+=20.0
        import numpy as np; from numpy.linalg import eigvals
        eigen_vals = eigvals(Omega)
        eigen_real = np.real(eigen_vals)
        if np.all(eigen_real <= OMEGA_EIGEN_THRESHOLD): score+=15.0
        if m.sortino_ratio >= 2.0: score+=5.0
        if m.omega_ratio >= 1.5: score+=5.0
        if m.rolling_sharpe_stability <= 0.5: score+=5.0
        if m.max_consecutive_losses <= 5: score+=5.0
        if m.tail_ratio >= 1.5: score+=5.0
        return score >= 70.0, [c for c in [m.sharpe_ratio>=TARGET_SHARPE_MIN,m.k_ratio>=TARGET_KRATIO,m.max_dd<=TARGET_MAX_DD,m.lyapunov<LYAPUNOV_THRESHOLD]]

# ==============================
# SAC强化学习自动演进模块（增强版）
# ==============================
class GyroEvolve:
    def __init__(self):
        self.omega = np.array([0.5, 0.5, 0.5])
        self.omega_history = deque(maxlen=100)
        self.reward_history = deque(maxlen=50)
        self.learning_rate = 1e-4
        self.gamma = 0.99

    def get_reward(self, metrics: StrategyMetrics):
        reward = 0.0

        if TARGET_SHARPE_MIN <= metrics.sharpe_ratio <= TARGET_SHARPE_MAX:
            reward += metrics.sharpe_ratio * 10
        else:
            reward -= abs(metrics.sharpe_ratio - 2.5) * 5

        if metrics.k_ratio > TARGET_KRATIO:
            reward += metrics.k_ratio * 5

        reward -= metrics.max_dd * 20
        reward -= abs(metrics.lyapunov) * 30

        if metrics.sortino_ratio >= 2.0:
            reward += metrics.sortino_ratio * 3
        if metrics.omega_ratio >= 1.5:
            reward += metrics.omega_ratio * 2
        if metrics.rolling_sharpe_stability <= 0.5:
            reward += (0.5 - metrics.rolling_sharpe_stability) * 10

        reward -= metrics.max_consecutive_losses * 2

        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())

        exploration_noise = np.random.normal(0, 0.05, 3)
        gradient = np.random.normal(0, self.learning_rate, 3)

        if reward > np.mean(self.reward_history) if self.reward_history else 0:
            gradient *= 1.2
        else:
            gradient *= -0.5

        new_omega = self.omega + gradient + exploration_noise
        self.omega = np.clip(new_omega, 0.1, 2.0)

        return self.omega

# ==============================
# 组合凸优化风控模块（增强版）
# ==============================

# ==============================
# P2: AdaptiveRiskManager
# ==============================
class AdaptiveRiskManager:
    def __init__(self, base_sl=0.02, base_tp=0.06):
        self.base_sl=base_sl; self.base_tp=base_tp; self.vol_lb=20; self.va=0.95
    def adjust(self, ret):
        if len(ret)<self.vol_lb: return self.base_sl,self.base_tp
        r=ret[-self.vol_lb:]; vol=np.std(r) if len(r)>1 else 0.02
        vf=min(2.5,max(0.5,vol/0.02)); var=np.percentile(r,5)
        return self.base_sl*vf*(1+abs(var)), self.base_tp*vf*(1+abs(var))

# ==============================
# P2: MultiCycleConfirmer
# ==============================
class MultiCycleConfirmer:
    def __init__(self, ww=20): self.ww=ww
    def confirm(self, ds, wp):
        if len(wp)<self.ww: return ds
        wr=np.diff(np.log(wp[-self.ww:])); wt=np.mean(wr)/(np.std(wr)+1e-8)
        if np.sign(ds)==np.sign(wt) and np.sign(ds)!=0: return ds*min(1.0,abs(wt)/2.0)
        return ds*0.3
class GyroPortfolioOpt:
    def __init__(self):
        self.max_lev = MAX_LEVERAGE
        self.max_single = SINGLE_ASSET_MAX

    def objective(self, w, ret, cov, dE, cvar, metrics):
        profit = -np.sum(w * ret)
        risk = 0.5 * np.sqrt(w.T @ cov @ w)
        steady = 0.3 * dE
        tail_risk = 0.2 * cvar
        correlation_penalty = 0.1 * np.sum(np.abs(w)) * metrics.market_correlation
        return profit + risk + steady + tail_risk + correlation_penalty

    def optimize(self, ret, cov, dE, cvar, metrics):
        n = len(ret)
        w0 = np.ones(n) / n
        bounds = [(-self.max_single, self.max_single) for _ in range(n)]
        cons = ({"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - self.max_lev})
        res = minimize(self.objective, w0, args=(ret, cov, dE, cvar, metrics), 
                      bounds=bounds, constraints=cons, method='SLSQP')
        return res.x if res.success else w0

# ==============================
# 完整策略主类（金融级专业版）
# ==============================
class GyroCompleteStrategy:
    def __init__(self):
        self.dynamics = GyroDynamics()
        self.evolver = GyroEvolve()
        self.opt = GyroPortfolioOpt()
        self.state_prev = None
        self.omega_prev = np.array([0.5, 0.5, 0.5])
        self.trade_history = []
        self.metrics_history = []
        self.equity_curve = [1.0]
        self.current_equity = 1.0
        self.max_equity = 1.0
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.holding_days = 0

    def calculate_all_metrics(self, returns, benchmark_returns=None):
        if benchmark_returns is None:
            benchmark_returns = np.zeros_like(returns)
        
        equity = 1 + np.cumsum(returns)
        max_equity = np.maximum.accumulate(equity)
        drawdown = (equity - max_equity) / max_equity
        max_dd = np.min(drawdown)

        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        k_ratio = (np.mean(returns) / np.std(returns)) / np.abs(max_dd) if np.abs(max_dd) > 0 and np.std(returns) > 0 else 0
        
        sortino = self.dynamics.indicator.calc_sortino(returns)
        omega = self.dynamics.indicator.calc_omega(returns)
        tail_ratio = self.dynamics.indicator.calc_tail_ratio(returns)
        rolling_stability = self.dynamics.indicator.calc_rolling_sharpe_stability(returns)
        info_ratio = self.dynamics.indicator.calc_information_ratio(returns, benchmark_returns)

        return StrategyMetrics(
            sharpe_ratio=sharpe,
            k_ratio=k_ratio,
            max_dd=max_dd,
            cap_util=min(len(self.trade_history) * 0.05, 1.0),
            sortino_ratio=sortino,
            omega_ratio=omega,
            rolling_sharpe_stability=rolling_stability,
            information_ratio=info_ratio,
            market_correlation=0.5,
            tail_ratio=tail_ratio,
            trade_frequency=len(self.trade_history) / max(len(returns)/252, 1),
            max_consecutive_losses=self.consecutive_losses,
            avg_holding_period=self.holding_days / max(len(self.trade_history), 1),
            recovery_time=0.0,
            lyapunov=0.0
        )

    def run_step(self, price_window, ret, cov, cvar, benchmark_ret=None):
        mom = self.dynamics.indicator.calc_momentum(price_window)
        vol = self.dynamics.indicator.calc_volatility(price_window)
        corr = np.corrcoef(price_window) if price_window.ndim > 1 else np.eye(3)

        Omega = self.dynamics.build_spin_matrix(mom, vol, corr)
        state_curr = np.array([mom, vol, np.mean(corr)])
        F = self.dynamics.calc_torque(state_curr, self.state_prev if self.state_prev is not None else state_curr)

        lyap = self.dynamics.calc_lyapunov(np.array([self.evolver.omega]))
        dE = self.dynamics.calc_energy_diff(self.evolver.omega, self.omega_prev)

        adjust = self.dynamics.gyro_response(F, self.evolver.omega, Omega)

        current_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
        metrics = self.calculate_all_metrics(current_returns, benchmark_ret)
        metrics.lyapunov = lyap
        self.metrics_history.append(metrics)

        converged, conditions = self.dynamics.is_converged(metrics, Omega)
        
        if not converged:
            reward = self.evolver.get_reward(metrics)
            new_omega = self.evolver.evolve_omega(state_curr, reward)
        else:
            new_omega = self.evolver.omega

        weights = self.opt.optimize(ret, cov, dE, cvar, metrics)

        self.state_prev = state_curr
        self.omega_prev = new_omega.copy()

        return weights, adjust, new_omega, lyap, dE, metrics, converged

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

        for i in range(20, len(prices)):
            price_window = prices[max(0, i-60):i]
            if i >= 21:
                p_slice = prices[max(0, i-20):i]
                ret = np.diff(p_slice) / p_slice[:-1] if len(p_slice) > 1 else np.array([0.001, 0.001, 0.001])
            else:
                ret = np.array([0.001, 0.001, 0.001])
            ret = np.resize(ret, 3)
            
            # P5: Ledoit-Wolf 协方差收缩估计
            if len(price_window) >= 30:
                raw_ret = np.resize(price_window[-30:], (3, 10))
                sc = np.cov(raw_ret, rowvar=False)
                T_d, N = sc.shape
                mu = np.trace(sc) / N
                d2 = np.sum((sc - mu * np.eye(N))**2) / N
                b2 = min(d2, np.sum(sc**2) / N)
                shrinkage = b2 / d2 if d2 > 0 else 0.0
                cov = shrinkage * mu * np.eye(N) + (1 - shrinkage) * sc
            else:
                cov = np.eye(3) * 0.01
            cvar = self.dynamics.indicator.calc_cvar(ret, 0.95)
            
            weights, adjust, new_omega, lyap, dE, metrics, converged = self.run_step(
                price_window, ret, cov, cvar
            )
            
            current_weights = weights
            position = np.sum(weights) * (equity / prices[i])
            
            if i > 0:
                daily_return = (prices[i] - prices[i-1]) / prices[i-1] * position / (equity / prices[i])
                equity *= (1 + daily_return)
                max_equity = max(max_equity, equity)
                
                self.trade_history.append({
                    'time': data.index[i],
                    'price': prices[i],
                    'position': position,
                    'return': daily_return,
                    'omega': new_omega.copy(),
                })

            results['equity_curve'].append(equity)
            results['weights'].append(weights)
            results['metrics'].append(metrics)
            results['omega_history'].append(new_omega.copy())

        total_return = (equity - initial_capital) / initial_capital * 100
        max_dd = (max_equity - equity) / max_equity * 100
        
        all_returns = np.array([t['return'] for t in self.trade_history])
        sharpe = np.mean(all_returns) / np.std(all_returns) * np.sqrt(252) if np.std(all_returns) > 0 else 0
        
        final_metrics = self.calculate_all_metrics(all_returns)
        final_metrics.max_dd = max_dd / 100
        final_metrics.sharpe_ratio = sharpe

        result_for_eval = {
            'returns': all_returns,
            'days': len(data),
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
# 一键启动策略
# ==============================
if __name__ == "__main__":
    strategy = GyroCompleteStrategy()
    print("✅ 陀螺恒稳进动矩阵自适应演进策略启动成功（金融级专业版）")
    
    # 生成测试数据
    np.random.seed(42)
    n_days = 500
    dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')
    prices = 100 + np.cumsum(np.random.randn(n_days) * 0.8)
    
    test_data = pd.DataFrame({
        'Open': prices,
        'High': prices + np.random.rand(n_days) * 2,
        'Low': prices - np.random.rand(n_days) * 2,
        'Close': prices,
        'Volume': np.random.randint(1000000, 10000000, n_days)
    }, index=dates)
    
    result = strategy.run_backtest(test_data, 100000)
    
    print(f"\n📊 回测结果:")
    print(f"   综合评分: {result['final_score']:.2f} ({result['grade']})")
    print(f"   总收益率: {result['total_return_pct']:.2f}%")
    print(f"   夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"   最大回撤: {result['max_drawdown_pct']:.2f}%")
    print(f"   交易次数: {result['total_trades']}")
    
    print("\n🏆 各指标得分:")
    for k, v in sorted(result['metric_scores'].items(), key=lambda x: x[1], reverse=True):
        print(f"   {k:<25}: {v:.1f}")
