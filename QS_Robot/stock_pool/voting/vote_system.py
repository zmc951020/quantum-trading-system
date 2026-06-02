#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 投票表决系统
"""
from typing import List, Dict, Any
import uuid
from datetime import datetime, timedelta
from stock_pool.core.models import Stock, Strategy, EvaluationResult, VoteResult


class ExpertAgent:
    """专家智能体"""
    
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        """评估股票-策略组合"""
        raise NotImplementedError("子类必须实现evaluate方法")


class DataQualityAgent(ExpertAgent):
    """数据质量专家"""
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        score = 100
        
        # 检查数据完整性
        if stock.price == 0:
            score -= 30
        if stock.pe == 0:
            score -= 10
        if stock.volume == 0:
            score -= 20
        
        # 检查数据合理性
        if stock.pe < 0 or stock.pe > 100:
            score -= 15
        if stock.pb < 0 or stock.pb > 20:
            score -= 10
        
        return {
            'agent': self.name,
            'role': self.role,
            'score': max(0, score),
            'reasons': self._get_reasons(stock, score)
        }
    
    def _get_reasons(self, stock: Stock, score: int) -> List[str]:
        reasons = []
        if stock.price == 0:
            reasons.append("价格数据缺失")
        if stock.volume == 0:
            reasons.append("成交量数据缺失")
        if stock.pe < 0 or stock.pe > 100:
            reasons.append("PE值异常")
        if score >= 80:
            reasons.append("数据质量良好")
        return reasons


class StrategyValidator(ExpertAgent):
    """策略验证专家"""
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        score = 0
        
        # 波动率匹配
        vol_mapping = {'low': 0.02, 'medium': 0.05, 'high': 0.1}
        target_vol = vol_mapping.get(strategy.volatility_profile, 0.05)
        vol_diff = abs(stock.volatility - target_vol)
        if vol_diff < 0.03:
            score += 30
        elif vol_diff < 0.05:
            score += 20
        else:
            score += 10
        
        # 趋势匹配
        trend_diff = abs(stock.trend_strength - strategy.ideal_trend)
        if trend_diff < 0.2:
            score += 30
        elif trend_diff < 0.4:
            score += 20
        else:
            score += 10
        
        # 流动性匹配
        if stock.volume >= strategy.min_liquidity:
            score += 40
        else:
            score += min(40, stock.volume / strategy.min_liquidity * 40)
        
        return {
            'agent': self.name,
            'role': self.role,
            'score': round(score, 2),
            'reasons': self._get_reasons(stock, strategy, score)
        }
    
    def _get_reasons(self, stock: Stock, strategy: Strategy, score: int) -> List[str]:
        reasons = []
        if stock.volume >= strategy.min_liquidity:
            reasons.append("流动性充足")
        else:
            reasons.append("流动性不足")
        if score >= 70:
            reasons.append("策略匹配度高")
        elif score >= 50:
            reasons.append("策略匹配度中等")
        else:
            reasons.append("策略匹配度低")
        return reasons


class RiskAssessor(ExpertAgent):
    """风险评估专家"""
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        score = 100
        
        # 市场风险
        if stock.volatility > 0.1:
            score -= min(30, (stock.volatility - 0.1) * 300)
        
        # 流动性风险
        if stock.volume < 30000000:
            score -= min(25, (30000000 - stock.volume) / 300000)
        
        # 估值风险
        if stock.pe > 50:
            score -= min(20, (stock.pe - 50) * 0.5)
        
        return {
            'agent': self.name,
            'role': self.role,
            'score': max(0, round(score, 2)),
            'reasons': self._get_reasons(stock, score)
        }
    
    def _get_reasons(self, stock: Stock, score: int) -> List[str]:
        reasons = []
        if stock.volatility > 0.1:
            reasons.append("波动率较高")
        if stock.volume < 30000000:
            reasons.append("流动性风险")
        if stock.pe > 50:
            reasons.append("估值偏高")
        if score >= 70:
            reasons.append("风险可控")
        return reasons


class ComplianceOfficer(ExpertAgent):
    """合规专家"""
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        checks = []
        
        # 交易限制检查
        if stock.code.startswith('688'):  # 科创板
            checks.append(('科创板股票', True, '符合要求'))
        elif stock.code.startswith('300'):  # 创业板
            checks.append(('创业板股票', True, '符合要求'))
        else:
            checks.append(('主板股票', True, '符合要求'))
        
        # 停牌检查（假设没有停牌数据）
        checks.append(('交易状态', True, '正常交易'))
        
        passed = all(c[1] for c in checks)
        
        return {
            'agent': self.name,
            'role': self.role,
            'score': 100 if passed else 0,
            'passed': passed,
            'checks': checks
        }


class ExpertAgentSystem:
    """专家智能体系统"""
    
    def __init__(self):
        self.agents = [
            DataQualityAgent("数据质量专家", "data_quality"),
            StrategyValidator("策略验证专家", "strategy_validator"),
            RiskAssessor("风险评估专家", "risk_assessor"),
            ComplianceOfficer("合规专家", "compliance_officer")
        ]
    
    def evaluate(self, stock: Stock, strategy: Strategy) -> Dict[str, Any]:
        """多专家综合评估"""
        evaluations = {}
        
        for agent in self.agents:
            result = agent.evaluate(stock, strategy)
            evaluations[agent.role] = result
        
        # 检查合规
        compliance_passed = evaluations['compliance_officer']['passed']
        
        # 计算综合评分
        composite_score = self._calculate_composite_score(evaluations)
        
        return {
            'stock': stock,
            'strategy': strategy,
            'evaluations': evaluations,
            'composite_score': round(composite_score, 2),
            'compliance_passed': compliance_passed,
            'passed': compliance_passed and composite_score >= 70
        }
    
    def _calculate_composite_score(self, evaluations: Dict[str, Any]) -> float:
        """计算综合评分"""
        weights = {
            'data_quality': 0.2,
            'strategy_validator': 0.35,
            'risk_assessor': 0.35,
            'compliance_officer': 0.1
        }
        
        score = 0
        for role, weight in weights.items():
            score += evaluations[role]['score'] * weight
        
        return score


class VotingSystem:
    """投票表决系统"""
    
    def __init__(self):
        self.proposals = {}
        self.quorum = 3
        self.threshold = 0.6
    
    def create_proposal(self, stock: Stock, strategy: Strategy) -> VoteResult:
        """创建提案"""
        proposal_id = str(uuid.uuid4())
        
        # 先进行专家评估
        expert_system = ExpertAgentSystem()
        evaluation = expert_system.evaluate(stock, strategy)
        
        proposal = VoteResult(
            proposal_id=proposal_id,
            stock=stock,
            strategy=strategy,
            votes=[],
            status='pending',
            deadline=datetime.now() + timedelta(hours=24),
            quorum=self.quorum,
            threshold=self.threshold
        )
        
        self.proposals[proposal_id] = {
            'vote_result': proposal,
            'evaluation': evaluation
        }
        
        return proposal
    
    def vote(self, proposal_id: str, voter: str, decision: str, reason: str = "") -> VoteResult:
        """投票"""
        if proposal_id not in self.proposals:
            raise ValueError("提案不存在")
        
        proposal = self.proposals[proposal_id]['vote_result']
        
        # 检查是否已投票
        for vote in proposal.votes:
            if vote['voter'] == voter:
                raise ValueError("该投票者已投票")
        
        # 添加投票
        proposal.votes.append({
            'voter': voter,
            'decision': decision,
            'reason': reason,
            'timestamp': datetime.now()
        })
        
        # 检查是否达到法定人数
        if len(proposal.votes) >= proposal.quorum:
            self._count_votes(proposal)
        
        return proposal
    
    def _count_votes(self, proposal: VoteResult):
        """计票"""
        yes_votes = sum(1 for v in proposal.votes if v['decision'] == 'yes')
        total_votes = len(proposal.votes)
        
        if yes_votes / total_votes >= proposal.threshold:
            proposal.status = 'approved'
        elif datetime.now() > proposal.deadline:
            proposal.status = 'rejected'
    
    def get_proposal(self, proposal_id: str) -> dict:
        """获取提案详情"""
        if proposal_id not in self.proposals:
            return None
        return self.proposals[proposal_id]
    
    def list_proposals(self, status: str = None) -> List[dict]:
        """列出提案"""
        result = []
        for pid, data in self.proposals.items():
            if status is None or data['vote_result'].status == status:
                result.append(data)
        return result