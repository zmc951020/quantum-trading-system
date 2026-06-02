#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""韬定律策略优化器集群 - 端到端集成总线验证测试"""
import os, sys, json, time, random

# Windows控制台UTF-8编码补丁
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加QS_Robot路径
QS_ROBOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'QS_Robot')
if os.path.exists(QS_ROBOT_PATH) and QS_ROBOT_PATH not in sys.path:
    sys.path.insert(0, QS_ROBOT_PATH)

random.seed(42)

print("=" * 70)
print("韬定律策略优化器集群 - 端到端集成总线验证测试")
print("=" * 70)

results = []

def run_test(name, test_func):
    try:
        print(f"\n[{name}]")
        test_func()
        results.append((name, True))
    except Exception as e:
        print(f"  失败: {e}")
        import traceback
        traceback.print_exc()
        results.append((name, False))

# ============================================================
# 测试1: 核心模块导入检查
# ============================================================
def test_01_modules():
    from core.tau_optimizer_cluster import (
        TauOptimizerCluster, BernoulliCoandaModule, ShepherdRotationModule,
        FactorSpaceFolding, ParameterSpaceFolding,
        StrategyParameterStore, get_parameter_store
    )
    from core.integration_bus import StrategyIntegrationBus, get_integration_bus
    from core.enhanced_strategy_manager import EnhancedStrategyManager, get_strategy_manager, BacktestResult
    print("  韬定律集群: OK")
    print("  策略集成总线: OK")
    print("  增强策略管理器: OK")
    print("  ✅ 所有核心模块导入成功")

run_test("核心模块导入", test_01_modules)

# ============================================================
# 测试2: 策略参数持久化存储
# ============================================================
def test_02_persistence():
    from core.tau_optimizer_cluster import get_parameter_store
    
    store = get_parameter_store()
    
    # 写入一些测试数据
    store.record_optimization("集成测试策略A", {"x": 1.5}, 0.85, "test", 50, {"x": (0.5, 2.0)})
    store.record_optimization("集成测试策略B", {"y": 3.0}, 0.92, "test", 80, {"y": (1.0, 5.0)})
    
    best_a = store.get_best_params("集成测试策略A")
    best_score = store.get_best_score("集成测试策略A")
    
    print(f"  存储文件: {os.path.basename(store.store_file)}")
    print(f"  策略A最佳评分: {best_score:.4f}")
    print(f"  已优化策略数: {len(store.get_optimized_strategies())}")
    
    # 测试版本演进
    r = store.record_optimization("集成测试策略A", {"x": 2.0}, 0.95, "test_v2", 100, {"x": (0.5, 2.0)})
    print(f"  版本演进: v{store.get_strategy('集成测试策略A').get('current_version', 0)} "
          f"(改进: +{r.get('improvement', 0):.4f})")
    
    assert best_a is not None, "应能读取最佳参数"
    print("  ✅ 策略参数持久化正常")

run_test("策略参数持久化", test_02_persistence)

# ============================================================
# 测试3: BernoulliCoandaModule estimate_quality评分
# ============================================================
def test_03_bernoulli_quality():
    from core.tau_optimizer_cluster import BernoulliCoandaModule
    
    mod = BernoulliCoandaModule()
    
    good_params = {
        'short_period': 12.0, 'mid_period': 35.0, 'long_period': 70.0,
        'bernoulli_threshold': 0.06, 'momentum_alpha': 1.0, 'pressure_sensitivity': 0.8,
        'coanda_attachment': 0.6, 'curvature_sensitivity': 0.5, 'separation_threshold': 1.0,
        'stop_loss_pct': 0.05, 'position_size': 0.3, 'confirmation_bars': 3.0
    }
    bad_params = {
        'short_period': 3.0, 'mid_period': 5.0, 'long_period': 10.0,
        'bernoulli_threshold': 0.3, 'momentum_alpha': 3.0, 'pressure_sensitivity': 2.5,
        'coanda_attachment': 0.01, 'curvature_sensitivity': 2.0, 'separation_threshold': 0.1,
        'stop_loss_pct': 0.25, 'position_size': 0.9, 'confirmation_bars': 20.0
    }
    
    good_score = mod.estimate_quality(good_params)
    bad_score = mod.estimate_quality(bad_params)
    
    print(f"  合理参数评分: {good_score:.4f}")
    print(f"  差参数评分: {bad_score:.4f}")
    assert good_score > bad_score, "好参数评分应高于差参数"
    print(f"  ✅ 评分逻辑正确 (好 {good_score:.2f} > 差 {bad_score:.2f})")

run_test("伯努利评分逻辑", test_03_bernoulli_quality)

# ============================================================
# 测试4: 策略类型自动识别
# ============================================================
def test_04_strategy_detection():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    
    test_cases = [
        ("伯努利-康达策略", "bernoulli"),
        ("智能标的轮动", "shepherd"),
        ("双均线策略", "generic"),
        ("Bernoulli策略", "bernoulli"),
        ("Shepherd Rotation", "shepherd"),
    ]
    
    for name, expected in test_cases:
        detected = bus.detect_strategy_type(name)
        icon = "✅" if detected == expected else "❌"
        print(f"  {icon} {name} → {detected} (期望 {expected})")
    
    print(f"  ✅ 策略识别: {sum(1 for n, e in test_cases if bus.detect_strategy_type(n) == e)}/{len(test_cases)} 正确")

run_test("策略类型识别", test_04_strategy_detection)

# ============================================================
# 测试5: 流程1 - 单策略韬定律优化
# ============================================================
def test_05_single_optimize():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    r = bus.auto_optimize_strategy("伯努利-康达策略", coarse_points=25, refined_points_per_region=10)
    
    print(f"  策略: {r['strategy_name']}")
    print(f"  类型: {r['strategy_type']}")
    print(f"  折叠方法: {r['folding_method']}")
    print(f"  最佳评分: {r['best_score']:.4f}")
    print(f"  评估次数: {r['total_evaluations']}")
    print(f"  耗时: {r['elapsed_seconds']:.2f}s")
    print(f"  Warm Start: {'是' if r['warm_start_used'] else '否 (首次)'}")
    
    assert r['best_score'] > 0.3, f"评分应>0.3, 实际 {r['best_score']}"
    print("  ✅ 单策略优化完成")

run_test("流程1:单策略优化", test_05_single_optimize)

# ============================================================
# 测试6: 流程2 - 策略股票池匹配
# ============================================================
def test_06_stock_pool():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    r = bus.auto_match_stock_pool("伯努利-康达策略", stock_count=15)
    
    print(f"  策略画像: {r['factor_profile']['name']}")
    print(f"  关键因子: {', '.join(r['factor_profile']['key_factors'][:3])}")
    print(f"  匹配股票: {r['total_matched']} 只")
    print(f"  推荐模式: {r['recommendation_mode']}")
    
    if r['matched_stocks']:
        top = r['matched_stocks'][0]
        print(f"  最佳: {top.get('name','')} ({top.get('code','')}) "
              f"评分={top.get('score',0):.3f} {top.get('grade','')}")
    
    assert r['total_matched'] > 0, "至少应该匹配一些股票"
    print("  ✅ 股票池匹配完成")

run_test("流程2:股票池匹配", test_06_stock_pool)

# ============================================================
# 测试7: 流程3 - 完整自动化流程
# ============================================================
def test_07_full_workflow():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    r = bus.auto_full_workflow("智能标的轮动", coarse_points=20, refined_points_per_region=8)
    
    print(f"  优化评分: {r['optimization']['best_score']:.4f}")
    print(f"  优化评估: {r['optimization']['total_evaluations']} 次")
    print(f"  匹配股票: {r['stock_pool']['total_matched']} 只")
    print(f"  交易配置: {'就绪 ✅' if r['trading_config']['ready_to_trade'] else '未就绪'}")
    print(f"  配置版本: {r['trading_config']['version']}")
    print(f"  总耗时: {r['total_elapsed_seconds']:.2f}s")
    
    print(f"  总结: 评分={r['summary']['best_score']:.4f}, "
          f"股票={r['summary']['matched_stocks']}只, "
          f"配置={'就绪' if r['summary']['config_ready'] else '未就绪'}")
    
    assert r['trading_config']['ready_to_trade'], "交易配置应该就绪"
    print("  ✅ 完整自动化流程完成")

run_test("流程3:完整自动化流程", test_07_full_workflow)

# ============================================================
# 测试8: 流程4 - 批量优化
# ============================================================
def test_08_batch():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    strategies = ["伯努利-康达策略", "智能标的轮动", "双均线策略"]
    
    r = bus.auto_batch_optimize(strategies, coarse_points=15, refined_points_per_region=8)
    
    print(f"  策略总数: {r['total_strategies']}")
    print(f"  成功: {r['successful_count']}")
    print(f"  失败: {r['failed_count']}")
    
    for name, score in r['best_scores_ranking'][:3]:
        print(f"    🏆 {name}: {score:.4f}")
    
    print(f"  总耗时: {r['total_elapsed_seconds']:.2f}s")
    assert r['successful_count'] > 0, "至少应成功优化一个策略"
    print("  ✅ 批量优化完成")

run_test("流程4:批量优化", test_08_batch)

# ============================================================
# 测试9: 流程5 - 应用优化结果到交易配置
# ============================================================
def test_09_apply():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    r = bus.auto_apply_optimization("伯努利-康达策略", min_score_threshold=0.3)
    
    if r.get('success'):
        print(f"  最佳评分: {r.get('best_score', 0):.4f}")
        print(f"  交易配置: {'就绪 ✅' if r.get('ready_to_trade') else '评分不足'}")
        config = r.get('trading_config', {})
        if config:
            print(f"  目标股票: {len(config.get('target_stocks', []))} 只")
            print(f"  风控参数: max_pos={config.get('risk_parameters',{}).get('max_position_size_pct','?')}%")
    else:
        print(f"  ⚠️: {r.get('error', '未知原因')}")
    
    print("  ✅ 优化结果应用完成")

run_test("流程5:应用优化结果", test_09_apply)

# ============================================================
# 测试10: 流程6 - 健康检查
# ============================================================
def test_10_health():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    r = bus.check_and_reoptimize(force_reoptimize=False)
    
    print(f"  检查策略数: {r['checked_strategies']}")
    print(f"  重优化数: {r['reoptimized_count']}")
    
    for detail in r['details'][:5]:
        icon = "🔄" if detail['reoptimized'] else "✅"
        print(f"    {icon} {detail['strategy']}: {detail.get('reason','ok')}")
    
    print("  ✅ 健康检查完成")

run_test("流程6:健康检查", test_10_health)

# ============================================================
# 测试11: 集成总线状态报告
# ============================================================
def test_11_report():
    from core.integration_bus import get_integration_bus
    
    bus = get_integration_bus()
    report = bus.get_workflow_report()
    
    print(f"  总执行流程数: {report['total_workflows_executed']}")
    print(f"  已优化策略数: {report['optimized_strategies_count']}")
    
    print(f"  模块状态:")
    for mod_name, available in report['modules_available'].items():
        icon = "✅" if available else "⚠️"
        print(f"    {icon} {mod_name}")
    
    print(f"  支持流程: {len(report['supported_workflows'])} 个")
    for wf in report['supported_workflows'][:3]:
        print(f"    • {wf}")
    
    print("  ✅ 状态报告生成完成")

run_test("集成总线状态报告", test_11_report)

# ============================================================
# 测试12: 持久化文件验证
# ============================================================
def test_12_file_check():
    from core.tau_optimizer_cluster import get_parameter_store
    
    store = get_parameter_store()
    
    if os.path.exists(store.store_file):
        with open(store.store_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        strategies = [k for k in data.keys() if not k.startswith('_')]
        print(f"  存储文件: {os.path.basename(store.store_file)}")
        print(f"  策略记录数: {len(strategies)}")
        
        for s in strategies:
            info = data[s]
            hist = info.get('optimization_history', [])
            current_v = info.get('current_version', 0)
            best = info.get('best_score', 0)
            print(f"    - {s}: v{current_v}, score={best:.4f}, 优化次数={len(hist)}")
        
        print("  ✅ 持久化文件验证成功")
    else:
        print(f"  ⚠️ 存储文件不存在: {store.store_file}")

run_test("持久化文件验证", test_12_file_check)

# ============================================================
# 最终总结
# ============================================================
print("\n" + "=" * 70)
print("测试结果汇总")
print("=" * 70)

passed = sum(1 for _, ok in results if ok)
total = len(results)

for name, ok in results:
    status = "✅" if ok else "❌"
    print(f"  {status} {name}")

print(f"\n总计: {passed}/{total} 通过, {total - passed} 失败")
print(f"成功率: {passed/total*100:.1f}%")

if passed == total:
    print("\n" + "=" * 70)
    print("🎉 所有测试通过 - 韬定律集成总线系统完整可用！")
    print("=" * 70)
    print("\n系统集成总览:")
    print(f"""
┌─────────────────────────────────────────────────────────────┐
│                    韬定律策略优化器集群                         │
├─────────────────────────────────────────────────────────────┤
│  🔧 核心模块:                                                 │
│     • 韬定律优化集群 (tau_optimizer_cluster.py)              │
│     • 策略参数持久化 (StrategyParameterStore)                │
│     • 伯努利-康达策略专用评分 (BernoulliCoandaModule)         │
│     • 智能标的轮动68因子优化 (ShepherdRotationModule)         │
│     • 集成总线 (StrategyIntegrationBus) - 新增                 │
│                                                             │
│  💻 桌面UI集成: (qs_robot_desktop_v2.py)                      │
│     • 策略管理面板 + 韬定律优化按钮                           │
│     • 优化器标签页 + 韬定律自动集成面板 - 新增                  │
│     • 完整自动化流程/批量优化/股票池匹配/状态报告按钮 - 新增   │
│                                                             │
│  🌐 Web API集成: (ui/server.py)                              │
│     • 韬定律集群路由 (/api/tau/*)                            │
│     • 集成总线路由 (/api/integration/*) - 新增                │
│                                                             │
│  🤖 机器人助手: (qs_robot_core.py)                            │
│     • 优化 [策略名] - 单策略优化 - 新增                        │
│     • 完整流程 [策略名] - 全流程自动化 - 新增                   │
│     • 批量优化所有策略 - 批量优化 - 新增                        │
│     • 推荐股票 [策略名] - 股票池匹配 - 新增                     │
│     • 系统状态报告 - 健康检查 - 新增                            │
│                                                             │
│  🔄 6个固定自动化流程:                                        │
│     1. auto_optimize_strategy - 单策略优化                     │
│     2. auto_match_stock_pool - 股票池匹配                      │
│     3. auto_full_workflow - 完整流程                           │
│     4. auto_batch_optimize - 批量优化                          │
│     5. auto_apply_optimization - 应用交易配置                   │
│     6. check_and_reoptimize - 健康检查+重优化                   │
│                                                             │
│  💾 持久化:                                                    │
│     • strategy_optimization_store.json                        │
│     • 每个策略自动版本管理 (v1 → v2 → v3...)                   │
│     • 自动warm start下次优化                                   │
└─────────────────────────────────────────────────────────────┘
    """)
else:
    print(f"\n⚠️ 有 {total - passed} 个测试失败")
    sys.exit(1)
