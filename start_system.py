#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一启动脚本 - 使用路径管理器和配置管理器
支持跨平台运行，自动适配不同环境
"""

import os
import sys
import time
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import path_manager
from config_manager import config_manager

def check_dependencies():
    """
    检查依赖库
    """
    print("[1/5] 检查依赖库...")
    required_packages = [
        'pandas', 'numpy', 'matplotlib', 'scikit-learn',
        'Flask', 'Flask-Cors', 'requests', 'python-dotenv'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  OK {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"  NO {package}")
    
    if missing_packages:
        print(f"\n缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    return True

def check_files():
    """
    检查必要文件
    """
    print("\n[2/5] 检查必要文件...")
    
    files_to_check = [
        'paths.py',
        'config_manager.py',
        '.env',
        'Aurora/strategies/huijin_value_strategy.py'
    ]
    
    all_exist = True
    for file_path in files_to_check:
        full_path = path_manager.get_path(file_path)
        if full_path.exists():
            print(f"  OK {file_path}")
        else:
            print(f"  NO {file_path}")
            all_exist = False
    
    return all_exist

def check_config():
    """
    检查配置
    """
    print("\n[3/5] 检查配置...")
    
    config_items = [
        'initial_balance',
        'base_price',
        'default_strategy',
        'host',
        'port'
    ]
    
    for item in config_items:
        value = config_manager.get(item)
        print(f"  OK {item}: {value}")
    
    return True

def start_aurora():
    """
    启动Aurora系统
    """
    print("\n[4/5] 启动Aurora系统...")
    
    try:
        # 导入Aurora系统
        sys.path.insert(0, str(path_manager.get_path('Aurora')))
        from main import AuroraSystem
        
        # 初始化系统
        system = AuroraSystem()
        
        # 选择汇金策略
        success = system.strategy_manager.select_strategy('huijin_value')
        if success:
            print("  OK 汇金价值AI轮动策略已激活")
        else:
            print("  NO 无法激活汇金策略")
            return False
        
        # 启动Web服务
        print("\n[5/5] 启动Web服务...")
        os.chdir(str(path_manager.get_path('Aurora')))
        os.system('python visualization.py')
        
    except Exception as e:
        print(f"  ✗ 启动失败: {e}")
        return False
    
    return True

def main():
    """
    主函数
    """
    print("=" * 60)
    print("  量化交易系统启动器")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 检查依赖
    if not check_dependencies():
        return False
    
    # 检查文件
    if not check_files():
        return False
    
    # 检查配置
    if not check_config():
        return False
    
    # 启动系统
    if not start_aurora():
        return False
    
    print("\n" + "=" * 60)
    print("  启动完成！")
    print("  访问地址: http://localhost:5000")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    main()