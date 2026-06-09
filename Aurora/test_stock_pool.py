#!/usr/bin/env python3
"""测试股票池API"""
import json
import urllib.request
import socket

socket.setdefaulttimeout(30)

print("=== 测试股票池API ===")
data = json.dumps({"symbols": ["000001.SZ", "600519.SH"], "min_score": 50}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:5002/api/integration/stock_pool",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode())
    print(f"✅ HTTP {resp.status}")
    print(f"  总数: {result['total_count']}")
    print(f"  通过: {result['passed_count']}")
    print(f"  最小分数: {result['min_score']}")
    for r in result["results"][:3]:
        print(f"    - {r['symbol']}: score={r['score']}, {r['recommendation']}")
except Exception as e:
    print(f"❌ 错误: {e}")
