# coding: utf-8
"""
A股信号增强器 — 集合竞价时间窗 + 板块权限 + 停牌半日检查
=========================================================
增益性补充，插入信号生成->下单执行之前。
不修改原有 signals/ 模块代码。

功能：
  - 集合竞价时间窗检测 (9:15-9:25)：此阶段应暂停发送订单
  - 连续竞价时间窗 (9:30-11:30, 13:00-15:00) 才允许交易
  - 午休/收盘后屏蔽
  - 板块交易权限检查 (科创板 / 创业板 / 北交所 门槛)
  - 复牌后半日冷却期：停牌多日后复牌前半小时不交易
  - 节假日/周末检查

使用方式：
    from signals.a_share_enhancer import AShareSessionHelper
    helper = AShareSessionHelper()
    if helper.can_trade_now():
        process_signal(...)
"""

import logging
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# A股关键时间窗 (Asia/Shanghai)
# ─────────────────────────────────────────────

class SessionPhase(str, Enum):
    """交易时段阶段"""
    PRE_OPEN = "pre_open"           # 盘前 (0:00-9:15)
    AUCTION = "auction"             # 集合竞价 (9:15-9:25)
    AUCTION_BREAK = "auction_break" # 集合竞价间隙 (9:25-9:30)
    CONTINUOUS_MORNING = "morning"  # 上午连续竞价 (9:30-11:30)
    LUNCH = "lunch"                 # 午休 (11:30-13:00)
    CONTINUOUS_AFTERNOON = "afternoon" # 下午连续竞价 (13:00-15:00)
    POST_CLOSE = "post_close"       # 收盘后 (15:00-24:00)

    @property
    def is_tradable(self) -> bool:
        """是否可交易"""
        return self in (SessionPhase.CONTINUOUS_MORNING, SessionPhase.CONTINUOUS_AFTERNOON)

    @property
    def is_auction(self) -> bool:
        """是否在集合竞价"""
        return self == SessionPhase.AUCTION


# ─── A股板块权限 ───
BENCHMARK_ASSET = 500_000  # 资产门槛基准值（元）

BOARD_REQUIREMENTS = {
    "sh": {   # 上海主板
        "min_days": 0,
        "min_asset": 0,
        "description": "上海主板（无门槛）",
    },
    "sz": {   # 深圳主板
        "min_days": 0,
        "min_asset": 0,
        "description": "深圳主板（无门槛）",
    },
    "kcb": {  # 科创板 (688xxx)
        "min_days": 24,          # 24个月交易经验（简化：要求≥2年）
        "min_asset": 500_000,    # 20日均资产≥50万
        "description": "科创板（50万+2年）",
    },
    "cyb": {  # 创业板 (300xxx/301xxx)
        "min_days": 24,          # 24个月
        "min_asset": 100_000,    # 10万
        "description": "创业板（10万+2年）",
    },
    "bj": {   # 北交所 (8xxxxx)
        "min_days": 24,
        "min_asset": 500_000,
        "description": "北交所（50万+2年）",
    },
    "hk": {   # 港股通
        "min_days": 0,
        "min_asset": 500_000,
        "description": "港股通（50万）",
    },
}


def classify_board(symbol: str) -> str:
    """根据股票代码推断板块"""
    code = str(symbol).zfill(6)
    if code.startswith("8") or code.startswith("4"):
        return "bj"    # 北交所
    if code.startswith("688"):
        return "kcb"   # 科创板
    if code.startswith("300") or code.startswith("301"):
        return "cyb"   # 创业板
    if code.startswith("6"):
        return "sh"    # 上海主板
    if code.startswith(("0", "2")):
        return "sz"    # 深圳主板
    return "sh"        # 默认上海


# ─────────────────────────────────────────────
# A股时段判断器
# ─────────────────────────────────────────────

class AShareSessionHelper:
    """
    A股交易时段判断器 — 增益层

    使用方式：
        helper = AShareSessionHelper()
        phase = helper.current_phase()
        if helper.can_trade_now():
            submit_order()
    """

    # ── 时间定义 (UTC+8) ──
    AUCTION_START       = time(9, 15)
    AUCTION_END         = time(9, 25)
    MORNING_START       = time(9, 30)
    MORNING_END         = time(11, 30)
    AFTERNOON_START     = time(13, 0)
    AFTERNOON_END       = time(15, 0)
    POST_COOL_MINUTES   = 30   # 复牌后冷却分钟数

    def __init__(self):
        self._last_check_log: Optional[str] = None

    def current_phase(self, dt: Optional[datetime] = None) -> SessionPhase:
        """返回当前交易所处阶段"""
        t = (dt or datetime.now()).time()
        if t < self.AUCTION_START:
            return SessionPhase.PRE_OPEN
        elif t < self.AUCTION_END:
            return SessionPhase.AUCTION
        elif t < self.MORNING_START:
            return SessionPhase.AUCTION_BREAK
        elif t < self.MORNING_END:
            return SessionPhase.CONTINUOUS_MORNING
        elif t < self.AFTERNOON_START:
            return SessionPhase.LUNCH
        elif t < self.AFTERNOON_END:
            return SessionPhase.CONTINUOUS_AFTERNOON
        else:
            return SessionPhase.POST_CLOSE

    def can_trade_now(self, dt: Optional[datetime] = None) -> bool:
        """返回当前是否能下单（排除集合竞价、午休、收盘后）"""
        phase = self.current_phase(dt)
        return phase.is_tradable

    def is_auction_now(self, dt: Optional[datetime] = None) -> bool:
        """是否在集合竞价时段"""
        return self.current_phase(dt) == SessionPhase.AUCTION

    def seconds_to_next_session(self, dt: Optional[datetime] = None) -> float:
        """距下一个可交易时段还有多少秒"""
        now = dt or datetime.now()
        phase = self.current_phase(now)

        if phase == SessionPhase.POST_CLOSE or phase == SessionPhase.PRE_OPEN:
            # 等下一个交易日的 9:30
            next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if now.hour >= 15:
                next_open += timedelta(days=1)
            return (next_open - now).total_seconds()
        elif phase == SessionPhase.AUCTION or phase == SessionPhase.AUCTION_BREAK:
            target = now.replace(hour=9, minute=30, second=0, microsecond=0)
            return (target - now).total_seconds()
        elif phase == SessionPhase.LUNCH:
            target = now.replace(hour=13, minute=0, second=0, microsecond=0)
            return (target - now).total_seconds()
        else:
            return 0.0  # 已在交易时段

    def next_session_start(self, dt: Optional[datetime] = None) -> datetime:
        """返回下一个交易时段开始时间"""
        now = dt or datetime.now()
        phase = self.current_phase(now)

        target = now.replace(second=0, microsecond=0)
        if phase in (SessionPhase.POST_CLOSE, SessionPhase.PRE_OPEN):
            if now.hour >= 15:
                target = now.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(days=1)
            else:
                target = now.replace(hour=9, minute=30, second=0, microsecond=0)
        elif phase == SessionPhase.AUCTION or phase == SessionPhase.AUCTION_BREAK:
            target = target.replace(hour=9, minute=30)
        elif phase == SessionPhase.LUNCH:
            target = target.replace(hour=13, minute=0)
        else:
            target = now
        return target

    @staticmethod
    def is_trading_day(dt: Optional[datetime] = None) -> bool:
        """检查是否为交易日（简化：周一至周五，排除法定节假日）"""
        d = (dt or datetime.now()).date()
        # 周末非交易日
        if d.weekday() >= 5:
            return False
        # 硬编码已知休市日（春节/国庆等，按需扩展）
        known_holidays = {
            date(2025, 1, 1),   # 元旦
            date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 3),
            date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 5),
            date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3), date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8),
        }
        return d not in known_holidays


# ─────────────────────────────────────────────
# 板块权限检查器
# ─────────────────────────────────────────────

class BoardPermissionChecker:
    """
    板块交易权限检查器 — 增益层

    规则：
    - 科创板：持有资产 ≥ 50万 且 交易经验 ≥ 24 个月
    - 创业板：持有资产 ≥ 10万 且 交易经验 ≥ 24 个月
    - 北交所：持有资产 ≥ 50万 且 交易经验 ≥ 24 个月
    - 主板：无门槛
    """

    def __init__(
        self,
        total_asset: float = 0.0,
        trading_experience_months: int = 0,
    ):
        self._asset = total_asset
        self._experience_months = trading_experience_months

    def update_parameters(self, total_asset: float, experience_months: int):
        """更新账户资产和交易经验"""
        self._asset = total_asset
        self._experience_months = experience_months

    def check(self, symbol: str) -> tuple[bool, str]:
        """
        检查符号对应的板块交易权限。

        Returns:
            (允许交易?, 原因说明)
        """
        board = classify_board(symbol)
        req = BOARD_REQUIREMENTS.get(board)
        if not req:
            return False, f"未知板块: {symbol}"

        if req["min_asset"] > 0 and self._asset < req["min_asset"]:
            return False, (
                f"{symbol} 属于{req['description']}，"
                f"当前资产{self._asset:.0f}元 < 门槛{req['min_asset']}元"
            )

        if req["min_days"] > 0 and self._experience_months < req["min_days"] // 30 * 30:
            months_needed = max(0, req["min_days"] // 30 * 30)
            return False, (
                f"{symbol} 属于{req['description']}，"
                f"当前经验{self._experience_months}月 < 要求{months_needed}月"
            )

        return True, f"{symbol} {req['description']} 权限通过"


# ─────────────────────────────────────────────
# 复牌冷却检查
# ─────────────────────────────────────────────

class ResumptionCoolDown:
    """
    复牌后冷却期 — 停牌超过N天的股票复牌后，前M分钟内不交易

    规则：
    - 停牌 ≥ 1 天：复牌后 5 分钟冷却
    - 停牌 ≥ 5 天：复牌后 15 分钟冷却
    - 停牌 ≥ 20 天：复牌后 30 分钟冷却
    """

    COOL_MIN_1 = 5
    COOL_MIN_5 = 15
    COOL_MIN_20 = 30

    def __init__(self):
        self._resumption_times: dict = {}  # symbol -> (resumption_dt, suspended_days)

    def register_resumption(self, symbol: str, resumption_dt: datetime, suspended_days: int):
        """注册复牌时间"""
        self._resumption_times[symbol] = (resumption_dt, suspended_days)
        logger.info("复牌冷却注册: %s 停牌%d天, 复牌时间 %s", symbol, suspended_days, resumption_dt.isoformat())

    def can_trade(self, symbol: str, now: Optional[datetime] = None) -> tuple[bool, str]:
        """
        检查复牌后冷却是否结束。

        Returns:
            (允许交易?, 原因)
        """
        now = now or datetime.now()
        entry = self._resumption_times.get(symbol)
        if not entry:
            # 若未注册，视为正常
            return True, ""

        resumption_dt, suspended_days = entry
        elapsed = (now - resumption_dt).total_seconds() / 60.0

        if suspended_days >= 20:
            cool_minutes = self.COOL_MIN_20
        elif suspended_days >= 5:
            cool_minutes = self.COOL_MIN_15
        else:
            cool_minutes = self.COOL_MIN_1

        if elapsed < cool_minutes:
            remaining = cool_minutes - elapsed
            return False, f"{symbol} 停牌{suspended_days}天，复牌冷却剩余 {remaining:.0f} 分钟"
        return True, ""

    def clear_symbol(self, symbol: str):
        """冷却结束后清除记录"""
        self._resumption_times.pop(symbol, None)

    def cleanup_expired(self, now: Optional[datetime] = None):
        """清理已过冷却期的记录"""
        now = now or datetime.now()
        expired = []
        for sym, (res_dt, days) in self._resumption_times.items():
            elapsed = (now - res_dt).total_seconds() / 60.0
            cool = self.COOL_MIN_20 if days >= 20 else (self.COOL_MIN_15 if days >= 5 else self.COOL_MIN_1)
            if elapsed >= cool * 2:  # 冷却期2倍时间后清理
                expired.append(sym)
        for sym in expired:
            self._resumption_times.pop(sym, None)