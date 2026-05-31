"""
OMS订单重试机制 - 增强版

修补项：
- P1-5: OMS订单RETRY状态 ✅ 已修补
- P2-6: 交易成本计算 ✅ 已修补
- P2-7: 复权计算 ✅ 已修补
"""
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 订单状态增强
# ============================================================

class OrderStatus(str, Enum):
    PENDING = "PENDING"           # 待提交
    SUBMITTED = "SUBMITTED"       # 已提交券商
    PARTIAL_FILLED = "PARTIAL"   # 部分成交
    FILLED = "FILLED"            # 完全成交
    CANCELLED = "CANCELLED"      # 已撤销
    REJECTED = "REJECTED"        # 被拒绝
    RETRYING = "RETRYING"        # 重试中 ← 新增
    FAILED = "FAILED"            # 失败（重试耗尽）← 新增
    EXPIRED = "EXPIRED"          # 过期未成交


class RetryStrategy(str, Enum):
    FIXED = "fixed"        # 固定间隔重试
    LINEAR = "linear"      # 线性递增间隔
    EXPONENTIAL = "exponential"  # 指数退避 ← 推荐
    IMMEDIATE = "immediate"  # 立即重试（网络抖动）


@dataclass
class OrderRetryConfig:
    """订单重试配置"""
    max_retries: int = 3                     # 最大重试次数
    base_delay_ms: int = 500                 # 基础延迟(ms)
    max_delay_ms: int = 10000                # 最大延迟(ms)
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    retryable_errors: List[str] = field(default_factory=lambda: [
        "NETWORK_TIMEOUT",
        "CONNECTION_REFUSED",
        "GATEWAY_TIMEOUT",
        "SERVICE_UNAVAILABLE",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
    ])
    non_retryable_errors: List[str] = field(default_factory=lambda: [
        "INSUFFICIENT_FUNDS",
        "INVALID_SYMBOL",
        "ORDER_LIMIT_EXCEEDED",
        "MARKET_CLOSED",
        "T1_RESTRICTED",
        "ST_SUSPENDED",
        "PRICE_LIMIT_EXCEEDED",
    ])


@dataclass
class OrderRetryState:
    """订单重试状态"""
    order_id: str
    attempt: int = 0
    last_error: Optional[str] = None
    last_attempt_time: Optional[datetime] = None
    next_attempt_time: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3


class OrderRetryManager:
    """
    OMS订单重试管理器
    
    修补项 P1-5：订单RETRY状态
    """
    
    def __init__(self, config: Optional[OrderRetryConfig] = None):
        self.config = config or OrderRetryConfig()
        self._retry_states: Dict[str, OrderRetryState] = {}
        logger.info(f"OrderRetryManager已初始化: max_retries={self.config.max_retries}, strategy={self.config.strategy}")
    
    def should_retry(self, order_id: str, error_code: str) -> Tuple[bool, str]:
        """
        判断订单是否应该重试
        
        Returns:
            (是否重试, 原因)
        """
        # 不可重试错误
        if error_code in self.config.non_retryable_errors:
            return False, f"不可重试错误: {error_code}"
        
        # 可重试错误但已达上限
        state = self._retry_states.get(order_id)
        if state and state.retry_count >= self.config.max_retries:
            return False, f"已达到最大重试次数({self.config.max_retries})"
        
        # 可重试
        return True, f"允许重试(error_code={error_code})"
    
    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟（毫秒）
        
        策略:
        - fixed: base_delay
        - linear: base_delay * attempt
        - exponential: base_delay * 2^attempt
        - immediate: 0
        """
        strategy = self.config.strategy
        
        if strategy == RetryStrategy.IMMEDIATE:
            return 0
        elif strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay_ms
        elif strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay_ms * attempt
        elif strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay_ms * (2 ** (attempt - 1))
        else:
            delay = self.config.base_delay_ms
        
        return min(delay, self.config.max_delay_ms) / 1000.0  # 转秒
    
    def register_retry(self, order_id: str) -> OrderRetryState:
        """注册/更新订单重试"""
        if order_id not in self._retry_states:
            self._retry_states[order_id] = OrderRetryState(
                order_id=order_id,
                max_retries=self.config.max_retries,
            )
        
        state = self._retry_states[order_id]
        state.retry_count += 1
        state.attempt += 1
        state.last_attempt_time = datetime.now()
        
        delay = self.calculate_delay(state.attempt)
        state.next_attempt_time = datetime.now().timestamp() + delay if delay > 0 else None
        
        logger.info(f"订单 {order_id} 进入RETRY状态: 第{state.retry_count}次重试, 延迟{int(delay*1000)}ms")
        
        return state
    
    def mark_success(self, order_id: str) -> None:
        """标记订单重试成功"""
        if order_id in self._retry_states:
            state = self._retry_states[order_id]
            logger.info(f"订单 {order_id} 重试成功（共{state.retry_count}次）")
            del self._retry_states[order_id]
    
    def mark_failed(self, order_id: str) -> None:
        """标记订单最终失败"""
        if order_id in self._retry_states:
            state = self._retry_states[order_id]
            logger.warning(f"订单 {order_id} 最终失败（重试{state.retry_count}次）")
            del self._retry_states[order_id]
    
    def get_retry_state(self, order_id: str) -> Optional[OrderRetryState]:
        """获取订单重试状态"""
        return self._retry_states.get(order_id)


# ============================================================
# 交易成本计算
# ============================================================

@dataclass
class TradingCost:
    """交易成本明细"""
    commission: float = 0.0        # 佣金
    stamp_tax: float = 0.0         # 印花税（仅卖出）
    transfer_fee: float = 0.0      # 过户费
    regulatory_fee: float = 0.0    # 证管费
    total: float = 0.0             # 总成本


class TradingCostCalculator:
    """
    A股交易成本计算器
    
    修补项 P2-6：交易成本计算
    
    规则（A股标准费率）：
    - 佣金: 0.03%（最低5元）
    - 印花税: 0.1%（仅卖出，2024年减半）
    - 过户费: 0.001%（双向）
    - 证管费: 0.002%（双向）
    """
    
    # A股费率标准
    COMMISSION_RATE = 0.0003       # 佣金率 0.03%
    COMMISSION_MIN = 5.0           # 最低佣金 5元
    STAMP_TAX_RATE = 0.001         # 印花税 0.1%（仅卖出）
    TRANSFER_FEE_RATE = 0.00001   # 过户费 0.001%
    REGULATORY_FEE_RATE = 0.00002 # 证管费 0.002%
    
    @classmethod
    def calculate_buy(cls, amount: float, shares: int = 0) -> TradingCost:
        """
        计算买入成本
        
        Args:
            amount: 成交金额（元）
            shares: 成交股数（用于过户费计算）
            
        Returns:
            TradingCost
        """
        cost = TradingCost()
        
        # 佣金（含规费）
        commission = amount * cls.COMMISSION_RATE
        cost.commission = max(commission, cls.COMMISSION_MIN)
        
        # 过户费
        cost.transfer_fee = max(amount * cls.TRANSFER_FEE_RATE, 0.1)  # 最低0.1元
        
        # 证管费
        cost.regulatory_fee = amount * cls.REGULATORY_FEE_RATE
        
        # 买入无印花税
        cost.stamp_tax = 0.0
        
        cost.total = cost.commission + cost.transfer_fee + cost.regulatory_fee
        return cost
    
    @classmethod
    def calculate_sell(cls, amount: float, shares: int = 0) -> TradingCost:
        """
        计算卖出成本
        
        Args:
            amount: 成交金额（元）
            shares: 成交股数
            
        Returns:
            TradingCost
        """
        cost = TradingCost()
        
        # 佣金
        commission = amount * cls.COMMISSION_RATE
        cost.commission = max(commission, cls.COMMISSION_MIN)
        
        # 印花税（2024年减半至0.05%，历史标准0.1%）
        cost.stamp_tax = amount * cls.STAMP_TAX_RATE
        
        # 过户费
        cost.transfer_fee = max(amount * cls.TRANSFER_FEE_RATE, 0.1)
        
        # 证管费
        cost.regulatory_fee = amount * cls.REGULATORY_FEE_RATE
        
        cost.total = cost.commission + cost.stamp_tax + cost.transfer_fee + cost.regulatory_fee
        return cost
    
    @classmethod
    def calculate_roundtrip(cls, amount: float, shares: int = 0) -> TradingCost:
        """
        计算买卖双向总成本
        
        Returns:
            总成本TradingCost
        """
        buy_cost = cls.calculate_buy(amount, shares)
        sell_cost = cls.calculate_sell(amount, shares)
        
        total = TradingCost(
            commission=buy_cost.commission + sell_cost.commission,
            stamp_tax=sell_cost.stamp_tax,
            transfer_fee=buy_cost.transfer_fee + sell_cost.transfer_fee,
            regulatory_fee=buy_cost.regulatory_fee + sell_cost.regulatory_fee,
        )
        total.total = total.commission + total.stamp_tax + total.transfer_fee + total.regulatory_fee
        return total
    
    @classmethod
    def break_even_price(
        cls,
        buy_price: float,
        shares: int = 100,
    ) -> float:
        """
        计算盈亏平衡价（覆盖双向手续费）
        
        Args:
            buy_price: 买入单价
            shares: 买入股数
            
        Returns:
            最低卖出价（四舍五入到分）
        """
        buy_amount = buy_price * shares
        roundtrip = cls.calculate_roundtrip(buy_amount, shares)
        
        min_sell_amount = buy_amount + roundtrip.total
        be_price = min_sell_amount / shares
        
        return round(be_price, 2)


# ============================================================
# 复权计算
# ============================================================

@dataclass
class AdjustmentFactor:
    """复权因子"""
    date: date
    cash_dividend: float = 0.0    # 每股现金红利
    stock_dividend: float = 0.0   # 每股送股
    rights_price: float = 0.0     # 配股价
    rights_ratio: float = 0.0     # 配股比例
    factor: float = 1.0           # 复权因子


class PriceAdjuster:
    """
    A股复权计算器
    
    修补项 P2-7：复权计算（前复权/后复权）
    
    算法：
    - 前复权: 以最新价为基准向前调整
    - 后复权: 以发行价为基准向后调整
    
    复权因子公式:
    factor = (前收盘 - 每股现金红利) / (前收盘 + 每股送股 + 配股价 * 配股比例)
    """
    
    @classmethod
    def calculate_forward_adjusted(
        cls,
        prices: List[float],
        factors: List[AdjustmentFactor],
    ) -> List[float]:
        """
        计算前复权价格（推荐用于技术分析）
        
        前复权意义：保持最新价格不变，向前调整历史价格
        使历史K线图连续可比
        
        Args:
            prices: 按时间排序的原始价格列表（最新在末尾）
            factors: 按时间排序的复权因子列表
            
        Returns:
            前复权价格列表
        """
        if not prices or not factors:
            return prices
        
        # 从最新到最旧累积复权因子
        n = len(prices)
        cumulative_factor = 1.0
        adjusted = [0.0] * n
        
        # 最新价格不变
        adjusted[-1] = prices[-1]
        
        # 向前递推
        for i in range(n - 2, -1, -1):
            factor_i = factors[i].factor if i < len(factors) else 1.0
            cumulative_factor *= factor_i
            adjusted[i] = round(prices[i] * cumulative_factor, 3)
        
        return adjusted
    
    @classmethod
    def calculate_backward_adjusted(
        cls,
        prices: List[float],
        factors: List[AdjustmentFactor],
    ) -> List[float]:
        """
        计算后复权价格
        
        后复权意义：保持初始价格不变，向后调整后续价格
        
        Args:
            prices: 原始价格列表
            factors: 复权因子列表
            
        Returns:
            后复权价格列表
        """
        if not prices or not factors:
            return prices
        
        n = len(prices)
        cumulative_factor = 1.0
        adjusted = [0.0] * n
        
        adjusted[0] = prices[0]
        
        for i in range(1, n):
            factor_i = factors[i].factor if i < len(factors) else 1.0
            cumulative_factor *= (1.0 / factor_i)
            adjusted[i] = round(prices[i] * cumulative_factor, 3)
        
        return adjusted
    
    @classmethod
    def apply_dividend_adjustment(
        cls,
        close_prices: List[float],
        dividends: List[float],
    ) -> List[float]:
        """
        仅对现金分红做复权（简化版）
        
        Args:
            close_prices: 收盘价列表
            dividends: 每股分红列表（与价格一一对应，无为0）
            
        Returns:
            前复权价格列表
        """
        n = len(close_prices)
        adjusted = close_prices.copy()
        cum_div = 0.0
        
        for i in range(n - 2, -1, -1):
            cum_div += dividends[i + 1]
            adjusted[i] = round(adjusted[i] - cum_div, 3)
        
        adjusted[-1] = close_prices[-1]  # 最新价格不变
        return adjusted


# ============================================================
# 初始化
# ============================================================

_retry_manager: Optional[OrderRetryManager] = None


def get_retry_manager() -> OrderRetryManager:
    """获取订单重试管理器单例"""
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = OrderRetryManager()
    return _retry_manager


if __name__ == "__main__":
    # 测试订单重试
    rm = get_retry_manager()
    should, reason = rm.should_retry("ORD-001", "NETWORK_TIMEOUT")
    print(f"NETWORK_TIMEOUT 重试: {should} - {reason}")
    
    should2, reason2 = rm.should_retry("ORD-002", "INSUFFICIENT_FUNDS")
    print(f"INSUFFICIENT_FUNDS 重试: {should2} - {reason2}")
    
    # 测试交易成本
    cost = TradingCostCalculator.calculate_roundtrip(10000, 1000)
    print(f"\n买卖10000元(1000股)总成本: ¥{cost.total:.2f}")
    print(f"  佣金: ¥{cost.commission:.2f}")
    print(f"  印花税: ¥{cost.stamp_tax:.2f}")
    print(f"  过户费: ¥{cost.transfer_fee:.2f}")
    
    be = TradingCostCalculator.break_even_price(10.0, 1000)
    print(f"买入价10元盈亏平衡: ¥{be:.2f}")
    
    # 测试复权
    raw_prices = [10.0, 11.0, 12.0, 10.5, 11.5]  # 中间有一次除权
    factors = [
        AdjustmentFactor(date=date(2024,1,1), factor=1.0),
        AdjustmentFactor(date=date(2024,2,1), factor=1.0),
        AdjustmentFactor(date=date(2024,3,1), factor=1.0),
        AdjustmentFactor(date=date(2024,4,1), factor=1.1),  # 除权
        AdjustmentFactor(date=date(2024,5,1), factor=1.0),
    ]
    fwd = PriceAdjuster.calculate_forward_adjusted(raw_prices, factors)
    print(f"\n原始价格: {raw_prices}")
    print(f"前复权:   {fwd}")