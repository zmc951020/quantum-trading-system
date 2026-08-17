"""方案A: 安全清理临时文件和脚本"""
import os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "archive")

# 35个临时脚本 (保留 _verify_three_entries.py 和 __init__.py)
TEMP_SCRIPTS = [
    "_verify_p0_fixes.py", "_verify_runtime.py", "_add_applicable_pool.py",
    "_test_auditor_mock.py", "_verify_final.py", "_verify_security_fixes.py",
    "_verify_ths_18.py", "_verify_strategic_params.py", "_test_degradation.py",
    "_verify_vibe_full.py", "_verify_ths_14.py", "_verify_oneclick.py",
    "_verify_integration.py", "_verify_sf_integration.py", "_verify_quick.py",
    "_test_approval_api.py", "_add_strategy_id.py", "_verify_all_final.py",
    "_verify_pool_filter.py", "_vibe_e2e_test.py", "_test_api_approval.py",
    "_scan_vibe_skills.py", "_explore_vibe_api.py", "_verify_ths_4.py",
    "_quick_verify.py", "_verify_health.py", "_test_registry.py",
    "_verify_engineering_loop.py", "_test_integration.py", "_test_new_endpoints.py",
    "_verify.py", "_seed_approval_data.py", "_check_engine_names.py",
    "_check_vibe.py", "_test_vibe_status.py",
]

# 6个临时输出文件
OUTPUT_FILES = [
    "_check_funcs.txt", "_page_results.txt", "_test_output.txt",
    "_vibe_e2e_output.txt", "_vibe_full_analysis.txt", "_vibe_skills_analysis.txt",
]

# 19个根目录测试脚本 -> tests/
ROOT_TESTS = [
    "test_comprehensive_audit.py", "test_reliability.py", "test_l5.py",
    "test_l7.py", "test_l6.py", "test_l4.py", "test_route_validation.py",
    "test_data_bus.py", "test_auto_flow.py", "test_full_system.py",
    "test_system.py", "test_optimizer_chain.py", "test_health_check.py",
    "test_imports.py", "test_security_fixes.py", "test_simple.py",
    "test_flask.py", "test_template.py", "test_trade_debug.py",
]

def main():
    print("=== 方案A: 安全清理 ===")
    stats = {"moved": 0, "deleted": 0, "errors": 0}

    os.makedirs(ARCHIVE, exist_ok=True)

    # 1. 移动临时脚本到 archive/
    print("\n[1/4] 移动临时脚本到 archive/")
    for fname in TEMP_SCRIPTS:
        src = os.path.join(ROOT, fname)
        dst = os.path.join(ARCHIVE, fname)
        if os.path.exists(src):
            shutil.move(src, dst)
            stats["moved"] += 1
            print(f"  ✓ {fname}")
        else:
            print(f"  - {fname} (不存在)")

    # 2. 删除临时输出文件
    print("\n[2/4] 删除临时输出文件")
    for fname in OUTPUT_FILES:
        fpath = os.path.join(ROOT, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            stats["deleted"] += 1
            print(f"  ✓ {fname}")

    # 3. 移动根目录测试脚本到 tests/
    print("\n[3/4] 移动根目录测试脚本到 tests/")
    for fname in ROOT_TESTS:
        src = os.path.join(ROOT, fname)
        dst = os.path.join(ROOT, "tests", fname)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.move(src, dst)
            stats["moved"] += 1
            print(f"  ✓ {fname} -> tests/")
        elif os.path.exists(dst):
            print(f"  - {fname} (tests/中已存在，保留原文件)")

    # 4. 删除 temp/ 目录
    print("\n[4/4] 删除 temp/ 目录")
    temp_dir = os.path.join(ROOT, "temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print(f"  ✓ temp/ 已删除")

    print(f"\n=== 清理完成: 移动{stats['moved']}个, 删除{stats['deleted']}个, 错误{stats['errors']}个 ===")
    print(f"归档位置: {ARCHIVE}")
    return 0

if __name__ == "__main__":
    sys.exit(main())