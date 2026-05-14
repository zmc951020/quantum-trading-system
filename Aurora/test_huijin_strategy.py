#!/usr/bin/env python3
"""
汇金价值AI轮动策略测试脚本
测试策略的各项功能
"""

import logging
import sys
import os

# 添加汇金价值AI轮动策略的路径
huijin_path = r"D:\Gupiao\量化交易测试设备方案\攒机\量化交易\汇金价值AI轮动策略"
sys.path.insert(0, huijin_path)

# 添加Aurora策略路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.huijin_value_strategy import HuijinValueStrategy
from strategy_engine import HuijinValueStrategyEngine, SignalType, StrategyState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('HuijinStrategyTest')


def test_strategy_initialization():
    """测试策略初始化"""
    logger.info("=== 测试策略初始化 ===")
    try:
        strategy = HuijinValueStrategy(initial_balance=100000)
        logger.info(f"策略初始化成功: {type(strategy).__name__}")
        logger.info(f"初始资金: {strategy.initial_balance}")
        logger.info(f"当前资金: {strategy.current_balance}")
        logger.info(f"当前状态: {strategy.get_market_state()}")
        logger.info("策略初始化测试通过")
        return strategy
    except Exception as e:
        logger.error(f"策略初始化失败: {e}")
        return None


def test_market_scan(strategy):
    """测试盘前扫描"""
    logger.info("\n=== 测试盘前扫描 ===")
    try:
        candidates = strategy.scan_market()
        logger.info(f"盘前扫描完成，找到 {len(candidates)} 个候选股票")
        logger.info("盘前扫描测试通过")
        return candidates
    except Exception as e:
        logger.error(f"盘前扫描失败: {e}")
        return []


def test_signal_generation(strategy):
    """测试信号生成"""
    logger.info("\n=== 测试信号生成 ===")
    try:
        signals = strategy.engine.generate_signals()
        logger.info(f"生成了 {len(signals)} 个交易信号")
        for signal in signals:
            logger.info(f"  信号: {signal.signal_type.value} - {signal.symbol}")
        logger.info("信号生成测试通过")
        return signals
    except Exception as e:
        logger.error(f"信号生成失败: {e}")
        return []


def test_risk_control(strategy):
    """测试风控检查"""
    logger.info("\n=== 测试风控检查 ===")
    try:
        alerts = strategy.engine.check_risk_controls()
        logger.info(f"风控检查完成，生成 {len(alerts)} 个预警")
        for alert in alerts:
            logger.info(f"  预警: {alert.reason}")
        logger.info("风控检查测试通过")
        return alerts
    except Exception as e:
        logger.error(f"风控检查失败: {e}")
        return []


def test_strategy_update(strategy):
    """测试策略更新"""
    logger.info("\n=== 测试策略更新 ===")
    try:
        # 模拟价格更新
        for i in range(5):
            current_price = 50000 + i * 100
            result = strategy.update_price(current_price)
            logger.info(f"价格更新: {current_price}, 结果: {result}")
        logger.info("策略更新测试通过")
    except Exception as e:
        logger.error(f"策略更新失败: {e}")


def test_performance(strategy):
    """测试性能指标"""
    logger.info("\n=== 测试性能指标 ===")
    try:
        performance = strategy.get_performance()
        logger.info(f"性能指标: {performance}")
        logger.info(f"总收益率: {performance.get('total_return', 0) * 100:.2f}%")
        logger.info(f"胜率: {performance.get('win_rate', 0) * 100:.2f}%")
        logger.info("性能指标测试通过")
    except Exception as e:
        logger.error(f"性能指标测试失败: {e}")


def test_signal_operations(strategy):
    """测试信号操作"""
    logger.info("\n=== 测试信号操作 ===")
    try:
        # 生成信号
        signals = strategy.engine.generate_signals()
        if signals:
            signal_id = signals[0].signal_id
            # 测试确认信号
            confirm_result = strategy.confirm_signal(signal_id)
            logger.info(f"确认信号结果: {confirm_result}")
            # 测试执行信号
            execute_result = strategy.execute_signal(signal_id)
            logger.info(f"执行信号结果: {execute_result}")
        logger.info("信号操作测试通过")
    except Exception as e:
        logger.error(f"信号操作测试失败: {e}")


def main():
    """主测试函数"""
    logger.info("开始测试汇金价值AI轮动策略")
    
    # 测试策略初始化
    strategy = test_strategy_initialization()
    if not strategy:
        logger.error("策略初始化失败，测试终止")
        return
    
    # 测试盘前扫描
    test_market_scan(strategy)
    
    # 测试信号生成
    test_signal_generation(strategy)
    
    # 测试风控检查
    test_risk_control(strategy)
    
    # 测试策略更新
    test_strategy_update(strategy)
    
    # 测试性能指标
    test_performance(strategy)
    
    # 测试信号操作
    test_signal_operations(strategy)
    
    logger.info("\n=== 测试完成 ===")
    logger.info("汇金价值AI轮动策略测试通过！")


if __name__ == "__main__":
    main()
