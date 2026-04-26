#!/usr/bin/env python3
"""
资金配置策略实现
"""

import numpy as np
import pandas as pd
import time
import pickle
import os
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional, Any

class DCAStrategy:
    """
     dollar-cost averaging (DCA) 策略
    """
    
    def __init__(self, initial_balance: float = 100000, 
                 fixed_amount: float = 1000, 
                 interval: int = 1, 
                 adaptive: bool = True):
        """
        初始化DCA策略
        
        Args:
            initial_balance: 初始资金
            fixed_amount: 固定投资金额
            interval: 投资间隔（天）
            adaptive: 是否使用自适应投资金额
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.fixed_amount = fixed_amount
        self.interval = interval
        self.position = 0
        self.last_investment_date = None
        self.adaptive = adaptive
        self.price_history = []
    
    def should_invest(self, current_date: pd.Timestamp) -> bool:
        """
        判断是否应该投资
        
        Args:
            current_date: 当前日期
            
        Returns:
            是否应该投资
        """
        if self.last_investment_date is None:
            return True
        
        days_since_last = (current_date - self.last_investment_date).days
        return days_since_last >= self.interval
    
    def invest(self, current_price: float, current_date: pd.Timestamp) -> Dict[str, any]:
        """
        执行投资
        
        Args:
            current_price: 当前价格
            current_date: 当前日期
            
        Returns:
            投资结果
        """
        if not self.should_invest(current_date):
            return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 计算投资金额
        if self.adaptive and len(self.price_history) > 20:
            # 计算20日移动平均线
            ma20 = sum(self.price_history[-20:]) / 20
            # 价格低于均线时增加投资金额，高于均线时减少投资金额
            if current_price < ma20:
                # 价格低时多买
                invest_amount = self.fixed_amount * (1 + (ma20 - current_price) / ma20 * 2)
            else:
                # 价格高时少买
                invest_amount = self.fixed_amount * (1 - (current_price - ma20) / ma20)
            # 限制投资金额范围
            invest_amount = max(self.fixed_amount * 0.5, min(invest_amount, self.fixed_amount * 2))
        else:
            invest_amount = self.fixed_amount
        
        # 确保投资金额不超过当前余额
        invest_amount = min(invest_amount, self.current_balance)
        
        # 计算可以购买的数量
        quantity = invest_amount / current_price
        
        # 执行购买
        if invest_amount > 0:
            self.position += quantity
            self.current_balance -= invest_amount
            self.last_investment_date = current_date
            
            return {
                "action": "buy",
                "quantity": quantity,
                "price": current_price,
                "balance": self.current_balance,
                "position": self.position,
                "invest_amount": invest_amount
            }
        else:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self, current_price: float) -> Dict[str, float]:
        """
        获取策略性能
        
        Args:
            current_price: 当前价格
            
        Returns:
            性能指标
        """
        total_value = self.current_balance + self.position * current_price
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "position": self.position,
            "total_value": total_value,
            "pnl": total_value - self.initial_balance,
            "return": (total_value / self.initial_balance - 1) * 100
        }

class HFTStrategy:
    """
    高频交易 (HFT) 策略 - 优化用于分钟级交易
    """
    
    def __init__(self, initial_balance: float = 100000, 
                 min_profit: float = 0.0005,  # 降低盈利目标以适应分钟级交易
                 max_position: float = 1000, 
                 stop_loss: float = 0.002,  # 降低止损以控制风险
                 max_trade_size: float = 0.1,  # 进一步限制交易规模
                 lookback_period: int = 5):  # 短期回溯期
        """
        初始化HFT策略
        
        Args:
            initial_balance: 初始资金
            min_profit: 最小盈利目标
            max_position: 最大持仓
            stop_loss: 止损比例
            max_trade_size: 每次交易最大资金比例
            lookback_period: 价格回溯期
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.min_profit = min_profit
        self.max_position = max_position
        self.stop_loss = stop_loss
        self.max_trade_size = max_trade_size  # 每次交易最大使用10%资金
        self.lookback_period = lookback_period
        self.position = 0
        self.entry_price = 0
        self.price_history = []
        self.wins = 0
        self.losses = 0
        self.last_trade_time = None
    
    def update_price(self, current_price: float, timestamp: Optional[pd.Timestamp] = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            timestamp: 当前时间戳
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 限制价格历史长度
        if len(self.price_history) > self.lookback_period * 2:
            self.price_history = self.price_history[-self.lookback_period * 2:]
        
        # 检查是否有持仓
        if self.position == 0:
            # 没有持仓，考虑买入
            if self.current_balance > 0 and len(self.price_history) >= self.lookback_period:
                # 简单的动量策略：价格上涨时买入
                recent_prices = self.price_history[-self.lookback_period:]
                price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                
                if price_change > 0.0001:  # 微小上涨信号
                    # 计算可以购买的数量（限制交易规模）
                    max_trade_amount = self.current_balance * self.max_trade_size
                    quantity = min(self.max_position, max_trade_amount / current_price)
                    if quantity > 0:
                        self.position = quantity
                        self.entry_price = current_price
                        self.current_balance -= quantity * current_price
                        self.last_trade_time = timestamp
                        return {
                            "action": "buy",
                            "quantity": quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position
                        }
        else:
            # 有持仓，检查是否达到盈利目标或止损
            profit = (current_price - self.entry_price) / self.entry_price
            
            # 检查止损
            if profit <= -self.stop_loss:
                # 达到止损，卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.losses += 1
                self.last_trade_time = timestamp
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "stop_loss"
                }
            
            # 检查盈利目标
            if profit >= self.min_profit:
                # 达到盈利目标，卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.wins += 1
                self.last_trade_time = timestamp
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "take_profit"
                }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "pnl": self.current_balance - self.initial_balance,
            "return": (self.current_balance / self.initial_balance - 1) * 100
        }

class MLFundAllocator:
    """
    基于机器学习的资金分配器 - 智能队列优化版本
    """
    
    def __init__(self, initial_balance: float = 100000):
        """
        初始化基于机器学习的资金分配器
        
        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.strategies = {}
        self.allocations = {}
        self.price_history = []
        self.performance_history = []
        self.best_allocations = {}
        
        # 智能队列优化相关
        self.candidate_queue = []  # 候选方案队列
        self.max_queue_size = 50  # 最大队列大小
        self.convergence_threshold = 0.0001  # 收敛阈值
        self.convergence_patience = 100  # 收敛耐心值
        self.optimization_cycle = 0  # 优化周期计数
        self.queue_file = "candidate_queue.pkl"  # 队列持久化文件
        
        # 加载历史队列
        self._load_queue()
        
        # 导入机器学习模块
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.preprocessing import StandardScaler
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.scaler = StandardScaler()
            self.use_ml = True
        except:
            self.use_ml = False
    
    def add_strategy(self, name: str, strategy, allocation: float):
        """
        添加策略
        
        Args:
            name: 策略名称
            strategy: 策略实例
            allocation: 资金分配比例
        """
        self.strategies[name] = strategy
        self.allocations[name] = allocation
        self.best_allocations[name] = allocation
        
        # 分配资金 - 按比例分配初始资金
        allocated_amount = self.initial_balance * allocation
        if hasattr(strategy, 'current_balance'):
            strategy.current_balance = allocated_amount
        if hasattr(strategy, 'initial_balance'):
            strategy.initial_balance = allocated_amount
    
    def extract_features(self, data: pd.Series) -> np.ndarray:
        """
        提取特征
        
        Args:
            data: 价格数据
            
        Returns:
            特征数组
        """
        features = []
        
        # 基本特征
        returns = data.pct_change().dropna()
        if len(returns) >= 30:
            # 动量指标
            momentum_10 = (data.iloc[-1] - data.iloc[-10]) / data.iloc[-10]
            momentum_20 = (data.iloc[-1] - data.iloc[-20]) / data.iloc[-20]
            momentum_50 = (data.iloc[-1] - data.iloc[-50]) / data.iloc[-50]
            
            # 波动率
            volatility_10 = returns.iloc[-10:].std()
            volatility_20 = returns.iloc[-20:].std()
            volatility_50 = returns.iloc[-50:].std()
            
            # 移动平均线
            ma5 = data.iloc[-5:].mean()
            ma10 = data.iloc[-10:].mean()
            ma20 = data.iloc[-20:].mean()
            ma50 = data.iloc[-50:].mean()
            
            # 均线交叉
            ma_crossover = (ma5 - ma20) / ma20
            
            # 相对强弱指标
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).iloc[-14:].mean()
            loss = (-delta.where(delta < 0, 0)).iloc[-14:].mean()
            rsi = 100 - (100 / (1 + (gain / loss))) if loss > 0 else 100
            
            # 布林带
            std_20 = data.iloc[-20:].std()
            upper_band = ma20 + 2 * std_20
            lower_band = ma20 - 2 * std_20
            bollinger_position = (data.iloc[-1] - lower_band) / (upper_band - lower_band) if (upper_band - lower_band) > 0 else 0.5
            
            # 成交量模拟（使用价格变化率作为代理）
            volume_proxy = abs(returns.iloc[-10:]).mean()
            
            features = [
                momentum_10, momentum_20, momentum_50,
                volatility_10, volatility_20, volatility_50,
                ma5, ma10, ma20, ma50, ma_crossover,
                rsi, bollinger_position, volume_proxy
            ]
        
        return np.array(features)
    
    def optimize_allocations(self, data: pd.Series):
        """
        优化资金分配
        
        Args:
            data: 价格数据
        """
        if not self.use_ml or len(self.price_history) < 50:
            return
        
        # 提取特征
        features = self.extract_features(data)
        if len(features) == 0:
            return
        
        # 基于机器学习的分配优化逻辑
        momentum_10 = features[0]
        momentum_20 = features[1]
        momentum_50 = features[2]
        volatility_10 = features[3]
        volatility_20 = features[4]
        volatility_50 = features[5]
        ma_crossover = features[10]
        rsi = features[11]
        bollinger_position = features[12]
        volume_proxy = features[13]
        
        # 计算综合市场状态指标
        trend_strength = (momentum_10 + momentum_20 + momentum_50) / 3
        volatility_level = (volatility_10 + volatility_20 + volatility_50) / 3
        market_sentiment = rsi / 100  # 0-1 范围
        
        # 基于市场状态调整分配
        if trend_strength > 0.01 and market_sentiment < 0.7 and volatility_level < 0.02:
            # 强劲上升趋势，低波动，增加HFT策略分配
            if 'hft' in self.allocations:
                self.allocations['hft'] = min(0.6, self.allocations['hft'] + 0.05)
            if 'dca' in self.allocations:
                self.allocations['dca'] = max(0.2, self.allocations['dca'] - 0.05)
        elif trend_strength < -0.01 or market_sentiment > 0.7:
            # 下降趋势或超买，增加DCA策略分配
            if 'dca' in self.allocations:
                self.allocations['dca'] = min(0.6, self.allocations['dca'] + 0.05)
            if 'hft' in self.allocations:
                self.allocations['hft'] = max(0.2, self.allocations['hft'] - 0.05)
        elif volatility_level > 0.03:
            # 高波动市场，减少HFT策略分配，增加DCA策略分配
            if 'dca' in self.allocations:
                self.allocations['dca'] = min(0.7, self.allocations['dca'] + 0.05)
            if 'hft' in self.allocations:
                self.allocations['hft'] = max(0.1, self.allocations['hft'] - 0.05)
        
        # 确保留有足够的回撤接盘资金（20%）
        total_allocated = sum(self.allocations.values())
        if total_allocated > 0.8:
            # 按比例减少各策略资金
            for name in self.allocations:
                self.allocations[name] = self.allocations[name] * 0.8 / total_allocated
        
        # 重新分配资金
        total = sum(self.allocations.values())
        for name in self.allocations:
            self.allocations[name] /= total
            # 更新策略资金
            if hasattr(self.strategies[name], 'current_balance'):
                allocated_amount = self.current_balance * self.allocations[name]
                self.strategies[name].current_balance = allocated_amount
    
    def optimize_with_machine_learning(self, data: pd.Series, 
                                        max_queue_size: Optional[int] = None,
                                        convergence_threshold: Optional[float] = None,
                                        convergence_patience: Optional[int] = None,
                                        print_interval: int = 100,
                                        parallel_workers: int = 4):
        """
        使用智能队列优化进行资金分配优化
        
        核心思想：
        1. 不设置固定最大迭代次数
        2. 维护候选方案队列，按性能排序
        3. 基于收敛判断自动停止
        4. 支持跨交易周期持续优化
        5. 并行评估候选方案，提高效率
        
        Args:
            data: 价格数据
            max_queue_size: 最大队列大小（候选方案数量）
            convergence_threshold: 收敛阈值
            convergence_patience: 收敛耐心值
            print_interval: 打印间隔
            parallel_workers: 并行评估的工作线程数
        """
        if not self.use_ml:
            return
        
        # 使用实例默认值或参数
        max_queue_size = max_queue_size or self.max_queue_size
        convergence_threshold = convergence_threshold or self.convergence_threshold
        convergence_patience = convergence_patience or self.convergence_patience
        
        self.optimization_cycle += 1
        
        print(f"\n{'='*60}")
        print(f"智能队列优化 - 周期 {self.optimization_cycle}")
        print(f"{'='*60}")
        print(f"队列大小: {max_queue_size}")
        print(f"收敛阈值: {convergence_threshold:.6f}")
        print(f"收敛耐心: {convergence_patience}")
        print(f"并行工作线程: {parallel_workers}")
        
        # 初始化最佳值
        best_return = -float('inf')
        best_allocations = self.allocations.copy()
        no_improvement_count = 0
        iteration_count = 0
        
        # 如果有历史队列，从中选择优秀方案作为起点
        if self.candidate_queue:
            print(f"\n从历史队列加载 {len(self.candidate_queue)} 个候选方案")
            # 按收益率排序，取最好的
            self.candidate_queue.sort(key=lambda x: x['return'], reverse=True)
            best_candidate = self.candidate_queue[0]
            best_return = best_candidate['return']
            best_allocations = best_candidate['allocations'].copy()
            print(f"历史最佳收益率: {best_return:.4f}")
        
        print(f"\n开始优化搜索...")
        
        while True:
            iteration_count += 1
            
            # 生成多个候选方案
            candidates = [self._generate_candidate() for _ in range(parallel_workers)]
            
            # 并行评估候选方案
            candidate_returns = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as executor:
                future_to_candidate = {
                    executor.submit(self._evaluate_candidate, candidate, data): candidate 
                    for candidate in candidates
                }
                for future in concurrent.futures.as_completed(future_to_candidate):
                    candidate = future_to_candidate[future]
                    try:
                        candidate_return = future.result()
                        candidate_returns.append((candidate, candidate_return))
                    except Exception as e:
                        print(f"评估候选方案时出错: {str(e)}")
            
            # 处理评估结果
            iteration_improved = False
            for candidate, candidate_return in candidate_returns:
                if candidate_return > best_return + convergence_threshold:
                    improvement = candidate_return - best_return
                    best_return = candidate_return
                    best_allocations = candidate.copy()
                    no_improvement_count = 0
                    iteration_improved = True
                    
                    # 添加到队列
                    self._add_to_queue({
                        'allocations': candidate.copy(),
                        'return': candidate_return,
                        'cycle': self.optimization_cycle,
                        'timestamp': datetime.now()
                    })
                    
                    if iteration_count % print_interval == 0 or iteration_count == 1:
                        print(f"迭代 {iteration_count}: 发现更好方案! 收益率: {best_return:.4f} (+{improvement:.6f})")
            
            if not iteration_improved:
                no_improvement_count += 1
                
                # 定期打印进度
                if iteration_count % print_interval == 0:
                    print(f"迭代 {iteration_count}: 当前最佳: {best_return:.4f}, "
                          f"无改进: {no_improvement_count}/{convergence_patience}")
            
            # 检查收敛条件
            if no_improvement_count >= convergence_patience:
                print(f"\n迭代 {iteration_count}: 连续 {convergence_patience} 次迭代改进小于阈值，已收敛!")
                break
            
            # 安全检查：避免无限循环
            if iteration_count > 100000:
                print(f"\n迭代 {iteration_count}: 达到安全上限，停止优化")
                break
        
        # 应用最佳分配
        # 检查最佳分配是否与当前策略匹配
        current_strategy_names = set(self.strategies.keys())
        best_alloc_names = set(best_allocations.keys())
        
        if current_strategy_names != best_alloc_names:
            print(f"[WARNING] 最佳分配方案与当前策略不匹配，使用默认分配")
            # 使用平均分配
            num_strategies = len(self.strategies)
            default_alloc = 1.0 / num_strategies
            best_allocations = {name: default_alloc for name in self.strategies.keys()}
        
        self.allocations = best_allocations
        
        print(f"\n{'='*60}")
        print(f"优化完成!")
        print(f"{'='*60}")
        print(f"总迭代次数: {iteration_count}")
        print(f"总评估方案数: {iteration_count * parallel_workers}")
        print(f"最佳收益率: {best_return:.4f}")
        print(f"最佳分配: {best_allocations}")
        print(f"队列大小: {len(self.candidate_queue)}")
        
        # 打印队列中最好的几个方案
        if self.candidate_queue:
            print(f"\n队列Top 5方案:")
            top_candidates = sorted(self.candidate_queue, key=lambda x: x['return'], reverse=True)[:5]
            for i, cand in enumerate(top_candidates, 1):
                print(f"  {i}. 收益率: {cand['return']:.4f}, 分配: {cand['allocations']}")
        
        print(f"{'='*60}\n")
        
        # 更新策略资金
        for name in self.allocations:
            if name in self.strategies and hasattr(self.strategies[name], 'current_balance'):
                allocated_amount = self.current_balance * self.allocations[name]
                self.strategies[name].current_balance = allocated_amount
    
    def _generate_candidate(self) -> Dict[str, float]:
        """
        生成候选分配方案
        支持多策略组合（2个或更多）
        
        Returns:
            候选分配方案字典
        """
        candidate = {}
        strategy_names = list(self.allocations.keys())
        num_strategies = len(strategy_names)
        
        if num_strategies == 1:
            # 只有一个策略
            name = strategy_names[0]
            candidate[name] = 1.0
        elif num_strategies == 2:
            # 两个策略的情况
            if 'dca' in self.allocations and 'grid' in self.allocations:
                # DCA + Grid 策略组合
                if self.candidate_queue and np.random.random() < 0.7:
                    # 70%概率从历史队列选择并变异
                    try:
                        parent = self.candidate_queue[np.random.randint(0, min(5, len(self.candidate_queue)))]
                        # 检查父方案是否包含所需的策略
                        if 'dca' in parent['allocations'] and 'grid' in parent['allocations']:
                            dca_alloc = parent['allocations']['dca'] + np.random.normal(0, 0.05)
                            dca_alloc = np.clip(dca_alloc, 0.1, 0.9)
                        else:
                            # 策略不匹配，使用随机分配
                            dca_alloc = np.random.uniform(0.1, 0.9)
                    except (KeyError, IndexError):
                        # 历史队列不匹配，使用随机分配
                        dca_alloc = np.random.uniform(0.1, 0.9)
                else:
                    # 30%概率完全随机
                    dca_alloc = np.random.uniform(0.1, 0.9)
                
                grid_alloc = 1.0 - dca_alloc
                candidate['dca'] = dca_alloc
                candidate['grid'] = grid_alloc
            elif 'dca' in self.allocations and 'hft' in self.allocations:
                # DCA + HFT 策略组合
                if self.candidate_queue and np.random.random() < 0.7:
                    try:
                        parent = self.candidate_queue[np.random.randint(0, min(5, len(self.candidate_queue)))]
                        # 检查父方案是否包含所需的策略
                        if 'dca' in parent['allocations'] and 'hft' in parent['allocations']:
                            dca_alloc = parent['allocations']['dca'] + np.random.normal(0, 0.05)
                            dca_alloc = np.clip(dca_alloc, 0.3, 0.7)
                        else:
                            # 策略不匹配，使用随机分配
                            dca_alloc = np.random.uniform(0.3, 0.7)
                    except (KeyError, IndexError):
                        # 历史队列不匹配，使用随机分配
                        dca_alloc = np.random.uniform(0.3, 0.7)
                else:
                    dca_alloc = np.random.uniform(0.3, 0.7)
                
                hft_alloc = 1.0 - dca_alloc
                candidate['dca'] = dca_alloc
                candidate['hft'] = hft_alloc
            else:
                # 其他两个策略的组合
                if self.candidate_queue and np.random.random() < 0.7:
                    try:
                        # 从历史队列变异
                        parent = self.candidate_queue[np.random.randint(0, min(5, len(self.candidate_queue)))]
                        # 检查父方案是否与当前策略匹配
                        if set(parent['allocations'].keys()) == set(strategy_names):
                            for name in strategy_names:
                                alloc = parent['allocations'][name] + np.random.normal(0, 0.05)
                                alloc = np.clip(alloc, 0.1, 0.9)
                                candidate[name] = alloc
                        else:
                            # 策略不匹配，使用随机分配
                            alloc1 = np.random.uniform(0.1, 0.9)
                            candidate[strategy_names[0]] = alloc1
                            candidate[strategy_names[1]] = 1.0 - alloc1
                    except (KeyError, IndexError):
                        # 历史队列不匹配，使用随机分配
                        alloc1 = np.random.uniform(0.1, 0.9)
                        candidate[strategy_names[0]] = alloc1
                        candidate[strategy_names[1]] = 1.0 - alloc1
                else:
                    # 随机分配
                    alloc1 = np.random.uniform(0.1, 0.9)
                    candidate[strategy_names[0]] = alloc1
                    candidate[strategy_names[1]] = 1.0 - alloc1
        else:
            # 三个或更多策略的情况
            if self.candidate_queue and np.random.random() < 0.7:
                try:
                    # 从历史队列变异
                    parent = self.candidate_queue[np.random.randint(0, min(5, len(self.candidate_queue)))]
                    # 检查父方案是否与当前策略匹配
                    if set(parent['allocations'].keys()) == set(strategy_names):
                        for name in strategy_names:
                            alloc = parent['allocations'][name] + np.random.normal(0, 0.03)
                            alloc = np.clip(alloc, 0.05, 0.8)
                            candidate[name] = alloc
                    else:
                        # 策略不匹配，使用随机分配
                        weights = np.random.dirichlet(np.ones(num_strategies))
                        for i, name in enumerate(strategy_names):
                            candidate[name] = weights[i]
                except (KeyError, IndexError):
                    # 历史队列不匹配，使用随机分配
                    weights = np.random.dirichlet(np.ones(num_strategies))
                    for i, name in enumerate(strategy_names):
                        candidate[name] = weights[i]
            else:
                # 随机分配（Dirichlet分布）
                weights = np.random.dirichlet(np.ones(num_strategies))
                for i, name in enumerate(strategy_names):
                    candidate[name] = weights[i]
            
            # 归一化
            total = sum(candidate.values())
            for name in candidate:
                candidate[name] /= total
        
        return candidate
    
    def _evaluate_candidate(self, candidate: Dict[str, float], data: pd.Series) -> float:
        """
        评估候选方案
        
        Args:
            candidate: 候选分配方案
            data: 价格数据
            
        Returns:
            收益率
        """
        temp_balance = self.current_balance
        temp_strategies = {}
        
        # 复制策略
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'current_balance'):
                if name in ['grid', 'final_market_adaptive', 'ml_range_grid']:
                    # 对于需要base_price参数的策略
                    strategy_copy = type(strategy)(
                        base_price=data.iloc[0], 
                        initial_balance=temp_balance * candidate[name]
                    )
                else:
                    strategy_copy = type(strategy)(initial_balance=temp_balance * candidate[name])
                temp_strategies[name] = strategy_copy
        
        # 模拟交易过程
        for j, price in enumerate(data):
            current_data = data.iloc[:j+1] if j+1 >= 20 else data
            for name, strategy in temp_strategies.items():
                if hasattr(strategy, 'update_price'):
                    if name == 'grid':
                        strategy.update_price(price, data=current_data)
                    else:
                        strategy.update_price(price)
        
        # 计算模拟结果
        total_value = 0
        last_price = data.iloc[-1]
        for name, strategy in temp_strategies.items():
            if hasattr(strategy, 'get_performance'):
                import inspect
                sig = inspect.signature(strategy.get_performance)
                if len(sig.parameters) > 0:
                    perf = strategy.get_performance(last_price)
                else:
                    perf = strategy.get_performance()
                if 'total_value' in perf:
                    total_value += perf['total_value']
                else:
                    total_value += perf['current_balance']
        
        return (total_value - temp_balance) / temp_balance
    
    def _add_to_queue(self, candidate_info: Dict[str, Any]):
        """
        添加候选方案到队列
        
        Args:
            candidate_info: 候选方案信息
        """
        self.candidate_queue.append(candidate_info)
        
        # 按收益率排序
        self.candidate_queue.sort(key=lambda x: x['return'], reverse=True)
        
        # 保持队列大小
        if len(self.candidate_queue) > self.max_queue_size:
            self.candidate_queue = self.candidate_queue[:self.max_queue_size]
        
        # 保存队列
        self._save_queue()
    
    def _load_queue(self):
        """
        加载历史队列
        """
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'rb') as f:
                    self.candidate_queue = pickle.load(f)
                print(f"[INFO] 从 {self.queue_file} 加载了 {len(self.candidate_queue)} 个历史候选方案")
            except Exception as e:
                print(f"[WARNING] 加载队列失败: {str(e)}")
                self.candidate_queue = []
    
    def _save_queue(self):
        """
        保存队列到文件
        """
        try:
            with open(self.queue_file, 'wb') as f:
                pickle.dump(self.candidate_queue, f)
            # print(f"[INFO] 队列已保存到 {self.queue_file}")
        except Exception as e:
            print(f"[WARNING] 保存队列失败: {str(e)}")
    
    def update(self, current_price: float, current_date: Optional[pd.Timestamp] = None) -> Dict[str, any]:
        """
        更新所有策略
        
        Args:
            current_price: 当前价格
            current_date: 当前日期
            
        Returns:
            所有策略的交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 优化资金分配
        if len(self.price_history) > 50:
            price_series = pd.Series(self.price_history)
            self.optimize_allocations(price_series)
        
        results = {}
        total_balance = 0
        total_position_value = 0
        
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'invest') and current_date:
                result = strategy.invest(current_price, current_date)
            else:
                # 检查方法签名以确定参数
                import inspect
                sig = inspect.signature(strategy.update_price)
                if len(sig.parameters) > 1:
                    if name in ['grid', 'final_market_adaptive', 'ml_range_grid'] and hasattr(self, 'price_history'):
                        # 为网格策略传递价格数据
                        price_series = pd.Series(self.price_history)
                        result = strategy.update_price(current_price, price_series)
                    else:
                        # 为其他策略传递当前日期
                        result = strategy.update_price(current_price, current_date)
                else:
                    result = strategy.update_price(current_price)
            
            results[name] = result
            
            # 计算总资金
            if 'balance' in result:
                total_balance += result['balance']
            if 'position' in result and hasattr(strategy, 'get_performance'):
                if hasattr(strategy, 'get_performance') and callable(strategy.get_performance):
                    try:
                        # 检查方法签名以确定是否需要参数
                        sig = inspect.signature(strategy.get_performance)
                        if len(sig.parameters) > 0:
                            perf = strategy.get_performance(current_price)
                        else:
                            perf = strategy.get_performance()
                        if 'total_value' in perf:
                            # 只计算一次总价值
                            total_position_value += perf['total_value'] - perf['current_balance']
                    except:
                        pass
        
        # 计算总资金（现金余额 + 持仓价值）
        self.current_balance = total_balance
        
        # 记录性能历史
        if current_date:
            performance = self.get_performance(current_price)
            self.performance_history.append({
                'date': current_date,
                'total_value': performance['overall']['total_value'],
                'allocations': self.allocations.copy()
            })
        
        return results
    
    def get_performance(self, current_price: float) -> Dict[str, any]:
        """
        获取整体性能
        
        Args:
            current_price: 当前价格
            
        Returns:
            整体性能指标
        """
        performance = {}
        total_value = 0
        total_balance = 0
        total_position_value = 0
        
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'get_performance') and callable(strategy.get_performance):
                try:
                    # 检查方法签名以确定是否需要参数
                    import inspect
                    sig = inspect.signature(strategy.get_performance)
                    if len(sig.parameters) > 0:
                        perf = strategy.get_performance(current_price)
                    else:
                        perf = strategy.get_performance()
                    performance[name] = perf
                    if 'total_value' in perf:
                        total_value += perf['total_value']
                        total_balance += perf['current_balance']
                        total_position_value += perf['total_value'] - perf['current_balance']
                    else:
                        total_value += perf['current_balance']
                        total_balance += perf['current_balance']
                except:
                    pass
        
        performance['overall'] = {
            "initial_balance": self.initial_balance,
            "current_balance": total_balance,
            "total_position_value": total_position_value,
            "total_value": total_value,
            "pnl": total_value - self.initial_balance,
            "return": (total_value / self.initial_balance - 1) * 100,
            "current_allocations": self.allocations
        }
        
        return performance

class FundAllocator:
    """
    资金分配器
    """
    
    def __init__(self, initial_balance: float = 100000):
        """
        初始化资金分配器
        
        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.strategies = {}
        self.allocations = {}
    
    def add_strategy(self, name: str, strategy, allocation: float):
        """
        添加策略
        
        Args:
            name: 策略名称
            strategy: 策略实例
            allocation: 资金分配比例
        """
        self.strategies[name] = strategy
        self.allocations[name] = allocation
        
        # 分配资金
        allocated_amount = self.initial_balance * allocation
        if hasattr(strategy, 'current_balance'):
            strategy.current_balance = allocated_amount
    
    def update(self, current_price: float, current_date: Optional[pd.Timestamp] = None) -> Dict[str, any]:
        """
        更新所有策略
        
        Args:
            current_price: 当前价格
            current_date: 当前日期
            
        Returns:
            所有策略的交易结果
        """
        results = {}
        total_balance = 0
        
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'invest') and current_date:
                result = strategy.invest(current_price, current_date)
            else:
                result = strategy.update_price(current_price)
            
            results[name] = result
            
            # 计算总资金
            if 'balance' in result:
                total_balance += result['balance']
            if 'position' in result and hasattr(strategy, 'get_performance'):
                if hasattr(strategy, 'get_performance') and callable(strategy.get_performance):
                    try:
                        # 检查方法签名以确定是否需要参数
                        import inspect
                        sig = inspect.signature(strategy.get_performance)
                        if len(sig.parameters) > 0:
                            perf = strategy.get_performance(current_price)
                        else:
                            perf = strategy.get_performance()
                        if 'total_value' in perf:
                            total_balance += perf['total_value'] - perf['current_balance']
                    except:
                        pass
        
        self.current_balance = total_balance
        return results
    
    def get_performance(self, current_price: float) -> Dict[str, any]:
        """
        获取整体性能
        
        Args:
            current_price: 当前价格
            
        Returns:
            整体性能指标
        """
        performance = {}
        total_value = 0
        
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'get_performance') and callable(strategy.get_performance):
                try:
                    perf = strategy.get_performance(current_price)
                    performance[name] = perf
                    if 'total_value' in perf:
                        total_value += perf['total_value']
                    else:
                        total_value += perf['current_balance']
                except:
                    pass
        
        performance['overall'] = {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "total_value": total_value,
            "pnl": total_value - self.initial_balance,
            "return": (total_value / self.initial_balance - 1) * 100
        }
        
        return performance
