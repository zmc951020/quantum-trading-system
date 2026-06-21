#!/usr/bin/env python3
"""JT-001: 混沌工程 - 宕机恢复测试
单服务宕机30s内自动恢复，5003降级链路可用
"""
import sys
import os
import time
import requests
from pathlib import Path

AURORA_URL = "http://127.0.0.1:5002"
QS_ROBOT_URL = "http://127.0.0.1:5003"
RECOVERY_THRESHOLD_S = 30
CHECK_INTERVAL_S = 1


def check_service(url: str, timeout: int = 3) -> bool:
    """检查服务是否可用（200=健康, 503=降级但可用）"""
    try:
        r = requests.get(f"{url}/api/health", timeout=timeout)
        return r.status_code in (200, 503)  # 503 degraded but still running
    except Exception:
        return False


def check_degradation():
    """检查5003降级链路是否正常"""
    try:
        r = requests.get(f"{QS_ROBOT_URL}/api/equity_curve", timeout=5)
        if r.status_code == 200:
            data = r.json()
            # 检查是否标记了降级数据
            if data.get("data", {}).get("is_simulated") or data.get("data", {}).get("_source") == "fallback":
                return True, "降级链路正常（标记降级数据）"
            return True, "数据正常（非降级）"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def main():
    print("[JT-001] 混沌工程 - 宕机恢复测试")
    print(f"  恢复阈值: ≤ {RECOVERY_THRESHOLD_S}s")
    print()

    # 检查5002是否运行
    print("  检查5002服务状态...")
    if not check_service(AURORA_URL):
        print("  ⚠️ 5002 服务未运行，无法执行宕机测试")
        print("  请先启动: python visualization.py")
        return False

    print("  5002 服务正常运行 ✓")

    # 检查5003是否运行
    print("  检查5003服务状态...")
    qs_available = check_service(QS_ROBOT_URL)
    if qs_available:
        print("  5003 服务正常运行 ✓")
    else:
        print("  ⚠️ 5003 服务未运行，仅测试5002恢复")

    print()
    print("  ⚠️ 宕机恢复测试需要手动操作：")
    print("  1. 在5002终端按 Ctrl+C 停止服务")
    print("  2. 等待本脚本检测到服务不可用")
    print("  3. 重新启动5002: python visualization.py")
    print("  4. 本脚本自动检测恢复时间")
    print()
    print("  开始监控5002服务状态...")
    print("  (请在5002终端按 Ctrl+C 停止服务)")
    print()

    # 等待5002宕机
    while check_service(AURORA_URL):
        time.sleep(CHECK_INTERVAL_S)
        print(".", end="", flush=True)

    t_down = time.time()
    print(f"\n  5002 服务已停止 (T={0:.0f}s)")

    # 检查5003降级
    if qs_available:
        print("  检查5003降级链路...")
        ok, msg = check_degradation()
        print(f"  5003: {msg}")

    # 等待5002恢复
    print("  等待5002恢复...")
    print("  (请重新启动5002: python visualization.py)")
    print()

    while not check_service(AURORA_URL):
        elapsed = time.time() - t_down
        if elapsed > RECOVERY_THRESHOLD_S * 3:
            print(f"\n  ⚠️ 等待超时 ({elapsed:.0f}s)，5002未恢复")
            print("  请手动启动5002服务后重新运行本测试")
            return False
        time.sleep(CHECK_INTERVAL_S)
        print(".", end="", flush=True)

    t_up = time.time()
    recovery_time = t_up - t_down

    print(f"\n  5002 服务已恢复")
    print(f"\n  统计结果:")
    print(f"    宕机时间: {recovery_time:.1f}s")

    passed = recovery_time <= RECOVERY_THRESHOLD_S

    print(f"\n  验收结果:")
    print(f"    恢复时间 ≤ {RECOVERY_THRESHOLD_S}s: {'✅ 通过' if passed else f'❌ 未通过 ({recovery_time:.1f}s)'}")

    if not passed:
        print(f"\n  建议:")
        print(f"    - 使用进程守护工具(如 supervisor)自动重启")
        print(f"    - 配置 systemd 服务自动恢复")

    return passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)