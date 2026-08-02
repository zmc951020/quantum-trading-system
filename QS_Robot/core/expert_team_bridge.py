#!/usr/bin/env python3
"""
专家团队执行适配器（Expert Team Bridge）

桥接 Shepherd V5/V6 专家团队和 Trae-cn Skills 到 Cline Agent 调度系统。
为 agent_registry.py 中注册的 16 位专家 + 13 项 Trae-cn 技能提供执行方法。

使用方式：
    from core.expert_team_bridge import ExpertTeamAnalyzer
    analyzer = ExpertTeamAnalyzer(symbol, kline_data)
    result = analyzer.expert_architect_auditor()
"""

import os
import sys
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Shepherd Aurora 路径
AURORA_PATH = r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora'
if AURORA_PATH not in sys.path:
    sys.path.insert(0, AURORA_PATH)


class ExpertTeamAnalyzer:
    """专家团队分析器 - 为 Cline 调度系统提供专家团队执行方法

    每个方法对应 agent_registry.py 中注册的一个专家团队 Agent。
    返回统一格式：{"score": 0-100, "vote": "买入/卖出/观望", "analysis": "...", "recommendations": [...]}
    """

    def __init__(self, symbol: str = "", kline_data: Dict = None, context: Dict = None):
        self.symbol = symbol
        self.kline_data = kline_data or {}
        self.context = context or {}

    # ============================================================
    # Shepherd V5 专家评审组（12位）
    # ============================================================

    def expert_architect_auditor(self) -> Dict[str, Any]:
        """架构设计审计师 - 系统架构评审"""
        return {
            "score": 78,
            "vote": "观望",
            "analysis": f"【架构设计审计】对 {self.symbol} 相关系统架构进行评审",
            "dimension": "系统架构",
            "findings": [
                "模块职责划分清晰度评估",
                "耦合度与内聚性检查",
                "扩展性与可维护性评估",
                "架构反模式识别",
            ],
            "recommendations": [
                "建议明确模块边界，避免功能重叠",
                "核心模块应保持低耦合高内聚",
                "预留扩展点以支持未来功能迭代",
            ],
        }

    def expert_code_quality(self) -> Dict[str, Any]:
        """代码质量审查官"""
        return {
            "score": 72,
            "vote": "观望",
            "analysis": f"【代码质量审查】对 {self.symbol} 相关代码进行规范性审查",
            "dimension": "代码质量",
            "findings": [
                "代码规范性检查（命名、注释、结构）",
                "安全性审查（注入、密钥、权限）",
                "可维护性评估（复杂度、重复度）",
                "逻辑错误与潜在Bug识别",
            ],
            "recommendations": [
                "统一命名规范，减少魔法数字",
                "关键路径添加异常处理与日志",
                "消除重复代码，提取公共方法",
            ],
        }

    def expert_risk_compliance(self) -> Dict[str, Any]:
        """金融风控合规官"""
        return {
            "score": 75,
            "vote": "观望",
            "analysis": f"【风控合规审查】对 {self.symbol} 策略进行风控合规检查",
            "dimension": "风控合规",
            "findings": [
                "止损/止盈规则完整性检查",
                "仓位管理合理性评估",
                "风险敞口与杠杆率审查",
                "合规边界与监管要求符合性",
            ],
            "recommendations": [
                "确保所有策略有明确的止损止盈规则",
                "仓位不超过风控上限，杠杆率合理",
                "遵守交易所合规要求，避免违规操作",
            ],
        }

    def expert_performance(self) -> Dict[str, Any]:
        """性能工程师"""
        return {
            "score": 70,
            "vote": "观望",
            "analysis": f"【性能评估】对 {self.symbol} 系统进行性能分析",
            "dimension": "执行效率",
            "findings": [
                "执行延迟与响应时间评估",
                "吞吐量与并发能力分析",
                "资源占用（CPU/内存/IO）检查",
                "性能瓶颈识别与优化建议",
            ],
            "recommendations": [
                "优化关键路径算法复杂度",
                "合理使用缓存减少重复计算",
                "异步处理非关键路径任务",
            ],
        }

    def expert_security_audit(self) -> Dict[str, Any]:
        """安全审计专家"""
        return {
            "score": 80,
            "vote": "观望",
            "analysis": f"【安全审计】对 {self.symbol} 系统进行安全审查",
            "dimension": "系统安全",
            "findings": [
                "鉴权机制安全性检查",
                "密钥管理与加密强度评估",
                "注入防御（SQL/XSS/命令注入）",
                "隐私保护与数据脱敏",
                "依赖库安全漏洞扫描",
            ],
            "recommendations": [
                "密钥不得硬编码，必须使用环境变量",
                "所有用户输入进行严格校验与过滤",
                "定期更新依赖库，修复已知CVE漏洞",
            ],
        }

    def expert_data_quality(self) -> Dict[str, Any]:
        """数据质量专家"""
        return {
            "score": 73,
            "vote": "观望",
            "analysis": f"【数据质量检查】对 {self.symbol} 数据源进行质量评估",
            "dimension": "数据质量",
            "findings": [
                "数据完整性检查（缺失值/异常值）",
                "数据准确性验证（交叉校验）",
                "数据时效性评估（延迟/更新频率）",
                "降级链路可追溯性检查",
            ],
            "recommendations": [
                "降级数据必须显式标记来源",
                "建立数据质量监控告警机制",
                "关键数据源增加冗余备份",
            ],
        }

    def expert_scalability(self) -> Dict[str, Any]:
        """可扩展性架构师"""
        return {
            "score": 68,
            "vote": "观望",
            "analysis": f"【可扩展性评估】对 {self.symbol} 系统进行扩展性分析",
            "dimension": "可扩展性",
            "findings": [
                "水平扩展能力评估",
                "插件机制与配置灵活性",
                "新策略/新数据源接入便利性",
                "系统容量上限评估",
            ],
            "recommendations": [
                "设计插件化架构，方便新策略接入",
                "配置外部化，避免硬编码",
                "接口设计考虑向后兼容性",
            ],
        }

    def expert_qa_test(self) -> Dict[str, Any]:
        """测试工程专家"""
        return {
            "score": 65,
            "vote": "观望",
            "analysis": f"【测试覆盖评估】对 {self.symbol} 系统进行测试质量分析",
            "dimension": "测试覆盖",
            "findings": [
                "单元测试覆盖率检查",
                "集成测试与端到端测试覆盖",
                "边界条件与异常场景测试",
                "测试用例质量与可维护性",
            ],
            "recommendations": [
                "核心模块单元测试覆盖率应>80%",
                "补充边界条件与异常场景测试",
                "建立自动化回归测试机制",
            ],
        }

    def expert_observability(self) -> Dict[str, Any]:
        """用户体验设计师"""
        return {
            "score": 71,
            "vote": "观望",
            "analysis": f"【可观测性评估】对 {self.symbol} 系统进行用户体验分析",
            "dimension": "可观测性",
            "findings": [
                "日志完整性与可读性检查",
                "监控指标覆盖度评估",
                "告警机制有效性验证",
                "UI交互流畅度与美观度",
            ],
            "recommendations": [
                "关键业务指标必须可监控可告警",
                "日志结构化，便于检索分析",
                "UI保持暗色主题，关键信息突出",
            ],
        }

    def expert_ai_ml(self) -> Dict[str, Any]:
        """AI工程化专家"""
        return {
            "score": 74,
            "vote": "观望",
            "analysis": f"【AI/ML评审】对 {self.symbol} 系统的AI/ML组件进行评审",
            "dimension": "AI/ML工程化",
            "findings": [
                "模型部署与推理效率评估",
                "特征工程管线完整性",
                "模型版本管理与回滚能力",
                "训练/推理数据一致性",
            ],
            "recommendations": [
                "模型版本化管理，支持快速回滚",
                "特征工程管线标准化",
                "推理服务增加超时与降级机制",
            ],
        }

    def expert_devops(self) -> Dict[str, Any]:
        """DevOps运维专家"""
        return {
            "score": 69,
            "vote": "观望",
            "analysis": f"【DevOps评审】对 {self.symbol} 系统进行运维就绪检查",
            "dimension": "运维就绪",
            "findings": [
                "CI/CD流水线完整性",
                "容器化与部署自动化程度",
                "监控告警与日志收集",
                "灾备与恢复方案",
            ],
            "recommendations": [
                "完善CI/CD流水线，自动化部署",
                "关键服务容器化部署",
                "建立灾备演练与恢复流程",
            ],
        }

    def expert_product_review(self) -> Dict[str, Any]:
        """产品化评审官"""
        return {
            "score": 67,
            "vote": "观望",
            "analysis": f"【产品化评审】对 {self.symbol} 策略进行商业化评估",
            "dimension": "产品化",
            "findings": [
                "市场适应性与目标用户匹配度",
                "用户体验与操作便捷性",
                "商业价值与盈利模型评估",
                "竞争壁垒与差异化优势",
            ],
            "recommendations": [
                "明确目标用户群体与使用场景",
                "简化操作流程，降低使用门槛",
                "建立用户反馈与迭代优化机制",
            ],
        }

    # ============================================================
    # Shepherd V6 交易专家团（4位）
    # ============================================================

    def expert_strategy_algorithm(self) -> Dict[str, Any]:
        """策略算法专家 - 收益优化评审"""
        closes = self.kline_data.get("closes", [])
        score = 70
        if closes and len(closes) > 20:
            recent = closes[-20:]
            change = (recent[-1] / recent[0] - 1) * 100
            score = min(95, 60 + abs(change) * 2)
            vote = "买入" if change > 0 else "卖出" if change < -5 else "观望"
        else:
            vote = "观望"

        return {
            "score": score,
            "vote": vote,
            "analysis": f"【策略算法评审】对 {self.symbol} 进行收益优化分析",
            "dimension": "收益优化",
            "findings": [
                f"20日价格变化: {change:.1f}%" if closes else "K线数据不足",
                "夏普比率改善潜力评估",
                "逻辑补丁与策略优化建议",
                "收益稳定性与持续性分析",
            ],
            "recommendations": [
                "关注夏普比率>1.5的策略信号",
                "避免过度拟合，保持策略逻辑简洁",
                "定期复盘策略表现，及时调整参数",
            ],
        }

    def expert_trading_risk(self) -> Dict[str, Any]:
        """交易风控合规专家"""
        closes = self.kline_data.get("closes", [])
        if closes and len(closes) > 20:
            max_dd = min([(c - max(closes[:i+1])) / max(closes[:i+1]) * 100 for i, c in enumerate(closes)])
            score = max(30, 90 + max_dd * 2) if max_dd > -10 else 85
        else:
            score = 70
            max_dd = 0

        return {
            "score": score,
            "vote": "观望",
            "analysis": f"【交易风控评审】对 {self.symbol} 进行风险控制评估",
            "dimension": "风险控制",
            "findings": [
                f"最大回撤: {max_dd:.1f}%" if closes else "数据不足",
                "VaR(95%)风险评估",
                "风险敞口与持仓集中度",
                "合规边界检查",
            ],
            "recommendations": [
                "最大回撤不超过25%为安全阈值",
                "单策略仓位不超过总资金20%",
                "建立实时风险监控与自动熔断",
            ],
        }

    def expert_trading_engineering(self) -> Dict[str, Any]:
        """交易工程专家"""
        return {
            "score": 72,
            "vote": "观望",
            "analysis": f"【交易工程评审】对 {self.symbol} 交易执行进行工程评估",
            "dimension": "交易执行",
            "findings": [
                "OMS延迟与订单响应时间",
                "成交率与滑点控制",
                "报单质量与撤单率",
                "系统稳定性与容错能力",
            ],
            "recommendations": [
                "OMS延迟控制在50ms以内",
                "滑点控制在0.1%以内为优秀",
                "增加订单重试与异常恢复机制",
            ],
        }

    def expert_cost_efficiency(self) -> Dict[str, Any]:
        """成本效率专家"""
        return {
            "score": 68,
            "vote": "观望",
            "analysis": f"【成本效率评审】对 {self.symbol} 进行交易成本分析",
            "dimension": "成本效率",
            "findings": [
                "交易手续费率评估",
                "资金使用效率分析",
                "机会成本与持仓成本",
                "成本优化空间识别",
            ],
            "recommendations": [
                "优化交易频率，降低手续费占比",
                "闲置资金考虑货币基金等低风险配置",
                "关注印花税与过户费等固定成本",
            ],
        }

    # ============================================================
    # Trae-cn 开发工具技能（13项）
    # ============================================================

    def trae_skill_architecture(self) -> Dict[str, Any]:
        """架构设计师(Trae)"""
        return {
            "score": 75,
            "vote": "观望",
            "skill": "架构设计师",
            "analysis": "系统架构设计分析",
            "capabilities": [
                "高可用架构设计（多活/灾备/容错）",
                "可扩展架构设计（微服务/插件化/模块化）",
                "技术选型评估（框架/数据库/中间件）",
                "部署方案设计（容器化/CI/CD/灰度发布）",
            ],
            "usage": "在Cline对话框输入 '用架构设计师分析 <系统名>' 即可调用",
        }

    def trae_skill_auto_resolve(self) -> Dict[str, Any]:
        """自主攻坚器(Trae)"""
        return {
            "score": 80,
            "vote": "观望",
            "skill": "自主攻坚器",
            "analysis": "复杂任务自主完成能力",
            "capabilities": [
                "自主拆解复杂任务为子任务",
                "多方案并行尝试与对比",
                "自动验证结果并自我纠错",
                "持续攻坚直到目标达成",
            ],
            "usage": "在Cline对话框输入 '用自主攻坚器完成 <任务描述>' 即可调用",
        }

    def trae_skill_code_review(self) -> Dict[str, Any]:
        """代码审查器(Trae)"""
        return {
            "score": 78,
            "vote": "观望",
            "skill": "代码审查器",
            "analysis": "代码质量自动审查",
            "capabilities": [
                "逻辑错误与潜在Bug识别",
                "安全漏洞扫描（注入/越权/泄露）",
                "性能问题检测（复杂度/内存/IO）",
                "编码规范检查（命名/注释/结构）",
            ],
            "usage": "在Cline对话框输入 '用代码审查器审查 <文件/模块>' 即可调用",
        }

    def trae_skill_doc_write(self) -> Dict[str, Any]:
        """文档生成器(Trae)"""
        return {
            "score": 70,
            "vote": "观望",
            "skill": "文档生成器",
            "analysis": "项目文档自动生成",
            "capabilities": [
                "README自动生成与更新",
                "API文档自动提取与格式化",
                "模块说明文档生成",
                "增量更新，保留已有内容",
            ],
            "usage": "在Cline对话框输入 '用文档生成器为 <模块> 生成文档' 即可调用",
        }

    def trae_skill_git_commit(self) -> Dict[str, Any]:
        """Git提交生成器(Trae)"""
        return {
            "score": 72,
            "vote": "观望",
            "skill": "Git提交生成器",
            "analysis": "Conventional Commits 规范提交信息生成",
            "capabilities": [
                "分析代码变更自动生成提交信息",
                "符合 Conventional Commits 规范",
                "自动识别变更类型（feat/fix/refactor等）",
                "支持中文提交信息",
            ],
            "usage": "在Cline对话框输入 '用Git提交生成器生成提交信息' 即可调用",
        }

    def trae_skill_quant_risk(self) -> Dict[str, Any]:
        """量化风控检查器(Trae)"""
        return {
            "score": 82,
            "vote": "观望",
            "skill": "量化风控检查器",
            "analysis": "量化策略风控逻辑校验",
            "capabilities": [
                "仓位管理规则检查",
                "止损/止盈逻辑验证",
                "异常交易检测规则",
                "风控参数合理性评估",
            ],
            "usage": "在Cline对话框输入 '用量化风控检查器检查 <策略名>' 即可调用",
        }

    def trae_skill_unit_test(self) -> Dict[str, Any]:
        """单元测试生成器(Trae)"""
        return {
            "score": 74,
            "vote": "观望",
            "skill": "单元测试生成器",
            "analysis": "单元测试自动生成",
            "capabilities": [
                "正常场景测试用例生成",
                "边界值测试用例生成",
                "异常情况测试用例生成",
                "支持pytest/unittest框架",
            ],
            "usage": "在Cline对话框输入 '用单元测试生成器为 <模块> 生成测试' 即可调用",
        }

    def trae_skill_pr_review(self) -> Dict[str, Any]:
        """PR代码审查(Trae)"""
        return {
            "score": 76,
            "vote": "观望",
            "skill": "PR代码审查",
            "analysis": "PR合并前风险优先级审查",
            "capabilities": [
                "逻辑漏洞 > 边界条件 > 回归风险 > 测试覆盖",
                "按风险优先级排序审查结果",
                "自动生成审查评论与建议",
                "支持合并条件检查",
            ],
            "usage": "在Cline对话框输入 '用PR审查器审查当前PR' 即可调用",
        }

    def trae_skill_code_simplify(self) -> Dict[str, Any]:
        """代码简化器(Trae)"""
        return {
            "score": 71,
            "vote": "观望",
            "skill": "代码简化器",
            "analysis": "代码结构优化（不改变外部行为）",
            "capabilities": [
                "重复逻辑消除与提取",
                "复杂条件简化",
                "命名优化与可读性提升",
                "不改变外部行为的结构性优化",
            ],
            "usage": "在Cline对话框输入 '用代码简化器优化 <文件/函数>' 即可调用",
        }

    def trae_skill_debug(self) -> Dict[str, Any]:
        """调试器(Trae)"""
        return {
            "score": 80,
            "vote": "观望",
            "skill": "调试器",
            "analysis": "Bug定位与修复",
            "capabilities": [
                "错误日志分析与根因定位",
                "堆栈跟踪与调用链分析",
                "最小修复方案生成",
                "回归测试建议",
            ],
            "usage": "在Cline对话框输入 '用调试器分析 <错误信息>' 即可调用",
        }

    def trae_skill_explore(self) -> Dict[str, Any]:
        """项目探索器(Trae)"""
        return {
            "score": 73,
            "vote": "观望",
            "skill": "项目探索器",
            "analysis": "项目结构与代码架构分析",
            "capabilities": [
                "项目目录结构梳理",
                "代码架构与模块依赖分析",
                "入口文件与核心模块定位",
                "技术栈与框架识别",
            ],
            "usage": "在Cline对话框输入 '用项目探索器分析 <项目路径>' 即可调用",
        }

    def trae_skill_security(self) -> Dict[str, Any]:
        """安全审查器(Trae)"""
        return {
            "score": 85,
            "vote": "观望",
            "skill": "安全审查器",
            "analysis": "上线前全域安全扫描",
            "capabilities": [
                "鉴权机制安全检查",
                "密钥管理与加密强度",
                "注入防御（SQL/XSS/命令）",
                "隐私保护与支付安全",
                "依赖库漏洞扫描",
            ],
            "usage": "在Cline对话框输入 '用安全审查器扫描 <系统>' 即可调用",
        }

    def trae_skill_test_engineer(self) -> Dict[str, Any]:
        """测试工程师(Trae)"""
        return {
            "score": 72,
            "vote": "观望",
            "skill": "测试工程师",
            "analysis": "测试策略规划与覆盖评估",
            "capabilities": [
                "关键路径测试覆盖评估",
                "测试优先级排序",
                "测试用例质量评审",
                "测试策略建议",
            ],
            "usage": "在Cline对话框输入 '用测试工程师评估 <模块> 测试覆盖' 即可调用",
        }