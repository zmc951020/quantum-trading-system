#!/usr/bin/env python3
"""
Ollama Agent
整合工具调用系统，实现完整的触发机制和流程
"""

import json
from typing import Dict, Any, Optional
from tools.tool_manager import tool_manager

class OllamaAgent:
    """
    Ollama Agent
    """
    
    def __init__(self):
        """
        初始化Ollama Agent
        """
        self.tool_manager = tool_manager
        self.conversation_history = []
    
    def process_message(self, message: str) -> Dict[str, Any]:
        """
        处理用户消息
        
        Args:
            message: 用户消息
            
        Returns:
            处理结果
        """
        # 添加到对话历史
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # 分析消息，确定是否需要工具调用
        tool_info = self.tool_manager.analyze_request(message)
        
        if tool_info:
            # 需要工具调用
            result = self.tool_manager.execute_tool_call(tool_info)
            
            # 添加工具调用结果到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": f"执行了工具调用: {tool_info['tool']}",
                "tool_call": tool_info,
                "tool_result": result
            })
            
            return {
                "status": "tool_called",
                "tool_info": tool_info,
                "result": result
            }
        else:
            # 不需要工具调用，直接响应
            response = self._generate_response(message)
            
            # 添加响应到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": response
            })
            
            return {
                "status": "direct_response",
                "response": response
            }
    
    def _generate_response(self, message: str) -> str:
        """
        生成直接响应
        
        Args:
            message: 用户消息
            
        Returns:
            响应内容
        """
        # 简单的响应逻辑，实际应用中可能需要更复杂的处理
        if "你好" in message or "Hello" in message:
            return "你好！我是Ollama Agent，有什么可以帮助你的吗？"
        elif "工具调用" in message:
            return "我已经配置了完整的工具调用系统，可以帮你执行各种任务，如打开网页、读取文件、运行命令等。"
        elif "策略" in message:
            return "我可以帮你分析和测试量化交易策略，需要我做什么？"
        else:
            return "我理解你的请求，但是我需要更多信息来提供更准确的帮助。"
    
    def get_conversation_history(self) -> list:
        """
        获取对话历史
        
        Returns:
            对话历史列表
        """
        return self.conversation_history
    
    def clear_conversation(self):
        """
        清除对话历史
        """
        self.conversation_history = []

# 创建Ollama Agent实例
ollama_agent = OllamaAgent()

if __name__ == "__main__":
    # 测试Ollama Agent
    print("Ollama Agent 测试")
    print("输入'退出'结束测试")
    
    while True:
        user_input = input("用户: ")
        if user_input == "退出":
            break
        
        result = ollama_agent.process_message(user_input)
        print(f"Ollama: {json.dumps(result, indent=2, ensure_ascii=False)}")
        print()
