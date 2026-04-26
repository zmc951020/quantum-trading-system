#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
记忆管理工具
提供记忆的添加、搜索、删除、查看等功能
"""

import argparse
import json
from pathlib import Path
from typing import Optional
from memx.local_vector_mem import LocalVectorMemory

def print_memory(memory: dict):
    """打印单个记忆"""
    print("\n" + "=" * 80)
    print(f"ID: {memory.get('id', 'N/A')}")
    print(f"优先级: {memory.get('priority', 0.5):.2f}")
    print(f"相关度: {memory.get('relevance', 0):.2f}" if 'relevance' in memory else "")
    print(f"时间戳: {memory.get('timestamp', 0)}")
    print("-" * 80)
    content = memory.get('content', '')
    if len(content) > 500:
        print(content[:500] + "...")
    else:
        print(content)
    print("=" * 80)

def add_memory_command(args):
    """添加记忆命令"""
    print("[INFO] 添加记忆")
    print(f"[INFO] 租户: {args.tenant}")
    
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[ERROR] 文件不存在: {args.file}")
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"[ERROR] 读取文件失败: {e}")
            return
        
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "priority": args.priority
        }
    else:
        content = args.content
        metadata = {"priority": args.priority}
    
    local_mem = LocalVectorMemory()
    memory_id = local_mem.add(args.tenant, content, metadata)
    
    if memory_id:
        print(f"[SUCCESS] 记忆添加成功，ID: {memory_id}")
    else:
        print(f"[ERROR] 记忆添加失败")

def search_memory_command(args):
    """搜索记忆命令"""
    print(f"[INFO] 搜索记忆: {args.query}")
    print(f"[INFO] 租户: {args.tenant}")
    print(f"[INFO] 最多返回: {args.limit}条")
    
    local_mem = LocalVectorMemory()
    results = local_mem.search(args.tenant, args.query, args.limit)
    
    if not results:
        print("[INFO] 没有找到匹配的记忆")
        return
    
    print(f"[INFO] 找到 {len(results)} 条匹配的记忆")
    for i, memory in enumerate(results, 1):
        print(f"\n--- 结果 {i} ---")
        print_memory(memory)

def list_memories_command(args):
    """列出所有记忆命令"""
    print(f"[INFO] 列出所有记忆")
    print(f"[INFO] 租户: {args.tenant}")
    
    local_mem = LocalVectorMemory()
    memories = local_mem.get_all_memories(args.tenant)
    
    if not memories:
        print("[INFO] 该租户没有记忆")
        return
    
    print(f"[INFO] 共有 {len(memories)} 条记忆")
    
    if args.verbose:
        for i, memory in enumerate(memories, 1):
            print(f"\n--- 记忆 {i} ---")
            print_memory(memory)
    else:
        print("\nID\t\t\t\t优先级\t文件名")
        print("-" * 80)
        for memory in memories:
            metadata = memory.get('metadata', {})
            file_name = metadata.get('file_name', 'N/A')
            print(f"{memory['id'][:32]}\t{memory['priority']:.2f}\t{file_name}")

def delete_memory_command(args):
    """删除记忆命令"""
    print(f"[INFO] 删除记忆: {args.id}")
    print(f"[INFO] 租户: {args.tenant}")
    
    local_mem = LocalVectorMemory()
    success = local_mem.delete(args.tenant, args.id)
    
    if success:
        print(f"[SUCCESS] 记忆删除成功")
    else:
        print(f"[ERROR] 记忆删除失败，可能ID不存在")

def clear_memories_command(args):
    """清空所有记忆命令"""
    print(f"[WARNING] 即将清空租户 {args.tenant} 的所有记忆！")
    confirm = input("确认清空吗？(输入 'yes' 确认): ")
    
    if confirm.lower() != 'yes':
        print("[INFO] 操作已取消")
        return
    
    local_mem = LocalVectorMemory()
    success = local_mem.clear_memories(args.tenant)
    
    if success:
        print(f"[SUCCESS] 记忆清空成功")
    else:
        print(f"[ERROR] 记忆清空失败")

def export_memories_command(args):
    """导出记忆命令"""
    print(f"[INFO] 导出记忆到: {args.output}")
    print(f"[INFO] 租户: {args.tenant}")
    
    local_mem = LocalVectorMemory()
    memories = local_mem.get_all_memories(args.tenant)
    
    output_path = Path(args.output)
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        print(f"[SUCCESS] 成功导出 {len(memories)} 条记忆")
    except Exception as e:
        print(f"[ERROR] 导出失败: {e}")

def main():
    parser = argparse.ArgumentParser(description="记忆管理工具")
    subparsers = parser.add_subparsers(title="命令", dest="command")
    
    # 添加记忆
    add_parser = subparsers.add_parser("add", help="添加记忆")
    add_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    add_parser.add_argument("--priority", "-p", type=float, default=0.7, help="优先级 (0-1)")
    add_parser.add_argument("--file", "-f", type=str, help="从文件添加")
    add_parser.add_argument("content", nargs="?", type=str, help="记忆内容")
    add_parser.set_defaults(func=add_memory_command)
    
    # 搜索记忆
    search_parser = subparsers.add_parser("search", help="搜索记忆")
    search_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    search_parser.add_argument("--limit", "-l", type=int, default=10, help="最多返回结果数")
    search_parser.add_argument("query", type=str, help="搜索查询")
    search_parser.set_defaults(func=search_memory_command)
    
    # 列出记忆
    list_parser = subparsers.add_parser("list", help="列出所有记忆")
    list_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    list_parser.set_defaults(func=list_memories_command)
    
    # 删除记忆
    delete_parser = subparsers.add_parser("delete", help="删除记忆")
    delete_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    delete_parser.add_argument("id", type=str, help="记忆ID")
    delete_parser.set_defaults(func=delete_memory_command)
    
    # 清空记忆
    clear_parser = subparsers.add_parser("clear", help="清空所有记忆")
    clear_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    clear_parser.set_defaults(func=clear_memories_command)
    
    # 导出记忆
    export_parser = subparsers.add_parser("export", help="导出记忆")
    export_parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    export_parser.add_argument("output", type=str, help="输出文件路径")
    export_parser.set_defaults(func=export_memories_command)
    
    args = parser.parse_args()
    
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    
    args.func(args)

if __name__ == "__main__":
    main()
