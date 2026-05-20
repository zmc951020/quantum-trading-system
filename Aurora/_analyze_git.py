#!/usr/bin/env python3
"""分析git状态，了解牧羊人优化器、集成迁移、错误页面等"""
import subprocess
import os

os.chdir(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout + r.stderr

print("=" * 60)
print("1. GIT LOG (最近20条)")
print("=" * 60)
print(run("git log --oneline -20 --all"))

print("\n" + "=" * 60)
print("2. 当前HEAD状态")
print("=" * 60)
print(run("git log --oneline -1 HEAD"))

print("\n" + "=" * 60)
print("3. 未暂存的修改 (git diff)")
print("=" * 60)
print(run("git diff --name-status"))

print("\n" + "=" * 60)
print("4. 已暂存的修改 (git diff --cached)")
print("=" * 60)
print(run("git diff --cached --name-status"))

print("\n" + "=" * 60)
print("5. 未跟踪的文件")
print("=" * 60)
print(run("git status --short"))

print("\n" + "=" * 60)
print("6. stash列表")
print("=" * 60)
print(run("git stash list"))

print("\n" + "=" * 60)
print("7. 89fbdd31到7b9632d2的变更 (集成迁移到牧羊人)")
print("=" * 60)
print(run("git diff --name-status 89fbdd31..7b9632d2"))

print("\n" + "=" * 60)
print("8. 7b9632d2的提交详情")
print("=" * 60)
print(run("git show 7b9632d2 --stat"))

print("\n" + "=" * 60)
print("9. 89fbdd31的提交详情")
print("=" * 60)
print(run("git show 89fbdd31 --stat"))

print("\n" + "=" * 60)
print("10. 检查templates/deepseek.html的git历史")
print("=" * 60)
print(run("git log --oneline -- templates/deepseek.html"))

print("\n" + "=" * 60)
print("11. 检查templates/maintenance.html的git历史")
print("=" * 60)
print(run("git log --oneline -- templates/maintenance.html"))

print("\n" + "=" * 60)
print("12. 检查shepherd_five_line_optimizer.py的git历史")
print("=" * 60)
print(run("git log --oneline -- shepherd_five_line_optimizer.py"))

print("\n" + "=" * 60)
print("13. 检查所有以_开头的脚本的git历史")
print("=" * 60)
print(run("git log --oneline -- _*.py"))

print("\n" + "=" * 60)
print("14. 检查auto_backtest/strategy_optimizer.py的git历史")
print("=" * 60)
print(run("git log --oneline -- auto_backtest/strategy_optimizer.py"))

print("\n" + "=" * 60)
print("15. 检查auto_backtest/auto_backtest_system.py的git历史")
print("=" * 60)
print(run("git log --oneline -- auto_backtest/auto_backtest_system.py"))

print("\n" + "=" * 60)
print("16. 检查main.py的git历史")
print("=" * 60)
print(run("git log --oneline -- main.py"))

print("\n" + "=" * 60)
print("17. 检查production_start.py的git历史")
print("=" * 60)
print(run("git log --oneline -- production_start.py"))

print("\n" + "=" * 60)
print("18. 检查real_time_trading.py的git历史")
print("=" * 60)
print(run("git log --oneline -- real_time_trading.py"))

print("\n" + "=" * 60)
print("19. 检查templates/index.html的git历史")
print("=" * 60)
print(run("git log --oneline -- templates/index.html"))

print("\n" + "=" * 60)
print("20. 检查visualization.py的git历史")
print("=" * 60)
print(run("git log --oneline -- visualization.py"))
