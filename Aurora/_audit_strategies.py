#!/usr/bin/env python3
"""审计策略注册表与前端下拉框的一致性"""
import re
import json

# 1. 读取策略注册表
with open('strategies/strategy_registry.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有策略名称
strategy_names = re.findall(r'"([A-Z]\w+Strategy|[A-Z]\w+Trading|[A-Z]\w+Agent)"\s*:\s*\{', content)
print("=" * 60)
print("策略注册表 (strategy_registry.py) 中的策略:")
print("=" * 60)
for s in strategy_names:
    print(f"  ✅ {s}")
print(f"\n总计: {len(strategy_names)} 个策略\n")

# 2. 读取前端HTML
with open('templates/deepseek.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 提取所有option值
options = re.findall(r'value="([A-Z]\w+)"', html)
print("=" * 60)
print("前端 deepseek.html 下拉框中的策略:")
print("=" * 60)
for o in options:
    print(f"  ✅ {o}")
print(f"\n总计: {len(options)} 个策略\n")

# 3. 对比差异
registry_set = set(strategy_names)
frontend_set = set(options)

missing_in_frontend = registry_set - frontend_set
extra_in_frontend = frontend_set - registry_set

print("=" * 60)
print("差异分析:")
print("=" * 60)
if missing_in_frontend:
    print(f"\n⚠️  注册表中有但前端缺失的策略 ({len(missing_in_frontend)}):")
    for s in sorted(missing_in_frontend):
        print(f"  ❌ {s}")
else:
    print("\n✅ 所有注册表中的策略都已在前端展示")

if extra_in_frontend:
    print(f"\n⚠️  前端有但注册表中不存在的策略 ({len(extra_in_frontend)}):")
    for s in sorted(extra_in_frontend):
        print(f"  ❌ {s}")
else:
    print("\n✅ 前端没有多余的策略")

# 4. 检查策略信息面板字段
print("\n" + "=" * 60)
print("策略信息面板字段检查:")
print("=" * 60)
info_fields = re.findall(r'info-(\w+)', html)
info_fields_unique = set(info_fields)
print(f"信息面板字段: {sorted(info_fields_unique)}")

# 5. 检查API端点
print("\n" + "=" * 60)
print("API端点检查:")
print("=" * 60)
with open('visualization.py', 'r', encoding='utf-8') as f:
    viz = f.read()

api_routes = re.findall(r"@app\.route\('/api/([^']+)'\)", viz)
for route in sorted(api_routes):
    print(f"  ✅ /api/{route}")

print("\n" + "=" * 60)
print("审计完成!")
print("=" * 60)
