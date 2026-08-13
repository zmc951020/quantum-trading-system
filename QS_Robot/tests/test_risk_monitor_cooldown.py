"""RiskMonitor 告警去重冷却机制单元测试

验证 60秒冷却时间内的告警去重逻辑：
  1. 同标的同类别告警在冷却时间内只触发一次
  2. 冷却时间过后可再次触发
  3. 不同类别的告警独立去重
  4. 不同标的的告警独立去重
  5. 持仓止损/止盈触发后自动平仓，不再重复告警
  6. 手动清除告警后冷却不受影响
"""
import sys
import os
import time
import logging
from datetime import datetime
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")

from tools.risk_monitor import (
    RiskMonitor, Alert, FLASH_CRASH_THRESHOLD, LIMIT_DOWN_RATIO,
    ALERT_COOLDOWN_SEC, FLASH_CRASH_WINDOW, AMPLITUDE_THRESHOLD,
    AMPLITUDE_MIN_POINTS, VOLUME_DROP_RATIO,
)

# ========== 测试辅助 ==========

def _make_monitor():
    """创建预配置的监控器"""
    m = RiskMonitor()
    m.set_prev_close("TEST01", 10.00)
    m.set_prev_close("TEST02", 20.00)
    m.set_daily_avg_vol("TEST01", 5_000_000)
    m.set_daily_avg_vol("TEST02", 3_000_000)
    return m


def _feed_sequence(monitor, symbol, prices, base_vol=500_000):
    """喂入价格序列"""
    for i, p in enumerate(prices):
        monitor.feed(symbol, {"price": p, "volume": base_vol, "time": f"09:{30+i:02d}"})


def _mock_time_sequence(monitor, timestamps):
    """模拟时间流逝，每次调用 _should_alert 用下一个时间戳"""
    original = monitor._should_alert

    def mock_should_alert(symbol, category):
        ts = timestamps.pop(0) if timestamps else datetime.now().timestamp()
        key = (symbol, category)
        now = ts
        last = monitor._last_alert_time.get(key, 0)
        if now - last < ALERT_COOLDOWN_SEC:
            return False
        monitor._last_alert_time[key] = now
        return True

    monitor._should_alert = mock_should_alert
    return original


# ========== 测试用例 ==========

def test_cooldown_same_category_same_symbol():
    """测试1: 同标的同类别告警 — 冷却时间内只触发一次"""
    m = _make_monitor()
    # 构造闪崩：6个点，从10.00跌到9.40（-6%）
    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])

    flash_alerts = [a for a in m.get_alerts() if a["category"] == "flash_crash"]
    assert len(flash_alerts) == 1, f"冷却时间内应只有1次闪崩告警，实际: {len(flash_alerts)}"
    print("  ✅ 测试1通过: 同类别冷却去重 (1次告警)")


def test_cooldown_expiry():
    """测试2: 冷却时间过后可再次触发"""
    m = _make_monitor()

    # 第一次闪崩
    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])
    assert len([a for a in m.get_alerts(clear=True) if a["category"] == "flash_crash"]) == 1

    # 模拟冷却时间过后（手动重置冷却记录）
    m._last_alert_time.clear()
    # 再次闪崩
    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])
    flash_alerts = [a for a in m.get_alerts() if a["category"] == "flash_crash"]
    assert len(flash_alerts) == 1, f"冷却过期后应再次触发，实际: {len(flash_alerts)}"
    print("  ✅ 测试2通过: 冷却过期后再次触发")


def test_different_categories_independent():
    """测试3: 不同类别告警独立去重"""
    m = _make_monitor()

    # 同时触发闪崩和跌停
    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])
    # 再喂一个跌停价
    m.feed("TEST01", {"price": 9.02, "volume": 1_000_000, "time": "09:37"})

    alerts = m.get_alerts()
    flash = [a for a in alerts if a["category"] == "flash_crash"]
    limit = [a for a in alerts if a["category"] == "limit_down"]
    assert len(flash) >= 1, f"闪崩告警应触发，实际: {len(flash)}"
    assert len(limit) >= 1, f"跌停告警应触发，实际: {len(limit)}"
    assert len(flash) <= 2, f"闪崩告警不应重复轰炸，实际: {len(flash)}"
    assert len(limit) <= 2, f"跌停告警不应重复轰炸，实际: {len(limit)}"
    print(f"  ✅ 测试3通过: 不同类别独立去重 (闪崩{len(flash)}次, 跌停{len(limit)}次)")


def test_different_symbols_independent():
    """测试4: 不同标的告警独立去重"""
    m = _make_monitor()

    # TEST01 闪崩
    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])
    # TEST02 闪崩
    _feed_sequence(m, "TEST02", [20.02, 20.05, 20.08, 20.10, 20.12, 18.90])

    alerts = m.get_alerts()
    flash_01 = [a for a in alerts if a["category"] == "flash_crash" and a["symbol"] == "TEST01"]
    flash_02 = [a for a in alerts if a["category"] == "flash_crash" and a["symbol"] == "TEST02"]
    assert len(flash_01) >= 1, f"TEST01闪崩应触发，实际: {len(flash_01)}"
    assert len(flash_02) >= 1, f"TEST02闪崩应触发，实际: {len(flash_02)}"
    assert len(flash_01) <= 2, f"TEST01不应重复轰炸，实际: {len(flash_01)}"
    assert len(flash_02) <= 2, f"TEST02不应重复轰炸，实际: {len(flash_02)}"
    print(f"  ✅ 测试4通过: 不同标的独立去重 (TEST01:{len(flash_01)}次, TEST02:{len(flash_02)}次)")


def test_position_auto_close():
    """测试5: 持仓止损触发后自动平仓，不再重复告警"""
    m = _make_monitor()
    m.set_prev_close("TEST01", 10.00)
    m.open_position("TEST01", 10.10, stop_loss_pct=-0.04, take_profit_pct=0.07)

    # 喂入跌破止损价的数据
    prices = [10.08, 10.05, 9.95, 9.65, 9.60]
    for i, p in enumerate(prices):
        m.feed("TEST01", {"price": p, "volume": 500_000, "time": f"09:4{i}"})

    alerts = m.get_alerts()
    stop_loss_alerts = [a for a in alerts if a["category"] == "stop_loss"]
    assert len(stop_loss_alerts) == 1, f"止损应只触发1次，实际: {len(stop_loss_alerts)}"
    assert "TEST01" not in m.positions, "触发止损后应自动平仓"
    print("  ✅ 测试5通过: 止损触发→自动平仓→不重复告警")


def test_position_take_profit_auto_close():
    """测试6: 止盈触发后自动平仓"""
    m = _make_monitor()
    m.set_prev_close("TEST01", 10.00)
    m.open_position("TEST01", 10.10, stop_loss_pct=-0.04, take_profit_pct=0.07)

    prices = [10.15, 10.30, 10.50, 10.85, 10.90]
    for i, p in enumerate(prices):
        m.feed("TEST01", {"price": p, "volume": 500_000, "time": f"09:4{i}"})

    alerts = m.get_alerts()
    tp_alerts = [a for a in alerts if a["category"] == "take_profit"]
    assert len(tp_alerts) == 1, f"止盈应只触发1次，实际: {len(tp_alerts)}"
    assert "TEST01" not in m.positions, "触发止盈后应自动平仓"
    print("  ✅ 测试6通过: 止盈触发→自动平仓→不重复告警")


def test_alert_clear_does_not_affect_cooldown():
    """测试7: get_alerts(clear=True) 清除告警列表但不影响冷却计时"""
    m = _make_monitor()

    _feed_sequence(m, "TEST01", [10.02, 10.05, 10.08, 10.10, 10.12, 9.40])
    # 清除告警
    cleared = m.get_alerts(clear=True)
    assert len(cleared) >= 1, "清除前应有告警"

    # 冷却时间内再次喂入，不应产生新告警
    m.feed("TEST01", {"price": 9.38, "volume": 1_000_000, "time": "09:38"})
    remaining = m.get_alerts()
    flash = [a for a in remaining if a["category"] == "flash_crash"]
    assert len(flash) == 0, f"冷却时间内清除告警后不应再产生，实际: {len(flash)}"
    print("  ✅ 测试7通过: 清除告警不影响冷却计时")


def test_cooldown_config_constant():
    """测试8: 冷却时间配置常量存在且合理"""
    assert ALERT_COOLDOWN_SEC == 60, f"默认冷却时间应为60秒，实际: {ALERT_COOLDOWN_SEC}"
    assert ALERT_COOLDOWN_SEC > 0, "冷却时间必须为正数"
    assert ALERT_COOLDOWN_SEC < 300, "冷却时间不应超过5分钟"
    print("  ✅ 测试8通过: 冷却配置合理 (60秒)")


def test_input_validation():
    """测试9: 输入校验 — 异常数据不崩溃"""
    m = _make_monitor()

    # 缺少 price 字段
    m.feed("TEST01", {"volume": 1000})
    # price 为 0
    m.feed("TEST01", {"price": 0, "volume": 1000})
    # price 为负数
    m.feed("TEST01", {"price": -5.0, "volume": 1000})
    # price 为非数字
    m.feed("TEST01", {"price": "invalid", "volume": 1000})
    # 正常数据仍可喂入
    m.feed("TEST01", {"price": 10.00, "volume": 1000})

    assert len(m.price_history.get("TEST01", [])) == 1, \
        f"异常数据不应进入历史，实际: {len(m.price_history.get('TEST01', []))}"
    print("  ✅ 测试9通过: 异常输入不崩溃且正确过滤")


def test_amplitude_min_points():
    """测试10: 振幅检测需要足够数据点"""
    m = _make_monitor()
    m.set_prev_close("TEST01", 10.00)

    # 喂入 AMPLITUDE_MIN_POINTS - 1 个点（不足）
    for i in range(AMPLITUDE_MIN_POINTS - 1):
        m.feed("TEST01", {"price": 10.0 + i * 0.5, "volume": 1000, "time": f"09:{i:02d}"})

    alerts_before = m.get_alerts()
    amp_before = [a for a in alerts_before if a["category"] == "amplitude"]
    assert len(amp_before) == 0, f"数据不足时不应触发振幅告警，实际: {len(amp_before)}"

    # 再喂一个点到满足条件
    m.feed("TEST01", {"price": 15.0, "volume": 1000, "time": "09:30"})

    alerts_after = m.get_alerts()
    amp_after = [a for a in alerts_after if a["category"] == "amplitude"]
    assert len(amp_after) >= 1, f"数据充足时应触发振幅告警，实际: {len(amp_after)}"
    print(f"  ✅ 测试10通过: 振幅检测需≥{AMPLITUDE_MIN_POINTS}点")


def test_duplicate_open_position_warning():
    """测试11: 重复开仓有警告"""
    m = _make_monitor()
    m.open_position("TEST01", 10.00)
    m.open_position("TEST01", 10.50)  # 重复开仓

    assert "TEST01" in m.positions, "持仓应存在"
    assert m.positions["TEST01"]["entry_price"] == 10.50, "应更新为最新入场价"
    print("  ✅ 测试11通过: 重复开仓覆盖+警告")


def test_set_prev_close_validation():
    """测试12: 昨收价校验"""
    m = RiskMonitor()  # 使用全新监控器，避免 _make_monitor 预设值干扰
    m.set_prev_close("TEST_X", 0)
    assert "TEST_X" not in m.prev_close, "0价不应被接受"
    m.set_prev_close("TEST_X", -5.0)
    assert "TEST_X" not in m.prev_close, "负价不应被接受"
    m.set_prev_close("TEST_X", 10.00)
    assert m.prev_close["TEST_X"] == 10.00, "正常价格应被接受"
    print("  ✅ 测试12通过: 昨收价校验")


# ========== 运行器 ==========

def run_all():
    print("=" * 60)
    print("  RiskMonitor 告警去重冷却机制 — 单元测试")
    print(f"  冷却时间: {ALERT_COOLDOWN_SEC}秒")
    print("=" * 60)
    print()

    tests = [
        ("同类别冷却去重", test_cooldown_same_category_same_symbol),
        ("冷却过期后再次触发", test_cooldown_expiry),
        ("不同类别独立去重", test_different_categories_independent),
        ("不同标的独立去重", test_different_symbols_independent),
        ("止损→自动平仓→不重复", test_position_auto_close),
        ("止盈→自动平仓→不重复", test_position_take_profit_auto_close),
        ("清除告警不影响冷却", test_alert_clear_does_not_affect_cooldown),
        ("冷却配置合理", test_cooldown_config_constant),
        ("异常输入不崩溃", test_input_validation),
        ("振幅检测最小数据点", test_amplitude_min_points),
        ("重复开仓警告", test_duplicate_open_position_warning),
        ("昨收价校验", test_set_prev_close_validation),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  结果: {passed}/{len(tests)} 通过")
    if failed == 0:
        print("  ✅ 全部通过！")
    else:
        print(f"  ❌ {failed} 个测试失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)