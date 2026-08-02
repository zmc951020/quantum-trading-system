#!/usr/bin/env python3
"""同花顺金融大师集成 - 最终验证脚本"""
import sys
import os
import json
import importlib.util
from pathlib import Path

# Windows UTF-8 补丁
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

fail = 0
ok = 0


def report(name: str, success: bool, detail: str = ""):
    global ok, fail
    flag = "✅" if success else "❌"
    print(f"  {flag} {name}{(' - ' + detail) if detail else ''}")
    if success:
        ok += 1
    else:
        fail += 1


print("=" * 70)
print("同花顺金融大师集成 - 最终验证")
print("=" * 70)

# ============================================================
# 1. 32策略文件完整性
# ============================================================
print("\n[1] 32策略文件完整性检查")
BASE_14 = ROOT / "core" / "strategies" / "ths_strategies" / "14_strategies"
BASE_18 = ROOT / "core" / "strategies" / "ths_strategies" / "18_advanced"

if BASE_14.exists():
    files_14 = sorted([f.stem for f in BASE_14.glob("*.py") if not f.name.startswith("__")])
    report("14策略文件", len(files_14) == 14, f"实际: {len(files_14)}")
else:
    report("14策略目录", False, "目录不存在")

if BASE_18.exists():
    files_18 = sorted([f.stem for f in BASE_18.glob("*.py") if not f.name.startswith("__")])
    report("18战法文件", len(files_18) == 18, f"实际: {len(files_18)}")
else:
    report("18战法目录", False, "目录不存在")

# ============================================================
# 2. JSON 元数据完整性
# ============================================================
print("\n[2] JSON 元数据完整性")
DATA_DIR = ROOT / "data" / "ths_academy"
for fname, expected_count in [("basics.json", None),
                              ("14_strategies.json", 14),
                              ("18_advanced.json", 18)]:
    fpath = DATA_DIR / fname
    if not fpath.exists():
        report(f"JSON {fname}", False, "文件不存在")
        continue
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "strategies" in data:
            count = len(data["strategies"])
        elif isinstance(data, list):
            count = len(data)
        else:
            count = None
        if expected_count:
            report(f"JSON {fname}", count == expected_count,
                   f"条目数={count}" if count is not None else "结构异常")
        else:
            report(f"JSON {fname}", True, "存在")
    except Exception as e:
        report(f"JSON {fname}", False, str(e)[:50])

# ============================================================
# 3. SignalCollector 加载验证
# ============================================================
print("\n[3] SignalCollector 桥接模块")
try:
    from api.ths_bridge.signal_collector import SignalCollector
    collector = SignalCollector()
    s14, s18 = collector.list_strategies()
    report("14策略加载", len(s14) == 14, f"实际: {len(s14)}")
    report("18战法加载", len(s18) == 18, f"实际: {len(s18)}")
    report("桥接模块总策略数", (len(s14) + len(s18)) == 32,
           f"总数={len(s14) + len(s18)}")
except Exception as e:
    report("SignalCollector导入", False, str(e)[:80])

# ============================================================
# 4. 三类选股分流 (使用唯一测试符号避免与持久化数据冲突)
# ============================================================
print("\n[4] 三类选股分流")
try:
    from core.stock_pool import StockPoolManager, StockSource, PoolLevel
    mgr = StockPoolManager()

    # 测试前清理可能存在的测试残留
    for sym in ["TEST_AUR", "TEST_VIBE", "TEST_THS"]:
        mgr.remove_stock(sym)

    # 使用唯一测试符号
    r1 = mgr.add_stock("TEST_AUR", "Aurora测试", PoolLevel.WATCHLIST,
                       source=StockSource.AURORA_NATIVE,
                       strategy_name="test_aurora")
    r2 = mgr.add_stock("TEST_VIBE", "Vibe测试", PoolLevel.WATCHLIST,
                       source=StockSource.VIBE_TRADING,
                       strategy_name="test_vibe")
    r3 = mgr.add_stock("TEST_THS", "THS测试", PoolLevel.WATCHLIST,
                       source=StockSource.THS_IWENCAI,
                       strategy_name="test_ths")
    report("Aurora自创选股入口", r1.get("success", False))
    report("Vibe Trading选股入口", r2.get("success", False))
    report("同花顺选股入口", r3.get("success", False))

    summary = mgr.get_source_summary()
    report("来源汇总接口", all(k in summary for k in
                              ["aurora_native", "vibe_trading", "ths_iwencai"]),
          f"summary={summary}")

    matrix = mgr.get_source_level_matrix()
    report("来源×池层矩阵接口",
          "aurora_native" in matrix and "ths_iwencai" in matrix)

    # 清理测试数据
    for sym in ["TEST_AUR", "TEST_VIBE", "TEST_THS"]:
        mgr.remove_stock(sym)
except Exception as e:
    report("三类选股分流", False, str(e)[:80])

# ============================================================
# 5. IntegrationBus 三类入口方法
# ============================================================
print("\n[5] IntegrationBus 三类选股入口方法")
try:
    from core.integration_bus import get_integration_bus
    bus = get_integration_bus()
    has_aurora = hasattr(bus, "select_stocks_aurora_native")
    has_vibe = hasattr(bus, "select_stocks_vibe")
    has_ths = hasattr(bus, "select_stocks_ths_iwencai")
    has_compare = hasattr(bus, "get_source_comparison")
    report("select_stocks_aurora_native", has_aurora)
    report("select_stocks_vibe", has_vibe)
    report("select_stocks_ths_iwencai", has_ths)
    report("get_source_comparison", has_compare)
except Exception as e:
    report("IntegrationBus", False, str(e)[:80])

# ============================================================
# 6. 策略类型识别 (含网格交易套利回归测试)
# ============================================================
print("\n[6] 策略类型识别回归")
try:
    from core.enhanced_strategy_manager import EnhancedStrategyManager
    test_cases = [
        ("MACD顺势波段", "ths_strategies"),
        ("5句口诀抓龙头", "ths_strategies"),
        ("龙虎榜跟庄", "ths_strategies"),
        ("BOLL上轨突破", "ths_strategies"),
        ("主力量价操盘", "ths_advanced"),
        ("问财AI选股", "ths_advanced"),
        ("筹码单峰密集", "ths_advanced"),
        ("北向资金跟随", "ths_advanced"),
        ("网格交易套利", "ths_advanced"),  # 回归测试关键点
        ("主力筹码控盘综合", "ths_advanced"),  # 回归测试关键点
    ]
    pass_count = 0
    for name, expected in test_cases:
        actual = EnhancedStrategyManager._detect_strategy_type(name, {})
        if actual == expected:
            pass_count += 1
        else:
            print(f"    ❌ '{name}' → {actual} (期望: {expected})")
    report("策略类型识别", pass_count == len(test_cases),
           f"{pass_count}/{len(test_cases)}")
except Exception as e:
    report("策略类型识别", False, str(e)[:80])

# ============================================================
# 7. 学院蓝图与模板
# ============================================================
print("\n[7] 学院蓝图与模板")
bp_path = ROOT / "ui" / "blueprints" / "ths_academy_bp.py"
report("蓝图 ths_academy_bp.py", bp_path.exists())

tpl_dir = ROOT / "ui" / "templates" / "ths_academy"
if tpl_dir.exists():
    templates = [f.name for f in tpl_dir.glob("*.html")]
    report("index.html", "index.html" in templates)
    report("source_compare.html", "source_compare.html" in templates)
    report("strategy_list.html", "strategy_list.html" in templates)
    report("strategy_detail.html", "strategy_detail.html" in templates)
else:
    report("模板目录", False, "目录不存在")

# ============================================================
# 8. 健康检查 L2_018 / L2_019
# ============================================================
print("\n[8] 健康检查集成")
try:
    from core.system_health_checker import SystemHealthChecker
    checker = SystemHealthChecker()
    # L2 检查方法名为 _build_l2_checks（生成器）
    method_name = "_build_l2_checks" if hasattr(checker, "_build_l2_checks") else "_l2_checks"
    if hasattr(checker, method_name):
        l2_checks = list(getattr(checker, method_name)())
        l2_ids = [c[0] for c in l2_checks]
        report("L2_018 同花顺桥接模块", "L2_018" in l2_ids,
               f"已注册L2数={len(l2_ids)}")
        report("L2_019 三类选股分流", "L2_019" in l2_ids)
    else:
        report("健康检查", False, "未找到L2检查方法")
except Exception as e:
    report("健康检查", False, str(e)[:80])

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 70)
total = ok + fail
print(f"最终验证结果: {ok}/{total} 通过")
if fail == 0:
    print("✅ 全部验证通过 - 可进入Git提交")
else:
    print(f"❌ {fail} 项未通过 - 需修复")
print("=" * 70)
sys.exit(0 if fail == 0 else 1)
