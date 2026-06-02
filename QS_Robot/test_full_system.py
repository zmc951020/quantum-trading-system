#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QS Robot 系统全面测试
"""
import sys
import os

# 设置输出编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
elif sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.enhanced_strategy_manager import get_strategy_manager

print('=== QS Robot 系统全面测试 ===')
print()

# 1. 初始化策略管理器
print('1. 初始化策略管理器...')
try:
    mgr = get_strategy_manager()
    print('   OK - 策略管理器初始化成功')
except Exception as e:
    print(f'   FAIL - 初始化失败: {e}')
    sys.exit(1)

# 2. 获取系统状态
print('2. 获取系统状态...')
try:
    status = mgr.get_system_status()
    print(f'   OK - 系统状态: {status.get("qs_robot_mode", "unknown")}')
except Exception as e:
    print(f'   FAIL - 获取状态失败: {e}')

# 3. 获取策略列表
print('3. 获取策略列表...')
try:
    strategies = mgr.get_strategy_list()
    print(f'   OK - 发现 {len(strategies)} 个策略')
except Exception as e:
    print(f'   FAIL - 获取策略列表失败: {e}')

# 4. 运行回测
print('4. 运行回测测试...')
try:
    if strategies:
        result = mgr.run_backtest(strategies[0]['name'], days=7)
        print(f'   OK - 回测完成: 收益 {result.total_return_pct}%, 夏普 {result.sharpe_ratio}')
    else:
        print('   SKIP - 没有可用策略')
except Exception as e:
    print(f'   FAIL - 回测失败: {e}')

# 5. 运行优化
print('5. 运行参数优化测试...')
try:
    if strategies:
        opt = mgr.run_optimization(strategies[0]['name'], iterations=5)
        if opt.get('success'):
            print(f'   OK - 优化完成: 最佳评分 {opt["data"]["best_score"]}')
        else:
            print(f'   WARN - 优化结果: {opt}')
    else:
        print('   SKIP - 没有可用策略')
except Exception as e:
    print(f'   FAIL - 优化失败: {e}')

# 6. 健康检查
print('6. 系统健康检查...')
try:
    health = mgr.get_system_health()
    print(f'   OK - 健康状态: {health.status}')
    print(f'        CPU: {health.cpu_percent}%, 内存: {health.memory_percent}%')
except Exception as e:
    print(f'   FAIL - 健康检查失败: {e}')

# 7. 风险状态
print('7. 获取风险状态...')
try:
    risk = mgr.get_risk_status()
    print(f'   OK - 风险状态获取成功')
except Exception as e:
    print(f'   FAIL - 获取风险状态失败: {e}')

# 8. 测试 QS Robot Core
print('8. 测试 QS Robot Core...')
try:
    from qs_robot_core import QSRobotCore
    robot = QSRobotCore()
    strategies_core = robot.aurora.get_strategy_list()
    print(f'   OK - QS Robot Core 工作正常，发现 {len(strategies_core)} 个策略')
except Exception as e:
    print(f'   FAIL - QS Robot Core 测试失败: {e}')

print()
print('=== 测试完成 ===')
print()
print('状态摘要:')
print(mgr.get_status_summary())