#!/usr/bin/env python3
"""
测试工具调用系统
"""

import json
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ollama_tool_config import ollama_tool_config
from tool_manager import tool_manager

# 测试触发规则
print("测试触发规则:")
test_requests = [
    "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站",
    "读取d:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py文件",
    "运行python strategies/test_all_grid_strategies.py命令"
]

for request in test_requests:
    print(f"\n测试请求: {request}")
    tool_info = tool_manager.analyze_request(request)
    if tool_info:
        print(f"识别到工具调用: {tool_info['tool']}")
        print(f"参数: {json.dumps(tool_info['params'], ensure_ascii=False)}")
        print(f"执行流程: {tool_info['flow']}")
    else:
        print("未识别到工具调用")

# 测试安全配置
print("\n\n测试安全配置:")
test_paths = [
    "d:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py",
    "c:\\Windows\\System32\\cmd.exe"
]

for path in test_paths:
    print(f"路径: {path}")
    print(f"是否允许: {ollama_tool_config.validate_path(path)}")

test_urls = [
    "https://www.youtube.com/watch?v=R6fZR_9kmIw",
    "https://malicious.com"
]

for url in test_urls:
    print(f"URL: {url}")
    print(f"是否允许: {ollama_tool_config.validate_url(url)}")

test_commands = [
    "python strategies/test_all_grid_strategies.py",
    "format C:"
]

for command in test_commands:
    print(f"命令: {command}")
    print(f"是否允许: {ollama_tool_config.validate_command(command)}")
