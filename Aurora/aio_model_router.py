#!/usr/bin/env python3
"""
Aurora AI模型智能路由器 (Smart Model Router)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
核心功能：根据任务关键程度自动选择最合适的AI模型
P0→DeepSeek Pro | P1→DeepSeek Flash | P2→Qwen3.6+ API
P3→Ollama qwen2.5:7b | P4→Ollama llama3.2:3b | P5→Ollama 超轻量

节省策略：自动将非核心任务从昂贵的DeepSeek Pro分流到
免费/廉价的Qwen3.6+ API 和 本地Ollama模型。

预计节省：DeepSeek Pro消耗降低 75-85%（~500元/天 → ~75-100元/天）
"""

import json
import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
import hashlib
import re

logger = logging.getLogger(__name__)


# ── 任务优先级枚举 ──
class TaskPriority(str, Enum):
    """
    任务优先级定义
    P0: 核心交易信号 — 必须用最强模型，不容出错或降级
    P1: 策略分析    — 可用Flash版，允许降级
    P2: 数据解析    — 可用API模型，允许降级
    P3: 报告生成    — 本地大模型即可
    P4: 日志分析    — 本地中模型即可
    P5: 辅助判断    — 超轻量模型即可
    """
    P0_CRITICAL = "P0"       # 核心交易信号生成、止盈止损、一键清仓
    P1_STRATEGY = "P1"       # 策略分析、市场状态判断、因子挖掘
    P2_DATA = "P2"           # 数据解析、技术指标计算、消息解析
    P3_REPORT = "P3"         # 报告生成、复盘分析、性能评估
    P4_LOG = "P4"            # 日志分析、异常分类、健康诊断
    P5_AUX = "P5"            # 辅助判断、数据标签、简单问答


# ── 模型后端枚举 ──
class ModelBackend(str, Enum):
    DEEPSEEK_PRO = "deepseek_pro"        # DeepSeek V4 Pro（最强，最贵，仅P0+明确指令可用）
    DEEPSEEK_FLASH = "deepseek_flash"    # DeepSeek V4 Flash（默认首选，便宜70%）
    QWEN3_CODER_FREE = "qwen3_coder_free" # Qwen3-Coder via OpenRouter（免费）
    MINIMAX_M21_FREE = "minimax_m21_free" # MiniMax-M2.1（免费）
    QWEN36_API = "qwen36_api"            # Qwen3.6-Plus API（强，中等成本）
    OLLAMA_30B = "ollama_30b"            # Ollama qwen3-coder:30b（本地，免费）
    OLLAMA_7B = "ollama_7b"              # Ollama qwen2.5:7b（本地，免费）
    OLLAMA_3B = "ollama_3b"              # Ollama llama3.2:3b（本地，免费）
    OLLAMA_15B = "ollama_15b"            # Ollama qwen3-coder:1.5b（本地，免费，轻量优选）
    OLLAMA_1B = "ollama_1b"              # Ollama qwen:1.8b（本地，免费）
    OLLAMA_05B = "ollama_05b"            # Ollama qwen2.5:0.5b（本地，免费）


# ── 成本估算（元/千token） ──
MODEL_COST_PER_1K = {
    ModelBackend.DEEPSEEK_PRO: 0.020,        # DeepSeek Pro 约0.02元/千token（仅P0+明确指令可用）
    ModelBackend.DEEPSEEK_FLASH: 0.006,      # DeepSeek Flash 约0.006元/千token（默认首选）
    ModelBackend.QWEN3_CODER_FREE: 0.0,     # Qwen3-Coder via OpenRouter（免费）
    ModelBackend.MINIMAX_M21_FREE: 0.0,     # MiniMax-M2.1（免费）
    ModelBackend.QWEN36_API: 0.008,          # Qwen3.6-Plus API 约0.008元/千token
    ModelBackend.OLLAMA_30B: 0.0,            # Ollama qwen3-coder:30b（本地免费）
    ModelBackend.OLLAMA_7B: 0.0,             # 本地免费
    ModelBackend.OLLAMA_3B: 0.0,             # 本地免费
    ModelBackend.OLLAMA_15B: 0.0,            # Ollama qwen3-coder:1.5b（本地免费，轻量优选）
    ModelBackend.OLLAMA_1B: 0.0,             # 本地免费
    ModelBackend.OLLAMA_05B: 0.0,            # 本地免费
}


# ── 熔断器状态（每后端独立） ──
class CircuitState(str, Enum):
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断（拒绝请求）
    HALF_OPEN = "half_open"    # 半开（尝试恢复）


@dataclass
class BackendCircuit:
    """后端熔断器"""
    backend: ModelBackend
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    open_until: Optional[float] = None  # 熔断到何时

    # 熔断参数
    FAILURE_THRESHOLD: int = 5           # 连续失败5次触发熔断
    COOLDOWN_SECONDS: int = 60           # 熔断冷却60秒
    HALF_OPEN_MAX_REQUESTS: int = 3      # 半开状态最多尝试3次

    def record_success(self):
        self.success_count += 1
        self.last_success_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.success_count = 0
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            logger.info(f"[熔断器] {self.backend.value} 恢复为 CLOSED")
        else:
            self.failure_count = 0  # 成功后重置失败计数

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.open_until = time.time() + self.COOLDOWN_SECONDS
            logger.warning(f"[熔断器] {self.backend.value} 半开失败，重新熔断 {self.COOLDOWN_SECONDS}s")
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.FAILURE_THRESHOLD:
            self.state = CircuitState.OPEN
            self.open_until = time.time() + self.COOLDOWN_SECONDS
            logger.warning(f"[熔断器] {self.backend.value} 连续失败{self.failure_count}次，触发熔断 {self.COOLDOWN_SECONDS}s")

    def allow_request(self) -> bool:
        """检查是否允许请求"""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.open_until and time.time() > self.open_until:
                self.state = CircuitState.HALF_OPEN
                self.failure_count = 0
                logger.info(f"[熔断器] {self.backend.value} 进入 HALF_OPEN，尝试恢复")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self.success_count < self.HALF_OPEN_MAX_REQUESTS
        return False


# ── 任务优先级判定规则 ──
PRIORITY_KEYWORDS = {
    TaskPriority.P0_CRITICAL: [
        "下单", "平仓", "清仓", "止损", "止盈", "市价单", "限价单", "一键清仓",
        "立即执行", "紧急", "开仓", "成交", "order", "trade", "position",
        "risk_limit", "margin_call", "liquidation", "force_close"
    ],
    TaskPriority.P1_STRATEGY: [
        "策略分析", "市场状态", "因子挖掘", "策略优化", "alpha", "夏普比率",
        "最大回撤", "波动率", "趋势判断", "策略回测", "参数优化",
        "strategy", "alpha_research", "sharpe", "backtest"
    ],
    TaskPriority.P2_DATA: [
        "数据解析", "技术指标", "MACD", "RSI", "布林带", "均线", "成交量",
        "消息解析", "数据清洗", "数据源", "行情", "K线",
        "indicator", "ohlcv", "candlestick", "volume"
    ],
    TaskPriority.P3_REPORT: [
        "报告", "复盘", "总结", "评估", "日报", "周报", "月报",
        "report", "summary", "review", "performance", "pnl"
    ],
    TaskPriority.P4_LOG: [
        "日志", "异常", "错误", "警告", "诊断", "健康检查",
        "log", "error", "exception", "diagnose", "health"
    ],
    TaskPriority.P5_AUX: [
        "问答", "帮助", "说明", "示例", "文档", "解释",
        "help", "faq", "guide", "tutorial", "example"
    ],
}


# ── 后端优先级映射（首选→降级链） ──
BACKEND_CHAIN: Dict[TaskPriority, List[ModelBackend]] = {
    TaskPriority.P0_CRITICAL: [
        ModelBackend.DEEPSEEK_PRO,      # 强制最强模型，不容降级
    ],
    TaskPriority.P1_STRATEGY: [
        ModelBackend.DEEPSEEK_FLASH,     # 首选（Flash便宜70%，日常默认）
        ModelBackend.QWEN3_CODER_FREE,   # 降级1：Qwen3-Coder OpenRouter免费
        ModelBackend.MINIMAX_M21_FREE,   # 降级2：MiniMax-M2.1免费
        ModelBackend.OLLAMA_30B,         # 降级3：本地30B免费
        ModelBackend.QWEN36_API,         # 降级4：付费API兜底
        ModelBackend.OLLAMA_7B,          # 降级5：本地7B最后
    ],
    TaskPriority.P2_DATA: [
        ModelBackend.DEEPSEEK_FLASH,     # 首选（日常默认）
        ModelBackend.QWEN3_CODER_FREE,   # 降级1：免费
        ModelBackend.MINIMAX_M21_FREE,   # 降级2：免费
        ModelBackend.OLLAMA_30B,         # 降级3：本地免费
        ModelBackend.QWEN36_API,         # 降级4：付费兜底
        ModelBackend.OLLAMA_7B,          # 降级5
    ],
    TaskPriority.P3_REPORT: [
        ModelBackend.QWEN3_CODER_FREE,   # 首选（免费优先）
        ModelBackend.MINIMAX_M21_FREE,   # 降级1：免费
        ModelBackend.OLLAMA_30B,         # 降级2：本地免费
        ModelBackend.OLLAMA_7B,          # 降级3：本地7B
        ModelBackend.QWEN36_API,         # 降级4：付费API仅在需要高质量报告时
    ],
    TaskPriority.P4_LOG: [
        ModelBackend.OLLAMA_30B,         # 首选（本地免费强力模型）
        ModelBackend.MINIMAX_M21_FREE,   # 降级1：免费API
        ModelBackend.OLLAMA_7B,          # 降级2：本地7B
        ModelBackend.OLLAMA_3B,          # 降级3：本地3B
    ],
    TaskPriority.P5_AUX: [
        ModelBackend.OLLAMA_15B,         # 首选（qwen3-coder:1.5b，本地免费，轻量优选）
        ModelBackend.OLLAMA_7B,          # 降级1：本地7B
        ModelBackend.OLLAMA_3B,          # 降级2：本地3B
        ModelBackend.OLLAMA_1B,          # 降级3（超轻量）
    ],
}


@dataclass
class RouterStats:
    """路由器统计"""
    total_requests: int = 0
    requests_by_priority: Dict[str, int] = field(default_factory=lambda: {p.value: 0 for p in TaskPriority})
    requests_by_backend: Dict[str, int] = field(default_factory=lambda: {b.value: 0 for b in ModelBackend})
    total_cost_estimated: float = 0.0
    total_cost_saved: float = 0.0  # 相比全部用DeepSeek Pro节省的费用
    degradation_count: int = 0     # 降级次数
    circuit_breaks: int = 0        # 熔断次数
    cache_hits: int = 0
    start_time: float = field(default_factory=time.time)
    last_request_time: Optional[float] = None


class AIOModelRouter:
    """
    AI模型智能路由器核心引擎
    统一入口：router.ask(prompt, priority, context)
    """

    def __init__(
        self,
        deepseek_client=None,      # DeepSeekClient 实例
        qwen_client=None,          # QwenClient 实例
        ollama_client=None,        # OllamaClient 实例
        enable_cache: bool = True,
        cache_ttl: int = 300,      # 缓存有效期（秒）
        enable_cost_tracking: bool = True,
    ):
        """
        初始化智能路由器

        Args:
            deepseek_client: DeepSeek客户端（支持Pro和Flash两个模型）
            qwen_client: Qwen3.6-Plus客户端
            ollama_client: Ollama本地客户端
            enable_cache: 启用结果缓存
            cache_ttl: 缓存有效期（秒）
            enable_cost_tracking: 启用费用追踪
        """
        self.deepseek = deepseek_client
        self.qwen = qwen_client
        self.ollama = ollama_client

        # 后端熔断器
        self.circuits: Dict[ModelBackend, BackendCircuit] = {
            b: BackendCircuit(backend=b) for b in ModelBackend
        }

        # 缓存
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # key→(timestamp, result)
        self._cache_lock = threading.Lock()

        # 统计
        self.enable_cost_tracking = enable_cost_tracking
        self.stats = RouterStats()

        # 线程安全
        self._lock = threading.Lock()

        # 后端健康状态
        self._backend_healthy: Dict[ModelBackend, bool] = {b: True for b in ModelBackend}

        logger.info("[Router] 智能路由器初始化完成")

    # ── 核心调用接口 ──

    def ask(
        self,
        prompt: str,
        priority: Optional[TaskPriority] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        force_backend: Optional[ModelBackend] = None,
        allow_degradation: bool = True,  # 是否允许降级
        task_type: str = "general_qa",
    ) -> Dict[str, Any]:
        """
        统一AI调用入口

        Args:
            prompt: 提问内容（当messages为None时使用）
            priority: 任务优先级（None则自动判断）
            messages: 完整消息列表（优先于prompt）
            system_prompt: 系统提示词
            max_tokens: 最大token数
            temperature: 温度
            force_backend: 强制使用指定后端（跳过优先级判断）
            allow_degradation: 是否允许降级（P0默认False）
            task_type: 任务类型标识

        Returns:
            {
                "content": "AI回复文本",
                "backend": "deepseek_pro",
                "priority": "P0",
                "latency_ms": 1234,
                "cost_estimated": 0.025,
                "degraded": False,
                "cached": False
            }
        """
        start_time = time.time()
        self.stats.total_requests += 1
        self.stats.last_request_time = start_time

        # 1. 确定优先级
        if priority is None:
            priority = self._classify_priority(prompt or str(messages))
        self.stats.requests_by_priority[priority.value] += 1

        # P0任务不允许降级
        if priority == TaskPriority.P0_CRITICAL:
            allow_degradation = False

        # 2. 确定后端链
        if force_backend:
            backend_chain = [force_backend]
        else:
            backend_chain = list(BACKEND_CHAIN.get(priority, [ModelBackend.OLLAMA_3B]))

        # 3. 检查缓存
        cache_key = self._make_cache_key(prompt, messages, system_prompt, max_tokens)
        if self.enable_cache:
            cached = self._cache_get(cache_key)
            if cached:
                self.stats.cache_hits += 1
                cached["_meta"]["cached"] = True
                cached["_meta"]["backend"] = "cache"
                cached["_meta"]["priority"] = priority.value
                cached["_meta"]["latency_ms"] = (time.time() - start_time) * 1000
                cached["_meta"]["cost_estimated"] = 0.0
                cached["_meta"]["degraded"] = False
                return cached

        # 4. 遍历后端链尝试调用
        call_result = None
        used_backend = None
        degraded = False
        backend_index = 0

        for i, backend in enumerate(backend_chain):
            if i > 0:
                degraded = True
                self.stats.degradation_count += 1

            # 检查熔断器
            circuit = self.circuits[backend]
            if not circuit.allow_request():
                logger.warning(f"[Router] 后端 {backend.value} 已熔断，跳过")
                self.stats.circuit_breaks += 1
                continue

            # 检查后端可用性
            if not self._is_backend_available(backend):
                logger.warning(f"[Router] 后端 {backend.value} 不可用，跳过")
                continue

            try:
                call_result = self._call_backend(
                    backend=backend,
                    prompt=prompt,
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    task_type=task_type,
                )
                circuit.record_success()
                used_backend = backend
                backend_index = i
                break
            except Exception as e:
                circuit.record_failure()
                logger.warning(f"[Router] 后端 {backend.value} 调用失败: {e}")
                continue

        # 5. 所有后端都失败
        if call_result is None:
            raise RuntimeError(
                f"[Router] 所有后端调用失败 (priority={priority.value}, "
                f"chain={[b.value for b in backend_chain]})"
            )

        # 6. 计算元数据
        latency_ms = (time.time() - start_time) * 1000
        cost = self._estimate_cost(used_backend, call_result.get("usage", {})) if self.enable_cost_tracking else 0.0
        saved = self._estimate_saved(priority, used_backend, call_result.get("usage", {})) if self.enable_cost_tracking else 0.0

        with self._lock:
            self.stats.requests_by_backend[used_backend.value] += 1
            self.stats.total_cost_estimated += cost
            self.stats.total_cost_saved += saved

        # 7. 封装返回
        result = {
            "content": self._extract_content(call_result),
            "_meta": {
                "backend": used_backend.value,
                "priority": priority.value,
                "latency_ms": round(latency_ms, 1),
                "cost_estimated": round(cost, 6),
                "cost_saved": round(saved, 6),
                "degraded": degraded,
                "degraded_from": backend_chain[0].value if degraded else None,
                "cached": False,
                "backend_index": backend_index,
                "total_backends_tried": backend_index + 1 if used_backend else len(backend_chain),
            },
            "_raw": call_result,
        }

        # 8. 写入缓存
        if self.enable_cache and len(result["content"]) > 0:
            self._cache_set(cache_key, result)

        return result

    # ── 优先级自动分类 ──

    def _classify_priority(self, text: str) -> TaskPriority:
        """根据文本内容自动判断任务优先级"""
        text_lower = text.lower()

        for priority, keywords in PRIORITY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return priority

        # 默认按复杂度和长度判断
        if len(text) > 2000:
            return TaskPriority.P3_REPORT
        elif len(text) > 500:
            return TaskPriority.P4_LOG
        else:
            return TaskPriority.P5_AUX

    # ── 后端调用 ──

    def _is_backend_available(self, backend: ModelBackend) -> bool:
        """检查后端是否可用"""
        if backend == ModelBackend.DEEPSEEK_PRO:
            return self.deepseek is not None
        elif backend == ModelBackend.DEEPSEEK_FLASH:
            return self.deepseek is not None
        elif backend == ModelBackend.QWEN36_API:
            return self.qwen is not None
        # 免费API后端（OpenRouter / MiniMax）— 始终可用，由具体客户端实现检查
        elif backend in [ModelBackend.QWEN3_CODER_FREE, ModelBackend.MINIMAX_M21_FREE]:
            return True  # 依赖 QwenClient 或独立 OpenRouter 调用
        # Ollama 后端
        elif backend in [
            ModelBackend.OLLAMA_30B,
            ModelBackend.OLLAMA_7B,
            ModelBackend.OLLAMA_3B,
            ModelBackend.OLLAMA_15B,
            ModelBackend.OLLAMA_1B,
            ModelBackend.OLLAMA_05B,
        ]:
            if self.ollama is None:
                return False
            return self.ollama.is_healthy()
        return False

    def _get_ollama_model_for_backend(self, backend: ModelBackend) -> str:
        """把后端枚举映射到Ollama模型名"""
        mapping = {
            ModelBackend.OLLAMA_30B: "qwen3-coder:30b",
            ModelBackend.OLLAMA_7B: "qwen2.5:7b-instruct",
            ModelBackend.OLLAMA_3B: "llama3.2:3b",
            ModelBackend.OLLAMA_15B: "qwen3-coder:1.5b",
            ModelBackend.OLLAMA_1B: "qwen:1.8b",
            ModelBackend.OLLAMA_05B: "qwen2.5:0.5b",
        }
        return mapping.get(backend, "llama3.2:3b")

    def _call_backend(
        self,
        backend: ModelBackend,
        prompt: str,
        messages: Optional[List[Dict[str, str]]],
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: float,
        task_type: str,
    ) -> Dict[str, Any]:
        """执行实际的后端调用"""
        # 构建消息
        if messages:
            msgs = list(messages)
        else:
            msgs = [{"role": "user", "content": prompt}]

        # DeepSeek 后端
        if backend in [ModelBackend.DEEPSEEK_PRO, ModelBackend.DEEPSEEK_FLASH]:
            if self.deepseek is None:
                raise RuntimeError("DeepSeek客户端未配置")
            model = "deepseek-v4-pro" if backend == ModelBackend.DEEPSEEK_PRO else "deepseek-v4-flash"
            return self.deepseek.chat(
                messages=msgs,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Qwen3.6+ API 后端
        elif backend == ModelBackend.QWEN36_API:
            if self.qwen is None:
                raise RuntimeError("Qwen客户端未配置")
            return self.qwen.chat(
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # OpenRouter 免费后端（Qwen3-Coder）
        elif backend == ModelBackend.QWEN3_CODER_FREE:
            return self._call_openrouter(
                messages=msgs,
                model="qwen/qwen3-coder",
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )

        # MiniMax-M2.1 免费后端
        elif backend == ModelBackend.MINIMAX_M21_FREE:
            return self._call_minimax(
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )

        # Ollama 后端（含30B、1.5B）
        elif backend in [
            ModelBackend.OLLAMA_30B,
            ModelBackend.OLLAMA_7B,
            ModelBackend.OLLAMA_3B,
            ModelBackend.OLLAMA_15B,
            ModelBackend.OLLAMA_1B,
            ModelBackend.OLLAMA_05B,
        ]:
            if self.ollama is None:
                raise RuntimeError("Ollama客户端未配置")
            model = self._get_ollama_model_for_backend(backend)
            return self.ollama.chat(
                messages=msgs,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt or self.ollama.get_system_prompt(task_type),
            )

        raise RuntimeError(f"未知后端: {backend}")

    def _call_openrouter(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        """通过 OpenRouter API 调用免费模型"""
        import os
        import requests
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY 未设置，无法使用免费后端")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _call_minimax(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        """通过 MiniMax API 调用 M2.1 免费模型"""
        import os
        import requests
        api_key = os.environ.get("MINIMAX_API_KEY", "")
        if not api_key:
            raise RuntimeError("MINIMAX_API_KEY 未设置，无法使用免费后端")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "minimax-m2.1",
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        resp = requests.post(
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── 内容提取 ──

    def _extract_content(self, result: Dict[str, Any]) -> str:
        """从各种格式的结果中提取文本内容"""
        # OpenAI格式
        if "choices" in result:
            choices = result["choices"]
            if choices and "message" in choices[0]:
                return choices[0]["message"].get("content", "")
            if choices and "text" in choices[0]:
                return choices[0]["text"]
        # Ollama格式
        if "message" in result:
            return result["message"].get("content", "")
        if "response" in result:
            return result["response"]
        # 兜底
        return str(result)

    # ── 成本估算 ──

    def _estimate_cost(self, backend: ModelBackend, usage: Dict[str, Any]) -> float:
        """估算本次调用成本（元）"""
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens == 0:
            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        cost_per_1k = MODEL_COST_PER_1K.get(backend, 0.0)
        return (total_tokens / 1000) * cost_per_1k

    def _estimate_saved(self, priority: TaskPriority, used_backend: ModelBackend, usage: Dict[str, Any]) -> float:
        """估算相比全部用DeepSeek Pro节省的费用"""
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens == 0:
            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        pro_cost = (total_tokens / 1000) * MODEL_COST_PER_1K[ModelBackend.DEEPSEEK_PRO]
        actual_cost = self._estimate_cost(used_backend, usage)
        return max(0, pro_cost - actual_cost)

    # ── 缓存 ──

    def _make_cache_key(self, prompt: str, messages: Optional[List], system_prompt: Optional[str], max_tokens: Optional[int]) -> str:
        """生成缓存键"""
        content = prompt or json.dumps(messages or [], ensure_ascii=False)
        raw = f"{content}|{system_prompt or ''}|{max_tokens or 0}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _cache_get(self, key: str) -> Optional[Dict]:
        """从缓存获取"""
        with self._cache_lock:
            if key in self._cache:
                ts, result = self._cache[key]
                if time.time() - ts < self.cache_ttl:
                    return dict(result)
                else:
                    del self._cache[key]
        return None

    def _cache_set(self, key: str, result: Dict):
        """写入缓存"""
        with self._cache_lock:
            self._cache[key] = (time.time(), dict(result))

    def clear_cache(self):
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()

    # ── 统计与监控 ──

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计"""
        with self._lock:
            uptime = time.time() - self.stats.start_time
            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self.stats.total_requests,
                "requests_by_priority": dict(self.stats.requests_by_priority),
                "requests_by_backend": dict(self.stats.requests_by_backend),
                "total_cost_estimated": round(self.stats.total_cost_estimated, 4),
                "total_cost_saved": round(self.stats.total_cost_saved, 4),
                "degradation_count": self.stats.degradation_count,
                "circuit_breaks": self.stats.circuit_breaks,
                "cache_hits": self.stats.cache_hits,
                "circuits": {b.value: c.state.value for b, c in self.circuits.items()},
                "daily_cost_projection": self._project_daily_cost(),
            }

    def _project_daily_cost(self) -> float:
        """预估每日费用"""
        uptime = max(time.time() - self.stats.start_time, 1)
        requests_per_day = (self.stats.total_requests / uptime) * 86400
        cost_per_request = self.stats.total_cost_estimated / max(self.stats.total_requests, 1)
        return round(requests_per_day * cost_per_request, 2)

    def get_model_distribution(self) -> Dict[str, float]:
        """获取模型使用分布（百分比）"""
        total = max(self.stats.total_requests, 1)
        return {
            b.value: round(self.stats.requests_by_backend.get(b.value, 0) / total * 100, 1)
            for b in ModelBackend
        }

    # ── 批量调用 ──

    def batch_ask(
        self,
        requests: List[Dict[str, Any]],
        default_priority: TaskPriority = TaskPriority.P4_LOG,
    ) -> List[Dict[str, Any]]:
        """
        批量调用（按优先级排序后依次执行）

        Args:
            requests: [{"prompt": "...", "priority": TaskPriority.P1_STRATEGY, ...}, ...]
            default_priority: 默认优先级

        Returns:
            结果列表（保持原顺序）
        """
        # 按优先级排序（P0最先）
        priority_order = {p: i for i, p in enumerate(TaskPriority)}
        indexed = list(enumerate(requests))
        indexed.sort(key=lambda x: priority_order.get(
            x[1].get("priority", default_priority), 99
        ))

        results = [None] * len(requests)
        for original_index, req in indexed:
            try:
                result = self.ask(
                    prompt=req.get("prompt", ""),
                    priority=req.get("priority", default_priority),
                    messages=req.get("messages"),
                    system_prompt=req.get("system_prompt"),
                    max_tokens=req.get("max_tokens"),
                    temperature=req.get("temperature", 0.7),
                    task_type=req.get("task_type", "general_qa"),
                )
                results[original_index] = {"success": True, "result": result}
            except Exception as e:
                results[original_index] = {"success": False, "error": str(e)}

        return results


# ── 快速工厂函数 ──
def create_model_router(
    deepseek_client=None,
    qwen_client=None,
    ollama_client=None,
) -> AIOModelRouter:
    """快速创建路由器实例"""
    # 尝试自动加载客户端
    if deepseek_client is None:
        try:
            from deepseek_client import DeepSeekClient
            import os
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if api_key:
                deepseek_client = DeepSeekClient(api_key)
                logger.info("[Router] DeepSeek客户端自动加载")
        except ImportError:
            logger.debug("[Router] DeepSeek客户端未安装")

    if qwen_client is None:
        try:
            from qwen_client import QwenClient
            import os
            api_key = os.environ.get("QWEN_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))
            if api_key:
                qwen_client = QwenClient(api_key)
                logger.info("[Router] Qwen客户端自动加载")
        except ImportError:
            logger.debug("[Router] Qwen客户端未安装")

    if ollama_client is None:
        try:
            from ollama_client import create_ollama_client
            ollama_client = create_ollama_client()
        except ImportError:
            logger.debug("[Router] Ollama客户端未安装")

    return AIOModelRouter(
        deepseek_client=deepseek_client,
        qwen_client=qwen_client,
        ollama_client=ollama_client,
    )


# ── 测试 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  AI模型智能路由器 测试")
    print("=" * 60)

    router = create_model_router()

    # 测试优先级分类
    test_prompts = [
        ("立即平仓所有BTC头寸", TaskPriority.P0_CRITICAL),
        ("分析当前市场的夏普比率并给出策略建议", TaskPriority.P1_STRATEGY),
        ("计算最近20日MACD指标", TaskPriority.P2_DATA),
        ("生成本周交易报告", TaskPriority.P3_REPORT),
        ("分析最近的系统错误日志", TaskPriority.P4_LOG),
        ("什么是量化交易？", TaskPriority.P5_AUX),
    ]

    print("\n→ 优先级自动分类测试:")
    all_correct = True
    for prompt, expected in test_prompts:
        classified = router._classify_priority(prompt)
        status = "✅" if classified == expected else "❌"
        if classified != expected:
            all_correct = False
        print(f"  {status} [{classified.value}] {prompt[:40]}...")

    print(f"\n分类准确性: {'全部正确' if all_correct else '存在错误'}")

    # 后端链
    print("\n→ 降级链:")
    for p in TaskPriority:
        chain = BACKEND_CHAIN[p]
        print(f"  {p.value}: {' → '.join([b.value for b in chain])}")

    # 成本对比
    print("\n→ 成本估算 (1000 tokens):")
    for b in ModelBackend:
        cost = MODEL_COST_PER_1K[b] * 1000  # 1000次调用
        print(f"  {b.value:20s}: ¥{cost:.4f}/千token")

    print("\n" + "=" * 60)