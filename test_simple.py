#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试技术分析功能
"""

import requests
import json

# API端点
BASE_URL = "http://localhost:8000"

# 测试技术分析
def test_technical_analysis():
    print("测试技术分析功能...")
    
    # 测试数据
    test_data = {
        "symbol": "BTCUSDT",
        "interval": "1h"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/xbk/analyze",
            headers={"Content-Type": "application/json"},
            json=test_data
        )
        
        if response.status_code == 200:
            result = response.json()
            print("技术分析成功!")
            print("交易对:", result.get('symbol'))
            print("周期:", result.get('interval'))
            print("信号数量:", len(result.get('signals', [])))
        else:
            print("技术分析失败:", response.status_code)
            print("错误信息:", response.text)
            
    except Exception as e:
        print("测试失败:", str(e))

if __name__ == "__main__":
    print("=====================================")
    print("技术分析功能测试")
    print("=====================================")
    
    test_technical_analysis()
    
    print("\n=====================================")
    print("测试完成!")
    print("=====================================")
