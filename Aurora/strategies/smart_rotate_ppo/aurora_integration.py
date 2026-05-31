#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — Aurora 框架全流程集成适配器 v0.1.0
========================================================
职责：作为策略引擎与 Aurora 框架之间的核心桥梁

集成链路：
  [Aurora StrategyAPI]
       ↓ 注册/管理
  [SmartRotateStrategy] ← 策略核心引擎
       ↓ 数据
  [Aurora DataProvider] ← 4源真实行情（可选）
       ↓ 风控
  [RiskGuard] ← 策略内置4层风控
       ↓ 第4层审查
  [Aurora HardRiskEngine] ← T+1、涨跌停、仓位上限、一键平仓
       ↓ 执行
  [Aurora BrokerManager] ← 订单执行/EMS

运行模式：
  1. 独立训练模式：python -m strategies.smart_rotate_ppo.aurora_integration --train
  2. Aurora 集成模式：python -m strategies.smart_rotate_ppo.aurora_integration --full
  3. 实盘模式：python -m strategies.smart_rotate_ppo.aurora_integration --live
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

# 策略核心模块
from strategies.smart_rotate_ppo.config import StrategyConfig, ETF_POOL, ETF_CODES, ETF_NAMES, SECTOR_MAP
from strategies.smart_rotate_ppo.strategy import SmartRotateStrategy
from strategies.smart_rotate_ppo.risk_guard import RiskGuard, RiskVerdict

logger = logging.getLogger(__name__)


class AuroraIntegration:
    """
    Aurora 框架全流程集成适配器

    一站式接口：注册 → 数据 → 训练 → 回测 → 风控审查 → 执行

    用法:
        adapter = AuroraIntegration()
        adapter.setup()          # 自动绑定所有 Aurora 模块
        adapter.train()          # 训练（可选模拟/真实数据）
        adapter.backtest()       # 回测
        adapter.run_live()       # 实盘推理
        adapter.health_report()  # 健康报告
    """

    def __init__(self, cfg: Optional[StrategyConfig] = None):
        """
        Args:
            cfg: 策略配置。为 None 则使用默认
        """
        self.cfg = cfg or StrategyConfig()
        self.strategy = SmartRotateStrategy(self.cfg)
        self.risk_guard = self.strategy.risk_guard

        # Aurora 模块引用
        self._strategy_api = None
        self._data_provider = None
        self._hard_risk_engine = None
        self._trade_security = None
        self._broker_manager = None

        # 集成状态
        self._setup_complete: bool = False
        self._aurora_ready: bool = False
        self._last_weights: Optional[np.ndarray] = None
        self._last_prices: Optional[np.ndarray] = None

        # 运行时追踪
        self._live_history: List[Dict[str, Any]] = []
        self._session_start: Optional[datetime] = None

    # ========================================================================
    # 集成设置
    # ========================================================================
    def setup(self, force_real_data: bool = False) -> Dict[str, Any]:
        """
        一站式设置：自动绑定所有可用的 Aurora 模块

        Args:
            force_real_data: 强制使用真实数据（默认先模拟）

        Returns:
            设置状态
        """
        results = {}

        # ── 1. 注册到 StrategyAPI ──
        if self.cfg.aurora_register_on_init:
            results["strategy_api"] = self.strategy.register_to_aurora()

        # ── 2. 绑定 Aurora HardRiskEngine ──
        results["risk_engine"] = self._bind_aurora_risk()

        # ── 3. 绑定 TradeSecurity ──
        results["trade_security"] = self._bind_trade_security()

        # ── 4. 绑定 DataProvider ──
        results["data_provider"] = self._bind_data_provider(force_real_data)

        # ── 5. 绑定 BrokerManager ──
        results["broker_manager"] = self._bind_broker()

        # ── 最终状态 ──
        self._setup_complete = True
        self._aurora_ready = all(
            isinstance(v, dict) and v.get("status") in ("success", "connected")
            for v in results.values()
            if v is not None
        )
        self._session_start = datetime.now()

        results["aurora_ready"] = self._aurora_ready
        results["strategy_id"] = self.strategy.strategy_id
        results["etf_pool_size"] = len(ETF_POOL)
        results["session_start"] = str(self._session_start)

        logger.info(f"Aurora 集成设置完成. Ready={self._aurora_ready}")
        return results

    def _bind_aurora_risk(self) -> Dict[str, str]:
        """绑定 Aurora HardRiskEngine"""
        try:
            from risk_manager import HardRiskEngine
            self._hard_risk_engine = HardRiskEngine()
            self.risk_guard.bind_aurora_risk(self._hard_risk_engine)
            self.strategy._aurora_risk_engine = self._hard_risk_engine
            self.strategy._aurora_risk_enabled = True
            return {"status": "connected", "module": "HardRiskEngine"}
        except ImportError:
            return {"status": "unavailable", "module": "HardRiskEngine"}
        except Exception as e:
            return {"status": "error", "module": "HardRiskEngine", "message": str(e)}

    def _bind_trade_security(self) -> Dict[str, str]:
        """绑定 Aurora TradeSecurity"""
        try:
            from trade_security import TradeSecurity
            self._trade_security = TradeSecurity()
            self.risk_guard.bind_aurora_trade_security(self._trade_security)
            return {"status": "connected", "module": "TradeSecurity"}
        except ImportError:
            return {"status": "unavailable", "module": "TradeSecurity"}
        except Exception as e:
            return {"status": "error", "module": "TradeSecurity", "message": str(e)}

    def _bind_data_provider(self, force_real: bool = False) -> Dict[str, str]:
        """绑定 Aurora DataProvider"""
        if not force_real:
            return {"status": "skipped", "module": "DataProvider", "reason": "使用模拟数据"}
        try:
            from data import get_data_provider
            self._data_provider = get_data_provider()
            if self._data_provider:
                self.strategy._aurora_data_provider = self._data_provider
                return {"status": "connected", "module": "DataProvider"}
            return {"status": "unavailable", "module": "DataProvider"}
        except ImportError:
            return {"status": "unavailable", "module": "DataProvider", "reason": "模块未安装"}
        except Exception as e:
            return {"status": "error", "module": "DataProvider", "message": str(e)}

    def _bind_broker(self) -> Dict[str, str]:
        """绑定 Aurora BrokerManager"""
        try:
            from broker_manager import BrokerManager
            self._broker_manager = BrokerManager()
            return {"status": "connected", "module": "BrokerManager"}
        except ImportError:
            return {"status": "unavailable", "module": "BrokerManager", "reason": "非实盘环境"}

    # ========================================================================
    # 训练（Aurora 集成版）
    # ========================================================================
    def train(self, real_data: bool = False) -> str:
        """
        Aurora 集成版训练

        Args:
            real_data: 是否使用 Aurora DataProvider 真实数据

        Returns:
            模型路径
        """
        if not self._setup_complete:
            self.setup(force_real_data=real_data)

        logger.info(f"开始训练（数据源: {'Aurora DataProvider' if real_data else '模拟数据'}）")
        return self.strategy.train()

    # ========================================================================
    # 回测（Aurora 集成版）
    # ========================================================================
    def backtest(self) -> Dict[str, Any]:
        """Aurora 集成版回测"""
        if not self._setup_complete:
            self.setup()

        result = self.strategy.backtest()

        # 附加 Aurora 状态
        base = result.to_dict() if hasattr(result, 'to_dict') else vars(result)
        return {
            **base,
            "aurora_ready": self._aurora_ready,
            "setup_status": self._setup_complete,
        }

    # ========================================================================
    # 实盘推理（Aurora 集成版）
    # ========================================================================
    def run_live(self) -> None:
        """
        实盘推理循环（演示用框架）

        完整流程（每周期）：
        1. Aurora DataProvider 获取最新行情
        2. 特征工程
        3. 模型推理 → 原始权重
        4. RiskGuard 风控 → 调整权重
        5. Aurora HardRiskEngine 审查 → 订单
        6. BrokerManager 执行
        """
        if not self._setup_complete:
            self.setup()

        logger.info("实盘推理模式启动（演示框架）")
        self.risk_guard.reset_kill_switch()

        # 加载模型
        if not os.path.exists(self.cfg.model_save_path):
            logger.error(f"模型不存在: {self.cfg.model_save_path}，请先训练")
            return

        from stable_baselines3 import PPO
        device = "cuda" if self.cfg.device == "cuda" or os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
        model = PPO.load(self.cfg.model_save_path, device=device)
        self._last_weights = np.zeros(self.cfg.N)

        # 主循环（演示用）
        for step in range(10):
            # ── 1. 获取行情 ──
            prices = self._get_live_prices()
            features = self._build_live_features(prices)

            # ── 2. 模型推理 ──
            action, _ = model.predict(features, deterministic=True)
            raw_weights = np.clip(action, 0, 1)
            raw_weights = raw_weights / (raw_weights.sum() + 1e-8)

            # ── 3. 风控审查 ──
            cov = self._estimate_cov()
            orders = self.risk_guard.weights_to_orders(
                raw_weights, self._last_weights or np.zeros(self.cfg.N),
                prices, self.strategy.current_balance,
            )

            verdict = self.risk_guard.enforce_with_aurora(
                weights=raw_weights,
                cov_matrix=cov,
                current_balance=self.strategy.current_balance,
                initial_balance=self.cfg.initial_balance,
                orders=orders if self._aurora_ready else None,
            )

            if verdict.kill_switch:
                logger.error(f"Kill Switch 触发: {verdict.kill_reason}")
                break

            if not verdict.passed:
                logger.warning(f"风控拦截: {verdict.blocked_reason}")
                continue

            # ── 4. 执行交易 ──
            final_weights = verdict.adjusted_weights
            self._execute_live_orders(orders)
            self._last_weights = final_weights

            # ── 5. 记录 ──
            self._live_history.append({
                "step": step,
                "timestamp": str(datetime.now()),
                "weights": final_weights.tolist(),
                "verdict_summary": verdict.summary(),
            })

            logger.info(
                f"Step {step}: 权重={np.round(final_weights, 3).tolist()}, "
                f"标的数={verdict.metrics.get('num_assets', 0)}, "
                f"总权重={verdict.metrics.get('total_weight', 0):.2%}"
            )

        logger.info(f"实盘推理完成，共 {len(self._live_history)} 步")

    # ========================================================================
    # 健康报告
    # ========================================================================
    def health_report(self) -> Dict[str, Any]:
        """生成策略健康报告"""
        report = {
            "strategy": self.cfg.strategy_display_name,
            "version": self.cfg.strategy_version,
            "strategy_id": self.strategy.strategy_id,
            "setup_complete": self._setup_complete,
            "aurora_ready": self._aurora_ready,
            "session_start": str(self._session_start) if self._session_start else None,
            "model_exists": os.path.exists(self.cfg.model_save_path),
            "strategy_health": self.strategy.health_check(),
            "kill_switch_active": self.risk_guard.is_kill_switch_active(),
            "live_steps": len(self._live_history),
        }

        # Aurora 模块状态
        report["modules"] = {
            "strategy_api": self._strategy_api is not None,
            "data_provider": self._data_provider is not None,
            "hard_risk_engine": self._hard_risk_engine is not None,
            "trade_security": self._trade_security is not None,
            "broker_manager": self._broker_manager is not None,
        }

        return report

    # ========================================================================
    # 内部辅助方法
    # ========================================================================
    def _get_live_prices(self) -> np.ndarray:
        """从 Aurora DataProvider 获取实时价格（或模拟）"""
        if self._data_provider:
            try:
                prices = []
                for etf in ETF_POOL:
                    data = self._data_provider.get_latest_price(etf["code"])
                    if data:
                        prices.append(data.get("close", 1.0))
                    else:
                        prices.append(np.random.uniform(0.8, 5.0))
                return np.array(prices)
            except Exception:
                pass
        # 回退：模拟
        return np.random.uniform(0.8, 5.0, self.cfg.N)

    def _build_live_features(self, prices: np.ndarray) -> np.ndarray:
        """从实时价格构建特征向量（简化版）"""
        # 简化：用价格归一化 + 零填充
        features = np.zeros(self.cfg.obs_dim, dtype=np.float32)
        for i in range(self.cfg.N):
            idx_start = i * self.cfg.per_asset_features
            features[idx_start] = prices[i] / prices.mean() - 1.0  # 价格相对偏离
        return features

    def _estimate_cov(self) -> np.ndarray:
        """估计协方差矩阵（回退）"""
        return np.eye(self.cfg.N) * 0.02

    def _execute_live_orders(self, orders: List[Dict]) -> None:
        """通过 BrokerManager 执行订单（或打印）"""
        if self._broker_manager and self._aurora_ready:
            for order in orders:
                try:
                    self._broker_manager.place_order(
                        symbol=order["symbol"],
                        side=order["side"],
                        quantity=order["quantity"],
                        price=order["price"],
                        order_type="limit",
                    )
                except Exception as e:
                    logger.error(f"下单失败 {order['symbol']}: {e}")
        else:
            # 演示模式
            if orders:
                logger.info(f"演示模式 - 待执行 {len(orders)} 笔订单")
                for o in orders[:3]:
                    logger.info(f"  {o['side']} {o['symbol']} x{o['quantity']} @ {o['price']:.2f}")


# ============================================================================
# CLI 入口
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="智能标的轮动策略 — Aurora 集成运行器")
    parser.add_argument("--train", action="store_true", help="训练模式")
    parser.add_argument("--backtest", action="store_true", help="回测模式")
    parser.add_argument("--full", action="store_true", help="全流程（训练+回测）")
    parser.add_argument("--live", action="store_true", help="实盘推理演示")
    parser.add_argument("--real-data", action="store_true", help="使用 Aurora 真实数据")
    parser.add_argument("--health", action="store_true", help="健康报告")
    parser.add_argument("--register", action="store_true", help="仅注册到 Aurora")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 创建适配器
    adapter = AuroraIntegration()

    # ── 健康报告 ──
    if args.health:
        report = adapter.health_report()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return

    # ── 注册 ──
    if args.register:
        result = adapter.strategy.register_to_aurora()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # ── 设置 ──
    adapter.setup(force_real_data=args.real_data)

    # ── 训练 ──
    if args.train or args.full:
        adapter.train(real_data=args.real_data)

    # ── 回测 ──
    if args.backtest or args.full:
        result = adapter.backtest()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    # ── 实盘 ──
    if args.live:
        adapter.run_live()

    # ── 健康报告 ──
    if args.full or args.live:
        report = adapter.health_report()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

    # 默认行为：全流程
    if not any([args.train, args.backtest, args.full, args.live, args.health, args.register]):
        logger.info("未指定模式，默认运行全流程")
        adapter.setup()
        adapter.train()
        result = adapter.backtest()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()