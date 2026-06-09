#!/usr/bin/env python3
"""完整测试所有新增API"""
import json
import urllib.request
import socket

socket.setdefaulttimeout(30)
BASE = "http://127.0.0.1:5002"

def test_api(name, path, method="GET", data=None):
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            BASE + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method=method
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        print(f"  ✅ {name:30s} -> HTTP {resp.status}")
        return True
    except Exception as e:
        print(f"  ❌ {name:30s} -> {e}")
        return False

print("=" * 60)
print("  完整API测试 (5002端口)")
print("=" * 60)

all_pass = True

print("\n【技术分析模块】")
all_pass &= test_api("技术分析单只股票", "/api/technical/analyze", "POST", {"symbol": "000001.SZ", "days": 100})
all_pass &= test_api("批量技术分析", "/api/technical/batch", "POST", {"symbols": ["000001.SZ", "600519.SH"]})
all_pass &= test_api("技术原始数据", "/api/technical/data/600519.SH")

print("\n【港大Vibe智能体模块】")
all_pass &= test_api("Vibe智能分析", "/api/vibe/analyze", "POST", {"symbol": "600519.SH", "analysis_type": "technical"})
all_pass &= test_api("Vibe增强分析", "/api/vibe/analyze_enhanced", "POST", {"symbol": "600519.SH"})

print("\n【Cline智能体模块】")
all_pass &= test_api("Cline智能对话", "/api/cline/chat", "POST", {"message": "你好", "model": "qwen"})

print("\n【模型切换模块】")
all_pass &= test_api("获取可用模型", "/api/llm/models")
all_pass &= test_api("切换模型", "/api/llm/switch", "POST", {"model": "qwen", "api_key": "test"})

print("\n【股票池模块】")
all_pass &= test_api("股票池筛选", "/api/integration/stock_pool", "POST", {"symbols": ["000001.SZ", "600519.SH"], "min_score": 50})

print("\n【页面路由测试】")
pages = ["/", "/qbot", "/technical_analysis", "/stock_pool", "/cline-agent", "/model-switch", "/vibe_analysis"]
for page in pages:
    try:
        resp = urllib.request.urlopen(BASE + page, timeout=15)
        print(f"  ✅ {page:30s} -> HTTP {resp.status}")
    except Exception as e:
        print(f"  ❌ {page:30s} -> {e}")
        all_pass = False

print("\n" + "=" * 60)
if all_pass:
    print("  ✅ 所有测试通过！")
else:
    print("  ⚠️  部分测试失败")
print("=" * 60)
