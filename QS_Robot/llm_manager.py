import os
from typing import Dict, Any, List, Optional
from config.config import config
from extensions.llm_providers import BaseLLMProvider, OllamaProvider, EchoBirdProvider, ClineAgentProvider
from extensions.llm_providers.smart_model_selector import SmartModelSelector, TaskType

class LLMManager:
    """LLM管理器 - 管理多个LLM提供者，支持智能模型切换"""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        self.smart_selector = None
        self._init_providers()
        self._init_smart_selector()
    
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
        
        # EchoBird
        if providers_config.get("echobird", {}).get("enabled", False):
            echobird_config = providers_config["echobird"]
            self.providers["echobird"] = EchoBirdProvider({
                "api_base": echobird_config.get("api_base", "http://localhost:8080/v1"),
                "model": echobird_config.get("default_model", "gpt-4o"),
                "api_key": echobird_config.get("api_key", "")
            })
            print("[OK] EchoBird提供者已初始化")
        
        # Cline智能体
        if providers_config.get("cline", {}).get("enabled", False):
            cline_config = providers_config["cline"]
            self.providers["cline"] = ClineAgentProvider({
                "model": cline_config.get("default_model", "claude-3-5-sonnet"),
                "provider": cline_config.get("provider", "anthropic")
            })
            print("[OK] Cline智能体提供者已初始化")
        
        # 设置默认激活的提供者
        if self.providers:
            self.active_provider = list(self.providers.values())[0]
            print(f"[OK] 默认LLM提供者: {self.active_provider.name}")
    
    def _init_smart_selector(self):
        """初始化智能模型选择器"""
        self.smart_selector = SmartModelSelector(self)
        print("[OK] 智能模型选择器已初始化")
    
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
    
    def chat(self, messages, stream=False, auto_switch=True, **kwargs):
        """
        通用聊天接口 - 使用当前激活的LLM提供者
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            auto_switch: 是否根据内容自动切换模型
            **kwargs: 其他参数
        
        Returns:
            str | Generator: 响应
        """
        if self.active_provider is None:
            return "[错误] 没有可用的LLM提供者"
        
        if not self.active_provider.is_available():
            return f"[错误] {self.active_provider.name} 服务不可用"
        
        # 智能自动切换模型
        if auto_switch and self.smart_selector and self.smart_selector.is_auto_switch_enabled():
            if messages:
                last_message = messages[-1]
                if isinstance(last_message, dict) and "content" in last_message:
                    task_type = self.smart_selector.detect_task_type(last_message["content"])
                    self.smart_selector.switch_to_best_model(task_type)
        
        return self.active_provider.chat(messages, stream, **kwargs)
    
    def simple_chat(self, user_message, system_prompt=None, auto_switch=True):
        """简单的单轮对话"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        return self.chat(messages, auto_switch=auto_switch)
    
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
    
    def enable_auto_switch(self, enabled: bool):
        """启用/禁用智能自动切换"""
        if self.smart_selector:
            self.smart_selector.enable_auto_switch(enabled)
            print(f"[OK] 智能自动切换已{'启用' if enabled else '禁用'}")
    
    def is_auto_switch_enabled(self) -> bool:
        """检查是否启用智能自动切换"""
        return self.smart_selector.is_auto_switch_enabled() if self.smart_selector else False
    
    def set_task_type(self, task_type: str):
        """设置当前任务类型"""
        if self.smart_selector:
            self.smart_selector.set_task_type(task_type)
    
    def detect_task_type(self, prompt: str) -> str:
        """检测任务类型"""
        if self.smart_selector:
            return self.smart_selector.detect_task_type(prompt)
        return TaskType.GENERAL_CHAT
    
    def suggest_models(self, task_type: str = None, top_n: int = 3) -> List[Dict[str, Any]]:
        """获取推荐的模型列表"""
        if self.smart_selector:
            return self.smart_selector.suggest_models(task_type, top_n)
        return []
    
    def switch_to_best_model(self, task_type: str = None) -> bool:
        """自动切换到最优模型"""
        if self.smart_selector:
            return self.smart_selector.switch_to_best_model(task_type)
        return False
    
    def get_task_types(self) -> List[str]:
        """获取所有支持的任务类型"""
        if self.smart_selector:
            return self.smart_selector.get_task_types()
        return []
    
    def get_task_type_description(self, task_type: str) -> str:
        """获取任务类型的描述"""
        if self.smart_selector:
            return self.smart_selector.get_task_type_description(task_type)
        return "未知任务类型"


# 全局LLM管理器实例
llm_manager = LLMManager()