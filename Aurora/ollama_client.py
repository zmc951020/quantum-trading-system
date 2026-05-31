#!/usr/bin/env python3
"""
Ollama 本地推理客户端
兼容 OpenAI SDK 格式，与 DeepSeekClient / QwenClient 接口一致
支持所有本地已部署的 Ollama 模型

本地模型清单:
  qwen2.5-coder:1.5b   (986MB)  代码辅助
  qwen:1.8b            (1.1GB)  轻量数据解析
  llama3.2:3b          (2.0GB)  通用轻量推理
  qwen2.5:7b-instruct  (4.7GB)  策略分析/中等推理
  qwen:7b              (4.5GB)  通用推理
  qwen2.5:0.5b         (397MB)  超轻量分类/排序
  llama3.2:1b          (1.3GB)  最小化推理
"""

import json
import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
import requests

logger = logging.getLogger(__name__)


# ── 模型规格定义 ──
@dataclass
class OllamaModelSpec:
    """Ollama模型规格"""
    name: str
    size_mb: float
    category: str          # "ultra_light" | "light" | "medium" | "heavy"
    max_tokens: int
    avg_latency_ms: float  # 平均推理延迟（毫秒）
    recommended_priority: str  # 推荐处理的任务优先级 P3/P4/P5
    fallback_for: List[str] = field(default_factory=list)  # 可作为哪些模型的降级方案

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "size_mb": self.size_mb,
            "category": self.category,
            "max_tokens": self.max_tokens,
            "avg_latency_ms": self.avg_latency_ms,
            "recommended_priority": self.recommended_priority,
            "fallback_for": self.fallback_for
        }


# 已知优质免费模型规格表
KNOWN_OLLAMA_MODELS: Dict[str, OllamaModelSpec] = {
    "qwen2.5:0.5b": OllamaModelSpec(
        name="qwen2.5:0.5b", size_mb=397, category="ultra_light",
        max_tokens=4096, avg_latency_ms=50, recommended_priority="P5",
        fallback_for=["qwen:1.8b", "llama3.2:1b"]
    ),
    "qwen:1.8b": OllamaModelSpec(
        name="qwen:1.8b", size_mb=1100, category="light",
        max_tokens=8192, avg_latency_ms=150, recommended_priority="P5",
        fallback_for=["llama3.2:3b"]
    ),
    "llama3.2:1b": OllamaModelSpec(
        name="llama3.2:1b", size_mb=1300, category="light",
        max_tokens=8192, avg_latency_ms=120, recommended_priority="P5",
        fallback_for=["qwen:1.8b", "llama3.2:3b"]
    ),
    "qwen2.5-coder:1.5b": OllamaModelSpec(
        name="qwen2.5-coder:1.5b", size_mb=986, category="light",
        max_tokens=8192, avg_latency_ms=200, recommended_priority="P4",
        fallback_for=["qwen2.5:7b-instruct"]
    ),
    "llama3.2:3b": OllamaModelSpec(
        name="llama3.2:3b", size_mb=2000, category="medium",
        max_tokens=16384, avg_latency_ms=500, recommended_priority="P4",
        fallback_for=["qwen2.5:7b-instruct", "qwen:7b"]
    ),
    "qwen2.5:7b-instruct": OllamaModelSpec(
        name="qwen2.5:7b-instruct", size_mb=4700, category="heavy",
        max_tokens=32768, avg_latency_ms=1500, recommended_priority="P3",
        fallback_for=["qwen3.6-plus", "deepseek-v4-flash"]
    ),
    "qwen:7b": OllamaModelSpec(
        name="qwen:7b", size_mb=4500, category="heavy",
        max_tokens=32768, avg_latency_ms=1400, recommended_priority="P3",
        fallback_for=["qwen2.5:7b-instruct"]
    ),
    "my-deepseek-coder:latest": OllamaModelSpec(
        name="my-deepseek-coder:latest", size_mb=4100, category="heavy",
        max_tokens=32768, avg_latency_ms=1600, recommended_priority="P4",
        fallback_for=["qwen2.5-coder:1.5b"]
    ),
}


class OllamaClient:
    """
    Ollama 本地推理客户端
    兼容 OpenAI SDK 格式的 chat 接口
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2:3b"
    DEFAULT_TIMEOUT = 120  # 默认超时（秒）

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[int] = None,
        auto_pull: bool = False  # 自动拉取不存在的模型（生产环境应为False）
    ):
        """
        初始化Ollama客户端

        Args:
            base_url: Ollama服务地址，默认 http://localhost:11434
            default_model: 默认模型名
            timeout: HTTP请求超时（秒）
            auto_pull: 是否自动拉取不存在的模型
        """
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip('/')
        self.default_model = default_model or self.DEFAULT_MODEL
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.auto_pull = auto_pull

        # 健康状态
        self._healthy = False
        self._last_check: Optional[float] = None
        self._available_models: List[str] = []
        self._model_latency: Dict[str, float] = {}  # 实测延迟记录
        self._lock = threading.Lock()

        # 推理统计
        self._stats = {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "total_latency_ms": 0.0,
            "last_error": None,
        }

        # 尝试连接
        self._check_health()

    # ── 健康检查 ──

    def _check_health(self) -> bool:
        """检查Ollama服务健康状态"""
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                self._available_models = [m.get("name", "") for m in data.get("models", [])]
                self._healthy = True
                self._last_check = time.time()
                logger.info(f"[Ollama] 服务健康，可用模型: {len(self._available_models)}个")
                return True
            else:
                self._healthy = False
                logger.warning(f"[Ollama] 服务异常 HTTP {resp.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            self._healthy = False
            logger.warning("[Ollama] 服务未运行 (ConnectionError)")
            return False
        except Exception as e:
            self._healthy = False
            logger.warning(f"[Ollama] 健康检查失败: {e}")
            return False

    def is_healthy(self) -> bool:
        """返回当前健康状态"""
        if self._last_check and time.time() - self._last_check > 30:
            self._check_health()
        return self._healthy

    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        if not self._last_check or time.time() - self._last_check > 30:
            self._check_health()
        return list(self._available_models)

    def is_model_available(self, model_name: str) -> bool:
        """检查指定模型是否可用"""
        # 去除可能的tag后缀
        base_name = model_name.split(":")[0] if ":" in model_name else model_name
        for avail in self._available_models:
            if avail == model_name or avail.startswith(base_name):
                return True
        return False

    # ── 核心推理接口 ──

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        system_prompt: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        发送聊天请求到Ollama

        Args:
            messages: 对话历史消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称（不传则用默认模型）
            temperature: 温度参数（0-2）
            top_p: top_p参数（0-1）
            max_tokens: 最大输出token数
            stream: 是否流式输出（暂不支持）
            system_prompt: 系统提示词
            timeout: 本次调用超时（秒）

        Returns:
            {
                "id": "...",
                "model": "...",
                "choices": [{"message": {"role": "assistant", "content": "..."}}],
                "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...},
                "latency_ms": ...
            }
        """
        model = model or self.default_model
        timeout = timeout or self.timeout
        start_time = time.time()

        self._stats["total_calls"] += 1

        try:
            # 检查模型可用性
            if not self.is_model_available(model):
                logger.warning(f"[Ollama] 模型 {model} 不在本地，尝试检查完整列表...")
                self._check_health()
                if not self.is_model_available(model):
                    fallback = self._find_fallback_model(model)
                    if fallback:
                        logger.warning(f"[Ollama] 模型 {model} 不可用，降级到 {fallback}")
                        model = fallback
                    else:
                        raise RuntimeError(f"模型 {model} 不可用且无降级方案")

            # 构建请求体
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                }
            }

            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            if system_prompt:
                payload["messages"] = [{"role": "system", "content": system_prompt}] + payload["messages"]

            # 发送请求
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()

            data = resp.json()
            latency_ms = (time.time() - start_time) * 1000

            # 记录实测延迟
            with self._lock:
                self._model_latency[model] = latency_ms
                self._stats["success_calls"] += 1
                self._stats["total_latency_ms"] += latency_ms

            # 转换为 OpenAI 兼容格式
            return {
                "id": f"ollama-{int(start_time * 1000)}",
                "object": "chat.completion",
                "model": model,
                "created": int(start_time),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": data.get("message", {}).get("content", "")
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                },
                "latency_ms": latency_ms,
                "_source": "ollama_local"
            }

        except requests.exceptions.Timeout:
            self._stats["failed_calls"] += 1
            self._stats["last_error"] = f"模型 {model} 超时 (>{timeout}s)"
            raise TimeoutError(f"Ollama模型 {model} 超时 (>{timeout}s)")

        except requests.exceptions.ConnectionError:
            self._stats["failed_calls"] += 1
            self._stats["last_error"] = "Ollama服务不可达"
            self._healthy = False
            raise ConnectionError("Ollama服务未运行，请执行 'ollama serve' 启动")

        except Exception as e:
            self._stats["failed_calls"] += 1
            self._stats["last_error"] = str(e)[:200]
            raise

    # ── 降级辅助 ──

    def _find_fallback_model(self, requested_model: str) -> Optional[str]:
        """为不可用的模型查找降级替代"""
        spec = KNOWN_OLLAMA_MODELS.get(requested_model)
        if spec:
            for fallback_name in spec.fallback_for:
                if self.is_model_available(fallback_name):
                    return fallback_name

        # 通用降级：按优先级尝试
        fallback_order = [
            "qwen2.5:7b-instruct",
            "llama3.2:3b",
            "qwen:1.8b",
            "qwen2.5:0.5b",
        ]
        for fb in fallback_order:
            if self.is_model_available(fb):
                return fb

        return None

    # ── 批量推理（用于非实时场景） ──

    def batch_chat(
        self,
        requests_list: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_workers: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        批量推理（顺序执行以避免本地模型OOM）

        Args:
            requests_list: [{"messages": [...], "temperature": 0.7, ...}, ...]
            model: 模型名称
            max_workers: 最大并发数（本地模型建议≤3）

        Returns:
            结果列表
        """
        results = []
        for i, req in enumerate(requests_list):
            try:
                result = self.chat(
                    messages=req.get("messages", []),
                    model=model or req.get("model"),
                    temperature=req.get("temperature", 0.7),
                    top_p=req.get("top_p", 0.9),
                    max_tokens=req.get("max_tokens"),
                    system_prompt=req.get("system_prompt"),
                )
                results.append({"index": i, "success": True, "result": result})
            except Exception as e:
                results.append({"index": i, "success": False, "error": str(e)})
        return results

    # ── 统计与信息 ──

    def get_stats(self) -> Dict[str, Any]:
        """获取推理统计"""
        with self._lock:
            total = max(self._stats["total_calls"], 1)
            return {
                "healthy": self._healthy,
                "available_models": len(self._available_models),
                "total_calls": self._stats["total_calls"],
                "success_rate": round(self._stats["success_calls"] / total * 100, 1),
                "avg_latency_ms": round(self._stats["total_latency_ms"] / total, 1),
                "model_latency": dict(self._model_latency),
                "last_error": self._stats["last_error"],
                "last_check": self._last_check,
            }

    def get_model_spec(self, model_name: str) -> Optional[dict]:
        """获取模型规格信息"""
        spec = KNOWN_OLLAMA_MODELS.get(model_name)
        return spec.to_dict() if spec else None

    def get_recommended_model_for_priority(self, priority: str) -> str:
        """根据任务优先级推荐最佳本地模型"""
        priority = priority.upper()
        priority_map = {
            "P3": ["qwen2.5:7b-instruct", "qwen:7b"],
            "P4": ["llama3.2:3b", "qwen2.5-coder:1.5b"],
            "P5": ["qwen:1.8b", "llama3.2:1b", "qwen2.5:0.5b"],
        }
        candidates = priority_map.get(priority, ["llama3.2:3b"])
        for model in candidates:
            if self.is_model_available(model):
                return model
        return self.default_model

    # ── 系统提示模板 ──

    QUANT_SYSTEM_PROMPTS = {
        "strategy_analysis": "你是一个量化交易策略分析师。请基于提供的市场数据，给出简洁有力的分析结论。",
        "data_parsing": "你是一个金融数据解析器。请从提供的原始数据中提取关键信息，以JSON格式输出。",
        "risk_assessment": "你是一个交易风控专家。请评估当前持仓风险，给出具体数值和操作建议。",
        "report_generation": "你是一个量化交易报告生成器。请生成专业、结构化的交易报告。",
        "code_review": "你是一个量化交易系统代码审查员。请审查代码逻辑，指出潜在问题。",
        "general_qa": "你是Aurora量化交易系统的AI助手，专门处理交易相关咨询。",
    }

    def get_system_prompt(self, task_type: str) -> str:
        """获取预置系统提示词"""
        return self.QUANT_SYSTEM_PROMPTS.get(
            task_type,
            "你是Aurora量化交易系统的AI助手，帮助用户处理量化交易相关任务。"
        )


# ── 快速启动函数 ──
def create_ollama_client() -> OllamaClient:
    """快速创建Ollama客户端的工厂函数"""
    client = OllamaClient()
    if client.is_healthy():
        logger.info(f"[Ollama] 客户端初始化成功，{len(client.get_available_models())}个模型可用")
    else:
        logger.warning("[Ollama] 客户端初始化完成但服务未运行")
    return client


# ── 命令行测试 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  Ollama 客户端测试")
    print("=" * 60)

    client = create_ollama_client()

    print(f"\n健康状态: {'✅ 正常' if client.is_healthy() else '❌ 未运行'}")
    print(f"可用模型: {client.get_available_models()}")

    if client.is_healthy():
        # 使用最小模型做快速测试
        test_model = "qwen2.5:0.5b" if client.is_model_available("qwen2.5:0.5b") else "llama3.2:1b"
        if client.is_model_available(test_model):
            print(f"\n→ 测试模型: {test_model}")
            try:
                result = client.chat(
                    messages=[{"role": "user", "content": "用一句话介绍什么是量化交易。"}],
                    model=test_model,
                    max_tokens=100
                )
                content = result["choices"][0]["message"]["content"]
                print(f"  回复: {content}")
                print(f"  延迟: {result['latency_ms']:.0f}ms")
                print(f"  Token: {result['usage']}")
            except Exception as e:
                print(f"  测试失败: {e}")

        # 优先级推荐
        print("\n→ 优先级模型推荐:")
        for p in ["P3", "P4", "P5"]:
            rec = client.get_recommended_model_for_priority(p)
            print(f"  {p}: {rec}")

    print(f"\n统计: {client.get_stats()}")
    print("=" * 60)