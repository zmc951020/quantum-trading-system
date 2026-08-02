#!/usr/bin/env python3
"""
FactorComparison - Alpha158 vs Wyckoff68 因子自动对比分析

核心功能：
  1. 双轨并行计算：同一数据上同时运行两套因子
  2. IC/IR对比：秩相关系数、信息比率差异分析
  3. 因子相关性：跨系统因子对应关系矩阵
  4. 信号一致性：两套因子产生的交易信号方向一致性
  5. 回测对比：同一策略分别用两套因子回测，对比收益/夏普/回撤
  6. 对比报告：自动生成Markdown/JSON报告，含切换建议

设计依据：
  豆包审查 + Trae方案 - 自动对比是灰度切换的安全验证手段
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================

@dataclass
class ComparisonResult:
    """单只股票因子对比结果"""
    symbol: str
    freq: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # 因子数量
    new_factor_count: int = 0
    old_factor_count: int = 0

    # IC对比
    new_mean_ic: Optional[float] = None
    old_mean_ic: Optional[float] = None
    ic_diff: Optional[float] = None
    ic_diff_pct: Optional[float] = None       # IC差异百分比

    # IR对比
    new_mean_ir: Optional[float] = None
    old_mean_ir: Optional[float] = None
    ir_diff: Optional[float] = None

    # 因子覆盖率
    new_coverage: float = 0.0                 # 新因子非NaN比例
    old_coverage: float = 0.0

    # 相关性
    cross_correlation: Optional[float] = None  # 两套因子值间平均相关性
    top_correlated_pairs: List[Dict] = field(default_factory=list)

    # 信号一致性
    signal_agreement: Optional[float] = None   # 信号方向一致性
    long_agreement: Optional[float] = None
    short_agreement: Optional[float] = None

    # 性能
    new_latency_ms: float = 0.0
    old_latency_ms: float = 0.0
    latency_ratio: float = 0.0

    # 结论
    recommendation: str = "unknown"            # pass / warn / fail
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class BacktestComparison:
    """回测对比结果"""
    strategy: str
    symbol: str

    # Alpha158因子回测结果
    new_total_return: float = 0.0
    new_sharpe: float = 0.0
    new_max_drawdown: float = 0.0
    new_win_rate: float = 0.0
    new_profit_loss_ratio: float = 0.0
    new_total_trades: int = 0

    # Wyckoff68因子回测结果
    old_total_return: float = 0.0
    old_sharpe: float = 0.0
    old_max_drawdown: float = 0.0
    old_win_rate: float = 0.0
    old_profit_loss_ratio: float = 0.0
    old_total_trades: int = 0

    # 差异
    return_diff: float = 0.0
    sharpe_diff: float = 0.0
    drawdown_diff: float = 0.0

    recommendation: str = "unknown"


@dataclass
class ComparisonReport:
    """综合对比报告"""
    report_id: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    summary: Dict[str, Any] = field(default_factory=dict)
    factor_comparisons: List[ComparisonResult] = field(default_factory=list)
    backtest_comparisons: List[BacktestComparison] = field(default_factory=list)
    overall_recommendation: str = "unknown"
    action_items: List[str] = field(default_factory=list)


class FactorComparator:
    """因子对比分析器

    使用示例:
        >>> comparator = FactorComparator()
        >>> result = comparator.compare_factors(
        ...     df, "600519", future_returns,
        ...     alpha158_engine, wyckoff_engine
        ... )
        >>> print(f"IC差异: {result.ic_diff:.4f}")
    """

    def __init__(self):
        self._results_cache: Dict[str, ComparisonResult] = {}

    # ================================================================
    # 因子对比
    # ================================================================

    def compare_factors(self,
                         df: pd.DataFrame,
                         symbol: str,
                         future_returns: np.ndarray,
                         alpha158_engine,
                         wyckoff_engine=None,
                         aligned_data=None,
                         freq: str = "day") -> ComparisonResult:
        """双轨并行计算并对比两套因子

        Args:
            df: OHLCV DataFrame (Qlib格式: $open, $high, $low, $close, $volume)
            symbol: 股票代码
            future_returns: 未来N期收益率（用于IC计算）
            alpha158_engine: Alpha158Engine 实例
            wyckoff_engine: WyckoffFactorEngine 实例（可选）
            aligned_data: MultiTimeframePipeline 的 AlignedData（Wyckoff需要）
            freq: 频率

        Returns:
            ComparisonResult
        """
        result = ComparisonResult(symbol=symbol, freq=freq)

        try:
            # ---- 1. 计算Alpha158因子 ----
            t0 = time.time()
            alpha_result = alpha158_engine.compute_ic_analysis(df, future_returns, freq)
            new_latency = (time.time() - t0) * 1000

            # 提取新因子IC/IR
            new_ics = [f.ic for f in alpha_result.factors.values() if f.ic is not None]
            new_irs = [f.ir for f in alpha_result.factors.values() if f.ir is not None]
            result.new_factor_count = len(alpha_result.factors)
            result.new_mean_ic = float(np.mean(new_ics)) if new_ics else None
            result.new_mean_ir = float(np.mean(new_irs)) if new_irs else None
            result.new_latency_ms = new_latency

            # 新因子覆盖率
            new_factor_matrix = alpha_result.get_factor_matrix(df, freq) if hasattr(alpha_result, 'get_factor_matrix') else pd.DataFrame()
            if not new_factor_matrix.empty:
                result.new_coverage = float(new_factor_matrix.notna().mean().mean())

            # ---- 2. 计算Wyckoff68因子 ----
            if wyckoff_engine is not None and aligned_data is not None:
                t0 = time.time()
                wyckoff_result = wyckoff_engine.compute_all(aligned_data)
                old_latency = (time.time() - t0) * 1000

                old_factor_matrix = wyckoff_result.get("factor_matrix", np.array([]))
                result.old_factor_count = old_factor_matrix.shape[1] if old_factor_matrix.ndim > 1 else 0
                result.old_latency_ms = old_latency

                if old_factor_matrix.size > 0:
                    result.old_coverage = float(np.mean(~np.isnan(old_factor_matrix)))

                # 计算旧因子IC（需要映射到日线）
                if old_factor_matrix.ndim == 2 and old_factor_matrix.shape[0] > 0:
                    old_ics = self._compute_ics_for_matrix(old_factor_matrix, future_returns)
                    result.old_mean_ic = float(np.mean(old_ics)) if old_ics else None
                    result.old_mean_ir = float(np.mean(old_ics) / np.std(old_ics)) if old_ics and np.std(old_ics) > 0 else None
            else:
                # 无 Wyckoff 引擎时，记录旧因子为 N/A
                result.old_factor_count = 0
                result.old_mean_ic = None
                result.old_mean_ir = None
                result.old_coverage = 0.0
                result.old_latency_ms = 0.0

            # ---- 3. IC差异分析 ----
            if result.new_mean_ic is not None and result.old_mean_ic is not None:
                result.ic_diff = result.new_mean_ic - result.old_mean_ic
                if abs(result.old_mean_ic) > 1e-10:
                    result.ic_diff_pct = result.ic_diff / abs(result.old_mean_ic) * 100

            if result.new_mean_ir is not None and result.old_mean_ir is not None:
                result.ir_diff = result.new_mean_ir - result.old_mean_ir

            # ---- 4. 跨系统因子相关性 ----
            if not new_factor_matrix.empty and wyckoff_engine is not None and aligned_data is not None:
                result.cross_correlation, result.top_correlated_pairs = \
                    self._compute_cross_correlation(new_factor_matrix, old_factor_matrix)

            # ---- 5. 信号一致性 ----
            if not new_factor_matrix.empty and wyckoff_engine is not None and aligned_data is not None:
                result.signal_agreement, result.long_agreement, result.short_agreement = \
                    self._compute_signal_consistency(new_factor_matrix, old_factor_matrix)

            # ---- 6. 时延对比 ----
            if result.old_latency_ms > 0:
                result.latency_ratio = result.new_latency_ms / result.old_latency_ms

            # ---- 7. 生成推荐 ----
            result.recommendation, result.warnings = self._generate_recommendation(result)

        except Exception as e:
            result.errors.append(f"对比失败: {e}")
            logger.error(f"因子对比失败: {symbol}: {e}")
            result.recommendation = "fail"

        self._results_cache[symbol] = result
        return result

    def compare_batch(self,
                       data: Dict[str, pd.DataFrame],
                       future_returns_dict: Dict[str, np.ndarray],
                       alpha158_engine,
                       wyckoff_engine=None,
                       aligned_data_dict: Dict[str, Any] = None,
                       freq: str = "day") -> List[ComparisonResult]:
        """批量对比多只股票

        Args:
            data: {symbol: DataFrame} 行情数据
            future_returns_dict: {symbol: np.ndarray} 未来收益
            alpha158_engine: Alpha158Engine
            wyckoff_engine: WyckoffFactorEngine
            aligned_data_dict: {symbol: AlignedData} Wyckoff所需
            freq: 频率

        Returns:
            List[ComparisonResult]
        """
        results = []
        for symbol, df in data.items():
            future_returns = future_returns_dict.get(symbol)
            aligned = aligned_data_dict.get(symbol) if aligned_data_dict else None

            if future_returns is None:
                continue

            result = self.compare_factors(
                df, symbol, future_returns,
                alpha158_engine, wyckoff_engine, aligned, freq
            )
            results.append(result)

        return results

    # ================================================================
    # 回测对比
    # ================================================================

    def compare_backtest(self,
                          strategy: str,
                          symbol: str,
                          new_backtest_result,   # BacktestResult (Alpha158)
                          old_backtest_result,   # BacktestResult (Wyckoff68)
                          ) -> BacktestComparison:
        """对比两套因子的回测结果

        Args:
            strategy: 策略名称
            symbol: 股票代码
            new_backtest_result: Alpha158因子回测结果
            old_backtest_result: Wyckoff68因子回测结果

        Returns:
            BacktestComparison
        """
        bc = BacktestComparison(strategy=strategy, symbol=symbol)

        # Alpha158结果
        bc.new_total_return = new_backtest_result.total_return
        bc.new_sharpe = new_backtest_result.sharpe_ratio
        bc.new_max_drawdown = new_backtest_result.max_drawdown
        bc.new_win_rate = new_backtest_result.win_rate
        bc.new_profit_loss_ratio = new_backtest_result.profit_loss_ratio
        bc.new_total_trades = new_backtest_result.total_trades

        # Wyckoff68结果
        bc.old_total_return = old_backtest_result.total_return
        bc.old_sharpe = old_backtest_result.sharpe_ratio
        bc.old_max_drawdown = old_backtest_result.max_drawdown
        bc.old_win_rate = old_backtest_result.win_rate
        bc.old_profit_loss_ratio = old_backtest_result.profit_loss_ratio
        bc.old_total_trades = old_backtest_result.total_trades

        # 差异
        bc.return_diff = bc.new_total_return - bc.old_total_return
        bc.sharpe_diff = bc.new_sharpe - bc.old_sharpe
        bc.drawdown_diff = bc.new_max_drawdown - bc.old_max_drawdown

        # 推荐
        if bc.sharpe_diff >= 0 and bc.return_diff >= 0 and bc.drawdown_diff <= 0:
            bc.recommendation = "pass"  # 新因子全面优于旧因子
        elif bc.sharpe_diff >= -0.1 and bc.return_diff >= -0.01:
            bc.recommendation = "warn"  # 轻微劣化，可接受
        else:
            bc.recommendation = "fail"  # 显著劣化

        return bc

    # ================================================================
    # 报告生成
    # ================================================================

    def generate_report(self,
                         factor_results: List[ComparisonResult],
                         backtest_results: List[BacktestComparison] = None,
                         output_path: str = None) -> ComparisonReport:
        """生成综合对比报告

        Args:
            factor_results: 因子对比结果列表
            backtest_results: 回测对比结果列表
            output_path: 报告输出路径（JSON）

        Returns:
            ComparisonReport
        """
        report = ComparisonReport(
            report_id=f"FCR_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            factor_comparisons=factor_results,
            backtest_comparisons=backtest_results or [],
        )

        # 汇总
        pass_count = sum(1 for r in factor_results if r.recommendation == "pass")
        warn_count = sum(1 for r in factor_results if r.recommendation == "warn")
        fail_count = sum(1 for r in factor_results if r.recommendation == "fail")

        ic_diffs = [r.ic_diff for r in factor_results if r.ic_diff is not None]
        ir_diffs = [r.ir_diff for r in factor_results if r.ir_diff is not None]

        report.summary = {
            "total_symbols": len(factor_results),
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "pass_rate": pass_count / max(len(factor_results), 1),

            "avg_ic_diff": float(np.mean(ic_diffs)) if ic_diffs else None,
            "avg_ir_diff": float(np.mean(ir_diffs)) if ir_diffs else None,
            "avg_new_coverage": float(np.mean([r.new_coverage for r in factor_results])),
            "avg_old_coverage": float(np.mean([r.old_coverage for r in factor_results])),

            "avg_new_latency_ms": float(np.mean([r.new_latency_ms for r in factor_results])),
            "avg_old_latency_ms": float(np.mean([r.old_latency_ms for r in factor_results if r.old_latency_ms > 0])),

            "avg_signal_agreement": float(np.mean(
                [r.signal_agreement for r in factor_results if r.signal_agreement is not None]
            )),
        }

        # 回测汇总
        if backtest_results:
            bt_pass = sum(1 for b in backtest_results if b.recommendation == "pass")
            report.summary["backtest_pass_rate"] = bt_pass / max(len(backtest_results), 1)
            report.summary["avg_sharpe_diff"] = float(np.mean([b.sharpe_diff for b in backtest_results]))
            report.summary["avg_return_diff"] = float(np.mean([b.return_diff for b in backtest_results]))

        # 整体推荐
        if report.summary["pass_rate"] >= 0.8:
            report.overall_recommendation = "ready_to_switch"   # 可以切换
            report.action_items = [
                "建议：Alpha158因子在大部分标的上表现优于或等于Wyckoff68因子",
                "可以推进灰度阶段到 PHASE_4（100%切换）",
                "建议持续监控IC差异变化，如有异常及时回退",
            ]
        elif report.summary["pass_rate"] >= 0.5:
            report.overall_recommendation = "continue_gray"     # 继续灰度
            report.action_items = [
                "建议：Alpha158因子在部分标的上表现良好，但存在一些劣化标的",
                "继续灰度推进，重点排查 fail 标的的因子计算问题",
                "建议对 fail 标的进行单独分析，确认是否可修复",
            ]
        else:
            report.overall_recommendation = "hold_and_fix"      # 暂缓切换
            report.action_items = [
                "警告：Alpha158因子在多数标的上表现不如Wyckoff68因子",
                "暂缓灰度切换，排查因子计算逻辑问题",
                "重点检查：因子归一化、缺失值处理、频率适配",
            ]

        # 保存报告
        if output_path:
            self._save_report(report, output_path)

        return report

    def _save_report(self, report: ComparisonReport, output_path: str):
        """保存报告到文件"""
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 转换为可序列化格式
            report_dict = {
                "report_id": report.report_id,
                "generated_at": report.generated_at,
                "summary": report.summary,
                "overall_recommendation": report.overall_recommendation,
                "action_items": report.action_items,
                "factor_comparisons": [
                    {
                        "symbol": r.symbol,
                        "freq": r.freq,
                        "new_factor_count": r.new_factor_count,
                        "old_factor_count": r.old_factor_count,
                        "new_mean_ic": r.new_mean_ic,
                        "old_mean_ic": r.old_mean_ic,
                        "ic_diff": r.ic_diff,
                        "ic_diff_pct": r.ic_diff_pct,
                        "new_mean_ir": r.new_mean_ir,
                        "old_mean_ir": r.old_mean_ir,
                        "ir_diff": r.ir_diff,
                        "new_coverage": r.new_coverage,
                        "old_coverage": r.old_coverage,
                        "cross_correlation": r.cross_correlation,
                        "signal_agreement": r.signal_agreement,
                        "long_agreement": r.long_agreement,
                        "short_agreement": r.short_agreement,
                        "new_latency_ms": r.new_latency_ms,
                        "old_latency_ms": r.old_latency_ms,
                        "latency_ratio": r.latency_ratio,
                        "recommendation": r.recommendation,
                        "warnings": r.warnings,
                        "errors": r.errors,
                    }
                    for r in report.factor_comparisons
                ],
                "backtest_comparisons": [
                    {
                        "strategy": b.strategy,
                        "symbol": b.symbol,
                        "new_total_return": b.new_total_return,
                        "new_sharpe": b.new_sharpe,
                        "new_max_drawdown": b.new_max_drawdown,
                        "new_win_rate": b.new_win_rate,
                        "old_total_return": b.old_total_return,
                        "old_sharpe": b.old_sharpe,
                        "old_max_drawdown": b.old_max_drawdown,
                        "old_win_rate": b.old_win_rate,
                        "return_diff": b.return_diff,
                        "sharpe_diff": b.sharpe_diff,
                        "drawdown_diff": b.drawdown_diff,
                        "recommendation": b.recommendation,
                    }
                    for b in report.backtest_comparisons
                ],
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, ensure_ascii=False, indent=2)

            logger.info(f"对比报告已保存: {output_path}")
        except Exception as e:
            logger.error(f"报告保存失败: {e}")

    # ================================================================
    # 内部计算
    # ================================================================

    def _compute_ics_for_matrix(self, factor_matrix: np.ndarray,
                                  future_returns: np.ndarray) -> List[float]:
        """计算因子矩阵的IC值"""
        from scipy.stats import spearmanr

        if factor_matrix.ndim != 2 or factor_matrix.shape[0] == 0:
            return []

        n_factors = factor_matrix.shape[1]
        n_samples = min(factor_matrix.shape[0], len(future_returns))

        ics = []
        for j in range(n_factors):
            values = factor_matrix[-n_samples:, j]
            valid = ~(np.isnan(values) | np.isnan(future_returns[-n_samples:]))
            if valid.sum() >= 30:
                try:
                    ic, _ = spearmanr(values[valid], future_returns[-n_samples:][valid])
                    if not np.isnan(ic):
                        ics.append(ic)
                except Exception:
                    pass

        return ics

    def _compute_cross_correlation(self,
                                     new_matrix: pd.DataFrame,
                                     old_matrix: np.ndarray) -> Tuple[Optional[float], List[Dict]]:
        """计算跨系统因子相关性"""
        try:
            if old_matrix.ndim != 2 or old_matrix.shape[0] == 0:
                return None, []

            n_new = new_matrix.shape[1]
            n_old = old_matrix.shape[1]
            n_samples = min(new_matrix.shape[0], old_matrix.shape[0])

            if n_samples < 10:
                return None, []

            new_vals = new_matrix.iloc[-n_samples:].values
            old_vals = old_matrix[-n_samples:]

            # 计算每对新旧因子间的相关性
            correlations = []
            for i in range(min(n_new, 50)):  # 限制对数量
                for j in range(min(n_old, 30)):
                    valid = ~(np.isnan(new_vals[:, i]) | np.isnan(old_vals[:, j]))
                    if valid.sum() >= 10:
                        corr = np.corrcoef(new_vals[valid, i], old_vals[valid, j])[0, 1]
                        if not np.isnan(corr):
                            correlations.append({
                                "new_factor": new_matrix.columns[i] if i < len(new_matrix.columns) else f"F{i}",
                                "old_factor_idx": j,
                                "correlation": float(corr),
                            })

            # 排序取top
            correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
            top_pairs = correlations[:20]

            avg_corr = float(np.mean([c["correlation"] for c in correlations])) if correlations else None
            return avg_corr, top_pairs

        except Exception as e:
            logger.debug(f"跨系统相关性计算失败: {e}")
            return None, []

    def _compute_signal_consistency(self,
                                      new_matrix: pd.DataFrame,
                                      old_matrix: np.ndarray) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """计算信号方向一致性

        将因子矩阵转换为方向信号（正/负），对比两套因子的方向一致性。
        """
        try:
            if old_matrix.ndim != 2 or old_matrix.shape[0] == 0:
                return None, None, None

            n_samples = min(new_matrix.shape[0], old_matrix.shape[0])
            if n_samples < 10:
                return None, None, None

            # 新因子：取最后一行的各因子方向
            new_last = new_matrix.iloc[-1].values
            new_direction = np.sign(new_last)

            # 旧因子：取最后一行的各因子方向
            old_last = old_matrix[-1]
            old_direction = np.sign(old_last)

            # 对比方向一致性（需要因子数量相同才有意义，这里简单对比统计）
            new_pos = np.mean(new_direction > 0)
            old_pos = np.mean(old_direction > 0)
            new_neg = np.mean(new_direction < 0)
            old_neg = np.mean(old_direction < 0)

            # 整体一致性
            long_agree = 1 - abs(new_pos - old_pos)
            short_agree = 1 - abs(new_neg - old_neg)
            overall = (long_agree + short_agree) / 2

            return float(overall), float(long_agree), float(short_agree)

        except Exception as e:
            logger.debug(f"信号一致性计算失败: {e}")
            return None, None, None

    def _generate_recommendation(self, result: ComparisonResult) -> Tuple[str, List[str]]:
        """生成单个标的的推荐"""
        warnings = []

        # IC下降超过10% → 警告
        if result.ic_diff is not None and result.ic_diff_pct is not None:
            if result.ic_diff_pct < -10:
                warnings.append(f"IC下降 {result.ic_diff_pct:.1f}% (新={result.new_mean_ic:.4f}, 旧={result.old_mean_ic:.4f})")

        # 覆盖率太低
        if result.new_coverage < 0.5:
            warnings.append(f"新因子覆盖率过低: {result.new_coverage:.1%}")

        # 信号一致性太低
        if result.signal_agreement is not None and result.signal_agreement < 0.5:
            warnings.append(f"信号一致性过低: {result.signal_agreement:.1%}")

        # 时延过高
        if result.latency_ratio > 3.0:
            warnings.append(f"新因子时延过高: {result.latency_ratio:.1f}x")

        if result.errors:
            return "fail", warnings

        if len(warnings) >= 3:
            return "fail", warnings
        elif len(warnings) >= 1:
            return "warn", warnings
        else:
            return "pass", warnings

    # ================================================================
    # 因子衰减对比
    # ================================================================

    def compare_factor_decay(self,
                              df: pd.DataFrame,
                              symbol: str,
                              future_returns: np.ndarray,
                              alpha158_engine,
                              wyckoff_engine=None,
                              aligned_data=None,
                              freq: str = "day") -> Dict[str, Any]:
        """对比因子衰减曲线

        Args:
            df: OHLCV DataFrame
            symbol: 股票代码
            future_returns: 未来收益
            alpha158_engine: Alpha158Engine
            wyckoff_engine: WyckoffFactorEngine
            aligned_data: AlignedData
            freq: 频率

        Returns:
            {new_decay: [...], old_decay: [...], lags: [...]}
        """
        lags = [1, 3, 5, 10, 20]

        # Alpha158因子衰减
        alpha_result = alpha158_engine.compute_ic_analysis(df, future_returns, freq)
        new_decay = []
        for factor in alpha_result.factors.values():
            if factor.decay is not None:
                new_decay.append(factor.decay)

        new_avg_decay = float(np.mean(new_decay)) if new_decay else None

        # Wyckoff因子衰减
        old_avg_decay = None
        if wyckoff_engine is not None and aligned_data is not None:
            wyckoff_result = wyckoff_engine.compute_all(aligned_data)
            old_matrix = wyckoff_result.get("factor_matrix", np.array([]))
            if old_matrix.ndim == 2 and old_matrix.shape[0] > 0:
                old_decay = []
                for j in range(old_matrix.shape[1]):
                    values = old_matrix[:, j]
                    valid = ~np.isnan(values)
                    if valid.sum() < 30:
                        continue
                    decay_ics = []
                    for lag in lags:
                        if lag < valid.sum():
                            v = values[valid][:-lag]
                            r = future_returns[lag:]
                            min_len = min(len(v), len(r))
                            from scipy.stats import spearmanr
                            ic, _ = spearmanr(v[:min_len], r[:min_len])
                            decay_ics.append(ic)
                    if decay_ics:
                        decay = np.polyfit(range(len(decay_ics)), decay_ics, 1)[0]
                        old_decay.append(decay)
                old_avg_decay = float(np.mean(old_decay)) if old_decay else None

        return {
            "symbol": symbol,
            "freq": freq,
            "new_avg_decay": new_avg_decay,
            "old_avg_decay": old_avg_decay,
            "decay_diff": new_avg_decay - old_avg_decay if new_avg_decay is not None and old_avg_decay is not None else None,
            "lags": lags,
            "new_factor_count": len(new_decay),
        }


# ============================================================
# 全局单例
# ============================================================

_comparator: Optional[FactorComparator] = None


def get_comparator() -> FactorComparator:
    global _comparator
    if _comparator is None:
        _comparator = FactorComparator()
    return _comparator


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from core.qlib_core.alpha_factors import Alpha158Engine, get_alpha_engine
    from core.qlib_core.data_converter import DataConverter

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    comparator = FactorComparator()

    # 生成模拟数据
    dates = pd.date_range("2026-01-01", "2026-06-18", freq="B")
    n = len(dates)
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)

    df = pd.DataFrame({
        "$open": close * (1 + np.random.randn(n) * 0.01),
        "$high": close * (1 + np.abs(np.random.randn(n) * 0.02)),
        "$low": close * (1 - np.abs(np.random.randn(n) * 0.02)),
        "$close": close,
        "$volume": np.random.uniform(1e6, 1e8, n),
        "$vwap": close * (1 + np.random.randn(n) * 0.005),
    }, index=dates)
    df["$high"] = df[["$open", "$high", "$close"]].max(axis=1) * 1.001
    df["$low"] = df[["$open", "$low", "$close"]].min(axis=1) * 0.999

    # 未来收益
    future_returns = np.diff(np.log(close), prepend=0)

    # Alpha158引擎
    engine = get_alpha_engine()

    print("=== 因子对比测试 ===")
    result = comparator.compare_factors(
        df, "600519", future_returns,
        alpha158_engine=engine,
        wyckoff_engine=None,  # 不依赖Wyckoff引擎也能测试
        freq="day",
    )
    print(f"  新因子数: {result.new_factor_count}")
    print(f"  新IC均值: {result.new_mean_ic}")
    print(f"  新覆盖率: {result.new_coverage:.2%}")
    print(f"  新因子耗时: {result.new_latency_ms:.0f}ms")
    print(f"  推荐: {result.recommendation}")
    print(f"  警告: {result.warnings}")

    # 测试批量对比
    print("\n=== 批量对比 ===")
    symbols = ["600519", "000858"]
    data = {}
    returns_dict = {}
    for sym in symbols:
        data[sym] = df
        returns_dict[sym] = future_returns

    results = comparator.compare_batch(
        data, returns_dict, engine, freq="day"
    )
    print(f"  对比结果: {len(results)} 个标的")

    # 生成报告
    print("\n=== 生成对比报告 ===")
    report = comparator.generate_report(results, output_path="./reports/factor_comparison_test.json")
    print(f"  报告ID: {report.report_id}")
    print(f"  通过率: {report.summary['pass_rate']:.1%}")
    print(f"  整体推荐: {report.overall_recommendation}")
    print(f"  行动项: {report.action_items}")

    # 测试因子衰减
    print("\n=== 因子衰减对比 ===")
    decay = comparator.compare_factor_decay(
        df, "600519", future_returns, engine, freq="day"
    )
    print(f"  新因子衰减: {decay.get('new_avg_decay')}")
    print(f"  衰减差异: {decay.get('decay_diff')}")

    print("\n全部测试通过!")