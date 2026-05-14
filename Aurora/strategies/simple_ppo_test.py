#!/usr/bin/env python3
"""
基于PPO的量化交易策略 - 快速测试版本
"""
import random
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque, namedtuple

# ==================== 简化的PPO代理 ====================
class SimplePPOAgent:
    def __init__(self, state_dim=5, action_dim=3):
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # 简化的线性策略网络
        self.network = nn.Sequential(
            nn.Linear(state_dim, 32),
            nn.ReLU(),
            nn.Linear(32, action_dim),
            nn.Softmax(dim=-1)
        )
        
        self.optimizer = optim.Adam(self.network.parameters(), lr=1e-3)
    
    def get_action(self, state):
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        probs = self.network(state_tensor)
        dist = torch.distributions.Categorical(probs)
        action = dist.sample()
        return action.item()
    
    def update(self, states, actions, rewards):
        if len(states) < 32:
            return
        
        states = torch.FloatTensor(states)
        actions = torch.LongTensor(actions)
        rewards = torch.FloatTensor(rewards)
        
        probs = self.network(states)
        action_probs = probs.gather(1, actions.unsqueeze(1)).squeeze()
        
        # 简单的策略梯度更新
        loss = -torch.mean(torch.log(action_probs + 1e-10) * rewards)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

# ==================== 交易代理 ====================
class TradingAgent:
    def __init__(self, initial_capital=100000):
        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.position = 0
        self.position_value = 0
        self.entry_price = 0
        
        self.ppo_agent = SimplePPOAgent(state_dim=5, action_dim=3)
        
        self.price_history = deque(maxlen=20)
        self.trade_history = []
        self.winning_trades = 0
        self.total_trades = 0
        
        # 用于训练的缓存
        self.train_states = []
        self.train_actions = []
        self.train_rewards = []
    
    def _compute_state(self, price):
        state = np.zeros(5)
        
        if len(self.price_history) >= 5:
            # 价格变化
            state[0] = (price - self.price_history[-1]) / self.price_history[-1] if self.price_history[-1] > 0 else 0
            
            # 波动率
            returns = [(self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1] 
                      for i in range(1, len(self.price_history)) if self.price_history[i-1] > 0]
            state[1] = np.std(returns) if returns else 0
            
            # 趋势
            ma5 = np.mean(list(self.price_history)[-5:])
            ma10 = np.mean(list(self.price_history)[-10:])
            state[2] = (ma5 - ma10) / ma10 if ma10 > 0 else 0
        
        # 仓位比例
        total_value = self.capital + self.position_value
        state[3] = self.position_value / total_value if total_value > 0 else 0
        
        # 资金比例
        state[4] = self.capital / self.initial_capital
        
        return state
    
    def update(self, price):
        self.price_history.append(price)
        self.position_value = self.position * price
        
        state = self._compute_state(price)
        action = self.ppo_agent.get_action(state)
        
        reward = 0
        prev_value = self.capital + self.position_value
        
        if action == 2 and self.capital > price:  # 买入
            shares = int(self.capital * 0.8 / price)
            if shares > 0:
                cost = shares * price
                fee = cost * 0.0001
                self.capital -= (cost + fee)
                self.position += shares
                self.entry_price = price
                self.total_trades += 1
        
        elif action == 0 and self.position > 0:  # 卖出
            proceeds = self.position * price
            fee = proceeds * 0.0001
            profit = proceeds - fee - self.position * self.entry_price
            
            self.capital += (proceeds - fee)
            
            if profit > 0:
                self.winning_trades += 1
            
            self.position = 0
            self.position_value = 0
            self.total_trades += 1
        
        # 计算奖励
        curr_value = self.capital + self.position_value
        reward = (curr_value - prev_value) / self.initial_capital * 100
        
        # 存储训练数据
        self.train_states.append(state)
        self.train_actions.append(action)
        self.train_rewards.append(reward)
        
        # 定期更新网络
        if len(self.train_states) >= 32:
            self.ppo_agent.update(self.train_states, self.train_actions, self.train_rewards)
            self.train_states = []
            self.train_actions = []
            self.train_rewards = []
        
        return action
    
    def get_performance(self):
        total_value = self.capital + self.position_value
        total_return = (total_value - self.initial_capital) / self.initial_capital
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'total_value': total_value,
            'total_return': total_return,
            'total_trades': self.total_trades,
            'win_rate': win_rate
        }

# ==================== 测试 ====================
def main():
    print("=" * 60)
    print("PPO量化交易策略 - 快速测试")
    print("=" * 60)
    
    # 测试参数
    test_days = 10
    minutes_per_day = 390
    base_price = 100
    
    # 测试不同市场类型
    market_types = {
        '横盘': {'mean': 0, 'std': 0.001},
        '上涨': {'mean': 0.0008, 'std': 0.001},
        '下跌': {'mean': -0.0008, 'std': 0.001},
        '波动': {'mean': 0, 'std': 0.002}
    }
    
    results = []
    
    for name, params in market_types.items():
        print(f"\n测试市场: {name}")
        
        agent = TradingAgent(initial_capital=100000)
        
        # 生成数据
        np.random.seed(42)
        returns = np.random.normal(params['mean'], params['std'], test_days * minutes_per_day)
        prices = base_price * np.cumprod(1 + returns)
        
        # 运行策略
        for price in prices:
            agent.update(price)
        
        # 获取结果
        perf = agent.get_performance()
        results.append({
            '市场': name,
            '最终价值': perf['total_value'],
            '收益率': perf['total_return'],
            '交易次数': perf['total_trades'],
            '胜率': perf['win_rate']
        })
        
        print(f"  最终价值: {perf['total_value']:,.0f}")
        print(f"  收益率: {perf['total_return']:.2%}")
        print(f"  交易次数: {perf['total_trades']}")
        print(f"  胜率: {perf['win_rate']:.2%}")
    
    # 输出汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    df = pd.DataFrame(results)
    print(df.to_string(formatters={
        '最终价值': '{:,.0f}'.format,
        '收益率': '{:.2%}'.format,
        '胜率': '{:.2%}'.format
    }))

if __name__ == "__main__":
    main()