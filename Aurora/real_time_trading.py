#!/usr/bin/env python3
"""
实时交易引擎
运行策略进行实时模拟交易
"""
import os
import sys
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('real_time_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xbk_simulator import XbkSimulatedTrader, OrderType, OrderSide
from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
import pandas as pd


class StrategyRunner:
    """
    策略运行器
    管理策略的实时运行
    """
    
    def __init__(
        self,
        trader: XbkSimulatedTrader,
        strategy_name: str = "Final Market Adaptive Grid",
        trading_interval: int = 180,  # 3分钟
        symbol: str = "BTCUSDT"
    ):
        """
        初始化策略运行器
        
        Args:
            trader: 交易客户端
            strategy_name: 策略名称
            trading_interval: 交易间隔（秒）
            symbol: 交易对
        """
        self.trader = trader
        self.strategy_name = strategy_name
        self.trading_interval = trading_interval
        self.symbol = symbol
        
        # 运行状态
        self.running = False
        self.thread = None
        
        # 性能统计
        self.performance = {
            "start_time": None,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "price_history": []
        }
        
        # 初始化完整策略
        self.strategy = None
        self.base_price = None
        
        logger.info(f"策略运行器初始化: {strategy_name}")
    
    def _run_loop(self):
        """
        策略运行主循环
        """
        self.performance["start_time"] = datetime.now()
        logger.info(f"策略开始运行: {self.strategy_name}")
        logger.info(f"交易间隔: {self.trading_interval}秒")
        logger.info(f"交易对: {self.symbol}")
        
        try:
            # 获取初始价格并初始化策略
            ticker = self.trader.get_ticker(self.symbol)
            if ticker.get("code") != 0:
                logger.error(f"获取初始价格失败: {ticker}")
                return
            
            self.base_price = ticker["data"]["last_price"]
            logger.info(f"初始价格: {self.base_price:.4f}")
            
            # 初始化完整策略
            self.strategy = FinalMarketAdaptiveGrid(
                base_price=self.base_price,
                initial_balance=100000.0
            )
            logger.info("Final Market Adaptive Grid 策略初始化完成")
            
            while self.running:
                # 获取市场数据
                ticker = self.trader.get_ticker(self.symbol)
                if ticker.get("code") != 0:
                    logger.warning(f"获取行情失败: {ticker}")
                    time.sleep(self.trading_interval)
                    continue
                
                current_price = ticker["data"]["last_price"]
                self.performance["price_history"].append(current_price)
                
                # 记录价格
                logger.info(f"当前价格: {current_price:.4f}")
                
                # 执行完整策略逻辑
                self._execute_full_strategy(current_price)
                
                # 显示账户信息
                self._display_account_info()
                
                # 等待下一个交易周期
                time.sleep(self.trading_interval)
                
        except Exception as e:
            logger.error(f"策略运行错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            logger.info("策略停止运行")
    
    def _execute_full_strategy(self, current_price: float):
        """
        执行完整的策略逻辑
        
        Args:
            current_price: 当前价格
        """
        if not self.strategy:
            logger.error("策略未初始化")
            return
        
        # 构建价格数据
        price_series = pd.Series(self.performance["price_history"])
        
        # 执行策略
        result = self.strategy.update_price(current_price, price_series)
        
        # 处理交易结果
        if result and result.get("action"):
            action = result["action"]
            quantity = result.get("quantity", 0)
            price = current_price
            
            if action == "buy":
                # 计算买入金额
                buy_amount = quantity * price
                # 检查可用资金
                account = self.trader.get_account_info()
                if account.get("code") == 0:
                    available = account["data"]["available"]
                    if available >= buy_amount:
                        # 执行买入
                        buy_result = self.trader.place_order(
                            symbol=self.symbol,
                            side=OrderSide.BUY,
                            order_type=OrderType.MARKET,
                            quantity=quantity
                        )
                        if buy_result.get("code") == 0:
                            self.performance["total_trades"] += 1
                            logger.info(f"买入成功: {quantity:.6f} @ {price:.4f} - 原因: {result.get('reason')}")
                        else:
                            logger.warning(f"买入失败: {buy_result['message']}")
                    else:
                        logger.warning(f"资金不足，无法买入: 可用 {available:.2f}, 需要 {buy_amount:.2f}")
            
            elif action == "sell":
                # 检查持仓
                position = self._get_position(self.symbol)
                if position and position.get("quantity", 0) >= quantity:
                    # 执行卖出
                    sell_result = self.trader.place_order(
                        symbol=self.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=quantity
                    )
                    if sell_result.get("code") == 0:
                        self.performance["total_trades"] += 1
                        self.performance["winning_trades"] += 1
                        logger.info(f"卖出成功: {quantity:.6f} @ {price:.4f} - 原因: {result.get('reason')}")
                    else:
                        logger.warning(f"卖出失败: {sell_result['message']}")
                else:
                    logger.warning(f"持仓不足，无法卖出: 持仓 {position.get('quantity', 0):.6f}, 需要 {quantity:.6f}")
            
            elif action == "hold":
                logger.info("策略决定: 持有")
    
    def _get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            持仓信息
        """
        positions = self.trader.get_positions()
        if positions.get("code") != 0:
            return None
        
        for pos in positions.get("data", []):
            if pos["symbol"] == symbol:
                return pos
        
        return None
    
    def _place_buy_order(self, quantity: float, price: float):
        """
        下单买入
        
        Args:
            quantity: 数量
            price: 价格
        """
        result = self.trader.place_order(
            symbol=self.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity
        )
        
        if result.get("code") == 0:
            self.performance["total_trades"] += 1
            logger.info(f"买入成功: {quantity:.6f} @ {price:.4f}")
        else:
            logger.warning(f"买入失败: {result['message']}")
    
    def _place_sell_order(self, quantity: float, price: float):
        """
        下单卖出
        
        Args:
            quantity: 数量
            price: 价格
        """
        result = self.trader.place_order(
            symbol=self.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity
        )
        
        if result.get("code") == 0:
            self.performance["total_trades"] += 1
            self.performance["winning_trades"] += 1  # 简化处理
            logger.info(f"卖出成功: {quantity:.6f} @ {price:.4f}")
        else:
            logger.warning(f"卖出失败: {result['message']}")
    
    def _display_account_info(self):
        """
        显示账户信息
        """
        account = self.trader.get_account_info()
        if account.get("code") != 0:
            return
        
        data = account["data"]
        logger.info(f"账户信息: 余额={data['balance']:.2f}, "
                    f"可用={data['available']:.2f}, "
                    f"总资产={data['total_value']:.2f}")
    
    def start(self):
        """
        启动策略
        """
        if self.running:
            logger.warning("策略已经在运行中")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("策略已启动")
    
    def stop(self):
        """
        停止策略
        """
        if not self.running:
            logger.warning("策略未在运行")
            return
        
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        logger.info("策略已停止")
    
    def get_performance(self) -> Dict[str, Any]:
        """
        获取策略性能
        
        Returns:
            性能数据
        """
        # 计算运行时间
        if self.performance["start_time"]:
            duration = datetime.now() - self.performance["start_time"]
            self.performance["duration_seconds"] = duration.total_seconds()
        else:
            self.performance["duration_seconds"] = 0
        
        return self.performance


def run_real_time_simulation(
    initial_balance: float = 100000.0,
    duration_seconds: int = 3600,  # 运行1小时
    trading_interval: int = 10,  # 快速测试使用10秒间隔
    symbol: str = "BTCUSDT"
):
    """
    运行实时模拟交易
    
    Args:
        initial_balance: 初始资金
        duration_seconds: 运行时长
        trading_interval: 交易间隔
        symbol: 交易对
    """
    print("=" * 70)
    print("西部宽客平台 - 实时模拟交易")
    print("=" * 70)
    
    # 创建交易客户端
    print(f"\n1. 初始化模拟交易平台...")
    trader = XbkSimulatedTrader(initial_balance=initial_balance)
    print(f"   初始资金: {initial_balance:.2f}")
    
    # 登录
    print("\n2. 登录...")
    login_result = trader.login("user", "password")
    print(f"   登录结果: {login_result['message']}")
    
    # 创建策略运行器
    print(f"\n3. 初始化策略...")
    runner = StrategyRunner(
        trader=trader,
        strategy_name="ML Range Grid (Simulated)",
        trading_interval=trading_interval,
        symbol=symbol
    )
    
    # 启动策略
    print(f"\n4. 启动实时交易...")
    print(f"   运行时长: {duration_seconds} 秒")
    print(f"   交易间隔: {trading_interval} 秒")
    print(f"   按 Ctrl+C 停止")
    print("\n" + "=" * 70)
    
    try:
        runner.start()
        
        # 等待指定时长
        time.sleep(duration_seconds)
        
    except KeyboardInterrupt:
        print("\n\n收到停止信号")
    finally:
        # 停止策略
        runner.stop()
        
        # 显示性能报告
        print("\n" + "=" * 70)
        print("策略运行结束 - 性能报告")
        print("=" * 70)
        
        performance = runner.get_performance()
        print(f"\n运行时间: {performance.get('duration_seconds', 0):.0f} 秒")
        print(f"总交易次数: {performance['total_trades']}")
        
        # 显示最终账户信息
        account = trader.get_account_info()
        if account.get("code") == 0:
            data = account["data"]
            print(f"\n最终账户:")
            print(f"  初始资金: {initial_balance:.2f}")
            print(f"  最终资金: {data['total_value']:.2f}")
            print(f"  收益率: {((data['total_value'] - initial_balance) / initial_balance * 100):.2f}%")
        
        print("\n" + "=" * 70)
        print("模拟交易完成！")
        print("=" * 70)


if __name__ == "__main__":
    # 运行实时模拟
    run_real_time_simulation(
        initial_balance=100000.0,
        duration_seconds=60,  # 先运行1分钟测试
        trading_interval=5,   # 快速测试5秒间隔
        symbol="BTCUSDT"
    )
