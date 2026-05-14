#!/usr/bin/env python3
"""
Qwen3.6-Plus API客户端
支持多个API平台：阿里云百炼、海鲸AI、OpenRouter等
"""

import os
from typing import Dict, Any, List, Optional
from openai import OpenAI


class QwenClient:
    """
    Qwen3.6-Plus API客户端
    兼容OpenAI SDK格式
    """

    # 支持的API平台配置
    PLATFORMS = {
        "dashscope": {
            "name": "阿里云百炼",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3.6-plus"
        },
        "atalk": {
            "name": "海鲸AI",
            "base_url": "https://api.atalk-ai.com/v2",
            "model": "qwen3.6-plus"
        },
        "openrouter": {
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen-3.6-plus"
        },
        "vvmai": {
            "name": "万维盟API",
            "base_url": "https://api.vvmai.com/v1",
            "model": "qwen3.6-plus"
        }
    }

    def __init__(self, api_key: str, platform: str = "dashscope", base_url: Optional[str] = None):
        """
        初始化Qwen客户端

        Args:
            api_key: API密钥
            platform: 平台名称 ("dashscope", "atalk", "openrouter", "vvmai")
            base_url: 自定义API地址（可选）
        """
        self.api_key = api_key
        self.platform = platform
        
        # 获取平台配置
        if platform in self.PLATFORMS:
            config = self.PLATFORMS[platform]
            self.base_url = base_url or config["base_url"]
            self.default_model = config["model"]
        else:
            self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            self.default_model = "qwen3.6-plus"
        
        # 初始化OpenAI兼容客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url
        )

    def chat(self, 
             messages: List[Dict[str, str]], 
             model: Optional[str] = None,
             temperature: float = 0.7,
             top_p: float = 0.9,
             max_tokens: Optional[int] = None,
             stream: bool = False,
             enable_thinking: bool = False) -> Dict[str, Any]:
        """
        发送聊天请求

        Args:
            messages: 对话历史消息列表
            model: 模型名称（可选，默认使用平台默认模型）
            temperature: 温度参数（0-2）
            top_p: top_p参数（0-1）
            max_tokens: 最大输出token数
            stream: 是否流式输出
            enable_thinking: 是否启用思考模式

        Returns:
            API响应结果
        """
        model = model or self.default_model
        
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

        # Qwen3.6-Plus原生支持思考模式
        if enable_thinking:
            params["extra_body"] = {"enable_thinking": True}

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
                    "total_tokens": response.usage.total_tokens
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
                    model: Optional[str] = None,
                    temperature: float = 0.7,
                    max_tokens: Optional[int] = None,
                    enable_thinking: bool = False):
        """
        流式聊天请求

        Args:
            messages: 对话历史消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出token数
            enable_thinking: 是否启用思考模式

        Yields:
            流式响应块
        """
        model = model or self.default_model
        
        # 构建请求参数
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        if enable_thinking:
            params["extra_body"] = {"enable_thinking": True}

        try:
            stream = self.client.chat.completions.create(**params)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"[错误] {str(e)}"

    def simple_query(self, 
                    prompt: str, 
                    model: Optional[str] = None,
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        result = self.chat(messages, model=model, temperature=temperature)
        
        if result.get("success"):
            return result.get("content", "")
        else:
            return f"查询失败: {result.get('error', '未知错误')}"

    def query_with_thinking(self, 
                           prompt: str, 
                           model: Optional[str] = None,
                           system_prompt: Optional[str] = None) -> Dict[str, str]:
        """
        带思考过程的查询

        Args:
            prompt: 用户提示词
            model: 模型名称
            system_prompt: 系统提示词（可选）

        Returns:
            包含思考过程和最终答案的字典
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result = self.chat(
            messages, 
            model=model, 
            enable_thinking=True
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

    def test_connection(self) -> Dict[str, Any]:
        """
        测试API连接

        Returns:
            测试结果
        """
        test_messages = [{"role": "user", "content": "你好，请回复'连接正常'"}]
        result = self.chat(test_messages, max_tokens=50)
        
        if result.get("success"):
            return {
                "connected": True,
                "platform": self.platform,
                "message": result.get("content", ""),
                "usage": result.get("usage", {})
            }
        else:
            return {
                "connected": False,
                "platform": self.platform,
                "error": result.get("error", "")
            }

    @classmethod
    def list_platforms(cls) -> List[Dict[str, str]]:
        """
        列出所有支持的平台

        Returns:
            平台列表
        """
        return [
            {"id": key, "name": value["name"], "base_url": value["base_url"]}
            for key, value in cls.PLATFORMS.items()
        ]


def create_qwen_client_from_env() -> Optional[QwenClient]:
    """
    从环境变量创建Qwen客户端

    Returns:
        Qwen客户端实例
    """
    api_key = os.getenv("QWEN_API_KEY", "")
    base_url = os.getenv("QWEN_BASE_URL", "")
    platform = os.getenv("QWEN_PLATFORM", "dashscope")
    
    if not api_key:
        print("错误: 未设置QWEN_API_KEY环境变量")
        return None
    
    return QwenClient(api_key, platform=platform, base_url=base_url if base_url else None)


if __name__ == "__main__":
    # 测试代码
    print("=" * 60)
    print("Qwen3.6-Plus API 客户端测试")
    print("=" * 60)
    
    # 显示支持的平台
    print("\n支持的平台:")
    for platform in QwenClient.list_platforms():
        print(f"  - {platform['id']}: {platform['name']} ({platform['base_url']})")
    
    # 尝试从环境变量创建客户端
    client = create_qwen_client_from_env()
    
    if not client:
        print("\n请设置QWEN_API_KEY环境变量，或直接传入API密钥")
        print("\n使用示例:")
        print("  export QWEN_API_KEY=your_api_key_here")
        print("  export QWEN_PLATFORM=dashscope  # 或 atalk, openrouter, vvmai")
        print("  或者:")
        print("  client = QwenClient('your_api_key_here', platform='dashscope')")
        exit(1)
    
    # 测试连接
    print(f"\n使用平台: {client.platform}")
    print("\n测试API连接...")
    test_result = client.test_connection()
    
    if test_result.get("connected"):
        print(f"✓ 连接成功: {test_result.get('message')}")
        
        # 简单查询测试
        print("\n简单查询测试...")
        response = client.simple_query(
            "请用Python写一个快速排序函数",
            model="qwen3.6-plus"
        )
        print(f"✓ 查询成功:\n{response[:200]}...")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
    else:
        print(f"✗ 连接失败: {test_result.get('error')}")
