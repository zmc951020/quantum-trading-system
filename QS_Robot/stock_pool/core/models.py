#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 核心数据模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any


@dataclass
class Stock:
    """股票数据模型"""
    code: str
    name: str
    market: str = "SH"  # SH/SZ
    price: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    roe: float = 0.0
    volume: float = 0.0
    turnover_rate: float = 0.0
    volatility: float = 0.0
    trend_strength: float = 0.0
    liquidity_score: float = 0.0
    quality_score: float = 0.0
    sector: str = ""
    industry: str = ""
    update_time: datetime = field(default_factory=datetime.now)


@dataclass
class Strategy:
    """策略数据模型"""
    name: str
    type: str  # trend/oscillate/momentum/value/arbitrage
    volatility_profile: str = "medium"  # low/medium/high
    min_liquidity: float = 50000000
    ideal_trend: float = 0.5
    min_return: float = 0.05
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Pool:
    """股票池数据模型"""
    name: str
    type: str  # candidate/classified/watchlist/adaptive/trading
    stocks: List[Stock] = field(default_factory=list)
    update_frequency: str = "daily"
    creation_time: datetime = field(default_factory=datetime.now)
    last_update_time: datetime = field(default_factory=datetime.now)


@dataclass
class SimulationResult:
    """模拟结果数据模型"""
    stock: Stock
    strategy: Strategy
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades: int = 0
    duration: int = 30
    passed: bool = False
    score: float = 0.0


@dataclass
class EvaluationResult:
    """评估结果数据模型"""
    stock: Stock
    strategy: Optional[Strategy] = None
    simulation_score: float = 0.0
    technical_score: float = 0.0
    risk_score: float = 0.0
    expert_score: float = 0.0
    compliance_passed: bool = True
    composite_score: float = 0.0
    passed: bool = False
    recommendations: List[str] = field(default_factory=list)


@dataclass
class VoteResult:
    """投票结果数据模型"""
    proposal_id: str
    stock: Stock
    strategy: Strategy
    votes: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending/approved/rejected
    quorum: int = 3
    threshold: float = 0.6
    deadline: datetime = field(default_factory=lambda: datetime.now())