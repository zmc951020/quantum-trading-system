#!/usr/bin/env python3
"""获取git信息，分析当前状态"""
import subprocess
import os

os.chdir(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return r.stdout.strip()

print("=== GIT LOG ===")
print(run("git log --oneline -15 --no-color"))

print("\n=== HEAD COMMIT ===")
print(run("git show HEAD --stat --no-color"))

print("\n=== DIFF HEAD vs origin/main (f68571e3) ===")
print(run("git diff --name-status f68571e3 HEAD --no-color"))

print("\n=== STASH LIST ===")
print(run("git stash list --no-color"))

print("\n=== STASH SHOW ===")
print(run("git stash show --name-status --no-color"))

print("\n=== UNTRACKED FILES ===")
print(run("git ls-files --others --exclude-standard"))

print("\n=== DIFF HEAD -- templates/ ===")
print(run("git diff HEAD -- templates/ --no-color"))
