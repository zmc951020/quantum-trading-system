
import os
from typing import Dict, Any, List, Optional
from config.config import config
from extensions.llm_providers import BaseLLMProvider, OllamaProvider

class LLMManager:
    """LLM管理器 - 管理多个LLM提供者"""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        self._init_providers()
    
    def _init_providers(self):
        """初始化所有启用的LLM提供者"""
        providers_config = config.get("llm_providers", {})
        
        # Ollama
        if providers_config.get("ollama", {}).get("enabled", False):
            ollama_config = providers_config["ollama"]
            self.providers["ollama"] = OllamaProvider({
                "api_base": ollama_config.get("api_base", "http://localhost:11434"),
                "model": ollama_config.get("default_model", "qwen2.5-coder:1.5b")
            })
            print("[OK] Ollama提供者已初始化")
        
        # 设置默认激活的提供者
        if self.providers:
            self.active_provider = list(self.providers.values())[0]
            print(f"[OK] 默认LLM提供者: {self.active_provider.name}")
    
    def get_provider(self, name):
        """获取指定名称的LLM提供者"""
        return self.providers.get(name)
    
    def set_active_provider(self, name):
        """设置当前激活的LLM提供者"""
        if name in self.providers:
            self.active_provider = self.providers[name]
            print(f"[OK] 已切换到LLM提供者: {name}")
            return True
        return False
    
    def chat(self, messages, stream=False, **kwargs):
        """
        通用聊天接口 - 使用当前激活的LLM提供者
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            **kwargs: 其他参数
        
        Returns:
            str | Generator: 响应
        """
        if self.active_provider is None:
            return "[错误] 没有可用的LLM提供者"
        
        if not self.active_provider.is_available():
            return f"[错误] {self.active_provider.name} 服务不可用"
        
        return self.active_provider.chat(messages, stream, **kwargs)
    
    def simple_chat(self, user_message, system_prompt=None):
        """简单的单轮对话"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        return self.chat(messages)
    
    def get_available_models(self):
        """获取当前激活的LLM的可用模型列表"""
        if self.active_provider:
            return self.active_provider.get_available_models()
        return []
    
    def set_model(self, model_name):
        """设置当前激活的LLM使用的模型"""
        if self.active_provider:
            return self.active_provider.set_model(model_name)
        return False
    
    def list_providers(self):
        """列出所有可用的LLM提供者"""
        return list(self.providers.keys())


# 全局LLM管理器实例
llm_manager = LLMManager()

