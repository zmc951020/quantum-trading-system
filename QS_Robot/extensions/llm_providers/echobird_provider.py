import requests
import json
from .base_llm import BaseLLMProvider

class EchoBirdProvider(BaseLLMProvider):
    """EchoBird LLM提供者 - 通过EchoBird代理访问多种模型"""
    
    name = "echobird"
    description = "EchoBird统一模型代理"
    
    def __init__(self, config=None):
        self.config = config or {}
        self.api_base = self.config.get("api_base", "http://localhost:8080/v1")
        self.model = self.config.get("model", "gpt-4o")
        self.api_key = self.config.get("api_key", "")
        self.available_models = []
        self._refresh_models()
    
    def _refresh_models(self):
        try:
            url = f"{self.api_base.rstrip('/')}/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self.available_models = [m.get("id", "") for m in data.get("data", [])]
        except Exception as e:
            print(f"[WARNING] 无法获取EchoBird模型列表: {e}")
    
    def chat(self, messages, stream=False, **kwargs):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if "options" in kwargs:
            payload["options"] = kwargs["options"]
        
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        if not stream:
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                raise Exception(f"EchoBird请求失败: {resp.status_code}")
            except Exception as e:
                return f"[错误] EchoBird调用失败: {str(e)}"
        else:
            def stream_generator():
                try:
                    resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=300)
                    if resp.status_code == 200:
                        for line in resp.iter_lines():
                            if line:
                                try:
                                    data = line.decode('utf-8')
                                    if data.startswith('data: '):
                                        data = data[6:]
                                        if data.strip() == '[DONE]':
                                            break
                                        chunk = json.loads(data)
                                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                        if content:
                                            yield content
                                except Exception:
                                    continue
                except Exception as e:
                    yield f"[错误] EchoBird流式调用失败: {str(e)}"
            return stream_generator()
    
    def get_available_models(self):
        self._refresh_models()
        return self.available_models
    
    def set_model(self, model_name):
        if model_name in self.available_models or not self.available_models:
            self.model = model_name
            return True
        return False
    
    def is_available(self):
        try:
            url = f"{self.api_base.rstrip('/')}/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            resp = requests.get(url, headers=headers, timeout=1)
            return resp.status_code == 200
        except Exception:
            return False