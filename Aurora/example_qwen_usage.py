#!/usr/bin/env python3
"""
Qwen3.6-Plus API 使用示例
展示如何在项目中使用Qwen3.6-Plus
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入Qwen客户端
from qwen_client import QwenClient, create_qwen_client_from_env


def example_1_simple_query():
    """示例1: 简单查询"""
    print("=" * 60)
    print("示例1: 简单查询")
    print("=" * 60)
    
    client = create_qwen_client_from_env()
    if not client:
        print("请先设置QWEN_API_KEY环境变量")
        return
    
    # 使用Qwen3.6-plus进行查询
    response = client.simple_query(
        "请用Python写一个计算斐波那契数列的函数",
        temperature=0.7
    )
    
    print(f"\n响应:\n{response}")
    print()


def example_2_thinking_mode():
    """示例2: 思考模式"""
    print("=" * 60)
    print("示例2: 思考模式")
    print("=" * 60)
    
    client = create_qwen_client_from_env()
    if not client:
        return
    
    # 使用思考模式
    result = client.query_with_thinking(
        "请分析: 量化交易策略的风险有哪些?",
    )
    
    if result.get("thinking"):
        print(f"\n思考过程:\n{result['thinking'][:300]}...\n")
    print(f"最终答案:\n{result['answer']}")
    print()


def example_3_chat_history():
    """示例3: 多轮对话"""
    print("=" * 60)
    print("示例3: 多轮对话")
    print("=" * 60)
    
    client = create_qwen_client_from_env()
    if not client:
        return
    
    # 构建对话历史
    messages = [
        {"role": "system", "content": "你是一个专业的量化交易助手"},
        {"role": "user", "content": "什么是网格交易策略？"},
        {"role": "assistant", "content": "网格交易是一种基于区间震荡的量化策略，通过在价格区间内设置多个买卖点来盈利。"},
        {"role": "user", "content": "如何设置网格参数?"}
    ]
    
    result = client.chat(
        messages,
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
    
    client = create_qwen_client_from_env()
    if not client:
        return
    
    print("\n正在生成回复...\n")
    
    for chunk in client.chat_stream(
        [{"role": "user", "content": "请介绍Qwen3.6-Plus的主要特点"}],
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
    if config.qwen_api_key:
        client = QwenClient(
            api_key=config.qwen_api_key,
            platform=config.qwen_platform,
            base_url=config.qwen_base_url
        )
        
        # 使用配置的模型
        response = client.simple_query(
            "请分析当前市场趋势（模拟）",
            model=config.qwen_model
        )
        
        print(f"\n响应:\n{response[:300]}...")
    else:
        print("请在.env文件中配置QWEN_API_KEY")
    print()


def example_6_switch_platform():
    """示例6: 切换API平台"""
    print("=" * 60)
    print("示例6: 切换API平台")
    print("=" * 60)
    
    # 列出所有支持的平台
    print("\n支持的平台:")
    for platform in QwenClient.list_platforms():
        print(f"  - {platform['id']}: {platform['name']}")
    
    api_key = os.getenv("QWEN_API_KEY", "")
    if api_key:
        # 使用不同平台
        client = QwenClient(api_key, platform="dashscope")
        print(f"\n当前平台: {client.platform}")
        print(f"基础URL: {client.base_url}")
        print(f"默认模型: {client.default_model}")
    else:
        print("\n请先配置QWEN_API_KEY")
    print()


def main():
    """主函数 - 运行所有示例"""
    print("Qwen3.6-Plus API 使用示例集")
    print("=" * 60)
    
    # 检查是否设置了API Key
    if not os.getenv("QWEN_API_KEY"):
        print("\n⚠️ 请先设置QWEN_API_KEY环境变量")
        print("1. 编辑 .env 文件")
        print("2. 设置 QWEN_API_KEY=your_key_here")
        print("3. 可选: 设置 QWEN_PLATFORM=dashscope/atalk/openrouter/vvmai")
        print()
        # 仍然显示平台信息
        example_6_switch_platform()
        return
    
    # 运行示例
    try:
        example_1_simple_query()
        example_2_thinking_mode()
        example_3_chat_history()
        example_4_streaming()
        example_5_integration_with_config()
        example_6_switch_platform()
        
        print("=" * 60)
        print("所有示例运行完成！")
        print("=" * 60)
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
