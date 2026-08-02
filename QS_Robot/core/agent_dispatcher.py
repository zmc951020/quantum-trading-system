#!/usr/bin/env python3
"""
Agent自由调度引擎（Agent Dispatcher）

5级粒度调度：
  粒度1: 单Agent调度 → "调用趋势智能体分析600519"
  粒度2: 组调度 → "调用技术分析组分析600519"
  粒度3: 技能调度 → "对600519计算MACD+RSI+布林带"
  粒度4: 辩论调度 → "让技术分析组和风控组辩论600519"
  粒度5: 自由组合 → "趋势+动量+成交量异动，排除宏观，分析600519"

核心能力：
  1. 自然语言解析 → 提取Agent/技能/股票代码
  2. 智能匹配 → 模糊匹配Agent名+技能名
  3. 并行执行 → 多Agent并行调度
  4. 辩论模式 → 多方vs空方辩论
  5. 结果聚合 → 加权投票+综合评分
"""

import os
import sys
import re
import time
import hashlib
import json as json_module
import threading
import logging
from enum import Enum
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple

from core.agent_registry import (
    AGENT_REGISTRY, SKILL_REGISTRY,
    get_agent, get_agents_by_group, get_agents_by_tags, get_agents_by_keyword,
    get_skill, get_skills_by_category, get_skills_by_tags, get_skills_by_keyword,
    get_all_groups, get_all_agents, get_all_categories, get_all_skills,
    get_registry_stats, AgentInfo, SkillInfo,
)

logger = logging.getLogger(__name__)


# ============================================================
# 自然语言解析
# ============================================================

class DispatchIntent:
    """调度意图"""
    def __init__(self):
        self.symbol: Optional[str] = None
        self.agent_ids: List[str] = []         # 指定的Agent ID列表
        self.group_ids: List[str] = []          # 指定的分组
        self.exclude_agent_ids: List[str] = []  # 排除的Agent
        self.skill_ids: List[str] = []          # 指定的技能
        self.mode: str = "vote"                 # vote / debate / skill_only / full
        self.raw_message: str = ""


def parse_dispatch(message: str) -> DispatchIntent:
    """解析自然语言调度指令

    支持的语法：
      - "分析600519" → 全量投票
      - "用趋势智能体分析600519" → 单Agent
      - "用技术分析组分析600519" → 组调度
      - "让趋势组和风控组辩论600519" → 辩论
      - "趋势+动量+成交量分析600519" → 自由组合
      - "对600519计算MACD+RSI+布林带" → 技能调度
      - "全部Agent分析600519，排除宏观" → 排除模式
    """
    intent = DispatchIntent()
    intent.raw_message = message
    msg = message.lower().strip()

    # 1. 提取股票代码（6位数字）
    symbol_match = re.search(r'(\d{6})', message)
    if symbol_match:
        intent.symbol = symbol_match.group(1)

    # 2. 检测辩论模式
    debate_keywords = ['辩论', '对辩', '多方空方', '多头空头', '多方vs空方']
    if any(kw in msg for kw in debate_keywords):
        intent.mode = "debate"

    # 3. 检测技能调度模式
    skill_keywords = ['计算', '指标', '技能', '技术指标', '因子']
    if any(kw in msg for kw in skill_keywords) and not intent.mode == "debate":
        intent.mode = "skill_only"

    # 4. 检测排除关键词
    exclude_match = re.search(r'排除[：:\s]*([^，,。.]+)', msg)
    if not exclude_match:
        exclude_match = re.search(r'不要[：:\s]*([^，,。.]+)', msg)
    if not exclude_match:
        exclude_match = re.search(r'去掉[：:\s]*([^，,。.]+)', msg)

    exclude_terms = []
    if exclude_match:
        exclude_terms = [t.strip() for t in re.split(r'[、，,]+', exclude_match.group(1))]

    # 5. 匹配分组（优先，独立于Agent匹配）
    all_groups = get_all_groups()
    for g in all_groups:
        if g.lower() in msg:
            intent.group_ids.append(g)

    # 6. 匹配具体Agent（仅在未指定分组时，或作为补充）
    if not intent.group_ids:
        matched_agents = _match_agents_from_message(message, exclude_terms)
        if matched_agents:
            intent.agent_ids = [a.agent_id for a in matched_agents]

    # 7. 匹配技能
    if intent.mode == "skill_only" or skill_keywords:
        matched_skills = _match_skills_from_message(message)
        intent.skill_ids = [s.skill_id for s in matched_skills]

    # 7. 排除Agent
    if exclude_terms:
        for term in exclude_terms:
            found = get_agents_by_keyword(term)
            for a in found:
                if a.agent_id not in intent.exclude_agent_ids:
                    intent.exclude_agent_ids.append(a.agent_id)

    return intent


def _match_agents_from_message(message: str, exclude_terms: List[str] = None) -> List[AgentInfo]:
    """从消息中匹配Agent"""
    msg = message.lower()
    matched = []

    # 直接匹配Agent名称（支持部分匹配）
    for agent_id, agent in AGENT_REGISTRY.items():
        # 检查名称中的关键词是否在消息中
        name_parts = [agent.name.replace("智能体", ""), agent.name]
        if any(part.lower() in msg for part in name_parts) or agent_id.lower() in msg:
            if exclude_terms and any(et.lower() in agent.name.lower() for et in exclude_terms):
                continue
            matched.append(agent)

    # 标签匹配
    if not matched:
        for agent_id, agent in AGENT_REGISTRY.items():
            for tag in agent.tags:
                if tag.lower() in msg:
                    if exclude_terms and any(et.lower() in agent.name.lower() for et in exclude_terms):
                        continue
                    matched.append(agent)
                    break

    return matched


def _has_explicit_agent_name(message: str) -> bool:
    """检查用户是否明确指定了Agent名称（而非仅用通用关键词）"""
    msg = message.lower()
    # 通用词黑名单，这些词即使匹配Agent名称也不算显式指定
    generic_words = {"分析", "评估", "审查", "检查", "审计", "诊断", "检测",
                     "交易", "策略", "系统", "数据", "风险", "安全", "测试",
                     "性能", "代码", "质量", "架构", "部署", "运维", "开发",
                     "监控", "配置", "管理", "优化", "资金", "市场", "行业"}
    for agent_id, agent in AGENT_REGISTRY.items():
        # 去掉"智能体"和"(Trae)"后缀
        name_core = agent.name.replace("智能体", "").replace("(Trae)", "")
        # 核心名匹配（>=2字符，如"趋势"、"动量"）
        if len(name_core) >= 2 and name_core.lower() in msg:
            if name_core not in generic_words:
                return True
        # ID匹配
        if agent_id.lower() in msg:
            return True
    return False


def _match_skills_from_message(message: str) -> List[SkillInfo]:
    """从消息中匹配技能"""
    msg = message.lower()
    matched = []

    for skill_id, skill in SKILL_REGISTRY.items():
        if skill_id.lower() in msg or skill.name.lower() in msg:
            matched.append(skill)
            continue
        for tag in skill.tags:
            if tag.lower() in msg:
                matched.append(skill)
                break

    return matched


# ============================================================
# 调度执行引擎
# ============================================================

class AgentDispatcher:
    """Agent自由调度引擎

    使用方式：
        dispatcher = AgentDispatcher()
        result = dispatcher.dispatch("用趋势和动量分析600519")
        # 或
        result = dispatcher.dispatch("让技术分析组和风控组辩论600519")
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._lock = threading.Lock()

    def dispatch(self, message: str) -> Dict[str, Any]:
        """主调度入口：自然语言 → Agent执行 → 结果聚合

        当未指定具体Agent/分组时，自动触发智能编排模式，
        由编排引擎识别任务意图、分解子任务、智能分配Agent。
        """
        start_time = time.time()

        try:
            # 1. 解析意图
            intent = parse_dispatch(message)

            if not intent.symbol:
                return {
                    "success": False,
                    "error": "未检测到股票代码，请提供6位数字代码（如：600519）",
                    "intent": {"mode": intent.mode, "agent_ids": intent.agent_ids},
                    "elapsed_ms": round((time.time() - start_time) * 1000, 0),
                }

            # 2. 确定要执行的Agent列表
            agents_to_run = self._resolve_agents(intent)

            # 3. 智能编排：未指定Agent/分组时，自动识别任务意图并分配
            # 如果用户没有明确指定Agent名称，即使标签匹配到了一些Agent/Skill，
            # 也应该触发智能编排，让系统自动选择最合适的Agent组合
            has_explicit_agent = _has_explicit_agent_name(message)
            if not has_explicit_agent and not intent.group_ids:
                logger.info(f"未指定Agent/分组，触发智能编排: {message}")
                from core.agent_orchestrator import orchestrate
                return orchestrate(message, intent.symbol)

            if not agents_to_run:
                return {
                    "success": False,
                    "error": "未匹配到任何Agent，请重新描述需求",
                    "intent": {"mode": intent.mode, "agent_ids": intent.agent_ids},
                    "elapsed_ms": round((time.time() - start_time) * 1000, 0),
                }

            # 3. 获取K线数据
            kline_data = self._fetch_kline(intent.symbol)

            # 4. 按模式执行
            if intent.mode == "debate":
                result = self._execute_debate(intent, agents_to_run, kline_data)
            elif intent.mode == "skill_only":
                result = self._execute_skills(intent, kline_data)
            else:
                result = self._execute_agents(intent, agents_to_run, kline_data)

            # 5. 聚合元数据
            result["success"] = True
            result["symbol"] = intent.symbol
            result["mode"] = intent.mode
            result["agents_executed"] = [a.agent_id for a in agents_to_run]
            result["agents_count"] = len(agents_to_run)
            result["elapsed_ms"] = round((time.time() - start_time) * 1000, 0)

            return result

        except Exception as e:
            import traceback
            logger.error(f"Agent调度失败: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "elapsed_ms": round((time.time() - start_time) * 1000, 0),
            }

    def _resolve_agents(self, intent: DispatchIntent) -> List[AgentInfo]:
        """解析要执行的Agent列表"""
        agents = []

        # 方式1: 指定了分组
        if intent.group_ids:
            for gid in intent.group_ids:
                agents.extend(get_agents_by_group(gid))

        # 方式2: 指定了具体Agent
        if intent.agent_ids:
            for aid in intent.agent_ids:
                a = get_agent(aid)
                if a and a not in agents:
                    agents.append(a)

        # 方式3: 都没指定 → 全部Agent
        if not agents:
            agents = get_all_agents()

        # 去重 + 排除
        seen = set()
        result = []
        for a in agents:
            if a.agent_id in seen:
                continue
            if a.agent_id in intent.exclude_agent_ids:
                continue
            seen.add(a.agent_id)
            result.append(a)

        return result

    def _fetch_kline(self, symbol: str) -> Dict:
        """获取K线数据"""
        try:
            from core.data_fetcher import UnifiedDataFetcher
            fetcher = UnifiedDataFetcher()
            return fetcher.get_kline_data(symbol, days=250)
        except Exception as e:
            logger.warning(f"数据获取降级: {e}")
            return {"closes": [], "opens": [], "highs": [], "lows": [], "volumes": []}

    def _execute_agents(self, intent: DispatchIntent, agents: List[AgentInfo],
                        kline_data: Dict) -> Dict[str, Any]:
        """并行执行多个Agent（支持Vibe Agent + 专家团队）"""
        from core.vibe_29_agents import VibeAgentAnalyzer
        from core.expert_team_bridge import ExpertTeamAnalyzer

        vibe_analyzer = VibeAgentAnalyzer(intent.symbol, kline_data)
        expert_analyzer = ExpertTeamAnalyzer(intent.symbol, kline_data)
        results = {}

        expert_groups = {"专家评审组", "交易专家团"}

        with ThreadPoolExecutor(max_workers=min(len(agents), 10)) as executor:
            futures = {}
            for agent in agents:
                if agent.group in expert_groups:
                    method = getattr(expert_analyzer, agent.method_name, None)
                else:
                    method = getattr(vibe_analyzer, agent.method_name, None)
                if method:
                    futures[executor.submit(method)] = agent

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    result = future.result(timeout=30)
                    results[agent.agent_id] = {
                        "agent_name": agent.name,
                        "group": agent.group,
                        "result": result,
                    }
                except Exception as e:
                    results[agent.agent_id] = {
                        "agent_name": agent.name,
                        "group": agent.group,
                        "error": str(e),
                    }

        # 聚合统计
        return self._aggregate_results(results, intent.symbol)

    def _execute_debate(self, intent: DispatchIntent, agents: List[AgentInfo],
                        kline_data: Dict) -> Dict[str, Any]:
        """执行辩论模式"""
        from core.vibe_29_agents import VibeAgentAnalyzer

        analyzer = VibeAgentAnalyzer(intent.symbol, kline_data)
        try:
            debate_result = analyzer.debate()
            return {
                "debate": debate_result,
                "verdict": debate_result.get("final_vote", {}).get("verdict", "未知"),
                "weighted_score": debate_result.get("weighted_score", 50),
            }
        except Exception as e:
            logger.error(f"辩论执行失败: {e}")
            return {"error": str(e), "debate": None}

    def _execute_skills(self, intent: DispatchIntent, kline_data: Dict) -> Dict[str, Any]:
        """执行技能模式（技术指标 + Trae-cn开发工具）"""
        if not intent.skill_ids:
            return {"error": "未指定技能", "skills": {}}

        results = {}
        closes = kline_data.get("closes", [])
        volumes = kline_data.get("volumes", [])

        # 初始化引擎（按需）
        tech = None
        factor = None
        expert_analyzer = None

        for sid in intent.skill_ids:
            skill = get_skill(sid)
            if not skill:
                continue

            try:
                # Trae-cn 开发工具类技能
                if skill.module == "expert_team_bridge":
                    if expert_analyzer is None:
                        from core.expert_team_bridge import ExpertTeamAnalyzer
                        expert_analyzer = ExpertTeamAnalyzer(intent.symbol, kline_data)
                    method = getattr(expert_analyzer, skill.method_name, None)
                    if method:
                        result = method()
                        results[sid] = {"name": skill.name, "result": result}
                    else:
                        results[sid] = {"name": skill.name, "note": "技能方法未实现"}

                # 技术分析类技能
                elif skill.module == "technical_analysis":
                    if tech is None:
                        from core.technical_analysis import TechnicalAnalysisEngine, FactorAnalysisEngine
                        tech = TechnicalAnalysisEngine()
                        factor = FactorAnalysisEngine()
                    if not closes:
                        results[sid] = {"name": skill.name, "error": "无K线数据"}
                        continue
                    if skill.method_name == "calculate_factor":
                        val = factor.calculate_factor(intent.symbol, closes, volumes)
                        results[sid] = {"name": skill.name, "value": val.get(skill.params.get("factor", ""), 0)}
                    else:
                        indicator = tech.calculate_indicator(closes, skill.params.get("indicator", ""))
                        results[sid] = {"name": skill.name, "value": indicator.values[-1] if indicator.values else None}

                else:
                    results[sid] = {"name": skill.name, "note": "需Agent执行"}
            except Exception as e:
                results[sid] = {"name": skill.name, "error": str(e)}

        return {"skills": results, "skill_count": len(results)}

    def _aggregate_results(self, agent_results: Dict, symbol: str) -> Dict[str, Any]:
        """聚合Agent结果"""
        scores = []
        votes = {"买入": 0, "卖出": 0, "观望": 0}
        group_summary = {}

        for agent_id, data in agent_results.items():
            result = data.get("result", {})
            score = result.get("score", 50)
            vote = result.get("vote", "观望")
            group = data.get("group", "未知")

            scores.append(score)
            votes.setdefault(vote, 0)
            votes[vote] += 1

            group_summary.setdefault(group, {"scores": [], "buy": 0, "sell": 0, "hold": 0})
            group_summary[group]["scores"].append(score)
            if vote == "买入":
                group_summary[group]["buy"] += 1
            elif vote == "卖出":
                group_summary[group]["sell"] += 1
            else:
                group_summary[group]["hold"] += 1

        # 计算组平均
        for g, gs in group_summary.items():
            gs["avg_score"] = round(sum(gs["scores"]) / len(gs["scores"]), 1) if gs["scores"] else 50
            del gs["scores"]

        avg_score = round(sum(scores) / len(scores), 1) if scores else 50
        total = sum(votes.values())
        buy_pct = round(votes.get("买入", 0) / total * 100, 1) if total > 0 else 0
        sell_pct = round(votes.get("卖出", 0) / total * 100, 1) if total > 0 else 0

        # 最终决策
        if buy_pct > 50:
            final_verdict = "强烈买入"
        elif buy_pct > sell_pct and avg_score >= 60:
            final_verdict = "谨慎买入"
        elif sell_pct > 50:
            final_verdict = "强烈卖出"
        elif sell_pct > buy_pct and avg_score < 50:
            final_verdict = "建议卖出"
        else:
            final_verdict = "观望"

        return {
            "agent_results": agent_results,
            "summary": {
                "avg_score": avg_score,
                "votes": votes,
                "buy_pct": buy_pct,
                "sell_pct": sell_pct,
                "final_verdict": final_verdict,
            },
            "group_summary": group_summary,
        }


# ============================================================
# 任务管理器（TaskManager）— 资源限流、优先级、环境隔离、审计
# ============================================================


class TaskPriority(Enum):
    """任务优先级：数值越小优先级越高"""
    LIVE_TRADING = 1       # 实盘交易监控
    RISK_CONTROL = 2       # 盘中风控校验
    SIGNAL_CALC = 3        # 策略实时信号
    CLINE_DEV = 4          # Cline代码开发
    BATCH_BACKTEST = 5     # 批量回测/参数优化


class TaskEnvironment(Enum):
    """运行环境"""
    SIMULATION = "simulation"   # 模拟环境：全功能开放
    LIVE = "live"              # 实盘环境：受限操作


class TaskStatus(Enum):
    """任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """单个任务"""
    def __init__(self, task_id: str, message: str, priority: TaskPriority,
                 environment: TaskEnvironment, user: str = "anonymous",
                 symbol: str = None):
        self.task_id = task_id
        self.message = message
        self.priority = priority
        self.environment = environment
        self.user = user
        self.symbol = symbol
        self.status = TaskStatus.QUEUED
        self.result: Optional[Dict] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.audit_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "message": self.message,
            "priority": self.priority.name,
            "environment": self.environment.value,
            "user": self.user,
            "symbol": self.symbol,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_ms": round((self.completed_at - self.started_at) * 1000, 0) if self.started_at and self.completed_at else None,
            "error": self.error,
            "audit_hash": self.audit_hash,
        }


class TaskManager:
    """统一任务管理器 — 替代原5002的所有中转、限流、调度功能

    职责：
      1. 任务队列 + 优先级排序
      2. 资源限流（并发数、数据读取并发）
      3. 环境隔离（模拟/实盘分离）
      4. 业务规则校验（实盘高风险操作拦截）
      5. 操作审计日志（不可篡改）
      6. 故障熔断（超时检测、自动重试）
    """

    # 高风险操作关键词（实盘环境禁止）
    LIVE_RESTRICTED_KEYWORDS = [
        "批量下单", "全量重优化", "全市场回测", "批量修改策略",
        "一键部署", "自动交易", "全量参数重优化", "批量调参",
        "删除策略", "删除所有", "清空配置",
    ]

    # 并发限制
    MAX_CONCURRENT_TASKS = 10
    MAX_CONCURRENT_LIVE_TASKS = 3
    MAX_DATA_READ_CONCURRENCY = 5
    TASK_TIMEOUT_SECONDS = 300  # 5分钟超时

    def __init__(self):
        self._task_queue: deque = deque()
        self._running_tasks: Dict[str, Task] = {}
        self._completed_tasks: Dict[str, Task] = {}
        self._audit_log: List[Dict] = []
        self._lock = threading.Lock()
        self._data_read_semaphore = threading.Semaphore(self.MAX_DATA_READ_CONCURRENCY)
        self._task_counter = 0
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT_TASKS)

        # 任务变更回调（供前端轮询/推送）
        self._status_callbacks: List[callable] = []

    def _generate_task_id(self) -> str:
        """生成唯一任务ID"""
        self._task_counter += 1
        ts = int(time.time() * 1000)
        return f"task_{ts}_{self._task_counter}"

    def _generate_audit_hash(self, task: Task) -> str:
        """生成审计哈希（不可篡改）"""
        data = f"{task.task_id}|{task.user}|{task.message}|{task.environment.value}|{task.created_at}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def submit_task(self, message: str, priority: TaskPriority = TaskPriority.CLINE_DEV,
                    environment: TaskEnvironment = TaskEnvironment.SIMULATION,
                    user: str = "anonymous", symbol: str = None,
                    auto_start: bool = True) -> Dict[str, Any]:
        """提交任务到队列

        Args:
            message: 任务描述
            priority: 优先级
            environment: 环境（模拟/实盘）
            user: 操作用户
            symbol: 关联股票代码
            auto_start: 是否自动开始执行

        Returns:
            {"success": bool, "task_id": str, "message": str}
        """
        # 业务规则校验
        validation = self._validate_task(message, environment)
        if not validation["allowed"]:
            logger.warning(f"任务被拦截: {validation['reason']}")
            return {"success": False, "error": validation["reason"], "blocked": True}

        task_id = self._generate_task_id()
        task = Task(task_id, message, priority, environment, user, symbol)
        task.audit_hash = self._generate_audit_hash(task)

        with self._lock:
            self._task_queue.append(task)
            # 按优先级排序
            self._task_queue = deque(sorted(self._task_queue, key=lambda t: t.priority.value))

        # 审计日志
        self._log_audit("TASK_SUBMIT", task, {"message": message})

        if auto_start:
            self._try_start_next()

        return {
            "success": True,
            "task_id": task_id,
            "priority": priority.name,
            "environment": environment.value,
            "queue_position": self._get_queue_position(task_id),
        }

    def _validate_task(self, message: str, environment: TaskEnvironment) -> Dict[str, Any]:
        """业务规则校验"""
        msg_lower = message.lower()

        # 实盘环境高风险操作拦截
        if environment == TaskEnvironment.LIVE:
            for kw in self.LIVE_RESTRICTED_KEYWORDS:
                if kw in msg_lower:
                    return {
                        "allowed": False,
                        "reason": f"实盘环境禁止执行高风险操作: '{kw}'。请切换到模拟环境或联系管理员审批。"
                    }

        # 并发限制检查
        live_count = sum(1 for t in self._running_tasks.values()
                        if t.environment == TaskEnvironment.LIVE)
        total_count = len(self._running_tasks)

        if environment == TaskEnvironment.LIVE and live_count >= self.MAX_CONCURRENT_LIVE_TASKS:
            return {
                "allowed": False,
                "reason": f"实盘并发任务已达上限({self.MAX_CONCURRENT_LIVE_TASKS})，请等待当前任务完成"
            }

        if total_count >= self.MAX_CONCURRENT_TASKS:
            return {
                "allowed": False,
                "reason": f"系统并发任务已达上限({self.MAX_CONCURRENT_TASKS})，请等待"
            }

        return {"allowed": True}

    def _try_start_next(self):
        """尝试启动下一个排队任务"""
        with self._lock:
            if not self._task_queue:
                return

            # 检查并发限制
            live_count = sum(1 for t in self._running_tasks.values()
                           if t.environment == TaskEnvironment.LIVE)
            total_count = len(self._running_tasks)

            if total_count >= self.MAX_CONCURRENT_TASKS:
                return

            # 取下一个任务
            task = self._task_queue.popleft()

            # 实盘额外限制
            if task.environment == TaskEnvironment.LIVE and live_count >= self.MAX_CONCURRENT_LIVE_TASKS:
                self._task_queue.appendleft(task)  # 放回队列
                return

            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self._running_tasks[task.task_id] = task

        # 异步执行
        self._executor.submit(self._execute_task, task)

    def _execute_task(self, task: Task):
        """执行任务（子线程）"""
        self._log_audit("TASK_START", task)
        self._notify_status_change()

        try:
            # 超时控制
            future = self._executor.submit(self._run_task_core, task)
            result = future.result(timeout=self.TASK_TIMEOUT_SECONDS)
            task.result = result
            task.status = TaskStatus.COMPLETED
        except TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"任务超时({self.TASK_TIMEOUT_SECONDS}s)"
            logger.error(f"任务超时: {task.task_id}")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"任务执行失败: {task.task_id} - {e}")

        task.completed_at = time.time()

        with self._lock:
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]
            self._completed_tasks[task.task_id] = task

        self._log_audit("TASK_END", task, {
            "status": task.status.value,
            "elapsed_ms": round((task.completed_at - task.started_at) * 1000, 0) if task.started_at else None,
        })
        self._notify_status_change()

        # 启动下一个任务
        self._try_start_next()

    def _run_task_core(self, task: Task):
        """任务核心执行逻辑"""
        dispatcher = get_dispatcher()
        return dispatcher.dispatch(task.message)

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """取消任务"""
        with self._lock:
            # 检查运行中
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                del self._running_tasks[task_id]
                self._completed_tasks[task_id] = task
                self._log_audit("TASK_CANCEL", task)
                self._notify_status_change()
                return {"success": True, "message": "任务已取消"}

            # 检查排队中
            for i, t in enumerate(self._task_queue):
                if t.task_id == task_id:
                    self._task_queue.remove(t)
                    t.status = TaskStatus.CANCELLED
                    self._completed_tasks[task_id] = t
                    self._log_audit("TASK_CANCEL", t)
                    return {"success": True, "message": "排队任务已取消"}

        return {"success": False, "error": "任务不存在或已完成"}

    def get_task_status(self, task_id: str = None) -> Dict[str, Any]:
        """获取任务状态"""
        if task_id:
            for d in [self._running_tasks, self._completed_tasks]:
                if task_id in d:
                    return d[task_id].to_dict()
            for t in self._task_queue:
                if t.task_id == task_id:
                    return t.to_dict()
            return {"error": "任务不存在"}

        with self._lock:
            return {
                "queued": [t.to_dict() for t in self._task_queue],
                "running": [t.to_dict() for t in self._running_tasks.values()],
                "completed": [t.to_dict() for t in list(self._completed_tasks.values())[-20:]],
                "stats": {
                    "total_queued": len(self._task_queue),
                    "total_running": len(self._running_tasks),
                    "total_completed": len(self._completed_tasks),
                    "max_concurrent": self.MAX_CONCURRENT_TASKS,
                    "max_live_concurrent": self.MAX_CONCURRENT_LIVE_TASKS,
                }
            }

    def _get_queue_position(self, task_id: str) -> int:
        """获取排队位置"""
        for i, t in enumerate(self._task_queue):
            if t.task_id == task_id:
                return i + 1
        return 0

    def _log_audit(self, action: str, task: Task, extra: Dict = None):
        """记录审计日志"""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "task_id": task.task_id if task else "N/A",
            "user": task.user if task else "system",
            "environment": task.environment.value if task else "N/A",
            "message": (task.message[:200] if task else action),
            "symbol": task.symbol if task else None,
            "audit_hash": task.audit_hash if task else None,
            "extra": extra or {},
        }
        with self._lock:
            self._audit_log.append(entry)
            # 保留最近 1000 条
            if len(self._audit_log) > 1000:
                self._audit_log = self._audit_log[-1000:]

        # 写入持久化审计文件
        try:
            audit_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      "logs", "cline_audit.jsonl")
            os.makedirs(os.path.dirname(audit_file), exist_ok=True)
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json_module.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"审计日志写入失败: {e}")

    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        """获取审计日志"""
        with self._lock:
            return self._audit_log[-limit:]

    def _notify_status_change(self):
        """通知状态变更"""
        for cb in self._status_callbacks:
            try:
                cb()
            except Exception:
                pass

    def register_status_callback(self, callback: callable):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)


# 全局任务管理器
_task_manager: Optional[TaskManager] = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    """获取全局任务管理器"""
    global _task_manager
    if _task_manager is None:
        with _task_manager_lock:
            if _task_manager is None:
                _task_manager = TaskManager()
    return _task_manager


# ============================================================
# 便捷API
# ============================================================

# 全局单例
_dispatcher: Optional[AgentDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_dispatcher() -> AgentDispatcher:
    """获取全局调度器单例"""
    global _dispatcher
    if _dispatcher is None:
        with _dispatcher_lock:
            if _dispatcher is None:
                _dispatcher = AgentDispatcher()
    return _dispatcher


def dispatch(message: str) -> Dict[str, Any]:
    """便捷调度函数"""
    return get_dispatcher().dispatch(message)


def get_registry() -> Dict[str, Any]:
    """获取完整的Agent+技能注册表（供前端面板使用）"""
    return {
        "agents": [
            {
                "id": a.agent_id,
                "name": a.name,
                "group": a.group,
                "description": a.description,
                "tags": a.tags,
                "dependencies": a.dependencies,
            }
            for a in get_all_agents()
        ],
        "groups": get_all_groups(),
        "skills": [
            {
                "id": s.skill_id,
                "name": s.name,
                "category": s.category,
                "description": s.description,
                "tags": s.tags,
                "usage_scenario": s.usage_scenario,
                "params": s.params,
            }
            for s in get_all_skills()
        ],
        "categories": get_all_categories(),
        "stats": get_registry_stats(),
    }