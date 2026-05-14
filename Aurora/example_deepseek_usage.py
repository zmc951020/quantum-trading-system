#!/usr/bin/env python3
"""
DeepSeek V4 API 使用示例
展示如何在项目中使用DeepSeek V4
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入DeepSeek客户端
from deepseek_client import DeepSeekClient, create_deepseek_client_from_env


def example_1_simple_query():
    """示例1: 简单查询"""
    print("=" * 60)
    print("示例1: 简单查询")
    print("=" * 60)
    
    client = create_deepseek_client_from_env()
    if not client:
        print("请先设置DEEPSEEK_API_KEY环境变量")
        return
    
    # 使用deepseek-v4-flash进行简单查询
    response = client.simple_query(
        "请用Python写一个计算斐波那契数列的函数",
        model="deepseek-v4-flash",
        temperature=0.7
    )
    
    print(f"\n响应:\n{response}")
    print()


def example_2_thinking_mode():
    """示例2: Thinking模式（带推理过程）"""
    print("=" * 60)
    print("示例2: Thinking模式（带推理过程）")
    print("=" * 60)
    
    client = create_deepseek_client_from_env()
    if not client:
        return
    
    # 使用deepseek-v4-pro的Thinking模式
    result = client.query_with_thinking(
        "请分析: 为什么比特币在2024年价格上涨?",
        reasoning_effort="medium",  # low, medium, high
        model="deepseek-v4-pro"
    )
    
    if result.get("thinking"):
        print(f"\n推理过程:\n{result['thinking']}\n")
    print(f"最终答案:\n{result['answer']}")
    print()


def example_3_chat_history():
    """示例3: 多轮对话"""
    print("=" * 60)
    print("示例3: 多轮对话")
    print("=" * 60)
    
    client = create_deepseek_client_from_env()
    if not client:
        return
    
    # 构建对话历史
    messages = [
        {"role": "system", "content": "你是一个专业的量化交易助手"},
        {"role": "user", "content": "什么是移动平均线？"},
        {"role": "assistant", "content": "移动平均线（MA）是一种平滑价格数据的技术分析指标，通过计算一定时间窗口内的平均价格来消除短期波动，帮助识别趋势。"},
        {"role": "user", "content": "那么黄金交叉和死亡交叉是什么？"}
    ]
    
    result = client.chat(
        messages,
        model="deepseek-v4-flash",
        temperature=0.7
    )
    
    if result.get("success"):
        print(f"\n响应:\n{result['content']}")
        print(f"\n使用统计: {result.get('usage', {})}")
    print()


def example_4_streaming():
    """示例4: 流式输出"""
    print("=" * 60)
    print("示例4: 流式输出")
    print("=" * 60)
    
    client = create_deepseek_client_from_env()
    if not client:
        return
    
    print("\n正在生成回复...\n")
    
    for chunk in client.chat_stream(
        [{"role": "user", "content": "请写一个简短的量化交易策略介绍"}],
        model="deepseek-v4-flash"
    ):
        print(chunk, end="", flush=True)
    print("\n")


def example_5_integration_with_config():
    """示例5: 与项目配置集成"""
    print("=" * 60)
    print("示例5: 与项目配置集成")
    print("=" * 60)
    
    from config.config import config
    
    # 从项目配置创建客户端
    if config.deepseek_api_key:
        client = DeepSeekClient(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url
        )
        
        # 使用配置的模型
        response = client.simple_query(
            "请分析当前市场趋势（模拟）",
            model=config.deepseek_model
        )
        
        print(f"\n响应:\n{response[:300]}...")
    else:
        print("请在.env文件中配置DEEPSEEK_API_KEY")
    print()


def main():
    """主函数 - 运行所有示例"""
    print("DeepSeek V4 API 使用示例集")
    print("=" * 60)
    
    # 检查是否设置了API Key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("\n⚠️ 请先设置DEEPSEEK_API_KEY环境变量")
        print("1. 复制 .env.example 为 .env")
        print("2. 在 .env 文件中填入您的API Key")
        print("3. 或者设置环境变量: export DEEPSEEK_API_KEY=your_key\n")
        return
    
    # 运行示例
    try:
        example_1_simple_query()
        example_2_thinking_mode()
        example_3_chat_history()
        example_4_streaming()
        example_5_integration_with_config()
        
        print("=" * 60)
        print("所有示例运行完成！")
        print("=" * 60)
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
