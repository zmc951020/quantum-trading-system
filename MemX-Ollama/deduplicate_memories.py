#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
记忆去重工具
自动检测和删除重复的记忆
"""

import argparse
import hashlib
from pathlib import Path
from memx.local_vector_mem import LocalVectorMemory


def calculate_content_hash(content: str) -> str:
    """计算内容的哈希值"""
    return hashlib.md5(content.encode()).hexdigest()


def deduplicate_memories(tenant_id: str, dry_run: bool = True, keep_highest_priority: bool = True):
    """
    去除重复记忆
    
    Args:
        tenant_id: 租户ID
        dry_run: 只预览不删除
        keep_highest_priority: 保留优先级最高的版本
    """
    print("=" * 80)
    print("记忆去重工具")
    print("=" * 80)
    print(f"[INFO] 租户: {tenant_id}")
    print(f"[INFO] 预览模式: {dry_run}")
    print(f"[INFO] 保留最高优先级: {keep_highest_priority}")
    print("=" * 80)
    
    local_mem = LocalVectorMemory()
    all_memories = local_mem.get_all_memories(tenant_id)
    
    print(f"\n[INFO] 总记忆数: {len(all_memories)}")
    
    content_hash_map = {}
    duplicates = []
    
    for memory in all_memories:
        content = memory.get("content", "")
        content_hash = calculate_content_hash(content)
        
        if content_hash in content_hash_map:
            duplicates.append((content_hash_map[content_hash], memory))
        else:
            content_hash_map[content_hash] = memory
    
    if not duplicates:
        print("\n[INFO] 没有发现重复记忆")
        return
    
    print(f"\n[INFO] 发现 {len(duplicates)} 组重复记忆")
    print("\n" + "=" * 80)
    
    to_delete = []
    
    for i, (mem1, mem2) in enumerate(duplicates, 1):
        print(f"\n--- 重复组 {i} ---")
        print(f"记忆1: ID={mem1['id'][:16]}, 优先级={mem1['priority']:.2f}")
        print(f"记忆2: ID={mem2['id'][:16]}, 优先级={mem2['priority']:.2f}")
        
        if keep_highest_priority:
            if mem1['priority'] >= mem2['priority']:
                to_delete.append(mem2['id'])
                print(f"  → 删除记忆2 (优先级较低)")
            else:
                to_delete.append(mem1['id'])
                print(f"  → 删除记忆1 (优先级较低)")
        else:
            to_delete.append(mem2['id'])
            print(f"  → 删除记忆2 (保留第一个)")
    
    print("\n" + "=" * 80)
    print(f"\n[INFO] 准备删除 {len(to_delete)} 条重复记忆")
    
    if dry_run:
        print("\n[INFO] 预览模式，不执行实际删除")
        print("[INFO] 如需实际删除，请使用 --no-dry-run 参数")
        return
    
    confirm = input("\n确认删除吗？(输入 'yes' 确认): ")
    if confirm.lower() != 'yes':
        print("[INFO] 操作已取消")
        return
    
    deleted_count = 0
    for memory_id in to_delete:
        if local_mem.delete(tenant_id, memory_id):
            deleted_count += 1
            print(f"[SUCCESS] 已删除: {memory_id[:16]}")
        else:
            print(f"[ERROR] 删除失败: {memory_id[:16]}")
    
    print("\n" + "=" * 80)
    print(f"[INFO] 去重完成！")
    print(f"[INFO] 删除了 {deleted_count} 条重复记忆")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="记忆去重工具")
    parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    parser.add_argument("--no-dry-run", action="store_true", help="执行实际删除（默认只预览）")
    parser.add_argument("--keep-first", action="store_true", help="保留第一个版本（默认保留最高优先级）")
    
    args = parser.parse_args()
    
    deduplicate_memories(
        tenant_id=args.tenant,
        dry_run=not args.no_dry_run,
        keep_highest_priority=not args.keep_first
    )


if __name__ == "__main__":
    main()
