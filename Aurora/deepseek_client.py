#!/usr/bin/env python3
"""
DeepSeek V4 API客户端
用于对接DeepSeek V4大语言模型API
支持deepseek-v4-pro和deepseek-v4-flash
"""

import os
import json
import time
from typing import Dict, Any, List, Optional, Union
from openai import OpenAI


class DeepSeekClient:
    """
    DeepSeek V4 API客户端
    兼容OpenAI SDK格式
    """
    
    # DeepSeek V4模型名称
    MODEL_V4_PRO = "deepseek-v4-pro"
    MODEL_V4_FLASH = "deepseek-v4-flash"
    
    # 旧模型名称（将于2026-07-24废弃）
    MODEL_CHAT = "deepseek-chat"
    MODEL_REASONER = "deepseek-reasoner"

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        """
        初始化DeepSeek客户端

        Args:
            api_key: DeepSeek API密钥
            base_url: API基础URL（OpenAI兼容格式）
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        
        # 初始化OpenAI兼容客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url
        )

    def chat(self, 
             messages: List[Dict[str, str]], 
             model: str = "deepseek-v4-flash",
             temperature: float = 1.0,
             top_p: float = 1.0,
             max_tokens: Optional[int] = None,
             thinking_mode: Optional[str] = None,
             stream: bool = False,
             system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        发送聊天请求

        Args:
            messages: 对话历史消息列表
            model: 模型名称
            temperature: 温度参数（0-2）
            top_p: top_p参数（0-1）
            max_tokens: 最大输出token数
            thinking_mode: 推理模式 ("non-thinking", "thinking", "thinking_max")
            stream: 是否流式输出
            system_prompt: 系统提示词（可选）

        Returns:
            API响应结果
        """
        # 如果提供了系统提示词，添加到消息开头
        if system_prompt and not any(msg.get("role") == "system" for msg in messages):
            messages = [{"role": "system", "content": system_prompt}] + messages

        # 构建请求参数
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        # 处理Thinking模式
        if thinking_mode:
            if thinking_mode == "thinking_max":
                params["reasoning_effort"] = "high"
            elif thinking_mode == "thinking":
                params["reasoning_effort"] = "medium"
            params["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            response = self.client.chat.completions.create(**params)
            
            if stream:
                return {"stream": response}
            
            # 解析响应
            result = {
                "success": True,
                "content": response.choices[0].message.content,
                "reasoning_content": getattr(response.choices[0].message, "reasoning_content", None),
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "prompt_cache_hit_tokens": getattr(response.usage, "prompt_cache_hit_tokens", 0)
                },
                "model": response.model
            }
            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None
            }

    def chat_stream(self, 
                    messages: List[Dict[str, str]], 
                    model: str = "deepseek-v4-flash",
                    temperature: float = 1.0,
                    top_p: float = 1.0,
                    max_tokens: Optional[int] = None,
                    thinking_mode: Optional[str] = None,
                    system_prompt: Optional[str] = None):
        """
        流式聊天请求

        Args:
            messages: 对话历史消息列表
            model: 模型名称
            temperature: 温度参数
            top_p: top_p参数
            max_tokens: 最大输出token数
            thinking_mode: 推理模式
            system_prompt: 系统提示词（可选）

        Yields:
            流式响应块
        """
        # 如果提供了系统提示词，添加到消息开头
        if system_prompt and not any(msg.get("role") == "system" for msg in messages):
            messages = [{"role": "system", "content": system_prompt}] + messages

        # 构建请求参数
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        # 处理Thinking模式
        if thinking_mode:
            if thinking_mode == "thinking_max":
                params["reasoning_effort"] = "high"
            elif thinking_mode == "thinking":
                params["reasoning_effort"] = "medium"
            params["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            stream = self.client.chat.completions.create(**params)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"[错误] {str(e)}"

    def simple_query(self, 
                    prompt: str, 
                    model: str = "deepseek-v4-flash",
                    temperature: float = 0.7,
                    system_prompt: Optional[str] = None) -> str:
        """
        简单查询接口（快速使用）

        Args:
            prompt: 用户提示词
            model: 模型名称
            temperature: 温度参数
            system_prompt: 系统提示词（可选）

        Returns:
            模型响应内容
        """
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, model=model, temperature=temperature, system_prompt=system_prompt)
        
        if result.get("success"):
            return result.get("content", "")
        else:
            return f"查询失败: {result.get('error', '未知错误')}"

    def query_with_thinking(self, 
                           prompt: str, 
                           model: str = "deepseek-v4-pro",
                           reasoning_effort: str = "medium",
                           system_prompt: Optional[str] = None) -> Dict[str, str]:
        """
        带推理过程的查询（Thinking模式）

        Args:
            prompt: 用户提示词
            model: 模型名称（推荐使用deepseek-v4-pro）
            reasoning_effort: 推理强度 ("low", "medium", "high")
            system_prompt: 系统提示词（可选）

        Returns:
            包含推理过程和最终答案的字典
        """
        messages = [{"role": "user", "content": prompt}]
        
        # 映射推理强度
        thinking_mode_map = {
            "low": "thinking",
            "medium": "thinking",
            "high": "thinking_max"
        }
        thinking_mode = thinking_mode_map.get(reasoning_effort, "thinking")

        result = self.chat(
            messages, 
            model=model, 
            thinking_mode=thinking_mode,
            system_prompt=system_prompt
        )

        if result.get("success"):
            return {
                "thinking": result.get("reasoning_content", ""),
                "answer": result.get("content", "")
            }
        else:
            return {
                "thinking": "",
                "answer": f"查询失败: {result.get('error', '未知错误')}"
            }

    def get_models(self) -> List[str]:
        """
        获取可用模型列表

        Returns:
            模型名称列表
        """
        return [
            self.MODEL_V4_PRO,
            self.MODEL_V4_FLASH,
            self.MODEL_CHAT,
            self.MODEL_REASONER
        ]

    def test_connection(self) -> Dict[str, Any]:
        """
        测试API连接

        Returns:
            测试结果
        """
        test_messages = [{"role": "user", "content": "你好，请回复'连接正常'"}]
        result = self.chat(test_messages, model=self.MODEL_V4_FLASH, max_tokens=50)
        
        if result.get("success"):
            return {
                "connected": True,
                "message": result.get("content", ""),
                "usage": result.get("usage", {})
            }
        else:
            return {
                "connected": False,
                "error": result.get("error", "")
            }


def create_deepseek_client_from_env() -> Optional[DeepSeekClient]:
    """
    从环境变量创建DeepSeek客户端

    Returns:
        DeepSeek客户端实例
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    if not api_key:
        print("错误: 未设置DEEPSEEK_API_KEY环境变量")
        return None
    
    return DeepSeekClient(api_key, base_url)


if __name__ == "__main__":
    # 测试代码
    print("=" * 50)
    print("DeepSeek V4 API 客户端测试")
    print("=" * 50)
    
    # 尝试从环境变量创建客户端
    client = create_deepseek_client_from_env()
    
    if not client:
        print("\n请设置DEEPSEEK_API_KEY环境变量，或直接传入API密钥")
        print("\n使用示例:")
        print("  export DEEPSEEK_API_KEY=your_api_key_here")
        print("  或者:")
        print("  client = DeepSeekClient('your_api_key_here')")
        exit(1)
    
    # 测试连接
    print("\n1. 测试API连接...")
    test_result = client.test_connection()
    
    if test_result.get("connected"):
        print(f"✓ 连接成功: {test_result.get('message')}")
        
        # 显示可用模型
        print("\n2. 可用模型:")
        for model in client.get_models():
            print(f"  - {model}")
        
        # 简单查询测试
        print("\n3. 简单查询测试...")
        response = client.simple_query(
            "请用Python写一个快速排序函数",
            model="deepseek-v4-flash"
        )
        print(f"✓ 查询成功:\n{response[:200]}...")
        
        # Thinking模式测试
        print("\n4. Thinking模式测试...")
        thinking_result = client.query_with_thinking(
            "请分析这个问题: 1+1为什么等于2?",
            reasoning_effort="medium"
        )
        
        if thinking_result.get("thinking"):
            print(f"✓ 推理过程:\n{thinking_result['thinking'][:200]}...")
        print(f"✓ 最终答案:\n{thinking_result['answer'][:200]}...")
        
        print("\n" + "=" * 50)
        print("测试完成！")
        print("=" * 50)
    else:
        print(f"✗ 连接失败: {test_result.get('error')}")
