#!/usr/bin/env python3
"""
期权/衍生品分析模块（Options Analyzer）

Vibe-Trading 系统的期权与衍生品工具集，提供：
  - Black-Scholes 期权定价（欧式看涨/看跌）
  - 希腊字母计算（Delta, Gamma, Theta, Vega, Rho）
  - 隐含波动率计算（Newton-Raphson 迭代法）
  - 波动率微笑/曲面分析
  - 期权策略盈亏分析（Straddle, Strangle, Butterfly, Iron Condor等）

依赖：numpy, scipy
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from scipy.stats import norm

logger = logging.getLogger(__name__)


# ============================================================
# 期权分析器
# ============================================================

class OptionsAnalyzer:
    """期权与衍生品分析器

    提供期权定价、希腊字母、隐含波动率、波动率曲面和策略分析。
    """

    def __init__(self):
        self._norm = norm

    # ============================================================
    # Black-Scholes 定价
    # ============================================================

    def black_scholes(self, S: float, K: float, T: float, r: float,
                      sigma: float, option_type: str = 'call') -> float:
        """Black-Scholes 期权定价模型

        计算欧式期权的理论价格。

        Args:
            S: 标的资产当前价格
            K: 行权价
            T: 到期时间（年）
            r: 无风险利率（年化，如 0.03 表示 3%）
            sigma: 波动率（年化，如 0.20 表示 20%）
            option_type: 'call' 看涨期权 / 'put' 看跌期权

        Returns:
            float: 期权理论价格
        """
        if T <= 0 or sigma <= 0:
            return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        if option_type == 'call':
            price = S * self._norm.cdf(d1) - K * np.exp(-r * T) * self._norm.cdf(d2)
        else:
            price = K * np.exp(-r * T) * self._norm.cdf(-d2) - S * self._norm.cdf(-d1)

        return float(price)

    # ============================================================
    # 希腊字母
    # ============================================================

    def calculate_greeks(self, S: float, K: float, T: float, r: float,
                         sigma: float) -> Dict[str, float]:
        """计算期权希腊字母

        计算 Delta, Gamma, Theta, Vega, Rho 五个希腊字母。

        Args:
            S: 标的资产价格
            K: 行权价
            T: 到期时间（年）
            r: 无风险利率
            sigma: 波动率

        Returns:
            dict: {delta, gamma, theta, vega, rho} (call和put的Delta分别计算)
        """
        try:
            if T <= 0 or sigma <= 0:
                return {
                    "call_delta": 0.0, "put_delta": 0.0,
                    "gamma": 0.0, "theta": 0.0,
                    "vega": 0.0, "call_rho": 0.0, "put_rho": 0.0,
                }

            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)

            pdf_d1 = self._norm.pdf(d1)
            cdf_d1 = self._norm.cdf(d1)
            cdf_d2 = self._norm.cdf(d2)
            cdf_neg_d1 = self._norm.cdf(-d1)
            cdf_neg_d2 = self._norm.cdf(-d2)

            sqrt_t = np.sqrt(T)

            # Delta
            call_delta = cdf_d1
            put_delta = cdf_d1 - 1.0

            # Gamma (call和put相同)
            gamma = pdf_d1 / (S * sigma * sqrt_t)

            # Theta (每日)
            term1 = -(S * pdf_d1 * sigma) / (2 * sqrt_t)
            call_theta = (term1 - r * K * np.exp(-r * T) * cdf_d2) / 365.0
            put_theta = (term1 + r * K * np.exp(-r * T) * cdf_neg_d2) / 365.0

            # Vega (1%波动率变化)
            vega = (S * pdf_d1 * sqrt_t) / 100.0

            # Rho (1%利率变化)
            call_rho = (K * T * np.exp(-r * T) * cdf_d2) / 100.0
            put_rho = (-K * T * np.exp(-r * T) * cdf_neg_d2) / 100.0

            return {
                "call_delta": round(float(call_delta), 6),
                "put_delta": round(float(put_delta), 6),
                "gamma": round(float(gamma), 6),
                "call_theta": round(float(call_theta), 6),
                "put_theta": round(float(put_theta), 6),
                "vega": round(float(vega), 6),
                "call_rho": round(float(call_rho), 6),
                "put_rho": round(float(put_rho), 6),
            }
        except Exception as e:
            logger.error(f"希腊字母计算失败: {e}")
            return {"error": str(e)}

    # ============================================================
    # 隐含波动率
    # ============================================================

    def implied_volatility(self, price: float, S: float, K: float, T: float,
                           r: float, option_type: str = 'call',
                           max_iterations: int = 100,
                           tolerance: float = 1e-8) -> float:
        """计算隐含波动率（Newton-Raphson 迭代法）

        Args:
            price: 期权市场价格
            S: 标的资产价格
            K: 行权价
            T: 到期时间（年）
            r: 无风险利率
            option_type: 'call' / 'put'
            max_iterations: 最大迭代次数
            tolerance: 收敛容差

        Returns:
            float: 隐含波动率（年化）
        """
        if price <= 0 or T <= 0:
            return 0.0

        # 内在价值检查
        intrinsic = max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)
        if price < intrinsic:
            return 0.0

        # 初始猜测
        sigma = 0.3

        for i in range(max_iterations):
            bs_price = self.black_scholes(S, K, T, r, sigma, option_type)
            diff = bs_price - price

            if abs(diff) < tolerance:
                return round(float(sigma), 6)

            # Vega = d(price)/d(sigma)
            if T <= 0:
                break
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            vega = S * self._norm.pdf(d1) * np.sqrt(T)

            if abs(vega) < 1e-10:
                # Vega 太小，使用二分法
                sigma = sigma * 0.5 if diff > 0 else sigma * 1.5
            else:
                sigma = sigma - diff / vega

            # 边界约束
            sigma = max(0.001, min(sigma, 5.0))

        # 返回最佳估计
        return round(float(sigma), 6)

    def implied_volatility_surface(self, prices: List[List[float]],
                                   S: float, strikes: List[float],
                                   maturities: List[float], r: float,
                                   option_type: str = 'call') -> Dict[str, Any]:
        """计算隐含波动率曲面

        Args:
            prices: 期权价格矩阵 [maturities][strikes]
            S: 标的资产价格
            strikes: 行权价列表
            maturities: 到期时间列表
            r: 无风险利率
            option_type: 'call' / 'put'

        Returns:
            dict: {success, iv_surface: [[...]], strikes, maturities, moneyness_matrix}
        """
        try:
            n_maturities = len(maturities)
            n_strikes = len(strikes)

            if n_maturities == 0 or n_strikes == 0:
                return {"success": False, "error": "行权价或到期时间为空"}

            iv_surface = np.zeros((n_maturities, n_strikes))
            moneyness = np.zeros((n_maturities, n_strikes))

            for i, T in enumerate(maturities):
                for j, K in enumerate(strikes):
                    p = prices[i][j] if i < len(prices) and j < len(prices[i]) else 0
                    iv_surface[i, j] = self.implied_volatility(p, S, K, T, r, option_type)
                    moneyness[i, j] = K / S

            return {
                "success": True,
                "S": S,
                "strikes": strikes,
                "maturities": maturities,
                "iv_surface": iv_surface.tolist(),
                "moneyness_matrix": moneyness.tolist(),
                "dimensions": {
                    "n_maturities": n_maturities,
                    "n_strikes": n_strikes,
                },
            }
        except Exception as e:
            logger.error(f"隐含波动率曲面计算失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 波动率微笑
    # ============================================================

    def volatility_smile(self, strikes: List[float],
                         ivs: List[float]) -> Dict[str, Any]:
        """波动率微笑分析

        分析不同行权价对应的隐含波动率，检测微笑/偏斜形态。

        Args:
            strikes: 行权价列表
            ivs: 对应的隐含波动率列表

        Returns:
            dict: {success, smile_data, smile_type, atm_iv, skew, curvature}
        """
        try:
            if len(strikes) < 3 or len(ivs) < 3:
                return {"success": False, "error": "至少需要3个数据点"}

            strikes_arr = np.asarray(strikes, dtype=np.float64)
            ivs_arr = np.asarray(ivs, dtype=np.float64)

            # 排序
            sort_idx = np.argsort(strikes_arr)
            strikes_arr = strikes_arr[sort_idx]
            ivs_arr = ivs_arr[sort_idx]

            # ATM IV (中间值)
            mid_idx = len(strikes_arr) // 2
            atm_iv = float(ivs_arr[mid_idx])

            # 微笑类型判断
            left_iv = np.mean(ivs_arr[:mid_idx])
            right_iv = np.mean(ivs_arr[mid_idx:])

            if left_iv > atm_iv and right_iv > atm_iv:
                smile_type = "smile"  # 微笑
            elif left_iv > atm_iv:
                smile_type = "smirk_left"  # 左偏
            elif right_iv > atm_iv:
                smile_type = "smirk_right"  # 右偏
            else:
                smile_type = "flat"  # 平坦

            # 偏度
            skew = float(right_iv - left_iv)

            # 曲率（二次拟合）
            if len(strikes_arr) >= 4:
                coeffs = np.polyfit(strikes_arr, ivs_arr, 2)
                curvature = float(coeffs[0])  # 二次项系数
            else:
                curvature = 0.0

            # 微笑数据点
            smile_data = [
                {"strike": float(s), "iv": float(iv)}
                for s, iv in zip(strikes_arr, ivs_arr)
            ]

            return {
                "success": True,
                "smile_data": smile_data,
                "smile_type": smile_type,
                "atm_iv": round(atm_iv, 6),
                "skew": round(skew, 6),
                "curvature": round(curvature, 8),
                "min_iv": round(float(np.min(ivs_arr)), 6),
                "max_iv": round(float(np.max(ivs_arr)), 6),
                "mean_iv": round(float(np.mean(ivs_arr)), 6),
            }
        except Exception as e:
            logger.error(f"波动率微笑分析失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 波动率曲面
    # ============================================================

    def volatility_surface(self, strikes: List[float],
                           maturities: List[float],
                           iv_matrix: List[List[float]]) -> Dict[str, Any]:
        """波动率曲面分析

        分析三维波动率曲面（行权价 × 到期时间）。

        Args:
            strikes: 行权价列表
            maturities: 到期时间列表
            iv_matrix: 隐含波动率矩阵 [maturities][strikes]

        Returns:
            dict: {success, surface_data, term_structure, skew_by_maturity, ...}
        """
        try:
            n_maturities = len(maturities)
            n_strikes = len(strikes)

            if n_maturities < 2 or n_strikes < 2:
                return {"success": False, "error": "数据和维度不足"}

            iv_arr = np.asarray(iv_matrix, dtype=np.float64)

            # 期限结构（ATM IV 随时间变化）
            mid_strike_idx = n_strikes // 2
            term_structure = []
            for i, T in enumerate(maturities):
                if i < len(iv_arr):
                    term_structure.append({
                        "maturity": float(T),
                        "atm_iv": round(float(iv_arr[i, mid_strike_idx]), 6),
                    })

            # 各到期时间的偏度
            skew_by_maturity = []
            for i, T in enumerate(maturities):
                if i < len(iv_arr):
                    left = np.mean(iv_arr[i, :mid_strike_idx])
                    right = np.mean(iv_arr[i, mid_strike_idx:])
                    skew_by_maturity.append({
                        "maturity": float(T),
                        "skew": round(float(right - left), 6),
                    })

            # 曲面摘要
            surface_data = {
                "strikes": strikes,
                "maturities": maturities,
                "iv_matrix": iv_arr.tolist(),
            }

            return {
                "success": True,
                "surface_data": surface_data,
                "term_structure": term_structure,
                "skew_by_maturity": skew_by_maturity,
                "dimensions": f"{n_maturities} × {n_strikes}",
                "global_stats": {
                    "min_iv": round(float(np.nanmin(iv_arr)), 6),
                    "max_iv": round(float(np.nanmax(iv_arr)), 6),
                    "mean_iv": round(float(np.nanmean(iv_arr)), 6),
                    "std_iv": round(float(np.nanstd(iv_arr)), 6),
                },
            }
        except Exception as e:
            logger.error(f"波动率曲面分析失败: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 期权策略盈亏分析
    # ============================================================

    def option_strategy_pnl(self, strategy_type: str,
                            params: Dict[str, Any]) -> Dict[str, Any]:
        """期权策略盈亏分析

        支持多种期权策略的盈亏图分析。

        Args:
            strategy_type: 策略类型
                - 'straddle': 跨式（买入call+put，同行权价）
                - 'strangle': 宽跨式（买入call+put，不同行权价）
                - 'butterfly': 蝶式（买入1低+卖出2中+买入1高）
                - 'iron_condor': 铁鹰（卖出宽跨式+买入保护）
                - 'bull_spread': 牛市价差
                - 'bear_spread': 熊市价差
                - 'covered_call': 备兑看涨
                - 'protective_put': 保护性看跌
            params: 策略参数 {S, r, T, 以及各策略特定参数}

        Returns:
            dict: {success, strategy_type, pnl_curve, max_profit, max_loss, break_even, ...}
        """
        try:
            S = params.get("S", 100.0)
            r = params.get("r", 0.03)
            T = params.get("T", 0.25)

            if T <= 0:
                return {"success": False, "error": "到期时间必须大于0"}

            # 价格范围（±30%）
            price_range = np.linspace(S * 0.7, S * 1.3, 200)

            if strategy_type == "straddle":
                pnl_curve = self._pnl_straddle(price_range, params, S, r, T)
            elif strategy_type == "strangle":
                pnl_curve = self._pnl_strangle(price_range, params, S, r, T)
            elif strategy_type == "butterfly":
                pnl_curve = self._pnl_butterfly(price_range, params, S, r, T)
            elif strategy_type == "iron_condor":
                pnl_curve = self._pnl_iron_condor(price_range, params, S, r, T)
            elif strategy_type == "bull_spread":
                pnl_curve = self._pnl_bull_spread(price_range, params, S, r, T)
            elif strategy_type == "bear_spread":
                pnl_curve = self._pnl_bear_spread(price_range, params, S, r, T)
            elif strategy_type == "covered_call":
                pnl_curve = self._pnl_covered_call(price_range, params, S, r, T)
            elif strategy_type == "protective_put":
                pnl_curve = self._pnl_protective_put(price_range, params, S, r, T)
            else:
                return {"success": False, "error": f"不支持的策略类型: {strategy_type}"}

            max_profit = float(np.max(pnl_curve))
            max_loss = float(np.min(pnl_curve))

            # 盈亏平衡点
            break_even = []
            for i in range(1, len(pnl_curve)):
                if pnl_curve[i - 1] * pnl_curve[i] <= 0:
                    be_price = price_range[i - 1] + (price_range[i] - price_range[i - 1]) * \
                               abs(pnl_curve[i - 1]) / (abs(pnl_curve[i - 1]) + abs(pnl_curve[i]))
                    break_even.append(round(float(be_price), 2))

            return {
                "success": True,
                "strategy_type": strategy_type,
                "S": S,
                "pnl_curve": [
                    {"price": round(float(p), 2), "pnl": round(float(pnl), 2)}
                    for p, pnl in zip(price_range, pnl_curve)
                ],
                "max_profit": round(max_profit, 2),
                "max_loss": round(max_loss, 2),
                "break_even": break_even,
                "risk_reward_ratio": round(abs(max_profit / max_loss), 2) if max_loss != 0 else None,
            }

        except Exception as e:
            logger.error(f"期权策略盈亏分析失败: {e}")
            return {"success": False, "error": str(e)}

    # ---- 策略实现 ----

    def _pnl_straddle(self, prices: np.ndarray, params: Dict,
                      S: float, r: float, T: float) -> np.ndarray:
        """跨式策略：买入同一行权价的call+put"""
        K = params.get("K", S)
        sigma = params.get("sigma", 0.25)
        call_price = self.black_scholes(S, K, T, r, sigma, 'call')
        put_price = self.black_scholes(S, K, T, r, sigma, 'put')
        cost = call_price + put_price
        return np.maximum(prices - K, 0) + np.maximum(K - prices, 0) - cost

    def _pnl_strangle(self, prices: np.ndarray, params: Dict,
                      S: float, r: float, T: float) -> np.ndarray:
        """宽跨式策略：买入不同行权价的call+put"""
        K_call = params.get("K_call", S * 1.05)
        K_put = params.get("K_put", S * 0.95)
        sigma = params.get("sigma", 0.25)
        call_price = self.black_scholes(S, K_call, T, r, sigma, 'call')
        put_price = self.black_scholes(S, K_put, T, r, sigma, 'put')
        cost = call_price + put_price
        return np.maximum(prices - K_call, 0) + np.maximum(K_put - prices, 0) - cost

    def _pnl_butterfly(self, prices: np.ndarray, params: Dict,
                       S: float, r: float, T: float) -> np.ndarray:
        """蝶式策略：买入K1+卖出2×K2+买入K3"""
        K1 = params.get("K1", S * 0.9)
        K2 = params.get("K2", S)
        K3 = params.get("K3", S * 1.1)
        sigma = params.get("sigma", 0.25)
        is_call = params.get("use_call", True)
        opt_type = 'call' if is_call else 'put'

        p1 = self.black_scholes(S, K1, T, r, sigma, opt_type)
        p2 = self.black_scholes(S, K2, T, r, sigma, opt_type)
        p3 = self.black_scholes(S, K3, T, r, sigma, opt_type)
        cost = p1 - 2 * p2 + p3

        payoff = (np.maximum(prices - K1, 0) - 2 * np.maximum(prices - K2, 0) +
                  np.maximum(prices - K3, 0))
        if not is_call:
            payoff = (np.maximum(K1 - prices, 0) - 2 * np.maximum(K2 - prices, 0) +
                      np.maximum(K3 - prices, 0))
        return payoff - cost

    def _pnl_iron_condor(self, prices: np.ndarray, params: Dict,
                         S: float, r: float, T: float) -> np.ndarray:
        """铁鹰策略"""
        K1 = params.get("K1", S * 0.85)
        K2 = params.get("K2", S * 0.95)
        K3 = params.get("K3", S * 1.05)
        K4 = params.get("K4", S * 1.15)
        sigma = params.get("sigma", 0.25)

        # 卖出K2 put + 买入K1 put + 卖出K3 call + 买入K4 call
        p1 = self.black_scholes(S, K1, T, r, sigma, 'put')
        p2 = self.black_scholes(S, K2, T, r, sigma, 'put')
        p3 = self.black_scholes(S, K3, T, r, sigma, 'call')
        p4 = self.black_scholes(S, K4, T, r, sigma, 'call')
        credit = -p1 + p2 - p4 + p3

        payoff = -(np.maximum(K1 - prices, 0) - np.maximum(K2 - prices, 0) +
                   np.maximum(prices - K4, 0) - np.maximum(prices - K3, 0))
        return payoff + credit

    def _pnl_bull_spread(self, prices: np.ndarray, params: Dict,
                         S: float, r: float, T: float) -> np.ndarray:
        """牛市价差：买入低行权价call + 卖出高行权价call"""
        K_low = params.get("K_low", S * 0.95)
        K_high = params.get("K_high", S * 1.05)
        sigma = params.get("sigma", 0.25)
        p_low = self.black_scholes(S, K_low, T, r, sigma, 'call')
        p_high = self.black_scholes(S, K_high, T, r, sigma, 'call')
        cost = p_low - p_high
        return np.maximum(prices - K_low, 0) - np.maximum(prices - K_high, 0) - cost

    def _pnl_bear_spread(self, prices: np.ndarray, params: Dict,
                         S: float, r: float, T: float) -> np.ndarray:
        """熊市价差：买入高行权价put + 卖出低行权价put"""
        K_low = params.get("K_low", S * 0.95)
        K_high = params.get("K_high", S * 1.05)
        sigma = params.get("sigma", 0.25)
        p_high = self.black_scholes(S, K_high, T, r, sigma, 'put')
        p_low = self.black_scholes(S, K_low, T, r, sigma, 'put')
        cost = p_high - p_low
        return np.maximum(K_high - prices, 0) - np.maximum(K_low - prices, 0) - cost

    def _pnl_covered_call(self, prices: np.ndarray, params: Dict,
                          S: float, r: float, T: float) -> np.ndarray:
        """备兑看涨：持有标的 + 卖出call"""
        K = params.get("K", S * 1.05)
        sigma = params.get("sigma", 0.25)
        call_price = self.black_scholes(S, K, T, r, sigma, 'call')
        cost = S - call_price
        return (prices - S) - np.maximum(prices - K, 0) + call_price

    def _pnl_protective_put(self, prices: np.ndarray, params: Dict,
                            S: float, r: float, T: float) -> np.ndarray:
        """保护性看跌：持有标的 + 买入put"""
        K = params.get("K", S * 0.95)
        sigma = params.get("sigma", 0.25)
        put_price = self.black_scholes(S, K, T, r, sigma, 'put')
        cost = S + put_price
        return (prices - S) + np.maximum(K - prices, 0) - put_price


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    analyzer = OptionsAnalyzer()

    # Black-Scholes 定价
    S, K, T, r, sigma = 100.0, 100.0, 0.25, 0.03, 0.25
    call_price = analyzer.black_scholes(S, K, T, r, sigma, 'call')
    put_price = analyzer.black_scholes(S, K, T, r, sigma, 'put')
    print(f"BS定价: call={call_price:.4f}, put={put_price:.4f}")

    # 希腊字母
    greeks = analyzer.calculate_greeks(S, K, T, r, sigma)
    print(f"\n希腊字母:")
    print(f"  Call Delta: {greeks.get('call_delta', 'N/A')}")
    print(f"  Put Delta:  {greeks.get('put_delta', 'N/A')}")
    print(f"  Gamma:      {greeks.get('gamma', 'N/A')}")
    print(f"  Vega:       {greeks.get('vega', 'N/A')}")
    print(f"  Call Theta: {greeks.get('call_theta', 'N/A')}")

    # 隐含波动率
    iv = analyzer.implied_volatility(call_price, S, K, T, r, 'call')
    print(f"\n隐含波动率: {iv:.6f} (应接近 {sigma})")

    # 波动率微笑
    strikes = [80, 85, 90, 95, 100, 105, 110, 115, 120]
    ivs = [0.354, 0.312, 0.281, 0.258, 0.252, 0.261, 0.278, 0.305, 0.345]
    smile = analyzer.volatility_smile(strikes, ivs)
    print(f"\n波动率微笑: type={smile.get('smile_type')}, skew={smile.get('skew')}")

    # 期权策略盈亏
    straddle = analyzer.option_strategy_pnl("straddle", {"S": S, "K": K, "r": r, "T": T, "sigma": sigma})
    print(f"\n跨式策略: max_profit={straddle.get('max_profit')}, max_loss={straddle.get('max_loss')}, BE={straddle.get('break_even')}")

    bull_spread = analyzer.option_strategy_pnl("bull_spread", {"S": S, "K_low": 95, "K_high": 105, "r": r, "T": T, "sigma": sigma})
    print(f"牛市价差: max_profit={bull_spread.get('max_profit')}, max_loss={bull_spread.get('max_loss')}")

    iron_condor = analyzer.option_strategy_pnl("iron_condor", {"S": S, "K1": 85, "K2": 95, "K3": 105, "K4": 115, "r": r, "T": T, "sigma": sigma})
    print(f"铁鹰策略: max_profit={iron_condor.get('max_profit')}, max_loss={iron_condor.get('max_loss')}")