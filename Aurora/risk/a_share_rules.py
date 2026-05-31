# coding: utf-8
"""
A股交易规则增益校验器 — 增益性补充模块
============================================
插入现有 TradeSecurityValidator 验证管线之后，
作为独立校验层，不修改原有代码。

功能：
  - T+1 卖出限制（当日买入不可卖出）
  - 涨跌停价格校验（主板/科创/创业板/北交所/ST 差异化）
  - 交易单位=100股(1手)校验
  - 停牌状态检测
  - 集合竞价时段识别与限制

使用方式：
  from risk.a_share_rules import AShareRulesValidator
  validator = AShareRulesValidator(data_provider)
  ok, msg = validator.validate(symbol, side, quantity, price, ref_date)
"""

import logging
from datetime import date, time, datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AShareRulesValidator:
    """A股交易规则校验器 — 增益层，可插入现有验证管线"""

    # ── 涨跌停幅度规则 ──
    # 主板 ±10% / 科创板 ±20% / 创业板 ±20% / 北交所 ±30% / ST ±5%
    _LIMIT_RULES = {
        "sh60": 0.10,
        "sz00": 0.10,
        "sz30": 0.10,
        "sh68": 0.20,       # 科创板 688xxx
        "sz300": 0.20,      # 创业板 300xxx
        "sz301": 0.20,      # 创业板 301xxx
        "bj":   0.30,       # 北交所 8xxx/4xxx
        "st":   0.05,       # ST 股票
    }

    # ── A股交易时段 ──
    MORNING_CALL_AUCTION_START = time(9, 15)
    MORNING_CALL_AUCTION_END   = time(9, 25)
    MORNING_CONTINUOUS_START   = time(9, 30)
    MORNING_CONTINUOUS_END     = time(11, 30)
    AFTERNOON_CONTINUOUS_START = time(13, 0)
    AFTERNOON_CONTINUOUS_END   = time(15, 0)

    def __init__(self, data_provider=None):
        """
        Args:
            data_provider: 可选的数据源对象，需提供：
                - get_prev_close(symbol) -> float | None
                - get_stock_info(symbol)  -> dict | None  (含 is_st, board 等)
                - is_suspended(symbol)    -> bool
        """
        self.data_provider = data_provider
        # 内部持仓记录：symbol -> {"quantity": int, "buy_date": "YYYY-MM-DD"}
        self._positions: dict = {}

    # ────────── 公开 API ──────────

    def validate(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        ref_date: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        综合校验 A 股交易规则。
        Returns: (是否通过, 原因描述)
        """
        # 1. 交易单位
        ok, msg = self._check_lot_size(quantity)
        if not ok:
            return False, msg

        # 2. 涨跌停
        prev_close = self._get_prev_close(symbol)
        if prev_close is not None and prev_close > 0:
            ok, msg = self._check_price_limit(symbol, side, price, prev_close)
            if not ok:
                return False, msg

        # 3. T+1（卖出方向）
        if side == "sell":
            ok, msg = self._check_t_plus_one(symbol, ref_date)
            if not ok:
                return False, msg

        # 4. 停牌
        if self.data_provider and hasattr(self.data_provider, "is_suspended"):
            if self.data_provider.is_suspended(symbol):
                return False, f"A股规则: {symbol} 停牌中，禁止交易"

        return True, "A股规则验证通过"

    # ────────── 内部持仓管理 ──────────

    def record_buy(self, symbol: str, quantity: int, buy_date: str):
        """记录买入（用于 T+1 校验）"""
        pos = self._positions.get(symbol, {"quantity": 0, "buy_date": None})
        pos["quantity"] += quantity
        pos["buy_date"] = buy_date or date.today().isoformat()
        self._positions[symbol] = pos

    def record_sell(self, symbol: str, quantity: int):
        """记录卖出"""
        pos = self._positions.get(symbol)
        if pos:
            pos["quantity"] = max(0, pos["quantity"] - quantity)

    # ────────── 规则检查函数 ──────────

    def _check_lot_size(self, quantity: int) -> Tuple[bool, str]:
        """检查最小交易单位（100股=1手）"""
        if quantity < 100:
            return False, f"A股规则: 最小交易单位100股(1手)，当前{quantity}股"
        if quantity % 100 != 0:
            return False, f"A股规则: 交易单位须为100股整数倍，当前{quantity}股"
        return True, ""

    def _check_price_limit(
        self, symbol: str, side: str, order_price: Optional[float], prev_close: float
    ) -> Tuple[bool, str]:
        """涨跌停价格校验"""
        limit_pct = self._get_limit_pct(symbol)
        limit_up = round(prev_close * (1 + limit_pct), 2)
        limit_down = round(prev_close * (1 - limit_pct), 2)

        if side == "buy" and order_price is not None and order_price > limit_up:
            return False, (
                f"A股规则: 买入价{order_price}超过涨停价{limit_up} "
                f"(昨收{prev_close}, 涨幅限制{limit_pct:.0%})"
            )
        if side == "sell" and order_price is not None and order_price < limit_down:
            return False, (
                f"A股规则: 卖出价{order_price}低于跌停价{limit_down} "
                f"(昨收{prev_close}, 跌幅限制{limit_pct:.0%})"
            )
        return True, ""

    def _check_t_plus_one(self, symbol: str, ref_date: Optional[str] = None) -> Tuple[bool, str]:
        """T+1 规则：当日买入的股票不可同日卖出"""
        pos = self._positions.get(symbol)
        if not pos or not pos.get("buy_date"):
            return True, ""
        ref = ref_date or date.today().isoformat()
        if pos["buy_date"] == ref:
            return False, f"A股规则: T+1限制 — {symbol} 今日买入不可同日卖出"
        return True, ""

    # ────────── 辅助函数 ──────────

    def _get_limit_pct(self, symbol: str) -> float:
        """根据股票代码判断涨跌停幅度"""
        # 提取纯数字代码
        code = symbol.replace(".SH", "").replace(".SZ", "").replace(".BJ", "").strip()
        # 科创板 688xxx
        if code.startswith("688"):
            return 0.20
        # 创业板 300xxx / 301xxx
        if code.startswith("300") or code.startswith("301"):
            return 0.20
        # 北交所 8xxx / 4xxx
        if code.startswith("8") or code.startswith("4"):
            return 0.30
        # ST 标识
        upper = symbol.upper()
        if "ST" in upper:
            return 0.05
        # 默认主板
        return 0.10

    def _get_prev_close(self, symbol: str) -> Optional[float]:
        """获取前收盘价"""
        if self.data_provider and hasattr(self.data_provider, "get_prev_close"):
            return self.data_provider.get_prev_close(symbol)
        return None

    @staticmethod
    def get_trading_phase() -> str:
        """
        返回当前交易阶段:
          'call_auction'  集合竞价 9:15-9:25
          'continuous'    连续竞价 9:30-11:30 / 13:00-15:00
          'lunch_break'   午休 11:30-13:00
          'closed'        休市
        """
        now = datetime.now().time()
        if AShareRulesValidator.MORNING_CALL_AUCTION_START <= now <= AShareRulesValidator.MORNING_CALL_AUCTION_END:
            return "call_auction"
        if (AShareRulesValidator.MORNING_CONTINUOUS_START <= now <= AShareRulesValidator.MORNING_CONTINUOUS_END) or \
           (AShareRulesValidator.AFTERNOON_CONTINUOUS_START <= now <= AShareRulesValidator.AFTERNOON_CONTINUOUS_END):
            return "continuous"
        if AShareRulesValidator.MORNING_CONTINUOUS_END < now < AShareRulesValidator.AFTERNOON_CONTINUOUS_START:
            return "lunch_break"
        return "closed"