#!/usr/bin/env python3
"""
Agent注册表 & 技能注册表（Agent Registry & Skill Registry）

港大29智能体 + 79项分析技能的统一注册、查询、匹配系统。

Agent注册表：6组29个智能体，每个Agent有名称、分组、标签、方法名
技能注册表：79项分析技能，每项有名称、分类、参数、适用场景

设计目标：
  1. 支持按名称/分组/标签精确匹配Agent
  2. 支持自然语言关键词模糊匹配技能
  3. 支持自由组合：选择特定Agent + 特定技能 → 执行
  4. 为Cline对话框提供可视化选择面板数据源
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field


# ============================================================
# 数据模型
# ============================================================

@dataclass
class AgentInfo:
    """Agent信息"""
    agent_id: str              # 唯一标识
    name: str                  # 中文名称
    group: str                 # 所属分组
    method_name: str           # vibe_29_agents.py中的方法名
    description: str           # 功能描述
    tags: List[str] = field(default_factory=list)  # 标签
    dependencies: List[str] = field(default_factory=list)  # 依赖的技能


@dataclass
class SkillInfo:
    """技能信息"""
    skill_id: str              # 唯一标识
    name: str                  # 中文名称
    category: str              # 分类
    module: str                # 来源模块
    method_name: str           # 方法名
    description: str           # 功能描述
    params: Dict[str, Any] = field(default_factory=dict)  # 参数说明
    output_type: str = "dict"  # 输出类型
    tags: List[str] = field(default_factory=list)  # 标签
    usage_scenario: str = ""   # 适用场景


# ============================================================
# 29个Agent注册表
# ============================================================

AGENT_REGISTRY: Dict[str, AgentInfo] = {
    # ===== 技术分析组（9个）=====
    "trend": AgentInfo(
        agent_id="trend",
        name="趋势智能体",
        group="技术分析组",
        method_name="trend_agent",
        description="MA/EMA多头空头排列、中期趋势判断、价格与均线关系分析",
        tags=["趋势", "均线", "多头", "空头", "MA", "EMA", "方向"],
        dependencies=["ma5", "ma10", "ma20", "ma60"],
    ),
    "momentum": AgentInfo(
        agent_id="momentum",
        name="动量智能体",
        group="技术分析组",
        method_name="momentum_agent",
        description="RSI超买超卖判断、KDJ金叉死叉识别、动量强度评估",
        tags=["RSI", "KDJ", "超买", "超卖", "金叉", "死叉", "震荡"],
        dependencies=["rsi_14", "kdj"],
    ),
    "pattern": AgentInfo(
        agent_id="pattern",
        name="形态智能体",
        group="技术分析组",
        method_name="pattern_agent",
        description="K线形态识别（突破/破位/横盘）、顶部/底部形态检测",
        tags=["K线", "形态", "突破", "破位", "横盘", "反转"],
        dependencies=["candlestick", "support_resistance"],
    ),
    "volume": AgentInfo(
        agent_id="volume",
        name="成交量智能体",
        group="技术分析组",
        method_name="volume_agent",
        description="量价关系分析（放量上涨/缩量下跌）、OBV趋势判断",
        tags=["成交量", "量价", "放量", "缩量", "OBV", "量能"],
        dependencies=["obv", "volume_ratio"],
    ),
    "money_flow": AgentInfo(
        agent_id="money_flow",
        name="资金流向智能体",
        group="技术分析组",
        method_name="money_flow_agent",
        description="主力资金动向分析、量比/成交量异动综合判断",
        tags=["资金流向", "主力", "量比", "异动", "北向资金"],
        dependencies=["money_flow", "volume_ratio", "vol_deviation"],
    ),
    "volume_anomaly": AgentInfo(
        agent_id="volume_anomaly",
        name="成交量异动智能体",
        group="技术分析组",
        method_name="volume_anomaly_agent",
        description="异常放量/缩量模式识别（恐慌抛盘/放量大涨/缩量横盘）",
        tags=["异动", "放量", "缩量", "恐慌", "异常"],
        dependencies=["volume_ratio", "vol_deviation"],
    ),
    "volatility": AgentInfo(
        agent_id="volatility",
        name="波动智能体",
        group="技术分析组",
        method_name="volatility_agent",
        description="波动率分析、布林带宽度、ATR波动范围、高/低波动环境判断",
        tags=["波动率", "布林带", "ATR", "HV", "标准差"],
        dependencies=["bollinger", "atr", "volatility"],
    ),
    "support_resistance": AgentInfo(
        agent_id="support_resistance",
        name="支撑阻力智能体",
        group="技术分析组",
        method_name="support_resistance_agent",
        description="关键支撑/阻力位识别、价格位置评估、突破/回踩判断",
        tags=["支撑", "阻力", "压力位", "关键位", "突破"],
        dependencies=["support_resistance"],
    ),
    "multi_period": AgentInfo(
        agent_id="multi_period",
        name="多周期智能体",
        group="技术分析组",
        method_name="multi_period_agent",
        description="日/周/月多周期共振分析、跨周期趋势一致性判断",
        tags=["多周期", "日线", "周线", "月线", "共振", "跨周期"],
        dependencies=["ma_multi_period"],
    ),

    # ===== 基本面分析组（6个）=====
    "macro": AgentInfo(
        agent_id="macro",
        name="宏观分析智能体",
        group="基本面分析组",
        method_name="macro_agent",
        description="GDP/CPI/PMI/利率/货币供应等宏观经济指标分析",
        tags=["宏观", "GDP", "CPI", "PMI", "利率", "货币政策", "经济周期"],
        dependencies=["macro_data"],
    ),
    "valuation": AgentInfo(
        agent_id="valuation",
        name="估值分析智能体",
        group="基本面分析组",
        method_name="valuation_agent",
        description="PE/PB/PS/EV/EBITDA估值分析、历史分位、行业对比",
        tags=["估值", "PE", "PB", "PS", "低估", "高估", "合理"],
        dependencies=["pe", "pb", "ps", "market_cap"],
    ),
    "growth": AgentInfo(
        agent_id="growth",
        name="成长性智能体",
        group="基本面分析组",
        method_name="growth_agent",
        description="营收/利润/净资产增长率分析、成长趋势判断",
        tags=["成长", "营收", "利润", "增长率", "ROE", "ROA"],
        dependencies=["roe", "roa", "growth_rate"],
    ),
    "profitability": AgentInfo(
        agent_id="profitability",
        name="盈利质量智能体",
        group="基本面分析组",
        method_name="profitability_agent",
        description="毛利率/净利率/ROE/ROA/ROIC 盈利能力分析",
        tags=["盈利", "毛利率", "净利率", "ROE", "ROA", "ROIC"],
        dependencies=["roe", "roa", "gross_margin", "net_margin"],
    ),
    "cashflow": AgentInfo(
        agent_id="cashflow",
        name="现金流智能体",
        group="基本面分析组",
        method_name="cashflow_agent",
        description="自由现金流/经营现金流分析、现金流质量评估",
        tags=["现金流", "自由现金流", "FCF", "经营现金流", "现金"],
        dependencies=["free_cashflow"],
    ),
    "dividend": AgentInfo(
        agent_id="dividend",
        name="分红智能体",
        group="基本面分析组",
        method_name="dividend_agent",
        description="股息率/分红稳定性/分红增长率分析",
        tags=["分红", "股息", "股息率", "红利", "派息"],
        dependencies=["dividend_yield"],
    ),

    # ===== 舆情分析组（5个）=====
    "news_sentiment": AgentInfo(
        agent_id="news_sentiment",
        name="新闻舆情智能体",
        group="舆情分析组",
        method_name="news_sentiment_agent",
        description="新闻情感分析、利好/利空判断、舆情热度评估",
        tags=["新闻", "舆情", "利好", "利空", "热度", "情感"],
        dependencies=["sentiment"],
    ),
    "social_media": AgentInfo(
        agent_id="social_media",
        name="社交媒体智能体",
        group="舆情分析组",
        method_name="social_media_agent",
        description="社交媒体热度分析、讨论量/关注度/情绪指数",
        tags=["社交", "热度", "讨论", "关注", "情绪"],
        dependencies=["social_sentiment"],
    ),
    "capital_flow": AgentInfo(
        agent_id="capital_flow",
        name="资金流向智能体(舆情)",
        group="舆情分析组",
        method_name="money_flow_agent",
        description="北向资金/龙虎榜/大宗交易资金流向分析",
        tags=["北向资金", "龙虎榜", "大宗交易", "机构"],
        dependencies=["north_bound", "top_traders"],
    ),
    "market_sentiment": AgentInfo(
        agent_id="market_sentiment",
        name="市场情绪智能体",
        group="舆情分析组",
        method_name="market_sentiment_agent",
        description="涨跌比/恐慌指数/市场宽度/情绪周期判断",
        tags=["情绪", "恐慌", "贪婪", "涨跌比", "市场宽度"],
        dependencies=["market_breadth"],
    ),
    "sector_rotation": AgentInfo(
        agent_id="sector_rotation",
        name="板块轮动智能体",
        group="舆情分析组",
        method_name="sector_rotation_agent",
        description="行业轮动信号识别、板块强弱对比、轮动节奏判断",
        tags=["板块", "轮动", "行业", "热点", "切换"],
        dependencies=["sector_performance"],
    ),

    # ===== 风控组（4个）=====
    "risk_assessment": AgentInfo(
        agent_id="risk_assessment",
        name="风险评估智能体",
        group="风控组",
        method_name="risk_assessment_agent",
        description="综合风险评估（VaR/最大回撤/波动率/相关性）",
        tags=["风险", "VaR", "回撤", "波动", "相关性"],
        dependencies=["var", "max_drawdown"],
    ),
    "position_management": AgentInfo(
        agent_id="position_management",
        name="仓位管理智能体",
        group="风控组",
        method_name="position_management_agent",
        description="仓位建议/凯利公式/资金管理/风险暴露计算",
        tags=["仓位", "凯利", "资金管理", "风险暴露", "配置"],
        dependencies=["kelly", "position_sizing"],
    ),
    "stop_loss": AgentInfo(
        agent_id="stop_loss",
        name="止损止盈智能体",
        group="风控组",
        method_name="stop_loss_agent",
        description="止损/止盈位计算（ATR/百分比/支撑位）",
        tags=["止损", "止盈", "ATR", "百分比", "保护"],
        dependencies=["atr", "support_resistance"],
    ),
    "black_swan": AgentInfo(
        agent_id="black_swan",
        name="黑天鹅监控智能体",
        group="风控组",
        method_name="black_swan_agent",
        description="极端事件检测/尾部风险/异常波动预警",
        tags=["黑天鹅", "极端", "尾部风险", "异常", "预警"],
        dependencies=["tail_risk"],
    ),

    # ===== 策略研究组（4个）=====
    "strategy_builder": AgentInfo(
        agent_id="strategy_builder",
        name="策略构建智能体",
        group="策略研究组",
        method_name="strategy_builder_agent",
        description="策略生成/因子组合/规则构建/信号合成",
        tags=["策略", "因子", "组合", "规则", "信号"],
        dependencies=["alpha_factors"],
    ),
    "backtest_validator": AgentInfo(
        agent_id="backtest_validator",
        name="回测验证智能体",
        group="策略研究组",
        method_name="backtest_validator_agent",
        description="回测验证/过拟合检测/样本外测试",
        tags=["回测", "验证", "过拟合", "样本外", "稳健"],
        dependencies=["backtest"],
    ),
    "execution": AgentInfo(
        agent_id="execution",
        name="执行智能体",
        group="策略研究组",
        method_name="execution_agent",
        description="订单执行策略/滑点控制/交易成本优化",
        tags=["执行", "订单", "滑点", "成本", "成交"],
        dependencies=["slippage", "commission"],
    ),
    "performance_attribution": AgentInfo(
        agent_id="performance_attribution",
        name="绩效归因智能体",
        group="策略研究组",
        method_name="performance_attribution_agent",
        description="收益归因分析（因子/选股/择时/行业）",
        tags=["绩效", "归因", "选股", "择时", "行业"],
        dependencies=["performance_attribution"],
    ),

    # ===== 辅助决策组（3个）=====
    "comprehensive": AgentInfo(
        agent_id="comprehensive",
        name="综合评分智能体",
        group="辅助决策组",
        method_name="comprehensive_agent",
        description="多维度加权综合评分（技术40%+基本面30%+舆情20%+风控10%）",
        tags=["综合", "评分", "加权", "多维", "最终"],
        dependencies=["all"],
    ),
    "debate": AgentInfo(
        agent_id="debate",
        name="辩论仲裁智能体",
        group="辅助决策组",
        method_name="debate",
        description="多方（技术分析组）vs 空方（风控组）辩论 + 最终加权投票",
        tags=["辩论", "多方", "空方", "投票", "仲裁"],
        dependencies=["all"],
    ),
    "decision": AgentInfo(
        agent_id="decision",
        name="决策输出智能体",
        group="辅助决策组",
        method_name="decision_agent",
        description="最终决策建议（买入/卖出/持有 + 理由 + 风险提示）",
        tags=["决策", "建议", "买入", "卖出", "持有", "结论"],
        dependencies=["all"],
    ),
# ===== 专家评审组（12位 Shepherd V5）=====
    "architect_auditor": AgentInfo(
        agent_id="architect_auditor",
        name="架构设计审计师",
        group="专家评审组",
        method_name="expert_architect_auditor",
        description="系统架构设计评审，检查模块职责划分、耦合度、扩展性，确保架构清晰无功能重叠",
        tags=["架构", "设计", "审计", "模块", "解耦", "扩展性"],
        dependencies=[],
    ),
    "code_quality_inspector": AgentInfo(
        agent_id="code_quality_inspector",
        name="代码质量审查官",
        group="专家评审组",
        method_name="expert_code_quality",
        description="代码规范性、安全性、可维护性审查，识别逻辑错误和性能问题",
        tags=["代码", "质量", "审查", "规范", "安全", "可维护"],
        dependencies=[],
    ),
    "risk_compliance_officer": AgentInfo(
        agent_id="risk_compliance_officer",
        name="金融风控合规官",
        group="专家评审组",
        method_name="expert_risk_compliance",
        description="金融风控与合规审查，检查策略风控逻辑、仓位管理、止损止盈规则",
        tags=["风控", "合规", "金融", "风险", "监管", "审计"],
        dependencies=[],
    ),
    "performance_engineer": AgentInfo(
        agent_id="performance_engineer",
        name="性能工程师",
        group="专家评审组",
        method_name="expert_performance",
        description="执行效率与性能优化，检测延迟、吞吐量、资源占用等性能瓶颈",
        tags=["性能", "优化", "延迟", "吞吐", "效率", "资源"],
        dependencies=[],
    ),
    "security_auditor": AgentInfo(
        agent_id="security_auditor",
        name="安全审计专家",
        group="专家评审组",
        method_name="expert_security_audit",
        description="系统安全审计，检查鉴权、密钥管理、注入防御、隐私保护、依赖安全",
        tags=["安全", "审计", "鉴权", "密钥", "注入", "隐私"],
        dependencies=[],
    ),
    "data_quality_specialist": AgentInfo(
        agent_id="data_quality_specialist",
        name="数据质量专家",
        group="专家评审组",
        method_name="expert_data_quality",
        description="数据完整性、准确性、时效性检查，确保数据源可靠、降级链路可追溯",
        tags=["数据", "质量", "完整性", "准确性", "降级", "追溯"],
        dependencies=[],
    ),
    "scalability_architect": AgentInfo(
        agent_id="scalability_architect",
        name="可扩展性架构师",
        group="专家评审组",
        method_name="expert_scalability",
        description="系统可扩展性评估，检查水平扩展能力、插件机制、配置灵活性",
        tags=["扩展", "弹性", "插件", "配置", "架构", "伸缩"],
        dependencies=[],
    ),
    "qa_test_lead": AgentInfo(
        agent_id="qa_test_lead",
        name="测试工程专家",
        group="专家评审组",
        method_name="expert_qa_test",
        description="测试覆盖率评估，检查单元测试、集成测试、边界测试覆盖情况",
        tags=["测试", "覆盖", "QA", "质量", "边界", "集成"],
        dependencies=[],
    ),
    "observability_designer": AgentInfo(
        agent_id="observability_designer",
        name="用户体验设计师",
        group="专家评审组",
        method_name="expert_observability",
        description="可观测性与用户体验设计，检查日志、监控、告警、UI交互质量",
        tags=["体验", "UI", "可观测", "监控", "告警", "日志"],
        dependencies=[],
    ),
    "ai_ml_engineer": AgentInfo(
        agent_id="ai_ml_engineer",
        name="AI工程化专家",
        group="专家评审组",
        method_name="expert_ai_ml",
        description="AI/ML集成与工程化评审，检查模型部署、推理效率、特征工程管线",
        tags=["AI", "ML", "模型", "部署", "推理", "特征"],
        dependencies=[],
    ),
    "devops_engineer": AgentInfo(
        agent_id="devops_engineer",
        name="DevOps运维专家",
        group="专家评审组",
        method_name="expert_devops",
        description="部署与运维就绪检查，验证CI/CD、容器化、监控告警、灾备方案",
        tags=["DevOps", "运维", "部署", "CI/CD", "容器", "灾备"],
        dependencies=[],
    ),
    "product_review_officer": AgentInfo(
        agent_id="product_review_officer",
        name="产品化评审官",
        group="专家评审组",
        method_name="expert_product_review",
        description="商业化与产品化评审，评估策略的市场适应性、用户体验、商业价值",
        tags=["产品", "商业", "市场", "用户", "价值", "评审"],
        dependencies=[],
    ),

    # ===== 交易专家团（4位 Shepherd V6）=====
    "strategy_algorithm_expert": AgentInfo(
        agent_id="strategy_algorithm_expert",
        name="策略算法专家",
        group="交易专家团",
        method_name="expert_strategy_algorithm",
        description="策略算法评审，评估收益优化、夏普比率改善、逻辑补丁质量",
        tags=["策略", "算法", "收益", "夏普", "优化", "逻辑"],
        dependencies=[],
    ),
    "trading_risk_compliance_expert": AgentInfo(
        agent_id="trading_risk_compliance_expert",
        name="交易风控合规专家",
        group="交易专家团",
        method_name="expert_trading_risk",
        description="交易风控与合规评审，检查最大回撤、VaR、风险敞口、合规边界",
        tags=["风控", "合规", "回撤", "VaR", "敞口", "交易"],
        dependencies=[],
    ),
    "trading_engineering_expert": AgentInfo(
        agent_id="trading_engineering_expert",
        name="交易工程专家",
        group="交易专家团",
        method_name="expert_trading_engineering",
        description="交易工程与执行评审，评估OMS延迟、成交率、滑点控制、报单质量",
        tags=["工程", "执行", "OMS", "延迟", "成交", "滑点"],
        dependencies=[],
    ),
    "cost_efficiency_expert": AgentInfo(
        agent_id="cost_efficiency_expert",
        name="成本效率专家",
        group="交易专家团",
        method_name="expert_cost_efficiency",
        description="成本效率评审，评估交易成本、手续费优化、资金使用效率",
        tags=["成本", "效率", "手续费", "资金", "费率", "优化"],
        dependencies=[],
    ),
}


# ============================================================
# 79项技能注册表
# ============================================================

SKILL_REGISTRY: Dict[str, SkillInfo] = {
    # ===== 技术指标类（20项）=====
    "ma5": SkillInfo("ma5", "MA5均线", "技术指标", "technical_analysis",
                     "calculate_ma", "5日移动平均线", {"period": 5},
                     tags=["均线", "短期", "MA"], usage_scenario="短期趋势判断"),
    "ma10": SkillInfo("ma10", "MA10均线", "技术指标", "technical_analysis",
                      "calculate_ma", "10日移动平均线", {"period": 10},
                      tags=["均线", "短期", "MA"], usage_scenario="中短期趋势"),
    "ma20": SkillInfo("ma20", "MA20均线", "技术指标", "technical_analysis",
                      "calculate_ma", "20日移动平均线（生命线）", {"period": 20},
                      tags=["均线", "中期", "MA", "生命线"], usage_scenario="中期趋势判断"),
    "ma60": SkillInfo("ma60", "MA60均线", "技术指标", "technical_analysis",
                      "calculate_ma", "60日移动平均线（牛熊分界线）", {"period": 60},
                      tags=["均线", "长期", "MA", "牛熊"], usage_scenario="长期趋势与牛熊判断"),
    "ema12": SkillInfo("ema12", "EMA12", "技术指标", "technical_analysis",
                       "calculate_ema", "12日指数移动平均线", {"period": 12},
                       tags=["均线", "EMA", "指数"], usage_scenario="MACD快线"),
    "ema26": SkillInfo("ema26", "EMA26", "技术指标", "technical_analysis",
                       "calculate_ema", "26日指数移动平均线", {"period": 26},
                       tags=["均线", "EMA", "指数"], usage_scenario="MACD慢线"),
    "rsi_14": SkillInfo("rsi_14", "RSI(14)", "技术指标", "technical_analysis",
                        "calculate_rsi", "14日相对强弱指数", {"period": 14},
                        tags=["RSI", "超买", "超卖", "震荡"], usage_scenario="超买超卖判断"),
    "macd": SkillInfo("macd", "MACD", "技术指标", "technical_analysis",
                      "calculate_macd", "MACD指标（DIF+DEA+柱状图）", {},
                      tags=["MACD", "趋势", "金叉", "死叉", "背离"], usage_scenario="趋势跟踪与买卖信号"),
    "bollinger": SkillInfo("bollinger", "布林带", "技术指标", "technical_analysis",
                           "calculate_bollinger", "布林带（上轨+中轨+下轨）", {"period": 20, "std": 2},
                           tags=["布林带", "波动", "轨道", "突破"], usage_scenario="波动率与突破信号"),
    "atr": SkillInfo("atr", "ATR", "技术指标", "technical_analysis",
                     "calculate_atr", "平均真实波幅", {"period": 14},
                     tags=["ATR", "波动", "止损", "振幅"], usage_scenario="止损位设置与波动率"),
    "kdj": SkillInfo("kdj", "KDJ", "技术指标", "technical_analysis",
                     "calculate_kdj", "随机指标（K+D+J）", {"period": 9},
                     tags=["KDJ", "超买", "超卖", "金叉", "死叉"], usage_scenario="短线买卖点"),
    "obv": SkillInfo("obv", "OBV", "技术指标", "technical_analysis",
                     "calculate_obv", "能量潮指标", {},
                     tags=["OBV", "量能", "资金", "背离"], usage_scenario="量价配合与背离"),
    "vwap": SkillInfo("vwap", "VWAP", "技术指标", "technical_analysis",
                      "calculate_vwap", "成交量加权平均价", {},
                      tags=["VWAP", "均价", "成交", "机构"], usage_scenario="机构成本价参考"),
    "cci": SkillInfo("cci", "CCI", "技术指标", "technical_analysis",
                     "calculate_cci", "商品通道指数", {"period": 20},
                     tags=["CCI", "超买", "超卖", "趋势"], usage_scenario="极端行情判断"),
    "adx": SkillInfo("adx", "ADX", "技术指标", "technical_analysis",
                     "calculate_adx", "平均趋向指数", {"period": 14},
                     tags=["ADX", "趋势强度", "方向"], usage_scenario="趋势强度评估"),
    "williams_r": SkillInfo("williams_r", "威廉指标", "技术指标", "technical_analysis",
                            "calculate_williams_r", "威廉%R指标", {"period": 14},
                            tags=["威廉", "超买", "超卖", "%R"], usage_scenario="超买超卖"),
    "mfi": SkillInfo("mfi", "MFI", "技术指标", "technical_analysis",
                     "calculate_mfi", "资金流量指标", {"period": 14},
                     tags=["MFI", "资金", "量价", "背离"], usage_scenario="资金流向与量价关系"),
    "ichimoku": SkillInfo("ichimoku", "一目均衡表", "技术指标", "technical_analysis",
                          "calculate_ichimoku", "一目均衡表（云层+转换线+基准线）", {},
                          tags=["一目均衡", "云层", "趋势", "支撑阻力"], usage_scenario="综合趋势判断"),
    "pivot_points": SkillInfo("pivot_points", "枢轴点", "技术指标", "technical_analysis",
                              "calculate_pivot_points", "枢轴点及支撑阻力位", {},
                              tags=["枢轴", "支撑", "阻力", "Pivot"], usage_scenario="日内关键价位"),
    "psar": SkillInfo("psar", "抛物线SAR", "技术指标", "technical_analysis",
                      "calculate_psar", "抛物线转向指标", {},
                      tags=["SAR", "止损", "反转", "趋势"], usage_scenario="趋势跟踪与止损"),

    # ===== 因子类（12项）=====
    "momentum_1d": SkillInfo("momentum_1d", "1日动量", "量化因子", "technical_analysis",
                             "calculate_factor", "当日价格变化率", {"factor": "momentum_1d"},
                             tags=["动量", "短期", "收益"], usage_scenario="短期动量效应"),
    "momentum_5d": SkillInfo("momentum_5d", "5日动量", "量化因子", "technical_analysis",
                             "calculate_factor", "5日价格变化率", {"factor": "momentum_5d"},
                             tags=["动量", "中期", "收益"], usage_scenario="中期动量效应"),
    "momentum_20d": SkillInfo("momentum_20d", "20日动量", "量化因子", "technical_analysis",
                              "calculate_factor", "20日价格变化率", {"factor": "momentum_20d"},
                              tags=["动量", "长期", "收益"], usage_scenario="长期动量效应"),
    "momentum_60d": SkillInfo("momentum_60d", "60日动量", "量化因子", "technical_analysis",
                              "calculate_factor", "60日价格变化率", {"factor": "momentum_60d"},
                              tags=["动量", "超长期", "收益"], usage_scenario="超长期趋势"),
    "volatility_20d": SkillInfo("volatility_20d", "20日波动率", "量化因子", "technical_analysis",
                                "calculate_factor", "20日历史波动率", {"factor": "volatility_20d"},
                                tags=["波动率", "风险", "标准差"], usage_scenario="风险度量"),
    "rsi_factor": SkillInfo("rsi_factor", "RSI因子", "量化因子", "technical_analysis",
                            "calculate_factor", "RSI(14)因子值", {"factor": "rsi_14d"},
                            tags=["RSI", "因子", "超买超卖"], usage_scenario="均值回归信号"),
    "bollinger_width": SkillInfo("bollinger_width", "布林带宽度", "量化因子", "technical_analysis",
                                 "calculate_factor", "布林带宽度因子", {"factor": "bollinger_width"},
                                 tags=["布林带", "波动率", "宽度"], usage_scenario="波动率变化"),
    "macd_signal": SkillInfo("macd_signal", "MACD信号", "量化因子", "technical_analysis",
                             "calculate_factor", "MACD DIF-DEA差值", {"factor": "macd_signal"},
                             tags=["MACD", "信号", "趋势"], usage_scenario="趋势信号"),
    "atr_ratio": SkillInfo("atr_ratio", "ATR比率", "量化因子", "technical_analysis",
                           "calculate_factor", "ATR/价格比率", {"factor": "atr_ratio"},
                           tags=["ATR", "波动率", "比率"], usage_scenario="相对波动率"),
    "obv_change": SkillInfo("obv_change", "OBV变化率", "量化因子", "technical_analysis",
                            "calculate_factor", "OBV变化率", {"factor": "obv_change"},
                            tags=["OBV", "资金", "变化"], usage_scenario="资金流向"),
    "ma_slope": SkillInfo("ma_slope", "均线斜率", "量化因子", "technical_analysis",
                          "calculate_factor", "20日均线斜率", {"factor": "ma_slope_20d"},
                          tags=["均线", "斜率", "趋势强度"], usage_scenario="趋势强度"),
    "volume_ratio": SkillInfo("volume_ratio", "量比因子", "量化因子", "technical_analysis",
                              "calculate_factor", "成交量比率因子", {"factor": "volume_ratio"},
                              tags=["量比", "成交量", "活跃度"], usage_scenario="成交量活跃度"),

    # ===== 期权分析类（15项）=====
    "bs_call": SkillInfo("bs_call", "BS看涨定价", "期权分析", "vibe_options_skills",
                         "black_scholes", "Black-Scholes欧式看涨期权定价", {"option_type": "call"},
                         tags=["期权", "定价", "BS", "看涨"], usage_scenario="期权理论价格"),
    "bs_put": SkillInfo("bs_put", "BS看跌定价", "期权分析", "vibe_options_skills",
                        "black_scholes", "Black-Scholes欧式看跌期权定价", {"option_type": "put"},
                        tags=["期权", "定价", "BS", "看跌"], usage_scenario="期权理论价格"),
    "delta": SkillInfo("delta", "Delta", "期权分析", "vibe_options_skills",
                       "calculate_greeks", "期权Delta（价格敏感度）", {},
                       tags=["希腊字母", "Delta", "敏感度"], usage_scenario="方向性风险"),
    "gamma": SkillInfo("gamma", "Gamma", "期权分析", "vibe_options_skills",
                       "calculate_greeks", "期权Gamma（Delta变化率）", {},
                       tags=["希腊字母", "Gamma", "曲率"], usage_scenario="Delta变化风险"),
    "theta": SkillInfo("theta", "Theta", "期权分析", "vibe_options_skills",
                       "calculate_greeks", "期权Theta（时间衰减）", {},
                       tags=["希腊字母", "Theta", "时间"], usage_scenario="时间价值衰减"),
    "vega": SkillInfo("vega", "Vega", "期权分析", "vibe_options_skills",
                      "calculate_greeks", "期权Vega（波动率敏感度）", {},
                      tags=["希腊字母", "Vega", "波动率"], usage_scenario="波动率风险"),
    "rho": SkillInfo("rho", "Rho", "期权分析", "vibe_options_skills",
                     "calculate_greeks", "期权Rho（利率敏感度）", {},
                     tags=["希腊字母", "Rho", "利率"], usage_scenario="利率风险"),
    "implied_vol": SkillInfo("implied_vol", "隐含波动率", "期权分析", "vibe_options_skills",
                             "implied_volatility", "Newton-Raphson迭代法隐含波动率", {},
                             tags=["隐含波动率", "IV", "迭代"], usage_scenario="市场预期波动"),
    "vol_smile": SkillInfo("vol_smile", "波动率微笑", "期权分析", "vibe_options_skills",
                           "volatility_smile", "波动率微笑曲线分析", {},
                           tags=["波动率微笑", "曲面", "偏度"], usage_scenario="波动率结构"),
    "vol_surface": SkillInfo("vol_surface", "波动率曲面", "期权分析", "vibe_options_skills",
                             "volatility_surface", "波动率曲面（行权价+到期日）", {},
                             tags=["波动率曲面", "三维", "期限结构"], usage_scenario="波动率期限结构"),
    "straddle": SkillInfo("straddle", "跨式策略", "期权分析", "vibe_options_skills",
                          "straddle_strategy", "跨式策略盈亏分析", {},
                          tags=["策略", "跨式", "波动", "Straddle"], usage_scenario="波动率交易"),
    "strangle": SkillInfo("strangle", "宽跨式策略", "期权分析", "vibe_options_skills",
                          "strangle_strategy", "宽跨式策略盈亏分析", {},
                          tags=["策略", "宽跨式", "波动", "Strangle"], usage_scenario="低成本波动率交易"),
    "butterfly": SkillInfo("butterfly", "蝶式策略", "期权分析", "vibe_options_skills",
                           "butterfly_strategy", "蝶式策略盈亏分析", {},
                           tags=["策略", "蝶式", "区间", "Butterfly"], usage_scenario="区间震荡交易"),
    "iron_condor": SkillInfo("iron_condor", "铁鹰策略", "期权分析", "vibe_options_skills",
                             "iron_condor_strategy", "铁鹰策略盈亏分析", {},
                             tags=["策略", "铁鹰", "区间", "Iron Condor"], usage_scenario="收益增强"),
    "calendar_spread": SkillInfo("calendar_spread", "日历价差", "期权分析", "vibe_options_skills",
                                 "calendar_spread_strategy", "日历价差策略盈亏分析", {},
                                 tags=["策略", "日历", "价差", "时间"], usage_scenario="时间价值套利"),

    # ===== 量能分析类（8项）=====
    "volume_anomaly_detect": SkillInfo("volume_anomaly_detect", "成交量异动检测", "量能分析",
                                       "vibe_29_agents", "volume_anomaly_agent",
                                       "异常放量/缩量模式识别", {},
                                       tags=["异动", "放量", "缩量", "检测"], usage_scenario="异常放量识别"),
    "volume_price_analysis": SkillInfo("volume_price_analysis", "量价关系分析", "量能分析",
                                       "vibe_29_agents", "volume_agent",
                                       "量价配合/背离分析", {},
                                       tags=["量价", "配合", "背离", "量能"], usage_scenario="量价一致性"),
    "money_flow_indicator": SkillInfo("money_flow_indicator", "资金流向指标", "量能分析",
                                      "vibe_29_agents", "money_flow_agent",
                                      "主力资金流向综合判断", {},
                                      tags=["资金", "主力", "流向"], usage_scenario="资金动向"),
    "volume_ratio_indicator": SkillInfo("volume_ratio_indicator", "量比分析", "量能分析",
                                        "technical_analysis", "calculate_indicator",
                                        "量比指标计算", {"indicator": "volume_ratio"},
                                        tags=["量比", "放量", "缩量"], usage_scenario="即时成交量对比"),
    "obv_divergence": SkillInfo("obv_divergence", "OBV背离检测", "量能分析",
                                "vibe_29_agents", "volume_agent",
                                "OBV与价格背离检测", {},
                                tags=["OBV", "背离", "量价背离"], usage_scenario="量价背离预警"),
    "volume_profile": SkillInfo("volume_profile", "成交量分布", "量能分析",
                                "technical_analysis", "calculate_indicator",
                                "成交量分布分析", {"indicator": "volume_profile"},
                                tags=["分布", "成交量", "Profile"], usage_scenario="关键价位成交量"),
    "money_flow_index": SkillInfo("money_flow_index", "资金流量指数", "量能分析",
                                  "technical_analysis", "calculate_mfi",
                                  "MFI资金流量指数", {},
                                  tags=["MFI", "资金", "流量"], usage_scenario="资金流入流出"),
    "accumulation_dist": SkillInfo("accumulation_dist", "累积/派发线", "量能分析",
                                   "technical_analysis", "calculate_indicator",
                                   "A/D累积/派发指标", {"indicator": "ad_line"},
                                   tags=["累积", "派发", "A/D"], usage_scenario="资金积累/派发"),

    # ===== 形态识别类（8项）=====
    "candlestick_pattern": SkillInfo("candlestick_pattern", "K线形态识别", "形态识别",
                                     "vibe_29_agents", "pattern_agent",
                                     "锤子线/吞没/启明星/黄昏星等", {},
                                     tags=["K线", "形态", "蜡烛", "反转"], usage_scenario="K线形态信号"),
    "support_resistance_level": SkillInfo("support_resistance_level", "支撑阻力位", "形态识别",
                                          "vibe_29_agents", "support_resistance_agent",
                                          "关键支撑/阻力位识别", {},
                                          tags=["支撑", "阻力", "关键位"], usage_scenario="关键价位"),
    "trend_line": SkillInfo("trend_line", "趋势线分析", "形态识别",
                            "vibe_29_agents", "trend_agent",
                            "趋势线 & 通道分析", {},
                            tags=["趋势线", "通道", "方向"], usage_scenario="趋势识别"),
    "breakout_detect": SkillInfo("breakout_detect", "突破检测", "形态识别",
                                 "vibe_29_agents", "pattern_agent",
                                 "突破/破位/假突破检测", {},
                                 tags=["突破", "破位", "假突破"], usage_scenario="突破信号"),
    "head_shoulders": SkillInfo("head_shoulders", "头肩顶/底", "形态识别",
                                "vibe_29_agents", "pattern_agent",
                                "头肩顶/头肩底形态识别", {},
                                tags=["头肩", "反转", "顶部", "底部"], usage_scenario="反转形态"),
    "double_top_bottom": SkillInfo("double_top_bottom", "双顶/双底", "形态识别",
                                   "vibe_29_agents", "pattern_agent",
                                   "双顶/双底形态识别", {},
                                   tags=["双顶", "双底", "W底", "M顶"], usage_scenario="反转形态"),
    "triangle_pattern": SkillInfo("triangle_pattern", "三角形形态", "形态识别",
                                  "vibe_29_agents", "pattern_agent",
                                  "对称/上升/下降三角形识别", {},
                                  tags=["三角形", "收敛", "突破"], usage_scenario="整理形态"),
    "flag_pattern": SkillInfo("flag_pattern", "旗形形态", "形态识别",
                              "vibe_29_agents", "pattern_agent",
                              "旗形/三角旗形识别", {},
                              tags=["旗形", "持续", "整理"], usage_scenario="持续形态"),

    # ===== 基本面类（8项）=====
    "macro_indicators": SkillInfo("macro_indicators", "宏观经济指标", "基本面分析",
                                  "vibe_29_agents", "macro_agent",
                                  "GDP/CPI/PMI/利率/货币供应", {},
                                  tags=["宏观", "GDP", "CPI", "PMI"], usage_scenario="宏观环境"),
    "valuation_metrics": SkillInfo("valuation_metrics", "估值指标", "基本面分析",
                                   "vibe_29_agents", "valuation_agent",
                                   "PE/PB/PS/EV/EBITDA", {},
                                   tags=["估值", "PE", "PB", "PS"], usage_scenario="估值分析"),
    "growth_metrics": SkillInfo("growth_metrics", "成长性指标", "基本面分析",
                                "vibe_29_agents", "growth_agent",
                                "营收/利润/净资产增长率", {},
                                tags=["成长", "增长率", "营收", "利润"], usage_scenario="成长性评估"),
    "profitability_metrics": SkillInfo("profitability_metrics", "盈利能力指标", "基本面分析",
                                       "vibe_29_agents", "profitability_agent",
                                       "毛利率/净利率/ROE/ROA/ROIC", {},
                                       tags=["盈利", "ROE", "ROA", "毛利率"], usage_scenario="盈利能力"),
    "cashflow_metrics": SkillInfo("cashflow_metrics", "现金流指标", "基本面分析",
                                  "vibe_29_agents", "cashflow_agent",
                                  "自由现金流/经营现金流", {},
                                  tags=["现金流", "FCF", "经营"], usage_scenario="现金流质量"),
    "dividend_metrics": SkillInfo("dividend_metrics", "分红指标", "基本面分析",
                                  "vibe_29_agents", "dividend_agent",
                                  "股息率/分红稳定性/增长", {},
                                  tags=["分红", "股息", "红利"], usage_scenario="分红收益"),
    "sector_analysis": SkillInfo("sector_analysis", "行业比较分析", "基本面分析",
                                 "vibe_29_agents", "sector_rotation_agent",
                                 "行业对比/轮动/强弱", {},
                                 tags=["行业", "对比", "轮动", "板块"], usage_scenario="行业选择"),
    "competitor_analysis": SkillInfo("competitor_analysis", "竞争对手分析", "基本面分析",
                                     "vibe_29_agents", "valuation_agent",
                                     "同行业公司对比分析", {},
                                     tags=["竞争", "对比", "同行", "市场份额"], usage_scenario="竞争优势"),

    # ===== 舆情类（5项）=====
    "news_sentiment_analysis": SkillInfo("news_sentiment_analysis", "新闻情感分析", "舆情分析",
                                         "vibe_29_agents", "news_sentiment_agent",
                                         "新闻情感/利好利空/热度", {},
                                         tags=["新闻", "情感", "利好", "利空"], usage_scenario="新闻影响"),
    "social_media_heat": SkillInfo("social_media_heat", "社交媒体热度", "舆情分析",
                                   "vibe_29_agents", "social_media_agent",
                                   "讨论量/关注度/情绪指数", {},
                                   tags=["社交", "热度", "讨论", "关注"], usage_scenario="市场关注度"),
    "north_bound_flow": SkillInfo("north_bound_flow", "北向资金分析", "舆情分析",
                                  "vibe_29_agents", "money_flow_agent",
                                  "北向资金/龙虎榜/大宗交易", {},
                                  tags=["北向", "资金", "龙虎榜", "机构"], usage_scenario="外资动向"),
    "market_sentiment_index": SkillInfo("market_sentiment_index", "市场情绪指数", "舆情分析",
                                        "vibe_29_agents", "market_sentiment_agent",
                                        "涨跌比/恐慌指数/市场宽度", {},
                                        tags=["情绪", "恐慌", "贪婪", "涨跌比"], usage_scenario="市场情绪"),
    "sector_rotation_signal": SkillInfo("sector_rotation_signal", "板块轮动信号", "舆情分析",
                                        "vibe_29_agents", "sector_rotation_agent",
                                        "行业轮动/板块强弱", {},
                                        tags=["板块", "轮动", "热点", "切换"], usage_scenario="板块轮动"),

    # ===== 风控类（3项）=====
    "risk_metrics": SkillInfo("risk_metrics", "风险指标", "风控管理",
                              "vibe_29_agents", "risk_assessment_agent",
                              "VaR/MaxDD/波动率/相关性", {},
                              tags=["风险", "VaR", "回撤", "波动"], usage_scenario="风险评估"),
    "position_sizing": SkillInfo("position_sizing", "仓位计算", "风控管理",
                                 "vibe_29_agents", "position_management_agent",
                                 "凯利公式/风险预算/仓位建议", {},
                                 tags=["仓位", "凯利", "资金管理"], usage_scenario="仓位管理"),
    "stop_loss_atr": SkillInfo("stop_loss_atr", "ATR止损位", "风控管理",
                               "vibe_29_agents", "stop_loss_agent",
                               "基于ATR的动态止损/止盈位", {},
                               tags=["止损", "ATR", "动态", "保护"], usage_scenario="止损设置"),

    # ===== Trae-cn开发工具（13项）=====
    "trae_architecture_designer": SkillInfo("trae_architecture_designer", "架构设计师(Trae)", "Trae-cn开发工具",
                                            "expert_team_bridge", "trae_skill_architecture",
                                            "设计高可用、可扩展、易维护的系统架构，输出架构图、技术选型、模块划分与部署方案",
                                            {}, tags=["架构", "设计", "技术选型", "部署", "模块"], usage_scenario="系统架构设计"),
    "trae_auto_resolver": SkillInfo("trae_auto_resolver", "自主攻坚器(Trae)", "Trae-cn开发工具",
                                    "expert_team_bridge", "trae_skill_auto_resolve",
                                    "自主拆解任务、多方案并行尝试、自动验证结果、自我纠错、持续攻坚直到目标完成",
                                    {}, tags=["自主", "攻坚", "纠错", "验证", "并行"], usage_scenario="复杂任务自主完成"),
    "trae_code_reviewer": SkillInfo("trae_code_reviewer", "代码审查器(Trae)", "Trae-cn开发工具",
                                    "expert_team_bridge", "trae_skill_code_review",
                                    "自动审查代码，识别逻辑错误、安全漏洞、性能问题和规范问题，并给出修复建议",
                                    {}, tags=["审查", "代码", "安全", "性能", "规范"], usage_scenario="代码审查"),
    "trae_doc_writer": SkillInfo("trae_doc_writer", "文档生成器(Trae)", "Trae-cn开发工具",
                                 "expert_team_bridge", "trae_skill_doc_write",
                                 "自动生成或更新项目README、API文档、模块说明，支持增量更新",
                                 {}, tags=["文档", "README", "API", "生成", "更新"], usage_scenario="文档自动生成"),
    "trae_git_commit_gen": SkillInfo("trae_git_commit_gen", "Git提交生成器(Trae)", "Trae-cn开发工具",
                                     "expert_team_bridge", "trae_skill_git_commit",
                                     "分析代码变更，自动生成符合Conventional Commits规范的Git提交信息",
                                     {}, tags=["Git", "Commit", "提交", "规范", "版本"], usage_scenario="Git提交信息生成"),
    "trae_quant_risk_checker": SkillInfo("trae_quant_risk_checker", "量化风控检查器(Trae)", "Trae-cn开发工具",
                                         "expert_team_bridge", "trae_skill_quant_risk",
                                         "校验量化交易策略代码的风控逻辑，检查仓位、止损、止盈、异常交易等规则",
                                         {}, tags=["量化", "风控", "止损", "仓位", "异常"], usage_scenario="策略风控校验"),
    "trae_unit_test_gen": SkillInfo("trae_unit_test_gen", "单元测试生成器(Trae)", "Trae-cn开发工具",
                                    "expert_team_bridge", "trae_skill_unit_test",
                                    "自动为指定代码生成完整单元测试用例，覆盖正常场景、边界值与异常情况",
                                    {}, tags=["测试", "单元", "覆盖", "边界", "异常"], usage_scenario="单元测试生成"),
    "trae_pr_code_review": SkillInfo("trae_pr_code_review", "PR代码审查(Trae)", "Trae-cn开发工具",
                                     "expert_team_bridge", "trae_skill_pr_review",
                                     "按风险优先级审查PR：逻辑漏洞>边界条件>回归风险>测试覆盖",
                                     {}, tags=["PR", "审查", "合并", "风险", "回归"], usage_scenario="PR合并前审查"),
    "trae_code_simplifier": SkillInfo("trae_code_simplifier", "代码简化器(Trae)", "Trae-cn开发工具",
                                      "expert_team_bridge", "trae_skill_code_simplify",
                                      "代码复杂度过高、重复逻辑、命名混乱时使用，不改变外部行为，只做结构性优化",
                                      {}, tags=["简化", "重构", "优化", "命名", "结构"], usage_scenario="代码结构优化"),
    "trae_debugger": SkillInfo("trae_debugger", "调试器(Trae)", "Trae-cn开发工具",
                               "expert_team_bridge", "trae_skill_debug",
                               "当用户报告错误、异常、报错日志时使用，按标准流程定位根因并给出最小修复方案",
                               {}, tags=["调试", "错误", "异常", "根因", "修复"], usage_scenario="Bug定位与修复"),
    "trae_explore": SkillInfo("trae_explore", "项目探索器(Trae)", "Trae-cn开发工具",
                              "expert_team_bridge", "trae_skill_explore",
                              "了解项目结构、梳理代码架构、寻找入口或核心文件",
                              {}, tags=["探索", "结构", "架构", "入口", "核心"], usage_scenario="项目结构分析"),
    "trae_security_review": SkillInfo("trae_security_review", "安全审查器(Trae)", "Trae-cn开发工具",
                                      "expert_team_bridge", "trae_skill_security",
                                      "上线前全域安全边界扫描，覆盖鉴权、密钥、注入防御、隐私支付、依赖配置",
                                      {}, tags=["安全", "扫描", "鉴权", "密钥", "注入"], usage_scenario="上线前安全扫描"),
    "trae_test_engineer": SkillInfo("trae_test_engineer", "测试工程师(Trae)", "Trae-cn开发工具",
                                    "expert_team_bridge", "trae_skill_test_engineer",
                                    "功能开发完成后，确保关键路径有测试覆盖，判断哪些测试最值得补",
                                    {}, tags=["测试", "覆盖", "关键路径", "质量", "验证"], usage_scenario="测试策略规划"),
}

# ============================================================
# 查询与匹配函数
# ============================================================

def get_agent(agent_id: str) -> Optional[AgentInfo]:
    """按ID获取Agent"""
    return AGENT_REGISTRY.get(agent_id)

def get_agents_by_group(group: str) -> List[AgentInfo]:
    """按分组获取Agent列表"""
    return [a for a in AGENT_REGISTRY.values() if a.group == group]

def get_agents_by_tags(tags: List[str]) -> List[AgentInfo]:
    """按标签匹配Agent（交集匹配）"""
    tag_set = set(t.lower() for t in tags)
    return [a for a in AGENT_REGISTRY.values()
            if tag_set & set(t.lower() for t in a.tags)]

def get_agents_by_keyword(keyword: str) -> List[AgentInfo]:
    """按关键词模糊搜索Agent"""
    kw = keyword.lower()
    results = []
    for a in AGENT_REGISTRY.values():
        if kw in a.name.lower() or kw in a.description.lower() or \
           any(kw in t.lower() for t in a.tags) or kw in a.group.lower():
            results.append(a)
    return results

def get_all_groups() -> List[str]:
    """获取所有分组"""
    return sorted(set(a.group for a in AGENT_REGISTRY.values()))

def get_all_agents() -> List[AgentInfo]:
    """获取所有Agent"""
    return list(AGENT_REGISTRY.values())

def get_skill(skill_id: str) -> Optional[SkillInfo]:
    """按ID获取技能"""
    return SKILL_REGISTRY.get(skill_id)

def get_skills_by_category(category: str) -> List[SkillInfo]:
    """按分类获取技能"""
    return [s for s in SKILL_REGISTRY.values() if s.category == category]

def get_skills_by_tags(tags: List[str]) -> List[SkillInfo]:
    """按标签匹配技能"""
    tag_set = set(t.lower() for t in tags)
    return [s for s in SKILL_REGISTRY.values()
            if tag_set & set(t.lower() for t in s.tags)]

def get_skills_by_keyword(keyword: str) -> List[SkillInfo]:
    """按关键词模糊搜索技能"""
    kw = keyword.lower()
    results = []
    for s in SKILL_REGISTRY.values():
        if kw in s.name.lower() or kw in s.description.lower() or \
           any(kw in t.lower() for t in s.tags) or kw in s.category.lower():
            results.append(s)
    return results

def get_all_categories() -> List[str]:
    """获取所有技能分类"""
    return sorted(set(s.category for s in SKILL_REGISTRY.values()))

def get_all_skills() -> List[SkillInfo]:
    """获取所有技能"""
    return list(SKILL_REGISTRY.values())

def get_agent_skills(agent_id: str) -> List[SkillInfo]:
    """获取Agent依赖的技能列表"""
    agent = AGENT_REGISTRY.get(agent_id)
    if not agent:
        return []
    return [s for s in SKILL_REGISTRY.values() if s.skill_id in agent.dependencies]

# ============================================================
# 注册表统计
# ============================================================

def get_registry_stats() -> Dict:
    """获取注册表统计信息"""
    agent_groups = {}
    for a in AGENT_REGISTRY.values():
        agent_groups.setdefault(a.group, 0)
        agent_groups[a.group] += 1

    skill_categories = {}
    for s in SKILL_REGISTRY.values():
        skill_categories.setdefault(s.category, 0)
        skill_categories[s.category] += 1

    return {
        "total_agents": len(AGENT_REGISTRY),
        "agent_groups": agent_groups,
        "total_skills": len(SKILL_REGISTRY),
        "skill_categories": skill_categories,
    }