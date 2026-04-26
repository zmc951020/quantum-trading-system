#!/usr/bin/env python3
"""
最大参数测试 - 全面测试机器学习优化迭代和所有交易策略
"""

import os
import sys
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.test_system import TestConfig, SystemTester, SimpleMonitor, SimpleEvaluator, SimpleReportGenerator

# 尝试导入模块
MODULES = {}
try:
    from strategies.grid_trading import GridTrading, MonteCarloSimulation, MLGridTrading
    MODULES['GridTrading'] = GridTrading
    MODULES['MLGridTrading'] = MLGridTrading
except ImportError as e:
    print(f"警告: 导入网格化交易策略失败: {str(e)}")

try:
    from strategies.trend_trading import MovingAveragesStrategy, RSIStrategy, TrendSwitchingStrategy
    MODULES['MovingAveragesStrategy'] = MovingAveragesStrategy
    MODULES['RSIStrategy'] = RSIStrategy
    MODULES['TrendSwitchingStrategy'] = TrendSwitchingStrategy
except ImportError as e:
    print(f"警告: 导入趋势交易策略失败: {str(e)}")

try:
    from strategies.fund_allocation import DCAStrategy, HFTStrategy, FundAllocator, MLFundAllocator
    MODULES['DCAStrategy'] = DCAStrategy
    MODULES['HFTStrategy'] = HFTStrategy
    MODULES['FundAllocator'] = FundAllocator
    MODULES['MLFundAllocator'] = MLFundAllocator
except ImportError as e:
    print(f"警告: 导入资金配置策略失败: {str(e)}")

try:
    from strategies.multi_factor_resonance import MultiFactorResonanceStrategy
    MODULES['MultiFactorResonanceStrategy'] = MultiFactorResonanceStrategy
except ImportError as e:
    print(f"警告: 导入多因子共振策略失败: {str(e)}")

try:
    from ml.dynamic_grid import MLBasedGridTrading
    from ml.trend_prediction import AdaptiveTradingStrategy
    MODULES['MLBasedGridTrading'] = MLBasedGridTrading
    MODULES['AdaptiveTradingStrategy'] = AdaptiveTradingStrategy
except ImportError as e:
    print(f"警告: 导入机器学习模块失败: {str(e)}")

try:
    from models.arma import ARMA_Model
    MODULES['ARMA_Model'] = ARMA_Model
except ImportError:
    print("警告: 缺少statsmodels库，ARMA模型测试将被跳过")

try:
    from models.sarima import SARIMA_Model
    MODULES['SARIMA_Model'] = SARIMA_Model
except ImportError:
    print("警告: 缺少statsmodels库，SARIMA模型测试将被跳过")

try:
    from models.lstm import LSTM_Model
    MODULES['LSTM_Model'] = LSTM_Model
except ImportError:
    print("警告: 缺少tensorflow库，LSTM模型测试将被跳过")

class ParameterTester:
    """参数测试器"""
    
    def __init__(self):
        self.results = []
        self.test_count = 0
    
    def test_configuration(self, config: TestConfig, test_name: str) -> Dict[str, Any]:
        """测试单个配置"""
        print(f"\n{'='*70}")
        print(f"测试: {test_name}")
        print(f"{'='*70}")
        
        start_time = time.time()
        
        try:
            # 创建测试器
            tester = SystemTester(config)
            
            # 生成测试数据
            data = tester.generate_test_data()
            print(f"\n数据: {len(data)} 条, 频率: {config.DATA_FREQUENCY}")
            print(f"时间: {data.index[0]} 至 {data.index[-1]}")
            
            # 测试各个策略
            strategy_results = self._test_all_strategies(data, config)
            
            # 测试机器学习优化
            ml_results = self._test_ml_optimization(data, config)
            
            end_time = time.time()
            duration = end_time - start_time
            
            result = {
                'test_name': test_name,
                'status': 'success',
                'duration': duration,
                'data_length': len(data),
                'data_frequency': config.DATA_FREQUENCY,
                'strategy_results': strategy_results,
                'ml_results': ml_results
            }
            
            print(f"\n✅ 测试完成! 耗时: {duration:.2f}秒")
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            result = {
                'test_name': test_name,
                'status': 'error',
                'duration': duration,
                'error': str(e)
            }
            print(f"\n❌ 测试失败: {str(e)}")
        
        self.results.append(result)
        self.test_count += 1
        return result
    
    def _test_all_strategies(self, data: pd.Series, config: TestConfig) -> Dict[str, Any]:
        """测试所有策略"""
        results = {}
        print(f"\n【测试交易策略】")
        
        # 测试网格交易策略
        if 'GridTrading' in MODULES:
            try:
                grid = MODULES['GridTrading'](
                    base_price=data.iloc[0], 
                    grid_spacing=config.GRID_SPACING
                )
                for i, price in enumerate(data):
                    current_data = data.iloc[:i+1] if i+1 >= 20 else data
                    grid.update_price(price, data=current_data)
                perf = grid.get_performance()
                results['grid_trading'] = perf
                print(f"  [OK] 网格交易: {perf.get('return', 0):.2f}%")
            except Exception as e:
                results['grid_trading'] = {'error': str(e)}
                print(f"  [FAIL] 网格交易: {str(e)[:50]}...")
        
        # 测试趋势交易策略
        if 'TrendSwitchingStrategy' in MODULES:
            try:
                trend = MODULES['TrendSwitchingStrategy']()
                recommended = trend.switch_strategy(data)
                results['trend_trading'] = {'recommended_strategy': recommended}
                print(f"  [OK] 趋势交易: 推荐策略={recommended}")
            except Exception as e:
                results['trend_trading'] = {'error': str(e)}
                print(f"  [FAIL] 趋势交易: {str(e)[:50]}...")
        
        # 测试DCA策略
        if 'DCAStrategy' in MODULES:
            try:
                dca = MODULES['DCAStrategy'](initial_balance=config.INITIAL_BALANCE)
                for i, price in enumerate(data):
                    timestamp = data.index[i]
                    dca.invest(price, timestamp)
                perf = dca.get_performance(data.iloc[-1])
                results['dca_strategy'] = perf
                print(f"  [OK] DCA策略: {perf.get('return', 0):.2f}%")
            except Exception as e:
                results['dca_strategy'] = {'error': str(e)}
                print(f"  [FAIL] DCA策略: {str(e)[:50]}...")
        
        # 测试多因子共振策略
        if 'MultiFactorResonanceStrategy' in MODULES:
            try:
                multi_factor = MODULES['MultiFactorResonanceStrategy'](
                    initial_balance=config.INITIAL_BALANCE
                )
                for i, price in enumerate(data):
                    current_data = data.iloc[:i+1] if i+1 >= 120 else data
                    multi_factor.update_price(price, data=current_data)
                perf = multi_factor.get_performance(data.iloc[-1])
                results['multi_factor'] = perf
                print(f"  [OK] 多因子共振: {perf.get('return', 0):.2f}%")
            except Exception as e:
                results['multi_factor'] = {'error': str(e)}
                print(f"  [FAIL] 多因子共振: {str(e)[:50]}...")
        
        return results
    
    def _test_ml_optimization(self, data: pd.Series, config: TestConfig) -> Dict[str, Any]:
        """测试机器学习优化"""
        results = {}
        print(f"\n【测试机器学习优化】")
        print(f"  迭代次数: {config.ML_OPTIMIZATION_ITERATIONS}")
        
        if 'MLFundAllocator' in MODULES and 'DCAStrategy' in MODULES and 'GridTrading' in MODULES:
            try:
                ml_allocator = MODULES['MLFundAllocator'](initial_balance=config.INITIAL_BALANCE)
                dca = MODULES['DCAStrategy']()
                grid = MODULES['GridTrading'](
                    base_price=data.iloc[0], 
                    grid_spacing=config.GRID_SPACING
                )
                
                ml_allocator.add_strategy("dca", dca, config.DEFAULT_ALLOCATION)
                ml_allocator.add_strategy("grid", grid, config.DEFAULT_ALLOCATION)
                
                # 执行机器学习优化
                start_ml = time.time()
                ml_allocator.optimize_with_machine_learning(
                    data, 
                    iterations=config.ML_OPTIMIZATION_ITERATIONS,
                    print_interval=config.ML_PRINT_INTERVAL
                )
                ml_duration = time.time() - start_ml
                
                # 运行策略
                for i, price in enumerate(data):
                    timestamp = data.index[i]
                    ml_allocator.update(price, timestamp)
                
                perf = ml_allocator.get_performance(data.iloc[-1])
                results = {
                    'status': 'success',
                    'duration': ml_duration,
                    'performance': perf,
                    'best_allocations': perf['overall']['current_allocations']
                }
                print(f"  [OK] ML优化: {perf['overall']['return']:.2f}%, 耗时: {ml_duration:.2f}秒")
                print(f"       最佳分配: {perf['overall']['current_allocations']}")
                
            except Exception as e:
                results = {'status': 'error', 'error': str(e)}
                print(f"  [FAIL] ML优化: {str(e)[:50]}...")
        else:
            print(f"  [SKIP] ML模块不可用")
        
        return results
    
    def print_summary(self):
        """打印测试摘要"""
        print(f"\n{'='*70}")
        print(f"最大参数测试摘要")
        print(f"{'='*70}")
        print(f"总测试数: {self.test_count}")
        
        success_count = sum(1 for r in self.results if r['status'] == 'success')
        print(f"成功: {success_count}/{self.test_count}")
        
        for result in self.results:
            print(f"\n  • {result['test_name']}:")
            print(f"    状态: {'✅ 成功' if result['status'] == 'success' else '❌ 失败'}")
            print(f"    耗时: {result.get('duration', 0):.2f}秒")
            
            if result['status'] == 'success':
                ml_res = result.get('ml_results', {})
                if ml_res.get('status') == 'success':
                    perf = ml_res.get('performance', {}).get('overall', {})
                    print(f"    ML优化收益率: {perf.get('return', 0):.2f}%")
        
        print(f"\n{'='*70}")

def main():
    """主函数"""
    print("="*70)
    print("最大参数测试 - 机器学习优化迭代和所有交易策略")
    print("="*70)
    
    # 创建参数测试器
    tester = ParameterTester()
    
    # 测试配置1：基础配置
    print(f"\n\n【测试1/4】基础配置")
    config1 = TestConfig()
    config1.DATA_LENGTH = 500
    config1.ML_OPTIMIZATION_ITERATIONS = 1000
    config1.ML_PRINT_INTERVAL = 200
    tester.test_configuration(config1, "基础配置 (500数据, 1000迭代)")
    
    # 测试配置2：分钟级数据
    print(f"\n\n【测试2/4】分钟级数据")
    config2 = TestConfig()
    config2.DATA_FREQUENCY = 'T'
    config2.DATA_LENGTH = 500  # 约8小时的分钟数据
    config2.ML_OPTIMIZATION_ITERATIONS = 2000
    config2.ML_PRINT_INTERVAL = 400
    tester.test_configuration(config2, "分钟级数据 (500数据, 2000迭代)")
    
    # 测试配置3：高迭代次数
    print(f"\n\n【测试3/4】高迭代次数")
    config3 = TestConfig()
    config3.DATA_LENGTH = 300
    config3.ML_OPTIMIZATION_ITERATIONS = 5000
    config3.ML_PRINT_INTERVAL = 500
    tester.test_configuration(config3, "高迭代次数 (300数据, 5000迭代)")
    
    # 测试配置4：最大配置（适度的最大值）
    print(f"\n\n【测试4/4】最大配置")
    config4 = TestConfig()
    config4.DATA_LENGTH = 1000
    config4.ML_OPTIMIZATION_ITERATIONS = 10000
    config4.ML_PRINT_INTERVAL = 1000
    tester.test_configuration(config4, "最大配置 (1000数据, 10000迭代)")
    
    # 打印摘要
    tester.print_summary()
    
    print("\n" + "="*70)
    print("所有最大参数测试完成！")
    print("="*70)

if __name__ == "__main__":
    # 创建报告目录
    os.makedirs("reports", exist_ok=True)
    main()
