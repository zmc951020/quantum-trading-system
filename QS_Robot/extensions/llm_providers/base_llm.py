
from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    """LLM提供者基类 - 所有LLM接口必须实现这个基类"""
    
    name = "base_llm"
    description = "基类LLM提供者"
    available_models = []
    
    @abstractmethod
    def __init__(self, config=None):
        """初始化LLM提供者"""
        pass
    
    @abstractmethod
    def chat(self, messages, stream=False, **kwargs):
        """
        聊天接口
        
        Args:
            messages: 对话历史，格式为 [{"role": "user", "content": "..."}]
            stream: 是否流式输出
            **kwargs: 其他参数
        
        Returns:
            str: 非流式时返回完整响应
            Generator[str, None, None]: 流式时返回迭代器
        """
        pass
    
    @abstractmethod
    def get_available_models(self):
        """获取可用模型列表"""
        pass
    
    @abstractmethod
    def set_model(self, model_name):
        """设置当前使用的模型"""
        pass
    
    @abstractmethod
    def is_available(self):
        """检查LLM服务是否可用"""
        pass

