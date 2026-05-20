#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量验证器
对实时/历史行情数据进行完整性、精度、时效性校验
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityValidator:
    """数据质量验证器 — 检查数据的完整性、精度、时效性和一致性"""

    def __init__(
        self,
        max_staleness_seconds: int = 300,
        min_price: float = 0.01,
        max_price: float = 1_000_000.0,
        max_volume_spike: float = 10.0,
        require_ohlc: bool = True,
    ):
        """
        Args:
            max_staleness_seconds: 最大允许的数据延迟（秒）
            min_price: 最小有效价格
            max_price: 最大有效价格
            max_volume_spike: 成交量相对历史均值的最大倍数
            require_ohlc: 是否要求完整的 OHLC 字段
        """
        self.max_staleness_seconds = max_staleness_seconds
        self.min_price = min_price
        self.max_price = max_price
        self.max_volume_spike = max_volume_spike
        self.require_ohlc = require_ohlc

        # 历史统计（用于异常检测）
        self._price_history: Dict[str, List[float]] = {}
        self._volume_history: Dict[str, List[float]] = {}
        self._history_max_len = 100

        # 统计
        self.total_validations = 0
        self.total_failures = 0

        logger.info(
            "[DataQualityValidator] 初始化完成，max_staleness=%ds, "
            "min_price=%.4f, max_price=%.2f",
            self.max_staleness_seconds,
            self.min_price,
            self.max_price,
        )

    # ── 核心验证接口 ──────────────────────────────────────────

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        验证单条数据记录

        Args:
            data: 包含 symbol, price, timestamp 等字段的字典

        Returns:
            (is_valid, message, report)
        """
        self.total_validations += 1
        report: Dict[str, Any] = {}

        # 1. 基础字段存在性
        symbol = data.get("symbol", data.get("code", ""))
        if not symbol:
            self.total_failures += 1
            return False, "缺少 symbol/code 字段", None

        # 2. 时效性检查
        timestamp = data.get("timestamp", data.get("time"))
        if timestamp is not None:
            ok, msg = self._check_staleness(timestamp)
            report["staleness"] = {"ok": ok, "msg": msg}
            if not ok:
                self.total_failures += 1
                return False, msg, report

        # 3. 价格校验
        for price_field in ("price", "close", "last"):
            price = data.get(price_field)
            if price is not None:
                break
        else:
            price = None

        if price is not None:
            ok, msg = self._check_price(price, symbol)
            report["price"] = {"ok": ok, "msg": msg}
            if not ok:
                self.total_failures += 1
                return False, msg, report
        else:
            if self.require_ohlc:
                self.total_failures += 1
                return False, "缺少价格字段（price/close/last）", None

        # 4. 成交量校验
        volume = data.get("volume", data.get("vol"))
        if volume is not None:
            ok, msg = self._check_volume(volume, symbol)
            report["volume"] = {"ok": ok, "msg": msg}
            if not ok:
                self.total_failures += 1
                return False, msg, report

        # 5. OHLC 完整性（可选）
        if self.require_ohlc:
            ohlc_fields = {"open", "high", "low", "close"}
            missing = [f for f in ohlc_fields if data.get(f) is None]
            if missing:
                self.total_failures += 1
                return False, f"缺失 OHLC 字段: {missing}", None

        return True, "数据有效", report

    def validate_dataframe(self, df: pd.DataFrame) -> Tuple[bool, str, Dict[str, Any]]:
        """
        批量验证 DataFrame

        Args:
            df: 包含 OHLCV 列的 DataFrame

        Returns:
            (all_valid, summary, details)
        """
        if df.empty:
            return False, "DataFrame 为空", {}

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(col.lower() for col in df.columns)
        if missing and self.require_ohlc:
            return False, f"缺失列: {missing}", {}

        null_summary = df[list(required)].isnull().sum().to_dict()
        total_nulls = sum(null_summary.values())

        dup_count = df.index.duplicated().sum() if df.index.is_unique is False else 0

        summary = {
            "total_rows": len(df),
            "null_counts": null_summary,
            "total_nulls": int(total_nulls),
            "duplicate_timestamps": int(dup_count),
        }

        ok = total_nulls == 0 and dup_count == 0
        msg = "数据有效" if ok else f"发现问题: nulls={total_nulls}, dup_ts={dup_count}"

        return ok, msg, summary

    # ── 内部检查方法 ─────────────────────────────────────────

    def _check_staleness(self, timestamp) -> Tuple[bool, str]:
        """检查数据是否过期"""
        now = datetime.now()

        if isinstance(timestamp, (int, float)):
            # Unix 时间戳
            if timestamp > 1e12:  # 毫秒
                timestamp = timestamp / 1000.0
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
            except ValueError:
                try:
                    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return True, "无法解析时间戳，跳过时效性检查"
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return True, "未知时间戳格式，跳过"

        age = (now - dt).total_seconds()
        if age > self.max_staleness_seconds:
            return False, f"数据过期（{age:.0f}s > {self.max_staleness_seconds}s）"
        return True, f"数据新鲜（{age:.0f}s）"

    def _check_price(self, price: float, symbol: str) -> Tuple[bool, str]:
        """检查价格有效性"""
        try:
            p = float(price)
        except (ValueError, TypeError):
            return False, f"价格无法转换为浮点数: {price}"

        if np.isnan(p) or np.isinf(p):
            return False, f"价格值异常: {p}"

        if p < self.min_price:
            return False, f"价格过低: {p} < {self.min_price}"

        if p > self.max_price:
            return False, f"价格过高: {p} > {self.max_price}"

        # 与历史比较，检测异常跳跃
        history = self._price_history.setdefault(symbol, [])
        if history:
            median = np.median(history[-20:]) if len(history) >= 5 else history[-1]
            if median > 0:
                change = abs(p - median) / median
                if change > 0.20:  # 20% 异常跳动
                    msg = f"价格异常跳变: {change*100:.1f}%（当前={p:.4f}, 参照中位数={median:.4f}）"
                    logger.warning("[DataQualityValidator] %s", msg)
                    # 不直接拒绝，只记录警告
                    return True, msg + "（仅警告）"

        history.append(p)
        if len(history) > self._history_max_len:
            history.pop(0)

        return True, "价格有效"

    def _check_volume(self, volume: float, symbol: str) -> Tuple[bool, str]:
        """检查成交量有效性"""
        try:
            v = float(volume)
        except (ValueError, TypeError):
            return False, f"成交量无法转换为浮点数: {volume}"

        if np.isnan(v) or np.isinf(v):
            return False, f"成交量值异常: {v}"

        if v < 0:
            return False, f"成交量为负: {v}"

        # 与历史比较
        history = self._volume_history.setdefault(symbol, [])
        if history:
            avg = np.mean(history[-20:]) if len(history) >= 5 else history[-1]
            if avg > 0 and v > avg * self.max_volume_spike:
                msg = f"成交量异常飙升: {v:.0f} vs 均值 {avg:.0f}"
                logger.warning("[DataQualityValidator] %s", msg)
                return False, msg

        history.append(v)
        if len(history) > self._history_max_len:
            history.pop(0)

        return True, "成交量有效"

    def get_status(self) -> Dict[str, Any]:
        """获取验证器状态"""
        return {
            "total_validations": self.total_validations,
            "total_failures": self.total_failures,
            "failure_rate": (
                self.total_failures / max(self.total_validations, 1)
            ),
            "tracked_symbols": len(self._price_history),
            "max_staleness_seconds": self.max_staleness_seconds,
        }


# ── 全局单例 ──────────────────────────────────────────────────

_global_validator: Optional[DataQualityValidator] = None


def get_data_validator() -> DataQualityValidator:
    """获取全局数据质量验证器实例"""
    global _global_validator
    if _global_validator is None:
        _global_validator = DataQualityValidator()
    return _global_validator