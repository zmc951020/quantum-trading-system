#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 智能筛选引擎
"""
from typing import List
from stock_pool.core.models import Stock


class LiquidityFilter:
    """流动性筛选器"""
    
    def __init__(self, min_volume: float = 50000000):
        self.min_volume = min_volume
    
    def filter(self, stocks: List[Stock]) -> List[Stock]:
        return [s for s in stocks if s.volume >= self.min_volume]


class FinancialFilter:
    """财务健康筛选器"""
    
    def __init__(self, pe_range: tuple = (0, 100), pb_range: tuple = (0, 20), min_roe: float = 0):
        self.pe_range = pe_range
        self.pb_range = pb_range
        self.min_roe = min_roe
    
    def filter(self, stocks: List[Stock]) -> List[Stock]:
        result = []
        for stock in stocks:
            pe_ok = self.pe_range[0] <= stock.pe <= self.pe_range[1]
            pb_ok = self.pb_range[0] <= stock.pb <= self.pb_range[1]
            roe_ok = stock.roe >= self.min_roe
            if pe_ok and pb_ok and roe_ok:
                result.append(stock)
        return result


class VolatilityFilter:
    """波动率筛选器"""
    
    def __init__(self, volatility_range: tuple = (0.01, 0.1)):
        self.volatility_range = volatility_range
    
    def filter(self, stocks: List[Stock]) -> List[Stock]:
        return [s for s in stocks if self.volatility_range[0] <= s.volatility <= self.volatility_range[1]]


class QualityFilter:
    """质量评分筛选器"""
    
    def __init__(self, min_score: float = 60):
        self.min_score = min_score
    
    def filter(self, stocks: List[Stock]) -> List[Stock]:
        return [s for s in stocks if s.quality_score >= self.min_score]


class SmartStockFilter:
    """智能股票筛选引擎"""
    
    def __init__(self):
        self.filters = [
            LiquidityFilter(),
            FinancialFilter(),
            VolatilityFilter(),
            QualityFilter()
        ]
    
    def filter(self, universe: List[Stock]) -> List[Stock]:
        """多阶段筛选流程"""
        candidates = universe
        
        for filter_instance in self.filters:
            candidates = filter_instance.filter(candidates)
            if not candidates:
                break
        
        return candidates
    
    def filter_with_scores(self, universe: List[Stock]) -> List[dict]:
        """筛选并返回评分详情"""
        results = []
        
        for stock in universe:
            scores = {}
            
            # 流动性评分
            liquidity_score = min(100, stock.volume / 50000000 * 100)
            scores['liquidity'] = round(liquidity_score, 2)
            
            # 财务健康评分
            pe_score = max(0, min(100, 100 - abs(stock.pe - 20) * 2))
            pb_score = max(0, min(100, 100 - abs(stock.pb - 3) * 10))
            roe_score = min(100, stock.roe * 10) if stock.roe > 0 else 0
            financial_score = (pe_score + pb_score + roe_score) / 3
            scores['financial'] = round(financial_score, 2)
            
            # 波动率评分（适中为好）
            ideal_volatility = 0.03
            vol_score = max(0, 100 - abs(stock.volatility - ideal_volatility) * 1000)
            scores['volatility'] = round(vol_score, 2)
            
            # 综合评分
            composite_score = (liquidity_score * 0.3 + financial_score * 0.4 + vol_score * 0.3)
            scores['composite'] = round(composite_score, 2)
            
            results.append({
                'stock': stock,
                'scores': scores,
                'passed': composite_score >= 60
            })
        
        return results