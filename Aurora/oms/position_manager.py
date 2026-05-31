# coding: utf-8
"""
持仓管理器增益模块 — 双复式记账 + 超买超卖防护
==================================================
增益性补充，不修改原有代码。

功能：
  - 现货持仓（买入/卖出原子更新）
  - 现金/总资产双复式记帐
  - 超买拦截（现金不足）
  - 超卖拦截（持仓不足）
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    avg_cost: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    buy_date: Optional[str] = None  # 最近买入日期，用于T+1


class PositionManager:
    """持仓管理器 — 增益层"""

    def __init__(self, initial_cash: float = 0.0):
        self._lock = threading.Lock()
        self._positions: Dict[str, Position] = {}
        self._cash: float = initial_cash
        self._frozen_cash: float = 0.0           # 冻结资金（待成交）
        self._frozen_positions: Dict[str, int] = {}  # 冻结持仓 symbol→qty

    # ────────── 公开 API ──────────

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def frozen_cash(self) -> float:
        return self._frozen_cash

    @property
    def available_cash(self) -> float:
        return self._cash - self._frozen_cash

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def get_all_positions(self) -> list:
        with self._lock:
            return list(self._positions.values())

    # ────────── 资金操作 ──────────

    def freeze_cash(self, amount: float) -> bool:
        """冻结资金（下单时扣）"""
        with self._lock:
            if amount > self.available_cash:
                logger.error("超买拦截: 冻结%.2f > 可用%.2f", amount, self.available_cash)
                return False
            self._frozen_cash += amount
            return True

    def unfreeze_cash(self, amount: float):
        """解冻资金（撤单/废单时还）"""
        with self._lock:
            self._frozen_cash = max(0.0, self._frozen_cash - amount)

    # ────────── 持仓操作 ──────────

    def freeze_position(self, symbol: str, quantity: int) -> bool:
        """冻结持仓（卖出下单时扣）"""
        with self._lock:
            pos = self._positions.get(symbol)
            available_qty = (pos.quantity if pos else 0) - self._frozen_positions.get(symbol, 0)
            if quantity > available_qty:
                logger.error("超卖拦截: %s 冻结%d > 可用%d", symbol, quantity, available_qty)
                return False
            self._frozen_positions[symbol] = self._frozen_positions.get(symbol, 0) + quantity
            return True

    def unfreeze_position(self, symbol: str, quantity: int):
        """解冻持仓"""
        with self._lock:
            self._frozen_positions[symbol] = max(0, self._frozen_positions.get(symbol, 0) - quantity)

    # ────────── 成交确认（原子更新） ──────────

    def confirm_buy(self, symbol: str, quantity: int, price: float, buy_date: str):
        """确认买入成交，原子扣款+增仓"""
        with self._lock:
            cost = quantity * price
            self._cash -= cost
            self._frozen_cash = max(0.0, self._frozen_cash - cost)

            pos = self._positions.get(symbol)
            if not pos:
                pos = Position(symbol=symbol)
                self._positions[symbol] = pos
            total_cost = (pos.avg_cost * pos.quantity) + (price * quantity)
            pos.quantity += quantity
            pos.avg_cost = total_cost / pos.quantity if pos.quantity > 0 else 0.0
            pos.buy_date = buy_date

    def confirm_sell(self, symbol: str, quantity: int, price: float):
        """确认卖出成交，原子加款+减仓"""
        with self._lock:
            self._cash += quantity * price
            pos = self._positions.get(symbol)
            if pos:
                pos.quantity -= quantity
                self._frozen_positions[symbol] = max(0, self._frozen_positions.get(symbol, 0) - quantity)
                if pos.quantity == 0:
                    self._positions.pop(symbol, None)

    # ────────── 总资产 ──────────

    def get_total_asset(self, market_prices: Dict[str, float]) -> float:
        """总资产 = 现金 + 持仓市值"""
        with self._lock:
            mv = 0.0
            for sym, pos in self._positions.items():
                price = market_prices.get(sym, pos.avg_cost)
                mv += pos.quantity * price
            return self._cash + mv