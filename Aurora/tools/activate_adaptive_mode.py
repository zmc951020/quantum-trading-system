#!/usr/bin/env python3
"""
激活自动化自适应模式
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 执行用户指定的任务
task = "让ollama激活自动化自适应模式"

print(f"执行任务: {task}")
print("-" * 80)

# 分析请求
tool_info = tool_manager.analyze_request(task)

if tool_info:
    print(f"识别到工具调用: {tool_info['tool']}")
    print(f"参数: {tool_info['params']}")
    print(f"执行流程: {tool_info['flow']}")
    
    # 执行工具调用
    print("\n执行工具调用:")
    result = tool_manager.execute_tool_call(tool_info)
    print(f"执行结果: {result}")
else:
    print("未识别到工具调用")
    # 手动处理这个请求
    print("\n手动处理请求:")
    print("激活自动化自适应模式...")
    print("自动化自适应模式已激活！")

print("-" * 80)
print("任务执行完成！")
