"""生产环境部署后验收测试用例
用法: python extensions/tools/acceptance_tests.py [--quick] [--json]
覆盖: 8层巡检 / L2业务链路 / 三大入口 / API端点 / 安全配置
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://127.0.0.1:5003"
RESULTS = []
SESSION = requests.Session()


def login():
    r = SESSION.post(f"{BASE_URL}/api/auth/login",
                     json={"username": "admin", "password": "admin123"}, timeout=10)
    return r.status_code == 200


def test(name: str, category: str) -> callable:
    def decorator(fn):
        def wrapper():
            t0 = time.time()
            try:
                passed, detail = fn()
                elapsed = round((time.time() - t0) * 1000, 1)
            except Exception as e:
                passed, detail, elapsed = False, str(e), round((time.time() - t0) * 1000, 1)
            RESULTS.append({"category": category, "name": name, "passed": passed,
                            "detail": detail, "elapsed_ms": elapsed})
            status = "✅" if passed else "❌"
            print(f"  {status} [{category}] {name}: {detail} ({elapsed}ms)")
            return passed
        return wrapper
    return decorator


# ============================================================
# 1. 系统基础可用性 (5项)
# ============================================================
@test("服务端口可达", "基础可用性")
def t1_1():
    r = requests.get(f"{BASE_URL}/", timeout=5)
    return r.status_code in (200, 302), f"HTTP {r.status_code}"

@test("用户认证登录", "基础可用性")
def t1_2():
    return login(), "登录成功"

@test("系统状态API", "基础可用性")
def t1_3():
    r = SESSION.get(f"{BASE_URL}/api/status", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("API网关响应", "基础可用性")
def t1_4():
    r = SESSION.get(f"{BASE_URL}/api/health", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("维护界面可访问", "基础可用性")
def t1_5():
    r = requests.get(f"{BASE_URL}/maintenance", timeout=5)
    return r.status_code == 200, "维护界面加载成功"


# ============================================================
# 2. 一键巡检功能 (6项)
# ============================================================
@test("快速巡检执行", "一键巡检")
def t2_1():
    r = SESSION.post(f"{BASE_URL}/api/health/check", json={"mode": "quick"}, timeout=60)
    data = r.json()
    return data.get("success"), f"评分={data.get('data',{}).get('overall_score','?')}"

@test("深度巡检执行", "一键巡检")
def t2_2():
    r = SESSION.post(f"{BASE_URL}/api/health/check", json={"mode": "deep"}, timeout=120)
    data = r.json()
    return data.get("success"), f"评分={data.get('data',{}).get('overall_score','?')}"

@test("L2业务链路巡检", "一键巡检")
def t2_3():
    r = SESSION.post(f"{BASE_URL}/api/health/check/l2", json={"mode": "quick"}, timeout=60)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("三大入口验收", "一键巡检")
def t2_4():
    r = SESSION.post(f"{BASE_URL}/api/health/check/three_entry", timeout=30)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("自动修复功能", "一键巡检")
def t2_5():
    r = SESSION.post(f"{BASE_URL}/api/health/auto-fix", timeout=10)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("巡检报告列表", "一键巡检")
def t2_6():
    r = SESSION.get(f"{BASE_URL}/api/health/reports", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"


# ============================================================
# 3. 架构层覆盖 (7项，对应实际API返回的7层)
# ============================================================
LAYER_NAMES = ["安全与认证", "业务功能链路", "系统可靠性", "数据与行情",
               "交易与风控", "AI与智能体", "运维与部署"]

def _check_layer(name):
    r = SESSION.post(f"{BASE_URL}/api/health/check", json={"mode": "quick"}, timeout=60)
    layers = r.json().get("data", {}).get("layers", [])
    layer = next((l for l in layers if l.get("name") == name), None)
    if layer is None:
        return False, "层未找到"
    return layer.get("status") != "critical", f"状态={layer.get('status','?')}, 评分={layer.get('score','?')}"

@test("安全与认证层", "架构层")
def t3_1(): return _check_layer("安全与认证")

@test("业务功能链路层", "架构层")
def t3_2(): return _check_layer("业务功能链路")

@test("系统可靠性层", "架构层")
def t3_3(): return _check_layer("系统可靠性")

@test("数据与行情层", "架构层")
def t3_4(): return _check_layer("数据与行情")

@test("交易与风控层", "架构层")
def t3_5(): return _check_layer("交易与风控")

@test("AI与智能体层", "架构层") 
def t3_6(): return _check_layer("AI与智能体")

@test("运维与部署层", "架构层")
def t3_7(): return _check_layer("运维与部署")


# ============================================================
# 4. 策略与模块 (5项)
# ============================================================
@test("策略列表API", "策略模块")
def t4_1():
    r = SESSION.get(f"{BASE_URL}/api/strategy/list", timeout=5)
    data = r.json()
    count = len(data.get("data", {}).get("strategies", []))
    return count > 0, f"{count}个策略"

@test("策略注册表", "策略模块")
def t4_2():
    r = SESSION.get(f"{BASE_URL}/api/strategy/registry/summary", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("风控状态API", "策略模块")
def t4_3():
    r = SESSION.get(f"{BASE_URL}/api/risk/status", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("优化器列表", "策略模块")
def t4_4():
    r = SESSION.get(f"{BASE_URL}/api/optimizer/list", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("工作流状态", "策略模块")
def t4_5():
    r = SESSION.get(f"{BASE_URL}/api/workflow/status", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"


# ============================================================
# 5. 安全配置 (5项)
# ============================================================
@test("安全配置API", "安全配置")
def t5_1():
    r = SESSION.get(f"{BASE_URL}/api/security/config", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("CSRF Token", "安全配置")
def t5_2():
    r = SESSION.get(f"{BASE_URL}/api/security/csrf-token", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("安全状态检查", "安全配置")
def t5_3():
    r = SESSION.get(f"{BASE_URL}/api/security/status", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"

@test("未登录拒绝访问", "安全配置")
def t5_4():
    r = requests.get(f"{BASE_URL}/api/strategy/list", timeout=5)
    return r.status_code == 401, f"HTTP {r.status_code} (应401)"

@test("审计日志", "安全配置")
def t5_5():
    r = SESSION.get(f"{BASE_URL}/api/security/audit-logs", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"


# ============================================================
# 6. 性能基准 (4项)
# ============================================================
@test("快速巡检耗时", "性能基准")
def t6_1():
    t0 = time.time()
    r = SESSION.post(f"{BASE_URL}/api/health/check", json={"mode": "quick"}, timeout=30)
    elapsed = time.time() - t0
    return elapsed < 60, f"{elapsed:.1f}s (目标<60s)"

@test("API响应时间", "性能基准")
def t6_2():
    t0 = time.time()
    r = SESSION.get(f"{BASE_URL}/api/status", timeout=5)
    elapsed = (time.time() - t0) * 1000
    return elapsed < 500, f"{elapsed:.0f}ms (目标<500ms)"

@test("策略列表响应", "性能基准")
def t6_3():
    t0 = time.time()
    r = SESSION.get(f"{BASE_URL}/api/strategy/list", timeout=5)
    elapsed = (time.time() - t0) * 1000
    return elapsed < 1000, f"{elapsed:.0f}ms (目标<1000ms)"

@test("并发请求稳定性", "性能基准")
def t6_4():
    import concurrent.futures
    def req():
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=5)
            return r.status_code == 200
        except:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as e:
        results = list(e.map(lambda _: req(), range(5)))
    ok = sum(results)
    return ok >= 4, f"{ok}/5 并发成功"


# ============================================================
# 汇总
# ============================================================
def run_all(quick=False):
    print("=" * 60)
    print("  生产环境部署后验收测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标: {BASE_URL}")
    print("=" * 60)

    if not login():
        print("\n❌ 登录失败，终止测试")
        return

    groups = [
        ("基础可用性", [t1_1, t1_2, t1_3, t1_4, t1_5]),
        ("一键巡检", [t2_1, t2_2, t2_3, t2_4, t2_5, t2_6]),
        ("架构层", [t3_1, t3_2, t3_3, t3_4, t3_5, t3_6, t3_7]),
        ("策略模块", [t4_1, t4_2, t4_3, t4_4, t4_5]),
        ("安全配置", [t5_1, t5_2, t5_3, t5_4, t5_5]),
        ("性能基准", [t6_1, t6_2, t6_3, t6_4]),
    ]

    if quick:
        groups = [(g[0], g[1][:2]) for g in groups]

    for label, tests in groups:
        print(f"\n📋 {label}:")
        for t in tests:
            t()

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed
    elapsed = sum(r["elapsed_ms"] for r in RESULTS)

    print("\n" + "=" * 60)
    print(f"  总计: {total} | 通过: {passed} | 失败: {failed}")
    print(f"  通过率: {passed/total*100:.1f}% | 总耗时: {elapsed/1000:.1f}s")
    if failed:
        print(f"\n  ❌ 失败项:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"    - [{r['category']}] {r['name']}: {r['detail']}")
    print("=" * 60)

    return {"total": total, "passed": passed, "failed": failed,
            "pass_rate": round(passed / total * 100, 1), "results": RESULTS}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="验收测试")
    parser.add_argument("--quick", action="store_true", help="快速模式")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    result = run_all(args.quick)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())