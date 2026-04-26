#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文件系统记忆导入器
从本地文件系统中批量导入文件到记忆系统
支持多种文件格式：txt, md, py, js, json, csv等
"""

import os
import time
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
import argparse

def read_file_content(file_path: Path) -> Optional[str]:
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except Exception as e:
            print(f"[WARNING] 无法读取文件 {file_path}: {e}")
            return None
    except Exception as e:
        print(f"[ERROR] 读取文件失败 {file_path}: {e}")
        return None

def get_file_metadata(file_path: Path) -> Dict:
    """获取文件元数据"""
    stat = file_path.stat()
    return {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "file_size": stat.st_size,
        "file_type": file_path.suffix,
        "created_time": stat.st_ctime,
        "modified_time": stat.st_mtime,
        "priority": 0.7
    }

def import_to_memory_api(content: str, metadata: Dict, user_id: str = "zmc") -> bool:
    """通过API导入记忆"""
    url = "http://localhost:8000/chat"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"请记住以下内容，文件：{metadata.get('file_name', 'unknown')}\n\n{content}"
    
    data = {
        "user_id": user_id,
        "prompt": prompt
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        print(f"[SUCCESS] 导入成功: {metadata.get('file_name')}")
        return True
    except Exception as e:
        print(f"[ERROR] 导入失败 {metadata.get('file_name')}: {e}")
        return False

def import_to_local_memory(content: str, metadata: Dict, tenant_id: str = "default") -> str:
    """直接导入到本地记忆存储"""
    from memx.local_vector_mem import LocalVectorMemory
    
    try:
        local_mem = LocalVectorMemory()
        memory_id = local_mem.add(tenant_id, content, metadata)
        print(f"[SUCCESS] 本地导入成功: {metadata.get('file_name')} -> ID: {memory_id}")
        return memory_id
    except Exception as e:
        print(f"[ERROR] 本地导入失败 {metadata.get('file_name')}: {e}")
        return ""

def scan_directory(directory: Path, extensions: Optional[List[str]] = None) -> List[Path]:
    """扫描目录中的文件"""
    if extensions is None:
        extensions = ['.txt', '.md', '.py', '.js', '.json', '.csv', '.html', '.css', '.xml']
    
    files = []
    for ext in extensions:
        files.extend(directory.rglob(f"*{ext}"))
    
    return sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)

def main():
    parser = argparse.ArgumentParser(description="文件系统记忆导入器")
    parser.add_argument("--dir", "-d", type=str, default=".", help="要扫描的目录")
    parser.add_argument("--extensions", "-e", type=str, nargs="+", 
                        default=[".txt", ".md", ".py", ".js", ".json", ".csv"],
                        help="要导入的文件扩展名")
    parser.add_argument("--user", "-u", type=str, default="zmc", help="用户ID")
    parser.add_argument("--tenant", "-t", type=str, default="default", help="租户ID")
    parser.add_argument("--mode", "-m", type=str, choices=["api", "local", "both"], default="local",
                        help="导入模式：api(通过API), local(本地存储), both(两者都)")
    parser.add_argument("--limit", "-l", type=int, default=100, help="最多导入文件数")
    parser.add_argument("--delay", type=float, default=1.0, help="每次导入的延迟(秒)")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("文件系统记忆导入器")
    print("=" * 80)
    print(f"[INFO] 扫描目录: {args.dir}")
    print(f"[INFO] 文件扩展名: {args.extensions}")
    print(f"[INFO] 用户ID: {args.user}")
    print(f"[INFO] 租户ID: {args.tenant}")
    print(f"[INFO] 导入模式: {args.mode}")
    print(f"[INFO] 最多导入: {args.limit}个文件")
    print("=" * 80)
    
    directory = Path(args.dir)
    if not directory.exists():
        print(f"[ERROR] 目录不存在: {args.dir}")
        return
    
    files = scan_directory(directory, args.extensions)
    print(f"[INFO] 找到 {len(files)} 个文件")
    
    if len(files) > args.limit:
        files = files[:args.limit]
        print(f"[INFO] 限制为 {args.limit} 个文件")
    
    success_count = 0
    fail_count = 0
    
    print("\n[INFO] 开始导入...\n")
    
    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] 处理: {file_path.name}")
        
        content = read_file_content(file_path)
        if content is None:
            fail_count += 1
            continue
        
        metadata = get_file_metadata(file_path)
        
        success = True
        
        if args.mode in ["api", "both"]:
            if not import_to_memory_api(content, metadata, args.user):
                success = False
        
        if args.mode in ["local", "both"]:
            memory_id = import_to_local_memory(content, metadata, args.tenant)
            if not memory_id:
                success = False
        
        if success:
            success_count += 1
        else:
            fail_count += 1
        
        if i < len(files):
            time.sleep(args.delay)
    
    print("\n" + "=" * 80)
    print("导入完成！")
    print("=" * 80)
    print(f"[INFO] 成功: {success_count}")
    print(f"[INFO] 失败: {fail_count}")
    print(f"[INFO] 总计: {len(files)}")
    print("=" * 80)

if __name__ == "__main__":
    main()
