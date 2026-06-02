#!/usr/bin/env python3
"""Windows UTF-8编码补丁验证测试 - emoji输出专项"""
import sys
sys.path.insert(0, r'd:\Gupiao\升级vscode\QS_Robot')

# 关键: 导入核心模块后应该自动应用编码补丁
from qs_robot_core import AuroraSystemIntegration

# 测试各种emoji和中文字符输出
test_cases = [
    ("✅ 对号", "success icon"),
    ("❌ 叉号", "error icon"),
    ("⚠️ 警告", "warning icon"),
    ("🚀 火箭", "rocket icon"),
    ("⚡ 闪电", "bolt icon"),
    ("🐑 牧羊人", "sheep icon"),
    ("📊 图表", "chart icon"),
    ("🔍 搜索", "search icon"),
    ("🎯 目标", "target icon"),
    ("💡 想法", "light icon"),
    ("中文字符测试", "中文"),
    ("混合: ✅ 策略优化成功 🚀", "mix"),
]

print("=" * 60)
print("Emoji输出测试 (Windows GBK环境验证)")
print("=" * 60)
print()

success_count = 0
for emoji_text, desc in test_cases:
    try:
        print(f"  [{desc}] {emoji_text}")
        success_count += 1
    except UnicodeEncodeError as e:
        print(f"  [{desc}] FAIL: {e}")

print()
print("=" * 60)
print(f"结果: {success_count}/{len(test_cases)} 项成功输出")
if success_count == len(test_cases):
    print("✅ 所有emoji和中文字符正常输出!")
else:
    print("❌ 存在编码问题")
print("=" * 60)

# 再测试从韬定律集群模块直接输出
print()
print("韬定律集群模块中的emoji输出:")
from core.enhanced_strategy_manager import get_strategy_manager
mgr = get_strategy_manager()
info = mgr.get_tau_cluster_info()
print(f"  测试1: 集群名称 -> {info.get('name')}")
print(f"  测试2: 集群状态 -> {info.get('status')}")
print(f"  测试3: 特性列表 -> {info.get('features')}")
print()
print("✅ 韬定律集群模块UTF-8验证通过")
