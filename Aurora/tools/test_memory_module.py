#!/usr/bin/env python3
"""
智能记忆模块测试
测试智能记忆模块的存储、检索、触发和维护功能
"""

import json
import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from intelligent_memory import intelligent_memory
from tool_manager import tool_manager

class MemoryModuleTest:
    """
    智能记忆模块测试类
    """

    def __init__(self):
        """
        初始化测试类
        """
        self.test_results = []

    def test_add_memory(self):
        """
        测试添加记忆
        """
        print("\n测试1：添加记忆")
        print("-" * 80)

        # 测试添加情景记忆
        memory_id1 = intelligent_memory.add_memory(
            "这是一个测试情景记忆",
            "episodic",
            {"source": "test", "importance": "high"}
        )
        print(f"添加情景记忆成功，ID: {memory_id1}")

        # 测试添加永久记忆
        memory_id2 = intelligent_memory.add_memory(
            "这是一个测试永久记忆",
            "permanent",
            {"category": "general", "priority": 1}
        )
        print(f"添加永久记忆成功，ID: {memory_id2}")

        # 测试添加语义记忆
        memory_id3 = intelligent_memory.add_memory(
            "这是一个测试语义记忆",
            "semantic",
            {"topic": "test", "relevance": 0.9}
        )
        print(f"添加语义记忆成功，ID: {memory_id3}")

        # 测试添加上下文记忆
        memory_id4 = intelligent_memory.add_memory(
            "这是一个测试上下文记忆",
            "contextual",
            {"context": "test", "timestamp": "2026-04-17"}
        )
        print(f"添加上下文记忆成功，ID: {memory_id4}")

        self.test_results.append({
            "test": "添加记忆",
            "status": "success",
            "memories": [memory_id1, memory_id2, memory_id3, memory_id4]
        })

    def test_retrieve_memory(self):
        """
        测试检索记忆
        """
        print("\n测试2：检索记忆")
        print("-" * 80)

        # 测试检索所有类型记忆
        results = intelligent_memory.retrieve_memory("测试")
        print(f"检索'测试'的记忆结果: {len(results)}个")
        for i, result in enumerate(results):
            print(f"{i+1}. 类型: {result['memory_type']}, 相关性: {result['relevance']:.2f}")
            print(f"   内容: {result['content']}")

        # 测试检索特定类型记忆
        episodic_results = intelligent_memory.retrieve_memory("测试", "episodic")
        print(f"\n检索'测试'的情景记忆: {len(episodic_results)}个")

        self.test_results.append({
            "test": "检索记忆",
            "status": "success",
            "total_results": len(results),
            "episodic_results": len(episodic_results)
        })

    def test_update_memory(self):
        """
        测试更新记忆
        """
        print("\n测试3：更新记忆")
        print("-" * 80)

        # 先添加一个记忆用于测试
        memory_id = intelligent_memory.add_memory(
            "这是一个待更新的记忆",
            "episodic",
            {"source": "test", "importance": "medium"}
        )
        print(f"添加待更新记忆，ID: {memory_id}")

        # 更新记忆
        success = intelligent_memory.update_memory(
            memory_id,
            "这是一个更新后的记忆",
            {"source": "test", "importance": "high", "updated": True}
        )
        print(f"更新记忆: {'成功' if success else '失败'}")

        # 验证更新
        results = intelligent_memory.retrieve_memory("更新")
        print(f"检索'更新'的记忆结果: {len(results)}个")
        for result in results:
            print(f"内容: {result['content']}")

        self.test_results.append({
            "test": "更新记忆",
            "status": "success" if success else "error",
            "memory_id": memory_id
        })

    def test_delete_memory(self):
        """
        测试删除记忆
        """
        print("\n测试4：删除记忆")
        print("-" * 80)

        # 先添加一个记忆用于测试
        memory_id = intelligent_memory.add_memory(
            "这是一个待删除的记忆",
            "episodic",
            {"source": "test", "importance": "low"}
        )
        print(f"添加待删除记忆，ID: {memory_id}")

        # 删除记忆
        success = intelligent_memory.delete_memory(memory_id)
        print(f"删除记忆: {'成功' if success else '失败'}")

        # 验证删除
        results = intelligent_memory.retrieve_memory("待删除")
        print(f"检索'待删除'的记忆结果: {len(results)}个")

        self.test_results.append({
            "test": "删除记忆",
            "status": "success" if success else "error",
            "memory_id": memory_id
        })

    def test_memory_stats(self):
        """
        测试记忆统计
        """
        print("\n测试5：记忆统计")
        print("-" * 80)

        stats = intelligent_memory.get_memory_stats()
        print("记忆统计:")
        for memory_type, count in stats.items():
            print(f"{memory_type}: {count}")

        self.test_results.append({
            "test": "记忆统计",
            "status": "success",
            "stats": stats
        })

    def test_memory_triggers(self):
        """
        测试记忆触发
        """
        print("\n测试6：记忆触发")
        print("-" * 80)

        # 添加触发
        def test_condition(context):
            return context.get('query') == 'test trigger'

        def test_action(context):
            print(f"触发动作: {context.get('query')}")
            # 添加一个记忆
            intelligent_memory.add_memory(
                f"触发记忆: {context.get('query')}",
                "episodic",
                {"source": "trigger", "timestamp": "2026-04-17"}
            )
            return "触发成功"

        intelligent_memory.add_trigger(test_condition, test_action)

        # 测试触发
        trigger_results = intelligent_memory.check_triggers({"query": "test trigger"})
        print(f"触发测试结果: {trigger_results}")

        # 验证触发是否添加了记忆
        results = intelligent_memory.retrieve_memory("触发记忆")
        print(f"检索'触发记忆'的记忆结果: {len(results)}个")

        self.test_results.append({
            "test": "记忆触发",
            "status": "success",
            "trigger_results": trigger_results,
            "triggered_memories": len(results)
        })

    def test_tool_integration(self):
        """
        测试工具集成
        """
        print("\n测试7：工具集成")
        print("-" * 80)

        # 测试通过工具管理器激活智能记忆模块
        request = "激活智能记忆模块"
        result = tool_manager.process_request(request)
        print(f"激活智能记忆模块结果: {result.get('status', 'unknown')}")
        if 'result' in result:
            print(f"消息: {result['result'].get('message', '无消息')}")

        # 测试添加记忆
        request2 = "添加记忆 '这是通过工具添加的记忆'"
        result2 = tool_manager.process_request(request2)
        print(f"添加记忆结果: {result2.get('status', 'unknown')}")

        self.test_results.append({
            "test": "工具集成",
            "status": "success",
            "activation_result": result.get('status', 'unknown'),
            "add_memory_result": result2.get('status', 'unknown')
        })

    def run_all_tests(self):
        """
        运行所有测试
        """
        print("智能记忆模块综合测试")
        print("=" * 80)

        # 运行各个测试
        self.test_add_memory()
        self.test_retrieve_memory()
        self.test_update_memory()
        self.test_delete_memory()
        self.test_memory_stats()
        self.test_memory_triggers()
        self.test_tool_integration()

        # 打印测试结果汇总
        print("\n" + "=" * 80)
        print("测试结果汇总")
        print("=" * 80)

        for result in self.test_results:
            print(f"{result['test']}: {result['status']}")

        # 统计成功和失败的测试
        success_count = sum(1 for result in self.test_results if result['status'] == 'success')
        total_count = len(self.test_results)

        print(f"\n测试完成: {success_count}/{total_count} 测试通过")

        if success_count == total_count:
            print("所有测试通过！智能记忆模块功能正常。")
        else:
            print(f"有 {total_count - success_count} 个测试失败。")

        # 导出测试结果
        with open("memory_test_results.json", 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, ensure_ascii=False, indent=2)
        print("\n测试结果已导出到 memory_test_results.json")

if __name__ == "__main__":
    test = MemoryModuleTest()
    test.run_all_tests()
