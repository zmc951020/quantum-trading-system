#!/usr/bin/env python3
import requests
import json
import time

print('等待数据积累...')
time.sleep(30)

# 登录获取session
login_resp = requests.post('http://localhost:5000/api/auth/login',
                          json={'username': 'admin', 'password': 'admin123'}, timeout=5)
session_id = login_resp.json().get('session_id')
headers = {'X-Session-ID': session_id}

# 测试市场数据条数
resp = requests.get('http://localhost:5000/api/market-data', headers=headers, timeout=5)
print(f'市场数据条数: {len(resp.json())}')

# 测试技术指标
resp = requests.get('http://localhost:5000/api/technical-indicators', headers=headers, timeout=5)
print(f'技术指标API状态: {resp.status_code}')
if resp.status_code == 200:
    result = resp.json()
    if 'error' in result:
        print(f'错误: {result["error"]}')
    else:
        print(f'技术指标数量: {len(result.get("indicators", {}))}')
        print(f'指标列表: {list(result.get("indicators", {}).keys())}')
else:
    print(f'错误: {resp.text[:500]}')