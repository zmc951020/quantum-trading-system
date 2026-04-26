"""
策略适配器模块
将量化交易策略与西部宽客交易平台对接

使用方法：
1. 配置API凭证（通过环境变量或配置文件）
2. 初始化策略适配器
3. 运行策略
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from xbk_trader import XbkTrader, OrderSide, OrderType, get_trader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StrategyAdapter:
    """策略适配器基类"""

    def __init__(self, trader: Optional[XbkTrader] = None):
        """
        初始化策略适配器

        Args:
            trader: 交易客户端实例，如果为None则创建默认实例
        """
        self.trader = trader or get_trader()
        self.connected = False

    def login(self, username: str, password: str) -> bool:
        """
        登录交易平台

        Args:
            username: 用户名
            password: 密码

        Returns:
            是否登录成功
        """
        result = self.trader.login(username, password)
        self.connected = result.get("code") == 0
        return self.connected

    def logout(self) -> bool:
        """登出交易平台"""
        result = self.trader.logout()
        self.connected = False
        return result.get("code") == 0

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场数据

        Args:
            symbol: 交易对符号

        Returns:
            市场数据字典
        """
        return self.trader.get_ticker(symbol)

    def get_historical_data(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """
        获取历史数据

        Args:
            symbol: 交易对符号
            interval: K线周期
            limit: 数据条数

        Returns:
            K线数据列表
        """
        result = self.trader.get_kline(symbol, interval, limit)
        return result.get("data", [])

    def get_account_balance(self) -> float:
        """
        获取账户可用余额

        Returns:
            可用余额
        """
        result = self.trader.get_account_info()
        if result.get("code") == 0:
            return result["data"].get("available", 0.0)
        return 0.0

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取指定交易对的持仓

        Args:
            symbol: 交易对符号

        Returns:
            持仓信息，如果没有持仓则返回None
        """
        result = self.trader.get_positions()
        if result.get("code") == 0:
            positions = result.get("data", [])
            for pos in positions:
                if pos.get("symbol") == symbol:
                    return pos
        return None

    def place_buy_order(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        下买入单

        Args:
            symbol: 交易对符号
            quantity: 数量
            price: 价格（限价单必填）
            order_type: 订单类型

        Returns:
            下单结果字典
        """
        return self.trader.place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=order_type,
            quantity=quantity,
            price=price
        )

    def place_sell_order(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        下卖出单

        Args:
            symbol: 交易对符号
            quantity: 数量
            price: 价格（限价单必填）
            order_type: 订单类型

        Returns:
            下单结果字典
        """
        return self.trader.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=order_type,
            quantity=quantity,
            price=price
        )

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            取消结果字典
        """
        return self.trader.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> str:
        """
        获取订单状态

        Args:
            order_id: 订单ID

        Returns:
            订单状态字符串
        """
        result = self.trader.get_order_info(order_id)
        if result.get("code") == 0:
            return result["data"].get("status", "unknown")
        return "error"

class MarketAdaptiveStrategyAdapter(StrategyAdapter):
    """
    市场自适应策略适配器
    对应 final_market_adaptive.py 策略
    """

    def __init__(self, trader: Optional[XbkTrader] = None):
        super().__init__(trader)
        self.strategy_name = "MarketAdaptiveStrategy"
        self.parameters = {
            "lookback_period": 20,
            "threshold": 0.02,
            "max_position": 0.1
        }

    def run(
        self,
        symbol: str,
        interval: str = "1h",
        capital: float = 100000.0
    ) -> Dict[str, Any]:
        """
        运行市场自适应策略

        Args:
            symbol: 交易对符号
            interval: K线周期
            capital: 起始资金

        Returns:
            策略运行结果
        """
        logger.info(f"运行{self.strategy_name}，交易对：{symbol}，周期：{interval}，资金：{capital}")

        # 获取历史数据
        klines = self.get_historical_data(symbol, interval, self.parameters["lookback_period"])
        if not klines:
            return {"code": -1, "message": "获取历史数据失败"}

        # 计算市场状态
        market_state = self._analyze_market_state(klines)

        # 获取当前持仓
        position = self.get_position(symbol)

        # 根据市场状态执行交易
        action = self._decide_action(market_state, position, capital)

        # 执行交易
        result = self._execute_action(symbol, action, capital)

        return {
            "code": 0,
            "message": "策略执行完成",
            "data": {
                "market_state": market_state,
                "action": action,
                "result": result
            }
        }

    def _analyze_market_state(self, klines: List[Dict]) -> Dict[str, Any]:
        """分析市场状态"""
        # 简化实现，实际需要根据策略逻辑实现
        closes = [k["close"] for k in klines]
        avg_close = sum(closes) / len(closes)
        current_close = closes[-1]

        trend = "up" if current_close > avg_close else "down"
        volatility = (max(closes) - min(closes)) / avg_close

        return {
            "trend": trend,
            "volatility": volatility,
            "avg_price": avg_close,
            "current_price": current_close
        }

    def _decide_action(
        self,
        market_state: Dict[str, Any],
        position: Optional[Dict],
        capital: float
    ) -> str:
        """决定交易动作"""
        has_position = position is not None and position.get("quantity", 0) > 0

        if market_state["trend"] == "up" and not has_position:
            return "buy"
        elif market_state["trend"] == "down" and has_position:
            return "sell"
        else:
            return "hold"

    def _execute_action(self, symbol: str, action: str, capital: float) -> Dict[str, Any]:
        """执行交易动作"""
        if action == "buy":
            current_price = self.get_market_data(symbol)["data"]["last_price"]
            quantity = (capital * self.parameters["max_position"]) / current_price
            return self.place_buy_order(symbol, quantity)

        elif action == "sell":
            position = self.get_position(symbol)
            if position:
                return self.place_sell_order(symbol, position["quantity"])

        return {"code": 0, "message": "无操作"}

class GridTradingStrategyAdapter(StrategyAdapter):
    """
    网格交易策略适配器
    对应 MLRangeGridTrading 策略
    """

    def __init__(self, trader: Optional[XbkTrader] = None):
        super().__init__(trader)
        self.strategy_name = "GridTradingStrategy"
        self.parameters = {
            "grid_count": 10,
            "grid_ratio": 0.02,
            "single_position": 0.05
        }

    def run(
        self,
        symbol: str,
        interval: str = "1h",
        capital: float = 100000.0
    ) -> Dict[str, Any]:
        """
        运行网格交易策略

        Args:
            symbol: 交易对符号
            interval: K线周期
            capital: 起始资金

        Returns:
            策略运行结果
        """
        logger.info(f"运行{self.strategy_name}，交易对：{symbol}，周期：{interval}，资金：{capital}")

        # 获取当前价格
        ticker = self.get_market_data(symbol)
        if ticker.get("code") != 0:
            return {"code": -1, "message": "获取行情失败"}

        current_price = ticker["data"]["last_price"]

        # 计算网格
        grids = self._calculate_grids(current_price)

        # 获取持仓
        position = self.get_position(symbol)

        # 执行网格交易
        result = self._execute_grid_trading(symbol, grids, position, capital)

        return {
            "code": 0,
            "message": "策略执行完成",
            "data": {
                "current_price": current_price,
                "grids": grids,
                "result": result
            }
        }

    def _calculate_grids(self, price: float) -> List[float]:
        """计算网格价格"""
        grids = []
        grid_ratio = self.parameters["grid_ratio"]
        for i in range(self.parameters["grid_count"]):
            grid_price = price * (1 + (i - self.parameters["grid_count"] / 2) * grid_ratio)
            grids.append(grid_price)
        return grids

    def _execute_grid_trading(
        self,
        symbol: str,
        grids: List[float],
        position: Optional[Dict],
        capital: float
    ) -> Dict[str, Any]:
        """执行网格交易"""
        results = []
        current_price = self.get_market_data(symbol)["data"]["last_price"]

        position_value = position.get("quantity", 0) * current_price if position else 0
        target_position_value = capital * self.parameters["single_position"]

        # 在网格价格附近下单
        for grid_price in grids:
            if abs(current_price - grid_price) / grid_price < 0.005:  # 价格在网格附近
                if position_value < target_position_value:
                    quantity = target_position_value / grid_price
                    result = self.place_buy_order(symbol, quantity, order_type=OrderType.LIMIT)
                    results.append(result)
                elif position_value > target_position_value:
                    if position:
                        result = self.place_sell_order(symbol, position["quantity"] / 2, order_type=OrderType.LIMIT)
                        results.append(result)

        return {"orders": results}

def create_strategy_adapter(strategy_type: str, trader: Optional[XbkTrader] = None) -> StrategyAdapter:
    """
    创建策略适配器

    Args:
        strategy_type: 策略类型 ("market_adaptive" 或 "grid_trading")
        trader: 交易客户端实例

    Returns:
        策略适配器实例
    """
    if strategy_type == "market_adaptive":
        return MarketAdaptiveStrategyAdapter(trader)
    elif strategy_type == "grid_trading":
        return GridTradingStrategyAdapter(trader)
    else:
        raise ValueError(f"未知的策略类型：{strategy_type}")

if __name__ == "__main__":
    # 测试代码
    trader = XbkTrader()
    adapter = create_strategy_adapter("market_adaptive", trader)

    # 登录（使用时请替换为实际账号密码）
    # if adapter.login("your_username", "your_password"):
    #     result = adapter.run("BTCUSDT", "1h", 100000)
    #     print(f"策略执行结果：{result}")
    #     adapter.logout()

    # 测试获取行情
    ticker = adapter.get_market_data("BTCUSDT")
    print(f"行情数据：{ticker}")
