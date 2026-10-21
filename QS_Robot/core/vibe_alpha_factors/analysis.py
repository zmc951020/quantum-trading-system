"""因子分析 Mixin — IC/IR、分位数分层、衰减、相关性"""
import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class AnalysisMixin:
    """因子分析：IC/IR、分位数分层、衰减、相关性"""

    def calculate_ic_ir(self, factor_name: str,
                        factor_values: np.ndarray,
                        returns: np.ndarray) -> Dict[str, Any]:
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            rt = np.asarray(returns, dtype=np.float64)
            valid = ~(np.isnan(fv) | np.isnan(rt))
            fv = fv[valid]
            rt = rt[valid]
            if len(fv) < 10:
                return {"success": False, "error": "数据点不足", "factor_name": factor_name}
            from scipy.stats import spearmanr
            ic, _ = spearmanr(fv, rt)
            ic_series = np.array([ic])
            ic_mean = float(np.nanmean(ic_series))
            ic_std = float(np.nanstd(ic_series))
            ir = ic_mean / ic_std if ic_std > 0 else 0.0
            ic_positive_rate = float(np.sum(ic_series > 0) / len(ic_series))
            return {
                "success": True,
                "factor_name": factor_name,
                "ic_mean": round(ic_mean, 6),
                "ic_std": round(ic_std, 6),
                "ir": round(ir, 4),
                "ic_positive_rate": round(ic_positive_rate, 4),
                "sample_count": len(fv),
            }
        except Exception as e:
            logger.error(f"IC/IR分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_quantile_analysis(self, factor_name: str,
                                 factor_values: np.ndarray,
                                 returns: np.ndarray,
                                 n_quantiles: int = 5) -> Dict[str, Any]:
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            rt = np.asarray(returns, dtype=np.float64)
            valid = ~(np.isnan(fv) | np.isnan(rt))
            fv = fv[valid]
            rt = rt[valid]
            if len(fv) < n_quantiles * 5:
                return {"success": False, "error": "数据点不足", "factor_name": factor_name}
            quantile_edges = np.percentile(fv, np.linspace(0, 100, n_quantiles + 1))
            quantiles = []
            for i in range(n_quantiles):
                mask = (fv >= quantile_edges[i]) & (fv < quantile_edges[i + 1])
                if i == n_quantiles - 1:
                    mask = (fv >= quantile_edges[i]) & (fv <= quantile_edges[i + 1])
                quantiles.append({
                    "rank": i + 1,
                    "mean_return": round(float(np.nanmean(rt[mask])), 6),
                    "count": int(np.sum(mask)),
                })
            top_minus_bottom = quantiles[-1]["mean_return"] - quantiles[0]["mean_return"]
            return {
                "success": True,
                "factor_name": factor_name,
                "quantiles": quantiles,
                "top_minus_bottom": round(top_minus_bottom, 6),
                "n_quantiles": n_quantiles,
            }
        except Exception as e:
            logger.error(f"分位数分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_decay_analysis(self, factor_name: str,
                              factor_values: np.ndarray,
                              future_returns: Dict[int, np.ndarray]) -> Dict[str, Any]:
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            decay_curve = []
            for period, rt in sorted(future_returns.items()):
                rt_arr = np.asarray(rt, dtype=np.float64)
                valid = ~(np.isnan(fv) | np.isnan(rt_arr))
                if np.sum(valid) < 10:
                    continue
                from scipy.stats import spearmanr
                ic, _ = spearmanr(fv[valid], rt_arr[valid])
                decay_curve.append({
                    "period": period,
                    "ic_mean": round(float(ic), 6),
                })
            half_life = None
            if len(decay_curve) >= 2 and decay_curve[0]["ic_mean"] != 0:
                for dc in decay_curve:
                    if abs(dc["ic_mean"]) < abs(decay_curve[0]["ic_mean"]) / 2:
                        half_life = dc["period"]
                        break
            return {
                "success": True,
                "factor_name": factor_name,
                "decay_curve": decay_curve,
                "half_life_days": half_life,
            }
        except Exception as e:
            logger.error(f"因子衰减分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_correlation_matrix(self,
                                  factor_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
        try:
            factor_names = list(factor_data.keys())
            n = len(factor_names)
            if n < 2:
                return {"success": False, "error": "至少需要2个因子", "factor_names": factor_names}
            data_matrix = np.column_stack([
                np.asarray(factor_data[name], dtype=np.float64)
                for name in factor_names
            ])
            valid_rows = ~np.any(np.isnan(data_matrix), axis=1)
            data_matrix = data_matrix[valid_rows]
            if len(data_matrix) < 10:
                return {"success": False, "error": "有效数据点不足", "factor_names": factor_names}
            corr_matrix = np.corrcoef(data_matrix.T)
            corr_list = corr_matrix.tolist()
            high_corr_pairs = []
            for i in range(n):
                for j in range(i + 1, n):
                    if abs(corr_matrix[i, j]) > 0.7:
                        high_corr_pairs.append({
                            "factor_a": factor_names[i],
                            "factor_b": factor_names[j],
                            "correlation": round(float(corr_matrix[i, j]), 4),
                        })
            return {
                "success": True,
                "factor_names": factor_names,
                "correlation_matrix": corr_list,
                "high_correlation_pairs": high_corr_pairs,
                "sample_count": len(data_matrix),
            }
        except Exception as e:
            logger.error(f"因子相关性分析失败: {e}")
            return {"success": False, "error": str(e), "factor_names": list(factor_data.keys())}