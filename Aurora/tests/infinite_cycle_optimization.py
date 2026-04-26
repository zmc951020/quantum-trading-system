#!/usr/bin/env python3
"""
无限周期循环测试 - 循环次数不限，持续优化
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import signal

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 尝试导入模块
MODULES = {}
try:
    from strategies.grid_trading import GridTrading
    MODULES['GridTrading'] = GridTrading
except ImportError as e:
    print(f"警告: 导入网格化交易策略失败: {str(e)}")

try:
    from strategies.fund_allocation import DCAStrategy, MLFundAllocator
    MODULES['DCAStrategy'] = DCAStrategy
    MODULES['MLFundAllocator'] = MLFundAllocator
except ImportError as e:
    print(f"警告: 导入资金配置策略失败: {str(e)}")

class InfiniteOptimizer:
    """
    无限周期优化器
    """
    
    def __init__(self, initial_balance: float = 100000):
        """
        初始化无限优化器
        
        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.ml_allocator = None
        self.current_price = 100.0
        self.cycle_count = 0
        self.total_time = 0
        self.best_returns = []
        self.best_allocations = []
        self.running = True
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signal, frame):
        """
        信号处理函数
        """
        print("\n" + "="*70)
        print("收到停止信号，正在停止...")
        print("="*70)
        self.running = False
    
    def generate_market_data(self, length: int = 300, start_price: float = 100, volatility: float = 0.01):
        """
        生成市场数据
        
        Args:
            length: 数据长度
            start_price: 起始价格
            volatility: 波动率
            
        Returns:
            价格序列
        """
        dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
        returns = np.random.normal(0, volatility, length)
        prices = start_price * (1 + returns).cumprod()
        return pd.Series(prices, index=dates)
    
    def initialize(self):
        """
        初始化优化器
        """
        print("="*70)
        print("无限周期循环优化器")
        print("="*70)
        
        # 检查必要模块
        required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
        for mod in required_modules:
            if mod not in MODULES:
                print(f"\n[FAIL] 缺少必要模块: {mod}")
                return False
        
        # 创建ML资金分配器
        print("\n初始化ML资金分配器...")
        self.ml_allocator = MODULES['MLFundAllocator'](initial_balance=self.initial_balance)
        
        # 添加策略
        dca = MODULES['DCAStrategy']()
        grid = MODULES['GridTrading'](base_price=self.current_price, grid_spacing=0.01)
        
        self.ml_allocator.add_strategy("dca", dca, 0.5)
        self.ml_allocator.add_strategy("grid", grid, 0.5)
        
        print("[OK] 策略已添加")
        print("[INFO] 按 Ctrl+C 停止优化")
        return True
    
    def run(self):
        """
        运行无限循环
        """
        if not self.initialize():
            return
        
        # 优化配置
        config = {
            'max_queue_size': 100,
            'convergence_threshold': 0.00001,
            'convergence_patience': 200,
            'print_interval': 100
        }
        
        print("\n" + "="*70)
        print("开始无限周期循环")
        print("="*70)
        print(f"循环次数: 不限")
        print(f"智能收敛: 自动停止")
        print(f"队列继承: 持续优化")
        print(f"按 Ctrl+C 停止")
        print("="*70)
        
        while self.running:
            self.cycle_count += 1
            
            print(f"\n" + "="*70)
            print(f"周期 {self.cycle_count}")
            print(f"="*70)
            
            # 生成新的市场数据
            cycle_data = self.generate_market_data(length=300, start_price=self.current_price)
            self.current_price = cycle_data.iloc[-1]
            
            print(f"  数据点: {len(cycle_data)}")
            print(f"  价格范围: {cycle_data.min():.2f} - {cycle_data.max():.2f}")
            print(f"  价格变化: {((cycle_data.iloc[-1] - cycle_data.iloc[0]) / cycle_data.iloc[0] * 100):.2f}%")
            
            # 运行优化
            start_time = datetime.now()
            self.ml_allocator.optimize_with_machine_learning(cycle_data, **config)
            cycle_time = (datetime.now() - start_time).total_seconds()
            self.total_time += cycle_time
            
            # 运行策略
            for i, price in enumerate(cycle_data):
                timestamp = cycle_data.index[i]
                self.ml_allocator.update(price, timestamp)
            
            # 获取性能
            perf = self.ml_allocator.get_performance(cycle_data.iloc[-1])
            current_return = perf['overall']['return']
            self.best_returns.append(current_return)
            self.best_allocations.append(perf['overall']['current_allocations'])
            
            print(f"  周期耗时: {cycle_time:.2f}秒")
            print(f"  队列大小: {len(self.ml_allocator.candidate_queue)}")
            print(f"  当前收益率: {current_return:.2f}%")
            print(f"  最佳分配: {perf['overall']['current_allocations']}")
            
            # 打印队列中的最佳方案
            if self.ml_allocator.candidate_queue:
                top_candidate = sorted(self.ml_allocator.candidate_queue, key=lambda x: x['return'], reverse=True)[0]
                print(f"  队列最佳收益率: {top_candidate['return']:.4f}")
            
            # 打印统计信息
            if self.cycle_count % 5 == 0:
                self._print_statistics()
        
        # 打印最终统计
        self._print_statistics()
        
    def _print_statistics(self):
        """
        打印统计信息
        """
        print("\n" + "="*70)
        print("统计信息")
        print("="*70)
        print(f"总周期数: {self.cycle_count}")
        print(f"总耗时: {self.total_time:.2f}秒")
        print(f"平均周期耗时: {self.total_time / self.cycle_count:.2f}秒")
        
        if self.best_returns:
            print(f"最高收益率: {max(self.best_returns):.2f}%")
            print(f"最低收益率: {min(self.best_returns):.2f}%")
            print(f"平均收益率: {sum(self.best_returns) / len(self.best_returns):.2f}%")
            print(f"当前收益率: {self.best_returns[-1]:.2f}%")
        
        if self.ml_allocator.candidate_queue:
            print(f"队列大小: {len(self.ml_allocator.candidate_queue)}")
            top_candidate = sorted(self.ml_allocator.candidate_queue, key=lambda x: x['return'], reverse=True)[0]
            print(f"队列最佳方案: {top_candidate['allocations']}")
            print(f"队列最佳收益率: {top_candidate['return']:.4f}")
        
        print("="*70)
        print("继续运行... 按 Ctrl+C 停止")
        print("="*70)

def main():
    """
    主函数
    """
    optimizer = InfiniteOptimizer()
    optimizer.run()

if __name__ == "__main__":
    main()
