#!/usr/bin/env python3
"""
测试技能和智能模块的触发和执行
"""

import json
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 测试技能和智能模块的触发和执行
print("测试技能和智能模块的触发和执行:")
print("=" * 80)

test_requests = [
    "使用创建技能",
    "激活分析技能",
    "运行测试技能",
    "执行优化技能",
    "使用交易模块",
    "激活分析模块",
    "运行测试模块",
    "执行优化模块"
]

for i, request in enumerate(test_requests):
    print(f"\n测试请求 {i+1}: {request}")
    print("-" * 80)
    
    # 分析请求
    tool_info = tool_manager.analyze_request(request)
    
    if tool_info:
        print(f"识别到工具调用: {tool_info['tool']}")
        print(f"参数: {json.dumps(tool_info['params'], ensure_ascii=False)}")
        print(f"执行流程: {tool_info['flow']}")
        
        # 执行工具调用
        print("\n执行工具调用:")
        result = tool_manager.execute_tool_call(tool_info)
        print(f"执行结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print("未识别到工具调用")
    
    print("-" * 80)

print("\n测试完成！")
