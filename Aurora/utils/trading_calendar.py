"""
A股交易日历模块
支持：节假日识别、半日市判断、交易日计算、T+N日期跳转
数据源：中国证监会公布+内部维护

修补项 P0-3：A股交易日历
状态：✅ 已修补
"""
from datetime import datetime, date, timedelta
from typing import List, Optional, Set, Tuple
import json
import os
import logging

logger = logging.getLogger(__name__)


class AShareTradingCalendar:
    """
    A股交易日历
    
    功能：
    - is_trading_day(date) — 判断是否交易日
    - is_half_day(date) — 判断是否半日市
    - get_next_trading_day(date) — 获取下一个交易日
    - get_prev_trading_day(date) — 获取上一个交易日
    - t_plus_n(date, n) — T+N日期跳转（用于T+1校验）
    - is_trading_time(dt) — 判断当前是否在交易时段
    - get_trading_days_between(start, end) — 获取区间内交易日数
    """

    # A股交易时段（北京时间）
    MORNING_OPEN = (9, 30)
    MORNING_CLOSE = (11, 30)
    AFTERNOON_OPEN = (13, 0)
    AFTERNOON_CLOSE = (15, 0)
    
    # 集合竞价时段
    CALL_AUCTION_START = (9, 15)  # 集合竞价开始
    CALL_AUCTION_END = (9, 25)    # 集合竞价结束
    
    # A股固定休市日（公历节假日，需每年更新）
    # 格式: YYYY-MM-DD
    _HOLIDAYS_2025: Set[str] = {
        "2025-01-01",  # 元旦
        "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04",  # 春节
        "2025-04-04", "2025-04-07",  # 清明节
        "2025-05-01", "2025-05-02", "2025-05-05",  # 劳动节
        "2025-05-30",  # 端午节
        "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",  # 国庆+中秋
    }
    
    _HOLIDAYS_2026: Set[str] = {
        "2026-01-01", "2026-01-02",  # 元旦
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23", "2026-02-24",  # 春节（预估）
        "2026-04-03", "2026-04-06",  # 清明节
        "2026-05-01", "2026-05-04", "2026-05-05",  # 劳动节
        "2026-06-19",  # 端午节
        "2026-09-25",  # 中秋节
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆
    }
    
    # 半日市（通常为春节前最后一个交易日、元旦前等）
    _HALF_DAYS: Set[str] = {
        # 2025年半日市
        "2025-01-27",  # 春节前
        "2025-12-31",  # 元旦前
    }

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._all_holidays = set()
            cls._instance._all_holidays.update(cls._HOLIDAYS_2025)
            cls._instance._all_holidays.update(cls._HOLIDAYS_2026)
        return cls._instance

    def is_trading_day(self, check_date: date) -> bool:
        """
        判断是否为A股交易日
        
        Args:
            check_date: 待判断的日期
            
        Returns:
            True=交易日, False=非交易日
        """
        # 1. 周末不交易
        if check_date.weekday() >= 5:
            return False
        
        # 2. 节假日不交易
        date_str = check_date.strftime("%Y-%m-%d")
        if date_str in self._all_holidays:
            return False
        
        return True

    def is_half_day(self, check_date: date) -> bool:
        """
        判断是否为半日市（仅上午交易）
        
        Args:
            check_date: 待判断的日期
            
        Returns:
            True=半日市, False=全天交易或非交易日
        """
        date_str = check_date.strftime("%Y-%m-%d")
        return date_str in self._HALF_DAYS

    def get_next_trading_day(self, from_date: date, skip: int = 1) -> date:
        """
        获取从 from_date 之后第 skip 个交易日
        
        Args:
            from_date: 起始日期（不含当日）
            skip: 跳过多少个交易日，默认1
            
        Returns:
            下一个交易日的date对象
        """
        next_day = from_date
        found = 0
        max_days = skip * 3 + 10  # 安全上限
        
        for _ in range(max_days):
            next_day += timedelta(days=1)
            if self.is_trading_day(next_day):
                found += 1
                if found >= skip:
                    return next_day
        
        raise ValueError(f"无法在 {max_days} 天内找到 {skip} 个交易日，起始日期: {from_date}")

    def get_prev_trading_day(self, from_date: date, skip: int = 1) -> date:
        """
        获取从 from_date 之前第 skip 个交易日
        
        Args:
            from_date: 起始日期（不含当日）
            skip: 跳过多少个交易日，默认1
            
        Returns:
            上一个交易日的date对象
        """
        prev_day = from_date
        found = 0
        max_days = skip * 3 + 10
        
        for _ in range(max_days):
            prev_day -= timedelta(days=1)
            if self.is_trading_day(prev_day):
                found += 1
                if found >= skip:
                    return prev_day
        
        raise ValueError(f"无法在 {max_days} 天内找到 {skip} 个交易日，起始日期: {from_date}")

    def t_plus_n(self, from_date: date, n: int = 1) -> date:
        """
        T+N日期跳转（用于T+1校验）
        
        T日买入，T+N日可卖出
        A股标准：n=1 表示T+1
        
        Args:
            from_date: T日（交易日）
            n: 偏移天数
            
        Returns:
            可卖出的最早日期
        """
        result = from_date
        for _ in range(n):
            result = self.get_next_trading_day(result)
        return result

    def is_trading_time(self, dt: Optional[datetime] = None) -> bool:
        """
        判断当前是否在A股连续竞价交易时段
        
        交易时段:
        - 上午 9:30 — 11:30
        - 下午 13:00 — 15:00
        
        Args:
            dt: 待判断的datetime，默认当前时间
            
        Returns:
            True=交易时段内, False=非交易时段
        """
        if dt is None:
            dt = datetime.now()
        
        # 非交易日
        if not self.is_trading_day(dt.date()):
            return False
        
        t = (dt.hour, dt.minute)
        
        # 上午交易时段
        if self.MORNING_OPEN <= t < self.MORNING_CLOSE:
            return True
        
        # 下午交易时段
        if self.AFTERNOON_OPEN <= t < self.AFTERNOON_CLOSE:
            return True
        
        return False

    def is_call_auction_time(self, dt: Optional[datetime] = None) -> bool:
        """
        判断是否为集合竞价时段
        
        Args:
            dt: 待判断的datetime
            
        Returns:
            True=集合竞价时段
        """
        if dt is None:
            dt = datetime.now()
        
        if not self.is_trading_day(dt.date()):
            return False
        
        t = (dt.hour, dt.minute)
        return self.CALL_AUCTION_START <= t < self.CALL_AUCTION_END

    def get_trading_days_between(self, start_date: date, end_date: date) -> int:
        """
        计算两个日期之间的交易日数量（含首尾）
        
        Args:
            start_date: 起始日期
            end_date: 结束日期
            
        Returns:
            交易日数量
        """
        if start_date > end_date:
            return 0
        
        count = 0
        current = start_date
        while current <= end_date:
            if self.is_trading_day(current):
                count += 1
            current += timedelta(days=1)
        
        return count

    def get_trading_days_in_month(self, year: int, month: int) -> List[date]:
        """
        获取指定年月的所有交易日
        
        Args:
            year: 年份
            month: 月份(1-12)
            
        Returns:
            交易日列表
        """
        import calendar
        _, days_in_month = calendar.monthrange(year, month)
        trading_days = []
        
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            if self.is_trading_day(d):
                trading_days.append(d)
        
        return trading_days

    def add_holiday(self, holiday_date: date) -> None:
        """
        手动添加节假日
        """
        date_str = holiday_date.strftime("%Y-%m-%d")
        self._all_holidays.add(date_str)
        logger.info(f"手动添加节假日: {date_str}")

    def add_half_day(self, half_day_date: date) -> None:
        """
        手动添加半日市
        """
        date_str = half_day_date.strftime("%Y-%m-%d")
        self._HALF_DAYS.add(date_str)
        logger.info(f"手动添加半日市: {date_str}")

    def market_time_remaining_seconds(self, dt: Optional[datetime] = None) -> int:
        """
        计算到收盘剩余秒数
        
        Returns:
            剩余秒数，若已收盘或非交易日返回0
        """
        if dt is None:
            dt = datetime.now()
        
        if not self.is_trading_day(dt.date()):
            return 0
        
        now_h = dt.hour
        now_m = dt.minute
        now_s = dt.second
        now_seconds = now_h * 3600 + now_m * 60 + now_s
        
        morning_close_s = self.MORNING_CLOSE[0] * 3600 + self.MORNING_CLOSE[1] * 60
        afternoon_close_s = self.AFTERNOON_CLOSE[0] * 3600 + self.AFTERNOON_CLOSE[1] * 60
        afternoon_open_s = self.AFTERNOON_OPEN[0] * 3600 + self.AFTERNOON_OPEN[1] * 60
        
        # 半日市只有上午交易
        if self.is_half_day(dt.date()):
            if now_seconds < morning_close_s:
                return morning_close_s - now_seconds
            return 0
        
        # 上午交易时段剩余
        if now_seconds < morning_close_s:
            remaining = morning_close_s - now_seconds
            # 加上下午时段
            remaining += afternoon_close_s - afternoon_open_s
            return remaining
        
        # 午间休市
        if morning_close_s <= now_seconds < afternoon_open_s:
            return afternoon_close_s - afternoon_open_s
        
        # 下午交易时段
        if afternoon_open_s <= now_seconds < afternoon_close_s:
            return afternoon_close_s - now_seconds
        
        return 0


# 全局单例
_trading_calendar: Optional[AShareTradingCalendar] = None


def get_trading_calendar() -> AShareTradingCalendar:
    """获取交易日历单例"""
    global _trading_calendar
    if _trading_calendar is None:
        _trading_calendar = AShareTradingCalendar()
        logger.info("A股交易日历已初始化")
    return _trading_calendar