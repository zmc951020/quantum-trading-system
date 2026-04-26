#!/usr/bin/env python3
"""
简单的服务测试脚本
"""

import http.client
import json

# 测试服务连接
try:
    conn = http.client.HTTPConnection("localhost", 8009, timeout=10)
    conn.request("GET", "/health")
    response = conn.getresponse()
    data = response.read().decode('utf-8')
    print(f"健康检查响应: {data}")
    print(f"状态码: {response.status}")
    
    # 测试聊天接口
    conn.request(
        "POST", "/test/chat/noauth",
        json.dumps({"user_id": "test", "prompt": "你好"}),
        {"Content-Type": "application/json"}
    )
    response = conn.getresponse()
    data = response.read().decode('utf-8')
    print(f"\n聊天接口响应: {data}")
    print(f"状态码: {response.status}")
    
    conn.close()
    print("\n✅ 服务测试成功！")
except Exception as e:
    print(f"❌ 服务测试失败: {e}")
