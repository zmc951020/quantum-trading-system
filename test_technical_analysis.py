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
            print("✅ 技术分析成功!")
            print(f"交易对: {result.get('symbol')}")
            print(f"周期: {result.get('interval')}")
            print(f"MA5: {result.get('ma', {}).get('ma5', [])[-1] if result.get('ma', {}).get('ma5') else 'N/A'}")
            print(f"RSI: {result.get('rsi', [])[-1] if result.get('rsi') else 'N/A'}")
            print(f"信号数量: {len(result.get('signals', []))}")
            for signal in result.get('signals', []):
                print(f"  - {signal['type']}: {signal['reason']}")
        else:
            print(f"❌ 技术分析失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")

# 测试系统状态
def test_system_status():
    print("\n测试系统状态...")
    
    try:
        response = requests.get(f"{BASE_URL}/status")
        if response.status_code == 200:
            result = response.json()
            print("✅ 系统状态获取成功!")
            print(f"当前策略: {result.get('current_strategy', {}).get('name', '无')}")
            print(f"系统状态: {result.get('status')}")
            print(f"可用策略数: {len(result.get('strategies', []))}")
        else:
            print(f"❌ 系统状态获取失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")

# 测试获取信号
def test_get_signals():
    print("\n测试获取信号...")
    
    try:
        response = requests.get(f"{BASE_URL}/signals")
        if response.status_code == 200:
            result = response.json()
            print("✅ 信号获取成功!")
            print(f"信号数量: {result.get('total')}")
            for signal in result.get('data', []):
                print(f"  - {signal['type']}: {signal['symbol']} @ {signal['price']}")
        else:
            print(f"❌ 信号获取失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")

if __name__ == "__main__":
    print("=====================================")
    print("📊 技术分析功能测试")
    print("=====================================")
    
    test_system_status()
    test_technical_analysis()
    test_get_signals()
    
    print("\n=====================================")
    print("测试完成!")
    print("=====================================")
