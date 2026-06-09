#!/usr/bin/env python3
"""测试5002端口所有API功能"""
import json
import urllib.request

BASE = "http://127.0.0.1:5002"

def test_api(name, path, method="GET", data=None):
    try:
        if method == "POST":
            req = urllib.request.Request(
                BASE + path,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
        else:
            req = urllib.request.Request(BASE + path, method="GET")
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        print(f"  ✅ {name:30s} -> HTTP {resp.status}")
        return True
    except Exception as e:
        print(f"  ❌ {name:30s} -> {e}")
        return False

print("=" * 60)
print("  Aurora+QS-Robot API 功能测试 (5002端口)")
print("=" * 60)
print()

print("【技术分析模块】")
test_api("技术分析单只股票", "/api/technical/analyze", "POST", {"symbol": "000001.SS", "days": 100})
test_api("批量技术分析", "/api/technical/batch", "POST", {"symbols": ["000001.SS", "600519.SS"], "days": 100})
print()

print("【港大Vibe智能体模块】")
test_api("Vibe智能分析", "/api/vibe/analyze", "POST", {"symbol": "600519.SS", "analysis_type": "technical"})
test_api("Vibe增强分析", "/api/vibe/analyze_enhanced", "POST", {"symbol": "600519.SS"})
print()

print("【Cline智能体模块】")
test_api("Cline聊天", "/api/cline/chat", "POST", {"message": "你好，请简单介绍一下股票分析", "model": "qwen"})
print()

print("【模型切换模块】")
test_api("获取可用模型", "/api/llm/models", "GET")
test_api("切换模型", "/api/llm/switch", "POST", {"model": "qwen", "api_key": "test"})
print()

print("【股票池模块】")
test_api("股票池筛选", "/api/integration/stock_pool", "POST", {"symbols": ["000001.SS", "600519.SS"], "min_score": 50})
print()

print("=" * 60)
print("  API测试完成！")
print("=" * 60)
