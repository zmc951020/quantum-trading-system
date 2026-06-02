#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 策略匹配引擎
"""
from typing import List, Dict
from stock_pool.core.models import Stock, Strategy


class StrategyStockMatcher:
    """策略与股票智能匹配器"""
    
    def __init__(self):
        self.strategy_profiles = self._load_default_strategies()
    
    def _load_default_strategies(self) -> List[Strategy]:
        """加载默认策略配置"""
        return [
            Strategy(
                name="趋势跟踪策略",
                type="trend",
                volatility_profile="medium",
                min_liquidity=50000000,
                ideal_trend=0.7,
                min_return=0.08
            ),
            Strategy(
                name="网格交易策略",
                type="oscillate",
                volatility_profile="medium",
                min_liquidity=100000000,
                ideal_trend=0.3,
                min_return=0.03
            ),
            Strategy(
                name="动量策略",
                type="momentum",
                volatility_profile="high",
                min_liquidity=50000000,
                ideal_trend=0.8,
                min_return=0.1
            ),
            Strategy(
                name="价值投资策略",
                type="value",
                volatility_profile="low",
                min_liquidity=30000000,
                ideal_trend=0.4,
                min_return=0.05
            ),
            Strategy(
                name="套利策略",
                type="arbitrage",
                volatility_profile="low",
                min_liquidity=200000000,
                ideal_trend=0.1,
                min_return=0.02
            )
        ]
    
    def get_stock_features(self, stock: Stock) -> Dict[str, float]:
        """提取股票特征"""
        return {
            'volatility': stock.volatility,
            'trend_strength': stock.trend_strength,
            'liquidity': stock.volume,
            'historical_return': stock.quality_score / 100  # 用质量评分近似
        }
    
    def _calculate_match_score(self, features: Dict[str, float], strategy: Strategy) -> float:
        """计算匹配分数"""
        score = 0
        
        # 波动率匹配（25%）
        vol_mapping = {'low': 0.02, 'medium': 0.05, 'high': 0.1}
        target_vol = vol_mapping.get(strategy.volatility_profile, 0.05)
        vol_diff = abs(features['volatility'] - target_vol)
        vol_score = max(0, 25 - vol_diff * 500)
        score += vol_score
        
        # 趋势强度匹配（25%）
        trend_match = 1 - abs(features['trend_strength'] - strategy.ideal_trend)
        score += trend_match * 25
        
        # 流动性匹配（25%）
        if features['liquidity'] >= strategy.min_liquidity:
            score += 25
        else:
            score += min(25, features['liquidity'] / strategy.min_liquidity * 25)
        
        # 历史表现匹配（25%）
        if features['historical_return'] >= strategy.min_return:
            score += 25
        else:
            score += min(25, features['historical_return'] / strategy.min_return * 25)
        
        return min(100, max(0, score))
    
    def match(self, stock: Stock, top_n: int = 3) -> List[Dict[str, any]]:
        """为股票匹配最合适的策略"""
        features = self.get_stock_features(stock)
        matches = []
        
        for strategy in self.strategy_profiles:
            score = self._calculate_match_score(features, strategy)
            matches.append({
                'strategy': strategy,
                'score': round(score, 2),
                'features': features
            })
        
        # 按匹配度排序
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        return matches[:top_n]
    
    def match_all(self, stocks: List[Stock]) -> List[Dict[str, any]]:
        """批量匹配"""
        results = []
        for stock in stocks:
            matches = self.match(stock)
            results.append({
                'stock': stock,
                'matches': matches,
                'best_match': matches[0] if matches else None
            })
        return results