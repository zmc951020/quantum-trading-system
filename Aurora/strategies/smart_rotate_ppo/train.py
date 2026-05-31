#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 训练入口
=============================
最小化入口脚本，一键训练

用法:
    python strategies/smart_rotate_ppo/train.py
    python strategies/smart_rotate_ppo/train.py --timesteps 500000 --device cuda
"""

from __future__ import annotations

import argparse
import logging
import sys

from strategies.smart_rotate_ppo.config import StrategyConfig
from strategies.smart_rotate_ppo.strategy import SmartRotateStrategy

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="智能标的轮动策略 — PPO 训练")
    parser.add_argument(
        "--timesteps",
        type=int,
        default=None,
        help="训练总步数（默认使用配置文件值）",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cpu", "cuda", "auto"],
        help="设备选择（默认使用配置文件值）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="随机种子",
    )
    parser.add_argument(
        "--train-only",
        action="store_true",
        help="仅训练，不执行回测",
    )
    parser.add_argument(
        "--backtest-only",
        action="store_true",
        help="仅回测，不训练（需要已有模型）",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="回测时使用的模型路径",
    )

    args = parser.parse_args()

    # 构建配置
    cfg = StrategyConfig()
    if args.device:
        cfg.device = args.device
    if args.seed is not None:
        cfg.random_seed = args.seed

    # 创建策略
    strategy = SmartRotateStrategy(cfg)

    if args.backtest_only:
        # 仅回测
        print("🔍 仅执行回测模式...")
        if args.model_path:
            result = strategy.backtest(model_path=args.model_path)
        else:
            result = strategy.backtest()
    else:
        if args.train_only:
            # 仅训练
            print("🚀 仅执行训练模式...")
            strategy.prepare_data()
            strategy.train(total_timesteps=args.timesteps)
            print(f"✅ 训练完成！模型保存至: {cfg.model_save_path}")
        else:
            # 全流程
            print("🚀 全流程运行中...")
            result = strategy.run_full_pipeline()

            # 最终判断
            print()
            if result.passed:
                print("✅ 策略达标！满足夏普≥1.0 且 最大回撤≤20%")
            else:
                print("⚠️ 策略未达标，请检查指标或调整参数")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    main()