#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RLEnhancer — 金融级强化学习仓位管理增强器
==========================================
基于 stable-baselines3 PPO 实现，是 Aurora 系统的核心增益模块。

架构：
  RLEnhancer (接口不变，enabled/disabled 开关)
    ├── SB3TradingEnv (gymnasium.Env) — 交易环境
    ├── PPO (stable_baselines3) — MlpPolicy [64, 64]
    ├── GPU 训练 + 推理
    ├── 模型持久化（自动保存/加载）
    └── 金融级奖励函数（夏普、回撤、交易成本、市场对齐）

设计原则：
  - 增益性注入：不修改现有策略代码，通过 enabled 开关控制
  - 回滚安全：enabled=False 立即回退到原始逻辑
  - 金融级：严格风险预算约束、模型版本管理

使用方式：
  enhancer = get_rl_enhancer()
  enhancer.enabled = True
  action = enhancer.predict(state_vector)  # 返回仓位建议 [0, 1]
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ==================== 可选依赖检查 ====================

SB3_AVAILABLE = False
GYMNASIUM_AVAILABLE = False

try:
    import gymnasium as gym
    GYMNASIUM_AVAILABLE = True
except ImportError:
    logger.warning("[RLEnhancer] gymnasium 未安装，使用模拟模式")

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_AVAILABLE = True
except ImportError:
    logger.warning("[RLEnhancer] stable-baselines3 未安装，使用模拟模式")

# 本地环境
try:
    from utils.sb3_trading_env import SB3TradingEnv, TradingEnvConfig, create_trading_env
    ENV_AVAILABLE = True
except ImportError:
    ENV_AVAILABLE = False
    logger.warning("[RLEnhancer] sb3_trading_env 未找到，使用内置降级环境")


# ==================== 配置 ====================

@dataclass
class RLEnhancerConfig:
    """RLEnhancer 配置"""
    # 模型
    model_dir: str = "model_storage/rl_enhancer"
    model_name: str = "ppo_position_manager"
    policy_kwargs: Dict = field(default_factory=lambda: {"net_arch": [64, 64]})

    # 训练
    total_timesteps: int = 100_000
    learning_rate: float = 3e-4
    n_steps: int = 2048
    batch_size: int = 64
    gamma: float = 0.99
    gae_lambda: float = 0.95

    # 推理
    deterministic_inference: bool = True
    inference_clip_range: float = 0.2

    # 风险
    max_position: float = 1.0
    min_position: float = 0.0
    emergency_position: float = 0.0  # 紧急清仓

    # 版本
    auto_save: bool = True
    save_frequency_steps: int = 10_000
    max_model_versions: int = 5


# ==================== 训练回调 ====================

class TrainingCallback(BaseCallback):
    """训练进度回调"""
    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self.episode_rewards: List[float] = []
        self.episode_lengths: List[int] = []
        self._current_episode_reward = 0.0
        self._current_episode_length = 0

    def _on_step(self) -> bool:
        self._current_episode_reward += self.locals.get("rewards", [0])[0]
        self._current_episode_length += 1

        if self.locals.get("dones", [False])[0]:
            self.episode_rewards.append(self._current_episode_reward)
            self.episode_lengths.append(self._current_episode_length)
            self._current_episode_reward = 0.0
            self._current_episode_length = 0
        return True


# ==================== RLEnhancer 主类 ====================

class RLEnhancer:
    """
    金融级强化学习仓位管理增强器

    特性：
    - 基于 stable-baselines3 PPO 的连续仓位控制
    - 20维市场状态输入 → 连续仓位 [0, 1] 输出
    - 自动模型持久化与版本管理
    - enabled/disabled 一键回滚
    - 紧急清仓机制
    """

    def __init__(self, config: Optional[RLEnhancerConfig] = None):
        self.config = config or RLEnhancerConfig()
        self.enabled: bool = True
        self._model: Any = None  # PPO 模型
        self._env: Any = None    # SB3TradingEnv
        self._vec_env: Any = None
        self._trained: bool = False
        self._training_history: Dict[str, List] = {
            "rewards": [],
            "episodes": [],
            "timestamps": [],
        }
        self._inference_count: int = 0
        self._emergency_mode: bool = False

        # 确保模型目录
        os.makedirs(self.config.model_dir, exist_ok=True)

        # 尝试加载已有模型
        if SB3_AVAILABLE:
            self._try_load_model()
        else:
            logger.info("[RLEnhancer] SB3 不可用，初始化为模拟模式")

        logger.info(
            f"[RLEnhancer] 初始化完成 | "
            f"enabled={self.enabled} | "
            f"trained={self._trained} | "
            f"SB3={SB3_AVAILABLE}"
        )

    # ==================== 公共接口 ====================

    def predict(
        self,
        state: Union[np.ndarray, List[float], Dict[str, Any]],
        deterministic: Optional[bool] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        预测仓位建议

        Args:
            state: 市场状态，支持三种格式：
                   - np.ndarray: 20维状态向量
                   - List[float]: 20维列表
                   - Dict[str, Any]: 原始市场数据字典（自动构建状态）
            deterministic: 是否确定性推理，默认使用配置值

        Returns:
            action: 仓位建议 [0, 1]
            info: 附加信息（置信度、风险标记等）
        """
        if not self.enabled:
            return 0.5, {"source": "disabled", "confidence": 0.0}

        # 紧急模式：强制清仓
        if self._emergency_mode:
            return self.config.emergency_position, {
                "source": "emergency",
                "confidence": 1.0,
                "reason": "emergency_mode_active",
            }

        # 无模型：返回默认中性仓位
        if not self._model or not self._trained:
            return 0.5, {"source": "fallback", "confidence": 0.0}

        det = deterministic if deterministic is not None else self.config.deterministic_inference

        try:
            # 状态预处理
            observation = self._preprocess_state(state)

            # SB3 推理
            if SB3_AVAILABLE:
                action, _states = self._model.predict(
                    observation, deterministic=det
                )
                # action 是 [batch_size, action_dim] 或 [action_dim,]
                if isinstance(action, np.ndarray):
                    action_val = float(np.clip(action.flat[0], 0, 1))
                else:
                    action_val = float(np.clip(action, 0, 1))
            else:
                # 模拟模式：基于信号置信度的简单规则
                action_val = float(np.clip(0.5 + 0.3 * (np.mean(observation) - 0.5), 0, 1))

            self._inference_count += 1

            info = {
                "source": "sb3_ppo" if SB3_AVAILABLE else "simulation",
                "confidence": self._compute_confidence(observation),
                "inference_count": self._inference_count,
                "deterministic": det,
            }

            return action_val, info

        except Exception as e:
            logger.error(f"[RLEnhancer] 推理失败: {e}，返回默认仓位")
            return 0.5, {"source": "error", "confidence": 0.0, "error": str(e)}

    def predict_batch(
        self,
        states: List[Union[np.ndarray, List[float], Dict[str, Any]]],
        deterministic: Optional[bool] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """批量预测"""
        return [self.predict(s, deterministic) for s in states]

    def train(
        self,
        market_data_seq: Optional[List[Dict[str, Any]]] = None,
        total_timesteps: Optional[int] = None,
        reset_model: bool = False,
    ) -> Dict[str, Any]:
        """
        训练/微调模型

        Args:
            market_data_seq: 市场数据序列（可选，不提供则使用模拟数据）
            total_timesteps: 总步数
            reset_model: 是否重置现有模型

        Returns:
            训练统计信息
        """
        if not SB3_AVAILABLE:
            return {
                "status": "skipped",
                "reason": "SB3 未安装",
                "message": "请执行: pip install stable-baselines3 gymnasium",
            }

        steps = total_timesteps or self.config.total_timesteps

        try:
            # 创建环境
            if ENV_AVAILABLE:
                self._env = create_trading_env()
            else:
                self._env = self._build_minimal_env()

            self._vec_env = DummyVecEnv([lambda: self._env])

            # 创建或加载模型
            if self._model is None or reset_model:
                self._model = PPO(
                    "MlpPolicy",
                    self._vec_env,
                    policy_kwargs=self.config.policy_kwargs,
                    learning_rate=self.config.learning_rate,
                    n_steps=self.config.n_steps,
                    batch_size=self.config.batch_size,
                    gamma=self.config.gamma,
                    gae_lambda=self.config.gae_lambda,
                    verbose=0,
                    tensorboard_log=None,
                )
                logger.info("[RLEnhancer] 创建新 PPO 模型")

            # 训练回调
            callback = TrainingCallback()

            # 如果用自定义数据，先预填充环境
            if market_data_seq:
                self._env.set_market_data_sequence(market_data_seq)

            # 训练
            logger.info(f"[RLEnhancer] 开始训练，总步数={steps}")
            self._model.learn(total_timesteps=steps, callback=callback, progress_bar=False)
            self._trained = True

            # 记录统计
            stats = {
                "status": "success",
                "total_timesteps": steps,
                "num_episodes": len(callback.episode_rewards),
                "avg_episode_reward": float(np.mean(callback.episode_rewards))
                if callback.episode_rewards else 0.0,
                "std_episode_reward": float(np.std(callback.episode_rewards))
                if callback.episode_rewards else 0.0,
                "avg_episode_length": float(np.mean(callback.episode_lengths))
                if callback.episode_lengths else 0.0,
                "timestamp": datetime.now().isoformat(),
            }
            self._training_history["rewards"].append(stats["avg_episode_reward"])
            self._training_history["episodes"].append(stats["num_episodes"])
            self._training_history["timestamps"].append(stats["timestamp"])

            # 自动保存
            if self.config.auto_save:
                self.save()

            logger.info(
                f"[RLEnhancer] 训练完成 | "
                f"总步数={steps} | "
                f"episodes={stats['num_episodes']} | "
                f"平均奖励={stats['avg_episode_reward']:.4f}"
            )

            return stats

        except Exception as e:
            logger.error(f"[RLEnhancer] 训练失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def save(self, version: Optional[str] = None) -> Optional[str]:
        """保存模型"""
        if not self._model or not SB3_AVAILABLE:
            logger.warning("[RLEnhancer] 无模型可保存")
            return None

        if version is None:
            version = datetime.now().strftime("%Y%m%d_%H%M%S")

        model_path = os.path.join(
            self.config.model_dir, f"{self.config.model_name}_{version}.zip"
        )

        try:
            self._model.save(model_path)
            logger.info(f"[RLEnhancer] 模型已保存: {model_path}")

            # 清理旧版本
            self._cleanup_old_models()

            # 保存元数据
            meta_path = model_path.replace(".zip", "_meta.pkl")
            metadata = {
                "version": version,
                "timestamp": datetime.now().isoformat(),
                "config": {k: v for k, v in self.config.__dict__.items()
                          if not k.startswith("_")},
                "training_history": self._training_history,
                "inference_count": self._inference_count,
            }
            with open(meta_path, "wb") as f:
                pickle.dump(metadata, f)

            return model_path

        except Exception as e:
            logger.error(f"[RLEnhancer] 保存失败: {e}")
            return None

    def load(self, version: Optional[str] = None) -> bool:
        """加载指定版本模型"""
        if not SB3_AVAILABLE:
            return False

        if version:
            model_path = os.path.join(
                self.config.model_dir, f"{self.config.model_name}_{version}.zip"
            )
        else:
            model_path = self._find_latest_model()

        if not model_path or not os.path.exists(model_path):
            logger.warning(f"[RLEnhancer] 模型文件不存在: {model_path}")
            return False

        try:
            self._env = self._ensure_env()
            self._vec_env = DummyVecEnv([lambda: self._env])
            self._model = PPO.load(model_path, env=self._vec_env)
            self._trained = True
            logger.info(f"[RLEnhancer] 模型已加载: {model_path}")
            return True
        except Exception as e:
            logger.error(f"[RLEnhancer] 加载失败: {e}")
            return False

    # ==================== 紧急控制 ====================

    def emergency_stop(self) -> None:
        """紧急停止：强制清仓"""
        self._emergency_mode = True
        logger.warning("[RLEnhancer] ⚠️ 紧急模式已激活 — 所有预测返回清仓信号")

    def emergency_reset(self) -> None:
        """重置紧急模式"""
        self._emergency_mode = False
        logger.info("[RLEnhancer] 紧急模式已解除")

    # ==================== 状态管理 ====================

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "enabled": self.enabled,
            "trained": self._trained,
            "sb3_available": SB3_AVAILABLE,
            "emergency_mode": self._emergency_mode,
            "inference_count": self._inference_count,
            "model_dir": self.config.model_dir,
            "training_history_length": len(self._training_history["rewards"]),
            "last_training_time": (
                self._training_history["timestamps"][-1]
                if self._training_history["timestamps"] else None
            ),
        }

    def reset_stats(self) -> None:
        """重置推理计数"""
        self._inference_count = 0

    # ==================== 内部方法 ====================

    def _preprocess_state(
        self,
        state: Union[np.ndarray, List[float], Dict[str, Any]],
    ) -> np.ndarray:
        """状态预处理：统一转为 20 维 numpy 数组"""
        if isinstance(state, dict):
            # 从字典构建状态（委托给环境）
            if self._env and hasattr(self._env, "_build_state"):
                return self._env._build_state(state)
            else:
                # 降级：从字典提取可用数值
                return self._dict_to_state_vector(state)
        elif isinstance(state, list):
            arr = np.array(state, dtype=np.float32)
        elif isinstance(state, np.ndarray):
            arr = state.astype(np.float32).copy()
        else:
            raise TypeError(f"不支持的状态类型: {type(state)}")

        # 确保 20 维
        if len(arr) < 20:
            padded = np.zeros(20, dtype=np.float32)
            padded[:len(arr)] = arr
            arr = padded
        elif len(arr) > 20:
            arr = arr[:20]

        return arr

    def _dict_to_state_vector(self, data: Dict[str, Any]) -> np.ndarray:
        """从字典构建状态向量（降级方案）"""
        state = np.zeros(20, dtype=np.float32)
        mapping = {
            0: ("price_change_pct", 0.0),
            1: ("volatility", 0.02),
            2: ("rsi", 50.0),
            3: ("macd_signal", 0.0),
            4: ("adx", 25.0),
            6: ("position", 0.5),
            8: ("market_regime_encoded", 0.5),
            9: ("signal_confidence", 0.5),
            10: ("risk_score", 30.0),
            11: ("volume_change_pct", 0.0),
        }
        for idx, (key, default) in mapping.items():
            state[idx] = data.get(key, default)
        return state

    def _compute_confidence(self, observation: np.ndarray) -> float:
        """基于观察的置信度估计"""
        # 信号置信度维度（索引 9）直接反映
        signal_conf = float(observation[9]) if len(observation) > 9 else 0.5
        # 风险评分反向影响置信度
        risk = float(observation[10]) / 100.0 if len(observation) > 10 else 0.3
        confidence = signal_conf * (1.0 - risk * 0.5)
        return float(np.clip(confidence, 0.01, 0.99))

    def _try_load_model(self) -> None:
        """尝试加载已有模型"""
        latest = self._find_latest_model()
        if latest:
            self.load()
        else:
            logger.info("[RLEnhancer] 未找到已有模型，需要训练")

    def _find_latest_model(self) -> Optional[str]:
        """查找最新模型文件"""
        model_dir = Path(self.config.model_dir)
        if not model_dir.exists():
            return None

        models = sorted(
            model_dir.glob(f"{self.config.model_name}_*.zip"),
            key=os.path.getmtime,
            reverse=True,
        )
        return str(models[0]) if models else None

    def _cleanup_old_models(self) -> None:
        """清理旧模型版本"""
        model_dir = Path(self.config.model_dir)
        models = sorted(
            model_dir.glob(f"{self.config.model_name}_*.zip"),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in models[self.config.max_model_versions:]:
            old.unlink()
            meta = Path(str(old).replace(".zip", "_meta.pkl"))
            if meta.exists():
                meta.unlink()

    def _ensure_env(self):
        """确保环境已创建"""
        if self._env is None:
            if ENV_AVAILABLE:
                self._env = create_trading_env()
            else:
                self._env = self._build_minimal_env()
        return self._env

    def _build_minimal_env(self):
        """构建最小化环境（降级方案）"""
        # 不依赖外部文件的简单 gym 环境
        if GYMNASIUM_AVAILABLE:
            class MinimalTradingEnv(gym.Env):
                def __init__(self):
                    self.observation_space = gym.spaces.Box(
                        low=-1, high=1, shape=(20,), dtype=np.float32
                    )
                    self.action_space = gym.spaces.Box(
                        low=0, high=1, shape=(1,), dtype=np.float32
                    )
                    self._step_count = 0
                    self._state = np.zeros(20, dtype=np.float32)

                def reset(self, seed=None, options=None):
                    super().reset(seed=seed)
                    self._step_count = 0
                    self._state = np.zeros(20, dtype=np.float32)
                    return self._state.copy(), {}

                def step(self, action):
                    self._step_count += 1
                    self._state = np.random.randn(20).astype(np.float32) * 0.1
                    reward = float(np.sin(self._step_count * 0.1) * 0.01)
                    terminated = self._step_count >= 1000
                    truncated = False
                    return self._state.copy(), reward, terminated, truncated, {}

            return MinimalTradingEnv()
        else:
            raise RuntimeError("gymnasium 未安装，无法创建环境")


# ==================== 单例/工厂 ====================

_enhancer_instance: Optional[RLEnhancer] = None


def get_rl_enhancer(config: Optional[RLEnhancerConfig] = None) -> RLEnhancer:
    """
    获取全局 RLEnhancer 单例

    使用方式：
        enhancer = get_rl_enhancer()
        enhancer.enabled = True
        action, info = enhancer.predict(state)

    Returns:
        RLEnhancer: 全局单例
    """
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = RLEnhancer(config=config)
    return _enhancer_instance


def create_rl_enhancer(config: Optional[RLEnhancerConfig] = None) -> RLEnhancer:
    """
    创建新的 RLEnhancer 实例（非单例）

    Returns:
        RLEnhancer: 新实例
    """
    return RLEnhancer(config=config)


# ==================== 自测 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("RLEnhancer 自测")
    print("=" * 60)

    enhancer = get_rl_enhancer()
    print(f"\n状态: {enhancer.get_status()}")

    # 测试预测（无模型时降级）
    print("\n--- 测试 predict（降级模式）---")
    for i in range(3):
        state = np.random.randn(20).astype(np.float32)
        action, info = enhancer.predict(state)
        print(f"  输入状态: mean={np.mean(state):.3f} → 仓位={action:.3f} | {info}")

    # 测试字典输入
    print("\n--- 测试 predict（字典输入）---")
    market_data = {
        "price_change_pct": 1.5,
        "volatility": 0.03,
        "rsi": 65.0,
        "signal_confidence": 0.8,
        "risk_score": 25.0,
        "market_regime": "bull",
    }
    action, info = enhancer.predict(market_data)
    print(f"  市场数据 → 仓位={action:.3f} | {info}")

    # 紧急模式
    print("\n--- 测试紧急模式 ---")
    enhancer.emergency_stop()
    action, info = enhancer.predict(np.zeros(20))
    print(f"  紧急模式 → 仓位={action:.3f} | {info}")
    enhancer.emergency_reset()

    # 禁用模式
    print("\n--- 测试禁用模式 ---")
    enhancer.enabled = False
    action, info = enhancer.predict(np.zeros(20))
    print(f"  禁用模式 → 仓位={action:.3f} | {info}")
    enhancer.enabled = True

    # 训练（如果 SB3 可用）
    if SB3_AVAILABLE:
        print("\n--- 测试训练（快速）---")
        stats = enhancer.train(total_timesteps=5000, reset_model=True)
        print(f"  训练统计: {stats}")
        print(f"  状态: {enhancer.get_status()}")
    else:
        print("\n" + "─" * 60)
        print("⚠️ stable-baselines3 未安装，跳过训练测试")
        print("  安装命令: pip install stable-baselines3 gymnasium")
        print("─" * 60)

    print("\n✅ RLEnhancer 自测完成！")