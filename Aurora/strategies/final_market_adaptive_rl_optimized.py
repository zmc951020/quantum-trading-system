#!/usr/bin/env python3
"""
量化交易策略 - PPO强化学习优化版
由DeepSeek Flash自动生成
生成时间：2026-05-11 19:37:22
"""

我来为您生成完整的优化后策略代码。这是一个基于PPO算法的强化学习交易系统。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名: final_market_adaptive.py
描述: 基于PPO算法的自适应市场交易策略
作者: 量化交易策略专家
版本: 3.0
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque, namedtuple
import random
import logging
import pickle
import os
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 配置类 ====================
@dataclass
class PPOConfig:
    """PPO算法配置"""
    # 网络参数
    state_dim: int = 20  # 状态空间维度
    action_dim: int = 3  # 动作空间维度（买入、卖出、持有）
    hidden_dim: int = 256  # 隐藏层维度
    
    # PPO超参数
    lr_actor: float = 3e-4  # Actor学习率
    lr_critic: float = 1e-3  # Critic学习率
    gamma: float = 0.99  # 折扣因子
    gae_lambda: float = 0.95  # GAE参数
    clip_epsilon: float = 0.2  # PPO裁剪参数
    entropy_coef: float = 0.01  # 熵正则化系数
    value_loss_coef: float = 0.5  # 价值损失系数
    max_grad_norm: float = 0.5  # 梯度裁剪
    update_epochs: int = 10  # 每次更新轮数
    batch_size: int = 64  # 批次大小
    memory_size: int = 10000  # 经验回放大小
    
    # 训练参数
    target_kl: float = 0.01  # KL散度目标
    use_gae: bool = True  # 是否使用GAE
    normalize_advantage: bool = True  # 是否标准化优势

@dataclass
class TradingConfig:
    """交易配置"""
    # 交易参数
    initial_capital: float = 100000.0  # 初始资金
    max_position_size: float = 0.95  # 最大仓位比例
    min_position_size: float = 0.01  # 最小仓位比例
    trade_fee: float = 0.0003  # 交易手续费
    slippage: float = 0.0001  # 滑点
    
    # 止损止盈参数
    stop_loss_atr_multiplier: float = 2.0  # 止损ATR倍数
    take_profit_atr_multiplier: float = 4.0  # 止盈ATR倍数
    trailing_stop_activation: float = 0.02  # 追踪止损激活阈值
    trailing_stop_distance: float = 0.01  # 追踪止损距离
    
    # 频率控制
    min_trades_per_day: int = 50  # 最小每日交易次数
    max_trades_per_day: int = 200  # 最大每日交易次数
    min_hold_time: int = 5  # 最小持仓时间（分钟）
    
    # 风险管理
    max_drawdown: float = 0.15  # 最大回撤
    risk_per_trade: float = 0.02  # 每笔交易风险
    volatility_window: int = 20  # 波动率计算窗口

# ==================== PPO网络结构 ====================
class PPONetwork(nn.Module):
    """PPO网络：Actor-Critic架构"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super(PPONetwork, self).__init__()
        
        # 共享特征提取层
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.LayerNorm(hidden_dim // 2),
            nn.ReLU()
        )
        
        # Actor网络（策略网络）
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic网络（价值网络）
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1)
        )
        
        # 初始化权重
        self._init_weights()
        
    def _init_weights(self):
        """初始化网络权重"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0)
                
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        前向传播
        Args:
            state: 状态张量
        Returns:
            action_probs: 动作概率分布
            state_value: 状态价值
        """
        features = self.feature_layer(state)
        action_probs = self.actor(features)
        state_value = self.critic(features)
        return action_probs, state_value
    
    def get_action(self, state: torch.Tensor, deterministic: bool = False) -> Tuple[int, torch.Tensor, torch.Tensor]:
        """
        获取动作
        Args:
            state: 状态张量
            deterministic: 是否确定性选择
        Returns:
            action: 选择的动作
            log_prob: 动作的对数概率
            state_value: 状态价值
        """
        action_probs, state_value = self.forward(state)
        
        if deterministic:
            action = torch.argmax(action_probs, dim=-1)
        else:
            dist = torch.distributions.Categorical(action_probs)
            action = dist.sample()
            
        log_prob = torch.log(action_probs.gather(1, action.unsqueeze(1))).squeeze()
        
        return action.item(), log_prob, state_value

# ==================== PPO训练器 ====================
class PPOTrainer:
    """PPO算法训练器"""
    
    def __init__(self, config: PPOConfig):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 初始化网络
        self.network = PPONetwork(
            state_dim=config.state_dim,
            action_dim=config.action_dim,
            hidden_dim=config.hidden_dim
        ).to(self.device)
        
        # 优化器
        self.optimizer = optim.Adam([
            {'params': self.network.actor.parameters(), 'lr': config.lr_actor},
            {'params': self.network.critic.parameters(), 'lr': config.lr_critic}
        ])
        
        # 经验回放缓冲区
        self.memory = deque(maxlen=config.memory_size)
        self.Transition = namedtuple('Transition', 
                                   ['state', 'action', 'reward', 'next_state', 'done', 'log_prob', 'value'])
        
        # 训练统计
        self.training_stats = {
            'episode_rewards': [],
            'episode_lengths': [],
            'actor_losses': [],
            'critic_losses': [],
            'entropy_losses': []
        }
        
        logger.info(f"PPO训练器初始化完成，使用设备: {self.device}")
        
    def store_transition(self, state, action, reward, next_state, done, log_prob, value):
        """存储经验"""
        transition = self.Transition(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            log_prob=log_prob,
            value=value
        )
        self.memory.append(transition)
        
    def compute_gae(self, rewards: List[float], values: List[torch.Tensor], dones: List[bool]) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        """
        计算GAE（广义优势估计）
        Args:
            rewards: 奖励序列
            values: 价值序列
            dones: 终止标志序列
        Returns:
            advantages: 优势函数值
            returns: 折扣回报
        """
        advantages = []
        returns = []
        gae = 0
        
        values = [v.item() for v in values]
        
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = 0 if dones[t] else values[t]
            else:
                next_value = 0 if dones[t] else values[t + 1]
                
            delta = rewards[t] + self.config.gamma * next_value - values[t]
            gae = delta + self.config.gamma * self.config.gae_lambda * (1 - dones[t]) * gae
            
            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])
            
        return advantages, returns
    
    def update(self) -> Dict[str, float]:
        """
        更新网络参数
        Returns:
            loss_dict: 损失字典
        """
        if len(self.memory) < self.config.batch_size:
            return {'actor_loss': 0, 'critic_loss': 0, 'entropy_loss': 0}
            
        # 准备训练数据
        batch = random.sample(self.memory, min(self.config.batch_size, len(self.memory)))
        
        states = torch.FloatTensor([t.state for t in batch]).to(self.device)
        actions = torch.LongTensor([t.action for t in batch]).to(self.device)
        rewards = [t.reward for t in batch]
        dones = [t.done for t in batch]
        old_log_probs = torch.FloatTensor([t.log_prob for t in batch]).to(self.device)
        old_values = [t.value for t in batch]
        
        # 计算GAE
        advantages, returns = self.compute_gae(rewards, old_values, dones)
        advantages = torch.FloatTensor(advantages).to(self.device)
        returns = torch.FloatTensor(returns).to(self.device)
        
        if self.config.normalize_advantage:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            
        # PPO更新
        total_actor_loss = 0
        total_critic_loss = 0
        total_entropy_loss = 0
        
        for _ in range(self.config.update_epochs):
            # 前向传播
            action_probs, state_values = self.network(states)
            dist = torch.distributions.Categorical(action_probs)
            
            # 计算新对数概率
            new_log_probs = dist.log_prob(actions)
            entropy = dist.entropy().mean()
            
            # 计算比率
            ratio = torch.exp(new_log_probs - old_log_probs.detach())
            
            # PPO裁剪
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.config.clip_epsilon, 1 + self.config.clip_epsilon) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()
            
            # Critic损失
            value_pred = state_values.squeeze()
            critic_loss = F.mse_loss(value_pred, returns)
            
            # 总损失
            total_loss = (actor_loss + 
                         self.config.value_loss_coef * critic_loss - 
                         self.config.entropy_coef * entropy)
            
            # 反向传播
            self.optimizer.zero_grad()
            total_loss.backward()
            nn.utils.clip_grad_norm_(self.network.parameters(), self.config.max_grad_norm)
            self.optimizer.step()
            
            total_actor_loss += actor_loss.item()
            total_critic_loss += critic_loss.item()
            total_entropy_loss += entropy.item()
            
        # 记录训练统计
        avg_actor_loss = total_actor_loss / self.config.update_epochs
        avg_critic_loss = total_critic_loss / self.config.update_epochs
        avg_entropy_loss = total_entropy_loss / self.config.update_epochs
        
        self.training_stats['actor_losses'].append(avg_actor_loss)
        self.training_stats['critic_losses'].append(avg_critic_loss)
        self.training_stats['entropy_losses'].append(avg_entropy_loss)
        
        return {
            'actor_loss': avg_actor_loss,
            'critic_loss': avg_critic_loss,
            'entropy_loss': avg_entropy_loss
        }
    
    def save_model(self, path: str):
        """保存模型"""
        torch.save({
            'network_state_dict': self.network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_stats': self.training_stats,
            'config': self.config
        }, path)
        logger.info(f"模型已保存到: {path}")
        
    def load_model(self, path: str):
        """加载模型"""
        if os.path.exists(path):
            checkpoint = torch.load(path, map_location=self.device)
            self.network.load_state_dict(checkpoint['network_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.training_stats = checkpoint['training_stats']
            logger.info(f"模型已从 {path} 加载")
            return True
        return False

# ==================== 增强的强化学习交易代理 ====================
class EnhancedRLTrader:
    """增强的强化学习交易代理"""
    
    def __init__(self, ppo_config: PPOConfig, trading_config: TradingConfig):
        self.ppo_config = ppo_config
        self.trading_config = trading_config
        self.trainer = PPOTrainer(ppo_config)
        
        # 交易状态
        self.capital = trading_config.initial_capital
        self.position = 0  # 当前持仓量
        self.position_value = 0  # 持仓市值
        self.total_trades = 0
        self.daily_trades = 0
        self.current_day = None
        
        # 持仓记录
        self.holdings = []  # 持仓历史
        self.trade_history = []  # 交易历史
        
        # 技术指标缓存
        self.price_history = deque(maxlen=100)
        self.volume_history = deque(maxlen=100)
        self.atr = 0  # 平均真实波幅
        self.volatility = 0  # 波动率
        
        # 止损止盈
        self.stop_loss_price = 0
        self.take_profit_price = 0
        self.trailing_stop_price = 0
        self.entry_price = 0
        
        # 性能统计
        self.performance_stats = {
            'total_return': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'avg_profit': 0,
            'avg_loss': 0
        }
        
        logger.info("增强的RL交易代理初始化完成")
        
    def _compute_state(self, market_data: Dict) -> np.ndarray:
        """
        计算状态向量
        Args:
            market_data: 市场数据字典
        Returns:
            state: 状态向量
        """
        state = np.zeros(self.ppo_config.state_dim)
        
        try:
            # 1. 价格特征（0-4）
            current_price = market_data.get('close', 0)
            if len(self.price_history) > 0:
                prev_price = self.price_history[-1]
                price_change = (current_price - prev_price) / prev_price
                state[0] = price_change  # 即时价格变化
                state[1] = np.mean([(self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1] 
                                   for i in range(1, len(self.price_history))])  # 平均价格变化
                state[2] = current_price / np.mean(self.price_history) - 1  # 相对位置
                
            # 2. 技术指标（5-9）
            if len(self.price_history) >= 20:
                # RSI
                gains = []
                losses = []
                for i in range(1, min(15, len(self.price_history))):
                    change = self.price_history[-i] - self.price_history[-i-1]
                    if change > 0:
                        gains.append(change)
                    else:
                        losses.append(abs(change))
                avg_gain = np.mean(gains) if gains else 0
                avg_loss = np.mean(losses) if losses else 0
                rs = avg_gain / (avg_loss + 1e-10)
                rsi = 100 - (100 / (1 + rs))
                state[5] = rsi / 100  # 归一化RSI
                
                # 波动率
                returns = [(self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1] 
                          for i in range(1, len(self.price_history))]
                state[6] = np.std(returns) * np.sqrt(252)  # 年化波动率
                
                # 趋势强度
                short_ma = np.mean(list(self.price_history)[-5:])
                long_ma = np.mean(list(self.price_history))
                state[7] = (short_ma - long_ma) / long_ma  # 趋势强度
                
            # 3. 持仓状态（10-14）
            state[10] = self.position / (self.capital + self.position_value + 1e-10)  # 仓位比例
            state[11] = self.capital / self.trading_config.initial_capital  # 资金比例
            state[12] = self.total_trades / 1000  # 累计交易次数
            
            # 4. 风险指标（15-19）
            state[15] = self.volatility  # 当前波动率
            state[16] = self.atr / current_price if current_price > 0 else 0  # 相对ATR
            state[17] = self.performance_stats.get('max_drawdown', 0)  # 最大回撤
            state[18] = self.performance_stats.get('sharpe_ratio', 0)  # 夏普比率
            state[19] = self.total_trades / max(1, self.daily_trades)  # 交易频率
            
        except Exception as e:
            logger.error(f"计算状态向量时出错: {e}")
            
        return state
    
    def _compute_reward(self, action: int, price: float, next_price: float) -> float:
        """
        计算奖励
        Args:
            action: 执行的动作
            price: 当前价格
            next_price: 下一时刻价格
        Returns:
            reward: 奖励值
        """
        reward = 0
        
        try:
            # 1. 即时利润
            if self.position > 0:
                profit = self.position * (next_price - price)
                reward += profit / self.trading_config.initial_capital * 100  # 归一化
            
            # 2. 交易成本惩罚
            if action != 1:  # 非持有动作
                trade_value = self.capital * self.trading_config.trade_fee
                reward -= trade_value / self.trading_config.initial_capital * 10
            
            # 3. 风险惩罚
            if self.volatility > 0.02:  # 高波动率惩罚
                reward -= self.volatility * 5
                
            # 4. 频率奖励
            if self.daily_trades < self.trading_config.min_trades_per_day:
                reward += 0.01  # 鼓励交易
            elif self.daily_trades > self.trading_config.max_trades_per_day:
                reward -= 0.02  # 惩罚过度交易
                
            # 5. 多样性奖励
            if len(self.trade_history) > 0:
                recent_actions = [t['action'] for t in self.trade_history[-10:]]
                if len(set(recent_actions)) >= 2:  # 动作多样性
                    reward += 0.005
                    
        except Exception as e:
            logger.error(f"计算奖励时出错: {e}")
            
        return reward
    
    def _update_stop_loss_take_profit(self, price: float):
        """更新止损止盈价格"""
        if self.position > 0:
            # 基于ATR的动态止损
            self.stop_loss_price = self.entry_price - self.atr * self.trading_config.stop_loss_atr_multiplier
            self.take_profit_price = self.entry_price + self.atr * self.trading_config.take_profit_atr_multiplier
            
            # 追踪止损
            if price > self.entry_price * (1 + self.trading_config.trailing_stop_activation):
                new_stop = price * (1 - self.trading_config.trailing_stop_distance)
                self.trailing_stop_price = max(self.trailing_stop_price, new_stop)
                
    def _check_stop_loss_take_profit(self, price: float) -> bool:
        """检查是否触发止损止盈"""
        if self.position <= 0:
            return False
            
        # 检查止损
        if price <= self.stop_loss_price or price <= self.trailing_stop_price:
            logger.info(f"触发止损: 当前价格 {price:.2f}, 止损价格 {self.stop_loss_price:.2f}")
            return True
            
        # 检查止盈
        if price >= self.take_profit_price:
            logger.info(f"触发止盈: 当前价格 {price:.2f}, 止盈价格 {self.take_profit_price:.2f}")
            return True
            
        return False
    
    def execute_trade(self, action: int, price: float, volume: int = 0) -> Dict:
        """
        执行交易
        Args:
            action: 0-卖出, 1-持有, 2-买入
            price: 交易价格
            volume: 交易量
        Returns:
            trade_result: 交易结果
        """
        trade_result = {
            'action': action,
            'price': price,
            'volume': 0,
            'value': 0,
            'fee': 0,
            'profit': 0,
            'success': False
        }
        
        try:
            if action == 2:  # 买入
                # 计算可买入数量
                available_capital = self.capital * (1 - self.trading_config.trade_fee)
                max_shares = int(available_capital / price)
                
                if max_shares > 0:
                    # 限制仓位
                    max_position_value = (self.capital + self.position_value) * self.trading_config.max_position_size
                    current_position_value = self.position * price
                    available_position_value = max_position_value - current_position_value
                    
                    buy_value = min(available_capital, available_position_value)
                    buy_shares = int(buy_value / price)
                    
                    if buy_shares > 0:
                        fee = buy_shares * price * self.trading_config.trade_fee
                        self.position += buy_shares
                        self.capital -= buy_shares * price + fee
                        self.position_value = self.position * price
                        self.entry_price = price
                        
                        trade_result['volume'] = buy_shares
                        trade_result['value'] = buy_shares * price
                        trade_result['fee'] = fee
                        trade_result['success'] = True
                        
                        logger.debug(f"买入 {buy_shares} 股，价格 {price:.2f}，费用 {fee:.2f}")
                        
            elif action == 0:  # 卖出
                if self.position > 0:
                    sell_shares = self.position
                    fee = sell_shares * price * self.trading_config.trade_fee
                    profit = sell_shares * (price - self.entry_price) - fee
                    
                    self.capital += sell_shares * price - fee
                    self.position = 0
                    self.position_value = 0
                    
                    trade_result['volume'] = sell_shares
                    trade_result['value'] = sell_shares * price
                    trade_result['fee'] = fee
                    trade_result['profit'] = profit
                    trade_result['success'] = True
                    
                    logger.debug(f"卖出 {sell_shares} 股，价格 {price:.2f}，利润 {profit:.2f}")
                    
            # 更新交易统计
            if trade_result['success']:
                self.total_trades += 1
                self.daily_trades += 1
                self.trade_history.append(trade_result)
                
        except Exception as e:
            logger.error(f"执行交易时出错: {e}")
            
        return trade_result
    
    def step(self, market_data: Dict) -> Tuple[int, float, Dict]:
        """
        执行一步交易
        Args:
            market_data: 市场数据
        Returns:
            action: 执行的动作
            reward: 获得的奖励
            info: 额外信息
        """
        # 更新市场数据
        price = market_data.get('close', 0)
        self.price_history.append(price)
        
        # 计算技术指标
        if len(self.price_history) >= 2:
            self.volatility = np.std([(self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1] 
                                     for i in range(1, len(self.price_history))])
            
        # 检查止损止盈
        if self._check_stop_loss_take_profit(price):
            action = 0  # 强制卖出
        else:
            # 获取状态
            state = self._compute_state(market_data)
            
            # PPO选择动作
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.trainer.device)
                action, log_prob, value = self.trainer.network.get_action(state_tensor)
                
        # 执行交易
        trade_result = self.execute_trade(action, price)
        
        # 更新止损止盈
        if action == 2:  # 买入后更新
            self._update_stop_loss_take_profit(price)
            
        # 计算奖励
        next_price = market_data.get('next_close', price)
        reward = self._compute_reward(action, price, next_price)
        
        # 存储经验
        self.trainer.store_transition(state, action, reward, state, False, log_prob, value)
        
        # 更新性能统计
        self._update_performance_stats()
        
        info = {
            'capital': self.capital,
            'position': self.position,
            'position_value': self.position_value,
            'total_trades': self.total_trades,
            'daily_trades': self.daily_trades,
            'trade_result': trade_result
        }
        
        return action, reward, info
    
    def _update_performance_stats(self):
        """更新性能统计"""
        if len(self.trade_history) > 0:
            profits = [t.get('profit', 0) for t in self.trade_history if 'profit' in t]
            if profits:
                winning_trades = [p for p in profits if p > 0]
                losing_trades = [p for p in profits if p < 0]
                
                self.performance_stats['win_rate'] = len(winning_trades) / len(profits) if profits else 0
                self.performance_stats['avg_profit'] = np.mean(winning_trades) if winning_trades else 0
                self.performance_stats['avg_loss'] = np.mean(losing_trades) if losing_trades else 0
                
                # 计算夏普比率
                if len(profits) > 1:
                    self.performance_stats['sharpe_ratio'] = np.mean(profits) / (np.std(profits) + 1e-10) * np.sqrt(252)
                    
    def reset_daily_stats(self):
        """重置每日统计"""
        self.daily_trades = 0
        
    def save_agent(self, path: str):
        """保存代理状态"""
        agent_data = {
            'capital': self.capital,
            'position': self.position,
            'position_value': self.position_value,
            'total_trades': self.total_trades,
            'performance_stats': self.performance_stats,
            'trading_config': self.trading_config
        }
        
        with open(path + '_agent.pkl', 'wb') as f:
            pickle.dump(agent_data, f)
            
        self.trainer.save_model(path + '_model.pt')
        logger.info(f"代理状态已保存到: {path}")
        
    def load_agent(self, path: str):
        """加载代理状态"""
        agent_path = path + '_agent.pkl'
        model_path = path + '_model.pt'
        
        if os.path.exists(agent_path):
            with open(agent_path, 'rb') as f:
                agent_data = pickle.load(f)
                self.capital = agent_data['capital']
                self.position = agent_data['position']
                self.position_value = agent_data['position_value']
                self.total_trades = agent_data['total_trades']
                self.performance_stats = agent_data['performance_stats']
                
        if os.path.exists(model_path):
            self.trainer.load_model(model_path)
            
        logger.info(f"代理状态已从 {path} 加载")

# ==================== 最终自适应网格策略 ====================
class FinalMarketAdaptiveGrid:
    """最终自适应网格交易策略"""
    
    def __init__(self, ppo_config: Optional[PPOConfig] = None, 
                 trading_config: Optional[TradingConfig] = None):
        # 初始化配置
        self.ppo_config = ppo_config or PPOConfig()
        self.trading_config = trading_config or TradingConfig()
        
        # 初始化RL交易代理
        self.rl_trader = EnhancedRLTrader(self.ppo_config, self.trading_config)
        
        # 网格参数
        self.grid_levels = 10  # 网格层数
        self.grid_spacing = 0.005  # 网格间距
        self.grid_positions = {}  # 网格持仓
        
        # 市场状态
        self.market_regime = 'neutral'  # bull, bear, neutral
        self.regime_confidence = 0.5
        
        # 性能监控
        self.performance_monitor = {
            'equity_curve': [],
            'drawdown_curve': [],
            'trade_times': [],
            'daily_returns': []
        }
        
        # 模型路径
        self.model_path = os.path.join(os.path.dirname(__file__), 'models')
        os.makedirs(self.model_path, exist_ok=True)
        
        logger.info("最终自适应网格策略初始化完成")
        
    def _detect_market_regime(self, market_data: pd.DataFrame) -> Tuple[str, float]:
        """
        检测市场状态
        Args:
            market_data: 市场数据
        Returns:
            regime: 市场状态
            confidence: 置信度
        """
        try:
            # 计算技术指标
            close_prices = market_data['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            
            # 趋势判断
            short_ma = np.mean(close_prices[-20:])
            long_ma = np.mean(close_prices[-50:])
            trend_strength = (short_ma - long_ma) / long_ma
            
            # 波动率判断
            volatility = np.std(returns[-20:]) * np.sqrt(252)
            
            # 动量判断
            momentum = np.sum(returns[-10:])
            
            # 综合判断
            if trend_strength > 0.02 and momentum > 0:
                regime = 'bull'
                confidence = min(1.0, abs(trend_strength) * 10)
            elif trend_strength < -0.02 and momentum < 0:
                regime = 'bear'
                confidence = min(1.0, abs(trend_strength) * 10)
            else:
                regime = 'neutral'
                confidence = max(0, 1 - abs(trend_strength) * 5)
                
            return regime, confidence
            
        except Exception as e:
            logger.error(f"检测市场状态时出错: {e}")
            return 'neutral', 0.5
            
    def _adjust_grid_parameters(self):
        """调整网格参数"""
        # 根据市场状态调整网格间距
        if self.market_regime == 'bull':
            self.grid_spacing = 0.008  # 牛市扩大网格
        elif self.market_regime == 'bear':
            self.grid_spacing = 0.003  # 熊市缩小网格
        else:
            self.grid_spacing = 0.005  # 中性市场
            
        # 根据波动率调整网格层数
        if self.rl_trader.volatility > 0.03:
            self.grid_levels = 15  # 高波动增加层数
        else:
            self.grid_levels = 10  # 低波动减少层数
            
    def _execute_grid_trades(self, price: float) -> List[Dict]:
        """
        执行网格交易
        Args:
            price: 当前价格
        Returns:
            trades: 执行的交易列表
        """
        trades = []
        
        try:
            # 计算网格价格
            base_price = price
            grid_prices = [base_price * (1 + i * self.grid_spacing) for i in range(-self.grid_levels, self.grid_levels + 1)]
            
            # 检查每个网格
            for grid_price in grid_prices:
                if grid_price not in self.grid_positions:
                    # 新网格，建立仓位
                    position_size = self.trading_config.initial_capital / len(grid_prices) * 0.1
                    self.grid_positions[grid_price] = {
                        'size': position_size,
                        'entry_time': pd.Timestamp.now()
                    }
                    
                    # 执行RL交易
                    market_data = {'close': price, 'next_close': price}
                    action, reward, info = self.rl_trader.step(market_data)
                    
                    if action == 2:  # 买入
                        trade_result = self.rl_trader.execute_trade(2, price)
                        trades.append(trade_result)
                        
                elif abs(price - grid_price) / grid_price < self.grid_spacing * 0.5:
                    # 价格接近网格，检查是否需要平仓
                    position = self.grid_positions[grid_price]
                    profit_pct = (price - grid_price) / grid_price
                    
                    if profit_pct > self.trading_config.take_profit_atr_multiplier * self.rl_trader