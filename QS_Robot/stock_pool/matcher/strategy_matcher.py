#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 策略匹配引擎
"""
from typing import List, Dict, Optional, Any
from stock_pool.core.models import Stock, Strategy


# 系统策略类别 → 匹配器策略配置的映射表
# 每个类别映射到: (type, volatility_profile, ideal_trend, min_liquidity, min_return)
CATEGORY_TO_PROFILE: Dict[str, tuple] = {
    "RL":        ("momentum",  "high",   0.75, 80000000,  0.08),
    "Grid":      ("oscillate", "medium", 0.30, 100000000, 0.03),
    "ML":        ("trend",     "medium", 0.60, 50000000,  0.06),
    "Value":     ("trend",     "low",    0.40, 30000000,  0.05),
    "MultiFactor": ("momentum", "medium", 0.65, 60000000,  0.07),
    "Trend":     ("trend",     "medium", 0.70, 50000000,  0.08),
    "Fund":      ("trend",     "low",    0.35, 20000000,  0.03),
    "Defense":   ("oscillate", "low",    0.20, 40000000,  0.02),
    "Ensemble":  ("trend",     "medium", 0.55, 70000000,  0.06),
}


class StrategyStockMatcher:
    """策略与股票智能匹配器
    
    支持从系统策略管理器动态加载真实策略列表，
    自动将系统策略类别映射到匹配器所需的配置参数。
    """
    
    def __init__(self, strategy_manager=None):
        self._strategy_mgr = strategy_manager
        self.strategy_profiles = self._load_strategies()
    
    def _load_strategies(self) -> List[Strategy]:
        """从系统策略管理器加载真实策略，失败时回退到默认配置"""
        if self._strategy_mgr is not None:
            try:
                real_strategies = self._strategy_mgr.get_strategy_list()
                if real_strategies:
                    return self._build_profiles(real_strategies)
            except Exception:
                pass  # 加载失败则回退到默认配置
        return self._load_default_strategies()
    
    def _build_profiles(self, strategy_list: List[dict]) -> List[Strategy]:
        """将系统策略列表转换为匹配器可用的策略配置"""
        profiles = []
        for s in strategy_list:
            name = s.get("name", "")
            category = s.get("category", "")
            
            # 从映射表获取配置，未匹配的类别使用默认值
            profile = CATEGORY_TO_PROFILE.get(category, ("trend", "medium", 0.50, 50000000, 0.05))
            profiles.append(Strategy(
                name=name,
                type=profile[0],
                volatility_profile=profile[1],
                min_liquidity=profile[2],
                ideal_trend=profile[3],
                min_return=profile[4],
                params=s.get("params", {})
            ))
        return profiles
    
    def refresh_strategies(self):
        """重新加载策略列表（策略变更后调用）"""
        self.strategy_profiles = self._load_strategies()
    
    def _load_default_strategies(self) -> List[Strategy]:
        """加载默认策略配置（降级方案）"""
        return [
            Strategy(
                name="FourierRLStrategy",
                type="momentum",
                volatility_profile="high",
                min_liquidity=80000000,
                ideal_trend=0.75,
                min_return=0.08
            ),
            Strategy(
                name="FinalMarketAdaptiveGrid",
                type="oscillate",
                volatility_profile="medium",
                min_liquidity=100000000,
                ideal_trend=0.30,
                min_return=0.03
            ),
            Strategy(
                name="MovingAveragesStrategy",
                type="trend",
                volatility_profile="medium",
                min_liquidity=50000000,
                ideal_trend=0.70,
                min_return=0.08
            ),
            Strategy(
                name="HuijinValueStrategy",
                type="trend",
                volatility_profile="low",
                min_liquidity=30000000,
                ideal_trend=0.40,
                min_return=0.05
            ),
            Strategy(
                name="MultiFactorResonanceStrategy",
                type="momentum",
                volatility_profile="medium",
                min_liquidity=60000000,
                ideal_trend=0.65,
                min_return=0.07
            ),
            Strategy(
                name="special_forces_wyckoff",
                type="trend",
                volatility_profile="medium",
                min_liquidity=80000000,
                ideal_trend=0.70,
                min_return=0.10
            ),
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