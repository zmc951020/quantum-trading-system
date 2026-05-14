#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试多数据源连接
验证Yahoo Finance、Alpha Vantage和Tushare数据源是否正常工作
"""

import sys
import os

# 添加Aurora根目录到路径
aurora_root = os.path.dirname(os.path.abspath(__file__))
if aurora_root not in sys.path:
    sys.path.insert(0, aurora_root)

print("=" * 80)
print("Aurora Multi-Data Source Connection Test")
print("=" * 80)

# 测试1：导入多数据源管理器
print("\n[Test 1] Import Multi-Data Source Manager...")
try:
    from data import get_multi_data_source_manager
    print("[OK] Import success")
except Exception as e:
    print(f"[FAIL] Import failed: {e}")
    sys.exit(1)

# 测试2：初始化多数据源管理器
print("\n[Test 2] Initialize Multi-Data Source Manager...")
try:
    manager = get_multi_data_source_manager()
    status = manager.get_status()
    print("[OK] Initialize success")
    print(f"   Available sources: {list(status['sources'].keys())}")
except Exception as e:
    print(f"[FAIL] Initialize failed: {e}")
    sys.exit(1)

# 测试3：测试Yahoo Finance（无需API Key）
print("\n[Test 3] Test Yahoo Finance Data Source...")
try:
    yahoo = manager.sources.get('yahoo')
    if yahoo:
        print("   Fetching AAPL historical data...")
        df = yahoo.fetch_historical('AAPL', days=5)
        if df is not None and not df.empty:
            print(f"[OK] Yahoo Finance is working")
            print(f"   Got {len(df)} records")
            print(f"   Latest price: {df['close'].iloc[-1]:.2f}")
        else:
            print("[WARN] Yahoo Finance returned empty data")
    else:
        print("[WARN] Yahoo Finance not configured")
except Exception as e:
    print(f"[FAIL] Yahoo Finance test failed: {e}")

# 测试4：测试Alpha Vantage（需要API Key）
print("\n[Test 4] Test Alpha Vantage Data Source...")
try:
    alpha = manager.sources.get('alpha')
    if alpha:
        if alpha.api_key and alpha.api_key != 'your_alpha_vantage_api_key_here':
            print("   Fetching stock data...")
            data = alpha.fetch_realtime('IBM')
            if data:
                print(f"[OK] Alpha Vantage is working")
                print(f"   IBM price: {data['price']:.2f}")
            else:
                print("[WARN] Alpha Vantage returned empty data")
        else:
            print("[WARN] Alpha Vantage API Key not configured, skip test")
    else:
        print("[WARN] Alpha Vantage not configured")
except Exception as e:
    print(f"[FAIL] Alpha Vantage test failed: {e}")

# 测试5：测试Tushare（需要Token）
print("\n[Test 5] Test Tushare Data Source...")
try:
    tushare = manager.sources.get('tushare')
    if tushare:
        if tushare.token and tushare.token != 'your_tushare_token_here':
            print("   Fetching A-share data...")
            df = tushare.fetch_historical('000001.SZ', days=5)
            if df is not None and not df.empty:
                print(f"[OK] Tushare is working")
                print(f"   Got {len(df)} records")
                print(f"   Latest price: {df['close'].iloc[-1]:.2f}")
            else:
                print("[WARN] Tushare returned empty data")
        else:
            print("[WARN] Tushare Token not configured, skip test")
    else:
        print("[WARN] Tushare not configured")
except Exception as e:
    print(f"[FAIL] Tushare test failed: {e}")

# 测试6：测试DataProvider集成
print("\n[Test 6] Test DataProvider Data Access Layer...")
try:
    from data import get_data_provider
    dp = get_data_provider()
    print("[OK] DataProvider initialize success")
    print(f"   Multi-source available: {dp.multi_source_manager is not None}")
except Exception as e:
    print(f"[FAIL] DataProvider test failed: {e}")

# 测试7：测试从多数据源获取数据
print("\n[Test 7] Test Unified Data Fetching Interface...")
try:
    from data import get_data_provider
    dp = get_data_provider()
    if dp.multi_source_manager:
        print("   Fetching AAPL data from Yahoo Finance...")
        data = dp.fetch_from_source('AAPL', 'realtime')
        if data:
            print(f"[OK] Unified data fetching interface is working")
            print(f"   AAPL price: {data['price']:.2f}")
        else:
            print("[WARN] Unified data fetching interface returned empty data")
    else:
        print("[WARN] Multi-source manager not connected")
except Exception as e:
    print(f"[FAIL] Unified data fetching interface test failed: {e}")

print("\n" + "=" * 80)
print("Test Complete!")
print("=" * 80)
print("\nNext Steps:")
print("1. For Alpha Vantage data, register free API Key at https://www.alphavantage.co")
print("2. For Tushare data, register at https://tushare.pro to get Token")
print("3. Fill API Key/Token into d:\\Gupiao\\.Env\\MM.env")
print("4. Use dp.start_live_updates(['AAPL'], 60) to start real-time data updates")
print("=" * 80)
