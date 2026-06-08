#!/usr/bin/env python3
"""
实时行情轮询机制（Real-time Market Data Polling）

核心能力：
  1. 支持订阅多个股票
  2. 定时轮询实时行情数据
  3. 触发回调通知（价格变动、涨跌幅预警等）
  4. 支持启动/停止控制
  5. 线程安全设计

使用方式：
    from core.realtime_poller import get_realtime_poller

    poller = get_realtime_poller()

    # 订阅股票
    poller.subscribe("000001", callback=my_callback)

    # 启动轮询
    poller.start(poll_interval=5)  # 每5秒轮询一次

    # 停止轮询
    poller.stop()
"""

import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from core.data_bus import get_data_bus

# ============================================================
# 实时行情数据结构
# ============================================================

class RealTimeData:
    """实时行情数据"""
    def __init__(self, symbol: str, price: float, change_pct: float,
                 volume: float, amount: float, source: str = ""):
        self.symbol = symbol
        self.price = price
        self.change_pct = change_pct
        self.volume = volume
        self.amount = amount
        self.source = source
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "price": round(self.price, 2),
            "change_pct": round(self.change_pct, 2),
            "volume": int(self.volume),
            "amount": round(self.amount, 2),
            "source": self.source,
            "timestamp": self.timestamp.isoformat()
        }

# ============================================================
# 订阅回调类型
# ============================================================

class CallbackType:
    """回调类型"""
    PRICE_CHANGE = "price_change"      # 价格变动
    PERCENT_CHANGE = "percent_change"  # 涨跌幅变化
    VOLUME_ALERT = "volume_alert"      # 成交量预警
    ANY = "any"                        # 任意变化

# ============================================================
# 订阅者信息
# ============================================================

class Subscriber:
    """订阅者信息"""
    def __init__(self, callback: Callable, callback_type: str = CallbackType.ANY,
                 threshold: float = 0.0):
        self.callback = callback
        self.callback_type = callback_type
        self.threshold = threshold
        self.last_price = 0.0
        self.last_change_pct = 0.0

# ============================================================
# 实时行情轮询器
# ============================================================

class RealTimePoller:
    """实时行情轮询器"""

    def __init__(self):
        self._bus = None
        self._subscribers: Dict[str, List[Subscriber]] = {}
        self._is_running = False
        self._poll_thread = None
        self._poll_interval = 5  # 默认5秒
        self._lock = threading.Lock()
        self._last_data: Dict[str, RealTimeData] = {}

    def _init_bus(self):
        """延迟初始化数据总线"""
        if self._bus is None:
            self._bus = get_data_bus()

    def subscribe(self, symbol: str, callback: Callable,
                  callback_type: str = CallbackType.ANY, threshold: float = 0.0) -> bool:
        """订阅股票实时行情

        Args:
            symbol: 股票代码
            callback: 回调函数，签名: callback(data: RealTimeData)
            callback_type: 回调类型
            threshold: 触发阈值（如涨跌幅超过多少才触发）

        Returns:
            bool: 是否订阅成功
        """
        with self._lock:
            if symbol not in self._subscribers:
                self._subscribers[symbol] = []

            # 检查是否已订阅
            for sub in self._subscribers[symbol]:
                if sub.callback == callback:
                    return False

            self._subscribers[symbol].append(Subscriber(
                callback=callback,
                callback_type=callback_type,
                threshold=threshold
            ))

        print(f"[RealTimePoller] 已订阅: {symbol}")
        return True

    def unsubscribe(self, symbol: str, callback: Callable = None) -> bool:
        """取消订阅

        Args:
            symbol: 股票代码
            callback: 回调函数（None表示取消所有该股票的订阅）

        Returns:
            bool: 是否取消成功
        """
        with self._lock:
            if symbol not in self._subscribers:
                return False

            if callback is None:
                del self._subscribers[symbol]
                print(f"[RealTimePoller] 已取消订阅所有: {symbol}")
                return True

            self._subscribers[symbol] = [
                sub for sub in self._subscribers[symbol]
                if sub.callback != callback
            ]

            if not self._subscribers[symbol]:
                del self._subscribers[symbol]

            print(f"[RealTimePoller] 已取消订阅: {symbol}")
            return True

    def get_subscribed_symbols(self) -> List[str]:
        """获取已订阅的股票列表"""
        with self._lock:
            return list(self._subscribers.keys())

    def start(self, poll_interval: int = 5):
        """启动轮询

        Args:
            poll_interval: 轮询间隔（秒）
        """
        if self._is_running:
            return

        self._poll_interval = poll_interval
        self._is_running = True
        self._init_bus()

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        print(f"[RealTimePoller] 已启动，轮询间隔: {poll_interval}秒")

    def stop(self):
        """停止轮询"""
        self._is_running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        print("[RealTimePoller] 已停止")

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._is_running

    def _poll_loop(self):
        """轮询主循环"""
        while self._is_running:
            try:
                self._poll_once()
            except Exception as e:
                print(f"[RealTimePoller] 轮询异常: {e}")

            time.sleep(self._poll_interval)

    def _poll_once(self):
        """执行一次轮询"""
        if not self._bus:
            return

        symbols = self.get_subscribed_symbols()
        if not symbols:
            return

        for symbol in symbols:
            try:
                # 获取实时数据
                data = self._bus.get_realtime(symbol)
                if data:
                    realtime_data = RealTimeData(
                        symbol=symbol,
                        price=data.get("price", 0),
                        change_pct=data.get("change_pct", 0),
                        volume=data.get("volume", 0),
                        amount=data.get("amount", 0),
                        source=data.get("source", "")
                    )
                    self._last_data[symbol] = realtime_data
                    self._notify_subscribers(symbol, realtime_data)
            except Exception as e:
                print(f"[RealTimePoller] 获取 {symbol} 实时数据失败: {e}")

    def _notify_subscribers(self, symbol: str, data: RealTimeData):
        """通知订阅者"""
        subscribers = self._subscribers.get(symbol, [])
        if not subscribers:
            return

        for sub in subscribers:
            try:
                # 根据回调类型判断是否触发
                should_notify = False

                if sub.callback_type == CallbackType.ANY:
                    should_notify = True
                elif sub.callback_type == CallbackType.PERCENT_CHANGE:
                    if abs(data.change_pct - sub.last_change_pct) >= sub.threshold:
                        should_notify = True
                elif sub.callback_type == CallbackType.PRICE_CHANGE:
                    if sub.last_price > 0 and \
                       abs(data.price - sub.last_price) >= sub.threshold:
                        should_notify = True
                elif sub.callback_type == CallbackType.VOLUME_ALERT:
                    if data.volume >= sub.threshold:
                        should_notify = True

                if should_notify:
                    sub.callback(data)
                    sub.last_price = data.price
                    sub.last_change_pct = data.change_pct

            except Exception as e:
                print(f"[RealTimePoller] 回调执行失败: {e}")

    def get_last_data(self, symbol: str) -> Optional[RealTimeData]:
        """获取最后一次获取的实时数据"""
        return self._last_data.get(symbol)

    def get_all_last_data(self) -> Dict[str, RealTimeData]:
        """获取所有股票的最后实时数据"""
        return dict(self._last_data)

# ============================================================
# 全局单例
# ============================================================

_global_poller = None
_global_poller_lock = threading.Lock()

def get_realtime_poller() -> RealTimePoller:
    """获取实时行情轮询器单例"""
    global _global_poller
    if _global_poller is None:
        with _global_poller_lock:
            if _global_poller is None:
                _global_poller = RealTimePoller()
    return _global_poller

# ============================================================
# 示例回调函数
# ============================================================

def example_callback(data: RealTimeData):
    """示例回调函数"""
    print(f"[{data.timestamp.strftime('%H:%M:%S')}] {data.symbol}: "
          f"{data.price:.2f} ({data.change_pct:.2f}%)")

def percent_alert_callback(data: RealTimeData):
    """涨跌幅预警回调"""
    if abs(data.change_pct) >= 5:
        print(f"⚠️ 涨跌幅预警 {data.symbol}: {data.change_pct:.2f}%")

# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    poller = get_realtime_poller()

    # 订阅股票
    poller.subscribe("000001", example_callback, CallbackType.ANY)
    poller.subscribe("000001", percent_alert_callback, CallbackType.PERCENT_CHANGE)
    poller.subscribe("000002", example_callback, CallbackType.ANY)

    # 启动轮询
    poller.start(poll_interval=3)

    print("\n实时行情轮询器运行中... (按 Ctrl+C 停止)")
    print(f"已订阅: {poller.get_subscribed_symbols()}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止轮询器")
        poller.stop()
