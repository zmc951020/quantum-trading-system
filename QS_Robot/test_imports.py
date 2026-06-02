#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试导入
"""
import sys
import os

# 设置输出编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
elif sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 开始测试 ===")

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"当前目录: {current_dir}")

try:
    import config
    print("OK config 模块导入成功")
except Exception as e:
    print(f"FAIL config 模块导入失败: {e}")
    import traceback
    traceback.print_exc()

try:
    import llm_manager
    print("OK llm_manager 模块导入成功")
except Exception as e:
    print(f"FAIL llm_manager 模块导入失败: {e}")
    import traceback
    traceback.print_exc()

try:
    from extensions.llm_providers import ollama_provider
    print("OK ollama_provider 导入成功")
except Exception as e:
    print(f"FAIL ollama_provider 导入失败: {e}")
    import traceback
    traceback.print_exc()

try:
    from flask import Flask
    print("OK flask 导入成功")
except Exception as e:
    print(f"FAIL flask 导入失败: {e}")

try:
    from qs_robot_core import QSRobotCore
    print("OK qs_robot_core 导入成功")
except Exception as e:
    print(f"FAIL qs_robot_core 导入失败: {e}")
    import traceback
    traceback.print_exc()

try:
    from extensions.data_sources import AuroraDataSource
    print("OK AuroraDataSource 导入成功")
except Exception as e:
    print(f"FAIL AuroraDataSource 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("=== 测试完成 ===")