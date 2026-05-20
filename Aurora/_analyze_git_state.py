#!/usr/bin/env python3
"""分析当前Git状态，理解集成迁移和牧羊人优化器的关系"""
import subprocess
import os

os.chdir(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip()

print("=" * 60)
print("GIT LOG (最近5个)")
print("=" * 60)
print(run("git log --oneline -5"))

print("\n" + "=" * 60)
print("GIT STATUS")
print("=" * 60)
print(run("git status --short"))

print("\n" + "=" * 60)
print("STASH LIST")
print("=" * 60)
print(run("git stash list"))

print("\n" + "=" * 60)
print("STASH CONTENT (files)")
print("=" * 60)
print(run("git stash show --name-status"))

print("\n" + "=" * 60)
print("DIFF f68571e3..89fbdd31 (集成迁移)")
print("=" * 60)
print(run("git diff --name-status f68571e3..89fbdd31"))

print("\n" + "=" * 60)
print("DIFF 89fbdd31..7b9632d2 (牧羊人提交)")
print("=" * 60)
print(run("git diff --name-status 89fbdd31..7b9632d2"))

print("\n" + "=" * 60)
print("DIFF f68571e3..7b9632d2 (总变化)")
print("=" * 60)
print(run("git diff --name-status f68571e3..7b9632d2"))

print("\n" + "=" * 60)
print("DIFF HEAD (未暂存)")
print("=" * 60)
print(run("git diff --name-status HEAD"))

print("\n" + "=" * 60)
print("DIFF --cached (已暂存)")
print("=" * 60)
print(run("git diff --cached --name-status"))

print("\n" + "=" * 60)
print("文件存在性检查")
print("=" * 60)
files_to_check = [
    "shepherd_five_line_optimizer.py",
    "signals/market_state_hub.py",
    "strategies/strategy_registry.py",
    "_add_strategy_info_endpoint.py",
    "_audit_strategies.py",
    "_check_db.py",
    "_find_lines.py",
    "_update_frontend.py",
]
for f in files_to_check:
    exists = os.path.exists(f)
    print(f"  {'✓' if exists else '✗'} {f}")
