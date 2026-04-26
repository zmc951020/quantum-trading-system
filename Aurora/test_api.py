#!/usr/bin/env python3
"""
Aurora量化交易系统 - API功能测试
"""

import requests
import json

def test_api():
    print('=' * 60)
    print('Aurora量化交易系统 - API功能测试')
    print('=' * 60)

    # 1. 测试登录
    print('\n[测试1] 用户登录')
    try:
        login_resp = requests.post('http://localhost:5000/api/auth/login',
                                  json={'username': 'admin', 'password': 'admin123'}, timeout=5)
        print(f'状态码: {login_resp.status_code}')
        result = login_resp.json()
        print(f'结果: {json.dumps(result, ensure_ascii=False)}')
        session_id = result.get('session_id')

        if not session_id:
            print('登录失败，测试终止')
            return
    except Exception as e:
        print(f'登录请求失败: {e}')
        return

    headers = {'X-Session-ID': session_id}

    # 2. 测试用户验证
    print('\n[测试2] 用户会话验证')
    try:
        resp = requests.get('http://localhost:5000/api/auth/validate', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 3. 测试策略状态
    print('\n[测试3] 策略状态API')
    try:
        resp = requests.get('http://localhost:5000/api/strategy-status', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 4. 测试市场数据
    print('\n[测试4] 市场数据API')
    try:
        resp = requests.get('http://localhost:5000/api/market-data', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        data = resp.json()
        print(f'数据条数: {len(data)}')
        if data:
            print(f'最新数据: timestamp={data[-1].get("timestamp")}, price={data[-1].get("price")}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 5. 测试技术指标
    print('\n[测试5] 技术指标API')
    try:
        resp = requests.get('http://localhost:5000/api/technical-indicators', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        result = resp.json()
        if 'error' in result:
            print(f'错误: {result["error"]}')
        else:
            print(f'指标数量: {len(result.get("indicators", {}))}')
            print(f'最新指标: {json.dumps(result.get("indicators", {}), ensure_ascii=False)[:200]}...')
    except Exception as e:
        print(f'请求失败: {e}')

    # 6. 测试股票池
    print('\n[测试6] 股票池API')
    try:
        resp = requests.get('http://localhost:5000/api/stock-pool', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 7. 测试交易池
    print('\n[测试7] 交易池API')
    try:
        resp = requests.get('http://localhost:5000/api/trading-pool', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 8. 测试账户切换
    print('\n[测试8] 账户切换API')
    try:
        resp = requests.post('http://localhost:5000/api/switch-account',
                            json={'account': 'account_a'}, headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 9. 测试用户统计（管理员）
    print('\n[测试9] 用户统计API（管理员）')
    try:
        resp = requests.get('http://localhost:5000/api/users/stats', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 10. 测试用户列表（管理员）
    print('\n[测试10] 用户列表API（管理员）')
    try:
        resp = requests.get('http://localhost:5000/api/users', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    # 11. 测试登出
    print('\n[测试11] 用户登出')
    try:
        resp = requests.post('http://localhost:5000/api/auth/logout', headers=headers, timeout=5)
        print(f'状态码: {resp.status_code}')
        print(f'结果: {json.dumps(resp.json(), ensure_ascii=False)}')
    except Exception as e:
        print(f'请求失败: {e}')

    print('\n' + '=' * 60)
    print('测试完成！')
    print('=' * 60)

if __name__ == '__main__':
    test_api()