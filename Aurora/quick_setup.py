#!/usr/bin/env python3
"""
DeepSeek V4 快速配置向导
"""

import os
from dotenv import load_dotenv, set_key
from pathlib import Path

def main():
    print("=" * 60)
    print("DeepSeek V4 快速配置")
    print("=" * 60)
    
    env_file = Path(".env")
    
    if not env_file.exists():
        print("\n未找到 .env 文件，正在创建...")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("# DeepSeek V4 API 配置\n")
            f.write("DEEPSEEK_API_KEY=\n")
            f.write("DEEPSEEK_BASE_URL=https://api.deepseek.com\n")
            f.write("DEEPSEEK_MODEL=deepseek-v4-flash\n")
            f.write("DEEPSEEK_THINKING_MODE=non-thinking\n")
    
    # 加载现有配置
    load_dotenv()
    current_key = os.getenv("DEEPSEEK_API_KEY", "")
    
    print(f"\n当前API Key: {current_key[:10]}...{current_key[-5:] if current_key else '(未设置)'}")
    
    api_key = input("\n请输入您的DeepSeek API Key (直接回车跳过): ").strip()
    
    if api_key:
        set_key(".env", "DEEPSEEK_API_KEY", api_key)
        print("\n✅ API Key已保存到 .env 文件!")
    
    print("\n" + "=" * 60)
    print("配置完成!")
    print("\n现在您可以:")
    print("1. 测试连接: python deepseek_client.py")
    print("2. 运行示例: python example_deepseek_usage.py")
    print("3. 查看文档: 打开 DEEPSEEK_V4_README.md")
    print("=" * 60)

if __name__ == "__main__":
    main()
