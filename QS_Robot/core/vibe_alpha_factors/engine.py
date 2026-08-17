"""AlphaFactorEngine — 因子计算引擎主类"""
import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any, Callable

from ._registry import _FACTOR_REGISTRY, FactorMeta
from .basic_factors import BasicFactorsMixin
from .technical_factors import TechnicalFactorsMixin
from .fundamental_factors import FundamentalFactorsMixin
from .analysis import AnalysisMixin

logger = logging.getLogger(__name__)


class AlphaFactorEngine(BasicFactorsMixin, TechnicalFactorsMixin,
                         FundamentalFactorsMixin, AnalysisMixin):
    """Alpha因子计算引擎

    计算所有注册因子，支持因子分析（IC/IR、分层、衰减、相关性）。
    """

    def __init__(self):
        self._factors: Dict[str, Callable] = {}
        self._factor_meta: Dict[str, FactorMeta] = {}
        self._register_builtin_factors()

    def _register_builtin_factors(self):
        for name in dir(self):
            if name.startswith('_'):
                continue
            attr = getattr(self, name)
            if callable(attr) and name in _FACTOR_REGISTRY:
                self._factors[name] = attr
                self._factor_meta[name] = _FACTOR_REGISTRY[name]
        logger.info(f"已注册 {len(self._factors)} 个Alpha因子")

    @property
    def factor_names(self) -> List[str]:
        return list(self._factors.keys())

    @property
    def factor_meta(self) -> Dict[str, FactorMeta]:
        return dict(self._factor_meta)

    def calculate_all(self, symbol: str, kline_data: Dict[str, np.ndarray],
                      financials: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        t0 = time.time()

        if kline_data is None or len(kline_data.get("close", [])) < 60:
            return {
                "success": False,
                "error": "K线数据不足（至少需要60根K线）",
                "factors": {},
                "elapsed_seconds": 0
            }

        close = np.asarray(kline_data["close"], dtype=np.float64)
        high = np.asarray(kline_data.get("high", close), dtype=np.float64)
        low = np.asarray(kline_data.get("low", close), dtype=np.float64)
        open_prices = np.asarray(kline_data.get("open", close), dtype=np.float64)
        volume = np.asarray(kline_data.get("volume", np.ones_like(close)), dtype=np.float64)
        turnover = np.asarray(kline_data.get("turnover", np.ones_like(close)), dtype=np.float64)

        factors = {}
        financials = financials or {}

        basic_sequence_args = {
            "momentum_1m": [close],
            "momentum_3m": [close],
            "momentum_6m": [close],
            "momentum_12m": [close],
            "reversal_1m": [close],
            "volatility_1m": [close],
            "volatility_3m": [close],
            "volume_ratio": [volume],
            "turnover_rate": [turnover],
            "amplitude": [high, low, close],
            "price_position": [close],
            "ma_deviation": [close],
            "volume_breakout": [volume],
            "drawdown": [close],
            "up_days_ratio": [close],
            "gap_ratio": [open_prices, close],
            "volume_trend": [close, volume],
            "high_low_ratio": [high, low],
            "continuous_days": [close],
        }
        for name, args in basic_sequence_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(*args)[-1])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        technical_sequence_args = {
            "rsi_factor": [close],
            "macd_divergence": [close],
            "boll_position": [close],
            "ma_alignment": [close],
            "kdj_golden_cross": [close, high, low],
            "atr_factor": [high, low, close],
            "obv_divergence": [close, volume],
            "cci_factor": [high, low, close],
            "williams_r": [high, low, close],
            "mfi_factor": [high, low, close, volume],
            "adx_trend": [high, low, close],
            "psar_reversal": [high, low, close],
            "ichimoku_cloud": [close, high, low],
            "ema_cross": [close],
            "bollinger_bandwidth": [close],
        }
        for name, args in technical_sequence_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(*args)[-1])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        fundamental_single_args = {
            "pe_factor": financials.get("pe", 0),
            "pb_factor": financials.get("pb", 0),
            "roe_factor": financials.get("roe", 0),
            "roa_factor": financials.get("roa", 0),
            "gross_margin": financials.get("gross_margin", 0),
            "net_margin": financials.get("net_margin", 0),
            "debt_ratio": financials.get("debt_ratio", 0),
            "cash_flow_ratio": financials.get("cash_flow_ratio", 0),
            "eps_growth": financials.get("eps_growth", 0),
            "revenue_growth": financials.get("revenue_growth", 0),
            "dividend_yield": financials.get("dividend_yield", 0),
            "current_ratio": financials.get("current_ratio", 0),
            "inventory_turnover": financials.get("inventory_turnover", 0),
            "peg_factor": financials.get("peg", 0),
            "ev_ebitda": financials.get("ev_ebitda", 0),
        }
        for name, arg in fundamental_single_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(arg)[0])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        valid_scores = [v for v in factors.values() if not np.isnan(v)]
        composite_score = float(np.nanmean(valid_scores)) if valid_scores else 50.0

        elapsed = round(time.time() - t0, 4)
        logger.info(f"[{symbol}] 因子计算完成: {len(factors)}个因子, 综合评分={composite_score:.1f}, 耗时={elapsed}s")

        return {
            "success": True,
            "symbol": symbol,
            "factors": factors,
            "composite_score": composite_score,
            "factor_count": len(factors),
            "elapsed_seconds": elapsed,
        }