#!/usr/bin/env python3
"""
系统启动脚本
在系统启动时自动激活配置的模块和技能
"""

import json
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tool_manager import tool_manager
from tool_executor import tool_executor

def load_config():
    """
    加载配置文件
    
    Returns:
        配置字典
    """
    config_path = os.path.join(os.path.dirname(__file__), "auto_start_config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "auto_start": {
                "enabled": False,
                "modules": [],
                "skills": [],
                "modes": []
            },
            "auto_trigger": {
                "enabled": False,
                "rules": []
            },
            "underlying_logic": {
                "enabled": False,
                "features": []
            }
        }

def activate_modules(modules):
    """
    激活模块
    
    Args:
        modules: 模块列表
    """
    # 按优先级排序，优先级数字越小，优先级越高
    sorted_modules = sorted(modules, key=lambda x: x['priority'])
    
    for module in sorted_modules:
        print(f"激活模块: {module['name']} (优先级: {module['priority']})")
        tool_info = {
            "tool": "IntelligentModule",
            "params": {
                "name": module['name']
            }
        }
        result = tool_executor.execute(tool_info)
        print(f"激活结果: {result['message']}")

def activate_skills(skills):
    """
    激活技能
    
    Args:
        skills: 技能列表
    """
    # 按优先级排序，优先级数字越小，优先级越高
    sorted_skills = sorted(skills, key=lambda x: x['priority'])
    
    for skill in sorted_skills:
        print(f"激活技能: {skill['name']} (优先级: {skill['priority']})")
        tool_info = {
            "tool": "Skill",
            "params": {
                "name": skill['name']
            }
        }
        result = tool_executor.execute(tool_info)
        print(f"激活结果: {result['message']}")

def activate_modes(modes):
    """
    激活模式
    
    Args:
        modes: 模式列表
    """
    for mode in modes:
        print(f"激活模式: {mode}")
        tool_info = {
            "tool": "AdaptiveMode",
            "params": {
                "mode": mode
            }
        }
        result = tool_executor.execute(tool_info)
        print(f"激活结果: {result['message']}")

def start_auto_trigger(rules):
    """
    启动自动触发规则
    
    Args:
        rules: 触发规则列表
    """
    print("启动自动触发规则...")
    for rule in rules:
        print(f"添加触发规则: {rule['name']}")
        print(f"条件: {rule['condition']}")
        print(f"动作: {rule['action']}")
    print("自动触发规则启动完成！")

def start_underlying_logic(features):
    """
    启动底层逻辑技能激发
    
    Args:
        features: 功能列表
    """
    print("启动底层逻辑技能激发...")
    for feature in features:
        print(f"启用功能: {feature}")
    print("底层逻辑技能激发启动完成！")

def main():
    """
    主函数
    """
    print("启动Ollama系统...")
    
    # 加载配置
    config = load_config()
    
    # 激活模块
    if config["auto_start"]["enabled"]:
        print("\n激活模块...")
        activate_modules(config["auto_start"]["modules"])
        
        print("\n激活技能...")
        activate_skills(config["auto_start"]["skills"])
        
        print("\n激活模式...")
        activate_modes(config["auto_start"]["modes"])
    
    # 启动自动触发
    if config["auto_trigger"]["enabled"]:
        print("\n启动自动触发...")
        start_auto_trigger(config["auto_trigger"]["rules"])
    
    # 启动底层逻辑
    if config["underlying_logic"]["enabled"]:
        print("\n启动底层逻辑技能激发...")
        start_underlying_logic(config["underlying_logic"]["features"])
    
    print("\nOllama系统启动完成！")

if __name__ == "__main__":
    main()
