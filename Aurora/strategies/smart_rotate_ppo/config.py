#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 统一配置中心 v0.1.0
========================================
所有超参、风控参数、调仓参数、标的配置在此唯一定义，
代码其他模块不得硬编码参数。

观测空间维度计算公式：
  OBS_DIM = N * PER_ASSET_FEATURES + PORTFOLIO_STATE_DIM
          = 10 * 16 + 13 = 173

动作空间：10维连续 [0,1]，经归一化后单标的 0~25%
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# ============================================================================
# 1. 标的池（宏观对冲版 — 跨资产/跨市场 10 只 ETF）
# ============================================================================
# 调仓规则：每周五收盘后决策，次周一开盘执行
# 覆盖：A股宽基 × 5 + 红利 × 1 + 黄金 × 1 + 跨境 × 2 + 债券 × 1
ETF_POOL: List[Dict[str, str]] = [
    {"code": "510300", "name": "沪深300ETF",     "sector": "宽基大盘",   "exchange": "SH"},
    {"code": "159915", "name": "创业板ETF",       "sector": "宽基成长",   "exchange": "SZ"},
    {"code": "510500", "name": "中证500ETF",      "sector": "宽基中小",   "exchange": "SH"},
    {"code": "588000", "name": "科创50ETF",       "sector": "宽基科创",   "exchange": "SH"},
    {"code": "159845", "name": "中证1000ETF",     "sector": "宽基小盘",   "exchange": "SZ"},
    {"code": "510880", "name": "红利ETF",         "sector": "红利价值",   "exchange": "SH"},
    {"code": "518880", "name": "黄金ETF",         "sector": "贵金属",     "exchange": "SH"},
    {"code": "513100", "name": "纳指ETF",         "sector": "跨境美股",   "exchange": "SH"},
    {"code": "159920", "name": "恒生ETF",         "sector": "跨境港股",   "exchange": "SZ"},
    {"code": "511260", "name": "十年国债ETF",     "sector": "债券利率",   "exchange": "SH"},
]

# 行业映射（用于行业集中度风控）
SECTOR_MAP: Dict[str, str] = {etf["code"]: etf["sector"] for etf in ETF_POOL}
ETF_CODES: List[str] = [etf["code"] for etf in ETF_POOL]
ETF_NAMES: List[str] = [etf["name"] for etf in ETF_POOL]


@dataclass
class StrategyConfig:
    """智能标的轮动策略完整配置"""

    # ========== 策略元信息（Aurora 注册用） ==========
    strategy_name: str = "smart_rotate_ppo"
    strategy_display_name: str = "智能标的轮动策略 (PPO)"
    strategy_version: str = "0.1.0"
    strategy_description: str = (
        "基于 PPO 强化学习的 ETF 标的轮动策略。"
        "10只核心ETF，173维特征观测空间，周频调仓，"
        "4层风控（权重约束 + 波动率缩放 + Kill Switch + Aurora HardRiskEngine 兜底）。"
    )
    strategy_tags: List[str] = field(default_factory=lambda: [
        "PPO", "ETF轮动", "强化学习", "风控", "周频调仓"
    ])

    # ========== 基本参数 ==========
    N: int = 10                              # 标的数量
    lookback: int = 60                       # 回看窗口（交易日）
    rebalance_freq: int = 5                  # 调仓频率（交易日），5=周频

    # ========== 观测/特征维度（动态计算） ==========
    per_asset_features: int = 16             # 每标的技术指标数
    portfolio_state_dim: int = 13            # 组合状态维度 (N权重 + balance_ratio + dd + vol)
    obs_dim: int = 173                       # 总观测维度 = N * per_asset_features + portfolio_state_dim

    # ========== 训练参数 ==========
    total_timesteps: int = 1_000_000         # PPO 总训练步数（100万步完整训练）
    train_ratio: float = 0.70                # 训练集比例
    val_ratio: float = 0.15                  # 验证集比例
    test_ratio: float = 0.15                 # 测试集比例
    random_seed: int = 42
    device: str = "auto"                     # cuda / cpu / auto

    # ========== 数据参数 ==========
    synthetic_data_length: int = 5000        # 模拟数据总行数
    data_start_date: str = "2015-01-01"
    data_end_date: str = "2024-12-31"
    use_real_data: bool = True               # 是否使用真实数据（yfinance→akshare→Aurora 三级降级）
    real_data_sources: List[str] = field(default_factory=lambda: [
        "yahoo", "eastmoney", "tushare", "akshare"
    ])

    # ========== PPO 超参（金融最优） ==========
    ppo_lr: float = 1e-4                     # 降学习率提升训练稳定性
    ppo_n_steps: int = 2048
    ppo_batch_size: int = 64
    ppo_n_epochs: int = 10
    ppo_gamma: float = 0.99
    ppo_gae_lambda: float = 0.95
    ppo_clip_range: float = 0.2
    ppo_ent_coef: float = 0.01
    ppo_vf_coef: float = 0.5
    ppo_max_grad_norm: float = 0.5

    # ========== 网络结构 ==========
    fc_dims: List[int] = field(default_factory=lambda: [512, 256, 128])

    # ========== 账户参数 ==========
    initial_balance: float = 1_000_000.0     # 初始资金
    transaction_cost: float = 0.0005         # 手续费+滑点 5bp
    risk_free_rate: float = 0.015            # 年化无风险利率（一年期国债）

    # ========== 仓位风控参数 ==========
    max_single_weight: float = 0.25          # 单标的上限 25%
    max_sector_weight: float = 0.35          # 单一行业上限 35%
    max_total_leverage: float = 1.0          # 总杠杆上限（不做空=1.0）

    # ========== 动态风控参数 ==========
    max_drawdown_trigger: float = 0.15       # 最大回撤触发线 15%
    kill_switch_drawdown: float = 0.15       # Kill Switch 回撤线 15%（P1修复：从12%调高，避免频繁截断Episode导致GAE失真）
    volatility_target: float = 0.12          # 目标年化波动率 12%
    volatility_scale_max: float = 0.50       # 波动率缩放最大削减比例

    # ========== 奖励函数权重（P0修复：量级重新平衡，消除33:1的收益/惩罚失衡） ==========
    reward_return_scale: float = 15.0        # 收益缩放系数（10→15，提升收益信号比重）
    reward_drawdown_penalty: float = 3.0     # 回撤惩罚系数（10→3，避免惩罚项碾压收益项）
    reward_turnover_penalty: float = 0.5     # 换手率惩罚系数（0.3→0.5，适度惩罚高频换手）
    reward_volatility_penalty: float = 0.5   # 波动率惩罚系数（不变）
    reward_sharpe_weight: float = 3.0        # 夏普比率加权系数（2.0→3.0，强化风险调整收益信号）

    # ========== 回测参数 ==========
    backtest_benchmark: str = "510300"       # 基准标的（沪深300ETF）
    backtest_min_sharpe: float = 1.5         # 回测达标最低夏普比率
    backtest_max_drawdown: float = 0.20      # 回测达标最大回撤
    backtest_min_calmar: float = 1.0         # 回测达标最低Calmar

    # ========== 模型路径 ==========
    model_save_dir: str = "strategies/smart_rotate_ppo/models"
    model_save_path: str = "strategies/smart_rotate_ppo/models/ppo_smart_rotate_final.zip"
    log_dir: str = "strategies/smart_rotate_ppo/logs"
    report_dir: str = "strategies/smart_rotate_ppo/reports"

    # ========== Aurora 集成参数 ==========
    aurora_dual_risk_enabled: bool = True    # 启用 Aurora HardRiskEngine 双层风控
    aurora_register_on_init: bool = True     # 初始化时自动注册到 Aurora StrategyAPI
    aurora_realtime_fallback: bool = False   # 实盘时回退到独立运行

    # ========== 功能开关 ==========
    enable_wechat_alert: bool = False        # 企业微信告警（首期关闭）
    enable_tensorboard: bool = True
    enable_checkpoint: bool = True
    enable_early_stopping: bool = False      # 首期关闭，后续开启

    def to_dict(self) -> dict:
        """导出为字典"""
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, (int, float, str, bool, list, dict, type(None))):
                d[k] = v
            else:
                d[k] = str(v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyConfig":
        """从字典创建"""
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in valid_fields})