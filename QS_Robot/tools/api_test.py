"""API 端点测试"""
import requests
base = 'http://localhost:5003'
endpoints = [
    ('/dashboard', '仪表盘'),
    ('/main_system', '主系统'),
    ('/aurora_main', 'Aurora'),
    ('/technical_analysis', '技术分析'),
    ('/vibe_analysis', 'Vibe分析'),
    ('/stock_pool', '股票池'),
    ('/maintenance', '维护'),
    ('/api/health', '健康检查'),
    ('/api/vibe/status', 'Vibe状态'),
    ('/ths_academy/', '同花顺'),
]
p = 0
for url, name in endpoints:
    try:
        r = requests.get(base + url, timeout=5)
        ok = r.status_code in [200, 302, 401]
        tag = "OK" if ok else "FAIL"
        print(f"  [{tag}] {name} ({r.status_code})")
        if ok:
            p += 1
    except Exception as e:
        print(f"  [ERR] {name}: {str(e)[:40]}")
print(f"\nAPI: {p}/{len(endpoints)} 通过")