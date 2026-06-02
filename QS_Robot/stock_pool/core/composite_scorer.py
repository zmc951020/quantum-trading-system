#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 综合评分器
"""
from typing import Dict, Any
from stock_pool.core.models import EvaluationResult


class CompositeScorer:
    """综合评分器"""
    
    def __init__(self):
        self.weights = {
            'simulation': 0.40,
            'technical': 0.25,
            'risk': 0.20,
            'expert': 0.10,
            'compliance': 0.05
        }
    
    def calculate(self, evaluations: Dict[str, Any]) -> Dict[str, Any]:
        """计算综合评分"""
        # 合规检查是门槛条件
        if not evaluations.get('compliance', {}).get('passed', True):
            return {
                'score': 0,
                'passed': False,
                'reason': '合规检查未通过'
            }
        
        # 计算加权得分
        total_score = 0
        breakdown = {}
        
        for key, weight in self.weights.items():
            score = evaluations.get(key, {}).get('score', 0)
            breakdown[key] = {
                'score': score,
                'weight': weight,
                'contribution': round(score * weight, 2)
            }
            total_score += score * weight
        
        # 额外惩罚项：风险评分低于60分
        risk_score = evaluations.get('risk', {}).get('score', 100)
        if risk_score < 60:
            penalty = min(20, (60 - risk_score) * 0.5)
            total_score = max(0, total_score - penalty)
            breakdown['risk_penalty'] = round(penalty, 2)
        
        # 额外奖励项：模拟评分高于80分
        simulation_score = evaluations.get('simulation', {}).get('score', 0)
        if simulation_score >= 80:
            bonus = min(5, (simulation_score - 80) * 0.25)
            total_score = min(100, total_score + bonus)
            breakdown['simulation_bonus'] = round(bonus, 2)
        
        return {
            'score': round(total_score, 2),
            'passed': total_score >= 70,
            'breakdown': breakdown,
            'grade': self._get_grade(total_score)
        }
    
    def _get_grade(self, score: float) -> str:
        """获取评级"""
        if score >= 85:
            return '优秀'
        elif score >= 70:
            return '良好'
        elif score >= 60:
            return '观察'
        else:
            return '拒绝'


class PoolManager:
    """股票池管理器"""
    
    def __init__(self):
        self.pools = {
            'candidate': [],      # 候选池
            'classified': [],     # 分类池
            'watchlist': [],      # 监控池
            'adaptive': [],       # 策略适配池
            'trading': []         # 实盘池
        }
    
    def add_to_pool(self, stock, pool_type: str):
        """添加股票到指定池"""
        if pool_type not in self.pools:
            raise ValueError(f"未知的股票池类型: {pool_type}")
        
        # 检查是否已存在
        for existing in self.pools[pool_type]:
            if existing.code == stock.code:
                return False
        
        self.pools[pool_type].append(stock)
        return True
    
    def remove_from_pool(self, stock_code: str, pool_type: str):
        """从指定池移除股票"""
        if pool_type not in self.pools:
            raise ValueError(f"未知的股票池类型: {pool_type}")
        
        self.pools[pool_type] = [s for s in self.pools[pool_type] if s.code != stock_code]
    
    def get_pool(self, pool_type: str):
        """获取指定池的股票"""
        if pool_type not in self.pools:
            raise ValueError(f"未知的股票池类型: {pool_type}")
        return self.pools[pool_type]
    
    def move_between_pools(self, stock_code: str, from_pool: str, to_pool: str):
        """在池之间移动股票"""
        # 先从原池移除
        stock = None
        for s in self.pools.get(from_pool, []):
            if s.code == stock_code:
                stock = s
                break
        
        if stock is None:
            return False
        
        self.remove_from_pool(stock_code, from_pool)
        self.add_to_pool(stock, to_pool)
        return True
    
    def update_pool(self, pool_type: str, stocks):
        """更新池的股票列表"""
        if pool_type not in self.pools:
            raise ValueError(f"未知的股票池类型: {pool_type}")
        self.pools[pool_type] = stocks
    
    def get_pool_summary(self) -> Dict[str, Any]:
        """获取所有池的摘要"""
        summary = {}
        for pool_type, stocks in self.pools.items():
            summary[pool_type] = {
                'count': len(stocks),
                'stocks': [{'code': s.code, 'name': s.name} for s in stocks]
            }
        return summary