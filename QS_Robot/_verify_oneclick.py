"""阶段6: 一键优化验证

验证熵韬优化器能否识别并纳入同花顺32策略：
  1. 策略类型识别（_detect_strategy_type）
  2. SignalCollector加载32策略
  3. 一键优化器能接收32策略名
  4. 参数空间可被优化器读取
"""
import sys
import logging
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)


def verify_strategy_type_detection():
    """验证策略类型识别"""
    from core.enhanced_strategy_manager import EnhancedStrategyManager
    mgr = EnhancedStrategyManager()
    test_cases = [
        ("MACD顺势波段", "ths_strategies"),
        ("周线突破战法", "ths_strategies"),
        ("5句口诀抓龙头", "ths_strategies"),
        ("龙虎榜跟庄", "ths_strategies"),
        ("BOLL上轨突破", "ths_strategies"),
        ("主力量价操盘", "ths_advanced"),
        ("问财AI选股", "ths_advanced"),
        ("筹码单峰密集", "ths_advanced"),
        ("北向资金跟随", "ths_advanced"),
        ("网格交易套利", "ths_advanced"),
        ("主力筹码控盘综合", "ths_advanced"),
    ]
    ok = 0
    for name, expected in test_cases:
        actual = mgr._detect_strategy_type(name, {})
        flag = "✅" if actual == expected else "❌"
        print(f"  {flag} '{name}' → {actual} (期望: {expected})")
        if actual == expected:
            ok += 1
    return ok, len(test_cases)


def verify_param_space_for_optimizer():
    """验证参数空间可被优化器读取"""
    from api.ths_bridge.signal_collector import SignalCollector
    collector = SignalCollector()
    s14, s18 = collector.list_strategies()
    all_strategies = collector._strategies_14 + collector._strategies_18
    ok = 0
    for strat in all_strategies:
        ps = strat.get_param_space()
        valid = isinstance(ps, dict) and len(ps) > 0
        if valid:
            for k, v in ps.items():
                if not (isinstance(v, tuple) and len(v) == 2 and v[0] < v[1]):
                    valid = False
                    break
        if valid:
            ok += 1
    return ok, len(all_strategies)


def verify_optimizer_accepts_ths():
    """验证优化器能接受同花顺策略"""
    try:
        from core.tau_enhanced_optimizer import EntropyTauOptimizer
        from api.ths_bridge.signal_collector import SignalCollector
        collector = SignalCollector()
        strategy = collector._strategies_14[0]
        ps = strategy.get_param_space()
        optimizer = EntropyTauOptimizer(
            strategy_name=strategy.NAME,
            param_ranges=ps,
        )
        return True, f"优化器接受{strategy.NAME}, 参数={list(ps.keys())}"
    except Exception as e:
        return False, f"优化器初始化失败: {e}"


def verify_batch_optimize_interface():
    """验证批量优化接口"""
    try:
        from extensions.tools.tau_oneclick import TauOneClickOptimizer
        has_run_multiple = hasattr(TauOneClickOptimizer, "run_multiple")
        has_optimize_and_apply = hasattr(TauOneClickOptimizer, "optimize_and_apply")
        return has_run_multiple and has_optimize_and_apply, \
            f"TauOneClickOptimizer: run_multiple={'✓' if has_run_multiple else '✗'}, " \
            f"optimize_and_apply={'✓' if has_optimize_and_apply else '✗'}"
    except Exception as e:
        return False, f"导入失败: {e}"


def main():
    print("=" * 70)
    print("阶段6: 一键优化验证")
    print("=" * 70)

    print("\n[1] 策略类型识别")
    ok1, total1 = verify_strategy_type_detection()
    print(f"  结果: {ok1}/{total1} 正确识别")

    print("\n[2] 参数空间可读性")
    ok2, total2 = verify_param_space_for_optimizer()
    print(f"  结果: {ok2}/{total2} 策略参数空间有效")

    print("\n[3] 优化器接受同花顺策略")
    success3, msg3 = verify_optimizer_accepts_ths()
    flag = "✅" if success3 else "❌"
    print(f"  {flag} {msg3}")

    print("\n[4] 批量优化接口")
    success4, msg4 = verify_batch_optimize_interface()
    flag = "✅" if success4 else "❌"
    print(f"  {flag} {msg4}")

    print("\n" + "=" * 70)
    all_pass = (ok1 == total1 and ok2 == total2 and success3 and success4)
    print(f"最终: {'✅ 全部通过' if all_pass else '❌ 存在失败项'}")
    print(f"  - 策略识别: {ok1}/{total1}")
    print(f"  - 参数空间: {ok2}/{total2}")
    print(f"  - 优化器接受: {'✅' if success3 else '❌'}")
    print(f"  - 批量接口: {'✅' if success4 else '❌'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
