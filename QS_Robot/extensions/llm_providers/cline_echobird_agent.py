import subprocess
import json
import os
import sys
import requests
from typing import Dict, List, Any, Optional
from .base_llm import BaseLLMProvider

class ClineEchoBirdAgent(BaseLLMProvider):
    """Cline智能体提供者 - 通过EchoBird实现模型切换的完整智能体能力"""
    
    name = "cline-echobird"
    description = "Cline智能体 + EchoBird模型切换"
    
    def __init__(self, config=None):
        self.config = config or {}
        self.model = self.config.get("model", "gpt-4o")
        self._available_models = []
        self._cline_path = self._find_cline_path()
        
        # EchoBird配置
        self._echobird_base = self.config.get("echobird_base", "http://localhost:8080/v1")
        self._echobird_api_key = self.config.get("echobird_api_key", "")
        self._use_echobird = self.config.get("use_echobird", True)
        
        self._load_models()
    
    def _find_cline_path(self):
        """查找Cline命令路径"""
        try:
            result = subprocess.run(
                ["cline", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "cline"
        except Exception:
            pass
        
        fixed_paths = [
            "node_modules/.bin/cline",
            "C:\\Users\\PT\\AppData\\Roaming\\npm\\node_modules\\cline\\bin\\cline",
            "C:\\Users\\PT\\AppData\\Roaming\\npm\\cline.cmd",
            "node_modules/cline/dist/cli.js"
        ]
        
        for path in fixed_paths:
            if os.path.exists(path):
                return path
        
        npm_path = "C:\\Users\\PT\\AppData\\Roaming\\npm"
        if os.path.isdir(npm_path):
            for item in os.listdir(npm_path):
                if item.startswith(".cline-") and os.path.isdir(os.path.join(npm_path, item)):
                    cline_bin = os.path.join(npm_path, item, "bin", "cline")
                    if os.path.exists(cline_bin):
                        return cline_bin
        
        node_modules_path = "C:\\Users\\PT\\AppData\\Roaming\\npm\\node_modules"
        if os.path.isdir(node_modules_path):
            for item in os.listdir(node_modules_path):
                if item.lower() == "cline" and os.path.isdir(os.path.join(node_modules_path, item)):
                    cline_bin = os.path.join(node_modules_path, item, "bin", "cline")
                    if os.path.exists(cline_bin):
                        return cline_bin
        
        return "npx cline"
    
    def _load_models(self):
        """加载可用模型列表 - 优先从EchoBird获取"""
        if self._use_echobird:
            self._load_echobird_models()
        if not self._available_models:
            self._load_cline_models()
    
    def _load_echobird_models(self):
        """从EchoBird获取模型列表"""
        try:
            url = f"{self._echobird_base.rstrip('/')}/models"
            headers = {}
            if self._echobird_api_key:
                headers["Authorization"] = f"Bearer {self._echobird_api_key}"
            
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self._available_models = [m.get("id", "") for m in data.get("data", [])]
                print(f"[INFO] 从EchoBird加载了 {len(self._available_models)} 个模型")
        except Exception as e:
            print(f"[WARNING] 无法从EchoBird获取模型列表: {e}")
    
    def _load_cline_models(self):
        """从Cline获取模型列表"""
        try:
            if self._cline_path == "npx cline":
                result = subprocess.run(
                    ["npx", "cline", "config", "list", "models"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            else:
                result = subprocess.run(
                    ["node", self._cline_path, "config", "list", "models"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                self._available_models = [line.strip() for line in lines if line.strip()]
        except Exception as e:
            print(f"[WARNING] 无法获取Cline模型列表: {e}")
    
    def chat(self, messages, stream=False, **kwargs):
        """
        调用Cline智能体聊天接口，通过EchoBird进行模型切换
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            **kwargs: 其他参数
        """
        if self._use_echobird and self.is_echobird_available():
            return self._chat_via_echobird(messages, stream, **kwargs)
        return self._chat_via_cline(messages, stream, **kwargs)
    
    def _chat_via_echobird(self, messages, stream=False, **kwargs):
        """通过EchoBird调用模型"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if "options" in kwargs:
            payload["options"] = kwargs["options"]
        
        url = f"{self._echobird_base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._echobird_api_key:
            headers["Authorization"] = f"Bearer {self._echobird_api_key}"
        
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
    
    def _chat_via_cline(self, messages, stream=False, **kwargs):
        """直接调用Cline"""
        try:
            prompt = ""
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt += f"{role}: {content}\n\n"
            
            if self._cline_path == "npx cline":
                cmd = ["npx", "cline", "-y", "--model", self.model]
            else:
                cmd = ["node", self._cline_path, "-y", "--model", self.model]
            
            if stream:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                
                def stream_generator():
                    with process.stdin:
                        process.stdin.write(prompt)
                        process.stdin.flush()
                    
                    for line in iter(process.stdout.readline, ''):
                        yield line.strip()
                
                return stream_generator()
            else:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    return f"[错误] Cline执行失败: {result.stderr}"
                    
        except Exception as e:
            return f"[错误] Cline调用失败: {str(e)}"
    
    def get_available_models(self):
        """获取可用模型列表"""
        self._load_models()
        return self._available_models
    
    def set_model(self, model_name):
        """设置当前使用的模型"""
        if model_name in self._available_models or not self._available_models:
            self.model = model_name
            return True
        return False
    
    def is_available(self):
        """检查是否可用"""
        if self._use_echobird and self.is_echobird_available():
            return True
        return self.is_cline_available()
    
    def is_echobird_available(self):
        """检查EchoBird是否可用"""
        try:
            url = f"{self._echobird_base.rstrip('/')}/models"
            headers = {}
            if self._echobird_api_key:
                headers["Authorization"] = f"Bearer {self._echobird_api_key}"
            resp = requests.get(url, headers=headers, timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
    
    def is_cline_available(self):
        """检查Cline是否可用"""
        try:
            if self._cline_path == "npx cline":
                result = subprocess.run(
                    ["npx", "cline", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                result = subprocess.run(
                    ["node", self._cline_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            return result.returncode == 0
        except Exception:
            return False
    
    def set_echobird_enabled(self, enabled: bool):
        """启用/禁用EchoBird"""
        self._use_echobird = enabled
        self._load_models()
    
    def get_echobird_status(self):
        """获取EchoBird状态"""
        return {
            "enabled": self._use_echobird,
            "available": self.is_echobird_available(),
            "base_url": self._echobird_base
        }