#!/usr/bin/env python3
"""
蒙特卡洛检验模块（Monte Carlo Validator）

Vibe-Trading 系统的统计检验引擎，提供：
  - 蒙特卡洛模拟：生成随机价格路径，评估策略稳健性
  - VaR/CVaR 计算：在险价值与条件在险价值
  - 压力测试：极端市场情景模拟
  - 滚动验证：滚动窗口交叉验证策略
  - 过拟合检测：样本内/外性能对比

依赖：numpy
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 蒙特卡洛验证器
# ============================================================

class MonteCarloValidator:
    """蒙特卡洛统计检验引擎

    对策略收益序列进行全面的统计检验，包括模拟、风险度量、
    压力测试、滚动验证和过拟合检测。
    """

    def __init__(self, random_seed: Optional[int] = None):
        """
        Args:
            random_seed: 随机种子，确保结果可复现
        """
        self._rng = np.random.RandomState(random_seed or 42)

    # ============================================================
    # 蒙特卡洛模拟
    # ============================================================

    def run_simulation(self, returns: np.ndarray,
                       n_simulations: int = 1000,
                       horizon: int = 252) -> Dict[str, Any]:
        """蒙特卡洛模拟

        基于历史收益率分布，生成多条模拟路径，评估策略表现。

        Args:
            returns: 日收益率序列（长度 >= 20）
            n_simulations: 模拟次数
            horizon: 模拟天数（默认252个交易日=1年）

        Returns:
            dict: {success, paths, final_values, confidence_interval, statistics, ...}
        """
        try:
            rt = np.asarray(returns, dtype=np.float64)
            rt = rt[~np.isnan(rt)]

            if len(rt) < 20:
                return {"success": False, "error": "收益率数据不足（至少需要20个数据点）"}

            mu = np.mean(rt)
            sigma = np.std(rt)

            # 生成模拟路径
            paths = np.zeros((n_simulations, horizon + 1))
            paths[:, 0] = 1.0

            for i in range(1, horizon + 1):
                random_returns = self._rng.normal(mu, sigma, n_simulations)
                paths[:, i] = paths[:, i - 1] * (1 + random_returns)

            final_values = paths[:, -1]
            total_returns = (final_values - 1) * 100

            # 置信区间
            ci_lower = np.percentile(total_returns, 5)
            ci_upper = np.percentile(total_returns, 95)
            median_return = np.median(total_returns)

            # 统计指标
            statistics = {
                "mean_return": round(float(np.mean(total_returns)), 4),
                "median_return": round(float(median_return), 4),
                "std_return": round(float(np.std(total_returns)), 4),
                "min_return": round(float(np.min(total_returns)), 4),
                "max_return": round(float(np.max(total_returns)), 4),
                "positive_probability": round(float(np.mean(total_returns > 0)), 4),
                "ci_95_lower": round(float(ci_lower), 4),
                "ci_95_upper": round(float(ci_upper), 4),
            }

            # 最大回撤分布
            max_drawdowns = []
            for p in paths:
                peak = np.maximum.accumulate(p)
                dd = (p - peak) / peak
                max_drawdowns.append(float(np.min(dd)))
            max_drawdowns = np.array(max_drawdowns)

            statistics["mean_max_drawdown"] = round(float(np.mean(max_drawdowns)), 4)
            statistics["worst_drawdown"] = round(float(np.min(max_drawdowns)), 4)

            return {
                "success": True,
                "n_simulations": n_simulations,
                "horizon": horizon,
                "final_values": total_returns.tolist(),
                "confidence_interval": {
                    "lower_5pct": round(float(ci_lower), 4),
                    "upper_95pct": round(float(ci_upper), 4),
                    "median": round(float(median_return), 4),
                },
                "statistics": statistics,
                "input_stats": {
                    "mean_daily_return": round(float(mu), 6),
                    "std_daily_return": round(float(sigma), 6),
                    "annualized_return": round(float(mu * 252), 4),
                    "annualized_volatility": round(float(sigma * np.sqrt(252)), 4),
                },
            }
        except Exception as e:
            logger.error(f"蒙特卡洛模拟失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # VaR / CVaR
    # ============================================================

    def calculate_var(self, returns: np.ndarray,
                      confidence: float = 0.95) -> float:
        """VaR计算（Value at Risk）

        在给定置信水平下，计算最大可能损失。

        Args:
            returns: 日收益率序列
            confidence: 置信水平（默认0.95）

        Returns:
            float: VaR值（负值表示损失）
        """
        rt = np.asarray(returns, dtype=np.float64)
        rt = rt[~np.isnan(rt)]
        if len(rt) < 10:
            return 0.0
        var = np.percentile(rt, (1 - confidence) * 100)
        return float(var)

    def calculate_cvar(self, returns: np.ndarray,
                       confidence: float = 0.95) -> float:
        """CVaR计算（Conditional Value at Risk / Expected Shortfall）

        在给定置信水平下，超过VaR的平均损失。

        Args:
            returns: 日收益率序列
            confidence: 置信水平（默认0.95）

        Returns:
            float: CVaR值（负值表示损失）
        """
        rt = np.asarray(returns, dtype=np.float64)
        rt = rt[~np.isnan(rt)]
        if len(rt) < 10:
            return 0.0
        var = self.calculate_var(rt, confidence)
        cvar = np.mean(rt[rt <= var])
        return float(cvar)

    def calculate_var_cvar_full(self, returns: np.ndarray,
                                confidence: float = 0.95) -> Dict[str, Any]:
        """完整的VaR/CVaR分析报告

        Args:
            returns: 日收益率序列
            confidence: 置信水平

        Returns:
            dict: {success, var, cvar, annualized_var, annualized_cvar, ...}
        """
        try:
            rt = np.asarray(returns, dtype=np.float64)
            rt = rt[~np.isnan(rt)]

            if len(rt) < 10:
                return {"success": False, "error": "数据不足"}

            var_daily = self.calculate_var(rt, confidence)
            cvar_daily = self.calculate_cvar(rt, confidence)

            # 年化
            var_annual = var_daily * np.sqrt(252)
            cvar_annual = cvar_daily * np.sqrt(252)

            # 历史模拟法的多个置信水平
            var_levels = {}
            for level in [0.90, 0.95, 0.975, 0.99]:
                v = np.percentile(rt, (1 - level) * 100)
                c = np.mean(rt[rt <= v])
                var_levels[f"var_{int(level*100)}pct"] = round(float(v), 6)
                var_levels[f"cvar_{int(level*100)}pct"] = round(float(c), 6)

            return {
                "success": True,
                "confidence": confidence,
                "var_daily": round(float(var_daily), 6),
                "cvar_daily": round(float(cvar_daily), 6),
                "var_annualized": round(float(var_annual), 6),
                "cvar_annualized": round(float(cvar_annual), 6),
                "var_by_levels": var_levels,
                "sample_count": len(rt),
                "skewness": round(float(self._safe_skewness(rt)), 4),
                "kurtosis": round(float(self._safe_kurtosis(rt)), 4),
            }
        except Exception as e:
            logger.error(f"VaR/CVaR计算失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 压力测试
    # ============================================================

    def stress_test(self, returns: np.ndarray,
                    scenarios: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
        """压力测试

        模拟极端市场情景下的策略表现。

        Args:
            returns: 日收益率序列
            scenarios: 自定义情景 {name: {volatility_multiplier, mean_shift}}
                       若为None，使用默认情景

        Returns:
            dict: {success, scenario_results: [{name, var, cvar, max_drawdown, ...}]}
        """
        try:
            rt = np.asarray(returns, dtype=np.float64)
            rt = rt[~np.isnan(rt)]

            if len(rt) < 10:
                return {"success": False, "error": "数据不足"}

            mu = np.mean(rt)
            sigma = np.std(rt)

            # 默认压力情景
            if scenarios is None:
                scenarios = {
                    "moderate_stress": {"vol_mult": 2.0, "mean_shift": -0.01},
                    "severe_stress": {"vol_mult": 3.0, "mean_shift": -0.02},
                    "crash_2008": {"vol_mult": 5.0, "mean_shift": -0.03},
                    "covid_2020": {"vol_mult": 4.0, "mean_shift": -0.025},
                    "flash_crash": {"vol_mult": 6.0, "mean_shift": -0.04},
                    "interest_rate_shock": {"vol_mult": 1.5, "mean_shift": -0.015},
                    "bull_reversal": {"vol_mult": 2.0, "mean_shift": -0.005},
                }

            scenario_results = []
            for name, params in scenarios.items():
                vol_mult = params.get("vol_mult", 1.0)
                mean_shift = params.get("mean_shift", 0.0)

                stressed_mu = mu + mean_shift
                stressed_sigma = sigma * vol_mult

                # 生成压力情景下的模拟收益
                n_sim = 1000
                simulated = self._rng.normal(stressed_mu, stressed_sigma, n_sim)

                var_95 = np.percentile(simulated, 5)
                cvar_95 = np.mean(simulated[simulated <= var_95])

                # 模拟最大回撤
                price = np.cumprod(1 + simulated)
                peak = np.maximum.accumulate(price)
                max_dd = float(np.min((price - peak) / peak))

                scenario_results.append({
                    "name": name,
                    "vol_multiplier": vol_mult,
                    "mean_shift": mean_shift,
                    "var_95": round(float(var_95), 6),
                    "cvar_95": round(float(cvar_95), 6),
                    "max_drawdown": round(max_dd, 4),
                    "annualized_loss": round(float(np.mean(simulated) * 252), 4),
                })

            return {
                "success": True,
                "base_metrics": {
                    "mean_daily": round(float(mu), 6),
                    "std_daily": round(float(sigma), 6),
                    "var_95": round(float(self.calculate_var(rt, 0.95)), 6),
                },
                "scenario_results": scenario_results,
                "scenario_count": len(scenario_results),
            }
        except Exception as e:
            logger.error(f"压力测试失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 滚动验证
    # ============================================================

    def rolling_validation(self, strategy: Callable[[np.ndarray], float],
                           data: np.ndarray,
                           window: int = 252,
                           step: int = 21) -> Dict[str, Any]:
        """滚动窗口验证

        在滚动窗口上反复训练和测试策略，评估稳定性。

        Args:
            strategy: 策略函数，接收数据窗口，返回收益率
            data: 完整数据序列（价格或收益率）
            window: 训练窗口大小（默认252个交易日）
            step: 步长（默认21个交易日）

        Returns:
            dict: {success, rolling_returns, rolling_sharpe, consistency, ...}
        """
        try:
            data_arr = np.asarray(data, dtype=np.float64)
            n = len(data_arr)

            if n < window + step:
                return {"success": False, "error": f"数据不足：需要至少 {window + step} 个数据点，当前 {n}"}

            rolling_returns = []
            rolling_sharpes = []

            for start in range(0, n - window, step):
                train_data = data_arr[start:start + window]
                end = min(start + window + step, n)
                test_data = data_arr[start + window:end]

                try:
                    ret = strategy(train_data)
                    rolling_returns.append(float(ret))

                    # 计算测试期间的夏普
                    if len(test_data) > 1:
                        test_returns = np.diff(test_data) / test_data[:-1]
                        if np.std(test_returns) > 0:
                            sharpe = np.mean(test_returns) / np.std(test_returns) * np.sqrt(252)
                            rolling_sharpes.append(float(sharpe))
                except Exception as e:
                    logger.warning(f"滚动窗口 [{start}:{start+window}] 策略执行失败: {e}")

            if not rolling_returns:
                return {"success": False, "error": "所有滚动窗口策略执行失败"}

            rolling_returns = np.array(rolling_returns)
            rolling_sharpes = np.array(rolling_sharpes) if rolling_sharpes else np.array([0.0])

            # 一致性指标
            consistency = {
                "mean_return": round(float(np.mean(rolling_returns)), 4),
                "std_return": round(float(np.std(rolling_returns)), 4),
                "min_return": round(float(np.min(rolling_returns)), 4),
                "max_return": round(float(np.max(rolling_returns)), 4),
                "positive_rate": round(float(np.mean(rolling_returns > 0)), 4),
                "mean_sharpe": round(float(np.mean(rolling_sharpes)), 4),
                "sharpe_stability": round(float(np.std(rolling_sharpes)), 4),
                "stability_score": round(float(1.0 - np.std(rolling_returns) / (abs(np.mean(rolling_returns)) + 1e-8)), 4),
            }

            return {
                "success": True,
                "window": window,
                "step": step,
                "total_windows": len(rolling_returns),
                "rolling_returns": rolling_returns.tolist(),
                "rolling_sharpes": rolling_sharpes.tolist(),
                "consistency": consistency,
            }
        except Exception as e:
            logger.error(f"滚动验证失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 过拟合检测
    # ============================================================

    def overfitting_detection(self, in_sample: np.ndarray,
                              out_sample: np.ndarray) -> Dict[str, Any]:
        """过拟合检测

        通过样本内/外性能对比，检测策略是否过拟合。

        Args:
            in_sample: 样本内收益率序列
            out_sample: 样本外收益率序列

        Returns:
            dict: {success, is_overfitted, degradation_ratio, metrics, ...}
        """
        try:
            is_rt = np.asarray(in_sample, dtype=np.float64)
            os_rt = np.asarray(out_sample, dtype=np.float64)

            is_rt = is_rt[~np.isnan(is_rt)]
            os_rt = os_rt[~np.isnan(os_rt)]

            if len(is_rt) < 10 or len(os_rt) < 10:
                return {"success": False, "error": "样本内/外数据不足"}

            # 样本内指标
            is_sharpe = self._calc_sharpe(is_rt)
            is_return = np.mean(is_rt) * 252
            is_max_dd = self._calc_max_drawdown(is_rt)
            is_win_rate = np.mean(is_rt > 0)

            # 样本外指标
            os_sharpe = self._calc_sharpe(os_rt)
            os_return = np.mean(os_rt) * 252
            os_max_dd = self._calc_max_drawdown(os_rt)
            os_win_rate = np.mean(os_rt > 0)

            # 退化比率
            sharpe_degradation = (is_sharpe - os_sharpe) / (abs(is_sharpe) + 1e-8)
            return_degradation = (is_return - os_return) / (abs(is_return) + 1e-8)
            dd_degradation = (abs(os_max_dd) - abs(is_max_dd)) / (abs(is_max_dd) + 1e-8)

            # 综合过拟合评分
            overfit_score = (
                max(0, sharpe_degradation) * 0.4 +
                max(0, return_degradation) * 0.3 +
                max(0, dd_degradation) * 0.3
            )

            # 判定
            if overfit_score < 0.2:
                overfit_level = "low"
            elif overfit_score < 0.5:
                overfit_level = "medium"
            elif overfit_score < 0.8:
                overfit_level = "high"
            else:
                overfit_level = "critical"

            return {
                "success": True,
                "is_overfitted": overfit_score > 0.3,
                "overfit_score": round(float(overfit_score), 4),
                "overfit_level": overfit_level,
                "in_sample": {
                    "sharpe": round(float(is_sharpe), 4),
                    "annual_return": round(float(is_return), 4),
                    "max_drawdown": round(float(is_max_dd), 4),
                    "win_rate": round(float(is_win_rate), 4),
                },
                "out_sample": {
                    "sharpe": round(float(os_sharpe), 4),
                    "annual_return": round(float(os_return), 4),
                    "max_drawdown": round(float(os_max_dd), 4),
                    "win_rate": round(float(os_win_rate), 4),
                },
                "degradation": {
                    "sharpe_degradation": round(float(sharpe_degradation), 4),
                    "return_degradation": round(float(return_degradation), 4),
                    "drawdown_degradation": round(float(dd_degradation), 4),
                },
            }
        except Exception as e:
            logger.error(f"过拟合检测失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 辅助方法
    # ============================================================

    def _calc_sharpe(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        """计算夏普比率"""
        mu = np.mean(returns) - risk_free / 252
        sigma = np.std(returns)
        if sigma == 0:
            return 0.0
        return mu / sigma * np.sqrt(252)

    def _calc_max_drawdown(self, returns: np.ndarray) -> float:
        """计算最大回撤"""
        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        return float(np.min((cumulative - peak) / peak))

    def _safe_skewness(self, data: np.ndarray) -> float:
        """安全计算偏度"""
        n = len(data)
        if n < 3:
            return 0.0
        mu = np.mean(data)
        sigma = np.std(data)
        if sigma == 0:
            return 0.0
        return float(np.mean(((data - mu) / sigma) ** 3))

    def _safe_kurtosis(self, data: np.ndarray) -> float:
        """安全计算峰度（超额峰度）"""
        n = len(data)
        if n < 4:
            return 0.0
        mu = np.mean(data)
        sigma = np.std(data)
        if sigma == 0:
            return 0.0
        return float(np.mean(((data - mu) / sigma) ** 4) - 3)


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    validator = MonteCarloValidator(random_seed=42)

    # 生成模拟收益率
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 500)

    # 蒙特卡洛模拟
    sim_result = validator.run_simulation(returns, n_simulations=500, horizon=252)
    print(f"蒙特卡洛模拟: success={sim_result['success']}")
    if sim_result['success']:
        print(f"  均值收益: {sim_result['statistics']['mean_return']}%")
        print(f"  95%CI: [{sim_result['confidence_interval']['lower_5pct']}%, {sim_result['confidence_interval']['upper_95pct']}%]")

    # VaR/CVaR
    var_result = validator.calculate_var_cvar_full(returns)
    print(f"\nVaR/CVaR: success={var_result['success']}")
    if var_result['success']:
        print(f"  VaR(95%): {var_result['var_daily']:.6f}")
        print(f"  CVaR(95%): {var_result['cvar_daily']:.6f}")

    # 压力测试
    stress_result = validator.stress_test(returns)
    print(f"\n压力测试: success={stress_result['success']}")
    if stress_result['success']:
        for s in stress_result['scenario_results'][:3]:
            print(f"  {s['name']}: VaR={s['var_95']:.6f}, MaxDD={s['max_drawdown']:.4f}")

    # 过拟合检测
    is_returns = returns[:300]
    os_returns = returns[300:]
    overfit_result = validator.overfitting_detection(is_returns, os_returns)
    print(f"\n过拟合检测: level={overfit_result.get('overfit_level', 'N/A')}, score={overfit_result.get('overfit_score', 'N/A')}")

    # 滚动验证
    def dummy_strategy(data: np.ndarray) -> float:
        return np.mean(np.diff(data) / data[:-1])

    prices = np.cumprod(1 + returns)
    rolling_result = validator.rolling_validation(dummy_strategy, prices, window=100, step=20)
    print(f"\n滚动验证: success={rolling_result['success']}, windows={rolling_result.get('total_windows', 0)}")