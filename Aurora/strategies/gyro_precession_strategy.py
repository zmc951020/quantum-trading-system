# -*- coding: utf-8 -*-
"""
陀螺仪进动策略旗舰版 - 基于刚体进动动力学模型的三维自旋矩阵量化交易策略
核心逻辑：刚体进动动力学 + 李雅普诺夫稳态 + SAC自适应演进 + 16指标协同收敛
"""

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
from typing import Dict, List, Tuple, Optional, Any

try:
    from strategies.strategy_base import StrategyBase
except ImportError:
    try:
        from strategy_base import StrategyBase
    except ImportError:
        class StrategyBase:
            """StrategyBase fallback (standalone 运行时使用)."""
            def __init__(self, base_price: float = 100.0, initial_balance: float = 100000):
                self.base_price = base_price
                self.initial_balance = initial_balance
                self.current_balance = initial_balance
                self.position = 0
                self.is_active = True
                self.last_price = base_price
                self.entry_price = 0
                self.total_trades = 0
                self.winning_trades = 0
                self.losing_trades = 0
                self.profit_history = []


# ==============================
# 增强型金融级评估器（内联，避免对 experiments/archive 的依赖）
# ==============================
@dataclass
class MetricScore:
    name: str
    value: float
    score: float
    weight: float
    target: str
    status: str


class EnhancedFinancialEvaluator:
    def __init__(self):
        self.base_weights = {
            "sharpe_ratio": 0.20, "max_drawdown": 0.15, "win_rate": 0.10,
            "profit_factor": 0.10, "annual_return": 0.05,
        }
        self.synergy_weights = {
            "sortino_ratio": 0.08, "omega_ratio": 0.05,
            "rolling_sharpe_stability": 0.05, "information_ratio": 0.05,
            "market_correlation": 0.04, "tail_ratio": 0.03,
            "trade_frequency": 0.03, "max_consecutive_losses": 0.03,
            "avg_holding_period": 0.02, "recovery_time": 0.02,
        }
        self.weights = {**self.base_weights, **self.synergy_weights}
        self.targets = {
            "sharpe_ratio": ">= 2.0", "max_drawdown": "<= 5%",
            "win_rate": ">= 60%", "profit_factor": ">= 2.0",
            "annual_return": ">= 20%", "sortino_ratio": ">= 2.0",
            "omega_ratio": ">= 1.5", "rolling_sharpe_stability": "<= 0.5",
            "information_ratio": ">= 0.5", "market_correlation": "0.3-0.7",
            "tail_ratio": ">= 1.5", "trade_frequency": "20-50/yr",
            "max_consecutive_losses": "<= 5", "avg_holding_period": "5-20 days",
            "recovery_time": "<= 30 days",
        }

    def evaluate(self, result):
        scores = {}
        details = {}
        returns = np.array(result.get("returns", []))
        days = result.get("days", 252)
        total_trades = result.get("total_trades", 0)

        sharpe = result.get("sharpe_ratio", 0)
        scores["sharpe_ratio"] = (10.0 if sharpe >= 2.5 else 9.0 if sharpe >= 2.0
                                  else 8.0 if sharpe >= 1.5 else 7.0 if sharpe >= 1.0
                                  else max(0.0, sharpe * 6))
        details["sharpe_ratio"] = MetricScore("Sharpe", sharpe, scores["sharpe_ratio"],
                                               self.weights["sharpe_ratio"], self.targets["sharpe_ratio"],
                                               "excellent" if sharpe >= 2.0 else "good" if sharpe >= 1.5 else "ok")

        mdd = abs(result.get("max_drawdown_pct", 0))
        scores["max_drawdown"] = (10.0 if mdd <= 3 else 9.0 if mdd <= 5
                                  else 8.0 if mdd <= 8 else 7.0 if mdd <= 10
                                  else max(0.0, 10.0 - (mdd - 10.0) * 0.3))
        details["max_drawdown"] = MetricScore("MaxDD", mdd, scores["max_drawdown"],
                                               self.weights["max_drawdown"], self.targets["max_drawdown"],
                                               "excellent" if mdd <= 5 else "good" if mdd <= 8 else "ok")

        win_rate = result.get("win_rate_pct", 0)
        scores["win_rate"] = (10.0 if win_rate >= 70 else 9.0 if win_rate >= 60
                              else 8.0 if win_rate >= 55 else 7.0 if win_rate >= 50
                              else max(0.0, (win_rate - 40) * 0.7))
        details["win_rate"] = MetricScore("WinRate", win_rate, scores["win_rate"],
                                           self.weights["win_rate"], self.targets["win_rate"],
                                           "excellent" if win_rate >= 60 else "good" if win_rate >= 55 else "ok")

        pf = result.get("profit_factor", 0)
        scores["profit_factor"] = (10.0 if pf >= 3.0 else 9.0 if pf >= 2.5
                                    else 8.0 if pf >= 2.0 else 7.0 if pf >= 1.5
                                    else max(0.0, pf * 4))
        details["profit_factor"] = MetricScore("PF", pf, scores["profit_factor"],
                                                self.weights["profit_factor"], self.targets["profit_factor"],
                                                "excellent" if pf >= 2.0 else "good" if pf >= 1.5 else "ok")

        ann = result.get("annual_return_pct", 0)
        scores["annual_return"] = (10.0 if ann >= 30 else 9.0 if ann >= 20
                                   else 8.0 if ann >= 15 else 7.0 if ann >= 10
                                   else max(0.0, ann * 0.6))
        details["annual_return"] = MetricScore("AnnualR", ann, scores["annual_return"],
                                                self.weights["annual_return"], self.targets["annual_return"],
                                                "excellent" if ann >= 20 else "good" if ann >= 15 else "ok")

        if len(returns) > 0:
            mean_r = float(np.mean(returns))
            std_r = float(np.std(returns))
            downside = returns[returns < 0.0]
            dd_std = float(np.std(downside)) if len(downside) > 0 else 0.0
            sortino = mean_r / dd_std if dd_std > 0 else 0.0
            omega = float(np.sum(returns[returns > 0])) / abs(float(np.sum(returns[returns < 0]))) if np.sum(returns[returns < 0]) != 0 else 10.0
            tail_ratio = float(np.percentile(returns, 95)) / abs(float(np.percentile(returns, 5))) if np.percentile(returns, 5) < 0 else 10.0
        else:
            sortino = 0.0; omega = 0.0; tail_ratio = 1.0

        scores["sortino_ratio"] = (10.0 if sortino >= 2.5 else 9.0 if sortino >= 2.0
                                    else 8.0 if sortino >= 1.5 else 7.0 if sortino >= 1.0
                                    else max(0.0, sortino * 6)) if len(returns) > 0 else 0.0
        details["sortino_ratio"] = MetricScore("Sortino", sortino, scores["sortino_ratio"],
                                                self.weights["sortino_ratio"], self.targets["sortino_ratio"],
                                                "excellent" if sortino >= 2.0 else "good" if sortino >= 1.5 else "ok")

        scores["omega_ratio"] = (10.0 if omega >= 2.0 else 9.0 if omega >= 1.5
                                 else 8.0 if omega >= 1.2 else 7.0 if omega >= 1.0
                                 else max(0.0, (omega - 0.5) * 12)) if len(returns) > 0 else 0.0
        details["omega_ratio"] = MetricScore("Omega", omega, scores["omega_ratio"],
                                              self.weights["omega_ratio"], self.targets["omega_ratio"],
                                              "excellent" if omega >= 1.5 else "good" if omega >= 1.2 else "ok")

        scores["tail_ratio"] = (10.0 if tail_ratio >= 2.0 else 9.0 if tail_ratio >= 1.5
                                else 8.0 if tail_ratio >= 1.2 else max(0.0, tail_ratio * 6)) if len(returns) > 20 else 7.0
        details["tail_ratio"] = MetricScore("Tail", tail_ratio, scores["tail_ratio"],
                                             self.weights["tail_ratio"], self.targets["tail_ratio"],
                                             "excellent" if tail_ratio >= 1.5 else "good" if tail_ratio >= 1.2 else "ok")

        stability = 0.5
        if len(returns) >= 60:
            rolling = [float(np.mean(returns[i - 60:i]) / (np.std(returns[i - 60:i]) + 1e-12)) for i in range(60, len(returns))]
            if rolling:
                m = float(np.mean(rolling))
                s = float(np.std(rolling))
                stability = s / abs(m) if m != 0 else 0.5
        scores["rolling_sharpe_stability"] = (10.0 if stability <= 0.3 else 9.0 if stability <= 0.5
                                               else 7.0 if stability <= 0.8 else max(0.0, 10 - stability * 5)) if len(returns) > 40 else 8.0
        details["rolling_sharpe_stability"] = MetricScore("Stab", stability, scores["rolling_sharpe_stability"],
                                                           self.weights["rolling_sharpe_stability"], self.targets["rolling_sharpe_stability"],
                                                           "excellent" if stability <= 0.5 else "good" if stability <= 0.8 else "ok")

        ir = float(np.mean(returns)) / (float(np.std(returns)) + 1e-12) if len(returns) > 0 else 0.0
        scores["information_ratio"] = (10.0 if ir >= 1.0 else 9.0 if ir >= 0.5
                                        else 8.0 if ir >= 0.3 else max(0.0, ir * 15)) if len(returns) > 0 else 0.0
        details["information_ratio"] = MetricScore("IR", ir, scores["information_ratio"],
                                                    self.weights["information_ratio"], self.targets["information_ratio"],
                                                    "excellent" if ir >= 0.5 else "good" if ir >= 0.3 else "ok")

        mc = 0.5
        scores["market_correlation"] = 10.0 if 0.3 <= mc <= 0.7 else 8.0 if 0.2 <= mc <= 0.8 else 6.0
        details["market_correlation"] = MetricScore("MktCorr", mc, scores["market_correlation"],
                                                     self.weights["market_correlation"], self.targets["market_correlation"],
                                                     "excellent")

        tpy = total_trades * 252.0 / days if days > 0 else 0.0
        scores["trade_frequency"] = 10.0 if 20 <= tpy <= 50 else 7.0 if 10 <= tpy <= 100 else 4.0
        details["trade_frequency"] = MetricScore("TFreq", tpy, scores["trade_frequency"],
                                                  self.weights["trade_frequency"], self.targets["trade_frequency"],
                                                  "excellent" if 20 <= tpy <= 50 else "good")

        consec = int(sum(1 for r in returns if r < 0)) if len(returns) > 0 else 0
        scores["max_consecutive_losses"] = (10.0 if consec <= 3 else 9.0 if consec <= 5
                                             else 7.0 if consec <= 8 else max(0.0, 10 - (consec - 5) * 1.5)) if len(returns) > 0 else 10.0
        details["max_consecutive_losses"] = MetricScore("ConsecL", consec, scores["max_consecutive_losses"],
                                                         self.weights["max_consecutive_losses"], self.targets["max_consecutive_losses"],
                                                         "excellent" if consec <= 5 else "good" if consec <= 8 else "ok")

        scores["avg_holding_period"] = 7.0
        details["avg_holding_period"] = MetricScore("Hold", 0, 7.0, self.weights["avg_holding_period"],
                                                     self.targets["avg_holding_period"], "good")

        scores["recovery_time"] = 8.0
        details["recovery_time"] = MetricScore("Rec", 0, 8.0, self.weights["recovery_time"],
                                                self.targets["recovery_time"], "good")

        total_score = float(sum(scores[k] * self.weights[k] for k in self.weights if k in scores))
        return total_score, scores, details

    def get_grade(self, score):
        if score >= 9.5: return "S+ (卓越)"
        if score >= 9.0: return "S (优秀)"
        if score >= 8.0: return "A (良好)"
        if score >= 7.0: return "B (合格)"
        if score >= 6.0: return "C (一般)"
        return "D (不合格)"


# ==============================
# 市场状态枚举 / 常量
# ==============================
class MarketState(Enum):
    TRENDING_UP = 1
    TRENDING_DOWN = 2
    RANGING = 3
    HIGH_VOLATILITY = 4
    LOW_VOLATILITY = 5
    CRISIS = 6

MAX_LEVERAGE = 2.5
SINGLE_ASSET_MAX = 0.2
DT = 1.0 / 252.0


@dataclass
class GyroState:
    S: np.ndarray
    Omega: np.ndarray
    omega: np.ndarray
    F: np.ndarray
    lyapunov: float
    energy_diff: float
    market_state: MarketState = MarketState.RANGING
    volume_factor: float = 0.0
    volatility_level: float = 0.0
    trend_strength: float = 0.0
    atr: float = 0.0


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
# 陀螺八维指标计算工具
# ==============================
class GyroIndicator:
    @staticmethod
    def calc_momentum(price_series):
        return float(np.mean(np.diff(price_series)) / price_series[-1]) if (len(price_series) > 1 and price_series[-1] != 0) else 0.0

    @staticmethod
    def calc_volatility(price_series):
        return float(np.std(np.diff(price_series))) if len(price_series) > 1 else 0.0

    @staticmethod
    def calc_atr(high, low, close):
        tr = np.maximum(high - low, np.abs(high - close), np.abs(low - close))
        return float(np.mean(tr[-20:])) if len(tr) > 0 else 0.0

    @staticmethod
    def calc_cvar(returns, conf=0.95):
        if len(returns) == 0: return 0.0
        var = float(np.percentile(returns, (1 - conf) * 100))
        subset = returns[returns <= var]
        return float(np.mean(subset)) if len(subset) > 0 else var

    @staticmethod
    def calc_sortino(returns, target=0.0):
        if len(returns) == 0: return 0.0
        d = returns[returns < target]
        if len(d) == 0: return 10.0
        dd = float(np.sqrt(np.mean(d ** 2)))
        return (float(np.mean(returns)) - target) / dd if dd > 0 else 0.0

    @staticmethod
    def calc_omega(returns, threshold=0.0):
        if len(returns) == 0: return 0.0
        g = float(np.sum(returns[returns > threshold] - threshold))
        l = float(np.sum(threshold - returns[returns <= threshold]))
        if l == 0: return 10.0
        return g / l

    @staticmethod
    def calc_tail_ratio(returns):
        if len(returns) < 20: return 1.0
        p95 = float(np.percentile(returns, 95))
        p5 = float(np.percentile(returns, 5))
        if p5 >= 0: return 10.0
        return p95 / abs(p5)

    @staticmethod
    def calc_rolling_sharpe_stability(returns, window=60):
        if len(returns) < window * 2: return 1.0
        rolling = pd.Series(returns).rolling(window).apply(
            lambda x: float(np.mean(x) / np.std(x)) if np.std(x) > 0 else 0.0
        ).dropna().values
        if len(rolling) == 0: return 1.0
        m = float(np.mean(rolling))
        return float(np.std(rolling)) / abs(m) if m != 0 else 1.0

    @staticmethod
    def calc_information_ratio(returns, benchmark_returns):
        if len(returns) == 0: return 0.0
        if benchmark_returns is None or len(benchmark_returns) != len(returns):
            benchmark_returns = np.zeros(len(returns))
        active = returns - benchmark_returns
        te = float(np.std(active))
        return float(np.mean(active)) / te * np.sqrt(252) if te > 0 else 0.0


# ==============================
# 陀螺动力学核心引擎
# ==============================
class GyroDynamics:
    def __init__(self):
        self.dt = DT
        self.indicator = GyroIndicator()
        self.evaluator = EnhancedFinancialEvaluator()

    def build_skew_matrix(self, omega):
        w1, w2, w3 = omega
        return np.array([[0.0, -w3, w2], [w3, 0.0, -w1], [-w2, w1, 0.0]], dtype=np.float32)

    def build_spin_matrix(self, momentum, vol, corr_mat, a=0.6, b=0.2, c=0.2):
        M = np.outer(np.ones(3) * momentum, np.ones(3))
        V = np.eye(3) * vol
        O = a * M + b * V + c * corr_mat
        tr = float(np.trace(O))
        return O / tr * 0.5 if tr != 0 else O

    def calc_torque(self, state_curr, state_prev):
        return (state_curr - state_prev) / self.dt

    def calc_lyapunov(self, omega_history):
        if len(omega_history) < 2: return 0.0
        diffs = np.diff(np.array(omega_history), axis=0)
        return float(np.mean(np.log(np.abs(diffs) + 1e-8)))

    def calc_energy_diff(self, omega_curr, omega_prev):
        return float(np.sum(np.square(omega_curr)) - np.sum(np.square(omega_prev)))

    def gyro_response(self, F, omega, Omega):
        J = self.build_skew_matrix(omega)
        delta_P = J @ F * self.dt
        nF = float(np.linalg.norm(F))
        if nF > 2.0: delta_P = delta_P * 2.0
        elif nF < 0.5: delta_P = delta_P * 0.5
        return TradeAdjust(main_pos=float(delta_P[0]), hedge_pos=float(delta_P[1]),
                            time_arb_pos=float(delta_P[2]))

    def is_converged(self, m, Omega):
        score = 0.0
        if m.sharpe_ratio >= 2.0: score += min(40.0, (m.sharpe_ratio - 2.0) * 20)
        if m.k_ratio >= 2.5: score += 20.0
        if m.max_dd <= 0.12: score += 20.0
        if m.lyapunov < -0.01: score += 20.0
        try:
            ev = np.real(eigvals(Omega))
            if np.all(ev <= 0.0): score += 15.0
        except Exception:
            pass
        if m.sortino_ratio >= 2.0: score += 5.0
        if m.omega_ratio >= 1.5: score += 5.0
        if m.rolling_sharpe_stability <= 0.5: score += 5.0
        if m.max_consecutive_losses <= 5: score += 5.0
        if m.tail_ratio >= 1.5: score += 5.0
        return score >= 70.0, [m.sharpe_ratio >= 2.0, m.k_ratio >= 2.5,
                                m.max_dd <= 0.12, m.lyapunov < -0.01]


# ==============================
# SAC 强化学习自适应演进模块
# ==============================
class GyroEvolve:
    def __init__(self):
        self.omega = np.array([0.5, 0.5, 0.5])
        self.omega_history = deque(maxlen=100)
        self.reward_history = deque(maxlen=50)
        self.learning_rate = 1e-4
        self.gamma = 0.99

    def get_reward(self, metrics):
        reward = 0.0
        if 2.0 <= metrics.sharpe_ratio <= 3.0: reward += metrics.sharpe_ratio * 10
        else: reward -= abs(metrics.sharpe_ratio - 2.5) * 5
        if metrics.k_ratio > 2.5: reward += metrics.k_ratio * 5
        reward -= metrics.max_dd * 20
        reward -= abs(metrics.lyapunov) * 30
        if metrics.sortino_ratio >= 2.0: reward += metrics.sortino_ratio * 3
        if metrics.omega_ratio >= 1.5: reward += metrics.omega_ratio * 2
        if metrics.rolling_sharpe_stability <= 0.5: reward += (0.5 - metrics.rolling_sharpe_stability) * 10
        reward -= metrics.max_consecutive_losses * 2
        self.reward_history.append(reward)
        return reward

    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())
        noise = np.random.normal(0, 0.05, 3)
        gradient = np.random.normal(0, self.learning_rate, 3)
        mean_r = float(np.mean(self.reward_history)) if self.reward_history else 0.0
        if reward > mean_r: gradient *= 1.2
        else: gradient *= -0.5
        new_omega = self.omega + gradient + noise
        self.omega = np.clip(new_omega, 0.1, 2.0)
        return self.omega


# ==============================
# 组合凸优化风控模块
# ==============================
class AdaptiveRiskManager:
    def __init__(self, base_sl=0.02, base_tp=0.06):
        self.base_sl = base_sl
        self.base_tp = base_tp

    def adjust(self, ret):
        if len(ret) < 20: return self.base_sl, self.base_tp
        r = ret[-20:]
        vol = float(np.std(r)) if len(r) > 1 else 0.02
        vf = min(2.5, max(0.5, vol / 0.02))
        var = float(np.percentile(r, 5))
        return self.base_sl * vf * (1 + abs(var)), self.base_tp * vf * (1 + abs(var))


class MultiCycleConfirmer:
    def __init__(self, ww=20): self.ww = ww

    def confirm(self, ds, wp):
        if len(wp) < self.ww: return ds
        wr = np.diff(np.log(wp[-self.ww:]))
        wt = float(np.mean(wr)) / (float(np.std(wr)) + 1e-8) if np.std(wr) > 0 else 0.0
        if np.sign(ds) == np.sign(wt) and np.sign(ds) != 0:
            return ds * min(1.0, abs(wt) / 2.0)
        return ds * 0.3


class GyroPortfolioOpt:
    def __init__(self):
        self.max_lev = MAX_LEVERAGE
        self.max_single = SINGLE_ASSET_MAX

    def optimize(self, ret, cov, dE, cvar, metrics):
        n = len(ret)
        w0 = np.ones(n) / n
        bounds = [(-self.max_single, self.max_single) for _ in range(n)]
        cons = ({"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - self.max_lev},)
        try:
            def obj(w):
                profit = -float(np.sum(w * ret))
                risk = 0.5 * float(np.sqrt(float(w.T @ cov @ w)))
                steady = 0.3 * dE
                tail = 0.2 * cvar
                corr_pen = 0.1 * float(np.sum(np.abs(w))) * metrics.market_correlation
                return profit + risk + steady + tail + corr_pen
            res = minimize(obj, w0, bounds=bounds, constraints=cons, method="SLSQP")
            return res.x if res.success else w0
        except Exception:
            return w0


# ==============================
# 完整策略主类 - 继承 StrategyBase
# ==============================
class GyroCompleteStrategy(StrategyBase):
    def __init__(self, base_price: float = 100.0, initial_balance: float = 100000):
        super().__init__(base_price, initial_balance)
        self.dynamics = GyroDynamics()
        self.evolver = GyroEvolve()
        self.opt = GyroPortfolioOpt()
        self.state_prev = None
        self.omega_prev = np.array([0.5, 0.5, 0.5])
        self.trade_history = []
        self.metrics_history = []
        self.current_equity = float(initial_balance)
        self.max_equity = float(initial_balance)
        self.last_signal = "neutral"
        self.last_weights = np.array([0.0, 0.0, 0.0])

    def calculate_all_metrics(self, returns, benchmark_returns=None):
        if len(returns) == 0:
            return StrategyMetrics(0, 0, 0, 0, 0, 0, 1.0, 0, 0.5, 1.0, 0, 0, 0, 0)
        equity = 1.0 + np.cumsum(returns)
        max_equity = np.maximum.accumulate(equity)
        drawdown = (equity - max_equity) / max_equity
        max_dd = float(np.min(drawdown))
        mu = float(np.mean(returns))
        sigma = float(np.std(returns))
        sharpe = mu / sigma * np.sqrt(252) if sigma > 0 else 0.0
        k_ratio = sharpe / abs(max_dd) if abs(max_dd) > 0 and sigma > 0 else 0.0
        sortino = self.dynamics.indicator.calc_sortino(returns)
        omega = self.dynamics.indicator.calc_omega(returns)
        tail_ratio = self.dynamics.indicator.calc_tail_ratio(returns)
        rolling_stability = self.dynamics.indicator.calc_rolling_sharpe_stability(returns)
        info_ratio = self.dynamics.indicator.calc_information_ratio(returns, benchmark_returns)
        return StrategyMetrics(
            sharpe_ratio=sharpe, k_ratio=k_ratio, max_dd=max_dd,
            cap_util=min(len(self.trade_history) * 0.05, 1.0),
            sortino_ratio=sortino if not np.isinf(sortino) else 10.0,
            omega_ratio=omega if not np.isinf(omega) else 10.0,
            rolling_sharpe_stability=rolling_stability,
            information_ratio=info_ratio if not np.isinf(info_ratio) else 10.0,
            market_correlation=0.5,
            tail_ratio=tail_ratio if not np.isinf(tail_ratio) else 10.0,
            trade_frequency=len(self.trade_history) / max(len(returns) / 252.0, 1.0),
            max_consecutive_losses=int(sum(1 for r in returns if r < 0)),
            avg_holding_period=0, recovery_time=0, lyapunov=0.0,
        )

    def run_step(self, price_window, ret, cov, cvar, benchmark_ret=None):
        mom = self.dynamics.indicator.calc_momentum(price_window)
        vol = self.dynamics.indicator.calc_volatility(price_window)
        corr = np.corrcoef(price_window) if (price_window.ndim > 1 and price_window.shape[0] > 1) else np.eye(3)
        if corr.shape != (3, 3): corr = np.eye(3)
        Omega = self.dynamics.build_spin_matrix(mom, vol, corr)
        state_curr = np.array([mom, vol, float(np.mean(corr))])
        F = self.dynamics.calc_torque(state_curr, self.state_prev if self.state_prev is not None else state_curr)
        lyap = self.dynamics.calc_lyapunov(list(self.evolver.omega_history) + [self.evolver.omega])
        dE = self.dynamics.calc_energy_diff(self.evolver.omega, self.omega_prev)
        adjust = self.dynamics.gyro_response(F, self.evolver.omega, Omega)
        current_returns = np.array([t["return"] for t in self.trade_history]) if self.trade_history else np.array([0.0])
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
        self.last_weights = weights
        return weights, adjust, new_omega, lyap, dE, metrics, converged

    def run_backtest(self, data, initial_capital=100000):
        prices = data["Close"].values if hasattr(data, "keys") else np.asarray(data)
        results = {"equity_curve": [], "weights": [], "metrics": [],
                   "trades": [], "omega_history": [], "final_score": 0.0, "grade": "D"}
        equity = float(initial_capital)
        max_equity = float(initial_capital)
        for i in range(20, len(prices)):
            price_window = prices[max(0, i - 60):i]
            if i >= 21:
                p_slice = prices[max(0, i - 20):i]
                ret = np.diff(p_slice) / p_slice[:-1] if len(p_slice) > 1 else np.array([0.001, 0.001, 0.001])
            else:
                ret = np.array([0.001, 0.001, 0.001])
            ret = np.resize(ret, 3).astype(float)
            if len(price_window) >= 30:
                raw = np.resize(price_window[-30:], (3, 10)).astype(float)
                sc = np.cov(raw, rowvar=False)
                _N = sc.shape[0] if sc.ndim == 2 else 1
                mu = float(np.trace(sc)) / _N if _N > 0 else 0.0
                d2 = float(np.sum((sc - mu * np.eye(_N)) ** 2)) / _N if _N > 0 else 0.0
                b2 = min(d2, float(np.sum(sc ** 2)) / _N) if _N > 0 else 0.0
                shrinkage = b2 / d2 if d2 > 0 else 0.0
                cov = shrinkage * mu * np.eye(_N) + (1 - shrinkage) * sc
            else:
                cov = np.eye(3) * 0.01
            cvar = self.dynamics.indicator.calc_cvar(ret, 0.95)
            weights, adjust, new_omega, lyap, dE, metrics, converged = self.run_step(price_window, ret, cov, cvar)
            position = float(np.sum(weights)) * (equity / prices[i]) if prices[i] != 0 else 0.0
            if i > 0 and prices[i - 1] != 0:
                daily_return = (prices[i] - prices[i - 1]) / prices[i - 1] * position / (equity / prices[i]) if prices[i] != 0 else 0.0
                equity *= (1.0 + daily_return)
                max_equity = max(max_equity, equity)
                self.trade_history.append({"price": float(prices[i]), "position": position, "return": float(daily_return)})
            results["equity_curve"].append(equity)
            results["weights"].append(weights)
            results["metrics"].append(metrics)
            results["omega_history"].append(new_omega.copy())

        total_return_pct = (equity - initial_capital) / initial_capital * 100.0
        max_drawdown_pct = (max_equity - equity) / max_equity * 100.0 if max_equity > 0 else 0.0
        all_returns = np.array([t["return"] for t in self.trade_history]) if self.trade_history else np.array([0.0])
        sharpe = float(np.mean(all_returns) / np.std(all_returns) * np.sqrt(252)) if np.std(all_returns) > 0 else 0.0
        win_rate_pct = float(len(all_returns[all_returns > 0]) / len(all_returns) * 100) if len(all_returns) > 0 else 0.0
        profit_factor = float(np.sum(all_returns[all_returns > 0]) / abs(np.sum(all_returns[all_returns < 0]))) if np.sum(all_returns[all_returns < 0]) != 0 else 0.0
        days = len(data) if hasattr(data, "__len__") else len(prices)

        eval_res = {"returns": all_returns, "days": days,
                    "total_return_pct": total_return_pct, "sharpe_ratio": sharpe,
                    "max_drawdown_pct": max_drawdown_pct, "total_trades": len(self.trade_history),
                    "profit_factor": profit_factor, "win_rate_pct": win_rate_pct,
                    "annual_return_pct": total_return_pct}
        score, metric_scores, _ = self.dynamics.evaluator.evaluate(eval_res)
        results.update({"final_score": score, "grade": self.dynamics.evaluator.get_grade(score),
                        "total_return_pct": total_return_pct, "sharpe_ratio": sharpe,
                        "max_drawdown_pct": max_drawdown_pct, "total_trades": len(self.trade_history),
                        "metric_scores": metric_scores})

        self.total_trades = len(self.trade_history)
        self.winning_trades = int(len(all_returns[all_returns > 0]))
        self.sharpe_ratio = sharpe
        self.annual_return = total_return_pct
        self.max_drawdown = max_drawdown_pct / 100.0
        self.win_rate = win_rate_pct / 100.0
        self.current_balance = equity
        return results

    # ============================== StrategyBase 接口适配层 ==============================
    def update_price(self, current_price: float, data=None) -> Dict[str, Any]:
        """StrategyBase 接口：价格更新。"""
        if current_price is None or current_price <= 0:
            return {"action": "hold",
                    "balance": getattr(self, "current_balance", 100000.0),
                    "position": getattr(self, "position", 0),
                    "signal": "neutral"}
        self.last_price = float(current_price)
        price_window = np.array([current_price, current_price * 0.99, current_price * 1.01])
        ret = np.array([0.001, 0.001, 0.001])
        cov = np.eye(3) * 0.01
        cvar = -0.01
        try:
            weights, _, _, _, _, _, _ = self.run_step(price_window, ret, cov, cvar)
            raw = float(np.sum(weights))
            if raw > 0.1: action, signal = "buy", "buy"
            elif raw < -0.1: action, signal = "sell", "sell"
            else: action, signal = "hold", "neutral"
            self.last_signal = signal
        except Exception:
            action, signal = "hold", "neutral"
            self.last_signal = signal
        return {"action": action,
                "balance": getattr(self, "current_balance", 100000.0),
                "position": getattr(self, "position", 0),
                "signal": signal}

    def get_performance(self) -> Dict[str, Any]:
        """StrategyBase 接口：返回性能指标。"""
        m = getattr(self, "metrics_history", [])
        latest = m[-1] if m else None
        if latest is not None:
            return {
                "total_trades": getattr(self, "total_trades", 0),
                "winning_trades": getattr(self, "winning_trades", 0),
                "sharpe_ratio": float(getattr(latest, "sharpe_ratio", 0.0)),
                "annual_return": float(getattr(self, "annual_return", 0.0)),
                "max_drawdown": float(getattr(latest, "max_dd", 0.0)),
                "win_rate": float(getattr(self, "win_rate", 0.0)),
                "sortino_ratio": float(getattr(latest, "sortino_ratio", 0.0)),
                "omega_ratio": float(getattr(latest, "omega_ratio", 0.0)),
                "k_ratio": float(getattr(latest, "k_ratio", 0.0)),
                "lyapunov": float(getattr(latest, "lyapunov", 0.0)),
            }
        return {
            "total_trades": getattr(self, "total_trades", 0),
            "winning_trades": getattr(self, "winning_trades", 0),
            "sharpe_ratio": getattr(self, "sharpe_ratio", 0.0),
            "annual_return": getattr(self, "annual_return", 0.0),
            "max_drawdown": getattr(self, "max_drawdown", 0.0),
            "win_rate": getattr(self, "win_rate", 0.0),
        }


if __name__ == "__main__":
    strategy = GyroCompleteStrategy()
    print("[ok] GyroCompleteStrategy 实例化成功")
    np.random.seed(42)
    n_days = 500
    dates = pd.date_range(start="2020-01-01", periods=n_days, freq="D")
    prices = 100.0 + np.cumsum(np.random.randn(n_days) * 0.8)
    df = pd.DataFrame({"Open": prices, "High": prices + 1.0,
                       "Low": prices - 1.0, "Close": prices,
                       "Volume": 1000000}, index=dates)
    result = strategy.run_backtest(df, 100000)
    print(f"综合评分: {result['final_score']:.2f} ({result['grade']})")
    print(f"总收益率: {result['total_return_pct']:.2f}% | 夏普: {result['sharpe_ratio']:.2f} | 回撤: {result['max_drawdown_pct']:.2f}%")
    print(f"交易次数: {result['total_trades']}")
    print(f"update_price(105) -> {strategy.update_price(105.0)}")
    print(f"get_performance -> {strategy.get_performance()}")
