#!/usr/bin/env python3
"""
PPO智能体实现
"""

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnNoModelImprovement
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.monitor import Monitor
import numpy as np
import pandas as pd

class PPOAgent:
    """
    PPO强化学习智能体
    """
    
    def __init__(self, env, config=None):
        """
        初始化PPO智能体
        
        Args:
            env: 交易环境
            config: 配置参数
        """
        if config is None:
            config = {}
        
        self.env = env
        self.config = config
        self.model = None
        
        # PPO参数
        self.learning_rate = config.get('learning_rate', 3e-4)
        self.n_steps = config.get('n_steps', 2048)
        self.batch_size = config.get('batch_size', 64)
        self.n_epochs = config.get('n_epochs', 10)
        self.gamma = config.get('gamma', 0.99)
        self.gae_lambda = config.get('gae_lambda', 0.95)
        self.clip_range = config.get('clip_range', 0.2)
        self.ent_coef = config.get('ent_coef', 0.01)
        self.vf_coef = config.get('vf_coef', 0.5)
        self.max_grad_norm = config.get('max_grad_norm', 0.5)
        
    def create_model(self):
        """
        创建PPO模型
        
        Returns:
            PPO模型
        """
        self.model = PPO(
            "MlpPolicy",
            self.env,
            learning_rate=self.learning_rate,
            n_steps=self.n_steps,
            batch_size=self.batch_size,
            n_epochs=self.n_epochs,
            gamma=self.gamma,
            gae_lambda=self.gae_lambda,
            clip_range=self.clip_range,
            ent_coef=self.ent_coef,
            vf_coef=self.vf_coef,
            max_grad_norm=self.max_grad_norm,
            verbose=1,
            tensorboard_log="./logs/tensorboard/"
        )
        return self.model
    
    def train(self, total_timesteps=100000, eval_env=None):
        """
        训练模型
        
        Args:
            total_timesteps: 训练步数
            eval_env: 评估环境
            
        Returns:
            训练后的模型
        """
        if not self.model:
            self.create_model()
        
        # 设置回调
        callbacks = []
        if eval_env:
            stop_callback = StopTrainingOnNoModelImprovement(
                max_no_improvement_evals=10,
                min_evals=20,
                verbose=1
            )
            
            eval_callback = EvalCallback(
                eval_env,
                best_model_save_path='./logs/best_model/',
                log_path='./logs/eval/',
                eval_freq=5000,
                deterministic=True,
                render=False,
                callback_after_eval=stop_callback
            )
            callbacks.append(eval_callback)
        
        # 训练
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks if callbacks else None,
            tb_log_name="fourier_rl_v2"
        )
        
        return self.model
    
    def predict(self, observation):
        """
        预测动作
        
        Args:
            observation: 观察
            
        Returns:
            动作
        """
        if not self.model:
            raise ValueError("Model not trained yet")
        
        action, _ = self.model.predict(observation, deterministic=True)
        return action
    
    def save(self, path):
        """
        保存模型
        
        Args:
            path: 保存路径
        """
        if self.model:
            self.model.save(path)
    
    def load(self, path, env=None):
        """
        加载模型
        
        Args:
            path: 模型路径
            env: 环境
            
        Returns:
            加载的模型
        """
        if env:
            self.env = env
        
        self.model = PPO.load(path, env=self.env)
        return self.model

class PPOTrainer:
    """
    PPO训练器
    """
    
    def __init__(self, config=None):
        """
        初始化PPO训练器
        
        Args:
            config: 配置参数
        """
        if config is None:
            config = {}
        
        self.config = config
    
    def create_env(self, df, feature_extractor, regime_detector):
        """
        创建训练环境
        
        Args:
            df: 价格数据
            feature_extractor: 特征提取器
            regime_detector: 市场状态识别器
            
        Returns:
            环境
        """
        from models.production_env import ProductionTradingEnv
        
        def make_env():
            env = ProductionTradingEnv(
                df=df,
                feature_extractor=feature_extractor,
                regime_detector=regime_detector,
                config=self.config.get('environment', {})
            )
            env = Monitor(env)
            return env
        
        env = DummyVecEnv([make_env])
        env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.0)
        
        return env
    
    def train_model(self, train_df, val_df, feature_extractor, regime_detector):
        """
        训练模型
        
        Args:
            train_df: 训练数据
            val_df: 验证数据
            feature_extractor: 特征提取器
            regime_detector: 市场状态识别器
            
        Returns:
            训练后的模型和环境
        """
        # 创建训练环境
        train_env = self.create_env(train_df, feature_extractor, regime_detector)
        
        # 创建验证环境
        val_env = self.create_env(val_df, feature_extractor, regime_detector)
        
        # 创建智能体
        agent = PPOAgent(train_env, self.config.get('ppo', {}))
        
        # 训练模型
        model = agent.train(
            total_timesteps=self.config.get('training', {}).get('total_timesteps', 100000),
            eval_env=val_env
        )
        
        return model, train_env
