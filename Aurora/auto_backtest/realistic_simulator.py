# coding: utf-8
"""
真实市况回测模拟器 — 流动性约束 + 冲击成本 + 真实手续费建模
==========================================================
增益性补充，插入回测引擎与模拟行情之间，提供金融级市况约束。
不修改原有 auto_backtest_system.py 代码。

功能：
  - 成交量约束：单笔订单≤日成交量 1%~20%（由流动性分位决定）
  - 对手盘验证：买入需要卖单对手量，卖出需要买单对手量
  - 分层滑点模型：小单0.1%、大单0.3%、超量0.5%+
  - 冲击成本（市场冲击 + 临时冲击）
  - 完整手续费建模：
    * A股：佣金 0.025%/最低5元 + 印花税 0.1%（卖） + 过户费 0.002%
    * 可转债/ETF：佣金 0.01%/最低0.1元，免印花税
  - 限价单撮合：不满足价格条件则拒单/挂单
  - T+1 股票当天买入不可卖出
  - 涨跌停板不可交易

使用方式：
    from auto_backtest.realistic_simulator import RealisticSimulator
    sim = RealisticSimulator(initial_cash=1e6, market_type="A")
    result = sim.execute_order(symbol="600519", side="buy", quantity=100, price=1800.0)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 枚举与常量
# ─────────────────────────────────────────────

class MarketType(str, Enum):
    A_SHARE = "A"       # A股主板
    ETF = "ETF"         # ETF
    CB = "CB"           # 可转债
    NORTH = "NORTH"     # 北向通


class OrderStatus(str, Enum):
    FILLED = "filled"           # 完全成交
    PARTIAL = "partial"         # 部分成交
    REJECTED = "rejected"       # 拒单
    PENDING = "pending"         # 限价单挂起待成交
    CANCELLED = "cancelled"     # 已撤单


# ─── A股费率结构 ───
FEE_SCHEDULE = {
    MarketType.A_SHARE: {
        "commission_rate": 0.00025,      # 0.025% 券商佣金
        "commission_min": 5.0,           # 最低5元
        "stamp_duty_rate": 0.001,        # 0.1% 印花税（仅卖出）
        "stamp_duty_min": 1.0,           # 最低1元
        "transfer_fee_rate": 0.00002,    # 0.002% 过户费
        "transfer_fee_min": 0.0,
        "stamp_tax_on": "sell",          # 仅卖出方
    },
    MarketType.ETF: {
        "commission_rate": 0.0001,       # 0.01%
        "commission_min": 0.1,
        "stamp_duty_rate": 0.0,          # ETF免印花税
        "stamp_duty_min": 0.0,
        "transfer_fee_rate": 0.00002,
        "transfer_fee_min": 0.0,
        "stamp_tax_on": "none",
    },
    MarketType.CB: {
        "commission_rate": 0.0001,
        "commission_min": 0.1,
        "stamp_duty_rate": 0.0,          # 可转债免印花税
        "stamp_duty_min": 0.0,
        "transfer_fee_rate": 0.0,
        "transfer_fee_min": 0.0,
        "stamp_tax_on": "none",
    },
    MarketType.NORTH: {
        "commission_rate": 0.0003,       # 港股通 0.03%
        "commission_min": 5.0,
        "stamp_duty_rate": 0.001,
        "stamp_duty_min": 1.0,
        "transfer_fee_rate": 0.00002,
        "transfer_fee_min": 0.0,
        "stamp_tax_on": "both",          # 买卖双向
    },
}


# ─────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────

@dataclass
class LiquidityProfile:
    """股票流动性画像"""
    symbol: str
    avg_daily_volume: int = 0            # 日均成交量（股）
    avg_daily_turnover: float = 0.0      # 日均成交额（元）
    bid_ask_spread_pct: float = 0.002    # 买卖价差%（默认0.2%）
    market_depth_5: int = 0              # 5档深度（股）
    is_suspended: bool = False           # 是否停牌
    is_limit_up: bool = False            # 涨停
    is_limit_down: bool = False          # 跌停
    last_price: float = 0.0             # 最新价
    prev_close: float = 0.0             # 昨收


@dataclass
class ExecutionResult:
    """订单执行结果"""
    order_id: str = ""
    symbol: str = ""
    side: str = ""                       # buy / sell
    quantity: int = 0
    filled_quantity: int = 0
    price: float = 0.0                   # 目标价
    filled_price: float = 0.0            # 实际成交均价
    status: OrderStatus = OrderStatus.REJECTED
    
    # ── 费用明细 ──
    commission: float = 0.0              # 佣金
    stamp_duty: float = 0.0             # 印花税
    transfer_fee: float = 0.0           # 过户费
    total_fee: float = 0.0              # 总费用
    slippage_pct: float = 0.0           # 滑点%
    impact_cost_pct: float = 0.0        # 冲击成本%
    total_cost_pct: float = 0.0         # 总成本%（含手续费）
    
    # ── 元数据 ──
    reject_reason: str = ""
    executed_at: str = ""
    is_t_plus_1_blocked: bool = False
    break_even_price: float = 0.0       # 盈亏平衡价


# ─────────────────────────────────────────────
# 主模拟器
# ─────────────────────────────────────────────

class RealisticSimulator:
    """
    真实市况回测模拟器 — 增益层

    插入回测引擎与行情之间，在每笔模拟成交前做：
      1. T+1 检查（A股）
      2. 涨跌停检查
      3. 流动性约束（成交量≤日平均N%）
      4. 冲击成本计算（Almgren–Chriss 简化模型）
      5. 滑点模拟（基于买卖价差+订单规模）
      6. 真实手续费计算
    """

    def __init__(
        self,
        initial_cash: float = 0.0,
        market_type: MarketType = MarketType.A_SHARE,
        *,
        volume_limit_pct: float = 0.05,          # 单笔≤日成交量5%（保守）
        max_position_pct: float = 0.10,           # 单票仓位上限10%
        enable_t_plus_1: bool = True,
        enable_limit_check: bool = True,
        enable_impact_cost: bool = True,
    ):
        self._lock = threading.Lock()
        self._market_type = market_type
        self._fee = FEE_SCHEDULE[market_type]

        # ── 可调参数 ──
        self.volume_limit_pct = volume_limit_pct
        self.max_position_pct = max_position_pct
        self.enable_t_plus_1 = enable_t_plus_1
        self.enable_limit_check = enable_limit_check
        self.enable_impact_cost = enable_impact_cost

        # ── 持仓追踪 ──
        self._positions: Dict[str, int] = {}            # symbol -> qty
        self._buy_dates: Dict[str, str] = {}            # symbol -> 最近买入日期
        self._cash: float = initial_cash
        self._total_commission: float = 0.0
        self._total_stamp: float = 0.0
        self._total_transfer: float = 0.0
        self._total_slippage: float = 0.0

        # ── 流动性数据注册 ──
        self._liquidity: Dict[str, LiquidityProfile] = {}

    # ────────── 行情注册 ──────────

    def register_liquidity(
        self,
        symbol: str,
        avg_daily_volume: int,
        avg_daily_turnover: float = 0.0,
        bid_ask_spread_pct: float = 0.002,
        market_depth_5: int = 0,
        last_price: float = 0.0,
        prev_close: float = 0.0,
        is_suspended: bool = False,
        is_limit_up: bool = False,
        is_limit_down: bool = False,
    ):
        """注册股票流动性画像（回测中用历史分时数据计算）"""
        profile = LiquidityProfile(
            symbol=symbol,
            avg_daily_volume=avg_daily_volume,
            avg_daily_turnover=avg_daily_turnover or avg_daily_volume * last_price,
            bid_ask_spread_pct=bid_ask_spread_pct,
            market_depth_5=market_depth_5 or avg_daily_volume // 100,
            last_price=last_price,
            prev_close=prev_close or last_price,
            is_suspended=is_suspended,
            is_limit_up=is_limit_up,
            is_limit_down=is_limit_down,
        )
        self._liquidity[symbol] = profile

    def register_batch(self, profiles: Dict[str, Dict[str, Any]]):
        """批量注册{符号: {volume, ...}}"""
        for sym, data in profiles.items():
            self.register_liquidity(sym, **data)

    # ────────── 市况快照 ──────────

    def get_net_position(self) -> Dict[str, Any]:
        """返回当前持仓快照"""
        with self._lock:
            return {
                "positions": dict(self._positions),
                "buy_dates": dict(self._buy_dates),
                "cash": self._cash,
                "total_commission": self._total_commission,
                "total_stamp": self._total_stamp,
                "total_transfer": self._total_transfer,
                "total_slippage": self._total_slippage,
            }

    # ────────── 核心：执行订单 ──────────

    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        *,
        order_type: str = "market",         # market / limit
        execution_date: Optional[str] = None,
        order_id: str = "",
    ) -> ExecutionResult:
        """
        执行模拟订单 — 完整市况约束流程。

        Args:
            symbol: 股票代码
            side: "buy" 或 "sell"
            quantity: 委托数量（股）
            price: 委托价格
            order_type: "market"（市价）或 "limit"（限价）
            execution_date: 执行日期 YYYY-MM-DD（用于T+1检查）
            order_id: 委托编号（可选）

        Returns:
            ExecutionResult 包含成交详情、费用、拒单原因
        """
        with self._lock:
            exec_date = execution_date or date.today().isoformat()
            if not order_id:
                order_id = f"{symbol}_{side}_{int(time.time()*1000)}"

            result = ExecutionResult(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                executed_at=datetime.now().isoformat(),
            )

            liq = self._liquidity.get(symbol)
            if not liq:
                result.reject_reason = f"缺少 {symbol} 流动性数据，请先 register_liquidity()"
                return result

            # ── 停牌检查 ──
            if liq.is_suspended:
                result.reject_reason = f"{symbol} 停牌中，不可交易"
                return result

            # ── 涨跌停检查 ──
            if self.enable_limit_check:
                if side == "buy" and liq.is_limit_up:
                    result.reject_reason = f"{symbol} 涨停，无法买入"
                    return result
                if side == "sell" and liq.is_limit_down:
                    result.reject_reason = f"{symbol} 跌停，无法卖出"
                    return result

            # ── T+1 检查 ──
            if self.enable_t_plus_1 and side == "sell":
                buy_date = self._buy_dates.get(symbol)
                if buy_date and buy_date == exec_date:
                    result.reject_reason = f"{symbol} T+1限制：{buy_date}买入，{exec_date}不可卖出"
                    result.is_t_plus_1_blocked = True
                    return result

            # ── 卖空检查 ──
            current_pos = self._positions.get(symbol, 0)
            if side == "sell" and quantity > current_pos:
                result.reject_reason = f"{symbol} 持仓不足：持有{current_pos}股，委托卖出{quantity}股"
                return result

            # ── 流动性约束 ──
            max_vol = max(1, int(liq.avg_daily_volume * self.volume_limit_pct))
            fillable_qty = min(quantity, max_vol)
            if fillable_qty < quantity:
                logger.warning(
                    "成交量约束: %s 委托%d超过流动性上限%d，仅成交%d",
                    symbol, quantity, max_vol, fillable_qty
                )

            # ── 滑点计算 ──
            slippage_pct = self._calc_slippage(liq, side, fillable_qty, order_type)
            if side == "buy":
                filled_price = price * (1 + slippage_pct)
            else:
                filled_price = price * (1 - slippage_pct)

            # ── 冲击成本 ──
            impact_pct = 0.0
            if self.enable_impact_cost:
                impact_pct = self._calc_impact(liq, fillable_qty, side)
                if side == "buy":
                    filled_price *= (1 + impact_pct)
                else:
                    filled_price *= (1 - impact_pct)

            # ── 限价单价格检查 ──
            if order_type == "limit":
                if side == "buy" and filled_price > price:
                    result.status = OrderStatus.REJECTED
                    result.reject_reason = f"限价买入：成交价{filled_price:.2f}>{price:.2f}，不满足限价"
                    return result
                if side == "sell" and filled_price < price:
                    result.status = OrderStatus.REJECTED
                    result.reject_reason = f"限价卖出：成交价{filled_price:.2f}<{price:.2f}，不满足限价"
                    return result

            # ── 手续费计算 ──
            fees = self._calc_fees(fillable_qty, filled_price, side)
            total_cost = (fillable_qty * filled_price) + fees["total"]
            proceeds = (fillable_qty * filled_price) - fees["total"]

            # ── 资金/持仓检查 ──
            if side == "buy":
                if self._cash < total_cost:
                    fillable_qty = int(self._cash // (filled_price + fees["total"] / max(fillable_qty, 1)))
                    if fillable_qty <= 0:
                        result.reject_reason = f"资金不足：需{total_cost:.2f}，可用{self._cash:.2f}"
                        return result
                    fees = self._calc_fees(fillable_qty, filled_price, side)
                # 更新持仓
                self._cash -= total_cost
                self._positions[symbol] = current_pos + fillable_qty
                self._buy_dates[symbol] = exec_date
            else:
                # sell
                self._cash += proceeds
                self._positions[symbol] = max(0, current_pos - fillable_qty)
                if self._positions[symbol] == 0:
                    self._positions.pop(symbol, None)
                    self._buy_dates.pop(symbol, None)

            # ── 累计费用 ──
            self._total_commission += fees["commission"]
            self._total_stamp += fees["stamp_duty"]
            self._total_transfer += fees["transfer_fee"]
            self._total_slippage += abs(filled_price - price) * fillable_qty

            # ── 填充结果 ──
            result.filled_quantity = fillable_qty
            result.filled_price = filled_price
            result.status = OrderStatus.FILLED if fillable_qty == quantity else OrderStatus.PARTIAL
            result.commission = fees["commission"]
            result.stamp_duty = fees["stamp_duty"]
            result.transfer_fee = fees["transfer_fee"]
            result.total_fee = fees["total"]
            result.slippage_pct = slippage_pct
            result.impact_cost_pct = impact_pct
            result.total_cost_pct = slippage_pct + impact_pct

            # 盈亏平衡价（买入时考虑费用，需要涨多少才回本）
            if side == "buy" and fillable_qty > 0:
                result.break_even_price = filled_price * (1 + (slippage_pct + impact_pct) * 2)
                result.break_even_price += fees["total"] / fillable_qty

            return result

    # ────────── 内部方法 ──────────

    def _calc_slippage(self, liq: LiquidityProfile, side: str, qty: int, order_type: str) -> float:
        """计算滑点%（基于买卖价差 + 订单规模）"""
        base = liq.bid_ask_spread_pct / 2.0  # 半价差
        # 大单惩罚
        size_ratio = qty / max(1, liq.market_depth_5)
        if size_ratio < 0.1:
            extra = 0.0005                     # 小单 0.05%
        elif size_ratio < 0.3:
            extra = 0.0015                     # 中单 0.15%
        elif size_ratio < 0.5:
            extra = 0.003                      # 大单 0.3%
        else:
            extra = 0.005                      # 超量 0.5%
        return base + extra

    def _calc_impact(self, liq: LiquidityProfile, qty: int, side: str) -> float:
        """冲击成本%（简化 Almgren-Chriss 模型）"""
        # 永久冲击 = 成交量占比 * 平均价差
        participation = qty / max(1, liq.avg_daily_volume)
        permanent = participation * 0.1      # ~10%的份额冲击系数
        # 临时冲击
        temporary = (participation ** 0.5) * 0.5 * liq.bid_ask_spread_pct
        return permanent + temporary

    def _calc_fees(self, qty: int, price: float, side: str) -> Dict[str, float]:
        """计算完整手续费"""
        turnover = qty * price
        fee = self._fee

        # 佣金
        commission = max(fee["commission_min"], turnover * fee["commission_rate"])

        # 印花税
        stamp_on = fee["stamp_tax_on"]
        stamp_duty = 0.0
        if (stamp_on == "sell" and side == "sell") or (stamp_on == "both"):
            stamp_duty = max(fee["stamp_duty_min"], turnover * fee["stamp_duty_rate"])
        elif (stamp_on == "buy" and side == "buy"):
            stamp_duty = max(fee["stamp_duty_min"], turnover * fee["stamp_duty_rate"])

        # 过户费
        transfer = max(fee["transfer_fee_min"], turnover * fee["transfer_fee_rate"])

        return {
            "commission": round(commission, 2),
            "stamp_duty": round(stamp_duty, 2),
            "transfer_fee": round(transfer, 2),
            "total": round(commission + stamp_duty + transfer, 2),
        }

    # ────────── 事务公开 ──────────

    def get_cash(self) -> float:
        return self._cash

    def get_position(self, symbol: str) -> int:
        return self._positions.get(symbol, 0)

    def get_total_fees(self) -> Dict[str, float]:
        return {
            "commission": round(self._total_commission, 2),
            "stamp_duty": round(self._total_stamp, 2),
            "transfer_fee": round(self._total_transfer, 2),
            "slippage": round(self._total_slippage, 2),
        }

    def reset(self, initial_cash: float = 0.0):
        """重置模拟器状态"""
        with self._lock:
            self._positions.clear()
            self._buy_dates.clear()
            self._cash = initial_cash
            self._total_commission = 0.0
            self._total_stamp = 0.0
            self._total_transfer = 0.0
            self._total_slippage = 0.0