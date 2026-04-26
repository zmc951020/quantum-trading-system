#!/usr/bin/env python3
"""
西部宽客API端点探索脚本
测试不同的API端点格式
"""
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_common_endpoints():
    """
    测试常见的API端点格式
    """
    print("=" * 70)
    print("西部宽客 API 端点探索")
    print("=" * 70)

    api_url = os.getenv("XBK_API_URL", "https://sim-api.xbk.com")
    api_key = os.getenv("XBK_API_KEY", "")
    api_secret = os.getenv("XBK_API_SECRET", "")

    print(f"\nAPI URL: {api_url}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print()

    # 常见的API端点格式
    endpoints_to_test = [
        # 行情相关
        ("GET", "/v1/market/ticker?symbol=BTCUSDT", "获取ticker"),
        ("GET", "/v1/market/ticker/BTCUSDT", "获取ticker (路径参数)"),
        ("GET", "/v1/ticker?symbol=BTCUSDT", "获取ticker (简化)"),
        ("GET", "/v1/ticker/BTCUSDT", "获取ticker (简化路径)"),
        ("GET", "/v1/kline?symbol=BTCUSDT&interval=1h", "获取K线"),
        ("GET", "/v1/klines?symbol=BTCUSDT&interval=1h", "获取K线 (复数)"),
        ("GET", "/v1/market/kline?symbol=BTCUSDT&interval=1h", "获取K线 (市场)"),

        # 账户相关
        ("GET", "/v1/account/info", "账户信息"),
        ("GET", "/v1/account/balance", "账户余额"),
        ("GET", "/v1/balance", "余额"),
        ("GET", "/v1/positions", "持仓列表"),
        ("GET", "/v1/position/BTCUSDT", "BTC持仓"),

        # 交易对相关
        ("GET", "/v1/symbols", "交易对列表"),
        ("GET", "/v1/markets", "市场列表"),
        ("GET", "/v1/exchangeInfo", "交易所信息"),
    ]

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
        "X-API-SECRET": api_secret,
    }

    print("测试不同的API端点...")
    print("-" * 70)

    successful_endpoints = []
    failed_endpoints = []

    for method, endpoint, description in endpoints_to_test:
        url = f"{api_url}{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, timeout=10)

            if response.status_code == 200:
                print(f"[OK] {method} {endpoint}")
                print(f"     描述: {description}")
                print(f"     响应: {response.text[:200]}...")
                print()
                successful_endpoints.append((method, endpoint, description, response.text))
            elif response.status_code == 404:
                print(f"[--] {method} {endpoint} - Not Found")
            else:
                print(f"[XX] {method} {endpoint} - {response.status_code}")
                failed_endpoints.append((method, endpoint, response.status_code, response.text[:100]))

        except Exception as e:
            print(f"[EE] {method} {endpoint} - Error: {str(e)[:50]}")
            failed_endpoints.append((method, endpoint, "Error", str(e)))

    print("-" * 70)
    print(f"\n测试完成！")
    print(f"成功: {len(successful_endpoints)} 个端点")
    print(f"失败: {len(failed_endpoints)} 个端点")

    if successful_endpoints:
        print("\n可用的API端点：")
        for method, endpoint, description, _ in successful_endpoints:
            print(f"  - {method} {endpoint} ({description})")

    print("=" * 70)

    return successful_endpoints

if __name__ == "__main__":
    try:
        test_common_endpoints()
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
