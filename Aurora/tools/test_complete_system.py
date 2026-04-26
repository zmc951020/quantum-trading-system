#!/usr/bin/env python3
"""
测试完整的工具调用系统，包括所有功能
"""

import json
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 测试完整的工具调用系统
print("测试完整的工具调用系统:")
print("=" * 80)

test_requests = [
    # 浏览器导航
    "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站",
    # 文件读取
    "读取d:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py文件",
    # 命令执行
    "运行python strategies/test_all_grid_strategies.py命令",
    # 技能执行
    "使用创建技能",
    "激活分析技能",
    # 智能模块执行
    "使用交易模块",
    "激活分析模块"
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
