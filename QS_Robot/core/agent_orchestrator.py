#!/usr/bin/env python3
"""
Agent智能编排引擎（Agent Orchestrator）

让Cline自主理解任务意图，自动分解子任务，智能分配Agent/Skill执行。

核心能力：
  1. 任务意图识别 → 分析用户消息，判断任务类型
  2. 子任务分解 → 将复杂任务拆解为可并行执行的子任务
  3. 智能Agent分配 → 为每个子任务自动匹配最合适的Agent/技能
  4. 编排执行 → 分层并行执行，聚合结果
  5. 工作流可视化 → 输出清晰的任务执行流程

任务类型映射：
  - 市场分析/行情研判 → 技术分析组 + 基本面分析组 + 舆情分析组
  - 风险评估/风控检查 → 风控组 + 交易专家团
  - 策略评估/策略优化 → 策略研究组 + 交易专家团 + 专家评审组
  - 系统审查/架构审计 → 专家评审组（全部12位）
  - 代码开发/调试 → Trae-cn开发工具
  - 综合诊断/全面分析 → 所有相关分组
"""

import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple

from core.agent_registry import (
    get_agent, get_agents_by_group, get_skills_by_category,
    get_all_agents, AgentInfo, SkillInfo,
)

logger = logging.getLogger(__name__)


# ============================================================
# 任务意图定义
# ============================================================

class TaskIntent:
    """任务意图"""
    def __init__(self):
        self.task_type: str = ""          # 任务类型
        self.sub_tasks: List[SubTask] = []  # 子任务列表
        self.priority_groups: List[str] = []  # 优先分组
        self.supplementary_groups: List[str] = []  # 补充分组
        self.suggested_skills: List[str] = []  # 建议技能


class SubTask:
    """子任务"""
    def __init__(self, name: str, description: str,
                 groups: List[str] = None, skills: List[str] = None,
                 priority: int = 5):
        self.name = name
        self.description = description
        self.groups = groups or []
        self.skills = skills or []
        self.priority = priority  # 1-10，越高越优先
        self.result: Optional[Dict] = None


# ============================================================
# 任务类型 → 分组/技能映射
# ============================================================

# 关键词 → 任务类型映射
TASK_TYPE_KEYWORDS = {
    "市场分析": [
        "分析", "研判", "走势", "行情", "涨跌", "趋势", "方向",
        "看涨", "看跌", "后市", "预测", "判断", "展望",
    ],
    "风险评估": [
        "风险", "风控", "回撤", "亏损", "止损", "安全", "波动",
        "最大回撤", "VaR", "敞口", "仓位", "杠杆",
    ],
    "策略评估": [
        "策略", "优化", "回测", "参数", "表现", "收益", "夏普",
        "胜率", "评估", "改进", "调优", "增强",
    ],
    "系统审查": [
        "架构", "审查", "审计", "代码", "质量", "安全审计",
        "性能", "可扩展", "部署", "运维", "测试",
    ],
    "开发任务": [
        "开发", "写代码", "生成", "文档", "测试", "调试",
        "debug", "修复", "bug", "报错", "异常", "简化",
        "重构", "提交", "commit", "PR",
    ],
    "综合诊断": [
        "全面", "综合", "诊断", "体检", "全量", "健康", "检查",
        "完整", "整体", "系统",
    ],
}


def identify_task_type(message: str) -> Tuple[str, float]:
    """识别任务类型，返回 (类型, 置信度)"""
    msg = message.lower()
    scores = {}

    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in msg:
                score += 1
        if score > 0:
            scores[task_type] = score

    if not scores:
        return "市场分析", 0.5  # 默认

    # 选择最高分
    best_type = max(scores, key=scores.get)
    max_score = scores[best_type]
    confidence = min(1.0, max_score / max(3, sum(scores.values()) * 0.5))

    return best_type, confidence


def decompose_task(message: str, task_type: str) -> TaskIntent:
    """根据任务类型分解子任务"""
    intent = TaskIntent()
    intent.task_type = task_type
    msg = message.lower()

    if task_type == "市场分析":
        intent.priority_groups = ["技术分析组"]
        intent.supplementary_groups = ["基本面分析组", "舆情分析组"]
        intent.sub_tasks = [
            SubTask("技术面分析", "K线形态、均线趋势、MACD/RSI/布林带等技术指标",
                    groups=["技术分析组"], priority=10),
            SubTask("资金面分析", "成交量、资金流向、北向资金、量价关系",
                    groups=["舆情分析组"], priority=8),
            SubTask("基本面评估", "估值、成长性、盈利能力、现金流",
                    groups=["基本面分析组"], priority=7),
            SubTask("综合研判", "汇总各维度分析，给出最终判断",
                    groups=["辅助决策组"], priority=5),
        ]
        intent.suggested_skills = ["macd", "rsi_14", "bollinger", "ma20", "ma60",
                                    "volume_anomaly_detect", "money_flow_indicator"]

    elif task_type == "风险评估":
        intent.priority_groups = ["风控组"]
        intent.supplementary_groups = ["交易专家团"]
        intent.sub_tasks = [
            SubTask("风险指标计算", "VaR、最大回撤、波动率、Beta",
                    groups=["风控组"], priority=10),
            SubTask("风控合规审查", "止损止盈规则、仓位管理、合规边界",
                    groups=["交易专家团"], priority=9),
            SubTask("仓位建议", "凯利公式、风险预算、最优仓位",
                    groups=["风控组"], priority=8),
            SubTask("风险汇总", "综合风险评估与建议",
                    groups=["风控组"], priority=6),
        ]
        intent.suggested_skills = ["risk_metrics", "position_sizing", "stop_loss_atr"]

    elif task_type == "策略评估":
        intent.priority_groups = ["策略研究组"]
        intent.supplementary_groups = ["交易专家团", "专家评审组"]
        intent.sub_tasks = [
            SubTask("策略算法评审", "收益优化、夏普比率、策略逻辑",
                    groups=["策略研究组", "交易专家团"], priority=10),
            SubTask("风控合规审查", "回撤、VaR、风险敞口",
                    groups=["交易专家团"], priority=9),
            SubTask("代码质量审查", "代码规范、性能、安全性",
                    groups=["专家评审组"], priority=8),
            SubTask("策略优化建议", "参数调优、逻辑改进、迭代方向",
                    groups=["策略研究组", "专家评审组"], priority=7),
        ]
        intent.suggested_skills = ["risk_metrics", "position_sizing"]

    elif task_type == "系统审查":
        intent.priority_groups = ["专家评审组"]
        intent.supplementary_groups = []
        intent.sub_tasks = [
            SubTask("架构审查", "模块职责划分、耦合度、扩展性",
                    groups=["专家评审组"], priority=10),
            SubTask("代码审查", "规范性、安全性、可维护性",
                    groups=["专家评审组"], priority=9),
            SubTask("安全审计", "鉴权、密钥、注入防御、依赖安全",
                    groups=["专家评审组"], priority=9),
            SubTask("性能评估", "延迟、吞吐量、资源占用",
                    groups=["专家评审组"], priority=7),
            SubTask("测试覆盖", "单元测试、集成测试、边界测试",
                    groups=["专家评审组"], priority=6),
        ]
        intent.suggested_skills = []

    elif task_type == "开发任务":
        intent.priority_groups = []
        intent.supplementary_groups = ["专家评审组"]
        intent.sub_tasks = [
            SubTask("代码开发/调试", "定位问题、修复代码、简化逻辑",
                    skills=["trae_debugger", "trae_code_simplifier",
                            "trae_auto_resolver"], priority=10),
            SubTask("代码审查", "审查修改质量，检查安全问题",
                    skills=["trae_code_reviewer", "trae_pr_code_review",
                            "trae_security_review"], priority=8),
            SubTask("测试验证", "生成测试用例，验证覆盖率",
                    skills=["trae_unit_test_gen", "trae_test_engineer"], priority=7),
            SubTask("文档更新", "更新README、API文档",
                    skills=["trae_doc_writer"], priority=5),
            SubTask("Git提交", "生成Conventional Commits提交信息",
                    skills=["trae_git_commit_gen"], priority=4),
        ]
        intent.suggested_skills = []

    elif task_type == "综合诊断":
        intent.priority_groups = ["技术分析组", "风控组", "策略研究组"]
        intent.supplementary_groups = ["基本面分析组", "舆情分析组",
                                        "专家评审组", "交易专家团"]
        intent.sub_tasks = [
            SubTask("技术面诊断", "趋势、动量、形态、量能全面分析",
                    groups=["技术分析组"], priority=10),
            SubTask("基本面诊断", "估值、成长、盈利、现金流",
                    groups=["基本面分析组"], priority=8),
            SubTask("风控诊断", "风险指标、仓位管理、止损建议",
                    groups=["风控组", "交易专家团"], priority=9),
            SubTask("策略诊断", "策略表现、优化空间、改进方向",
                    groups=["策略研究组"], priority=7),
            SubTask("系统诊断", "架构、性能、安全、测试",
                    groups=["专家评审组"], priority=6),
            SubTask("综合报告", "全维度汇总与最终建议",
                    groups=["辅助决策组"], priority=5),
        ]
        intent.suggested_skills = []

    return intent


# ============================================================
# 智能编排执行器
# ============================================================

class AgentOrchestrator:
    """Agent智能编排引擎

    使用方式：
        orchestrator = AgentOrchestrator()
        result = orchestrator.orchestrate("全面分析600519的市场风险")

    编排流程：
        1. 识别任务类型
        2. 分解子任务
        3. 为每个子任务分配Agent
        4. 并行执行子任务
        5. 聚合结果生成报告
    """

    def __init__(self, dispatcher=None):
        self.dispatcher = dispatcher  # 可注入AgentDispatcher实例
        self._executor = ThreadPoolExecutor(max_workers=10)

    def orchestrate(self, message: str, symbol: str = None,
                    kline_data: Dict = None) -> Dict[str, Any]:
        """智能编排入口"""
        start_time = time.time()

        try:
            # 1. 提取股票代码
            if not symbol:
                symbol_match = re.search(r'(\d{6})', message)
                if symbol_match:
                    symbol = symbol_match.group(1)

            # 2. 识别任务类型
            task_type, confidence = identify_task_type(message)
            logger.info(f"编排: 任务类型={task_type}, 置信度={confidence:.0%}")

            # 3. 分解子任务
            intent = decompose_task(message, task_type)

            # 4. 为每个子任务分配Agent
            sub_task_results = []
            for st in intent.sub_tasks:
                assigned_agents = self._assign_agents_for_subtask(st)
                assigned_skills = st.skills if st.skills else intent.suggested_skills
                sub_task_results.append({
                    "name": st.name,
                    "description": st.description,
                    "priority": st.priority,
                    "assigned_agents": [a.agent_id for a in assigned_agents],
                    "assigned_skills": assigned_skills,
                    "result": None,
                })

            # 5. 并行执行子任务
            if symbol:
                kline = kline_data or self._fetch_kline(symbol)
                with ThreadPoolExecutor(max_workers=min(len(intent.sub_tasks), 5)) as executor:
                    futures = {}
                    for i, st in enumerate(intent.sub_tasks):
                        agents = self._assign_agents_for_subtask(st)
                        skills = st.skills if st.skills else intent.suggested_skills
                        future = executor.submit(
                            self._execute_subtask, st, agents, skills, symbol, kline
                        )
                        futures[future] = i

                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            result = future.result(timeout=60)
                            sub_task_results[idx]["result"] = result
                        except Exception as e:
                            sub_task_results[idx]["result"] = {"error": str(e)}

            # 6. 聚合结果
            orchestration_result = self._aggregate_orchestration(
                message, symbol, task_type, confidence, intent, sub_task_results,
                time.time() - start_time
            )

            return orchestration_result

        except Exception as e:
            import traceback
            logger.error(f"编排失败: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "elapsed_ms": round((time.time() - start_time) * 1000, 0),
            }

    def _assign_agents_for_subtask(self, subtask: SubTask) -> List[AgentInfo]:
        """为子任务分配Agent"""
        agents = []
        seen = set()

        # 按分组分配
        for gid in subtask.groups:
            for a in get_agents_by_group(gid):
                if a.agent_id not in seen:
                    agents.append(a)
                    seen.add(a.agent_id)

        # 如果子任务指定了技能但没有分组，使用技能对应的Agent
        if not agents and subtask.skills:
            # 技能通常由Agent间接执行，这里返回空让调用方处理
            pass

        return agents

    def _execute_subtask(self, subtask: SubTask, agents: List[AgentInfo],
                         skills: List[str], symbol: str,
                         kline_data: Dict) -> Dict[str, Any]:
        """执行单个子任务"""
        results = {}

        if agents:
            # 使用Agent执行
            from core.vibe_29_agents import VibeAgentAnalyzer
            from core.expert_team_bridge import ExpertTeamAnalyzer

            vibe_analyzer = VibeAgentAnalyzer(symbol, kline_data)
            expert_analyzer = ExpertTeamAnalyzer(symbol, kline_data)
            expert_groups = {"专家评审组", "交易专家团"}

            for agent in agents:
                try:
                    if agent.group in expert_groups:
                        method = getattr(expert_analyzer, agent.method_name, None)
                    else:
                        method = getattr(vibe_analyzer, agent.method_name, None)
                    if method:
                        result = method()
                        results[agent.agent_id] = {
                            "agent_name": agent.name,
                            "group": agent.group,
                            "result": result,
                        }
                except Exception as e:
                    results[agent.agent_id] = {
                        "agent_name": agent.name,
                        "error": str(e),
                    }

        if skills:
            # 使用技能执行
            from core.expert_team_bridge import ExpertTeamAnalyzer
            from core.agent_registry import get_skill

            expert_analyzer = ExpertTeamAnalyzer(symbol, kline_data)
            for sid in skills:
                try:
                    skill = get_skill(sid)
                    if skill:
                        if skill.module == "expert_team_bridge":
                            method = getattr(expert_analyzer, skill.method_name, None)
                            if method:
                                results[sid] = {"skill_name": skill.name, "result": method()}
                        elif skill.module == "technical_analysis":
                            from core.technical_analysis import TechnicalAnalysisEngine
                            tech = TechnicalAnalysisEngine()
                            closes = kline_data.get("closes", [])
                            if closes:
                                indicator = tech.calculate_indicator(closes, skill.params.get("indicator", ""))
                                results[sid] = {"skill_name": skill.name,
                                                "value": indicator.values[-1] if indicator.values else None}
                except Exception as e:
                    results[sid] = {"skill_name": sid, "error": str(e)}

        return {
            "subtask": subtask.name,
            "agent_count": len(agents),
            "skill_count": len(skills),
            "results": results,
        }

    def _fetch_kline(self, symbol: str) -> Dict:
        """获取K线数据"""
        try:
            from core.market_data import MarketDataProvider
            provider = MarketDataProvider()
            return provider.get_kline(symbol, days=60)
        except Exception:
            return {"closes": [], "opens": [], "highs": [], "lows": [], "volumes": []}

    def _aggregate_orchestration(self, message: str, symbol: str,
                                  task_type: str, confidence: float,
                                  intent: TaskIntent,
                                  sub_task_results: List[Dict],
                                  elapsed: float) -> Dict[str, Any]:
        """聚合编排结果"""
        completed = sum(1 for s in sub_task_results if s["result"] and "error" not in str(s["result"]))
        failed = sum(1 for s in sub_task_results if s["result"] and "error" in str(s["result"]))
        pending = len(sub_task_results) - completed - failed

        # 计算总体评分
        total_score = 0
        score_count = 0
        for st in sub_task_results:
            if st["result"]:
                for rid, rdata in st["result"].get("results", {}).items():
                    res = rdata.get("result", {})
                    if isinstance(res, dict) and "score" in res:
                        total_score += res["score"]
                        score_count += 1

        avg_score = round(total_score / max(1, score_count), 1)

        return {
            "success": True,
            "symbol": symbol,
            "message": message,
            "task_type": task_type,
            "confidence": round(confidence * 100, 0),
            "mode": "auto",
            "sub_tasks": sub_task_results,
            "summary": {
                "total_sub_tasks": len(sub_task_results),
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "avg_score": avg_score,
                "priority_groups": intent.priority_groups,
                "supplementary_groups": intent.supplementary_groups,
            },
            "elapsed_ms": round(elapsed * 1000, 0),
        }


# ============================================================
# 便捷API
# ============================================================

# 全局编排器实例
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """获取全局编排器"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def orchestrate(message: str, symbol: str = None,
                kline_data: Dict = None) -> Dict[str, Any]:
    """便捷编排函数"""
    return get_orchestrator().orchestrate(message, symbol, kline_data)