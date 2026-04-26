#!/usr/bin/env python3
"""
Ollama 性能综合测试
测试工具调用、链式执行、智能判断、网络连接和多工具协作的性能
"""

import time
import json
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager
from chain_executor import chain_executor

class PerformanceTest:
    """
    Ollama 性能测试类
    """

    def __init__(self):
        """
        初始化性能测试
        """
        self.results = {}

    def test_tool_call_performance(self):
        """
        测试工具调用性能
        """
        print("\n测试1：工具调用性能")
        print("-" * 80)

        # 测试1.1：浏览器导航
        start_time = time.time()
        request1 = "打开https://www.google.com网站"
        result1 = tool_manager.process_request(request1)
        elapsed1 = time.time() - start_time
        print(f"浏览器导航: {elapsed1:.4f}秒")

        # 测试1.2：文件读取
        test_file = "d:\\test\\performance_test.txt"
        # 先创建测试文件
        if not os.path.exists(os.path.dirname(test_file)):
            os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("测试文件内容")
        
        start_time = time.time()
        request2 = f"读取{test_file}文件"
        result2 = tool_manager.process_request(request2)
        elapsed2 = time.time() - start_time
        print(f"文件读取: {elapsed2:.4f}秒")

        return {
            "browser_navigate": elapsed1,
            "file_read": elapsed2,
            "average": (elapsed1 + elapsed2) / 2
        }

    def test_chain_execution_performance(self):
        """
        测试链式执行性能
        """
        print("\n测试2：链式执行性能")
        print("-" * 80)

        # 测试2.1：带VPN的浏览器导航
        start_time = time.time()
        request1 = "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站"
        result1 = tool_manager.process_request(request1)
        elapsed1 = time.time() - start_time
        print(f"带VPN的浏览器导航: {elapsed1:.4f}秒")

        # 测试2.2：带目录创建的文件写入
        test_file = "d:\\test\\new_dir\\new_file.txt"
        start_time = time.time()
        request2 = f"写入{test_file}文件"
        result2 = tool_manager.process_request(request2)
        elapsed2 = time.time() - start_time
        print(f"带目录创建的文件写入: {elapsed2:.4f}秒")

        return {
            "vpn_browser": elapsed1,
            "directory_creation": elapsed2,
            "average": (elapsed1 + elapsed2) / 2
        }

    def test_intelligent_judgment(self):
        """
        测试智能判断性能
        """
        print("\n测试3：智能判断性能")
        print("-" * 80)

        # 测试3.1：不需要工具调用的请求
        start_time = time.time()
        request1 = "你好，今天天气怎么样？"
        result1 = tool_manager.process_request(request1)
        elapsed1 = time.time() - start_time
        print(f"不需要工具调用的请求: {elapsed1:.4f}秒")

        # 测试3.2：需要工具调用的请求
        start_time = time.time()
        request2 = "打开https://www.baidu.com网站"
        result2 = tool_manager.process_request(request2)
        elapsed2 = time.time() - start_time
        print(f"需要工具调用的请求: {elapsed2:.4f}秒")

        return {
            "no_tool_call": elapsed1,
            "with_tool_call": elapsed2,
            "average": (elapsed1 + elapsed2) / 2
        }

    def test_network_performance(self):
        """
        测试网络连接性能
        """
        print("\n测试4：网络连接性能")
        print("-" * 80)

        # 测试4.1：Cloudflare WARP连接
        start_time = time.time()
        # 重置VPN连接状态
        chain_executor.vpn_connected = False
        request1 = "打开https://www.youtube.com网站"
        result1 = tool_manager.process_request(request1)
        elapsed1 = time.time() - start_time
        print(f"Cloudflare WARP连接: {elapsed1:.4f}秒")

        # 测试4.2：普通网站访问
        start_time = time.time()
        request2 = "打开https://www.baidu.com网站"
        result2 = tool_manager.process_request(request2)
        elapsed2 = time.time() - start_time
        print(f"普通网站访问: {elapsed2:.4f}秒")

        return {
            "warp_connection": elapsed1,
            "normal_connection": elapsed2,
            "average": (elapsed1 + elapsed2) / 2
        }

    def test_multi_tool_coordination(self):
        """
        测试多工具协作性能
        """
        print("\n测试5：多工具协作性能")
        print("-" * 80)

        # 测试5.1：连续工具调用
        start_time = time.time()
        # 清理之前的测试文件
        test_file = "d:\\test\\coordination_test.txt"
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # 先创建文件
        request1 = f"写入{test_file}文件"
        result1 = tool_manager.process_request(request1)
        # 再读取文件
        request2 = f"读取{test_file}文件"
        result2 = tool_manager.process_request(request2)
        elapsed1 = time.time() - start_time
        print(f"连续工具调用: {elapsed1:.4f}秒")

        return {
            "coordination": elapsed1
        }

    def run_all_tests(self):
        """
        运行所有测试
        """
        print("Ollama 性能综合测试")
        print("=" * 80)

        # 测试1：工具调用性能
        tool_call_results = self.test_tool_call_performance()
        self.results["tool_call"] = tool_call_results

        # 测试2：链式执行性能
        chain_execution_results = self.test_chain_execution_performance()
        self.results["chain_execution"] = chain_execution_results

        # 测试3：智能判断性能
        intelligent_judgment_results = self.test_intelligent_judgment()
        self.results["intelligent_judgment"] = intelligent_judgment_results

        # 测试4：网络连接性能
        network_results = self.test_network_performance()
        self.results["network"] = network_results

        # 测试5：多工具协作性能
        coordination_results = self.test_multi_tool_coordination()
        self.results["coordination"] = coordination_results

        # 计算总体性能
        total_time = 0
        total_operations = 0
        for test_name, test_results in self.results.items():
            if "average" in test_results:
                total_time += test_results["average"]
                total_operations += 1

        overall_performance = total_time / total_operations if total_operations > 0 else 0
        self.results["overall"] = {
            "average_response_time": overall_performance
        }

        # 打印结果
        print("\n" + "=" * 80)
        print("性能测试结果汇总")
        print("=" * 80)
        print(json.dumps(self.results, indent=2, ensure_ascii=False))
        print("\n" + "=" * 80)
        print(f"总体平均响应时间: {overall_performance:.4f}秒")

        return self.results

if __name__ == "__main__":
    test = PerformanceTest()
    results = test.run_all_tests()
    
    # 保存测试结果到文件
    with open("performance_test_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n测试结果已保存到 performance_test_results.json")
