#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速烟雾测试 — 验证 P0+P1 修复正确性
运行: python strategies/smart_rotate_ppo/smoke_test_fixes.py
"""
from __future__ import annotations

import logging
import os
import sys
import time

# 确保 Aurora 根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("smoke_test")

print()
print("=" * 60)
print("🧪 智能标的轮动策略 — 修复烟雾测试")
print("=" * 60)

# ── 1. 验证 config.py 修复 ──
print("\n[Test 1] config.py 奖励权重 & Kill Switch")
from strategies.smart_rotate_ppo.config import StrategyConfig

cfg = StrategyConfig()
assert cfg.reward_return_scale == 15.0, f"FAIL: return_scale={cfg.reward_return_scale}"
assert cfg.reward_drawdown_penalty == 3.0, f"FAIL: drawdown_penalty={cfg.reward_drawdown_penalty}"
assert cfg.reward_turnover_penalty == 0.5, f"FAIL: turnover_penalty={cfg.reward_turnover_penalty}"
assert cfg.reward_volatility_penalty == 0.5, f"FAIL: volatility_penalty={cfg.reward_volatility_penalty}"
assert cfg.reward_sharpe_weight == 3.0, f"FAIL: sharpe_weight={cfg.reward_sharpe_weight}"
assert cfg.kill_switch_drawdown == 0.15, f"FAIL: kill_switch={cfg.kill_switch_drawdown}"
print("  ✅ config.py 所有值正确")

# ── 2. 验证 env 默认值与 config 一致 ──
print("\n[Test 2] trading_env.py 默认 reward_config 值")

# 用模拟数据构造最小 DataFrame
import numpy as np
import pandas as pd

N, L, F = 10, 60, 16
total_rows = L + 200  # 足够 step 使用
np.random.seed(42)

# 构造包含所需列的DataFrame
columns = ["date"]
for i in range(N):
    columns.extend([
        f"close_{i}", f"open_{i}", f"high_{i}", f"low_{i}", f"volume_{i}",
        f"return_{i}", f"price_{i}",
    ])
# 添加特征列
for i in range(N):
    for feat in range(F):
        columns.append(f"feat_{i}_{feat}")

data = {}
data["date"] = pd.date_range("2020-01-01", periods=total_rows, freq="B")
for col in columns:
    if col != "date":
        # 随机游走价格，收益率均值≈0
        data[col] = np.cumsum(np.random.randn(total_rows) * 0.01) + 100.0

df_test = pd.DataFrame(data)

feature_cols = [c for c in df_test.columns if c.startswith("feat_")]
return_cols = [f"return_{i}" for i in range(N)]

from strategies.smart_rotate_ppo.env.trading_env import SmartRotateTradingEnv

# 不传cfg → 走默认值分支
env_default = SmartRotateTradingEnv(
    df=df_test,
    feature_cols=feature_cols,
    N=N, L=L, F=F,
)
assert env_default.reward_return_scale == 15.0, f"FAIL: env default return_scale={env_default.reward_return_scale}"
assert env_default.reward_drawdown_penalty == 3.0, f"FAIL: env default drawdown_penalty={env_default.reward_drawdown_penalty}"
assert env_default.reward_sharpe_weight == 3.0, f"FAIL: env default sharpe_weight={env_default.reward_sharpe_weight}"

# 传cfg → 走cfg覆盖分支
env_cfg = SmartRotateTradingEnv(
    df=df_test,
    feature_cols=feature_cols,
    cfg=cfg,
)
assert env_cfg.reward_return_scale == 15.0, f"FAIL: cfg return_scale={env_cfg.reward_return_scale}"
assert env_cfg.kill_switch_drawdown == 0.15, f"FAIL: cfg kill_switch={env_cfg.kill_switch_drawdown}"
print("  ✅ env 默认值 与 config.py 一致")

# ── 3. 验证 WeeklyRebalanceWrapper 集成 ──
print("\n[Test 3] WeeklyRebalanceWrapper 集成验证")
from strategies.smart_rotate_ppo.env.trading_env import WeeklyRebalanceWrapper

env = SmartRotateTradingEnv(
    df=df_test,
    feature_cols=feature_cols,
    N=N, L=L, F=F,
)

# 包裹 Wrapper
wrapped_env = WeeklyRebalanceWrapper(env, rebalance_freq=5)
assert isinstance(wrapped_env, WeeklyRebalanceWrapper), "FAIL: not wrapped"
assert wrapped_env.rebalance_freq == 5, f"FAIL: freq={wrapped_env.rebalance_freq}"
print("  ✅ WeeklyRebalanceWrapper 正常包裹")

# ── 4. 验证 env reset + step 正常 ──
print("\n[Test 4] 环境 reset → step 循环验证")
obs, info = wrapped_env.reset()

assert len(obs) == 173, f"FAIL: obs dim={len(obs)}, expected 173"
assert obs.dtype == np.float32, f"FAIL: obs dtype={obs.dtype}"

# 跑20步，验证基本流程
actions = []
rewards = []
for step_idx in range(20):
    action = np.random.rand(10).astype(np.float32)
    action = action / action.sum()
    obs, reward, terminated, truncated, info = wrapped_env.step(action)
    actions.append(action)
    rewards.append(reward)

    if terminated:
        print(f"  ⚠️ Kill Switch triggered at step {step_idx + 1}")
        break
    if truncated:
        print(f"  ⚠️ Episode truncated at step {step_idx + 1}")
        break

print(f"  ✅ 完成 {len(rewards)} 步")
print(f"     last reward={rewards[-1]:.6f}, last balance={info.get('balance', 'N/A')}")
print(f"     last drawdown={info.get('drawdown', 'N/A')}")

# ── 5. 验证 strategy.py 导入与实例化 ──
print("\n[Test 5] strategy.py 导入与实例化")
from strategies.smart_rotate_ppo.strategy import SmartRotateStrategy

strategy = SmartRotateStrategy(cfg)
assert strategy.cfg.reward_return_scale == 15.0
print("  ✅ SmartRotateStrategy 实例化成功")
print(f"     strategy_id={strategy.strategy_id}, is_active={strategy.is_active}")

# ── 6. 检查 strategy.py 中 Wrapper 引用 ──
print("\n[Test 6] strategy.py 中 WeeklyRebalanceWrapper 引用检查")
import inspect
src = inspect.getsource(SmartRotateStrategy.train)
assert "WeeklyRebalanceWrapper" in src, "FAIL: train() 中未引用 WeeklyRebalanceWrapper"
src_backtest = inspect.getsource(SmartRotateStrategy.backtest)
assert "WeeklyRebalanceWrapper" in src_backtest, "FAIL: backtest() 中未引用 WeeklyRebalanceWrapper"
print("  ✅ train() 和 backtest() 均引用 WeeklyRebalanceWrapper")

# ── 总结 ──
print()
print("=" * 60)
print("🎉 全部 6 项测试通过！修复验证成功")
print("=" * 60)
print()
print("修复项确认清单:")
print("  ✅ P0-1 WeeklyRebalanceWrapper 集成 → train/val/test 三处包裹")
print("  ✅ P0-2 奖励权重重新平衡 → return_scale=15, drawdown_penalty=3")
print("  ✅ P1-3 Kill Switch 调高 → 15% (与 max_drawdown_trigger 一致)")
print("  ✅ P1-3 env默认值统一 → 15.0/3.0/0.5/3.0")
print()