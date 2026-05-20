#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SB3TradingEnv — 金融级强化学习交易环境
======================================
基于 gymnasium 标准接口，专为 stable-baselines3 设计。

设计目标：
  1. 连续状态空间（20维特征向量）
  2. 连续动作空间（仓位比例 [0, 1]）
  3. 金融级奖励函数（夏普、回撤、交易成本、市场对齐）
  4. 支持回测模式与实盘模式
  5. 风险预算约束

使用方式：
  env = SB3TradingEnv()
  obs, info = env.reset()
  obs, reward, terminated, truncated, info = env.step(action)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import logging

logger = logging.getLogger(__name__)

try:
    import gymnasium as gym
    from gymnasium import spaces
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    logger.warning("[SB3TradingEnv] gymnasium 未安装，使用模拟空间")


@dataclass
class TradingEnvConfig:
    """交易环境配置"""
    state_dim: int = 20
    max_position: float = 1.0
    min_position: float = 0.0
    max_episode_steps: int = 1000

    # 奖励函数权重
    reward_alpha: float = 0.35       # 收益权重
    reward_beta: float = 0.30        # 夏普权重
    reward_gamma: float = 0.20       # 回撤惩罚
    reward_delta: float = 0.10       # 交易频率惩罚
    reward_epsilon: float = 0.05     # 市场状态对齐奖励

    # 风险约束
    max_drawdown_limit: float = 0.15   # 最大允许回撤 15%
    max_position_change: float = 0.20  # 单步最大仓位变化 20%
    min_hold_days: int = 1             # 最小持有天数

    # 交易成本
    trading_cost: float = 0.0003       # 万三佣金
    slippage: float = 0.0001           # 滑点


class SB3TradingEnv(gym.Env if SB3_AVAILABLE else object):
    """
    金融级强化学习交易环境

    遵循 gymnasium 标准接口，可直接用于 stable-baselines3 训练。
    """

    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}

    def __init__(
        self,
        config: Optional[TradingEnvConfig] = None,
        render_mode: Optional[str] = None,
    ):
        super().__init__()

        self.config = config or TradingEnvConfig()
        self.render_mode = render_mode

        # 定义动作空间和观察空间
        if SB3_AVAILABLE:
            self.action_space = spaces.Box(
                low=self.config.min_position,
                high=self.config.max_position,
                shape=(1,),
                dtype=np.float32,
            )
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(self.config.state_dim,),
                dtype=np.float32,
            )
        else:
            # 降级模式
            self.action_space = None
            self.observation_space = None

        # 内部状态
        self._position = 0.5  # 当前仓位
        self._prev_position = 0.5
        self._step_count = 0
        self._hold_days = 0
        self._episode_return = 0.0
        self._returns_history: List[float] = []
        self._drawdown_history: List[float] = []
        self._peak_value = 1.0
        self._current_value = 1.0
        self._trade_count = 0

        # 市场数据缓存
        self._market_data: Dict[str, Any] = {}
        self._state: Optional[np.ndarray] = None

        # 性能统计
        self._episode_stats: Dict[str, List[float]] = {
            "returns": [],
            "sharpe": [],
            "drawdowns": [],
            "rewards": [],
        }

        logger.info(f"[SB3TradingEnv] 初始化完成，state_dim={self.config.state_dim}")

    # ==================== gymnasium 标准接口 ====================

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """
        重置环境

        Args:
            seed: 随机种子
            options: 可选参数，可传入 market_data 初始化市场状态

        Returns:
            observation: 初始状态
            info: 附加信息
        """
        super().reset(seed=seed)

        # 重置内部状态
        self._position = 0.5
        self._prev_position = 0.5
        self._step_count = 0
        self._hold_days = 0
        self._episode_return = 0.0
        self._returns_history = []
        self._drawdown_history = []
        self._peak_value = 1.0
        self._current_value = 1.0
        self._trade_count = 0

        # 如果提供了市场数据，使用它
        if options and "market_data" in options:
            self._market_data = options["market_data"]
        else:
            self._market_data = self._generate_default_market_data()

        # 构建初始状态
        self._state = self._build_state(self._market_data)

        info = {
            "position": self._position,
            "step": self._step_count,
            "market_regime": self._market_data.get("market_regime", "unknown"),
        }

        return self._state.copy(), info

    def step(
        self, action: Union[np.ndarray, float]
    ) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        执行一步交易

        Args:
            action: 目标仓位比例 [0, 1]

        Returns:
            observation: 新状态
            reward: 奖励值
            terminated: 是否终止（达到最大回撤或步数）
            truncated: 是否截断
            info: 附加信息
        """
        # 解析动作
        if isinstance(action, np.ndarray):
            target_position = float(np.clip(action[0], 0, 1))
        else:
            target_position = float(np.clip(action, 0, 1))

        # 风险约束：限制单步仓位变化
        position_change = target_position - self._prev_position
        if abs(position_change) > self.config.max_position_change:
            target_position = self._prev_position + np.sign(position_change) * self.config.max_position_change
            target_position = np.clip(target_position, 0, 1)

        # 最小持有天数约束
        if self._hold_days < self.config.min_hold_days:
            target_position = self._prev_position

        # 记录交易
        if abs(target_position - self._prev_position) > 0.01:
            self._trade_count += 1
            self._hold_days = 0
        else:
            self._hold_days += 1

        # 更新仓位
        self._prev_position = self._position
        self._position = target_position
        self._step_count += 1

        # 模拟市场回报（从市场数据获取）
        price_return = self._market_data.get("price_change_pct", 0) / 100.0
        volatility = self._market_data.get("volatility", 0.02)

        # 计算组合收益
        portfolio_return = self._position * price_return

        # 扣除交易成本
        trade_cost = abs(self._position - self._prev_position) * self.config.trading_cost
        slippage_cost = abs(self._position - self._prev_position) * self.config.slippage
        net_return = portfolio_return - trade_cost - slippage_cost

        # 更新组合价值
        self._current_value *= (1 + net_return)
        self._episode_return += net_return
        self._returns_history.append(net_return)

        # 更新回撤
        self._peak_value = max(self._peak_value, self._current_value)
        current_drawdown = (self._peak_value - self._current_value) / self._peak_value
        self._drawdown_history.append(current_drawdown)

        # 计算奖励
        reward = self._compute_reward(
            portfolio_return=net_return,
            sharpe_change=self._compute_rolling_sharpe(),
            drawdown_change=current_drawdown,
            trade_frequency=self._trade_count / max(self._step_count, 1),
            regime_alignment=self._market_data.get("regime_alignment", 0.5),
        )

        # 更新市场数据（模拟下一时刻）
        self._market_data = self._generate_next_market_data()

        # 构建新状态
        self._state = self._build_state(self._market_data)

        # 判断终止条件
        terminated = False
        truncated = False

        # 最大回撤终止
        if current_drawdown > self.config.max_drawdown_limit:
            terminated = True
            reward -= 1.0  # 额外惩罚
            logger.debug(f"[SB3TradingEnv] 最大回撤超限: {current_drawdown:.2%}")

        # 最大步数截断
        if self._step_count >= self.config.max_episode_steps:
            truncated = True

        # 构建信息
        info = {
            "position": self._position,
            "step": self._step_count,
            "portfolio_return": net_return,
            "drawdown": current_drawdown,
            "trade_count": self._trade_count,
            "episode_return": self._episode_return,
            "current_value": self._current_value,
            "peak_value": self._peak_value,
        }

        return self._state.copy(), reward, terminated, truncated, info

    def render(self):
        """渲染环境状态"""
        if self.render_mode == "human":
            print(
                f"Step: {self._step_count:4d} | "
                f"Position: {self._position:.2%} | "
                f"Value: {self._current_value:.4f} | "
                f"Drawdown: {self._drawdown_history[-1] if self._drawdown_history else 0:.2%}"
            )

    def close(self):
        """清理资源"""
        pass

    # ==================== 奖励函数 ====================

    def _compute_reward(
        self,
        portfolio_return: float,
        sharpe_change: float,
        drawdown_change: float,
        trade_frequency: float,
        regime_alignment: float,
    ) -> float:
        """
        金融级奖励函数

        包含：
        1. 组合收益奖励
        2. 夏普比率变化奖励
        3. 回撤惩罚（非线性）
        4. 交易频率惩罚
        5. 市场状态对齐奖励
        """
        cfg = self.config

        # 1. 收益奖励（线性）
        return_reward = cfg.reward_alpha * portfolio_return

        # 2. 夏普奖励
        sharpe_reward = cfg.reward_beta * sharpe_change

        # 3. 回撤惩罚（非线性：回撤越大惩罚越重）
        drawdown_penalty = cfg.reward_gamma * (drawdown_change ** 2) * 10

        # 4. 交易频率惩罚
        frequency_penalty = cfg.reward_delta * trade_frequency

        # 5. 市场状态对齐奖励
        alignment_reward = cfg.reward_epsilon * regime_alignment

        # 综合奖励
        reward = (
            return_reward
            + sharpe_reward
            - drawdown_penalty
            - frequency_penalty
            + alignment_reward
        )

        # 记录统计
        self._episode_stats["returns"].append(portfolio_return)
        self._episode_stats["sharpe"].append(sharpe_change)
        self._episode_stats["drawdowns"].append(drawdown_change)
        self._episode_stats["rewards"].append(reward)

        return float(reward)

    # ==================== 状态构建 ====================

    def _build_state(self, market_data: Dict[str, Any]) -> np.ndarray:
        """
        构建 20 维状态向量

        维度说明：
        [0]  归一化价格变化
        [1]  波动率
        [2]  RSI
        [3]  MACD 信号
        [4]  ADX
        [5]  ATR (归一化)
        [6]  当前仓位
        [7]  未实现盈亏
        [8]  市场状态编码
        [9]  信号置信度
        [10] 风险评分
        [11] 成交量变化
        [12] 短期动量
        [13] 长期动量
        [14] 布林带位置
        [15] 滚动夏普
        [16] 最大回撤
        [17] 交易频率
        [18] 时间衰减
        [19] 市场对齐度
        """
        state = np.zeros(self.config.state_dim, dtype=np.float32)

        # 维度 0: 归一化价格变化
        if "price_change_pct" in market_data:
            state[0] = np.clip(market_data["price_change_pct"] / 10.0, -1, 1)

        # 维度 1: 波动率
        if "volatility" in market_data:
            state[1] = np.clip(market_data["volatility"] / 0.5, 0, 1)

        # 维度 2: RSI
        if "rsi" in market_data:
            state[2] = market_data["rsi"] / 100.0

        # 维度 3: MACD 信号
        if "macd" in market_data and "macd_signal" in market_data:
            state[3] = float(np.tanh(market_data["macd"] - market_data["macd_signal"]))

        # 维度 4: ADX
        if "adx" in market_data:
            state[4] = market_data["adx"] / 100.0

        # 维度 5: ATR
        if "atr" in market_data and "close" in market_data:
            state[5] = np.clip(market_data["atr"] / market_data["close"], 0, 0.1) * 10

        # 维度 6: 当前仓位
        state[6] = self._position

        # 维度 7: 未实现盈亏
        if "unrealized_pnl_pct" in market_data:
            state[7] = np.clip(market_data["unrealized_pnl_pct"] / 0.1, -1, 1)

        # 维度 8: 市场状态
        if "market_regime" in market_data:
            regime_map = {
                "trending_up": 0.8,
                "range_bound": 0.5,
                "trending_down": 0.2,
                "bull": 0.9,
                "bear": 0.1,
                "volatile": 0.6,
            }
            state[8] = regime_map.get(market_data["market_regime"], 0.5)

        # 维度 9: 信号置信度
        if "signal_confidence" in market_data:
            state[9] = market_data["signal_confidence"]

        # 维度 10: 风险评分
        if "risk_score" in market_data:
            state[10] = np.clip(market_data["risk_score"] / 100.0, 0, 1)

        # 维度 11: 成交量变化
        if "volume_change_pct" in market_data:
            state[11] = np.clip(market_data["volume_change_pct"] / 5.0, -1, 1)

        # 维度 12: 短期动量
        if "momentum_short" in market_data:
            state[12] = np.clip(market_data["momentum_short"] / 0.1, -1, 1)

        # 维度 13: 长期动量
        if "momentum_long" in market_data:
            state[13] = np.clip(market_data["momentum_long"] / 0.2, -1, 1)

        # 维度 14: 布林带位置
        if "bb_position" in market_data:
            state[14] = np.clip(market_data["bb_position"], -1, 1)

        # 维度 15: 滚动夏普
        if "rolling_sharpe" in market_data:
            state[15] = np.clip(market_data["rolling_sharpe"] / 3.0, -1, 1)

        # 维度 16: 最大回撤
        if "max_drawdown" in market_data:
            state[16] = np.clip(market_data["max_drawdown"] / 0.3, 0, 1)

        # 维度 17: 交易频率
        if "trade_frequency" in market_data:
            state[17] = np.clip(market_data["trade_frequency"] / 50.0, 0, 1)

        # 维度 18: 时间衰减
        if "time_decay" in market_data:
            state[18] = market_data["time_decay"]

        # 维度 19: 市场对齐度
        if "regime_alignment" in market_data:
            state[19] = market_data["regime_alignment"]

        return state

    # ==================== 市场数据生成 ====================

    def _generate_default_market_data(self) -> Dict[str, Any]:
        """生成默认市场数据（用于初始状态）"""
        return {
            "price_change_pct": 0.0,
            "volatility": 0.02,
            "rsi": 50.0,
            "macd": 0.0,
            "macd_signal": 0.0,
            "adx": 25.0,
            "atr": 1.0,
            "close": 100.0,
            "unrealized_pnl_pct": 0.0,
            "market_regime": "range_bound",
            "signal_confidence": 0.5,
            "risk_score": 30.0,
            "volume_change_pct": 0.0,
            "momentum_short": 0.0,
            "momentum_long": 0.0,
            "bb_position": 0.0,
            "rolling_sharpe": 0.0,
            "max_drawdown": 0.0,
            "trade_frequency": 0.0,
            "time_decay": 1.0,
            "regime_alignment": 0.5,
        }

    def _generate_next_market_data(self) -> Dict[str, Any]:
        """生成下一时刻市场数据（模拟随机游走）"""
        data = self._market_data.copy()

        # 价格变化（带均值回归）
        prev_change = data.get("price_change_pct", 0)
        data["price_change_pct"] = (
            -0.1 * prev_change  # 均值回归
            + np.random.normal(0, 0.5)  # 随机扰动
        )

        # 波动率（带聚集效应）
        prev_vol = data.get("volatility", 0.02)
        data["volatility"] = np.clip(
            prev_vol + np.random.normal(0, 0.005),
            0.005, 0.5,
        )

        # RSI
        prev_rsi = data.get("rsi", 50)
        data["rsi"] = np.clip(
            prev_rsi + np.random.normal(0, 5),
            0, 100,
        )

        # 市场状态（简单马尔可夫链）
        regimes = ["trending_up", "range_bound", "trending_down"]
        current_regime = data.get("market_regime", "range_bound")
        if np.random.random() < 0.05:  # 5% 概率切换
            new_regime = np.random.choice([r for r in regimes if r != current_regime])
            data["market_regime"] = new_regime

        # 信号置信度
        data["signal_confidence"] = np.clip(
            data.get("signal_confidence", 0.5) + np.random.normal(0, 0.05),
            0, 1,
        )

        # 滚动夏普
        if self._returns_history:
            recent_returns = self._returns_history[-20:]
            if np.std(recent_returns) > 0:
                sharpe = np.mean(recent_returns) / np.std(recent_returns) * np.sqrt(252)
                data["rolling_sharpe"] = np.clip(sharpe, -3, 3)
            else:
                data["rolling_sharpe"] = 0.0

        # 最大回撤
        if self._drawdown_history:
            data["max_drawdown"] = max(self._drawdown_history)

        # 交易频率
        data["trade_frequency"] = self._trade_count / max(self._step_count, 1) * 100

        # 时间衰减
        data["time_decay"] = max(0.1, 1.0 - self._step_count / self.config.max_episode_steps)

        # 市场对齐度
        data["regime_alignment"] = np.clip(
            0.5 + 0.5 * abs(data.get("signal_confidence", 0.5) - 0.5),
            0, 1,
        )

        return data

    # ==================== 辅助方法 ====================

    def _compute_rolling_sharpe(self) -> float:
        """计算滚动夏普比率"""
        if len(self._returns_history) < 20:
            return 0.0

        recent_returns = self._returns_history[-20:]
        if np.std(recent_returns) == 0:
            return 0.0

        return float(np.mean(recent_returns) / np.std(recent_returns) * np.sqrt(252))

    def get_episode_stats(self) -> Dict[str, Any]:
        """获取当前 episode 统计"""
        stats = {}
        for key, values in self._episode_stats.items():
            if values:
                stats[f"avg_{key}"] = float(np.mean(values))
                stats[f"std_{key}"] = float(np.std(values))
                stats[f"last_{key}"] = float(values[-1])
            else:
                stats[f"avg_{key}"] = 0.0
                stats[f"std_{key}"] = 0.0
                stats[f"last_{key}"] = 0.0

        stats["total_steps"] = self._step_count
        stats["total_trades"] = self._trade_count
        stats["final_position"] = self._position
        stats["episode_return"] = self._episode_return
        stats["final_value"] = self._current_value
        stats["peak_value"] = self._peak_value

        return stats

    def reset_stats(self):
        """重置统计"""
        self._episode_stats = {
            "returns": [],
            "sharpe": [],
            "drawdowns": [],
            "rewards": [],
        }


# ==================== 便捷函数 ====================

def create_trading_env(
    config: Optional[TradingEnvConfig] = None,
    render_mode: Optional[str] = None,
) -> "SB3TradingEnv":
    """创建交易环境"""
    return SB3TradingEnv(config=config, render_mode=render_mode)


# ==================== 自测 ====================

if __name__ == "__main__":
    if not SB3_AVAILABLE:
        print("❌ gymnasium 未安装，请执行: pip install gymnasium")
        exit(1)

    print("=" * 60)
    print("SB3TradingEnv 自测")
    print("=" * 60)

    env = SB3TradingEnv(render_mode="human")

    # 测试 reset
    obs, info = env.reset()
    print(f"\n初始状态维度: {obs.shape}")
    print(f"初始状态前5维: {obs[:5]}")
    print(f"初始信息: {info}")

    # 测试 step
    print(f"\n执行 10 步模拟...")
    total_reward = 0.0
    for i in range(10):
        action = np.array([np.random.random()])
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        print(f"  步 {i+1:2d}: action={action[0]:.2f}, reward={reward:.4f}, "
              f"pos={info['position']:.2%}, dd={info['drawdown']:.2%}")

    print(f"\n总奖励: {total_reward:.4f}")
    print(f"Episode 统计: {env.get_episode_stats()}")

    env.close()
    print("\n✅ SB3TradingEnv 自测完成！")
