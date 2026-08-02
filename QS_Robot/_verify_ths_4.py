"""批量验证所有已实现的同花顺策略测试"""
import sys
import subprocess
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")

test_files = [
    "tests/strategies/ths/test_base.py",
    "tests/strategies/ths/14_strategies/test_01_macd_wave.py",
    "tests/strategies/ths/14_strategies/test_02_weekly_breakout.py",
    "tests/strategies/ths/14_strategies/test_03_dragon_head.py",
    "tests/strategies/ths/14_strategies/test_04_dragon_list_follow.py",
]

all_pass = True
for tf in test_files:
    try:
        r = subprocess.run(
            ["python", "-m", "pytest", tf, "-v", "--tb=short", "--no-header"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=r"D:\Gupiao\升级vscode\QS_Robot"
        )
        out = r.stdout
        passed = out.count("PASSED")
        failed = out.count("FAILED")
        errors = out.count("ERROR")
        status = "PASS" if failed == 0 and errors == 0 and passed > 0 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"[{status}] {tf}: {passed} passed, {failed} failed, {errors} errors")
        if failed > 0 or errors > 0:
            for line in out.split("\n"):
                if "FAILED" in line or "ERROR" in line or "Error" in line:
                    print(f"    {line.strip()[:200]}")
    except Exception as e:
        print(f"[ERR] {tf}: {e}")
        all_pass = False

print(f"\n=== 总结果: {'ALL PASS' if all_pass else 'HAS FAILURES'} ===")
