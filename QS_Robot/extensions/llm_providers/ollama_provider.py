
import requests
from .base_llm import BaseLLMProvider

class OllamaProvider(BaseLLMProvider):
    """Ollama本地LLM提供者"""
    
    name = "ollama"
    description = "Ollama本地LLM接口"
    
    def __init__(self, config=None):
        """
        初始化Ollama提供者
        
        Args:
            config: 配置字典，包含 api_base, model 等
        """
        self.config = config or {}
        self.api_base = self.config.get("api_base", "http://localhost:11434")
        self.model = self.config.get("model", "qwen2.5-coder:1.5b")
        self.available_models = []
        self._refresh_models()
    
    def _refresh_models(self):
        """从Ollama服务刷新可用模型列表"""
        try:
            resp = requests.get(f"{self.api_base}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self.available_models = [model.get("name", "") for model in data.get("models", [])]
        except Exception as e:
            print(f"[WARNING] 无法获取Ollama模型列表: {e}")
    
    def chat(self, messages, stream=False, **kwargs):
        """
        聊天接口
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            **kwargs: 其他参数
        
        Returns:
            str: 非流式输出时返回完整响应
            Generator[str]: 流式输出时返回迭代器
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        # 可选参数覆盖
        if "options" in kwargs:
            payload["options"] = kwargs["options"]
        
        url = f"{self.api_base}/api/chat"
        
        if not stream:
            try:
                resp = requests.post(url, json=payload, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("message", {}).get("content", "")
                raise Exception(f"Ollama请求失败: {resp.status_code}")
            except Exception as e:
                return f"[错误] Ollama调用失败: {str(e)}"
        else:
            def stream_generator():
                try:
                    resp = requests.post(url, json=payload, stream=True, timeout=300)
                    if resp.status_code == 200:
                        for line in resp.iter_lines():
                            if line:
                                try:
                                    data = line.decode('utf-8')
                                    import json
                                    chunk = json.loads(data)
                                    if "message" in chunk:
                                        yield chunk["message"].get("content", "")
                                except Exception:
                                    continue
                except Exception as e:
                    yield f"[错误] Ollama流式调用失败: {str(e)}"
            return stream_generator()
    
    def get_available_models(self):
        """获取可用模型列表"""
        self._refresh_models()
        return self.available_models
    
    def set_model(self, model_name):
        """设置当前使用的模型"""
        if model_name in self.available_models or not self.available_models:
            self.model = model_name
            return True
        return False
    
    def is_available(self):
        """检查Ollama服务是否可用"""
        try:
            resp = requests.get(f"{self.api_base}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

