#!/usr/bin/env python3
"""
测试所有模型：DeepSeek V4-Flash、DeepSeek V4-Pro、Qwen3.6-Plus
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)

print("=" * 70)
print("多模型配置测试")
print("=" * 70)

# 测试DeepSeek V4-Flash
print("\n1. 测试 DeepSeek V4-Flash...")
try:
    from deepseek_client import DeepSeekClient
    
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    if deepseek_key:
        client = DeepSeekClient(api_key=deepseek_key)
        result = client.chat(
            [{"role": "user", "content": "请用一句话介绍DeepSeek V4-Flash"}],
            model="deepseek-v4-flash",
            max_tokens=50
        )
        if result['success']:
            print("   [OK] DeepSeek V4-Flash 测试成功!")
            print("   响应:", result['content'])
        else:
            print("   [FAIL] DeepSeek V4-Flash 测试失败:", result['error'])
    else:
        print("   [-] DeepSeek未配置API Key")
except Exception as e:
    print("   [ERR] DeepSeek V4-Flash测试异常:", str(e))

# 测试DeepSeek V4-Pro
print("\n2. 测试 DeepSeek V4-Pro...")
try:
    from deepseek_client import DeepSeekClient
    
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    if deepseek_key:
        client = DeepSeekClient(api_key=deepseek_key)
        result = client.chat(
            [{"role": "user", "content": "请用一句话介绍DeepSeek V4-Pro"}],
            model="deepseek-v4-pro",
            max_tokens=50
        )
        if result['success']:
            print("   [OK] DeepSeek V4-Pro 测试成功!")
            print("   响应:", result['content'])
        else:
            print("   [FAIL] DeepSeek V4-Pro 测试失败:", result['error'])
    else:
        print("   [-] DeepSeek未配置API Key")
except Exception as e:
    print("   [ERR] DeepSeek V4-Pro测试异常:", str(e))

# 测试Qwen3.6-Plus
print("\n3. 测试 Qwen3.6-Plus...")
try:
    from qwen_client import QwenClient
    
    qwen_key = os.getenv('QWEN_API_KEY')
    qwen_platform = os.getenv('QWEN_PLATFORM', 'dashscope')
    qwen_url = os.getenv('QWEN_BASE_URL')
    
    if qwen_key:
        client = QwenClient(api_key=qwen_key, platform=qwen_platform, base_url=qwen_url)
        result = client.chat(
            [{"role": "user", "content": "请用一句话介绍Qwen3.6-Plus"}],
            model="qwen3.6-plus",
            max_tokens=50
        )
        if result['success']:
            print("   [OK] Qwen3.6-Plus 测试成功!")
            print("   响应:", result['content'])
        else:
            print("   [FAIL] Qwen3.6-Plus 测试失败:", result['error'])
    else:
        print("   [-] Qwen未配置API Key")
except Exception as e:
    print("   [ERR] Qwen3.6-Plus测试异常:", str(e))

# 测试DeepSeek Thinking模式
print("\n4. 测试 DeepSeek Thinking模式...")
try:
    from deepseek_client import DeepSeekClient
    
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    if deepseek_key:
        client = DeepSeekClient(api_key=deepseek_key)
        result = client.chat(
            [{"role": "user", "content": "1+1等于几？请详细解释"}],
            model="deepseek-v4-pro",
            max_tokens=100,
            thinking_mode="thinking"
        )
        if result['success']:
            print("   [OK] DeepSeek Thinking模式测试成功!")
            if result.get('reasoning_content'):
                print("   推理过程:", result['reasoning_content'][:50], "...")
            print("   最终答案:", result['content'])
        else:
            print("   [FAIL] DeepSeek Thinking模式测试失败:", result['error'])
    else:
        print("   [-] DeepSeek未配置API Key")
except Exception as e:
    print("   [ERR] DeepSeek Thinking模式测试异常:", str(e))

print("\n" + "=" * 70)
print("测试完成!")
print("=" * 70)

print("\n📋 cc-switch模型切换说明:")
print("-" * 70)
print("1. 在聊天界面点击右上角模型选择下拉菜单")
print("2. 选择您配置的供应商:")
print("   - DeepSeek V4-Flash / DeepSeek V4-Pro")
print("   - Qwen3.6-Plus")
print("3. 开始聊天即可自动切换")
print("\n✅ 切换原理:")
print("   - 每个供应商有独立的API Key和端点")
print("   - 切换时系统自动使用对应配置")
print("   - 无需重启客户端")
