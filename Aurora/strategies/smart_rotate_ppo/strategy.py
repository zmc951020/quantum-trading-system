#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 核心策略引擎 v0.1.0
========================================
全生命周期：训练 → 回测 → 推理（兼容 Aurora 框架）

Aurora 框架集成点：
  1. 实现 StrategyBase 兼容接口（update_price / get_performance）
     → 可被 StrategyManager 管理
  2. 支持 StrategyAPI 注册
  3. 对接 HardRiskEngine 双层风控
  4. 可选对接 Aurora DataProvider 获取真实行情

Phase 1: 单线程 MLP-PPO 基线（当前）
Phase 2: LSTM/Transformer-PPO + 超参搜索（后续）
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Any, List

import numpy as np
import pandas as pd

from strategies.smart_rotate_ppo.config import (
    StrategyConfig, ETF_CODES, ETF_NAMES, SECTOR_MAP,
)
from strategies.smart_rotate_ppo.data_pipeline import DataPipeline
from strategies.smart_rotate_ppo.env.trading_env import (
    SmartRotateTradingEnv,
    WeeklyRebalanceWrapper,
)
from strategies.smart_rotate_ppo.models.ppo_agent import PPOAgent, MLPFeatureExtractor
from strategies.smart_rotate_ppo.backtest.engine import BacktestEngine, BacktestResult
from strategies.smart_rotate_ppo.risk_guard import RiskGuard, RiskVerdict

logger = logging.getLogger(__name__)


class SmartRotateStrategy:
    """
    智能标的轮动策略（PPO 驱动）

    完整流程：
    1. 数据管线 → 模拟/真实数据
    2. 特征工程 → 每标的 16 维特征
    3. 环境构建 → Gymnasium 交易环境
    4. 模型训练 → PPO 训练
    5. 回测评估 → 金融级指标
    6. 集成输出 → Aurora 兼容接口

    用法:
        strategy = SmartRotateStrategy(cfg)
        strategy.train()
        result = strategy.backtest()
        strategy.print_report(result)

    Aurora 集成用法:
        strategy.register_to_aurora()      # 注册到 StrategyAPI
        strategy.enable_aurora_dual_risk() # 启用双层风控
        strategy.prepare_data()
        strategy.train()
    """

    # ── Aurora 框架兼容属性 ──
    strategy_id: str = "smart_rotate_ppo"
    is_active: bool = True  # StrategyManager 兼容

    def __init__(self, cfg: Optional[StrategyConfig] = None):
        """
        Args:
            cfg: 策略配置。为 None 则使用默认配置
        """
        self.cfg = cfg or StrategyConfig()
        self.data_pipeline = DataPipeline(self.cfg)
        self.agent = PPOAgent(self.cfg)
        self.risk_guard = RiskGuard(self.cfg)
        self.backtest_engine = BacktestEngine(self.cfg)

        # 运行时状态
        self._model_path: Optional[str] = None
        self._train_df: Optional[pd.DataFrame] = None
        self._val_df: Optional[pd.DataFrame] = None
        self._test_df: Optional[pd.DataFrame] = None
        self._feature_cols: Optional[List[str]] = None
        self._return_cols: Optional[List[str]] = None

        # Aurora 集成状态
        self._aurora_registered: bool = False
        self._aurora_risk_enabled: bool = False
        self._aurora_strategy_api = None
        self._aurora_risk_engine = None
        self._aurora_data_provider = None

        # 性能追踪（StrategyManager 兼容）
        self.current_balance: float = self.cfg.initial_balance
        self.position: int = 0
        self.total_trades: int = 0
        self.profit_history: List[float] = []

    # ========================================================================
    # Aurora 框架集成接口
    # ========================================================================
    def register_to_aurora(self) -> Dict[str, Any]:
        """
        注册到 Aurora StrategyAPI

        Returns:
            {'status': 'success'/'error', 'message': str}
        """
        try:
            from strategy_api import StrategyAPI
            self._aurora_strategy_api = StrategyAPI()
            result = self._aurora_strategy_api.register_strategy(
                name=self.cfg.strategy_name,
                description=self.cfg.strategy_description,
                parameters=self.cfg.to_dict(),
                tags=self.cfg.strategy_tags,
                version=self.cfg.strategy_version,
            )
            if result.get("status") == "success":
                self._aurora_registered = True
                self.strategy_id = self.cfg.strategy_name
                logger.info(f"策略 {self.cfg.strategy_name} 已注册到 Aurora StrategyAPI")
            return result
        except ImportError:
            logger.info("Aurora StrategyAPI 不可用，策略将以独立模式运行")
            return {"status": "warning", "message": "StrategyAPI 不可用，策略独立运行"}
        except Exception as e:
            logger.error(f"注册到 Aurora 失败: {e}")
            return {"status": "error", "message": str(e)}

    def enable_aurora_dual_risk(self) -> bool:
        """
        启用 Aurora HardRiskEngine 双层风控

        第1层：策略内置 RiskGuard（权重约束 + 波动率缩放 + Kill Switch）
        第2层：Aurora HardRiskEngine（T+1、涨跌停、仓位上限、熔断、一键平仓）

        Returns:
            True 如果成功启用
        """
        try:
            from risk_manager import HardRiskEngine
            self._aurora_risk_engine = HardRiskEngine()
            self._aurora_risk_enabled = True
            logger.info("Aurora HardRiskEngine 双层风控已启用")
            return True
        except ImportError:
            logger.info("Aurora HardRiskEngine 不可用，仅使用策略内置风控")
            return False
        except Exception as e:
            logger.error(f"启用 Aurora 风控失败: {e}")
            return False

    def enable_aurora_data_provider(self) -> bool:
        """
        切换到 Aurora DataProvider 获取真实行情
        （替代模拟数据）
        """
        try:
            from data import get_data_provider
            self._aurora_data_provider = get_data_provider()
            if self._aurora_data_provider:
                logger.info("已连接到 Aurora DataProvider（4源真实行情）")
                return True
            return False
        except ImportError:
            logger.info("Aurora DataProvider 不可用，使用模拟数据")
            return False

    def _aurora_pre_trade_check(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        通过 Aurora HardRiskEngine 逐单审查

        Args:
            orders: [{"symbol": "510050", "side": "buy", "quantity": 100, "price": 3.50}, ...]

        Returns:
            approved_orders: 通过风控的订单列表
            rejected_orders: 被拒绝的订单列表
        """
        approved = []
        rejected = []
        for order in orders:
            result = self._aurora_risk_engine.pre_trade_check(
                symbol=order.get("symbol", ""),
                side=order.get("side", "buy"),
                quantity=order.get("quantity", 0),
                price=order.get("price", 0),
                strategy_id=self.strategy_id,
            )
            if result.get("allowed", False):
                approved.append(order)
            else:
                rejected.append({**order, "reject_reason": result.get("reason", "")})
                logger.warning(f"[Aurora风控拦截] {order.get('symbol')} {order.get('side')}: {result.get('reason')}")
        return approved, rejected

    # ========================================================================
    # StrategyManager 兼容接口
    # ========================================================================
    def set_active(self, active: bool) -> None:
        """设置策略激活状态（StrategyManager 兼容）"""
        self.is_active = active

    def get_balance(self) -> float:
        """获取当前资金（StrategyManager 兼容）"""
        return self.current_balance

    def get_position(self) -> float:
        """获取当前持仓（StrategyManager 兼容）"""
        return self.position

    def update_price(
        self, current_price: float, data: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        更新价格并执行交易决策（StrategyManager 兼容）

        Args:
            current_price: 当前价格
            data: 价格数据（可选）

        Returns:
            交易结果字典
        """
        if not self.is_active or self._model_path is None:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}
        # 此处由 Auroral Integration 层驱动完整推理流程
        return {"action": "hold", "balance": self.current_balance, "position": self.position}

    def get_performance(self) -> Dict[str, float]:
        """获取策略性能指标（StrategyManager 兼容）"""
        if not self.profit_history:
            return {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
        returns = pd.Series(self.profit_history)
        total_return = (self.current_balance / self.cfg.initial_balance - 1)
        sharpe = returns.mean() / (returns.std() + 1e-8) * np.sqrt(252)
        cumulative = (1 + pd.Series(self.profit_history)).cumprod()
        max_dd = (cumulative.cummax() - cumulative).max()
        return {
            "total_return": float(total_return),
            "sharpe": float(sharpe),
            "max_drawdown": float(max_dd),
            "total_trades": self.total_trades,
        }

    # ========================================================================
    # 数据准备
    # ========================================================================
    def prepare_data(self, use_real: Optional[bool] = None) -> None:
        """
        准备训练数据：获取 → 特征工程 → 时序分割

        同时保存特征列名和收益率列名供后续使用

        Args:
            use_real: 是否使用真实数据。None 则遵循 cfg.use_real_data
        """
        logger.info("=" * 50)
        logger.info("Step 1/3: 数据准备")
        logger.info("=" * 50)

        # 获取/生成数据（自动选择真实/模拟）
        df_raw = self.data_pipeline.load_or_generate(use_real=use_real)
        logger.info(f"原始数据: {len(df_raw)} 行 × 10 标的, "
                     f"{df_raw['date'].min().date()} ~ {df_raw['date'].max().date()}")

        # 特征工程 → 返回 (df_features, feature_cols, return_cols)
        df, self._feature_cols, self._return_cols = self.data_pipeline.build_features(df_raw)

        logger.info(f"特征维度: {len(self._feature_cols)}, 收益率列: {len(self._return_cols)}")

        # 时序分割
        self._train_df, self._val_df, self._test_df = self.data_pipeline.time_series_split(df)

        logger.info("数据准备完成")

    # ========================================================================
    # 训练
    # ========================================================================
    def train(self, total_timesteps: Optional[int] = None) -> str:
        """
        训练 PPO 模型

        Args:
            total_timesteps: 训练总步数。为 None 则使用配置文件中的值

        Returns:
            模型保存路径
        """
        # 数据未准备则先准备
        if self._train_df is None or self._feature_cols is None or self._return_cols is None:
            self.prepare_data()

        logger.info("=" * 50)
        logger.info("Step 2/3: PPO 模型训练")
        logger.info("=" * 50)

        timesteps = total_timesteps or self.cfg.total_timesteps

        # 创建训练环境（+ 周频调仓Wrapper）
        train_env = SmartRotateTradingEnv(
            df=self._train_df,
            feature_cols=self._feature_cols,
            return_cols=self._return_cols,
            cfg=self.cfg,
            mode="train",
        )
        train_env = WeeklyRebalanceWrapper(train_env, rebalance_freq=self.cfg.rebalance_freq)

        # 创建验证环境（+ 周频调仓Wrapper）
        val_env = SmartRotateTradingEnv(
            df=self._val_df,
            feature_cols=self._feature_cols,
            return_cols=self._return_cols,
            cfg=self.cfg,
            mode="eval",
        )
        val_env = WeeklyRebalanceWrapper(val_env, rebalance_freq=self.cfg.rebalance_freq)

        # 创建模型
        model = self.agent.create_model(
            env=train_env,
            feature_extractor_cls=MLPFeatureExtractor,
        )

        # 训练
        save_path = self.cfg.model_save_path
        model = self.agent.train(
            model=model,
            total_timesteps=timesteps,
            eval_env=val_env,
            save_path=save_path,
        )

        self._model_path = save_path
        logger.info(f"训练完成: {save_path}")
        return save_path

    # ========================================================================
    # 回测
    # ========================================================================
    def backtest(self, model_path: Optional[str] = None) -> BacktestResult:
        """
        在测试集上回测

        Args:
            model_path: 模型路径。为 None 则使用最近训练的模型

        Returns:
            BacktestResult 回测结果
        """
        from stable_baselines3 import PPO

        if model_path is None:
            model_path = self._model_path or self.cfg.model_save_path

        # 数据未准备则先准备
        if self._test_df is None or self._feature_cols is None or self._return_cols is None:
            self.prepare_data()

        logger.info("=" * 50)
        logger.info("Step 3/3: 回测评估")
        logger.info("=" * 50)

        # 加载模型
        device = "cuda" if (
            self.cfg.device == "cuda" or
            (self.cfg.device == "auto" and os.environ.get("CUDA_VISIBLE_DEVICES"))
        ) else "cpu"
        model = PPO.load(model_path, device=device)

        # 创建测试环境（+ 周频调仓Wrapper）
        test_env = SmartRotateTradingEnv(
            df=self._test_df,
            feature_cols=self._feature_cols,
            return_cols=self._return_cols,
            cfg=self.cfg,
            mode="test",
        )
        test_env = WeeklyRebalanceWrapper(test_env, rebalance_freq=self.cfg.rebalance_freq)

        # 执行回测
        result = self.backtest_engine.run(model, test_env, self._test_df)

        # 打印
        self.backtest_engine.print_summary(result)

        # 保存
        self.backtest_engine.save_report(result)

        return result

    # ========================================================================
    # 推理（实盘/模拟用）
    # ========================================================================
    def predict_weights(self, features: np.ndarray) -> np.ndarray:
        """
        模型推理：给定特征向量，返回仓位权重

        Args:
            features: 形状 (obs_dim,) 的特征向量

        Returns:
            weights: 形状 (N,) 的仓位权重
        """
        from stable_baselines3 import PPO

        model_path = self._model_path or self.cfg.model_save_path
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型不存在: {model_path}，请先训练")

        device = "cuda" if (
            self.cfg.device == "cuda" or
            (self.cfg.device == "auto" and os.environ.get("CUDA_VISIBLE_DEVICES"))
        ) else "cpu"
        model = PPO.load(model_path, device=device)

        action, _ = model.predict(features, deterministic=True)
        raw_weights = np.clip(action, 0, 1)
        return raw_weights / (raw_weights.sum() + 1e-8)

    # ========================================================================
    # 全流程一键运行
    # ========================================================================
    def run_full_pipeline(self, register_to_aurora: bool = True) -> BacktestResult:
        """
        一键运行完整流程：注册 → 训练 → 回测

        Args:
            register_to_aurora: 是否注册到 Aurora StrategyAPI

        Returns:
            回测结果
        """
        start_time = datetime.now()

        logger.info("=" * 60)
        logger.info("智能标的轮动策略 (PPO) — 全流程启动")
        logger.info(f"   策略配置: {self.cfg.strategy_display_name}")
        logger.info(f"   标的池: {self.cfg.N} 只 ETF")
        logger.info(f"   特征维度: {self.cfg.N * self.cfg.per_asset_features}")
        logger.info(f"   训练步数: {self.cfg.total_timesteps:,}")
        logger.info(f"   风控参数: 单标{self.cfg.max_single_weight:.0%} / 行业{self.cfg.max_sector_weight:.0%} / 波动率{self.cfg.volatility_target:.0%}")
        logger.info("=" * 60)

        # Step 0: Aurora 集成
        if register_to_aurora:
            self.register_to_aurora()
            if self.cfg.aurora_dual_risk_enabled:
                self.enable_aurora_dual_risk()

        # Step 1: 数据
        self.prepare_data()

        # Step 2: 训练
        self.train()

        # Step 3: 回测
        result = self.backtest()

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"全流程完成，耗时 {elapsed:.1f} 秒")
        return result

    # ========================================================================
    # 工具方法
    # ========================================================================
    def print_report(self, result: BacktestResult) -> None:
        """打印完整报告"""
        self.backtest_engine.print_summary(result)

    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "strategy_name": self.cfg.strategy_name,
            "strategy_display": self.cfg.strategy_display_name,
            "version": self.cfg.strategy_version,
            "etf_pool": [{"code": e["code"], "name": e["name"], "sector": e["sector"]} for e in [
                {"code": c, "name": n, "sector": SECTOR_MAP.get(c, "")}
                for c, n in zip(ETF_CODES, ETF_NAMES)
            ]],
            "N": self.cfg.N,
            "lookback": self.cfg.lookback,
            "per_asset_features": self.cfg.per_asset_features,
            "total_features": self.cfg.N * self.cfg.per_asset_features,
            "initial_balance": self.cfg.initial_balance,
            "total_timesteps": self.cfg.total_timesteps,
            "ppo_lr": self.cfg.ppo_lr,
            "fc_dims": self.cfg.fc_dims,
            "device": self.agent._device if hasattr(self.agent, '_device') else self.cfg.device,
            "aurora_registered": self._aurora_registered,
            "aurora_risk_enabled": self._aurora_risk_enabled,
        }

    def health_check(self) -> Dict[str, Any]:
        """策略健康检查"""
        checks = {
            "config_valid": self.cfg is not None,
            "data_pipeline_loaded": self.data_pipeline is not None,
            "agent_loaded": self.agent is not None,
            "risk_guard_loaded": self.risk_guard is not None,
            "aurora_registered": self._aurora_registered,
            "aurora_risk_enabled": self._aurora_risk_enabled,
            "model_exists": os.path.exists(self.cfg.model_save_path) if self._model_path else False,
            "is_active": self.is_active,
        }
        checks["healthy"] = all(checks.values())
        return checks


# ============================================================================
# 主入口
# ============================================================================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 创建策略
    cfg = StrategyConfig()
    strategy = SmartRotateStrategy(cfg)

    # 全流程运行
    result = strategy.run_full_pipeline()

    # 打印最终判断
    print()
    if result.passed:
        print("✅ 策略达标！满足夏普≥1.5 且 最大回撤≤20%")
    else:
        print("⚠️ 策略未达标，请检查指标或调整参数")