#!/usr/bin/env python3
"""
西部宽客API连接测试脚本
"""
import os
import sys
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_xbk_api():
    """
    测试西部宽客API连接
    """
    print("=" * 70)
    print("西部宽客 API 连接测试")
    print("=" * 70)

    # 检查环境变量
    print("\n1. 检查环境变量配置...")
    api_key = os.getenv("XBK_API_KEY")
    api_secret = os.getenv("XBK_API_SECRET")
    api_url = os.getenv("XBK_API_URL", "https://api.xbk.com")

    if not api_key or not api_secret:
        print("   [错误] API密钥未配置！")
        print("   请在.env文件中配置以下变量：")
        print("   XBK_API_KEY=your_api_key")
        print("   XBK_API_SECRET=your_api_secret")
        print("   XBK_API_URL=https://api.xbk.com")
        return False

    print(f"   API URL: {api_url}")
    print(f"   API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"   API Secret: {api_secret[:4]}...{api_secret[-4:]}")
    print("   [OK] 环境变量配置正确")

    # 导入交易模块
    print("\n2. 导入交易模块...")
    try:
        from xbk_trader import XbkTrader
        from safe_config import SafeConfig
        print("   [OK] 模块导入成功")
    except Exception as e:
        print(f"   [错误] 模块导入失败: {str(e)}")
        return False

    # 创建交易客户端
    print("\n3. 创建交易客户端...")
    try:
        trader = XbkTrader()
        print("   [OK] 交易客户端创建成功")
    except Exception as e:
        print(f"   [错误] 交易客户端创建失败: {str(e)}")
        return False

    # 测试获取行情
    print("\n4. 测试获取行情数据...")
    try:
        ticker_result = trader.get_ticker("BTCUSDT")
        if ticker_result.get("code") == 0:
            print("   [OK] 获取行情成功")
            data = ticker_result.get("data", {})
            print(f"   BTC价格: {data.get('last_price', 'N/A')}")
        else:
            print(f"   [警告] 获取行情返回: {ticker_result}")
    except Exception as e:
        print(f"   [错误] 获取行情失败: {str(e)}")

    # 测试获取账户信息（需要登录）
    print("\n5. 测试账户信息获取...")
    print("   [提示] 需要登录才能获取账户信息")
    print("   请使用以下代码进行登录测试：")
    print()
    print("   from xbk_trader import XbkTrader")
    print("   trader = XbkTrader()")
    print("   result = trader.login('your_username', 'your_password')")
    print("   if result.get('code') == 0:")
    print("       print('登录成功!')")
    print("       account = trader.get_account_info()")
    print("       print(f'账户余额: {account}')")
    print()

    print("=" * 70)
    print("测试完成！")
    print("=" * 70)

    return True

if __name__ == "__main__":
    try:
        test_xbk_api()
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
