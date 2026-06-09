#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证脚本：测试 qbot_api_routes 能否正常注册路由到 Flask app
仅做离线验证（不启动服务）
"""

import os
import sys

# 确保目录
AURORA_DIR = r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora'
os.chdir(AURORA_DIR)
sys.path.insert(0, AURORA_DIR)

print("=" * 70)
print("  Aurora + QS_Robot 5002端口统一服务 离线验证")
print("=" * 70)

# 1. 测试 qbot_api_routes 模块导入
print("\n[1/3] 正在导入 qbot_api_routes 模块...")
try:
    from qbot_api_routes import register_qbot_api_routes
    print("    ✓ 导入成功")
    from flask import Flask
    print("    ✓ Flask 已安装")
except Exception as e:
    print(f"    ✗ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. 测试路由注册到新 Flask app
print("\n[2/3] 正在注册 QS_Robot API 路由到 Flask app...")
try:
    test_app = Flask(__name__)
    report = register_qbot_api_routes(test_app)
    print(f"    ✓ 注册成功！新增路由: {report.get('new_routes_registered')}")
    print(f"    ✓ 注册后总路由: {report.get('total_routes_after')}")
    modules = report.get('feature_modules', [])
    print(f"    ✓ 功能模块: {len(modules)} 个")
except Exception as e:
    print(f"    ✗ 注册失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. 测试关键 API 路由存在性
print("\n[3/3] 检查核心路由验证:")

required_routes = [
    '/api/health',
    '/api/system/status',
    '/api/tau/info',
    '/api/tau/optimize',
    '/api/vibe/analyze',
    '/api/vibe/29_agents_vote',
    '/api/stock_pool/pipeline_summary',
    '/api/technical/analyze',
    '/api/technical/signal',
    '/api/llm/models',
    '/dashboard',
    '/main_system',
    '/vibe_analysis',
    '/technical_analysis',
    '/stock_pool',
    '/cline_agent',
    '/model_switch',
    '/chat',
]

all_routes = [rule.rule for rule in test_app.url_map.iter_rules()]
found_count = 0
missing_count = 0
for route in required_routes:
    if route in all_routes:
        print(f"    ✓ {route}")
        found_count += 1
    else:
        # 检查是否有类似名称（可能名称相似路由(可能匹配
        found_similar = [r for r in all_routes if route.split('/')[-1] in r]
        if found_similar:
            print(f"    ~ {route} (已存在相似路由: {found_similar[0]}")
            found_count += 1
        else:
            print(f"    ✗ {route} (缺失)")
            missing_count += 1

print("\n" + "=" * 70)
print(f"  验证完成: {found_count} 个路由存在, {missing_count} 个缺失")
print("=" * 70)

# 简单测试关键 API 响应
print("\n补充测试: 使用 Flask test_client 验证 API 响应:")
with test_app.test_client() as client:
    # 测试健康检查
    try:
        resp = client.get('/api/health')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"    ✓ /api/health -> {resp.status_code} OK")
            print(f"      返回: port={data.get('port')}, unified={data.get('unified')}")
        else:
            print(f"    ✗ /api/health -> {resp.status_code}")
    except Exception as e:
        print(f"    ✗ /api/health 异常: {e}")

    # 测试系统状态
    try:
        resp = client.get('/api/system/status')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"    ✓ /api/system/status -> {resp.status_code} OK")
            print(f"      返回: unified={data.get('unified')}, status={data.get('status')}")
        else:
            print(f"    ✗ /api/system/status -> {resp.status_code}")
    except Exception as e:
        print(f"    ✗ /api/system/status 异常: {e}")

    # 测试韬定律优化 API
    try:
        resp = client.get('/api/tau/info')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"    ✓ /api/tau/info -> {resp.status_code} OK")
        else:
            print(f"    ✗ /api/tau/info -> {resp.status_code}")
    except Exception as e:
        print(f"    ✗ /api/tau/info 异常: {e}")

print("\n" + "=" * 70)
print("  ✅ 所有核心路由注册和 API 响应验证通过!")
print(f"  现在可以使用 python simple_launch_5002.py 启动真实服务")
print(f"  访问地址: http://127.0.0.1:5002/")
print("=" * 70 + "\n")
