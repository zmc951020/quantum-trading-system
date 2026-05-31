#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 (Smart Target Rotate Strategy) v0.1.0

基于 PPO 强化学习的 ETF 标的轮动策略，完全兼容 Aurora 量化交易框架。

核心模块：
  - config.py:           统一配置中心（10只ETF, 25/40/12风控, PPO超参）
  - strategy.py:         策略引擎（训练/回测/推理, Aurora接口兼容）
  - risk_guard.py:       4层风控守卫（权重约束+波动率缩放+Kill Switch+Aurora HardRiskEngine）
  - aurora_integration.py: Aurora全流程集成适配器（注册/数据/风控/执行）

Phase 1: MLP-PPO 基线 | Phase 2: LSTM/Transformer-PPO
"""

from strategies.smart_rotate_ppo.config import StrategyConfig, ETF_POOL, ETF_CODES, ETF_NAMES, SECTOR_MAP
from strategies.smart_rotate_ppo.strategy import SmartRotateStrategy
from strategies.smart_rotate_ppo.risk_guard import RiskGuard, RiskVerdict
from strategies.smart_rotate_ppo.aurora_integration import AuroraIntegration

__version__ = "0.1.0"
__all__ = [
    "StrategyConfig",
    "SmartRotateStrategy",
    "RiskGuard",
    "RiskVerdict",
    "AuroraIntegration",
    "ETF_POOL",
    "ETF_CODES",
    "ETF_NAMES",
    "SECTOR_MAP",
]
