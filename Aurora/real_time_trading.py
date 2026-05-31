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
import json
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


# ═══════════════════════════════════════════════════════════════
# AI交易顾问（Smart Model Router集成）
# ═══════════════════════════════════════════════════════════════

class AIAdvisor:
    """
    AI交易顾问 — 接入 Smart Model Router
    根据任务重要性自动路由到合适AI后端（Ollama本地 → DeepSeek → Qwen）

    优先级路由：
    - P0 交易决策 → DeepSeek V4（最高精度，本地降级备选）
    - P1 策略分析 → DeepSeek/Qwen（平衡精度与速度）
    - P2 数据分析 → Qwen（高吞吐，适合批量）
    - P3 报告生成 → Ollama本地（零费用，可接受延迟）
    """

    def __init__(self):
        self._ready = False
        try:
            from model_integration import (
                get_router, ask_ai, ask_trading,
                ask_strategy, ask_data, ask_report, ask_log
            )
            self.get_router = get_router
            self.ask_ai = ask_ai
            self.ask_trading = ask_trading
            self.ask_strategy = ask_strategy
            self.ask_data = ask_data
            self.ask_report = ask_report
            self.ask_log = ask_log
            self._ready = True
            logger.info("[AIAdvisor] ✓ 已接入Smart Model Router")
        except ImportError:
            logger.warning("[AIAdvisor] ✗ model_integration 未安装，AI功能不可用")
        except Exception as e:
            logger.warning(f"[AIAdvisor] ✗ 初始化失败: {e}")

    @property
    def is_ready(self) -> bool:
        """AI顾问是否就绪"""
        return self._ready

    def analyze_market_condition(
        self, symbol: str, price: float,
        indicators: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        P1优先级：AI分析当前市场状态
        辅助策略判断市场趋势、仓位建议、支撑阻力位

        Args:
            symbol: 交易品种
            price: 当前价格
            indicators: 技术指标字典

        Returns:
            {
                "content": "AI分析文本",
                "market_state": "strong_bullish/weak_bullish/ranging/weak_bearish/strong_bearish/unknown",
                "position_advice": 0.3,  # 建议仓位比例
                "support": 支撑价,
                "resistance": 阻力价
            }
        """
        if not self._ready:
            return {"content": "AI未就绪", "market_state": "unknown"}

        prompt = (
            f"分析当前{symbol}市场状态：\n"
            f"  当前价格: {price}\n"
            f"  技术指标: {json.dumps(indicators or {}, ensure_ascii=False)}\n\n"
            f"请判断并以JSON格式返回：\n"
            f"  1. market_state: 市场状态（strong_bullish/weak_bullish/ranging/weak_bearish/strong_bearish）\n"
            f"  2. position_advice: 建议仓位比例（0.0-1.0）\n"
            f"  3. support: 关键支撑位\n"
            f"  4. resistance: 关键阻力位\n"
            f"  5. summary: 一句话总结"
        )

        try:
            result = self.ask_strategy(prompt, temperature=0.3)
            return result
        except Exception as e:
            logger.error(f"[AIAdvisor] 市场分析失败: {e}")
            return {"content": f"分析失败: {e}", "market_state": "unknown"}

    def evaluate_trade_signal(
        self, symbol: str, signal_type: str,
        price: float, quantity: float
    ) -> Dict[str, Any]:
        """
        P0优先级：AI评估交易信号（核心交易决策，不容降级）
        在实盘下单前进行AI二次确认

        Args:
            symbol: 交易品种
            signal_type: 信号类型（buy/sell）
            price: 当前价格
            quantity: 计划数量

        Returns:
            {
                "content": "评估文本",
                "approved": True/False,
                "reason": "决策理由",
                "risk_level": "low/medium/high/critical",
                "stop_loss": 建议止损价
            }
        """
        if not self._ready:
            return {
                "content": "AI未就绪，跳过信号评估",
                "approved": False,
                "reason": "AI不可用"
            }

        prompt = (
            f"评估以下交易信号（核心交易决策）：\n"
            f"  品种: {symbol}\n"
            f"  信号类型: {signal_type}\n"
            f"  当前价格: {price}\n"
            f"  计划数量: {quantity}\n\n"
            f"请判断并以JSON格式返回：\n"
            f"  1. approved: 是否批准此交易（true/false）\n"
            f"  2. reason: 决策理由\n"
            f"  3. risk_level: 风险等级（low/medium/high/critical）\n"
            f"  4. stop_loss: 建议止损价格"
        )

        try:
            result = self.ask_trading(prompt, temperature=0.1)
            return result
        except Exception as e:
            logger.error(f"[AIAdvisor] 信号评估失败: {e}")
            return {"content": f"评估失败: {e}", "approved": False, "reason": str(e)}

    def generate_daily_report(
        self, trades: List[Dict], pnl: float, win_rate: float
    ) -> Dict[str, Any]:
        """
        P3优先级：生成每日交易报告
        使用本地Ollama模型零费用生成

        Args:
            trades: 交易记录列表
            pnl: 总盈亏
            win_rate: 胜率

        Returns:
            {"content": "报告文本"}
        """
        if not self._ready:
            return {
                "content": (
                    f"AI未就绪，跳过报告生成。\n"
                    f"交易数: {len(trades)}, 盈亏: {pnl:.2f}, 胜率: {win_rate:.1%}"
                )
            }

        prompt = (
            f"生成今日交易报告摘要：\n"
            f"  交易笔数: {len(trades)}\n"
            f"  总盈亏: {pnl:.4f}\n"
            f"  胜率: {win_rate:.1%}\n"
            f"  最近交易: {json.dumps(trades[-10:], ensure_ascii=False, indent=2)[:500]}\n\n"
            f"请用简洁中文总结今日表现，包括亮点和需要改进的地方。"
        )

        try:
            return self.ask_report(prompt, temperature=0.5)
        except Exception as e:
            logger.error(f"[AIAdvisor] 报告生成失败: {e}")
            return {"content": f"报告生成失败: {e}"}

    def get_cost_summary(self) -> Dict[str, Any]:
        """
        获取AI费用摘要
        查看各模型的调用次数和费用分布
        """
        if not self._ready:
            return {"status": "unavailable"}
        try:
            from model_integration import get_router_stats, get_model_distribution
            return {
                "stats": get_router_stats(),
                "distribution": get_model_distribution(),
            }
        except Exception as e:
            return {"error": str(e)}


# ── 全局AI顾问单例 ──
_ai_advisor = None
_ai_advisor_lock = threading.Lock()


def get_ai_advisor() -> AIAdvisor:
    """
    获取全局AI顾问单例（线程安全）
    在交易策略中可通过此函数获取AI辅助能力
    """
    global _ai_advisor
    if _ai_advisor is None:
        with _ai_advisor_lock:
            if _ai_advisor is None:
                _ai_advisor = AIAdvisor()
    return _ai_advisor


# ── 入口 ──
if __name__ == "__main__":
    # 运行实时模拟
    run_real_time_simulation(
        initial_balance=100000.0,
        duration_seconds=60,  # 先运行1分钟测试
        trading_interval=5,   # 快速测试5秒间隔
        symbol="BTCUSDT"
    )