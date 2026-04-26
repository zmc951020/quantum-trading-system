#!/usr/bin/env python3
"""
双维度市场状态识别器
结合傅里叶HMM状态（波动率维度）和Aurora趋势类型（趋势方向维度）
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple

class DualDimensionMarketState:
    """
    双维度市场状态识别器

    维度1 - HMM状态（波动率维度，用于风控决策）:
        0: TRENDING_LOW_VOL - 低波动趋势市（最佳交易环境）
        1: CHOPPY_HIGH_VOL - 高波动震荡市（降低仓位）
        2: CRISIS_MODE - 危机模式（只平仓）

    维度2 - 趋势类型（趋势方向维度，用于策略选择）:
        'range_bound': 横盘市场
        'trending_up': 上涨趋势
        'trending_down': 下跌趋势
    """

    def __init__(self):
        """初始化双维度市场状态识别器"""
        # HMM状态标签
        self.hmm_labels = {
            0: 'TRENDING_LOW_VOL',
            1: 'CHOPPY_HIGH_VOL',
            2: 'CRISIS_MODE'
        }

        # 趋势类型标签
        self.trend_labels = {
            'range_bound': 'RANGE_BOUND',
            'trending_up': 'TRENDING_UP',
            'trending_down': 'TRENDING_DOWN'
        }

        # 双维度交叉决策表
        # [HMM状态][趋势类型] = (交易信号, 仓位比例, 策略类型)
        self.decision_matrix = {
            # 低波动趋势市 - 最佳环境
            (0, 'trending_up'): {
                'signal': 'long',
                'position_ratio': 0.95,
                'strategy': 'momentum_grid',
                'description': '满仓做多，正常网格'
            },
            (0, 'range_bound'): {
                'signal': 'neutral',
                'position_ratio': 0.60,
                'strategy': 'mean_reversion',
                'description': '正常网格，横盘策略'
            },
            (0, 'trending_down'): {
                'signal': 'liquidate',
                'position_ratio': 0.0,
                'strategy': 'watch',
                'description': '清仓观望'
            },

            # 高波动震荡市 - 风险环境
            (1, 'trending_up'): {
                'signal': 'long',
                'position_ratio': 0.50,
                'strategy': 'tight_grid',
                'description': '半仓做多，缩小网格'
            },
            (1, 'range_bound'): {
                'signal': 'neutral',
                'position_ratio': 0.30,
                'strategy': 'mean_reversion',
                'description': '缩仓网格，横盘策略'
            },
            (1, 'trending_down'): {
                'signal': 'liquidate',
                'position_ratio': 0.0,
                'strategy': 'watch',
                'description': '清仓避险'
            },

            # 危机模式 - 熔断环境
            (2, 'trending_up'): {
                'signal': 'liquidate',
                'position_ratio': 0.0,
                'strategy': 'emergency_exit',
                'description': '强制平仓'
            },
            (2, 'range_bound'): {
                'signal': 'liquidate',
                'position_ratio': 0.0,
                'strategy': 'emergency_exit',
                'description': '强制平仓'
            },
            (2, 'trending_down'): {
                'signal': 'liquidate',
                'position_ratio': 0.0,
                'strategy': 'emergency_exit',
                'description': '强制平仓'
            }
        }

        # 当前状态
        self.current_hmm_state = 0
        self.current_trend_type = 'range_bound'

    def update_hmm_state(self, state: int):
        """
        更新HMM状态

        Args:
            state: HMM状态 (0, 1, 2)
        """
        self.current_hmm_state = state

    def update_trend_type(self, trend_type: str):
        """
        更新趋势类型

        Args:
            trend_type: 趋势类型 ('range_bound', 'trending_up', 'trending_down')
        """
        self.current_trend_type = trend_type

    def get_decision(self) -> Dict:
        """
        获取双维度交叉决策

        Returns:
            决策信息字典
        """
        key = (self.current_hmm_state, self.current_trend_type)
        decision = self.decision_matrix.get(key, self.decision_matrix[(0, 'range_bound')])

        return {
            'hmm_state': self.current_hmm_state,
            'hmm_label': self.hmm_labels[self.current_hmm_state],
            'trend_type': self.current_trend_type,
            'trend_label': self.trend_labels.get(self.current_trend_type, 'RANGE_BOUND'),
            'decision': decision,
            'signal': decision['signal'],
            'recommended_position_ratio': decision['position_ratio'],
            'recommended_strategy': decision['strategy'],
            'description': decision['description']
        }

    def should_liquidate(self) -> bool:
        """
        判断是否应该平仓

        Returns:
            是否应该平仓
        """
        decision = self.get_decision()
        return decision['signal'] == 'liquidate'

    def get_position_multiplier(self) -> float:
        """
        获取仓位调整系数

        Returns:
            仓位调整系数 (0.0 - 1.0)
        """
        decision = self.get_decision()
        return decision['recommended_position_ratio']

    def get_strategy_type(self) -> str:
        """
        获取推荐的策略类型

        Returns:
            策略类型
        """
        decision = self.get_decision()
        return decision['recommended_strategy']

    def is_safe_to_trade(self) -> bool:
        """
        判断是否适合交易

        Returns:
            是否适合交易
        """
        return self.current_hmm_state != 2


class TrendTypeDetector:
    """
    趋势类型检测器
    复现Aurora原有策略的市场类型判断逻辑
    """

    def __init__(self):
        """初始化趋势类型检测器"""
        self.market_types = ['range_bound', 'trending_up', 'trending_down']

    def detect(self, data: pd.Series) -> str:
        """
        检测市场趋势类型

        Args:
            data: 价格数据

        Returns:
            趋势类型
        """
        if len(data) < 20:
            return 'range_bound'

        # 计算EMA
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema30 = data.ewm(span=30).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]

        # 计算趋势强度
        trend_strength = (ema10 - ema60) / ema60

        # 计算价格范围
        recent_data = data.iloc[-20:]
        price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()

        # 确定市场类型
        if trend_strength < -0.02:
            return 'trending_down'
        elif trend_strength > 0.02:
            return 'trending_up'
        elif price_range < 0.04:
            return 'range_bound'
        elif price_range > 0.08:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            if abs(trend_strength) > 0.01:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'

    def get_confidence(self, data: pd.Series) -> float:
        """
        获取趋势判断置信度

        Args:
            data: 价格数据

        Returns:
            置信度 (0.0 - 1.0)
        """
        if len(data) < 20:
            return 0.5

        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]

        trend_strength = abs((ema10 - ema60) / ema60)

        # 归一化到0-1
        confidence = min(1.0, trend_strength / 0.05)
        return confidence
