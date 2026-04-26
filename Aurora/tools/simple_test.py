#!/usr/bin/env python3
"""
简单测试
直接创建tool_info来测试链式执行器
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chain_executor import chain_executor
from tool_executor import tool_executor

print("简单测试链式执行器")
print("=" * 80)

# 直接创建工具信息
test_tool_info = {
    "tool_type": "browser",
    "tool": "browser_navigate",
    "params": {
        "url": "https://www.youtube.com/watch?v=R6fZR_9kmIw",
        "newTab": True,
        "take_screenshot_afterwards": True
    },
    "flow": []
}

print(f"测试工具信息: {test_tool_info}")
print()

result = chain_executor.execute_with_chain(test_tool_info)
print()
print(f"执行结果: {result}")
