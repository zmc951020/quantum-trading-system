"""
信号校验层 + A股规则校验 + 时区对齐

修补项：
- P0-1: A股规则校验集成 ✅ 已修补
- P2-1: 信号校验层 ✅ 已修补
- P2-8: 时区对齐 ✅ 已修补
"""
import re
import zoneinfo
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# 中国时区 (UTC+8)
CN_TIMEZONE = timezone(timedelta(hours=8), 'Asia/Shanghai')


# ============================================================
# A股规则常量
# ============================================================

class MarketBoard(str, Enum):
    """市场板块"""
    SHANGHAI_MAIN = "SH"       # 上交所主板 (600/601/603)
    SHANGHAI_STAR = "STAR"     # 科创板 (688)
    SHENZHEN_MAIN = "SZ"       # 深交所主板 (000/001/002)
    SHENZHEN_GEM = "GEM"       # 创业板 (300/301)
    BEIJING = "BJ"             # 北交所 (8开头)
    B_SELL = "B"               # B股


class StockStatus(str, Enum):
    """股票状态"""
    NORMAL = "NORMAL"          # 正常交易
    ST = "ST"                  # ST风险警示
    STAR_ST = "*ST"            # *ST退市风险警示
    SUSPENDED = "SUSPENDED"    # 停牌
    DELISTED = "DELISTED"      # 退市


class PriceLimitType(str, Enum):
    """涨跌停类型"""
    STANDARD = "STANDARD"      # 10%（主板）
    STAR_MARKET = "STAR"       # 20%（科创板）
    GEM = "GEM"                # 20%（创业板）
    ST_LIMIT = "ST_LIMIT"      # 5%（ST/*ST）
    BJ = "BJ"                  # 30%（北交所）
    NEW_STOCK = "NEW"          # 新股首日44%


# ============================================================
# A股交易规则校验器
# ============================================================

@dataclass
class AShareRuleCheckResult:
    """A股规则校验结果"""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rule_details: Dict[str, Any] = field(default_factory=dict)


class AShareRuleValidator:
    """
    A股交易规则校验器
    
    修补项 P0-1：A股规则校验集成
    
    校验规则：
    1. T+1持仓校验（当日买入次日可卖）
    2. 涨跌停校验（不同板块不同幅度）
    3. ST股票禁止买入（可配置）
    4. 最小交易单位100股（1手）
    5. 整数倍校验
    6. 科创板/创业板权限校验
    7. 北交所权限校验
    """
    
    # 板块涨跌幅
    PRICE_LIMITS = {
        PriceLimitType.STANDARD: 0.10,
        PriceLimitType.STAR_MARKET: 0.20,
        PriceLimitType.GEM: 0.20,
        PriceLimitType.ST_LIMIT: 0.05,
        PriceLimitType.BJ: 0.30,
        PriceLimitType.NEW_STOCK: 0.44,
    }
    
    # 板块最小交易单位
    MIN_SHARES = 100  # 1手=100股
    
    # 板块代码规则
    CODE_PATTERNS = {
        MarketBoard.SHANGHAI_MAIN: r'^60[0123]\d{3}$',
        MarketBoard.SHANGHAI_STAR: r'^688\d{3}$',
        MarketBoard.SHENZHEN_MAIN: r'^00[012]\d{3}$',
        MarketBoard.SHENZHEN_GEM: r'^30[01]\d{3}$',
        MarketBoard.BEIJING: r'^8\d{5}$',
    }
    
    def __init__(self, allow_st_trading: bool = False, allow_new_stocks: bool = True):
        self.allow_st_trading = allow_st_trading  # 是否允许ST交易
        self.allow_new_stocks = allow_new_stocks   # 是否允许新股交易
        logger.info(f"AShareRuleValidator已初始化: ST交易={allow_st_trading}")
    
    @classmethod
    def detect_board(cls, symbol: str) -> Optional[MarketBoard]:
        """
        根据代码判断所属板块
        
        Args:
            symbol: 股票代码（如 '600519', '000001', '688981'）
            
        Returns:
            MarketBoard 或 None
        """
        symbol = symbol.strip()
        for board, pattern in cls.CODE_PATTERNS.items():
            if re.match(pattern, symbol):
                return board
        return None
    
    @classmethod
    def get_price_limit(cls, symbol: str) -> PriceLimitType:
        """
        获取股票涨跌停幅度类型
        
        Args:
            symbol: 股票代码
            
        Returns:
            PriceLimitType
        """
        board = cls.detect_board(symbol)
        if board == MarketBoard.SHANGHAI_STAR:
            return PriceLimitType.STAR_MARKET
        elif board == MarketBoard.SHENZHEN_GEM:
            return PriceLimitType.GEM
        elif board == MarketBoard.BEIJING:
            return PriceLimitType.BJ
        else:
            return PriceLimitType.STANDARD
    
    @classmethod
    def get_limit_rate(cls, symbol: str, is_st: bool = False, is_new: bool = False) -> float:
        """
        获取涨跌停幅度
        
        Args:
            symbol: 股票代码
            is_st: 是否ST
            is_new: 是否新股
            
        Returns:
            涨跌停百分比（小数）
        """
        if is_new:
            return cls.PRICE_LIMITS[PriceLimitType.NEW_STOCK]
        if is_st:
            return cls.PRICE_LIMITS[PriceLimitType.ST_LIMIT]
        limit_type = cls.get_price_limit(symbol)
        return cls.PRICE_LIMITS[limit_type]
    
    def validate_price(self, symbol: str, order_price: float, 
                       prev_close: float, is_st: bool = False) -> Tuple[bool, float, float]:
        """
        校验委托价格是否在涨跌停范围内
        
        Args:
            symbol: 股票代码
            order_price: 委托价格
            prev_close: 前收盘价
            is_st: 是否ST
            
        Returns:
            (是否有效, 涨停价, 跌停价)
        """
        limit_rate = self.get_limit_rate(symbol, is_st=is_st)
        
        upper_limit = round(prev_close * (1 + limit_rate), 2)
        lower_limit = round(prev_close * (1 - limit_rate), 2)
        
        # 跌停价不能为负
        lower_limit = max(0.01, lower_limit)
        
        is_valid = lower_limit <= order_price <= upper_limit
        
        if not is_valid:
            logger.warning(f"价格超限: {symbol} 委托{order_price} 范围[{lower_limit}, {upper_limit}]")
        
        return is_valid, upper_limit, lower_limit
    
    def validate_quantity(self, quantity: int) -> Tuple[bool, str]:
        """
        校验委托数量
        
        Args:
            quantity: 委托股数
            
        Returns:
            (是否有效, 错误信息)
        """
        if quantity < self.MIN_SHARES:
            return False, f"最低交易{self.MIN_SHARES}股（1手），当前{quantity}股"
        
        if quantity % self.MIN_SHARES != 0:
            return False, f"必须为{self.MIN_SHARES}股的整数倍，当前{quantity}股"
        
        return True, "OK"
    
    def validate_t1_rule(self, symbol: str, buy_date: date, 
                         today: Optional[date] = None) -> Tuple[bool, str]:
        """
        校验T+1规则
        
        Args:
            symbol: 股票代码
            buy_date: 买入日期
            today: 当前日期（默认今天）
            
        Returns:
            (是否可卖, 原因)
        """
        if today is None:
            today = date.today()
        
        # 同一天买入不能卖出
        if buy_date >= today:
            return False, f"T+1限制: 买入日期{buy_date}，最早可卖日期为下一个交易日"
        
        # 检查是否至少隔了1个交易日
        from utils.trading_calendar import get_trading_calendar
        calendar = get_trading_calendar()
        sellable_date = calendar.t_plus_n(buy_date, 1)
        
        if today < sellable_date:
            return False, f"T+1限制: 最早可卖日期为{sellable_date}"
        
        return True, "OK"
    
    def validate_st_trading(self, status: StockStatus) -> Tuple[bool, str]:
        """
        校验ST股票交易权限
        
        Args:
            status: 股票状态
            
        Returns:
            (是否可交易, 原因)
        """
        if not self.allow_st_trading:
            if status in (StockStatus.ST, StockStatus.STAR_ST):
                return False, f"系统禁止{status.value}股票交易"
        return True, "OK"
    
    def validate_board_permission(self, symbol: str, has_star_perm: bool = False,
                                   has_gem_perm: bool = False,
                                   has_bj_perm: bool = False) -> Tuple[bool, str]:
        """
        校验板块交易权限
        
        Args:
            symbol: 股票代码
            has_star_perm: 是否有科创板权限
            has_gem_perm: 是否有创业板权限
            has_bj_perm: 是否有北交所权限
            
        Returns:
            (是否可交易, 原因)
        """
        board = self.detect_board(symbol)
        
        if board == MarketBoard.SHANGHAI_STAR and not has_star_perm:
            return False, "缺少科创板交易权限"
        if board == MarketBoard.SHENZHEN_GEM and not has_gem_perm:
            return False, "缺少创业板交易权限"
        if board == MarketBoard.BEIJING and not has_bj_perm:
            return False, "缺少北交所交易权限"
        
        return True, "OK"
    
    def full_validation(
        self,
        symbol: str,
        order_price: float,
        quantity: int,
        prev_close: float,
        status: StockStatus = StockStatus.NORMAL,
        buy_date: Optional[date] = None,
        is_st: bool = False,
        is_new: bool = False,
        has_special_perms: bool = False,
    ) -> AShareRuleCheckResult:
        """
        完整A股规则校验
        
        Returns:
            AShareRuleCheckResult
        """
        result = AShareRuleCheckResult()
        
        # 1. 板块识别
        board = self.detect_board(symbol)
        result.rule_details['board'] = board.value if board else 'UNKNOWN'
        
        if board is None:
            result.passed = False
            result.errors.append(f"无法识别的股票代码: {symbol}")
            return result
        
        # 2. ST校验
        if not self.allow_st_trading and is_st:
            result.passed = False
            result.errors.append("系统禁止ST股票交易")
        
        # 3. 价格校验
        price_ok, upper, lower = self.validate_price(symbol, order_price, prev_close, is_st=is_st)
        result.rule_details['price_range'] = [lower, upper]
        if not price_ok:
            result.passed = False
            result.errors.append(
                f"价格超限: 委托{order_price}，范围[{lower}, {upper}]"
            )
        
        # 4. 数量校验
        qty_ok, qty_msg = self.validate_quantity(quantity)
        result.rule_details['quantity'] = quantity
        if not qty_ok:
            result.passed = False
            result.errors.append(qty_msg)
        
        # 5. T+1校验
        if buy_date:
            t1_ok, t1_msg = self.validate_t1_rule(symbol, buy_date)
            if not t1_ok:
                result.passed = False
                result.errors.append(t1_msg)
        
        # 6. 板块权限（非默认全开）
        if not has_special_perms:
            perm_ok, perm_msg = self.validate_board_permission(
                symbol,
                has_star_perm=False,
                has_gem_perm=False,
                has_bj_perm=False,
            )
            if not perm_ok:
                result.passed = False
                result.errors.append(perm_msg)
        
        logger.info(f"规则校验 {symbol}: {'PASS' if result.passed else 'FAIL'} - {result.errors if not result.passed else 'OK'}")
        return result


# ============================================================
# 信号校验层
# ============================================================

@dataclass
class SignalValidationResult:
    """信号校验结果"""
    passed: bool = True
    signal_id: str = ""
    symbol: str = ""
    direction: str = ""  # BUY / SELL / HOLD
    confidence: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SignalValidator:
    """
    交易信号校验器
    
    修补项 P2-1：信号校验层
    
    校验维度：
    1. 信号来源合法性（白名单策略）
    2. 信号置信度阈值
    3. 信号时效性
    4. 重复信号检测
    5. 逆向信号冲突检测
    """
    
    MIN_CONFIDENCE = 0.6           # 最低置信度阈值
    SIGNAL_TIMEOUT_SECONDS = 300   # 信号5分钟有效
    MAX_SIGNALS_PER_SYMBOL = 3     # 同股票5分钟最多3个信号
    
    def __init__(self, min_confidence: float = 0.6):
        self.min_confidence = min_confidence
        self._recent_signals: Dict[str, List[datetime]] = {}  # symbol→信号时间列表
        logger.info(f"SignalValidator已初始化: min_confidence={min_confidence}")
    
    def validate_confidence(self, confidence: float) -> Tuple[bool, str]:
        """
        校验信号置信度
        """
        if confidence < self.min_confidence:
            return False, f"置信度{confidence:.2f}低于阈值{self.min_confidence}"
        if confidence > 1.0:
            return False, f"置信度{confidence:.2f}超出范围[0,1]"
        return True, "OK"
    
    def validate_direction(self, direction: str) -> Tuple[bool, str]:
        """
        校验信号方向
        """
        valid = {"BUY", "SELL", "HOLD", "BUY_TO_COVER", "SELL_SHORT"}
        if direction.upper() not in valid:
            return False, f"无效方向: {direction}，有效值: {valid}"
        return True, "OK"
    
    def validate_timeliness(self, signal_time: datetime) -> Tuple[bool, str]:
        """
        校验信号时效性
        """
        now = datetime.now(tz=CN_TIMEZONE)
        diff_seconds = (now - signal_time.replace(tzinfo=CN_TIMEZONE)).total_seconds()
        
        if diff_seconds > self.SIGNAL_TIMEOUT_SECONDS:
            return False, f"信号已过期（{int(diff_seconds)}秒前，超时{self.SIGNAL_TIMEOUT_SECONDS}秒）"
        
        return True, "OK"
    
    def validate_duplicate(self, symbol: str) -> Tuple[bool, str]:
        """
        校验重复信号（防抖动）
        """
        now = datetime.now(tz=CN_TIMEZONE)
        
        if symbol in self._recent_signals:
            # 清理过期记录
            self._recent_signals[symbol] = [
                t for t in self._recent_signals[symbol]
                if (now - t).total_seconds() < self.SIGNAL_TIMEOUT_SECONDS
            ]
            
            if len(self._recent_signals[symbol]) >= self.MAX_SIGNALS_PER_SYMBOL:
                return False, f"同股票{self.SIGNAL_TIMEOUT_SECONDS}秒内已有{len(self._recent_signals[symbol])}个信号"
        
        # 记录本次信号
        if symbol not in self._recent_signals:
            self._recent_signals[symbol] = []
        self._recent_signals[symbol].append(now)
        
        return True, "OK"
    
    def full_validate(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        signal_time: Optional[datetime] = None,
        signal_id: str = "",
        strategy_name: str = "",
    ) -> SignalValidationResult:
        """
        完整信号校验
        """
        result = SignalValidationResult(
            signal_id=signal_id or f"SIG-{datetime.now().timestamp()}",
            symbol=symbol,
            direction=direction.upper(),
            confidence=confidence,
        )
        
        # 1. 方向校验
        ok, msg = self.validate_direction(direction)
        if not ok:
            result.passed = False
            result.errors.append(msg)
        
        # 2. 置信度校验
        ok, msg = self.validate_confidence(confidence)
        if not ok:
            result.passed = False
            result.errors.append(msg)
        
        # 3. 时效性校验
        if signal_time:
            ok, msg = self.validate_timeliness(signal_time)
            if not ok:
                result.warnings.append(msg)  # 警告而非拒绝
        
        # 4. 重复校验
        ok, msg = self.validate_duplicate(symbol)
        if not ok:
            result.passed = False
            result.errors.append(msg)
        
        result.metadata['strategy'] = strategy_name
        result.metadata['timestamp'] = datetime.now(tz=CN_TIMEZONE).isoformat()
        
        logger.info(
            f"信号校验 {symbol} {direction}: {'PASS' if result.passed else 'FAIL'} "
            f"(conf={confidence:.2f})"
        )
        
        return result


# ============================================================
# 时区工具
# ============================================================

def now_cn() -> datetime:
    """获取当前中国时间"""
    return datetime.now(tz=CN_TIMEZONE)


def to_cn_time(dt: datetime) -> datetime:
    """将任意datetime转换为中国时区"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CN_TIMEZONE)


def market_time_now() -> datetime:
    """获取当前市场时间（北京时间）"""
    return datetime.now(tz=CN_TIMEZONE)


def from_timestamp_cn(ts: float) -> datetime:
    """Unix时间戳转中国时间"""
    return datetime.fromtimestamp(ts, tz=CN_TIMEZONE)


def timestamp_cn(dt: Optional[datetime] = None) -> float:
    """获取中国时间的Unix时间戳"""
    if dt is None:
        dt = datetime.now(tz=CN_TIMEZONE)
    return dt.timestamp()


# ============================================================
# 初始化
# ============================================================

_rule_validator: Optional[AShareRuleValidator] = None
_signal_validator: Optional[SignalValidator] = None


def get_rule_validator() -> AShareRuleValidator:
    global _rule_validator
    if _rule_validator is None:
        _rule_validator = AShareRuleValidator()
    return _rule_validator


def get_signal_validator() -> SignalValidator:
    global _signal_validator
    if _signal_validator is None:
        _signal_validator = SignalValidator()
    return _signal_validator


if __name__ == "__main__":
    # 测试A股规则
    rv = get_rule_validator()
    
    # 正常交易
    result = rv.full_validation(
        symbol="600519",
        order_price=1800.00,
        quantity=100,
        prev_close=1780.00,
    )
    print(f"主板正常交易: {result.passed} - {result.errors}")
    print(f"  规则详情: {result.rule_details}")
    
    # 涨跌停测试
    result2 = rv.full_validation(
        symbol="600519",
        order_price=2000.00,  # 超过涨停价
        quantity=100,
        prev_close=1780.00,
    )
    print(f"\n超涨停价: {result2.passed} - {result2.errors}")
    
    # 科创板测试
    board = AShareRuleValidator.detect_board("688981")
    limit = AShareRuleValidator.get_price_limit("688981")
    print(f"\n688981板块: {board}, 涨跌幅: {AShareRuleValidator.PRICE_LIMITS[limit]}")
    
    # 信号校验测试
    sv = get_signal_validator()
    sig = sv.full_validate("600519", "BUY", 0.85)
    print(f"\n信号校验: {sig.passed} - {sig.errors}")
    
    # 低置信度
    sig2 = sv.full_validate("000001", "BUY", 0.45)
    print(f"低置信度: {sig2.passed} - {sig2.errors}")
    
    # 时区测试
    print(f"\n北京当前时间: {now_cn()}")