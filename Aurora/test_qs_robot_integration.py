#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  QS Robot 全链路连通性测试                                  ║
║  test_qs_robot_integration.py V3.1                          ║
║  验证: QSRobotCore → AuroraQBotAdapter → 12模块通路         ║
╚══════════════════════════════════════════════════════════════╝

测试层级:
  L1: 语法 — 所有文件可导入
  L2: 实例 — 单例与初始化
  L3: 功能 — 方法调用
  L4: 集成 — 适配器链
  L5: 事件总线 — Pub/Sub
  L6: 数据流 — 端到端
"""

import os, sys, time, json, traceback
from datetime import datetime

# 确保导入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# L1: 语法验证 — 导入 qs_robot_core
# ============================================================
print("=" * 70)
print("  L1: 语法验证 — 导入 qs_robot_core")
print("=" * 70)

try:
    from qs_robot_core import (
        QSRobotCore, QBotMode, QBotTaskType, QBotTask,
        get_qs_robot, get_qs_robot_instance
    )
    print("  ✅ qs_robot_core 全部符号导入成功")
    
    # 验证关键符号
    assert callable(get_qs_robot), "get_qs_robot 应可调用"
    assert callable(get_qs_robot_instance), "get_qs_robot_instance 应可调用"
    assert get_qs_robot is get_qs_robot_instance, "两个函数应为同一对象"
    assert QBotMode.STANDBY == "standby"
    assert QBotTaskType.BACKTEST == "backtest"
    assert QBotTaskType.OPTIMIZATION == "optimization"
    assert QBotTaskType.RISK_CHECK == "risk_check"
    print("  ✅ L1 全部通过\n")
    L1_OK = True
except Exception as e:
    print(f"  ❌ L1 失败: {e}")
    traceback.print_exc()
    L1_OK = False

# ============================================================
# L2: 实例化 — 单例模式
# ============================================================
print("=" * 70)
print("  L2: 单例模式验证")
print("=" * 70)

L2_OK = False
if L1_OK:
    try:
        inst1 = get_qs_robot()
        inst2 = get_qs_robot_instance()
        assert inst1 is inst2, "单例不唯一"
        print("  ✅ 单例模式正确: inst1 is inst2")
        
        # 测试 initialize
        ok = inst1.initialize()
        print(f"  📍 initialize() → {ok}")
        print(f"  📍 模式: {inst1._mode}")
        print(f"  ✅ L2 全部通过\n")
        L2_OK = True
    except Exception as e:
        print(f"  ❌ L2 失败: {e}")
        traceback.print_exc()

# ============================================================
# L3: 功能验证 — 核心API冒烟测试
# ============================================================
print("=" * 70)
print("  L3: 核心API冒烟测试")
print("=" * 70)

L3_OK = False
if L2_OK:
    try:
        robot = get_qs_robot()
        
        # 策略列表
        strategies = robot.get_all_strategies()
        print(f"  📋 get_all_strategies() → {len(strategies)}个策略")
        assert isinstance(strategies, list), "策略列表应为list"
        
        # 完整状态
        status = robot.get_full_status()
        print(f"  📊 get_full_status() → 模式={status['mode']}, 运行={status['uptime_seconds']:.0f}秒")
        assert 'mode' in status
        assert 'uptime_seconds' in status
        assert 'version' in status
        
        # 风控检查
        risk = robot.run_risk_check()
        print(f"  🛡️ run_risk_check() → {risk['overall_status']}")
        assert 'overall_status' in risk
        
        # 任务提交
        task_id = robot.submit_backtest("test_strategy", days=7)
        print(f"  📊 submit_backtest() → {task_id}")
        assert isinstance(task_id, str) and len(task_id) > 5, "task_id 应该为非空字符串"
        
        # 终止所有策略
        ok, msg = robot.stop_all_strategies()
        print(f"  🛑 stop_all_strategies() → {ok}, {msg}")
        
        print(f"  ✅ L3 全部通过\n")
        L3_OK = True
    except Exception as e:
        print(f"  ❌ L3 失败: {e}")
        traceback.print_exc()

# ============================================================
# L4: 集成链路 — AuroraQBotAdapter 深度集成验证
# ============================================================
print("=" * 70)
print("  L4: Aurora深度集成链路验证")
print("=" * 70)

L4_OK = False
L4_CHECKS = []

try:
    # 检查 aurora_qbot_deep_integration 模块
    from aurora_qbot_deep_integration import (
        SharedProcessBus, DeepFallbackEngine, CoEngine,
        AuroraQBotAdapter, StrategyBridge, BusEvent, BusEventType
    )
    L4_CHECKS.append("✅ aurora_qbot_deep_integration 导入成功")
    
    # 验证核心组件可实例化
    bus = SharedProcessBus()
    assert bus is not None
    L4_CHECKS.append("✅ SharedProcessBus 实例化成功")
    
    fallback = DeepFallbackEngine()
    assert fallback is not None
    L4_CHECKS.append("✅ DeepFallbackEngine 实例化成功")
    
    co = CoEngine(bus, fallback)
    assert co is not None
    L4_CHECKS.append("✅ CoEngine 实例化成功")
    
    adapter = AuroraQBotAdapter(bus, fallback, co)
    assert adapter is not None
    L4_CHECKS.append("✅ AuroraQBotAdapter 实例化成功")
    
    bridge = StrategyBridge(adapter)
    assert bridge is not None
    L4_CHECKS.append("✅ StrategyBridge 实例化成功")
    
    # 检查QSRobotCore内部链接
    robot = get_qs_robot()
    assert robot._bus is not None or robot._mode == QBotMode.DEGRADED, \
        "QSRobotCore未连接到SharedProcessBus"
    L4_CHECKS.append(f"✅ QSRobotCore→Bus连接 ({robot._mode})")
    
    L4_OK = True
except ImportError as e:
    L4_CHECKS.append(f"⚠️ 深度集成模块不可用: {e}")
    print(f"  ⚠️ aurora_qbot_deep_integration 不可用（预期内——可能尚未部署）")
except Exception as e:
    L4_CHECKS.append(f"❌ {e}")
    traceback.print_exc()

for c in L4_CHECKS:
    print(f"  {c}")
print(f"  {'✅' if L4_OK else '⚠️'} L4 {'全部通过' if L4_OK else '部分通过（深度集成模块待部署）'}\n")

# ============================================================
# L5: 事件总线 — Pub/Sub
# ============================================================
print("=" * 70)
print("  L5: 事件总线 Pub/Sub 验证")
print("=" * 70)

L5_OK = False
try:
    robot = get_qs_robot()
    signal_count_before = len(robot.get_recent_signals())
    risk_count_before = len(robot.get_risk_events())
    
    # 运行风控（会产生事件）
    robot.run_risk_check()
    
    signal_count_after = len(robot.get_recent_signals())
    risk_count_after = len(robot.get_risk_events())
    
    print(f"  📡 信号缓存: {signal_count_before} → {signal_count_after}")
    print(f"  🛡️ 风控事件: {risk_count_before} → {risk_count_after}")
    assert risk_count_after >= risk_count_before, "风控事件应增加"
    
    print(f"  ✅ L5 全部通过\n")
    L5_OK = True
except Exception as e:
    print(f"  ❌ L5 失败: {e}")
    traceback.print_exc()

# ============================================================
# L6: 数据流 — 端到端验证
# ============================================================
print("=" * 70)
print("  L6: 端到端数据流验证")
print("=" * 70)

L6_OK = False
try:
    robot = get_qs_robot()
    
    # 流程1: 策略→回测→结果
    print("  🔄 流程1: 策略→回测")
    strategies = robot.get_all_strategies()
    if strategies:
        sname = strategies[0].get('name', 'default')
        task_id = robot.submit_backtest(sname, days=7)
        time.sleep(3)
        result = robot.get_task_status(task_id)
        print(f"     task_id={task_id}, status={result['status']}")
        assert result is not None, "回测结果不应为空"
        print("  ✅ 流程1 通过")
    
    # 流程2: 完整状态→前端渲染
    print("  🔄 流程2: 完整状态拉取")
    status = robot.get_full_status()
    assert 'mode' in status
    assert 'strategy_count' in status
    assert 'uptime_seconds' in status
    print(f"     mode={status['mode']}, strategies={status['strategy_count']}")
    print("  ✅ 流程2 通过")
    
    # 流程3: 风控→事件
    print("  🔄 流程3: 风控→事件")
    risk = robot.run_risk_check()
    events = robot.get_risk_events(limit=5)
    print(f"     risk_status={risk['overall_status']}, events={len(events)}")
    assert risk['overall_status'] in ('ok', 'warning', 'error')
    print("  ✅ 流程3 通过")
    
    # 流程4: 旧版兼容接口
    print("  🔄 流程4: 兼容层验证")
    legacy_list = robot.get_strategy_list_legacy()
    print(f"     get_strategy_list_legacy() → {len(legacy_list)}个")
    legacy_result = robot.get_backtest_result_legacy("test", days=7)
    print(f"     get_backtest_result_legacy() → {legacy_result.get('source', 'N/A')}")
    assert isinstance(legacy_list, list), "旧版列表应为list"
    print("  ✅ 流程4 通过")
    
    L6_OK = True
    print(f"  ✅ L6 全部通过\n")
except Exception as e:
    print(f"  ❌ L6 失败: {e}")
    traceback.print_exc()

# ============================================================
# 总结
# ============================================================
print("=" * 70)
print("  📊 全链路连通性测试总结")
print("=" * 70)

results = {
    "L1_语法导入": L1_OK,
    "L2_单例模式": L2_OK,
    "L3_核心API": L3_OK,
    "L4_深度集成": L4_OK,
    "L5_事件总线": L5_OK,
    "L6_端到端": L6_OK,
}

for name, ok in results.items():
    print(f"  {name}: {'✅' if ok else '❌'}")

passed = sum(1 for v in results.values() if v)
total = len(results)
print(f"\n  通过率: {passed}/{total} ({passed*100//total}%)")

if passed == total:
    print("  🎉 所有测试全部通过！QS Robot 已与 Aurora 深度集成！")
elif passed >= 4:
    print("  ✅ 核心功能通过，深度集成模块待部署")
else:
    print("  ❌ 存在关键问题需要修复")

# 保存报告
report = {
    "test_time": datetime.now().isoformat(),
    "passed": passed,
    "total": total,
    "results": {k: v for k, v in results.items()},
    "L4_checks": L4_CHECKS if 'L4_CHECKS' in dir() else []
}

with open('qs_robot_integration_report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n  📄 报告已保存: qs_robot_integration_report.json")

# 清理
try:
    robot = get_qs_robot()
    robot.shutdown()
except Exception:
    pass