#!/usr/bin/env python3
"""
Aurora AI模型集成层 (Model Integration Layer)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
统一接口：对所有AI调用提供单一入口点
内部由 Smart Model Router 自动决策使用哪个后端

使用方式:
    from model_integration import ask_ai
    result = ask_ai("分析当前市场状态", priority="P1")
"""

import logging
import threading
from typing import Dict, Any, List, Optional, Union
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ── 全局单例 ──
_router = None
_router_lock = threading.Lock()
_initialized = False


def get_router():
    """获取/初始化全局路由器单例（懒加载）"""
    global _router, _initialized
    if _router is None:
        with _router_lock:
            if _router is None:
                from aio_model_router import create_model_router, AIOModelRouter
                _router = create_model_router()
                _initialized = True
                logger.info("[ModelIntegration] 路由器初始化完成")
    return _router


def init_router(
    deepseek_client=None,
    qwen_client=None,
    ollama_client=None,
    enable_cache: bool = True,
    cache_ttl: int = 300,
):
    """
    手动初始化路由器（可选，允许传入自定义客户端）

    Args:
        deepseek_client: DeepSeek客户端
        qwen_client: Qwen客户端
        ollama_client: Ollama客户端
        enable_cache: 启用缓存
        cache_ttl: 缓存TTL（秒）
    """
    global _router, _initialized
    from aio_model_router import AIOModelRouter

    with _router_lock:
        _router = AIOModelRouter(
            deepseek_client=deepseek_client,
            qwen_client=qwen_client,
            ollama_client=ollama_client,
            enable_cache=enable_cache,
            cache_ttl=cache_ttl,
        )
        _initialized = True
        logger.info("[ModelIntegration] 路由器手动初始化完成")


def reset_router():
    """重置路由器（用于测试或重新配置）"""
    global _router, _initialized
    with _router_lock:
        _router = None
        _initialized = False


# ── 快捷AI调用函数 ──

def ask_ai(
    prompt: str,
    priority: str = "P4",
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    task_type: str = "general_qa",
    allow_degradation: bool = True,
) -> Dict[str, Any]:
    """
    快捷AI调用 — 最简单的使用方式

    Args:
        prompt: 提问内容
        priority: 任务优先级 ("P0"~"P5")，默认P4
        system_prompt: 系统提示词
        max_tokens: 最大token数
        temperature: 温度
        task_type: 任务类型标识
        allow_degradation: 是否允许降级

    Returns:
        {
            "content": "AI回复",
            "_meta": {
                "backend": "ollama_3b",
                "priority": "P4",
                "latency_ms": 123,
                "cost_estimated": 0.0,
                ...
            }
        }
    """
    from aio_model_router import TaskPriority
    router = get_router()

    p = TaskPriority(f"P{priority}_CRITICAL") if priority == "P0" else TaskPriority(f"P{priority}_STRATEGY") if priority == "P1" else \
        TaskPriority(f"P{priority}_DATA") if priority == "P2" else TaskPriority(f"P{priority}_REPORT") if priority == "P3" else \
        TaskPriority(f"P{priority}_LOG") if priority == "P4" else TaskPriority(f"P{priority}_AUX") if priority == "P5" else None

    if p is None:
        # 自动分类
        return router.ask(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            task_type=task_type,
            allow_degradation=allow_degradation,
        )

    return router.ask(
        prompt=prompt,
        priority=p,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        task_type=task_type,
        allow_degradation=allow_degradation,
    )


def ask_trading(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    核心交易AI调用 — P0优先级，使用最强模型，不容降级
    用于：下单决策、止盈止损、一键清仓
    """
    return ask_ai(prompt, priority="P0", allow_degradation=False, task_type="strategy_analysis", **kwargs)


def ask_strategy(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    策略分析AI调用 — P1优先级，优先Flash，可降级
    用于：策略回测、因子分析、市场状态判断
    """
    return ask_ai(prompt, priority="P1", task_type="strategy_analysis", **kwargs)


def ask_data(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    数据解析AI调用 — P2优先级，优先API模型，可降级
    用于：技术指标计算、消息解析、数据清洗
    """
    return ask_ai(prompt, priority="P2", task_type="data_parsing", **kwargs)


def ask_report(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    报告生成AI调用 — P3优先级，优先本地大模型
    用于：交易报告、性能分析、复盘总结
    """
    return ask_ai(prompt, priority="P3", task_type="report_generation", **kwargs)


def ask_log(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    日志分析AI调用 — P4优先级，优先本地中模型
    用于：异常检测、健康诊断、日志分析
    """
    return ask_ai(prompt, priority="P4", task_type="log", **kwargs)


def ask_aux(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    辅助AI调用 — P5优先级，优先超轻量免费模型
    用于：简单问答、数据标签、文档辅助
    """
    return ask_ai(prompt, priority="P5", task_type="general_qa", **kwargs)


# ── 便捷函数：提取内容 ──

def ask_text(prompt: str, priority: str = "P4", **kwargs) -> str:
    """
    快捷AI调用 — 直接返回文本内容

    Returns:
        AI回复的纯文本
    """
    result = ask_ai(prompt, priority=priority, **kwargs)
    return result.get("content", "")


def ask_trading_text(prompt: str, **kwargs) -> str:
    """核心交易AI调用 — 直接返回文本"""
    return ask_text(prompt, priority="P0", task_type="strategy_analysis", **kwargs)


# ── 批量调用 ──

def batch_ask(
    prompts: List[str],
    priority: str = "P4",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    批量AI调用

    Args:
        prompts: 提问列表
        priority: 统一优先级

    Returns:
        [{"content": "...", "_meta": {...}}, ...]
    """
    results = []
    for prompt in prompts:
        try:
            result = ask_ai(prompt, priority=priority, **kwargs)
            results.append({"success": True, "result": result})
        except Exception as e:
            results.append({"success": False, "error": str(e), "prompt": prompt})
    return results


def batch_ask_text(prompts: List[str], priority: str = "P4", **kwargs) -> List[str]:
    """
    批量AI调用 — 直接返回文本列表
    """
    results = batch_ask(prompts, priority=priority, **kwargs)
    return [
        r.get("result", {}).get("content", "") if r.get("success") else f"[错误: {r.get('error', '')}]"
        for r in results
    ]


# ── 状态查询 ──

def get_router_stats() -> Dict[str, Any]:
    """获取路由器统计信息"""
    router = get_router()
    return router.get_stats() if router else {"error": "路由器未初始化"}


def get_model_distribution() -> Dict[str, float]:
    """获取各模型使用分布"""
    router = get_router()
    return router.get_model_distribution() if router else {}


def get_health_status() -> Dict[str, Any]:
    """获取AI服务健康状态"""
    router = get_router()
    if not router:
        return {"status": "uninitialized"}

    return {
        "router_initialized": _initialized,
        "backends": {
            "deepseek_pro": router._is_backend_available("deepseek_pro"),
            "deepseek_flash": router._is_backend_available("deepseek_flash"),
            "qwen36_api": router._is_backend_available("qwen36_api"),
            "ollama_7b": router._is_backend_available("ollama_7b"),
            "ollama_3b": router._is_backend_available("ollama_3b"),
            "ollama_1b": router._is_backend_available("ollama_1b"),
            "ollama_05b": router._is_backend_available("ollama_05b"),
        },
        "circuits": {b.value: c.state.value for b, c in router.circuits.items()},
        "cost_saved": round(router.stats.total_cost_saved, 4),
        "cost_estimated": round(router.stats.total_cost_estimated, 4),
    }


def print_status():
    """打印AI服务完整状态"""
    print("=" * 60)
    print("  Aurora AI模型服务状态")
    print("=" * 60)

    status = get_health_status()
    print(f"\n  路由器状态: {'✅ 已初始化' if status.get('router_initialized') else '❌ 未初始化'}")
    print(f"  累计节省费用: ¥{status.get('cost_saved', 0):.4f}")
    print(f"  累计实际费用: ¥{status.get('cost_estimated', 0):.4f}")

    print("\n  → 后端可用性:")
    for name, available in status.get("backends", {}).items():
        icon = "✅" if available else "❌"
        print(f"    {icon} {name}")

    print("\n  → 熔断器状态:")
    for name, state in status.get("circuits", {}).items():
        state_icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(state, "⚪")
        print(f"    {state_icon} {name}: {state}")

    # 详细统计
    stats = get_router_stats()
    if "total_requests" in stats:
        print(f"\n  → 请求统计:")
        print(f"    总请求数: {stats['total_requests']}")
        print(f"    缓存命中: {stats.get('cache_hits', 0)}")
        print(f"    降级次数: {stats.get('degradation_count', 0)}")
        print(f"    熔断次数: {stats.get('circuit_breaks', 0)}")
        print(f"    预计日费: ¥{stats.get('daily_cost_projection', 0)}")

        print(f"\n  → 模型分布:")
        dist = get_model_distribution()
        for model, pct in dist.items():
            bar = "█" * int(pct / 5)
            print(f"    {model:20s}: {pct:5.1f}% {bar}")

    print("\n" + "=" * 60)


# ── 上下文管理器：临时强制后端 ──

@contextmanager
def force_backend(backend_name: str):
    """
    临时强制使用指定后端

    Usage:
        with force_backend("ollama_7b"):
            result = ask_ai("重要但可本地处理的任务")
    """
    # 这是简化的上下文管理器，实际force_backend在ask()层处理
    # 此处提供便捷语法糖
    from aio_model_router import ModelBackend

    backend_map = {
        "deepseek_pro": ModelBackend.DEEPSEEK_PRO,
        "deepseek_flash": ModelBackend.DEEPSEEK_FLASH,
        "qwen36_api": ModelBackend.QWEN36_API,
        "ollama_7b": ModelBackend.OLLAMA_7B,
        "ollama_3b": ModelBackend.OLLAMA_3B,
        "ollama_1b": ModelBackend.OLLAMA_1B,
        "ollama_05b": ModelBackend.OLLAMA_05B,
    }

    backend = backend_map.get(backend_name)
    if backend is None:
        raise ValueError(f"未知后端: {backend_name}，可选: {list(backend_map.keys())}")

    # 这里简化实现 — 通过环境变量传递
    import os
    old_backend = os.environ.get("AURORA_FORCE_BACKEND")
    os.environ["AURORA_FORCE_BACKEND"] = backend.value
    try:
        yield
    finally:
        if old_backend:
            os.environ["AURORA_FORCE_BACKEND"] = old_backend
        else:
            os.environ.pop("AURORA_FORCE_BACKEND", None)


# ── 命令行测试 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print_status()

    # 测试调用
    print("\n→ 测试 ask_aux (Ollama本地):")
    try:
        result = ask_aux("一句话介绍量化交易")
        print(f"  回复: {result.get('content', 'N/A')[:100]}")
        print(f"  后端: {result.get('_meta', {}).get('backend', 'unknown')}")
        print(f"  延迟: {result.get('_meta', {}).get('latency_ms', 0)}ms")
        print(f"  费用: ¥{result.get('_meta', {}).get('cost_estimated', 0)}")
    except Exception as e:
        print(f"  测试失败: {e}")

    print("\n→ 测试 ask_text:")
    try:
        text = ask_text("什么是MACD?", priority="P5")
        print(f"  回复: {text[:100]}")
    except Exception as e:
        print(f"  测试失败: {e}")