#!/usr/bin/env python3
"""
NLP自然语言指令解析器 - 港大Vibe-Trading智能体调度入口

功能：
  1. 自然语言指令解析（中文/英文）
  2. 意图识别（分析/优化/回测/交易/扫描/查询）
  3. 意图→技能映射（映射到29个智能体/策略/优化器）
  4. 错配检测（意图无对应技能时给出提示）

设计依据：
  审计报告D1维度 - NLP解析/技能匹配/错配检测三项缺失
  采用关键词+规则引擎混合方案，轻量级、可解释、无外部依赖
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# 数据结构
# ============================================================


@dataclass
class ParsedIntent:
    """解析后的意图结构"""
    raw_text: str                          # 原始输入
    intent_type: str = ""                  # 意图类型
    target_symbols: List[str] = field(default_factory=list)   # 目标股票代码
    target_strategies: List[str] = field(default_factory=list) # 目标策略
    params: Dict[str, Any] = field(default_factory=dict)       # 提取的参数
    confidence: float = 0.0                # 置信度 0-1
    matched_skills: List[str] = field(default_factory=list)    # 匹配的技能
    mismatches: List[str] = field(default_factory=list)        # 错配警告
    suggestions: List[str] = field(default_factory=list)       # 建议


# ============================================================
# 意图类型定义
# ============================================================

INTENT_TYPES = {
    "analyze": {
        "keywords": ["分析", "评估", "诊断", "怎么看", "走势", "analyze", "evaluate", "diagnose"],
        "description": "分析股票/市场走势",
        "required_params": ["symbol"],
        "skills": [
            "trend", "momentum", "pattern", "volume", "volatility",
            "support_resistance", "multi_period", "valuation", "financial",
            "industry", "macro", "policy", "growth", "news_sentiment",
            "social_media", "money_flow", "market_sentiment", "sector_rotation",
            "risk_assessment", "black_swan", "coordinator"
        ]
    },
    "optimize": {
        "keywords": ["优化", "调参", "寻优", "超参数", "参数搜索", "optimize", "tune", "hyperparameter"],
        "description": "优化策略参数",
        "required_params": ["strategy"],
        "skills": [
            "tau_optimizer_cluster", "special_forces_evolution",
            "strategy_builder", "backtest_validator"
        ]
    },
    "backtest": {
        "keywords": ["回测", "回溯", "历史测试", "backtest", "back_test", "historical"],
        "description": "回测策略/参数",
        "required_params": ["strategy"],
        "skills": [
            "backtest_engine", "backtest_validator", "performance_attribution",
            "cross_engine_validator"
        ]
    },
    "trade": {
        "keywords": ["交易", "买入", "卖出", "下单", "开仓", "平仓", "trade", "buy", "sell", "order"],
        "description": "执行交易操作",
        "required_params": ["symbol"],
        "skills": [
            "execution", "position_management", "stop_loss",
            "risk_assessment", "coordinator"
        ]
    },
    "scan": {
        "keywords": ["扫描", "筛选", "选股", "海选", "股票池", "scan", "screen", "filter", "stock_pool"],
        "description": "扫描/筛选股票池",
        "required_params": [],
        "skills": [
            "sector_rotation", "money_flow", "volume_anomaly",
            "market_sentiment", "growth", "valuation"
        ]
    },
    "query": {
        "keywords": ["查询", "状态", "持仓", "盈亏", "收益", "query", "status", "position", "pnl", "profit"],
        "description": "查询系统状态/持仓/盈亏",
        "required_params": [],
        "skills": [
            "performance_attribution", "risk_assessment",
            "position_management", "pnl_learner"
        ]
    },
    "config": {
        "keywords": ["配置", "设置", "参数", "阈", "config", "setting", "threshold"],
        "description": "系统配置管理",
        "required_params": [],
        "skills": ["config_manager"]
    },
    "help": {
        "keywords": ["帮助", "help", "?", "？", "怎么用", "使用说明"],
        "description": "获取帮助信息",
        "required_params": [],
        "skills": []
    }
}

# ============================================================
# 可用技能注册表（与实际模块映射）
# ============================================================

SKILL_REGISTRY = {
    # 29个智能体
    "trend": {"module": "core.vibe_29_agents", "method": "trend_agent", "category": "技术分析"},
    "momentum": {"module": "core.vibe_29_agents", "method": "momentum_agent", "category": "技术分析"},
    "pattern": {"module": "core.vibe_29_agents", "method": "pattern_agent", "category": "技术分析"},
    "volume": {"module": "core.vibe_29_agents", "method": "volume_agent", "category": "技术分析"},
    "volume_anomaly": {"module": "core.vibe_29_agents", "method": "volume_anomaly_agent", "category": "技术分析"},
    "volatility": {"module": "core.vibe_29_agents", "method": "volatility_agent", "category": "技术分析"},
    "support_resistance": {"module": "core.vibe_29_agents", "method": "support_resistance_agent", "category": "技术分析"},
    "multi_period": {"module": "core.vibe_29_agents", "method": "multi_period_agent", "category": "技术分析"},
    "money_flow": {"module": "core.vibe_29_agents", "method": "money_flow_agent", "category": "资金流向"},
    "valuation": {"module": "core.vibe_29_agents", "method": "valuation_agent", "category": "基本面"},
    "financial": {"module": "core.vibe_29_agents", "method": "financial_agent", "category": "基本面"},
    "industry": {"module": "core.vibe_29_agents", "method": "industry_agent", "category": "行业"},
    "macro": {"module": "core.vibe_29_agents", "method": "macro_agent", "category": "宏观"},
    "policy": {"module": "core.vibe_29_agents", "method": "policy_agent", "category": "宏观"},
    "growth": {"module": "core.vibe_29_agents", "method": "growth_agent", "category": "基本面"},
    "news_sentiment": {"module": "core.vibe_29_agents", "method": "news_sentiment_agent", "category": "舆情"},
    "social_media": {"module": "core.vibe_29_agents", "method": "social_media_agent", "category": "舆情"},
    "market_sentiment": {"module": "core.vibe_29_agents", "method": "market_sentiment_agent", "category": "市场情绪"},
    "sector_rotation": {"module": "core.vibe_29_agents", "method": "sector_rotation_agent", "category": "行业轮动"},
    "risk_assessment": {"module": "core.vibe_29_agents", "method": "risk_assessment_agent", "category": "风控"},
    "position_management": {"module": "core.vibe_29_agents", "method": "position_management_agent", "category": "风控"},
    "stop_loss": {"module": "core.vibe_29_agents", "method": "stop_loss_agent", "category": "风控"},
    "black_swan": {"module": "core.vibe_29_agents", "method": "black_swan_agent", "category": "风控"},
    "strategy_builder": {"module": "core.vibe_29_agents", "method": "strategy_builder_agent", "category": "策略"},
    "backtest_validator": {"module": "core.vibe_29_agents", "method": "backtest_validator_agent", "category": "策略"},
    "execution": {"module": "core.vibe_29_agents", "method": "execution_agent", "category": "交易"},
    "performance_attribution": {"module": "core.vibe_29_agents", "method": "performance_attribution_agent", "category": "归因"},
    "coordinator": {"module": "core.vibe_29_agents", "method": "coordinator_agent", "category": "调度"},
    "conflict_detector": {"module": "core.vibe_29_agents", "method": "conflict_detector_agent", "category": "调度"},
    # 优化器
    "tau_optimizer_cluster": {"module": "core.tau_optimizer_cluster", "method": "optimize", "category": "优化器"},
    "special_forces_evolution": {"module": "core.special_forces_evolution", "method": "evolve", "category": "优化器"},
    # 回测引擎
    "backtest_engine": {"module": "core.backtest_engine", "method": "run_backtest", "category": "回测"},
    "cross_engine_validator": {"module": "core.cross_engine_validator", "method": "validate", "category": "回测"},
    # 学习模块
    "pnl_learner": {"module": "core.pnl_learner", "method": "learn_from_trades", "category": "学习"},
    # 配置
    "config_manager": {"module": "config.config", "method": "reload", "category": "系统"},
}

# 可用技能名称列表
AVAILABLE_SKILLS = list(SKILL_REGISTRY.keys())

# 可用策略名称（从策略管理器动态获取，此处为静态fallback）
KNOWN_STRATEGIES = [
    "陀螺仪", "gyro", "GyroStrategy",
    "伯努利康达", "bernoulli_conda", "BernoulliCondaStrategy",
    "智能标的轮动", "shepherd", "ShepherdStrategy",
    "网格交易", "grid", "GridStrategy",
    "多因子共振", "multi_factor", "MultiFactorStrategy",
    "自适应", "adaptive", "AdaptiveStrategy",
    "特种兵", "special_forces", "SpecialForcesStrategy",
    "威科夫", "wyckoff", "WyckoffStrategy",
    "均值回归", "mean_reversion",
    "趋势跟踪", "trend_following",
    "动量", "momentum",
]

# 已知股票代码映射
KNOWN_SYMBOLS = {
    "贵州茅台": "600519", "茅台": "600519",
    "沪深300": "510300", "沪深300ETF": "510300",
    "上证50": "510050", "上证50ETF": "510050",
    "中证500": "510500", "中证500ETF": "510500",
    "创业板": "159915", "创业板ETF": "159915",
    "科创50": "588000", "科创50ETF": "588000",
    "宁德时代": "300750", "宁德": "300750",
    "比亚迪": "002594",
    "招商银行": "600036", "招行": "600036",
    "中国平安": "601318", "平安": "601318",
    "五粮液": "000858",
    "隆基绿能": "601012", "隆基": "601012",
}


# ============================================================
# NLP解析器
# ============================================================

class NLPCommander:
    """自然语言指令解析器

    解析用户输入的自然语言指令，识别意图、提取参数、匹配技能，
    并检测错配情况。

    使用示例:
        >>> cmd = NLPCommander()
        >>> result = cmd.parse("分析贵州茅台")
        >>> print(result.intent_type)  # "analyze"
        >>> print(result.target_symbols)  # ["600519"]
    """

    def __init__(self):
        self._stock_code_pattern = re.compile(r'(?<![0-9])(\d{6})(?![0-9])')
        self._strategy_patterns = self._build_strategy_patterns()

    def _build_strategy_patterns(self) -> Dict[str, re.Pattern]:
        """构建策略名匹配模式"""
        patterns = {}
        for s in KNOWN_STRATEGIES:
            if len(s) > 2:
                patterns[s] = re.compile(re.escape(s), re.IGNORECASE)
        return patterns

    def parse(self, text: str) -> ParsedIntent:
        """解析自然语言指令

        Args:
            text: 用户输入的自然语言指令

        Returns:
            ParsedIntent: 解析结果
        """
        if not text or not text.strip():
            return ParsedIntent(
                raw_text=text or "",
                intent_type="help",
                confidence=0.0,
                suggestions=["请输入有效指令，输入「帮助」查看可用命令"]
            )

        text = text.strip()
        intent = ParsedIntent(raw_text=text)

        # 1. 识别意图类型
        intent_type, confidence = self._recognize_intent(text)
        intent.intent_type = intent_type
        intent.confidence = confidence

        # 2. 提取股票代码
        intent.target_symbols = self._extract_symbols(text)

        # 3. 提取策略名
        intent.target_strategies = self._extract_strategies(text)

        # 4. 提取参数
        intent.params = self._extract_params(text)

        # 5. 匹配技能
        intent.matched_skills = self._match_skills(intent_type, intent.params)

        # 6. 错配检测
        intent.mismatches, intent.suggestions = self._detect_mismatches(intent)

        # 7. 低置信度补充建议
        if confidence < 0.4:
            intent.suggestions.append(
                f"意图识别置信度较低({confidence:.0%})，请使用更明确的关键词。"
                f"可用意图类型: {', '.join(INTENT_TYPES.keys())}"
            )

        return intent

    def _recognize_intent(self, text: str) -> Tuple[str, float]:
        """识别意图类型（关键词匹配 + 规则）"""
        text_lower = text.lower()
        scores = {}

        for intent_type, config in INTENT_TYPES.items():
            score = 0
            for kw in config["keywords"]:
                if kw.lower() in text_lower:
                    # 关键词越长，权重越高
                    score += len(kw) * 0.5
            scores[intent_type] = score

        if not scores or max(scores.values()) == 0:
            return "help", 0.0

        # 取最高分
        best = max(scores, key=scores.get)
        max_score = scores[best]
        total_score = sum(scores.values()) or 1
        confidence = min(max_score / max(total_score, 1), 1.0)

        return best, confidence

    def _extract_symbols(self, text: str) -> List[str]:
        """提取股票代码（6位数字 + 中文名称映射）"""
        symbols = []

        # 6位数字代码
        matches = self._stock_code_pattern.findall(text)
        symbols.extend(matches)

        # 中文名称映射
        for name, code in KNOWN_SYMBOLS.items():
            if name in text:
                if code not in symbols:
                    symbols.append(code)

        return symbols

    def _extract_strategies(self, text: str) -> List[str]:
        """提取策略名称"""
        strategies = []
        for name, pattern in self._strategy_patterns.items():
            if pattern.search(text):
                strategies.append(name)
        return strategies

    def _extract_params(self, text: str) -> Dict[str, Any]:
        """提取参数（数值、时间范围等）"""
        params = {}

        # 提取数值参数: "迭代50次", "回测1年", "夏普>1.5"
        num_pattern = re.compile(
            r'(迭代|次数|iterations?|max_iter|epochs?)\s*[:：]?\s*(\d+)'
        )
        m = num_pattern.search(text)
        if m:
            params["iterations"] = int(m.group(2))

        # 时间范围: "最近3个月", "1年", "半年"
        time_pattern = re.compile(
            r'(最近|过去|近|过去)?\s*(\d+)\s*(年|月|周|天|日|year|month|week|day)'
        )
        m = time_pattern.search(text)
        if m:
            num = int(m.group(2))
            unit = m.group(3)
            unit_map = {"年": "year", "year": "year", "月": "month", "month": "month",
                        "周": "week", "week": "week", "天": "day", "日": "day", "day": "day"}
            params["lookback"] = f"{num}{unit_map.get(unit, unit)}"

        # 阈值: "夏普>1.5", "最大回撤<10%", "胜率>60%"
        threshold_pattern = re.compile(
            r'(夏普|sharpe|最大回撤|max_dd|胜率|win_rate|盈亏比|profit_ratio)\s*[:：]?\s*[>><<=≥≥≤]\s*([\d.]+)'
        )
        for m in threshold_pattern.finditer(text):
            key = m.group(1)
            val = float(m.group(2))
            params[f"threshold_{key}"] = val

        return params

    def _match_skills(self, intent_type: str, params: Dict) -> List[str]:
        """匹配意图到可用技能"""
        intent_config = INTENT_TYPES.get(intent_type)
        if not intent_config:
            return []

        skills = intent_config.get("skills", [])
        # 过滤只保留已注册的技能
        available = [s for s in skills if s in SKILL_REGISTRY]

        # 如果无匹配，返回相近意图的技能
        if not available and intent_type != "help":
            fallback = self._find_fallback_skills(intent_type)
            return fallback

        return available

    def _find_fallback_skills(self, intent_type: str) -> List[str]:
        """为无法匹配的意图查找相近技能"""
        # 按类别推荐
        category_map = {
            "analyze": ["分析"],
            "optimize": ["优化"],
            "backtest": ["回测"],
            "trade": ["交易"],
            "scan": ["扫描"],
            "query": ["查询"],
        }
        target_cat = category_map.get(intent_type, ["系统"])
        fallback = []
        for skill, info in SKILL_REGISTRY.items():
            if any(cat in info["category"] for cat in target_cat):
                fallback.append(skill)
        return fallback[:5]  # 最多5个

    def _detect_mismatches(self, intent: ParsedIntent) -> Tuple[List[str], List[str]]:
        """检测错配：意图需要但缺少的资源"""
        mismatches = []
        suggestions = []

        intent_config = INTENT_TYPES.get(intent.intent_type, {})

        # 检查必需参数
        required = intent_config.get("required_params", [])
        if "symbol" in required and not intent.target_symbols:
            mismatches.append("未识别到股票代码，请提供6位代码或股票名称")
            suggestions.append("示例: 「分析贵州茅台」或「分析600519」")
        if "strategy" in required and not intent.target_strategies:
            mismatches.append("未识别到策略名称")
            suggestions.append("可用策略: 陀螺仪、特种兵、网格交易、多因子共振等")

        # 检查技能匹配
        if not intent.matched_skills and intent.intent_type != "help":
            mismatches.append(f"意图「{intent.intent_type}」无匹配技能")
            suggestions.append("尝试输入「帮助」查看所有可用命令")

        # 检查不存在的股票代码
        if intent.target_symbols:
            unknown = [s for s in intent.target_symbols
                       if not s.isdigit() or len(s) != 6]
            if unknown:
                mismatches.append(f"股票代码格式无效: {unknown}")
                suggestions.append("请使用6位数字代码，如 600519")

        return mismatches, suggestions

    def get_help_text(self) -> str:
        """生成帮助文本"""
        lines = [
            "=" * 50,
            "  港大 Vibe-Trading 智能体指令系统",
            "=" * 50,
            "",
            "可用指令类型:",
        ]
        for itype, config in INTENT_TYPES.items():
            if itype == "help":
                continue
            lines.append(f"  [{itype}] {config['description']}")
            lines.append(f"        示例关键词: {', '.join(config['keywords'][:5])}")
            lines.append("")

        lines.extend([
            "输入示例:",
            "  「分析贵州茅台」—— 全智能体分析股票",
            "  「优化陀螺仪策略迭代100次」—— 参数优化",
            "  「回测特种兵策略最近1年」—— 历史回测",
            "  「扫描高成长股票」—— 股票池筛选",
            "  「查询持仓盈亏」—— 查询状态",
            "=" * 50,
        ])
        return "\n".join(lines)

    def list_available_skills(self, category: str = None) -> List[Dict]:
        """列出可用技能"""
        skills = []
        for name, info in SKILL_REGISTRY.items():
            if category and info["category"] != category:
                continue
            skills.append({
                "name": name,
                "module": info["module"],
                "method": info["method"],
                "category": info["category"]
            })
        return skills

    def get_skill_categories(self) -> List[str]:
        """获取所有技能分类"""
        cats = set()
        for info in SKILL_REGISTRY.values():
            cats.add(info["category"])
        return sorted(cats)


# ============================================================
# 全局单例
# ============================================================

_commander_instance: Optional[NLPCommander] = None


def get_nlp_commander() -> NLPCommander:
    """获取NLPCommander单例"""
    global _commander_instance
    if _commander_instance is None:
        _commander_instance = NLPCommander()
    return _commander_instance


# ============================================================
# 便捷函数
# ============================================================

def parse_command(text: str) -> Dict[str, Any]:
    """便捷解析函数，返回字典格式"""
    cmd = get_nlp_commander()
    result = cmd.parse(text)
    return {
        "raw_text": result.raw_text,
        "intent_type": result.intent_type,
        "target_symbols": result.target_symbols,
        "target_strategies": result.target_strategies,
        "params": result.params,
        "confidence": result.confidence,
        "matched_skills": result.matched_skills,
        "mismatches": result.mismatches,
        "suggestions": result.suggestions,
        "is_valid": len(result.mismatches) == 0 and result.confidence > 0.3,
    }


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    cmd = NLPCommander()

    test_cases = [
        "分析贵州茅台",
        "优化陀螺仪策略",
        "回测特种兵策略最近1年",
        "扫描高成长股票",
        "查询持仓盈亏",
        "买入600519",
        "帮助",
        "随机乱码xyz",
        "分析 600519 迭代50次",
        "配置止损阈值",
    ]

    for tc in test_cases:
        result = cmd.parse(tc)
        print(f"\n输入: {tc}")
        print(f"  意图: {result.intent_type} (置信度: {result.confidence:.0%})")
        print(f"  股票: {result.target_symbols}")
        print(f"  策略: {result.target_strategies}")
        print(f"  参数: {result.params}")
        print(f"  技能: {result.matched_skills}")
        if result.mismatches:
            print(f"  错配: {result.mismatches}")
        if result.suggestions:
            print(f"  建议: {result.suggestions}")