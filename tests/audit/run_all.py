#!/usr/bin/env python3
"""Aurora 量化系统全维度审核 - 一键运行入口
按顺序执行所有审核脚本，生成汇总报告
"""
import sys
import os
import subprocess
import time
from pathlib import Path

AUDIT_DIR = Path(__file__).parent

# 审核脚本清单（按依赖顺序排列）
AUDIT_SCRIPTS = [
    # 静态分析（无需服务运行）
    ("check_secrets.py", "JT-003 密钥硬编码扫描", False),
    ("test_probe_coverage.py", "SJ-001 探针覆盖率审计", False),
    ("test_burial_audit.py", "QZ-001 埋点覆盖率审计", False),
    # 基准测试（无需服务运行）
    ("test_factor_benchmark.py", "SW-001 多因子并行基准", False),
    ("test_extreme_scenario.py", "联动 极端行情场景模拟", False),
    # 需要5002服务的测试
    ("test_proxy_latency.py", "QX-002 代理通信延迟", True),
    ("test_latency_chain.py", "QX-001 全链路延迟统计", True),
    # 需要手动介入的测试
    ("test_chaos.py", "JT-001 混沌工程宕机恢复", True),
]


def run_script(script_name: str, description: str, needs_service: bool) -> dict:
    """运行单个审核脚本"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")

    if needs_service:
        print(f"  ⚠️ 此测试需要 5002 服务运行中")
        # 检查服务是否可用（200=健康, 503=降级但可用）
        try:
            import requests
            r = requests.get("http://127.0.0.1:5002/api/health", timeout=3)
            if r.status_code not in (200, 503):
                print(f"  ⚠️ 5002 服务不可用，跳过此测试")
                return {"script": script_name, "success": None, "skipped": True, "reason": "5002服务不可用"}
        except Exception:
            print(f"  ⚠️ 5002 服务不可达，跳过此测试")
            return {"script": script_name, "success": None, "skipped": True, "reason": "5002服务不可达"}

    script_path = AUDIT_DIR / script_name
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(AUDIT_DIR),
        )
        elapsed = time.time() - t0
        print(result.stdout)
        if result.stderr:
            print(f"[stderr]: {result.stderr[:500]}")

        return {
            "script": script_name,
            "success": result.returncode == 0,
            "skipped": False,
            "elapsed": elapsed,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "script": script_name,
            "success": False,
            "skipped": False,
            "elapsed": 120,
            "reason": "超时(>120s)",
        }
    except Exception as e:
        return {
            "script": script_name,
            "success": False,
            "skipped": False,
            "elapsed": 0,
            "reason": str(e),
        }


def main():
    print("=" * 60)
    print("  Aurora 量化系统 全维度审核")
    print("  审核框架: 身心拟人化七维度（气血/神经/思维/肌体/意识/全知全觉）")
    print("=" * 60)

    results = []
    for script_name, description, needs_service in AUDIT_SCRIPTS:
        result = run_script(script_name, description, needs_service)
        results.append(result)

    # 汇总报告
    print(f"\n\n{'='*60}")
    print(f"  审核汇总报告")
    print(f"{'='*60}")

    total = len(results)
    passed = sum(1 for r in results if r["success"] is True)
    failed = sum(1 for r in results if r["success"] is False)
    skipped = sum(1 for r in results if r["skipped"])

    print(f"\n  脚本总数: {total}")
    print(f"  通过:     {passed}")
    print(f"  未通过:   {failed}")
    print(f"  跳过:     {skipped}")

    print(f"\n  详细结果:")
    for r in results:
        if r["skipped"]:
            status = "⏭️ 跳过"
        elif r["success"]:
            status = "✅ 通过"
        else:
            status = "❌ 未通过"

        extra = f" ({r.get('reason', '')})" if r.get("reason") else ""
        elapsed = f" [{r.get('elapsed', 0):.1f}s]" if r.get("elapsed") else ""
        print(f"  {status} {r['script']}{elapsed}{extra}")

    # 评分
    effective_total = total - skipped
    if effective_total > 0:
        score = (passed / effective_total) * 100
        print(f"\n  综合得分: {score:.0f}/100")
        if score >= 90:
            print(f"  等级: A - 系统健康，可投入实盘")
        elif score >= 75:
            print(f"  等级: B - 基本可用，有改进空间")
        elif score >= 60:
            print(f"  等级: C - 存在风险，需整改后上线")
        else:
            print(f"  等级: D - 存在严重缺陷，禁止实盘")

    print()
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)