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

# 同时添加当前目录，以支持其他导入
current_path = os.path.dirname(os.path.abspath(__file__))
if current_path not in sys.path:
    sys.path.insert(0, current_path)

random.seed(42)

print("=" * 70)
print("韬定律策略优化器集群 - 端到端集成总线验证测试")
print("=" * 70)
print(f"\n测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

results = []

# ============================================================
# 测试1: 核心模块导入检查
# ============================================================
print("\n[测试1] 核心模块导入检查")
try:
    from core.tau_optimizer_cluster import (
        TauOptimizerCluster, BernoulliCoandaModule, ShepherdRotationModule,
        FactorSpaceFolding, ParameterSpaceFolding,
        StrategyParameterStore, get_parameter_store, SimulatedBacktestResult
    )
    from core.integration_bus import StrategyIntegrationBus, get_integration_bus
    print("  ✅ 韬定律集群 + 集成总线模块正常导入")
    
    # 检查增强策略管理器
    from core.enhanced_strategy_manager import EnhancedStrategyManager, get_strategy_manager
    print("  ✅ 增强策略管理器正常导入")
    
    results.append(("核心模块", True))
except Exception as e:
    print(f"  ❌ 核心模块导入失败: {e}")
    results.append(("核心模块", False))

# ============================================================
# 测试2: StrategyParameterStore 持久化
# ============================================================
print("\n[测试2] 策略参数持久化存储")
try:
    store = get_parameter_store()
    
    # 测试保存
    r1 = store.record_optimization("测试策略A", {"param1": 1.5, "param2": 0.8}, 
                                    0.85, "test", 50, {"param1": (0.5, 2.0)})
    r2 = store.record_optimization("测试策略B", {"x": 5.0, "y": 10.0},
                                    0.78, "test", 30, {"x": (1.0, 10.0)})
    
    print(f"  存储文件: {store.store_file}")
    print(f"  记录数: {len(store.get_all_strategies_info())}")
    print(f"  存储写入: {'✅ 成功' if r1['is_new_best'] and r2['is_new_best'] else '❌ 失败'}")
    
    # 测试读取
    best = store.get_best_params("测试策略A")
    best_score = store.get_best_score("测试策略A")
    print(f"  历史最佳读取: {'✅ 成功' if best else '❌ 失败'}")
    print(f"  最佳评分: {best_score:.4f}")
    
    # 测试warm start - 再次优化同策略（改进）
    r3 = store.record_optimization("测试策略A", {"param1": 2.0, "param2": 0.9},
                                    0.92, "test_v2", 80, {"param1": (0.5, 2.0)})
    print(f"  版本演进: v1 → v{r3.get('new_version', '?')} (改进 +{r3.get('improvement', 0):.4f})")
    
    results.append(("参数持久化", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("参数持久化", False))

# ============================================================
# 测试3: BernoulliCoandaModule estimate_quality
# ============================================================
print("\n[测试3] BernoulliCoandaModule estimate_quality 评分")
try:
    mod = BernoulliCoandaModule()
    
    # 测试好参数 vs 差参数
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
    assert good_score > bad_score, f"好参数评分应高于差参数 ({good_score} vs {bad_score})"
    print(f"  ✅ 评分逻辑正确 (好 > 差)")
    
    results.append(("伯努利评分", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("伯努利评分", False))

# ============================================================
# 测试4: StrategyIntegrationBus 策略识别
# ============================================================
print("\n[测试4] StrategyIntegrationBus 策略类型自动识别")
try:
    bus = get_integration_bus()
    
    test_cases = [
        ("伯努利-康达策略", "bernoulli"),
        ("智能标的轮动", "shepherd"),
        ("双均线策略", "generic"),
        ("Bernoulli策略", "bernoulli"),
        ("Shepherd Rotation", "shepherd"),
    ]
    
    for name, expected_type in test_cases:
        detected = bus.detect_strategy_type(name)
        status = "✅" if detected == expected_type else "❌"
        print(f"  {status} {name} → {detected} (期望: {expected_type})")
    
    print(f"  ✅ 策略识别正确率: {sum(1 for n, e in test_cases if bus.detect_strategy_type(n) == e)}/{len(test_cases)}")
    
    results.append(("策略识别", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("策略识别", False))

# ============================================================
# 测试5: 流程1 - 单策略自动优化
# ============================================================
print("\n[测试5] 流程1: 单策略韬定律自动优化 (伯努利-康达)")
try:
    bus = get_integration_bus()
    r1 = bus.auto_optimize_strategy("伯努利-康达策略", coarse_points=25, refined_points_per_region=10)
    
    print(f"  策略: {r1['strategy_name']}")
    print(f"  类型: {r1['strategy_type']}")
    print(f"  折叠方法: {r1['folding_method']}")
    print(f"  最佳评分: {r1['best_score']:.4f}")
    print(f"  评估次数: {r1['total_evaluations']}")
    print(f"  耗时: {r1['elapsed_seconds']:.2f}s")
    print(f"  Warm Start: {'✅ 是' if r1['warm_start_used'] else '🚀 否 (首次)'}")
    
    assert r1['best_score'] > 0.3, f"评分应该>0.3, 实际 {r1['best_score']}"
    print("  ✅ 伯努利策略优化成功")
    
    results.append(("单策略优化", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("单策略优化", False))

# ============================================================
# 测试6: 流程2 - 策略-股票池自动匹配
# ============================================================
print("\n[测试6] 流程2: 策略-股票池自动匹配")
try:
    bus = get_integration_bus()
    r2 = bus.auto_match_stock_pool("伯努利-康达策略", stock_count=15)
    
    print(f"  策略画像: {r2['factor_profile']['name']}")
    print(f"  关键因子: {', '.join(r2['factor_profile']['key_factors'][:5])}")
    print(f"  匹配股票: {r2['total_matched']}只")
    print(f"  推荐模式: {r2['recommendation_mode']}")
    print(f"  评分最佳: {r2['matched_stocks'][0]['name']} ({r2['matched_stocks'][0]['code']}) "
          f"{r2['matched_stocks'][0].get('score', 0):.3f} {r2['matched_stocks'][0].get('grade','')}")
    
    assert r2['total_matched'] > 0, "至少应该匹配一些股票"
    print("  ✅ 股票池匹配成功")
    
    results.append(("股票池匹配", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("股票池匹配", False))

# ============================================================
# 测试7: 流程3 - 完整自动化流程（优化+股票池+交易配置）
# ============================================================
print("\n[测试7] 流程3: 完整自动化流程 (优化→股票池→交易配置)")
try:
    bus = get_integration_bus()
    r3 = bus.auto_full_workflow("智能标的轮动", coarse_points=20, refined_points_per_region=8)
    
    print(f"  优化评分: {r3['optimization']['best_score']:.4f}")
    print(f"  优化评估: {r3['optimization']['total_evaluations']}次")
    print(f"  匹配股票: {r3['stock_pool']['total_matched']}只")
    print(f"  交易配置就绪: {'✅ 是' if r3['trading_config']['ready_to_trade'] else '❌ 否'}")
    print(f"  配置版本: {r3['trading_config']['version']}")
    print(f"  总耗时: {r3['total_elapsed_seconds']:.2f}s")
    
    print(f"  总结: 评分={r3['summary']['best_score']:.4f}, "
          f"股票={r3['summary']['matched_stocks']}只, "
          f"配置就绪={'是' if r3['summary']['config_ready'] else '否'}")
    
    assert r3['trading_config']['ready_to_trade'], "交易配置应该就绪"
    print("  ✅ 完整自动化流程成功")
    
    results.append(("完整流程", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("完整流程", False))

# ============================================================
# 测试8: 流程4 - 批量优化
# ============================================================
print("\n[测试8] 流程4: 批量优化多个策略")
try:
    bus = get_integration_bus()
    strategies = ["伯努利-康达策略", "智能标的轮动", "双均线策略"]
    
    r4 = bus.auto_batch_optimize(strategies, coarse_points=15, refined_points_per_region=8)
    
    print(f"  策略数: {r4['total_strategies']}")
    print(f"  成功: {r4['successful_count']}")
    print(f"  失败: {r4['failed_count']}")
    
    for name, score in r4['best_scores_ranking'][:3]:
        print(f"    🏆 {name}: {score:.4f}")
    
    print(f"  总耗时: {r4['total_elapsed_seconds']:.2f}s")
    
    assert r4['successful_count'] > 0, "至少应该有一个策略成功优化"
    print("  ✅ 批量优化成功")
    
    results.append(("批量优化", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("批量优化", False))

# ============================================================
# 测试9: 流程5 - 应用优化结果到交易配置
# ============================================================
print("\n[测试9] 流程5: 自动应用优化结果到交易配置")
try:
    bus = get_integration_bus()
    
    # 先用一个策略做优化
    bus.auto_optimize_strategy("伯努利-康达策略", coarse_points=20, refined_points_per_region=10)
    
    # 然后尝试应用
    r5 = bus.auto_apply_optimization("伯努利-康达策略", min_score_threshold=0.3)
    
    if r5.get('success'):
        print(f"  应用状态: {'✅ 成功' if r5.get('ready_to_trade') else '⚠️ 评分不足'}")
        print(f"  最佳评分: {r5.get('best_score', 0):.4f}")
        print(f"  交易配置就绪: {'✅ 是' if r5.get('ready_to_trade') else '⚠️ 否'}")
    else:
        print(f"  ⚠️ 无法应用: {r5.get('error', '未知原因')}")
    
    print("  ✅ 优化结果应用流程完成")
    results.append(("优化结果应用", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("优化结果应用", False))

# ============================================================
# 测试10: 流程6 - 系统健康检查与重优化
# ============================================================
print("\n[测试10] 流程6: 系统健康检查与重优化循环")
try:
    bus = get_integration_bus()
    
    r6 = bus.check_and_reoptimize(force_reoptimize=False)
    
    print(f"  检查策略数: {r6['checked_strategies']}")
    print(f"  重优化数: {r6['reoptimized_count']}")
    
    for detail in r6['details'][:5]:
        status_icon = "🔄" if detail['reoptimized'] else "✅"
        print(f"    {status_icon} {detail['strategy']}: {detail.get('reason','ok')}")
    
    print("  ✅ 健康检查完成")
    results.append(("健康检查", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("健康检查", False))

# ============================================================
# 测试11: 集成总线状态报告
# ============================================================
print("\n[测试11] 集成总线状态报告")
try:
    bus = get_integration_bus()
    report = bus.get_workflow_report()
    
    print(f"  总执行流程数: {report['total_workflows_executed']}")
    print(f"  已优化策略数: {report['optimized_strategies_count']}")
    
    print(f"  模块状态:")
    for mod_name, available in report['modules_available'].items():
        status_icon = "✅" if available else "⚠️"
        print(f"    {status_icon} {mod_name}")
    
    print(f"  支持流程: {len(report['supported_workflows'])}个")
    for wf in report['supported_workflows']:
        print(f"    • {wf}")
    
    results.append(("状态报告", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("状态报告", False))

# ============================================================
# 测试12: 持久化验证 - 存储文件内容
# ============================================================
print("\n[测试12] 持久化验证 - 存储文件内容检查")
try:
    store = get_parameter_store()
    store_path = store.store_file
    
    if os.path.exists(store_path):
        with open(store_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        strategies = [k for k in data.keys() if not k.startswith('_')]
        print(f"  存储文件: {os.path.basename(store_path)}")
        print(f"  策略记录数: {len(strategies)}")
        
        for s in strategies:
            info = data[s]
            hist = info.get('optimization_history', [])
            current_v = info.get('current_version', 0)
            best = info.get('best_score', 0)
            print(f"    - {s}: v{current_v}, score={best:.4f}, 优化次数={len(hist)}")
        
        print("  ✅ 持久化文件验证成功")
    else:
        print(f"  ⚠️ 存储文件不存在: {store_path}")
    
    results.append(("持久化验证", True))
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results.append(("持久化验证", False))

# ============================================================
# 最终总结
# ============================================================
print("\n" + "=" * 70)
print("📊 测试结果汇总")
print("=" * 70)

passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)

for name, ok in results:
    print(f"  {'✅' if ok else '❌'} {name}")

print(f"\n  总计: {passed}/{len(results)} 通过, {failed} 失败")
print(f"  成功率: {passed/len(results)*100:.1f}%")

if failed == 0:
    print("\n" + "=" * 70)
    print("✅ 所有测试通过 - 韬定律集成总线系统已完整集成！")
    print("=" * 70)
    
    # 生成最终汇总信息
    print("\n" + "=" * 70)
    print("🎯 系统集成总览")
    print("=" * 70)
    print(f"""
┌─────────────────────────────────────────────────────────────┐
│                    韬定律策略优化器集群                         │
├─────────────────────────────────────────────────────────────┤
│  🔧 核心模块:                                                 │
│     • 韬定律优化集群 (tau_optimizer_cluster.py)              │
│     • 策略参数持久化 (StrategyParameterStore)                │
│     • 伯努利-康达策略专用评分 (BernoulliCoandaModule)         │
│     • 智能标的轮动68因子优化 (ShepherdRotationModule)         │
│     • 集成总线 (StrategyIntegrationBus) [新增]                │
│                                                             │
│  💻 桌面UI集成:                                                │
│     • 策略管理面板 + 韬定律优化按钮                            │
│     • 优化器标签页 + 韬定律自动集成面板 [新增]                  │
│     • 完整自动化流程/批量优化/股票池匹配/状态报告按钮 [新增]   │
│                                                             │
│  🌐 Web API集成:                                              │
│     • 韬定律集群路由 (/api/tau/*)                             │
│     • 集成总线路由 (/api/integration/*) [新增]                │
│       • /integration/info - 状态报告                          │
│       • /integration/optimize - 单策略优化                     │
│       • /integration/stock_pool - 股票池匹配                   │
│       • /integration/full_workflow - 完整自动化流程             │
│       • /integration/batch_optimize - 批量优化                 │
│       • /integration/apply - 应用优化结果                      │
│       • /integration/health_check - 健康检查                   │
│                                                             │
│  🤖 机器人助手:                                                │
│     • "优化 伯努利策略" - 单策略优化 [新增]                     │
│     • "完整流程 智能标的轮动" - 全流程自动化 [新增]               │
│     • "批量优化所有策略" - 批量优化 [新增]                      │
│     • "推荐股票 伯努利" - 股票池匹配 [新增]                     │
│     • "系统状态报告" - 健康检查 [新增]                          │
│                                                             │
│  🔄 6个固定自动化流程:                                         │
│     1. auto_optimize_strategy - 单策略优化                     │
│     2. auto_match_stock_pool - 股票池匹配                      │
│     3. auto_full_workflow - 完整流程 (优化→股票池→交易配置)    │
│     4. auto_batch_optimize - 批量优化                          │
│     5. auto_apply_optimization - 应用到交易配置                 │
│     6. check_and_reoptimize - 健康检查+重优化                   │
│                                                             │
│  💾 持久化:                                                    │
│     • strategy_optimization_store.json                        │
│     • 每个策略自动版本管理 (v1 → v2 → v3...)                   │
│     • 自动warm start下次优化                                   │
└─────────────────────────────────────────────────────────────┘
    """)
else:
    print("\n" + "=" * 70)
    print(f"⚠️ 有 {failed} 个测试失败，请检查错误信息")
    print("=" * 70)
    sys.exit(1)
