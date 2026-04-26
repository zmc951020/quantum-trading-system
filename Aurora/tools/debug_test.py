#!/usr/bin/env python3
"""
调试测试
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 测试1：分析请求
print("测试1：分析请求")
print("-" * 80)
request = "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站"
print(f"请求: {request}")
tool_info = tool_manager.analyze_request(request)
print(f"工具信息: {tool_info}")

if tool_info:
    print("\n执行工具调用")
    result = tool_manager.execute_tool_call(tool_info)
    print(f"结果: {result}")
