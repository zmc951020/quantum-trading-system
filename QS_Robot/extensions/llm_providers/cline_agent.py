import subprocess
import json
import os
import sys
from typing import Dict, List, Any, Optional
from .base_llm import BaseLLMProvider

class ClineAgentProvider(BaseLLMProvider):
    """Cline智能体提供者 - 通过Cline CLI调用完整智能体能力"""
    
    name = "cline"
    description = "Cline智能体 - 完整AI助手能力"
    
    def __init__(self, config=None):
        self.config = config or {}
        self.model = self.config.get("model", "claude-3-5-sonnet")
        self.provider = self.config.get("provider", "anthropic")
        self._available_models = []
        self._cline_path = self._find_cline_path()
        self._load_models()
    
    def _find_cline_path(self):
        """查找Cline命令路径 - 优先使用系统命令"""
        # 先尝试直接使用系统命令 cline
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
        
        # 固定路径
        fixed_paths = [
            "node_modules/.bin/cline",
            "C:\\Users\\PT\\AppData\\Roaming\\npm\\node_modules\\cline\\bin\\cline",
            "C:\\Users\\PT\\AppData\\Roaming\\npm\\cline.cmd",
            "node_modules/cline/dist/cli.js"
        ]
        
        for path in fixed_paths:
            if os.path.exists(path):
                return path
        
        # 动态查找 .cline-* 目录
        npm_path = "C:\\Users\\PT\\AppData\\Roaming\\npm"
        if os.path.isdir(npm_path):
            for item in os.listdir(npm_path):
                if item.startswith(".cline-") and os.path.isdir(os.path.join(npm_path, item)):
                    cline_bin = os.path.join(npm_path, item, "bin", "cline")
                    if os.path.exists(cline_bin):
                        return cline_bin
        
        # 查找 node_modules/cline
        node_modules_path = "C:\\Users\\PT\\AppData\\Roaming\\npm\\node_modules"
        if os.path.isdir(node_modules_path):
            for item in os.listdir(node_modules_path):
                if item.lower() == "cline" and os.path.isdir(os.path.join(node_modules_path, item)):
                    cline_bin = os.path.join(node_modules_path, item, "bin", "cline")
                    if os.path.exists(cline_bin):
                        return cline_bin
        
        return "npx cline"
    
    def _load_models(self):
        """加载可用模型列表"""
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
        调用Cline智能体聊天接口
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            **kwargs: 其他参数
        
        Returns:
            str | Generator: 响应
        """
        try:
            prompt = ""
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt += f"{role}: {content}\n\n"
            
            if self._cline_path == "npx cline":
                cmd = ["npx", "cline", "-y", "--model", self.model, "--provider", self.provider]
            else:
                cmd = ["node", self._cline_path, "-y", "--model", self.model, "--provider", self.provider]
            
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
    
    def run_command(self, command: str) -> str:
        """运行Cline命令"""
        try:
            if self._cline_path == "npx cline":
                result = subprocess.run(
                    ["npx", "cline", "-y", command],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            else:
                result = subprocess.run(
                    ["node", self._cline_path, "-y", command],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"[错误] {result.stderr}"
        except Exception as e:
            return f"[错误] {str(e)}"