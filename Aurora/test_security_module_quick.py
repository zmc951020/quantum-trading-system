#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityModule 快速测试"""
import sys
import json
sys.path.insert(0, '.')

from risk.security_module import SecurityModule, get_security_module

sm = get_security_module()

# 1. 反向代理检测 — 高风险
test_headers = {
    'X-Forwarded-For': '10.0.0.1',
    'X-Real-IP': '10.0.0.1',
    'Host': 'proxy.example.com',
}
is_safe, msg, details = sm.detect_reverse_proxy(test_headers, '10.0.0.1')
print(f'[1] 反向代理高风险检测: is_safe={is_safe}, risk={details["risk_level"]}')
assert is_safe == False, '期望高风险被拦截'
assert details['risk_level'] == 'high', '期望风险等级为 high'

# 2. 正常请求
normal_headers = {'Host': 'localhost:5000'}
is_safe2, msg2, details2 = sm.detect_reverse_proxy(normal_headers, '203.0.113.1')
print(f'[2] 正常请求检测: is_safe={is_safe2}, risk={details2["risk_level"]}')
assert is_safe2 == True, '正常请求应通过'
assert details2['risk_level'] == 'low'

# 3. XSS 检测
is_safe3, msg3 = sm.detect_suspicious_input("<script>alert('xss')</script>")
print(f'[3] XSS检测: is_safe={is_safe3}')
assert is_safe3 == False

# 4. 正常输入
is_safe4, msg4 = sm.detect_suspicious_input('正常查询请求')
print(f'[4] 正常输入: is_safe={is_safe4}')
assert is_safe4 == True

# 5. SQL 注入
is_safe5, msg5 = sm.detect_suspicious_input("1' OR '1'='1")
print(f'[5] SQL注入检测: is_safe={is_safe5}')
assert is_safe5 == False

# 6. 订单验证
order = {'symbol': '600519', 'quantity': 1000, 'price': 1850.5, 'direction': 'buy'}
is_valid, vmsg = sm.validate_trade_order(order)
print(f'[6] 订单验证: valid={is_valid}')
assert is_valid == True

# 7. 频率限制
for i in range(5):
    allowed, lmsg = sm.check_rate_limit('test-ip-123')
    assert allowed, f'第{i}次请求应被允许'
print(f'[7] 频率限制: 5次请求通过')

# 8. 白名单
sm.add_whitelist_ip('192.168.1.100')
assert sm.is_whitelisted('192.168.1.100')
sm.remove_whitelist_ip('192.168.1.100')
assert not sm.is_whitelisted('192.168.1.100')
print(f'[8] 白名单管理: OK')

# 9. 安全摘要
summary = sm.get_security_summary()
print(f'[9] 安全摘要: total_checks={summary["total_checks"]}, blocked={summary["blocked_attempts"]}')

print()
print('=== [PASS] SecurityModule 全部 9 项测试通过 ===')
print(json.dumps(summary, ensure_ascii=False, indent=2))