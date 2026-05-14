import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque
import random
from typing import Tuple, List, Dict
# gym模块已移除，使用自定义空间

# 设置随机种子
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
random.seed(SEED)

class MarketTypeDetector:
    """市场类型检测器"""
    
    def __init__(self, lookback: int = 20, volatility_threshold: float = 0.02, trend_threshold: float = 0.01):
        self.lookback = lookback
        self.volatility_threshold = volatility_threshold
        self.trend_threshold = trend_threshold
        
    def detect_market_type(self, prices: np.ndarray) -> str:
        """检测市场类型"""
        if len(prices) < self.lookback:
            return "unknown"
            
        recent_prices = prices[-self.lookback:]
        returns = np.diff(recent_prices) / recent_prices[:-1]
        
        # 计算波动率
        volatility = np.std(returns)
        
        # 计算趋势强度
        trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # 判断市场类型
        if abs(trend) < self.trend_threshold and volatility < self.volatility_threshold:
            return "sideways"  # 横盘
        elif trend < -self.trend_threshold:
            return "downtrend"  # 下跌
        elif volatility > self.volatility_threshold * 1.5:
            return "volatile"  # 波动
        else:
            return "uptrend"  # 上涨

class AdaptiveRiskController:
    """自适应风险控制器"""
    
    def __init__(self, base_stop_loss: float = 0.05, base_position_size: float = 0.1):
        self.base_stop_loss = base_stop_loss
        self.base_position_size = base_position_size
        
        # 不同市场类型的风险参数
        self.risk_params = {
            "uptrend": {"stop_loss": 0.03, "position_size": 0.15, "max_trades": 5},
            "sideways": {"stop_loss": 0.02, "position_size": 0.05, "max_trades": 2},
            "downtrend": {"stop_loss": 0.01, "position_size": 0.03, "max_trades": 1},
            "volatile": {"stop_loss": 0.04, "position_size": 0.08, "max_trades": 3},
            "unknown": {"stop_loss": 0.03, "position_size": 0.1, "max_trades": 3}
        }
        
    def get_risk_params(self, market_type: str) -> Dict:
        """获取风险参数"""
        return self.risk_params.get(market_type, self.risk_params["unknown"])

class ImprovedPPONetwork(nn.Module):
    """改进的PPO网络"""
    
    def __init__(self, input_dim: int, hidden_dim: int = 256, output_dim: int = 3):
        super(ImprovedPPONetwork, self).__init__()
        
        # 共享层
        self.shared = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU()
        )
        
        # 策略头
        self.policy = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, output_dim)
        )
        
        # 价值头
        self.value = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1)
        )
        
        # 市场类型嵌入
        self.market_embedding = nn.Embedding(5, 16)
        
    def forward(self, x: torch.Tensor, market_type: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """前向传播"""
        # 市场类型嵌入
        market_embed = self.market_embedding(market_type)
        
        # 拼接输入
        combined = torch.cat([x, market_embed], dim=-1)
        
        # 共享层
        features = self.shared(combined)
        
        # 策略和价值
        action_probs = F.softmax(self.policy(features), dim=-1)
        state_value = self.value(features)
        
        return action_probs, state_value

class ImprovedTradingAgent:
    """改进的交易智能体"""
    
    def __init__(self, 
                 state_dim: int = 10,
                 action_dim: int = 3,
                 learning_rate: float = 3e-4,
                 gamma: float = 0.99,
                 epsilon: float = 0.2,
                 memory_size: int = 10000,
                 batch_size: int = 64,
                 update_steps: int = 10):
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon
        self.batch_size = batch_size
        self.update_steps = update_steps
        
        # 网络
        self.network = ImprovedPPONetwork(state_dim + 16, 256, action_dim)  # +16 for market embedding
        self.optimizer = optim.Adam(self.network.parameters(), lr=learning_rate)
        
        # 记忆
        self.memory = deque(maxlen=memory_size)
        
        # 市场检测器和风险控制器
        self.market_detector = MarketTypeDetector()
        self.risk_controller = AdaptiveRiskController()
        
        # 状态跟踪
        self.current_market_type = "unknown"
        self.trade_count = 0
        self.max_trades_per_episode = 10
        
    def get_state(self, prices: np.ndarray, indicators: Dict) -> np.ndarray:
        """获取状态"""
        if len(prices) < 10:
            return np.zeros(self.state_dim)
            
        # 价格特征
        returns = np.diff(prices[-10:]) / prices[-10:-1]
        price_features = [
            returns[-1],  # 最新收益
            np.mean(returns[-5:]),  # 5期平均收益
            np.std(returns[-5:]),  # 5期波动率
            (prices[-1] - prices[-5]) / prices[-5],  # 5期趋势
            (prices[-1] - prices[-10]) / prices[-10],  # 10期趋势
        ]
        
        # 指标特征
        indicator_features = [
            indicators.get('rsi', 50) / 100,
            indicators.get('macd', 0),
            indicators.get('bb_position', 0.5),
            indicators.get('volume_ratio', 1),
            indicators.get('atr', 0)
        ]
        
        state = np.array(price_features + indicator_features)
        return state[:self.state_dim]  # 确保维度正确
        
    def get_market_type_index(self, market_type: str) -> int:
        """获取市场类型索引"""
        market_types = ["uptrend", "sideways", "downtrend", "volatile", "unknown"]
        return market_types.index(market_type) if market_type in market_types else 4
        
    def select_action(self, state: np.ndarray, market_type: str, training: bool = True) -> int:
        """选择动作"""
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        market_type_tensor = torch.LongTensor([self.get_market_type_index(market_type)])
        
        with torch.no_grad():
            action_probs, _ = self.network(state_tensor, market_type_tensor)
        
        if training:
            # 根据市场类型调整探索率
            exploration_rate = self._get_exploration_rate(market_type)
            if np.random.random() < exploration_rate:
                return np.random.randint(self.action_dim)
            else:
                return torch.multinomial(action_probs, 1).item()
        else:
            return torch.argmax(action_probs).item()
            
    def _get_exploration_rate(self, market_type: str) -> float:
        """获取探索率"""
        exploration_rates = {
            "uptrend": 0.1,
            "sideways": 0.3,
            "downtrend": 0.2,
            "volatile": 0.15,
            "unknown": 0.2
        }
        return exploration_rates.get(market_type, 0.2)
        
    def calculate_reward(self, 
                        action: int, 
                        price_change: float,
                        market_type: str,
                        position: int,
                        portfolio_value: float) -> float:
        """计算奖励"""
        # 基础奖励
        if action == 1:  # 买入
            if price_change > 0:
                base_reward = price_change * 10
            else:
                base_reward = -abs(price_change) * 5
        elif action == 2:  # 卖出
            if price_change < 0:
                base_reward = abs(price_change) * 10
            else:
                base_reward = -price_change * 5
        else:  # 持有
            base_reward = -abs(price_change) * 0.5
            
        # 市场类型调整
        market_multipliers = {
            "uptrend": 1.2,
            "sideways": 0.5,
            "downtrend": 0.3,
            "volatile": 0.8,
            "unknown": 1.0
        }
        
        # 交易频率惩罚
        frequency_penalty = 0
        if action != 0:  # 非持有动作
            self.trade_count += 1
            if self.trade_count > self.max_trades_per_episode:
                frequency_penalty = -0.5
                
        # 风险调整
        risk_params = self.risk_controller.get_risk_params(market_type)
        position_penalty = 0
        if position > 0 and market_type == "downtrend":
            position_penalty = -0.3 * position
            
        # 组合奖励
        total_reward = (base_reward * market_multipliers.get(market_type, 1.0) 
                       + frequency_penalty 
                       + position_penalty)
        
        return total_reward
        
    def update(self) -> float:
        """更新网络"""
        if len(self.memory) < self.batch_size:
            return 0.0
            
        batch = random.sample(self.memory, self.batch_size)
        states, market_types, actions, rewards, next_states, dones = zip(*batch)
        
        # 转换为张量
        states = torch.FloatTensor(np.array(states))
        market_types = torch.LongTensor(np.array(market_types))
        actions = torch.LongTensor(np.array(actions))
        rewards = torch.FloatTensor(np.array(rewards))
        next_states = torch.FloatTensor(np.array(next_states))
        dones = torch.FloatTensor(np.array(dones))
        
        # 计算优势
        with torch.no_grad():
            _, values = self.network(states, market_types)
            _, next_values = self.network(next_states, market_types)
            advantages = rewards + self.gamma * next_values.squeeze() * (1 - dones) - values.squeeze()
            
        # PPO更新
        for _ in range(self.update_steps):
            action_probs, values = self.network(states, market_types)
            
            # 计算策略损失
            dist = torch.distributions.Categorical(action_probs)
            log_probs = dist.log_prob(actions)
            ratio = torch.exp(log_probs - log_probs.detach())
            
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.epsilon, 1 + self.epsilon) * advantages
            policy_loss = -torch.min(surr1, surr2).mean()
            
            # 计算价值损失
            value_loss = F.mse_loss(values.squeeze(), rewards + self.gamma * next_values.squeeze() * (1 - dones))
            
            # 总损失
            total_loss = policy_loss + 0.5 * value_loss
            
            # 优化
            self.optimizer.zero_grad()
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 0.5)
            self.optimizer.step()
            
        return total_loss.item()
        
    def store_transition(self, state, market_type, action, reward, next_state, done):
        """存储经验"""
        market_type_idx = self.get_market_type_index(market_type)
        self.memory.append((state, market_type_idx, action, reward, next_state, done))

class TradingEnvironment:
    """交易环境"""
    
    def __init__(self, prices: np.ndarray, initial_balance: float = 10000.0):
        self.prices = prices
        self.initial_balance = initial_balance
        self.reset()
        
    def reset(self):
        """重置环境"""
        self.current_step = 20  # 从第20步开始，确保有足够的历史数据
        self.balance = self.initial_balance
        self.position = 0
        self.portfolio_value = self.initial_balance
        self.trades = []
        self.market_detector = MarketTypeDetector()
        
        return self._get_state()
        
    def _get_state(self) -> np.ndarray:
        """获取状态"""
        if self.current_step < 20:
            return np.zeros(10)
            
        prices = self.prices[:self.current_step + 1]
        indicators = self._calculate_indicators(prices)
        
        # 简化的状态
        recent_prices = prices[-10:]
        returns = np.diff(recent_prices) / recent_prices[:-1]
        state = [
            returns[-1] if len(returns) > 0 else 0,
            np.mean(returns[-5:]) if len(returns) >= 5 else 0,
            np.std(returns[-5:]) if len(returns) >= 5 else 0,
            (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0,
            (prices[-1] - prices[-10]) / prices[-10] if len(prices) >= 10 else 0,
            indicators.get('rsi', 50) / 100,
            indicators.get('macd', 0),
            indicators.get('bb_position', 0.5),
            indicators.get('volume_ratio', 1),
            indicators.get('atr', 0)
        ]
        
        return np.array(state)
        
    def _calculate_indicators(self, prices: np.ndarray) -> Dict:
        """计算技术指标"""
        indicators = {}
        
        if len(prices) >= 14:
            # RSI
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-14:])
            avg_loss = np.mean(losses[-14:])
            if avg_loss == 0:
                indicators['rsi'] = 100
            else:
                rs = avg_gain / avg_loss
                indicators['rsi'] = 100 - (100 / (1 + rs))
                
            # MACD
            ema12 = pd.Series(prices).ewm(span=12).mean().values[-1]
            ema26 = pd.Series(prices).ewm(span=26).mean().values[-1]
            indicators['macd'] = ema12 - ema26
            
            # Bollinger Bands
            sma = np.mean(prices[-20:])
            std = np.std(prices[-20:])
            bb_upper = sma + 2 * std
            bb_lower = sma - 2 * std
            if bb_upper != bb_lower:
                indicators['bb_position'] = (prices[-1] - bb_lower) / (bb_upper - bb_lower)
            else:
                indicators['bb_position'] = 0.5
                
            # ATR
            high_low = np.max(prices[-14:]) - np.min(prices[-14:])
            indicators['atr'] = high_low / prices[-1]
            
            # Volume ratio (simulated)
            indicators['volume_ratio'] = 1.0
            
        return indicators
        
    def get_market_type(self) -> str:
        """获取市场类型"""
        prices = self.prices[:self.current_step + 1]
        return self.market_detector.detect_market_type(prices)
        
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """执行动作"""
        current_price = self.prices[self.current_step]
        next_price = self.prices[self.current_step + 1] if self.current_step + 1 < len(self.prices) else current_price
        price_change = (next_price - current_price) / current_price
        
        # 执行交易
        if action == 1 and self.balance > 0:  # 买入
            self.position = self.balance / current_price
            self.balance = 0
        elif action == 2 and self.position > 0:  # 卖出
            self.balance = self.position * current_price
            self.position = 0
            
        # 更新组合价值
        self.portfolio_value = self.balance + self.position * next_price
        
        # 计算奖励
        market_type = self.get_market_type()
        reward = self._calculate_reward(action, price_change, market_type)
        
        # 更新步数
        self.current_step += 1
        
        # 检查是否结束
        done = self.current_step >= len(self.prices) - 1
        
        # 获取新状态
        next_state = self._get_state()
        
        info = {
            'portfolio_value': self.portfolio_value,
            'position': self.position,
            'balance': self.balance,
            'market_type': market_type,
            'price_change': price_change
        }
        
        return next_state, reward, done, info
        
    def _calculate_reward(self, action: int, price_change: float, market_type: str) -> float:
        """计算奖励"""
        # 基础奖励
        if action == 1:  # 买入
            if price_change > 0:
                base_reward = price_change * 10
            else:
                base_reward = -abs(price_change) * 5
        elif action == 2:  # 卖出
            if price_change < 0:
                base_reward = abs(price_change) * 10
            else:
                base_reward = -price_change * 5
        else:  # 持有
            base_reward = -abs(price_change) * 0.5
            
        # 市场类型调整
        market_multipliers = {
            "uptrend": 1.2,
            "sideways": 0.5,
            "downtrend": 0.3,
            "volatile": 0.8,
            "unknown": 1.0
        }
        
        # 风险惩罚
        risk_penalty = 0
        if self.position > 0 and market_type == "downtrend":
            risk_penalty = -0.3 * self.position
            
        total_reward = (base_reward * market_multipliers.get(market_type, 1.0) + risk_penalty)
        
        return total_reward

def generate_test_data(n_points: int = 1000) -> np.ndarray:
    """生成测试数据"""
    np.random.seed(SEED)
    
    # 生成不同市场阶段
    prices = []
    current_price = 100.0
    
    # 上涨阶段 (0-300)
    for i in range(300):
        current_price *= (1 + np.random.normal(0.001, 0.02))
        prices.append(current_price)
        
    # 横盘阶段 (300-500)
    for i in range(200):
        current_price *= (1 + np.random.normal(0, 0.01))
        prices.append(current_price)
        
    # 波动阶段 (500-700)
    for i in range(200):
        current_price *= (1 + np.random.normal(0, 0.03))
        prices.append(current_price)
        
    # 下跌阶段 (700-1000)
    for i in range(300):
        current_price *= (1 + np.random.normal(-0.002, 0.02))
        prices.append(current_price)
        
    return np.array(prices)

def test_improved_strategy():
    """测试改进策略"""
    print("=" * 60)
    print("改进的PPO交易策略测试")
    print("=" * 60)
    
    # 生成测试数据
    prices = generate_test_data(1000)
    
    # 创建环境和智能体
    env = TradingEnvironment(prices)
    agent = ImprovedTradingAgent()
    
    # 训练参数
    n_episodes = 50
    total_rewards = []
    portfolio_values = []
    
    print("\n开始训练...")
    
    for episode in range(n_episodes):
        state = env.reset()
        done = False
        episode_reward = 0
        episode_trades = 0
        
        while not done:
            market_type = env.get_market_type()
            action = agent.select_action(state, market_type, training=True)
            next_state, reward, done, info = env.step(action)
            
            agent.store_transition(state, market_type, action, reward, next_state, done)
            agent.update()
            
            state = next_state
            episode_reward += reward
            
            if action != 0:
                episode_trades += 1
                
        total_rewards.append(episode_reward)
        portfolio_values.append(env.portfolio_value)
        
        if (episode + 1) % 10 == 0:
            print(f"Episode {episode + 1}/{n_episodes}, "
                  f"Reward: {episode_reward:.2f}, "
                  f"Portfolio: {env.portfolio_value:.2f}, "
                  f"Trades: {episode_trades}")
            
    print("\n训练完成!")
    print(f"平均奖励: {np.mean(total_rewards):.2f}")
    print(f"最终组合价值: {portfolio_values[-1]:.2f}")
    print(f"收益率: {(portfolio_values[-1] - env.initial_balance) / env.initial_balance * 100:.2f}%")
    
    # 测试不同市场类型
    print("\n" + "=" * 60)
    print("不同市场类型测试")
    print("=" * 60)
    
    market_types = {
        "uptrend": (0, 300),
        "sideways": (300, 500),
        "volatile": (500, 700),
        "downtrend": (700, 1000)
    }
    
    for market_name, (start, end) in market_types.items():
        market_prices = prices[start:end]
        market_env = TradingEnvironment(market_prices)
        state = market_env.reset()
        done = False
        market_reward = 0
        market_trades = 0
        
        while not done:
            market_type = market_env.get_market_type()
            action = agent.select_action(state, market_type, training=False)
            next_state, reward, done, info = market_env.step(action)
            state = next_state
            market_reward += reward
            if action != 0:
                market_trades += 1
                
        market_return = (market_env.portfolio_value - market_env.initial_balance) / market_env.initial_balance * 100
        
        print(f"\n{market_name.upper()} 市场:")
        print(f"  收益率: {market_return:.2f}%")
        print(f"  交易次数: {market_trades}")
        print(f"  总奖励: {market_reward:.2f}")

if __name__ == "__main__":
    test_improved_strategy()