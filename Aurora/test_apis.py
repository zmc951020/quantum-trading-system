#!/usr/bin/env python3
"""
测试DeepSeek和Qwen API连接
"""

import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv(override=True)

print("=" * 60)
print("API配置测试")
print("=" * 60)

# 检查环境变量
print("\n1. 检查环境变量配置:")
print(f"   DeepSeek API Key: {'已配置' if os.getenv('DEEPSEEK_API_KEY') else '未配置'}")
print(f"   Qwen API Key: {'已配置' if os.getenv('QWEN_API_KEY') else '未配置'}")

# 测试DeepSeek
print("\n2. 测试DeepSeek V4连接...")
try:
    from deepseek_client import DeepSeekClient
    
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    if deepseek_key:
        client = DeepSeekClient(api_key=deepseek_key)
        result = client.test_connection()
        if result['connected']:
            print("   [OK] DeepSeek连接成功!")
            print("   响应:", result['message'])
        else:
            print("   [FAIL] DeepSeek连接失败:", result['error'])
    else:
        print("   [-] DeepSeek未配置API Key")
except Exception as e:
    print("   [ERR] DeepSeek测试异常:", str(e))

# 测试Qwen
print("\n3. 测试Qwen3.6-Plus连接...")
try:
    from qwen_client import QwenClient
    
    qwen_key = os.getenv('QWEN_API_KEY')
    qwen_platform = os.getenv('QWEN_PLATFORM', 'dashscope')
    qwen_url = os.getenv('QWEN_BASE_URL')
    
    if qwen_key:
        client = QwenClient(api_key=qwen_key, platform=qwen_platform, base_url=qwen_url)
        result = client.test_connection()
        if result['connected']:
            print("   [OK] Qwen连接成功!")
            print("   平台:", result['platform'])
            print("   响应:", result['message'])
        else:
            print("   [FAIL] Qwen连接失败:", result['error'])
    else:
        print("   [-] Qwen未配置API Key")
except Exception as e:
    print("   [ERR] Qwen测试异常:", str(e))

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
