#!/usr/bin/env python3
"""
智能记忆模块
实现记忆系统的存储、检索、触发和维护
参考视频中提到的记忆系统实现方法
"""

import json
import os
import time
import hashlib
from typing import Dict, Any, List, Optional

class IntelligentMemoryModule:
    """
    智能记忆模块
    实现记忆系统的存储、检索、触发和维护
    """

    def __init__(self, memory_dir: str = "memory"):
        """
        初始化智能记忆模块

        Args:
            memory_dir: 记忆存储目录
        """
        self.memory_dir = memory_dir
        self.memory_files = {
            "permanent": os.path.join(memory_dir, "permanent_memory.json"),
            "contextual": os.path.join(memory_dir, "contextual_memory.json"),
            "episodic": os.path.join(memory_dir, "episodic_memory.json"),
            "semantic": os.path.join(memory_dir, "semantic_memory.json")
        }
        self.memory_data = {
            "permanent": {},
            "contextual": {},
            "episodic": [],
            "semantic": {}
        }
        self.triggers = []
        self.activation_threshold = 0.7
        self._initialize_memory()

    def _initialize_memory(self):
        """
        初始化记忆系统
        """
        # 创建记忆目录
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)

        # 加载现有记忆
        for memory_type, file_path in self.memory_files.items():
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.memory_data[memory_type] = json.load(f)
                except Exception as e:
                    print(f"加载{memory_type}记忆失败: {e}")
                    self.memory_data[memory_type] = {} if memory_type != "episodic" else []
            else:
                # 初始化空记忆
                self.memory_data[memory_type] = {} if memory_type != "episodic" else []

        # 加载永久记忆（如果存在全局文件）
        global_permanent_memory = "ml_permanent_memory.json"
        if os.path.exists(global_permanent_memory):
            try:
                with open(global_permanent_memory, 'r', encoding='utf-8') as f:
                    global_data = json.load(f)
                    # 合并到永久记忆
                    self.memory_data["permanent"].update(global_data)
            except Exception as e:
                print(f"加载全局永久记忆失败: {e}")

        # 保存初始化的记忆
        self._save_memory()

    def _save_memory(self):
        """
        保存记忆数据
        """
        for memory_type, data in self.memory_data.items():
            file_path = self.memory_files[memory_type]
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存{memory_type}记忆失败: {e}")

    def _generate_memory_id(self, content: str) -> str:
        """
        生成记忆ID

        Args:
            content: 记忆内容

        Returns:
            记忆ID
        """
        return hashlib.md5(content.encode()).hexdigest()

    def add_memory(self, content: str, memory_type: str = "episodic", metadata: Optional[Dict[str, Any]] = None):
        """
        添加记忆

        Args:
            content: 记忆内容
            memory_type: 记忆类型 (permanent, contextual, episodic, semantic)
            metadata: 记忆元数据

        Returns:
            记忆ID
        """
        if memory_type not in self.memory_data:
            raise ValueError(f"无效的记忆类型: {memory_type}")

        memory_id = self._generate_memory_id(content)
        timestamp = time.time()

        if memory_type == "episodic":
            # 情景记忆以列表形式存储
            memory_item = {
                "id": memory_id,
                "content": content,
                "timestamp": timestamp,
                "metadata": metadata or {}
            }
            self.memory_data[memory_type].append(memory_item)
            # 限制情景记忆数量
            if len(self.memory_data[memory_type]) > 1000:
                self.memory_data[memory_type] = self.memory_data[memory_type][-1000:]
        else:
            # 其他记忆以字典形式存储
            self.memory_data[memory_type][memory_id] = {
                "content": content,
                "timestamp": timestamp,
                "metadata": metadata or {}
            }

        self._save_memory()
        return memory_id

    def retrieve_memory(self, query: str, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        检索记忆

        Args:
            query: 查询内容
            memory_type: 记忆类型，None表示搜索所有类型

        Returns:
            匹配的记忆列表
        """
        results = []
        query_lower = query.lower()

        if memory_type is None:
            # 搜索所有记忆类型
            for m_type, data in self.memory_data.items():
                results.extend(self._search_memory(data, query_lower, m_type))
        else:
            # 搜索指定记忆类型
            if memory_type in self.memory_data:
                results.extend(self._search_memory(self.memory_data[memory_type], query_lower, memory_type))

        # 按相关性排序
        results.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return results[:10]  # 返回前10个结果

    def _search_memory(self, data: Any, query: str, memory_type: str) -> List[Dict[str, Any]]:
        """
        搜索特定类型的记忆

        Args:
            data: 记忆数据
            query: 查询内容
            memory_type: 记忆类型

        Returns:
            匹配的记忆列表
        """
        results = []

        if memory_type == "episodic":
            # 搜索情景记忆
            for item in data:
                content_lower = item.get('content', '').lower()
                relevance = self._calculate_relevance(content_lower, query)
                if relevance > self.activation_threshold:
                    results.append({
                        "id": item.get('id'),
                        "content": item.get('content'),
                        "timestamp": item.get('timestamp'),
                        "metadata": item.get('metadata'),
                        "memory_type": memory_type,
                        "relevance": relevance
                    })
        else:
            # 搜索其他类型记忆
            for memory_id, item in data.items():
                content_lower = item.get('content', '').lower()
                relevance = self._calculate_relevance(content_lower, query)
                if relevance > self.activation_threshold:
                    results.append({
                        "id": memory_id,
                        "content": item.get('content'),
                        "timestamp": item.get('timestamp'),
                        "metadata": item.get('metadata'),
                        "memory_type": memory_type,
                        "relevance": relevance
                    })

        return results

    def _calculate_relevance(self, content: str, query: str) -> float:
        """
        计算内容与查询的相关性

        Args:
            content: 记忆内容
            query: 查询内容

        Returns:
            相关性得分 (0-1)
        """
        if not content or not query:
            return 0.0

        # 简单的包含关系匹配
        if query in content:
            return 1.0
        
        # 词频匹配作为备选
        query_words = query.split()
        content_words = content.split()
        matched_words = set(query_words) & set(content_words)

        if not query_words:
            return 0.0

        return len(matched_words) / len(query_words)

    def add_trigger(self, condition: callable, action: callable, priority: int = 1):
        """
        添加记忆触发

        Args:
            condition: 触发条件函数
            action: 触发动作函数
            priority: 触发优先级
        """
        self.triggers.append({
            "condition": condition,
            "action": action,
            "priority": priority
        })
        # 按优先级排序
        self.triggers.sort(key=lambda x: x['priority'])

    def check_triggers(self, context: Dict[str, Any]) -> List[Any]:
        """
        检查并执行触发

        Args:
            context: 上下文信息

        Returns:
            触发结果列表
        """
        results = []

        for trigger in self.triggers:
            if trigger['condition'](context):
                result = trigger['action'](context)
                results.append(result)

        return results

    def update_memory(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        更新记忆

        Args:
            memory_id: 记忆ID
            content: 新的记忆内容
            metadata: 新的记忆元数据
        """
        for memory_type, data in self.memory_data.items():
            if memory_type == "episodic":
                # 更新情景记忆
                for item in data:
                    if item.get('id') == memory_id:
                        item['content'] = content
                        item['timestamp'] = time.time()
                        if metadata:
                            item['metadata'] = metadata
                        self._save_memory()
                        return True
            else:
                # 更新其他类型记忆
                if memory_id in data:
                    data[memory_id]['content'] = content
                    data[memory_id]['timestamp'] = time.time()
                    if metadata:
                        data[memory_id]['metadata'] = metadata
                    self._save_memory()
                    return True

        return False

    def delete_memory(self, memory_id: str):
        """
        删除记忆

        Args:
            memory_id: 记忆ID

        Returns:
            是否删除成功
        """
        for memory_type, data in self.memory_data.items():
            if memory_type == "episodic":
                # 删除情景记忆
                for i, item in enumerate(data):
                    if item.get('id') == memory_id:
                        del data[i]
                        self._save_memory()
                        return True
            else:
                # 删除其他类型记忆
                if memory_id in data:
                    del data[memory_id]
                    self._save_memory()
                    return True

        return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息

        Returns:
            记忆统计信息
        """
        stats = {}
        for memory_type, data in self.memory_data.items():
            if memory_type == "episodic":
                stats[memory_type] = len(data)
            else:
                stats[memory_type] = len(data)
        return stats

    def clear_memory(self, memory_type: Optional[str] = None):
        """
        清除记忆

        Args:
            memory_type: 记忆类型，None表示清除所有类型
        """
        if memory_type is None:
            # 清除所有记忆
            for m_type in self.memory_data:
                self.memory_data[m_type] = {} if m_type != "episodic" else []
        else:
            # 清除指定类型记忆
            if memory_type in self.memory_data:
                self.memory_data[memory_type] = {} if memory_type != "episodic" else []

        self._save_memory()

    def export_memory(self, file_path: str) -> bool:
        """
        导出记忆

        Args:
            file_path: 导出文件路径

        Returns:
            是否导出成功
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出记忆失败: {e}")
            return False

    def import_memory(self, file_path: str) -> bool:
        """
        导入记忆

        Args:
            file_path: 导入文件路径

        Returns:
            是否导入成功
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_data = json.load(f)

            # 合并导入的记忆
            for memory_type, data in imported_data.items():
                if memory_type in self.memory_data:
                    if memory_type == "episodic":
                        # 合并情景记忆
                        self.memory_data[memory_type].extend(data)
                        # 限制数量
                        if len(self.memory_data[memory_type]) > 1000:
                            self.memory_data[memory_type] = self.memory_data[memory_type][-1000:]
                    else:
                        # 合并其他类型记忆
                        self.memory_data[memory_type].update(data)

            self._save_memory()
            return True
        except Exception as e:
            print(f"导入记忆失败: {e}")
            return False

# 创建智能记忆模块实例
intelligent_memory = IntelligentMemoryModule()

if __name__ == "__main__":
    # 测试智能记忆模块
    print("智能记忆模块测试")
    print("=" * 80)

    # 添加记忆
    memory_id1 = intelligent_memory.add_memory(
        "这是一个测试记忆",
        "episodic",
        {"source": "test", "importance": "high"}
    )
    print(f"添加记忆1，ID: {memory_id1}")

    memory_id2 = intelligent_memory.add_memory(
        "这是一个永久记忆",
        "permanent",
        {"category": "general", "priority": 1}
    )
    print(f"添加记忆2，ID: {memory_id2}")

    # 检索记忆
    results = intelligent_memory.retrieve_memory("测试")
    print(f"\n检索'测试'的记忆结果:")
    for i, result in enumerate(results):
        print(f"{i+1}. 类型: {result['memory_type']}, 相关性: {result['relevance']:.2f}")
        print(f"   内容: {result['content']}")

    # 更新记忆
    success = intelligent_memory.update_memory(
        memory_id1,
        "这是一个更新后的测试记忆",
        {"source": "test", "importance": "medium", "updated": True}
    )
    print(f"\n更新记忆1: {'成功' if success else '失败'}")

    # 获取记忆统计
    stats = intelligent_memory.get_memory_stats()
    print(f"\n记忆统计:")
    for memory_type, count in stats.items():
        print(f"{memory_type}: {count}")

    # 测试触发
    def test_condition(context):
        return context.get('query') == 'test'

    def test_action(context):
        print(f"触发动作: {context.get('query')}")
        return "触发成功"

    intelligent_memory.add_trigger(test_condition, test_action)
    trigger_results = intelligent_memory.check_triggers({"query": "test"})
    print(f"\n触发测试结果: {trigger_results}")

    print("\n" + "=" * 80)
    print("智能记忆模块测试完成！")
