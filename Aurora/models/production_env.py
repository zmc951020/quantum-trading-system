#!/usr/bin/env python3
"""
生产级交易环境
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Optional, Tuple, Dict, Any
import pandas as pd

class ProductionTradingEnv(gym.Env):
    """
    生产级交易环境
    - 支持多资产
    - 完整的交易成本模型
    - 动态滑点
    - 涨跌停限制
    - 仓位约束
    """
    
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}
    
    def __init__(
        self,
        df: pd.DataFrame,
        feature_extractor,
        regime_detector,
        config: Dict[str, Any],
        render_mode: Optional[str] = None
    ):
        """
        初始化交易环境
        
        Args:
            df: 价格数据
            feature_extractor: 特征提取器
            regime_detector: 市场状态识别器
            config: 配置参数
            render_mode: 渲染模式
        """
        super().__init__()
        
        self.df = df.reset_index(drop=True)
        self.feature_extractor = feature_extractor
        self.regime_detector = regime_detector
        self.config = config
        
        # 交易参数
        self.initial_capital = config.get('initial_capital', 1_000_000)
        self.commission_rate = config.get('commission_rate', 0.0003)  # 万三
        self.slippage_model = config.get('slippage_model', 'linear')  # linear/constant/square_root
        self.max_position_pct = config.get('max_position_pct', 0.95)  # 最大仓位95%
        self.min_position_pct = config.get('min_position_pct', 0.0)
        
        # 风控参数
        self.max_daily_loss = config.get('max_daily_loss', 0.02)  # 单日最大亏损2%
        self.max_drawdown_limit = config.get('max_drawdown_limit', 0.15)  # 最大回撤15%
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 止损5%
        self.take_profit_pct = config.get('take_profit_pct', 0.15)  # 止盈15%
        
        # A股特殊规则
        self.limit_up_down = config.get('limit_up_down', 0.10)  # 涨跌停10%
        self.t_plus_1 = config.get('t_plus_1', True)  # T+1制度
        
        # 动作空间：连续仓位 [-1, 1] 负数表示做空（如果允许）
        self.action_space = spaces.Box(
            low=-1.0, 
            high=1.0, 
            shape=(1,), 
            dtype=np.float32
        )
        
        # 状态空间构建
        self._build_observation_space()
        
        # 渲染设置
        self.render_mode = render_mode
        self.render_data = {}
        
        self.reset()
    
    def _build_observation_space(self):
        """
        构建状态空间
        """
        # 基础特征维度
        fourier_dim = len(self._get_dummy_fourier_features())
        
        # 市场微观结构特征
        micro_dim = 8
        
        # 账户状态特征
        account_dim = 6
        
        # 历史价格特征
        price_dim = 10
        
        total_dim = fourier_dim + micro_dim + account_dim + price_dim
        
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(total_dim,),
            dtype=np.float32
        )
    
    def _get_dummy_fourier_features(self):
        """获取虚拟特征用于维度推断"""
        dummy_prices = np.random.randn(100) + 100
        features = self.feature_extractor.extract_features(dummy_prices)
        # 展平特征
        flat_features = []
        for key, value in features.items():
            if isinstance(value, (list, np.ndarray)):
                flat_features.extend(np.array(value).flatten())
            else:
                flat_features.append(value)
        return np.array(flat_features)
    
    def reset(
        self, 
        seed: Optional[int] = None, 
        options: Optional[dict] = None
    ) -> Tuple[np.ndarray, dict]:
        """
        重置环境
        
        Args:
            seed: 随机种子
            options: 选项
            
        Returns:
            初始观察和信息
        """
        super().reset(seed=seed)
        
        # 初始化账户
        self.balance = self.initial_capital
        self.shares = 0
        self.portfolio_value = self.initial_capital
        self.peak_value = self.initial_capital
        
        # 交易记录
        self.trades = []
        self.daily_pnl = []
        self.current_day = 0
        
        # 持仓跟踪（用于T+1）
        self.available_shares = 0
        self.locked_shares = 0
        
        # 步骤计数器
        self.current_step = self.config.get('warmup_steps', 100)
        
        # 预热特征提取器
        for i in range(self.current_step):
            self.feature_extractor.extract_features(
                self.df['Close'].values[:i+1]
            )
        
        # 初始化状态检测器
        if len(self.df) > self.current_step:
            returns = np.diff(np.log(self.df['Close'].values[:self.current_step]))
            self.current_regime = self.regime_detector.predict_regime(
                returns, 
                self.df['Volume'].values[:self.current_step-1] if 'Volume' in self.df else None
            )
        
        observation = self._get_observation()
        info = self._get_info()
        
        return observation, info
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """
        执行一步交易
        
        Args:
            action: 动作
            
        Returns:
            观察、奖励、是否终止、是否截断、信息
        """
        # 动作裁剪
        action = np.clip(action, self.action_space.low, self.action_space.high)[0]
        
        # 获取当前价格
        current_price = self._get_current_price()
        
        # 检查涨跌停
        if self._is_limit_hit(current_price):
            # 涨跌停时无法交易
            action = 0.0
        
        # 市场状态调整
        regime = self.current_regime
        action = self._adjust_action_by_regime(action, regime)
        
        # 执行交易
        trade_executed = self._execute_trade(action, current_price)
        
        # 更新持仓价值
        prev_value = self.portfolio_value
        self.portfolio_value = self.balance + self.shares * current_price
        
        # 更新峰值
        self.peak_value = max(self.peak_value, self.portfolio_value)
        
        # 计算奖励
        reward = self._calculate_reward(prev_value, self.portfolio_value, trade_executed)
        
        # 检查风控条件
        terminated = self._check_risk_limits()
        
        # 更新步骤
        self.current_step += 1
        truncated = self.current_step >= len(self.df) - 1
        
        # 处理T+1结算
        if self.t_plus_1:
            self._settle_t_plus_1()
        
        # 更新市场状态
        if self.current_step % 20 == 0:  # 每20步更新一次状态
            self._update_market_regime()
        
        # 获取观察
        observation = self._get_observation() if not terminated else np.zeros(self.observation_space.shape)
        
        # 记录信息
        info = self._get_info()
        info['trade_executed'] = trade_executed
        info['regime'] = regime
        
        # 渲染
        if self.render_mode == "human":
            self._render_frame()
        
        return observation, reward, terminated, truncated, info
    
    def _execute_trade(self, action: float, price: float) -> bool:
        """
        执行交易订单
        
        Args:
            action: 动作
            price: 价格
            
        Returns:
            是否成交
        """
        if abs(action) < 0.01:  # 忽略过小的动作
            return False
        
        target_position_value = self.portfolio_value * action
        current_position_value = self.shares * price
        trade_value = target_position_value - current_position_value
        
        if abs(trade_value) < 1000:  # 最小交易金额1000元
            return False
        
        # 计算滑点
        slippage = self._calculate_slippage(trade_value, price)
        
        if trade_value > 0:  # 买入
            available_cash = self.balance * self.max_position_pct
            max_buy_value = min(trade_value, available_cash)
            
            if max_buy_value > 0:
                # 计算可买入股数（A股100股整数倍）
                buy_price = price * (1 + slippage)
                shares_to_buy = int(max_buy_value / (buy_price * 100)) * 100
                
                if shares_to_buy > 0:
                    cost = shares_to_buy * buy_price * (1 + self.commission_rate)
                    if cost <= self.balance:
                        self.shares += shares_to_buy
                        self.balance -= cost
                        
                        if self.t_plus_1:
                            self.locked_shares += shares_to_buy
                        
                        self.trades.append({
                            'step': self.current_step,
                            'type': 'BUY',
                            'shares': shares_to_buy,
                            'price': buy_price,
                            'cost': cost
                        })
                        return True
        
        else:  # 卖出
            available_shares = self.available_shares if self.t_plus_1 else self.shares
            max_sell_value = min(abs(trade_value), available_shares * price)
            
            if max_sell_value > 0:
                sell_price = price * (1 - slippage)
                shares_to_sell = int(max_sell_value / (sell_price * 100)) * 100
                shares_to_sell = min(shares_to_sell, available_shares)
                
                if shares_to_sell > 0:
                    revenue = shares_to_sell * sell_price * (1 - self.commission_rate)
                    self.shares -= shares_to_sell
                    self.balance += revenue
                    
                    if self.t_plus_1:
                        self.available_shares -= shares_to_sell
                    
                    self.trades.append({
                        'step': self.current_step,
                        'type': 'SELL',
                        'shares': shares_to_sell,
                        'price': sell_price,
                        'revenue': revenue
                    })
                    return True
        
        return False
    
    def _calculate_slippage(self, trade_value: float, price: float) -> float:
        """
        计算滑点
        
        Args:
            trade_value: 交易价值
            price: 价格
            
        Returns:
            滑点
        """
        if self.slippage_model == 'constant':
            return 0.0001  # 万分之一固定滑点
        elif self.slippage_model == 'linear':
            # 线性滑点：交易金额越大，滑点越大
            return min(0.001, abs(trade_value) / 10_000_000 * 0.001)
        else:  # square_root
            return min(0.002, np.sqrt(abs(trade_value) / price) / 10000 * 0.001)
    
    def _calculate_reward(self, prev_value: float, curr_value: float, traded: bool) -> float:
        """
        计算差分夏普比率奖励
        
        Args:
            prev_value: 之前的组合价值
            curr_value: 当前的组合价值
            traded: 是否交易
            
        Returns:
            奖励
        """
        # 收益率
        ret = (curr_value / prev_value) - 1.0
        
        # 更新EWMA统计量
        if not hasattr(self, 'ewma_return'):
            self.ewma_return = 0.0
            self.ewma_return_sq = 0.0
            self.decay = 0.02
        
        self.ewma_return = self.decay * ret + (1 - self.decay) * self.ewma_return
        self.ewma_return_sq = self.decay * (ret**2) + (1 - self.decay) * self.ewma_return_sq
        
        # 差分夏普比率
        if self.ewma_return_sq > 1e-8:
            sharpe_ratio = self.ewma_return / np.sqrt(self.ewma_return_sq)
        else:
            sharpe_ratio = 0.0
        
        # 交易成本惩罚
        cost_penalty = -0.001 if traded else 0.0
        
        # 回撤惩罚
        drawdown = (self.peak_value - curr_value) / self.peak_value
        drawdown_penalty = -drawdown * 0.1 if drawdown > 0.05 else 0.0
        
        # 持仓惩罚（鼓励持仓而非频繁交易）
        position_penalty = -0.0001 * abs(self.shares * self._get_current_price() / curr_value - 0.5)
        
        reward = sharpe_ratio + cost_penalty + drawdown_penalty + position_penalty
        
        return float(reward)
    
    def _check_risk_limits(self) -> bool:
        """
        检查风控限制
        
        Returns:
            是否终止
        """
        # 检查最大回撤
        drawdown = (self.peak_value - self.portfolio_value) / self.peak_value
        if drawdown > self.max_drawdown_limit:
            return True
        
        # 检查单日亏损
        if len(self.daily_pnl) > 0:
            daily_loss = abs(self.daily_pnl[-1]) / self.initial_capital
            if daily_loss > self.max_daily_loss:
                return True
        
        # 检查止损止盈
        if self.shares > 0:
            current_price = self._get_current_price()
            avg_cost = self._get_average_cost()
            
            if avg_cost > 0:
                pnl_pct = (current_price - avg_cost) / avg_cost
                
                if pnl_pct < -self.stop_loss_pct:
                    # 触发止损，强制卖出
                    self._execute_trade(-1.0, current_price)
                    return False  # 不止损环境，只是执行交易
                    
                elif pnl_pct > self.take_profit_pct:
                    # 触发止盈，强制卖出
                    self._execute_trade(-1.0, current_price)
                    return False
        
        return False
    
    def _get_observation(self) -> np.ndarray:
        """
        构建状态观察向量
        
        Returns:
            观察向量
        """
        # 1. 傅里叶特征
        price_history = self.df['Close'].values[:self.current_step+1]
        fourier_features = self.feature_extractor.extract_features(
            price_history,
            self.df['Volume'].values[:self.current_step+1] if 'Volume' in self.df else None
        )
        
        # 展平傅里叶特征
        flat_fourier = []
        for key in ['dominant_periods', 'cycle_strength', 'phase_position', 
                   'spectral_entropy', 'trend_confidence', 'stationarity']:
            value = fourier_features[key]
            if isinstance(value, (list, np.ndarray)):
                # 取前3个周期
                flat_fourier.extend(np.array(value).flatten()[:3])
            else:
                flat_fourier.append(float(value))
        
        # 2. 微观结构特征
        current_price = self._get_current_price()
        recent_prices = self.df['Close'].values[max(0, self.current_step-20):self.current_step+1]
        recent_volumes = self.df['Volume'].values[max(0, self.current_step-20):self.current_step+1] if 'Volume' in self.df else np.ones_like(recent_prices)
        
        micro_features = [
            (current_price - np.mean(recent_prices)) / (np.std(recent_prices) + 1e-8),  # Z-score
            np.corrcoef(recent_prices[:-1], recent_prices[1:])[0, 1] if len(recent_prices) > 1 else 0,  # 自相关
            recent_volumes[-1] / (np.mean(recent_volumes) + 1e-8),  # 相对成交量
            self._calculate_rsi(recent_prices),
            self._calculate_bollinger_position(current_price, recent_prices),
            self.current_regime / 2.0,  # 归一化状态
            len(self.trades) / 100.0,  # 交易频率
            self.portfolio_value / self.initial_capital - 1.0  # 累计收益
        ]
        
        # 3. 账户状态
        account_features = [
            self.balance / self.portfolio_value,  # 现金比例
            (self.shares * current_price) / self.portfolio_value,  # 持仓比例
            (self.peak_value - self.portfolio_value) / self.peak_value,  # 当前回撤
            len(self.trades) % 2,  # 是否持仓（0/1）
            self._get_average_cost() / current_price if self.shares > 0 else 0,  # 持仓成本相对位置
            np.std(self.daily_pnl[-20:]) / self.initial_capital if len(self.daily_pnl) >= 20 else 0  # 近期波动
        ]
        
        # 4. 价格形态特征
        price_features = []
        for window in [5, 10, 20, 30, 60]:
            if self.current_step >= window:
                ret = (current_price - self.df['Close'].values[self.current_step-window]) / self.df['Close'].values[self.current_step-window]
                price_features.append(ret)
            else:
                price_features.append(0.0)
        
        # 添加移动平均位置
        for window in [5, 10, 20, 60]:
            if self.current_step >= window:
                ma = np.mean(self.df['Close'].values[self.current_step-window:self.current_step+1])
                price_features.append((current_price - ma) / ma)
            else:
                price_features.append(0.0)
        
        # 拼接所有特征
        observation = np.concatenate([
            np.array(flat_fourier),
            np.array(micro_features),
            np.array(account_features),
            np.array(price_features)
        ])
        
        # 处理NaN和无穷值
        observation = np.nan_to_num(observation, nan=0.0, posinf=1.0, neginf=-1.0)
        
        return observation.astype(np.float32)
    
    def _calculate_rsi(self, prices, period=14):
        """计算RSI"""
        if len(prices) < period:
            return 50.0
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        return (rsi - 50) / 50  # 归一化到[-1, 1]
    
    def _calculate_bollinger_position(self, price, prices, period=20, std=2):
        """计算布林带位置"""
        if len(prices) < period:
            return 0.0
        
        ma = np.mean(prices[-period:])
        std_dev = np.std(prices[-period:])
        
        upper = ma + std * std_dev
        lower = ma - std * std_dev
        
        position = (price - lower) / (upper - lower) if upper != lower else 0.5
        return (position - 0.5) * 2  # 归一化到[-1, 1]
    
    def _get_current_price(self) -> float:
        """获取当前价格"""
        return self.df['Close'].values[self.current_step]
    
    def _get_average_cost(self) -> float:
        """计算平均持仓成本"""
        if self.shares == 0:
            return 0.0
        
        total_cost = 0.0
        total_shares = 0
        
        for trade in self.trades:
            if trade['type'] == 'BUY':
                total_cost += trade['cost']
                total_shares += trade['shares']
            elif trade['type'] == 'SELL':
                # 简化的FIFO成本计算
                total_shares -= trade['shares']
                if total_shares > 0:
                    total_cost = total_cost * (total_shares / (total_shares + trade['shares']))
        
        return total_cost / total_shares if total_shares > 0 else 0.0
    
    def _is_limit_hit(self, price: float) -> bool:
        """检查是否涨跌停"""
        if self.current_step == 0:
            return False
        
        prev_price = self.df['Close'].values[self.current_step - 1]
        change_pct = abs(price / prev_price - 1)
        
        return change_pct >= self.limit_up_down * 0.99  # 接近涨跌停
    
    def _adjust_action_by_regime(self, action: float, regime: int) -> float:
        """根据市场状态调整动作"""
        if regime == 2:  # 危机模式
            return min(action, 0.0)  # 只能卖出
        elif regime == 1:  # 高波动
            return action * 0.5  # 减半仓位
        else:  # 趋势市
            return action
    
    def _settle_t_plus_1(self):
        """T+1结算"""
        self.available_shares = self.shares - self.locked_shares
        self.locked_shares = 0
    
    def _update_market_regime(self):
        """更新市场状态"""
        if self.current_step >= 100:
            start_idx = max(0, self.current_step - 100)
            prices = self.df['Close'].values[start_idx:self.current_step]
            returns = np.diff(np.log(prices))
            volumes = self.df['Volume'].values[start_idx:self.current_step-1] if 'Volume' in self.df else None
            
            self.current_regime = self.regime_detector.predict_regime(returns, volumes)
    
    def _get_info(self) -> dict:
        """获取额外信息"""
        return {
            'step': self.current_step,
            'portfolio_value': self.portfolio_value,
            'balance': self.balance,
            'shares': self.shares,
            'current_price': self._get_current_price() if self.current_step < len(self.df) else 0,
            'regime': self.current_regime,
            'drawdown': (self.peak_value - self.portfolio_value) / self.peak_value
        }
    
    def _render_frame(self):
        """渲染当前状态"""
        if self.render_mode == "human":
            info = self._get_info()
            print(f"\rStep: {info['step']} | "
                  f"Value: {info['portfolio_value']:,.0f} | "
                  f"Drawdown: {info['drawdown']:.2%} | "
                  f"Regime: {info['regime']}", end="")
    
    def close(self):
        """清理资源"""
        pass
