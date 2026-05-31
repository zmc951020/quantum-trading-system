#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 金融级风控守卫 (Risk Guard) v0.1.0
========================================================
4层防线 + Kill Switch + 波动率缩放 + Aurora HardRiskEngine 双向对接

风控层级（从内到外）：
  第1层：权重约束（单标的 ≤ 25%，行业 ≤ 35%）
  第2层：波动率缩放（目标年化波动率 12%）
  第3层：Kill Switch（日内回撤 > 8% 熔断）
  第4层：Aurora HardRiskEngine 兜底（T+1、涨跌停、仓位上限、策略熔断）

与 Aurora 现有模块的对接：
  - Aurora risk_manager.py → HardRiskEngine.pre_trade_check() 逐单审查
  - Aurora trade_security.py → TradeSecurity.validate_trade_amount() 频率/数量校验
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from strategies.smart_rotate_ppo.config import ETF_CODES, SECTOR_MAP, StrategyConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskVerdict:
    """风控判决结果"""
    passed: bool = True
    blocked_reason: str = ""
    original_weights: Optional[np.ndarray] = None
    adjusted_weights: Optional[np.ndarray] = None
    kill_switch: bool = False
    kill_reason: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    aurora_checks: Dict[str, bool] = field(default_factory=dict)

    def summary(self) -> str:
        """风控结果摘要"""
        parts = [
            f"风控判决: {'✅ 通过' if self.passed else '❌ 拦截'}",
        ]
        if self.blocked_reason:
            parts.append(f"  拦截原因: {self.blocked_reason}")
        if self.kill_switch:
            parts.append(f"  🔴 Kill Switch: {self.kill_reason}")
        for k, v in self.metrics.items():
            parts.append(f"  {k}: {v}")
        return "\n".join(parts)


class RiskGuard:
    """
    4 层风控防线 + Aurora 双向集成

    用法:
        guard = RiskGuard(cfg)

        # 基础用法（独立运行）
        verdict = guard.enforce(weights, cov_matrix)

        # Aurora 集成用法
        guard.bind_aurora_risk(hard_risk_engine)
        guard.bind_aurora_trade_security(trade_security)
        guard.register_strategy(strategy_id)

        verdict = guard.enforce_with_aurora(weights, cov_matrix, orders)
    """

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self._kill_switch_active: bool = False
        self._kill_reason: str = ""
        self._sector_map: Dict[str, str] = SECTOR_MAP
        self._kv_cache: Dict[str, float] = {}

        # Aurora 外部模块引用
        self._aurora_risk_engine = None
        self._aurora_trade_security = None
        self._strategy_id: str = "smart_rotate_ppo"

    # ========================================================================
    # Aurora 绑定接口
    # ========================================================================
    def bind_aurora_risk(self, hard_risk_engine) -> None:
        """绑定 Aurora HardRiskEngine"""
        self._aurora_risk_engine = hard_risk_engine
        logger.info("RiskGuard 已绑定 Aurora HardRiskEngine")

    def bind_aurora_trade_security(self, trade_security) -> None:
        """绑定 Aurora TradeSecurity"""
        self._aurora_trade_security = trade_security
        logger.info("RiskGuard 已绑定 Aurora TradeSecurity")

    def register_strategy(self, strategy_id: str) -> None:
        """注册策略 ID（供 Aurora 风控模块关联）"""
        self._strategy_id = strategy_id

    # ========================================================================
    # 主入口：独立风控（不依赖 Aurora）
    # ========================================================================
    def enforce(
        self,
        weights: np.ndarray,
        cov_matrix: Optional[np.ndarray] = None,
        returns_history: Optional[np.ndarray] = None,
        current_balance: float = 1_000_000.0,
        initial_balance: float = 1_000_000.0,
        orders: Optional[List[Dict]] = None,
    ) -> RiskVerdict:
        """
        执行 4 层风控约束（完整链路）

        Args:
            weights: 原始仓位权重，形状 (N,)
            cov_matrix: 协方差矩阵，形状 (N, N)，可选
            returns_history: 历史收益率，可选
            current_balance: 当前账户余额
            initial_balance: 初始账户余额
            orders: 订单列表（可选，供 Aurora 层审查）

        Returns:
            RiskVerdict 风控判决
        """
        original = np.asarray(weights, dtype=np.float64).copy()
        weights = original.copy()
        verdict = RiskVerdict(original_weights=original)

        # ── 第1层：权重约束 ──
        weights = self._constrain_weights(weights)
        if weights.sum() < 1e-10:
            verdict.passed = False
            verdict.blocked_reason = "所有权重被约束至零（单标的/行业超标）"
            verdict.adjusted_weights = np.zeros_like(weights)
            return verdict

        # ── 第2层：波动率缩放 ──
        if cov_matrix is not None:
            weights = self._volatility_scale(weights, cov_matrix)

        # ── 第3层：Kill Switch ──
        dd = self._compute_drawdown(current_balance, initial_balance)
        if self._kill_switch_active:
            verdict.kill_switch = True
            verdict.kill_reason = self._kill_reason
            verdict.passed = False
            verdict.adjusted_weights = np.zeros_like(weights)
            return verdict

        if dd > self.cfg.kill_switch_drawdown:
            self._kill_switch_active = True
            self._kill_reason = f"日内回撤 {dd:.2%} > KILL_SWITCH {self.cfg.kill_switch_drawdown:.2%}"
            logger.warning(f"[RISK GUARD] 🔴 {self._kill_reason}")
            verdict.kill_switch = True
            verdict.kill_reason = self._kill_reason
            verdict.passed = False
            verdict.adjusted_weights = np.zeros_like(weights)
            return verdict

        # ── 第4层：总和归一化 ──
        total = weights.sum()
        if total > self.cfg.max_total_leverage:
            weights = weights / total * self.cfg.max_total_leverage
        elif total > 1e-8:
            weights = weights / total

        # ── 可选：Aurora 审查（独立模式下跳过）──
        verdict.aurora_checks = {}
        if orders and self._aurora_risk_engine:
            verdict.aurora_checks = self._aurora_audit(orders)

        verdict.adjusted_weights = weights
        verdict.metrics = {
            "drawdown": round(dd, 4),
            "max_weight": round(float(np.max(weights)), 4),
            "num_assets": int(np.sum(weights > 0.001)),
            "total_weight": round(float(weights.sum()), 4),
            "turnover": round(float(np.abs(weights - original).sum()), 4),
            "volatility_target": self.cfg.volatility_target,
        }
        return verdict

    # ========================================================================
    # 主入口：Aurora 双层风控
    # ========================================================================
    def enforce_with_aurora(
        self,
        weights: np.ndarray,
        cov_matrix: Optional[np.ndarray] = None,
        current_balance: float = 1_000_000.0,
        initial_balance: float = 1_000_000.0,
        orders: Optional[List[Dict]] = None,
    ) -> RiskVerdict:
        """
        执行策略内风控 + Aurora HardRiskEngine 双向风控

        Args:
            weights: 原始仓位权重
            cov_matrix: 协方差矩阵
            current_balance: 当前余额
            initial_balance: 初始余额
            orders: 订单列表

        Returns:
            RiskVerdict 综合风控判决
        """
        # 第一步：策略内置风控（第1-3层）
        verdict = self.enforce(weights, cov_matrix, current_balance=current_balance, initial_balance=initial_balance)

        if not verdict.passed:
            logger.warning(f"策略内置风控拦截: {verdict.blocked_reason}")
            return verdict

        # 第二步：Aurora HardRiskEngine 审查（如果绑定）
        if orders and self._aurora_risk_engine:
            aurora_result = self._aurora_audit(orders)
            verdict.aurora_checks = aurora_result
            if not all(aurora_result.values()):
                failed_checks = [k for k, v in aurora_result.items() if not v]
                verdict.passed = False
                verdict.blocked_reason = f"Aurora HardRiskEngine 拦截: {failed_checks}"
                verdict.adjusted_weights = np.zeros_like(weights)
                logger.warning(f"[Aurora风控] 🔴 {verdict.blocked_reason}")

        return verdict

    # ========================================================================
    # Aurora 审查（第4层）
    # ========================================================================
    def _aurora_audit(self, orders: List[Dict]) -> Dict[str, bool]:
        """
        通过 Aurora HardRiskEngine + TradeSecurity 逐单审计

        Returns:
            {order_key: True/False, ...}
        """
        checks = {}
        for i, order in enumerate(orders):
            key = f"order_{i}_{order.get('symbol', 'UNKNOWN')}"
            try:
                # HardRiskEngine 审查
                if self._aurora_risk_engine:
                    result = self._aurora_risk_engine.pre_trade_check(
                        symbol=order.get("symbol", ""),
                        side=order.get("side", "buy"),
                        quantity=order.get("quantity", 0),
                        price=order.get("price", 0),
                        strategy_id=self._strategy_id,
                    )
                    checks[key] = result.get("allowed", True)

                # TradeSecurity 频率/数量校验
                if self._aurora_trade_security and checks.get(key, True):
                    ts_ok = self._aurora_trade_security.validate_trade_amount(
                        order.get("quantity", 0) * order.get("price", 0)
                    )
                    checks[key] = ts_ok
            except Exception as e:
                logger.error(f"Aurora 审查异常 ({key}): {e}")
                checks[key] = False
        return checks

    # ========================================================================
    # 第1层：权重约束
    # ========================================================================
    def _constrain_weights(self, weights: np.ndarray) -> np.ndarray:
        """单标的 ≤ 25%，行业 ≤ 35%"""
        weights = np.clip(np.asarray(weights, dtype=np.float64), 0.0, self.cfg.max_single_weight)

        # 行业约束
        if self._sector_map:
            sector_w: Dict[str, float] = {}
            for i in range(len(weights)):
                code = ETF_CODES[i] if i < len(ETF_CODES) else f"ETF_{i}"
                sector = self._sector_map.get(code, "未知")
                sector_w[sector] = sector_w.get(sector, 0.0) + weights[i]

            for sector, sw in sector_w.items():
                if sw > self.cfg.max_sector_weight:
                    scale = self.cfg.max_sector_weight / sw
                    for i in range(len(weights)):
                        code = ETF_CODES[i] if i < len(ETF_CODES) else f"ETF_{i}"
                        if self._sector_map.get(code, "未知") == sector:
                            weights[i] *= scale

        return weights

    # ========================================================================
    # 第2层：波动率缩放
    # ========================================================================
    def _volatility_scale(self, weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
        """目标波动率控制：缩放到 12% 年化"""
        if len(weights) == 0 or weights.sum() < 1e-10:
            return weights

        port_vol = float(np.sqrt(weights @ cov_matrix @ weights))
        if port_vol < 1e-10:
            return weights

        annual_vol = port_vol * np.sqrt(252)
        if annual_vol > self.cfg.volatility_target:
            scale = self.cfg.volatility_target / annual_vol
            scale = max(scale, self.cfg.volatility_scale_max)  # 不低于 50%
            weights = weights * scale
            logger.debug(f"波动率缩放: {annual_vol:.2%} → {self.cfg.volatility_target:.2%}, scale={scale:.2f}")

        return weights

    # ========================================================================
    # 第3层：Kill Switch
    # ========================================================================
    def _compute_drawdown(self, current_balance: float, initial_balance: float) -> float:
        """计算回撤百分比"""
        if initial_balance < 1e-8:
            return 0.0
        return max(0.0, (initial_balance - current_balance) / initial_balance)

    def is_kill_switch_active(self) -> bool:
        """查询 Kill Switch 状态"""
        return self._kill_switch_active

    def reset_kill_switch(self) -> None:
        """重置 Kill Switch（每日/每 session）"""
        self._kill_switch_active = False
        self._kill_reason = ""

    # ========================================================================
    # 权重→订单转换
    # ========================================================================
    def weights_to_orders(
        self,
        new_weights: np.ndarray,
        current_weights: np.ndarray,
        prices: np.ndarray,
        balance: float,
    ) -> List[Dict[str, Any]]:
        """
        将权重转换为订单列表（供 Aurora 审查和执行）

        Args:
            new_weights: 目标权重
            current_weights: 当前权重
            prices: 当前价格
            balance: 账户余额

        Returns:
            订单列表
        """
        orders = []
        for i in range(len(new_weights)):
            target_value = balance * new_weights[i]
            current_value = balance * current_weights[i]
            diff_value = target_value - current_value

            if abs(diff_value) < 100:  # 最低交易额 100 元
                continue

            quantity = int(abs(diff_value) / prices[i] / 100) * 100  # 整手
            if quantity < 100:
                continue

            side = "buy" if diff_value > 0 else "sell"
            orders.append({
                "symbol": ETF_CODES[i] if i < len(ETF_CODES) else f"ETF_{i}",
                "side": side,
                "quantity": quantity,
                "price": float(prices[i]),
                "value": float(quantity * prices[i]),
                "weight": float(new_weights[i]),
            })

        return orders

    # ========================================================================
    # 对接 Aurora 现有模块（向后兼容接口）
    # ========================================================================
    def integrate_aurora_risk(self, order: Dict) -> bool:
        """对接 Aurora risk_manager.py 的 check_order()（向后兼容）"""
        try:
            from risk_manager import RiskManager as AuroraRisk  # type: ignore
            checker = AuroraRisk()
            return checker.check_order(order)
        except ImportError:
            logger.debug("Aurora risk_manager 未加载，使用内置风控")
            return True

    def integrate_aurora_trade_security(self, amount: float) -> bool:
        """对接 Aurora trade_security.py 的频率/数量校验（向后兼容）"""
        try:
            from trade_security import TradeSecurity  # type: ignore
            ts = TradeSecurity()
            return ts.validate_trade_amount(amount)
        except ImportError:
            return True


__all__ = ["RiskGuard", "RiskVerdict"]