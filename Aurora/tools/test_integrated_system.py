#!/usr/bin/env python3
"""
测试集成了链式执行器的工具管理器
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager

# 测试集成系统
print("测试集成了链式执行器的工具管理器")
print("=" * 80)

# 测试1：浏览器导航（需要VPN）
print("\n测试1：浏览器导航（需要VPN）")
print("-" * 80)
request1 = "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站"
print(f"请求: {request1}")
result1 = tool_manager.process_request(request1)
print(f"处理结果: {result1}")

# 测试2：文件读取
print("\n测试2：文件读取")
print("-" * 80)
request2 = "读取d:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py文件"
print(f"请求: {request2}")
result2 = tool_manager.process_request(request2)
print(f"处理结果: {result2}")

# 测试3：激活智能模块
print("\n测试3：激活智能模块")
print("-" * 80)
request3 = "激活智能记忆模块"
print(f"请求: {request3}")
result3 = tool_manager.process_request(request3)
print(f"处理结果: {result3}")

print("\n" + "=" * 80)
print("测试完成！")
