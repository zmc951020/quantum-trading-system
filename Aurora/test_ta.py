#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from technical_analyzer import TechnicalAnalyzer

# 创建测试数据
test_data = []
for i in range(60):
    test_data.append({
        'price': 50000 + i * 10,
        'high': 50100 + i * 10,
        'low': 49900 + i * 10,
        'open': 50000 + i * 10,
        'volume': 1000
    })

print(f'测试数据条数: {len(test_data)}')

try:
    indicators = TechnicalAnalyzer.calculate_all_indicators(test_data)
    print('计算成功！')
    print(f'指标数量: {len(indicators)}')
    for key, value in list(indicators.items())[:5]:
        print(f'  {key}: {value[:3] if value else None}...')
except Exception as e:
    print(f'计算失败: {e}')
    import traceback
    traceback.print_exc()