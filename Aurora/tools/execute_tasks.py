#!/usr/bin/env python3
"""
执行用户指定的任务
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 执行用户指定的任务
tasks = [
    "打开新浪网",
    "读取文件 \"D:\\Gupiao\\量化交易测试设备方案\\攒机\\量化交易\\量化数学算法\\策略模型探索路径\\模型比较.md\"",
    "激活智能记忆模块"
]

for i, task in enumerate(tasks):
    print(f"\n执行任务 {i+1}: {task}")
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
    
    print("-" * 80)

print("\n任务执行完成！")
