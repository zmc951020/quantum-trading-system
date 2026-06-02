
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单测试
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("=== 开始测试 ===")
print(f"当前目录: {current_dir}")

ok = True

try:
    import config
    print("[OK] config 模块导入成功")
except Exception as e:
    print(f"[ERROR] config 模块导入失败: {e}")
    ok = False

try:
    import llm_manager
    print("[OK] llm_manager 模块导入成功")
except Exception as e:
    print(f"[ERROR] llm_manager 模块导入失败: {e}")
    import traceback
    traceback.print_exc()
    ok = False

try:
    from flask import Flask
    print("[OK] flask 导入成功")
except Exception as e:
    print(f"[ERROR] flask 导入失败: {e}")
    ok = False

print("=== 测试完成 ===")

if ok:
    print("\n所有模块导入成功!")
else:
    print("\n有模块导入失败!")

