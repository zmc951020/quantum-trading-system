"""L6 AI智能体检查"""
import os
import sys
from typing import List, Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l6_checks(hc) -> List[Callable]:
    def _l6_001():
        """LLM管理器（合并L6_001+L6_005，quick=模型列表/deep=+配置）"""
        ok, d = hc._api_get("/api/llm/models", timeout=3)
        models = d.get("data", {}).get("models", [])
        config_ok = True
        if hc.mode == "deep":
            config_ok, _ = hc._api_get("/api/llm/config")
        has_llm = ok and len(models) > 0
        return (True, 100 if has_llm else 75,
                f"LLM: {len(models)}个模型, 配置={'✓' if config_ok else '✗'}",
                "" if has_llm else "LLM服务未启动（Ollama），功能降级运行")
    yield ("L6_001", "LLM管理器", "L6_AI智能体", "warning", "both", _l6_001)

    def _l6_002():
        ok, d = hc._api_post("/api/vibe/analyze", {"symbol": "000001"})
        return (True, 100 if ok else 70, f"Vibe分析: {'通过' if ok else 'LLM不可用，降级运行'}", "")
    yield ("L6_002", "Vibe分析端点", "L6_AI智能体", "warning", "both", _l6_002)

    def _l6_003():
        ok, d = hc._api_post("/api/deepseek/chat", {"message": "你好", "history": []}, timeout=3)
        return (True, 100 if ok else 70, f"智能体对话: {'通过' if ok else 'LLM不可用，降级运行'}", "")
    yield ("L6_003", "智能体对话", "L6_AI智能体", "warning", "both", _l6_003)

    # 深度扩展
    def _l6_004():
        ok, d = hc._api_post("/api/vibe/29_agents_vote", {"symbol": "000001"})
        return (True, 100 if ok else 70, f"29智能体投票: {'通过' if ok else 'LLM不可用，降级运行'}", "")
    yield ("L6_004", "29智能体投票", "L6_AI智能体", "info", "deep", _l6_004)

    # 新增：智能体注册表API
    def _l6_005():
        ok, d = hc._api_get("/api/agent/registry")
        registry = d.get("registry", {})
        agents = registry.get("agents", {})
        return (ok and len(agents) > 0, 100 if ok and len(agents) > 0 else 0,
                f"智能体注册表: {len(agents)}个Agent" if ok and len(agents) > 0 else "智能体注册表为空",
                "" if ok else "检查 /api/agent/registry 端点")
    yield ("L6_005", "智能体注册表API", "L6_AI智能体", "warning", "both", _l6_005)

    # 新增：智能体调度降级
    def _l6_006():
        ok, d = hc._api_post("/api/agent/dispatch", {"message": "分析600519"}, timeout=15)
        degraded = d.get("degraded", False)
        has_subtasks = len(d.get("sub_tasks", [])) > 0
        return (ok and (degraded or has_subtasks), 100 if ok else 0,
                f"调度降级: degraded={degraded}, sub_tasks={len(d.get('sub_tasks', []))}" if ok else "调度失败",
                "" if ok else "检查 core/agent_orchestrator.py")
    yield ("L6_006", "智能体调度降级", "L6_AI智能体", "warning", "both", _l6_006)