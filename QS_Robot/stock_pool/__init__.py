#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统
"""
from .core.models import (
    Stock, Strategy, Pool, SimulationResult,
    EvaluationResult, VoteResult
)
from .core.composite_scorer import CompositeScorer, PoolManager
from .filters.smart_filter import SmartStockFilter
from .matcher.strategy_matcher import StrategyStockMatcher
from .simulator.pre_trading_simulator import PreTradingSimulator
from .voting.vote_system import ExpertAgentSystem, VotingSystem

__version__ = "1.0.0"
__author__ = "QS Robot Team"

__all__ = [
    'Stock', 'Strategy', 'Pool', 'SimulationResult', 'EvaluationResult', 'VoteResult',
    'CompositeScorer', 'PoolManager',
    'SmartStockFilter', 'StrategyStockMatcher',
    'PreTradingSimulator',
    'ExpertAgentSystem', 'VotingSystem'
]