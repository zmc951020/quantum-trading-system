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
import numpy as np

# ========== 增益性优化模块导入 ==========
strategy_performance_tracker = None
unified_risk_controller = None
rl_enhancer = None
data_quality_validator = None

try:
    from utils.strategy_performance_tracker import get_performance_tracker
    strategy_performance_tracker = get_performance_tracker()
    print("[OK] StrategyPerformanceTracker imported in real_time_trading")
except Exception as e:
    print(f"[WARNING] StrategyPerformanceTracker import failed: {e}")

try:
    from utils.unified_risk_controller import get_risk_controller
    unified_risk_controller = get_risk_controller()
    print("[OK] UnifiedRiskController imported in real_time_trading")
except Exception as e:
    print(f"[WARNING] UnifiedRiskController import failed: {e}")

try:
    from utils.rl_enhancer import get_rl_enhancer
    rl_enhancer = get_rl_enhancer()
    print("[OK] RLEnhancer imported in real_time_trading")
except Exception as e:
    print(f"[WARNING] RLEnhancer import failed: {e}")

try:
    from utils.data_quality_validator import get_data_validator
    data_quality_validator = get_data_validator()
    print("[OK] DataQualityValidator imported in real_time_trading")
except Exception as e:
    print(f"[WARNING] DataQualityValidator import failed: {e}")

# ========== 数据库维护模块导入 ==========
db_maintenance_scheduler = None
try:
    from utils.db_maintenance import DatabaseMaintenanceScheduler
    db_maintenance_scheduler = DatabaseMaintenanceScheduler()
    print("[OK] DatabaseMaintenanceScheduler imported in real_time_trading")
except Exception as e:
    print(f"[WARNING] DatabaseMaintenanceScheduler import failed: {e}")


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
            
            # 初始化RL增强器状态
            rl_state = None
            
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
                
                # ===== 增益性优化：数据质量校验 =====
                if data_quality_validator and data_quality_validator.enabled:
                    quality_data = {
                        'prices': self.performance["price_history"][-20:] if len(self.performance["price_history"]) >= 20 else self.performance["price_history"],
                        'volumes': [],
                        'timestamps': [datetime.now().isoformat()],
                    }
                    quality_report = data_quality_validator.check_data_quality(quality_data)
                    if quality_report.overall_score < 50.0:
                        logger.warning(f"数据质量评分过低 ({quality_report.overall_score:.1f})，跳过本轮交易")
                        time.sleep(self.trading_interval)
                        continue
                
                # ===== 增益性优化：RL增强器状态构建 =====
                if rl_enhancer and rl_enhancer.enabled:
                    account = self.trader.get_account_info()
                    account_data = account.get("data", {}) if account.get("code") == 0 else {}
                    
                    market_data = {
                        'price_change_pct': ((current_price - self.base_price) / self.base_price * 100) if self.base_price else 0,
                        'volatility': np.std(self.performance["price_history"][-20:]) / np.mean(self.performance["price_history"][-20:]) if len(self.performance["price_history"]) >= 20 else 0.01,
                        'rsi': 50.0,
                        'macd': 0.0,
                        'macd_signal': 0.0,
                        'adx': 25.0,
                        'atr': current_price * 0.01,
                        'close': current_price,
                        'position_pct': 0.5,
                        'unrealized_pnl_pct': 0.0,
                        'market_regime': 'range_bound',
                        'signal_confidence': 0.5,
                        'risk_score': 30.0,
                        'volume_change_pct': 0.0,
                        'momentum_short': 0.0,
                        'momentum_long': 0.0,
                        'bb_position': 0.5,
                        'rolling_sharpe': 0.0,
                        'max_drawdown': self.performance.get("max_drawdown", 0.0),
                        'trade_frequency': self.performance["total_trades"] / max((datetime.now() - self.performance["start_time"]).total_seconds() / 3600, 1),
                        'time_decay': 0.9,
                        'regime_alignment': 0.5,
                    }
                    rl_state = rl_enhancer.build_state(market_data)
                    rl_action = rl_enhancer.select_action(rl_state)
                    logger.info(f"[RL增强] 建议仓位比例: {rl_action:.4f}")
                
                # 执行完整策略逻辑
                self._execute_full_strategy(current_price)
                
                # ===== 增益性优化：RL经验存储 =====
                if rl_enhancer and rl_enhancer.enabled and rl_state is not None:
                    next_market_data = market_data.copy()
                    next_market_data['price_change_pct'] = ((current_price - self.base_price) / self.base_price * 100) if self.base_price else 0
                    next_state = rl_enhancer.build_state(next_market_data)
                    
                    # 计算奖励
                    account_after = self.trader.get_account_info()
                    account_after_data = account_after.get("data", {}) if account_after.get("code") == 0 else {}
                    portfolio_return = (account_after_data.get("total_value", 100000.0) - 100000.0) / 100000.0
                    
                    reward = rl_enhancer.compute_reward(
                        portfolio_return=portfolio_return,
                        sharpe_change=0.0,
                        drawdown_change=-self.performance.get("max_drawdown", 0.0) / 100.0,
                        trade_frequency=self.performance["total_trades"] / max((datetime.now() - self.performance["start_time"]).total_seconds() / 3600, 1) / 10.0,
                        regime_alignment=0.5,
                    )
                    rl_enhancer.store_transition(rl_state, rl_action, reward, next_state)
                    
                    # 定期更新策略
                    if self.performance["total_trades"] > 0 and self.performance["total_trades"] % 10 == 0:
                        update_stats = rl_enhancer.update_policy()
                        if update_stats.get("policy_loss", 0) > 0:
                            logger.info(f"[RL增强] 策略已更新: loss={update_stats['policy_loss']:.6f}")
                
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
        
        # ===== 增益性优化：统一风控检查 =====
        risk_override = False
        if unified_risk_controller and unified_risk_controller.enabled:
            account = self.trader.get_account_info()
            account_data = account.get("data", {}) if account.get("code") == 0 else {}
            
            risk_context = {
                'current_price': current_price,
                'base_price': self.base_price or current_price,
                'position_value': account_data.get("total_value", 0) - account_data.get("available", 0),
                'total_value': account_data.get("total_value", 100000.0),
                'available_cash': account_data.get("available", 100000.0),
                'daily_pnl': self.performance.get("total_pnl", 0.0),
                'max_drawdown': self.performance.get("max_drawdown", 0.0),
                'total_trades': self.performance["total_trades"],
                'winning_trades': self.performance["winning_trades"],
                'price_history': self.performance["price_history"],
                'volatility': np.std(self.performance["price_history"][-20:]) / np.mean(self.performance["price_history"][-20:]) if len(self.performance["price_history"]) >= 20 else 0.01,
            }
            
            risk_decision = unified_risk_controller.evaluate(risk_context)
            if risk_decision.get("action") == "halt":
                logger.warning(f"[风控] 交易暂停: {risk_decision.get('reason', '未知原因')}")
                risk_override = True
            elif risk_decision.get("action") == "reduce":
                logger.info(f"[风控] 降低仓位: {risk_decision.get('reason', '未知原因')}")
                # 降低仓位逻辑
                position = self._get_position(self.symbol)
                if position and position.get("quantity", 0) > 0:
                    reduce_qty = position["quantity"] * risk_decision.get("reduce_factor", 0.5)
                    self._place_sell_order(reduce_qty, current_price)
                return
        
        if risk_override:
            return
        
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
                            
                            # ===== 增益性优化：记录交易到性能追踪器 =====
                            if strategy_performance_tracker and strategy_performance_tracker.enabled:
                                strategy_performance_tracker.record_trade(
                                    action='buy',
                                    price=price,
                                    quantity=quantity,
                                    reason=result.get('reason', 'strategy_signal'),
                                    market_regime='range_bound',
                                    signal_confidence=0.7,
                                )
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
                        
                        # ===== 增益性优化：记录交易到性能追踪器 =====
                        if strategy_performance_tracker and strategy_performance_tracker.enabled:
                            strategy_performance_tracker.record_trade(
                                action='sell',
                                price=price,
                                quantity=quantity,
                                reason=result.get('reason', 'strategy_signal'),
                                market_regime='range_bound',
                                signal_confidence=0.7,
                            )
                    else:
                        logger.warning(f"卖出失败: {sell_result['message']}")
                else:
                    logger.warning(f"持仓不足，无法卖出: 持仓 {position.get('quantity', 0):.6f}, 需要 {quantity:.6f}")
            
            elif action == "hold":
                logger.info("策略决定: 持有")
        
        # ===== 增益性优化：更新性能追踪器 =====
        if strategy_performance_tracker and strategy_performance_tracker.enabled:
            account = self.trader.get_account_info()
            account_data = account.get("data", {}) if account.get("code") == 0 else {}
            total_value = account_data.get("total_value", 100000.0)
            
            strategy_performance_tracker.update_metrics(
                current_price=current_price,
                total_value=total_value,
                price_history=self.performance["price_history"],
            )
    
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
    
    # 启动数据库自动维护
    if db_maintenance_scheduler:
        try:
            db_maintenance_scheduler.start()
            print("[OK] 数据库自动维护调度器已启动")
        except Exception as e:
            print(f"[WARNING] 启动数据库维护调度器失败: {e}")
    
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
        
        # 停止数据库自动维护
        if db_maintenance_scheduler:
            try:
                db_maintenance_scheduler.stop()
                print("[OK] 数据库自动维护调度器已停止")
            except Exception as e:
                print(f"[WARNING] 停止数据库维护调度器失败: {e}")

        
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
