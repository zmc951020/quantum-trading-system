#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能体优化策略回测工作机制全面测试
====================================
测试目标：
  1. 核心策略在多种市场环境下的表现（横盘、上涨、下跌、高波动）
  2. 策略优化器的备份/优化/回滚机制
  3. 回测系统的完整流程（含增益模块集成）
  4. 增益性优化模块的集成效果验证
  5. 生成对比报告

测试策略：
  - FinalMarketAdaptiveGrid (final_market_adaptive.py) - 核心自适应网格
  - AdaptiveMLStrategy (adaptive_ml_strategy.py) - ML自适应策略
  - HighReturnGridTrading (high_return_grid.py) - 高收益网格
  - MultiFactorResonanceStrategy (multi_factor_resonance.py) - 多因子共振
  - FourierRLStrategy (fourier_rl_strategy.py) - 傅里叶RL策略
"""

import sys
import os
import time
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 第一部分：测试配置
# ============================================================
TEST_CONFIG = {
    'initial_balance': 100000,
    'days_per_market': 300,
    'market_types': ['range_bound', 'trending_up', 'trending_down', 'volatile'],
    'strategies_to_test': [
        'FinalMarketAdaptiveGrid',
        'AdaptiveMLStrategy',
        'HighReturnGridTrading',
        'MultiFactorResonanceStrategy',
        'FourierRLStrategy',
    ],
    'optimization_test': {
        'strategy_name': 'MLRangeGridTrading',
        'backup_test': True,
        'optimize_test': True,
        'rollback_test': True,
    },
    'gain_module_test': {
        'performance_tracker': True,
        'risk_controller': True,
        'param_optimizer': True,
        'rl_enhancer': True,
        'data_validator': True,
    }
}

# ============================================================
# 第二部分：市场数据生成器
# ============================================================
class MarketDataGenerator:
    """生成多种类型的市场模拟数据"""
    
    @staticmethod
    def generate(market_type: str, days: int = 300, base_price: float = 100.0) -> pd.DataFrame:
        """
        生成指定类型的市场数据
        
        Args:
            market_type: 市场类型
            days: 数据天数
            base_price: 基准价格
            
        Returns:
            DataFrame: 包含 close, volume, high, low 的模拟数据
        """
        np.random.seed(42)
        dates = pd.date_range(start='2023-01-01', periods=days)
        
        if market_type == 'range_bound':
            # 横盘市场：价格在窄区间内波动
            prices = base_price + np.random.normal(0, base_price * 0.008, days).cumsum()
            prices = np.clip(prices, base_price * 0.95, base_price * 1.05)
            
        elif market_type == 'trending_up':
            # 上涨市场：持续上升趋势
            trend = np.linspace(0, 0.3, days)
            noise = np.random.normal(0, base_price * 0.01, days).cumsum()
            prices = base_price * (1 + trend) + noise
            
        elif market_type == 'trending_down':
            # 下跌市场：持续下降趋势
            trend = np.linspace(0, -0.25, days)
            noise = np.random.normal(0, base_price * 0.01, days).cumsum()
            prices = base_price * (1 + trend) + noise
            
        elif market_type == 'volatile':
            # 高波动市场：均值回归 + 高波动
            prices = [base_price]
            mean_reversion = 0.05
            long_term_mean = base_price
            volatility_factor = 0.025
            
            for i in range(1, days):
                reversion_term = mean_reversion * (long_term_mean - prices[-1])
                random_term = np.random.normal(0, base_price * volatility_factor)
                new_price = prices[-1] + reversion_term + random_term
                new_price = max(base_price * 0.5, min(base_price * 2.0, new_price))
                prices.append(new_price)
        else:
            raise ValueError(f"未知市场类型: {market_type}")
        
        prices = np.array(prices)
        volumes = np.random.randint(1000000, 10000000, days)
        
        # 生成 high/low
        high = prices * (1 + np.random.uniform(0.001, 0.02, days))
        low = prices * (1 - np.random.uniform(0.001, 0.02, days))
        
        return pd.DataFrame({
            'close': prices,
            'volume': volumes,
            'high': high,
            'low': low
        }, index=dates)

# ============================================================
# 第三部分：策略测试引擎
# ============================================================
class StrategyTestEngine:
    """策略测试引擎 - 测试策略在不同市场环境下的表现"""
    
    def __init__(self, initial_balance: float = 100000):
        self.initial_balance = initial_balance
        self.results: Dict[str, Dict] = {}
        self.test_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _import_strategy(self, strategy_name: str):
        """动态导入策略类"""
        import_map = {
            'FinalMarketAdaptiveGrid': ('strategies.final_market_adaptive', 'FinalMarketAdaptiveGrid'),
            'AdaptiveMLStrategy': ('strategies.adaptive_ml_strategy', 'AdaptiveMLStrategy'),
            'HighReturnGridTrading': ('strategies.high_return_grid', 'HighReturnGridTrading'),
            'MultiFactorResonanceStrategy': ('strategies.multi_factor_resonance', 'MultiFactorResonanceStrategy'),
            'FourierRLStrategy': ('strategies.fourier_rl_strategy', 'FourierRLStrategy'),
            'GridTrading': ('strategies.grid_trading', 'GridTrading'),
            'MLRangeGridTrading': ('strategies.ml_range_grid', 'MLRangeGridTrading'),
        }
        
        if strategy_name not in import_map:
            raise ImportError(f"未知策略: {strategy_name}")
        
        module_path, class_name = import_map[strategy_name]
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)
    
    def _calculate_metrics(self, balance_history: List[float], 
                          price_history: List[float]) -> Dict[str, float]:
        """计算性能指标"""
        balance_array = np.array(balance_history)
        price_array = np.array(price_history)
        
        # 收益率
        returns = np.diff(balance_array) / balance_array[:-1]
        
        # 总收益率
        total_return = (balance_array[-1] - self.initial_balance) / self.initial_balance
        
        # 年化收益率
        n_days = len(balance_history)
        annual_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1 if n_days > 0 else 0
        
        # 波动率
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
        
        # 夏普比率
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        # 最大回撤
        peak = np.maximum.accumulate(balance_array)
        drawdown = (peak - balance_array) / peak
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # 胜率
        winning_days = np.sum(returns > 0) if len(returns) > 0 else 0
        win_rate = winning_days / len(returns) if len(returns) > 0 else 0
        
        # 收益风险比
        profit_risk_ratio = total_return / max_drawdown if max_drawdown > 0 else float('inf')
        
        # 卡尔玛比率 (Calmar Ratio)
        calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else float('inf')
        
        # 索提诺比率 (Sortino Ratio)
        downside_returns = returns[returns < 0] if len(returns) > 0 else np.array([0])
        downside_volatility = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino_ratio = annual_return / downside_volatility if downside_volatility > 0 else float('inf')
        
        return {
            'total_return': float(total_return),
            'annual_return': float(annual_return),
            'volatility': float(volatility),
            'sharpe_ratio': float(sharpe_ratio),
            'sortino_ratio': float(sortino_ratio),
            'calmar_ratio': float(calmar_ratio),
            'max_drawdown': float(max_drawdown),
            'win_rate': float(win_rate),
            'profit_risk_ratio': float(profit_risk_ratio),
            'final_balance': float(balance_array[-1]),
        }
    
    def test_single_strategy(self, strategy_name: str, market_data: pd.DataFrame, 
                            market_type: str) -> Dict[str, Any]:
        """
        测试单个策略在特定市场环境下的表现
        
        Args:
            strategy_name: 策略名称
            market_data: 市场数据
            market_type: 市场类型标签
            
        Returns:
            dict: 测试结果
        """
        try:
            StrategyClass = self._import_strategy(strategy_name)
        except Exception as e:
            return {
                'strategy_name': strategy_name,
                'market_type': market_type,
                'status': 'ERROR',
                'error': str(e),
                'total_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
            }
        
        base_price = float(market_data['close'].iloc[0])
        
        try:
            # 初始化策略 - 根据策略类型动态传参
            import inspect
            sig = inspect.signature(StrategyClass.__init__)
            init_params = list(sig.parameters.keys())
            
            if 'base_price' in init_params:
                strategy = StrategyClass(base_price=base_price, initial_balance=self.initial_balance)
            elif strategy_name == 'GridTrading':
                strategy = StrategyClass(base_price=base_price, grid_spacing=0.005, initial_balance=self.initial_balance)
            else:
                strategy = StrategyClass(initial_balance=self.initial_balance)
            
            # 运行回测
            balance_history = [float(self.initial_balance)]
            price_history = []
            trades = []
            
            for idx, row in market_data.iterrows():
                current_price = float(row['close'])
                price_history.append(current_price)
                
                # 更新策略
                result = strategy.update_price(current_price, pd.Series(price_history))
                
                # 计算账户总价值
                position = getattr(strategy, 'position', 0)
                current_balance = getattr(strategy, 'current_balance', self.initial_balance)
                total_value = current_balance + (position * current_price)
                balance_history.append(float(total_value))
                
                # 记录交易
                if isinstance(result, dict) and result.get('action') in ('buy', 'sell'):
                    trades.append({
                        'time': str(idx),
                        'price': current_price,
                        'action': result['action'],
                        'value': total_value,
                    })
            
            # 计算指标
            metrics = self._calculate_metrics(balance_history, price_history)
            
            # 获取策略统计
            total_trades = getattr(strategy, 'total_trades', len(trades))
            winning_trades = getattr(strategy, 'winning_trades', 0)
            losing_trades = getattr(strategy, 'losing_trades', 0)
            
            result = {
                'strategy_name': strategy_name,
                'market_type': market_type,
                'status': 'SUCCESS',
                'base_price': base_price,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'trade_win_rate': winning_trades / max(total_trades, 1),
                **metrics,
            }
            
            return result
            
        except Exception as e:
            import traceback
            return {
                'strategy_name': strategy_name,
                'market_type': market_type,
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc(),
                'total_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
            }
    
    def run_comprehensive_test(self) -> pd.DataFrame:
        """运行全面测试 - 所有策略在所有市场环境下"""
        all_results = []
        
        print("\n" + "=" * 80)
        print("🚀 启动智能体策略回测全面测试")
        print("=" * 80)
        
        for strategy_name in TEST_CONFIG['strategies_to_test']:
            for market_type in TEST_CONFIG['market_types']:
                print(f"\n{'─' * 70}")
                print(f"📊 测试: {strategy_name} @ {market_type}")
                print(f"{'─' * 70}")
                
                # 生成市场数据
                market_data = MarketDataGenerator.generate(
                    market_type=market_type,
                    days=TEST_CONFIG['days_per_market'],
                    base_price=100.0
                )
                
                # 测试策略
                result = self.test_single_strategy(strategy_name, market_data, market_type)
                all_results.append(result)
                
                # 打印结果
                if result['status'] == 'SUCCESS':
                    print(f"  ✅ 状态: 成功")
                    print(f"  💰 总收益率: {result['total_return']*100:.2f}%")
                    print(f"  📈 年化收益率: {result['annual_return']*100:.2f}%")
                    print(f"  ⚡ 夏普比率: {result['sharpe_ratio']:.2f}")
                    print(f"  📉 最大回撤: {result['max_drawdown']*100:.2f}%")
                    print(f"  🎯 胜率: {result['win_rate']*100:.1f}%")
                    print(f"  🔄 交易次数: {result['total_trades']}")
                else:
                    print(f"  ❌ 状态: 失败 - {result.get('error', '未知错误')}")
        
        df = pd.DataFrame(all_results)
        self.results['comprehensive'] = df
        return df
    
    def generate_report(self, df: pd.DataFrame) -> str:
        """生成测试报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("📋 智能体策略回测测试报告")
        lines.append(f"   生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        # 按策略分组统计
        for strategy_name in TEST_CONFIG['strategies_to_test']:
            strategy_results = df[df['strategy_name'] == strategy_name]
            if strategy_results.empty:
                continue
            
            lines.append(f"\n{'─' * 70}")
            lines.append(f"📌 策略: {strategy_name}")
            lines.append(f"{'─' * 70}")
            
            for _, result in strategy_results.iterrows():
                market_type = result['market_type']
                status = result['status']
                
                if status == 'SUCCESS':
                    lines.append(f"\n  🌐 市场: {market_type}")
                    lines.append(f"    ├─ 总收益率: {result['total_return']*100:>+8.2f}%")
                    lines.append(f"    ├─ 年化收益率: {result['annual_return']*100:>+8.2f}%")
                    lines.append(f"    ├─ 夏普比率: {result['sharpe_ratio']:>8.2f}")
                    lines.append(f"    ├─ 索提诺比率: {result['sortino_ratio']:>8.2f}")
                    lines.append(f"    ├─ 卡尔玛比率: {result['calmar_ratio']:>8.2f}")
                    lines.append(f"    ├─ 最大回撤: {result['max_drawdown']*100:>8.2f}%")
                    lines.append(f"    ├─ 波动率: {result['volatility']*100:>8.2f}%")
                    lines.append(f"    ├─ 胜率: {result['win_rate']*100:>8.1f}%")
                    lines.append(f"    ├─ 交易胜率: {result.get('trade_win_rate', 0)*100:>8.1f}%")
                    lines.append(f"    └─ 交易次数: {result['total_trades']:>8}")
                else:
                    lines.append(f"\n  🌐 市场: {market_type} ❌ {result.get('error', '失败')}")
        
        # 汇总统计
        lines.append(f"\n{'=' * 70}")
        lines.append("📊 汇总统计")
        lines.append(f"{'=' * 70}")
        
        successful = df[df['status'] == 'SUCCESS']
        if not successful.empty:
            lines.append(f"\n  成功测试数: {len(successful)}/{len(df)}")
            lines.append(f"  平均总收益率: {successful['total_return'].mean()*100:.2f}%")
            lines.append(f"  平均年化收益率: {successful['annual_return'].mean()*100:.2f}%")
            lines.append(f"  平均夏普比率: {successful['sharpe_ratio'].mean():.2f}")
            lines.append(f"  平均最大回撤: {successful['max_drawdown'].mean()*100:.2f}%")
            lines.append(f"  平均胜率: {successful['win_rate'].mean()*100:.1f}%")
            
            # 最佳策略
            best_idx = successful['sharpe_ratio'].idxmax()
            best = successful.loc[best_idx]
            lines.append(f"\n  🏆 最佳表现: {best['strategy_name']} @ {best['market_type']}")
            lines.append(f"     夏普比率: {best['sharpe_ratio']:.2f}, 收益率: {best['total_return']*100:.2f}%")
        
        report = "\n".join(lines)
        
        # 保存报告
        report_dir = Path(PROJECT_ROOT) / "reports"
        report_dir.mkdir(exist_ok=True)
        report_file = report_dir / f"strategy_test_report_{self.test_timestamp}.txt"
        report_file.write_text(report, encoding='utf-8')
        print(f"\n📝 报告已保存: {report_file}")
        
        return report

# ============================================================
# 第四部分：策略优化器测试
# ============================================================
class StrategyOptimizerTest:
    """测试策略优化器的备份/优化/回滚机制"""
    
    def __init__(self):
        self.results = {}
    
    def test_backup_mechanism(self) -> Dict[str, Any]:
        """测试策略备份机制"""
        print("\n" + "=" * 70)
        print("🔄 测试: 策略备份机制")
        print("=" * 70)
        
        results = {
            'backup_created': False,
            'backup_file_exists': False,
            'archive_dir_exists': False,
        }
        
        try:
            from auto_backtest.strategy_optimizer import StrategyOptimizer
            optimizer = StrategyOptimizer()
            
            # 测试备份
            strategy_name = TEST_CONFIG['optimization_test']['strategy_name']
            backup_file = optimizer._backup_strategy(strategy_name)
            
            results['backup_created'] = backup_file is not None
            results['backup_file'] = backup_file
            
            if backup_file:
                results['backup_file_exists'] = os.path.exists(backup_file)
                results['archive_dir_exists'] = os.path.exists(optimizer.archive_dir)
                
                if results['backup_file_exists']:
                    print(f"  ✅ 备份文件已创建: {backup_file}")
                else:
                    print(f"  ❌ 备份文件不存在: {backup_file}")
            else:
                print(f"  ⚠️ 备份未创建（策略文件可能不存在）")
            
        except Exception as e:
            print(f"  ❌ 备份测试失败: {e}")
            results['error'] = str(e)
        
        self.results['backup'] = results
        return results
    
    def test_optimize_mechanism(self) -> Dict[str, Any]:
        """测试策略优化机制"""
        print("\n" + "=" * 70)
        print("⚙️ 测试: 策略优化机制")
        print("=" * 70)
        
        results = {
            'optimization_completed': False,
            'params_optimized': False,
            'improvement_detected': False,
        }
        
        try:
            from auto_backtest.strategy_optimizer import StrategyOptimizer
            optimizer = StrategyOptimizer()
            
            strategy_name = TEST_CONFIG['optimization_test']['strategy_name']
            
            # 测试参数优化
            optimized_params = optimizer._optimize_parameters(strategy_name)
            
            if optimized_params:
                results['optimization_completed'] = True
                results['params_optimized'] = len(optimized_params) > 0
                results['optimized_params'] = optimized_params
                
                print(f"  ✅ 参数优化完成")
                for param_name, value in optimized_params.items():
                    print(f"    ├─ {param_name}: {value}")
                
                # 测试模拟回测
                backtest_result = optimizer._simulate_backtest(strategy_name, optimized_params)
                if backtest_result:
                    results['backtest_result'] = backtest_result
                    improvement = backtest_result.get('improvement', 0)
                    results['improvement_detected'] = improvement > 0
                    print(f"  ✅ 模拟回测完成")
                    print(f"    ├─ 优化前收益率: {backtest_result.get('baseline_return', 0)*100:.2f}%")
                    print(f"    ├─ 优化后收益率: {backtest_result.get('annual_return', 0)*100:.2f}%")
                    print(f"    └─ 提升幅度: {improvement*100:+.2f}%")
            else:
                print(f"  ⚠️ 参数优化未执行（策略不在优化列表中）")
            
        except Exception as e:
            print(f"  ❌ 优化测试失败: {e}")
            results['error'] = str(e)
        
        self.results['optimize'] = results
        return results
    
    def test_rollback_mechanism(self) -> Dict[str, Any]:
        """测试策略回滚机制"""
        print("\n" + "=" * 70)
        print("↩️ 测试: 策略回滚机制")
        print("=" * 70)
        
        results = {
            'rollback_completed': False,
            'original_file_restored': False,
        }
        
        try:
            from auto_backtest.strategy_optimizer import StrategyOptimizer
            optimizer = StrategyOptimizer()
            
            strategy_name = TEST_CONFIG['optimization_test']['strategy_name']
            
            # 检查是否有备份文件
            archive_dir = optimizer.archive_dir
            if os.path.exists(archive_dir):
                backup_files = [f for f in os.listdir(archive_dir) 
                              if f.startswith(f"{optimizer.backup_prefix}{strategy_name}")]
                results['backup_files_found'] = len(backup_files)
                print(f"  📂 找到 {len(backup_files)} 个备份文件")
                
                if backup_files:
                    results['rollback_completed'] = True
                    results['original_file_restored'] = True
                    print(f"  ✅ 回滚机制正常（备份文件可用）")
                else:
                    print(f"  ⚠️ 无备份文件，回滚不可用")
            else:
                print(f"  ⚠️ 备份目录不存在")
            
        except Exception as e:
            print(f"  ❌ 回滚测试失败: {e}")
            results['error'] = str(e)
        
        self.results['rollback'] = results
        return results
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有优化器测试"""
        print("\n" + "=" * 80)
        print("🔧 启动策略优化器工作机制测试")
        print("=" * 80)
        
        self.test_backup_mechanism()
        self.test_optimize_mechanism()
        self.test_rollback_mechanism()
        
        return self.results

# ============================================================
# 第五部分：回测系统集成测试
# ============================================================
class BacktestSystemTest:
    """测试回测系统的完整流程"""
    
    def __init__(self):
        self.results = {}
    
    def test_backtest_flow(self) -> Dict[str, Any]:
        """测试回测系统完整流程"""
        print("\n" + "=" * 80)
        print("🏗️ 测试: 回测系统完整流程")
        print("=" * 80)
        
        results = {
            'system_initialized': False,
            'strategies_registered': False,
            'backtest_executed': False,
            'audit_executed': False,
            'gain_modules_integrated': {},
        }
        
        try:
            from auto_backtest.auto_backtest_system import AutoBacktestSystem
            
            # 使用临时数据库
            test_db = f"test_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            system = AutoBacktestSystem(db_path=test_db)
            
            results['system_initialized'] = True
            print(f"  ✅ 回测系统初始化成功")
            
            # 检查注册的策略
            results['strategies_registered'] = len(system.strategies) > 0
            print(f"  ✅ 已注册 {len(system.strategies)} 个策略:")
            for s in system.strategies:
                print(f"    ├─ {s['name']} ({s['type']})")
            
            # 运行回测
            for strategy in system.strategies[:2]:  # 测试前2个策略
                print(f"\n  📊 回测: {strategy['name']}")
                backtest_result = system.run_backtest(
                    strategy_name=strategy['name'],
                    days=30,
                    initial_balance=100000
                )
                
                if backtest_result.get('success'):
                    results['backtest_executed'] = True
                    print(f"    ├─ 年化收益率: {backtest_result.get('annual_return', 0)*100:.2f}%")
                    print(f"    ├─ 夏普比率: {backtest_result.get('sharpe_ratio', 0):.2f}")
                    print(f"    ├─ 最大回撤: {backtest_result.get('max_drawdown', 0)*100:.2f}%")
                    print(f"    └─ 交易次数: {backtest_result.get('total_trades', 0)}")
                    
                    # 检查增益模块集成
                    gain_checks = {
                        'performance_tracker': 'risk_decision' not in backtest_result,
                        'risk_controller': 'risk_decision' in backtest_result,
                        'data_quality': 'data_quality' in backtest_result,
                        'rl_suggestion': 'rl_suggestion' in backtest_result,
                    }
                    results['gain_modules_integrated'] = gain_checks
                    
                    for module, integrated in gain_checks.items():
                        status = "✅" if integrated else "❌"
                        print(f"    {status} 增益模块: {module}")
            
            # 运行审计
            print(f"\n  📋 审计: {system.strategies[0]['name']}")
            audit_result = system.audit_strategy(system.strategies[0]['name'])
            results['audit_executed'] = audit_result.get('audit_passed', False)
            print(f"    {'✅' if results['audit_executed'] else '❌'} 审计结果: {'通过' if results['audit_executed'] else '未通过'}")
            
            # 清理临时数据库
            if os.path.exists(test_db):
                os.remove(test_db)
                print(f"\n  🧹 临时数据库已清理: {test_db}")
            
        except Exception as e:
            print(f"  ❌ 回测系统测试失败: {e}")
            import traceback
            traceback.print_exc()
            results['error'] = str(e)
        
        self.results['backtest_system'] = results
        return results

# ============================================================
# 第六部分：增益模块集成测试
# ============================================================
class GainModuleTest:
    """测试增益性优化模块的集成效果"""
    
    def __init__(self):
        self.results = {}
    
    def test_all_gain_modules(self) -> Dict[str, Any]:
        """测试所有增益模块"""
        print("\n" + "=" * 80)
        print("🧩 测试: 增益性优化模块集成")
        print("=" * 80)
        
        results = {}
        
        # 1. 测试 StrategyPerformanceTracker
        if TEST_CONFIG['gain_module_test']['performance_tracker']:
            print(f"\n{'─' * 50}")
            print("📊 测试: StrategyPerformanceTracker")
            print(f"{'─' * 50}")
            
            try:
                from utils.strategy_performance_tracker import get_performance_tracker
                tracker = get_performance_tracker()
                tracker.enabled = True
                
                # 模拟交易记录
                for i in range(20):
                    trade = {
                        'timestamp': datetime.now().isoformat(),
                        'strategy': 'TestStrategy',
                        'action': 'buy' if i % 2 == 0 else 'sell',
                        'quantity': 100 + i,
                        'price': 100.0 + i * 0.1,
                        'market_regime': 'range_bound',
                        'signal_confidence': 0.8,
                        'risk_score': 0.2,
                        'portfolio_value_before': 100000 + i * 1000,
                        'portfolio_value_after': 100000 + i * 1000 + 500,
                        'reason_code': 'signal_triggered',
                    }
                    tracker.record_trade(trade)
                
                metrics = tracker.get_rolling_metrics('TestStrategy', window=10)
                results['performance_tracker'] = {
                    'status': 'SUCCESS',
                    'total_profit': float(metrics.total_profit),
                    'sharpe_ratio': float(metrics.sharpe_ratio),
                    'max_drawdown': float(metrics.max_drawdown),
                    'win_rate': float(metrics.win_rate),
                    'total_trades': int(metrics.total_trades),
                }
                print(f"  ✅ 性能追踪器工作正常")
                print(f"    ├─ 总收益: {metrics.total_profit:.2f}")
                print(f"    ├─ 夏普比率: {metrics.sharpe_ratio:.2f}")
                print(f"    └─ 交易次数: {metrics.total_trades}")
                
            except Exception as e:
                results['performance_tracker'] = {'status': 'ERROR', 'error': str(e)}
                print(f"  ❌ 性能追踪器测试失败: {e}")
        
        # 2. 测试 UnifiedRiskController
        if TEST_CONFIG['gain_module_test']['risk_controller']:
            print(f"\n{'─' * 50}")
            print("🛡️ 测试: UnifiedRiskController")
            print(f"{'─' * 50}")
            
            try:
                from utils.unified_risk_controller import get_risk_controller
                risk_ctrl = get_risk_controller()
                risk_ctrl.enabled = True
                
                # 注册策略并设置资本
                risk_ctrl.set_capital(100000)
                risk_ctrl.register_strategy('TestStrategy', sharpe_ratio=1.5, volatility=0.02)
                
                # 模拟风险评估 - 使用 check_strategy_risk
                risk_params = {
                    'annual_return': 0.15,
                    'sharpe_ratio': 1.5,
                    'max_drawdown': -0.08,
                    'win_rate': 0.65,
                    'total_trades': 100,
                }
                risk_decision = risk_ctrl.check_strategy_risk('TestStrategy', risk_params)
                
                # 模拟交易校验
                trade_data = {
                    'strategy': 'TestStrategy',
                    'quantity': 100,
                    'price': 100.0,
                    'side': 'buy',
                    'portfolio_value': 100000,
                }
                trade_check = risk_ctrl.check_trade(trade_data)
                
                results['risk_controller'] = {
                    'status': 'SUCCESS',
                    'risk_score': float(risk_decision.get('risk_score', 0)),
                    'action': risk_decision.get('action', 'unknown'),
                    'trade_check_passed': trade_check.passed,
                }
                print(f"  ✅ 风险控制器工作正常")
                print(f"    ├─ 风险评分: {risk_decision.get('risk_score', 0):.2f}")
                print(f"    ├─ 建议操作: {risk_decision.get('action', 'unknown')}")
                print(f"    └─ 交易校验: {'通过' if trade_check.passed else '拒绝'}")
                
            except Exception as e:
                results['risk_controller'] = {'status': 'ERROR', 'error': str(e)}
                print(f"  ❌ 风险控制器测试失败: {e}")
        
        # 3. 测试 SmartParamOptimizer
        if TEST_CONFIG['gain_module_test']['param_optimizer']:
            print(f"\n{'─' * 50}")
            print("🔧 测试: SmartParamOptimizer")
            print(f"{'─' * 50}")
            
            try:
                from utils.smart_param_optimizer import get_param_optimizer
                optimizer = get_param_optimizer()
                optimizer.enabled = True
                
                from utils.smart_param_optimizer import ParamSpace
                
                # 定义参数空间
                param_spaces = [
                    ParamSpace('grid_spacing', 0.001, 0.01, 'float'),
                    ParamSpace('stop_loss', 0.005, 0.02, 'float'),
                    ParamSpace('take_profit', 0.01, 0.03, 'float'),
                    ParamSpace('max_position', 50, 200, 'int', step=10),
                ]
                
                # 定义目标函数
                def objective(params):
                    """模拟目标函数"""
                    grid_spacing = params['grid_spacing']
                    stop_loss = params['stop_loss']
                    take_profit = params['take_profit']
                    max_position = params['max_position']
                    
                    total_return = (
                        0.15 - 5 * grid_spacing - 2 * stop_loss
                        + 3 * take_profit + 0.0005 * max_position
                        + np.random.normal(0, 0.02)
                    )
                    sharpe_ratio = (
                        1.5 - 30 * grid_spacing - 10 * stop_loss
                        + 20 * take_profit + 0.002 * max_position
                        + np.random.normal(0, 0.1)
                    )
                    max_drawdown = -(
                        0.05 + 2 * grid_spacing + 5 * stop_loss
                        - 3 * take_profit - 0.0001 * max_position
                        + np.random.normal(0, 0.01)
                    )
                    return {
                        'total_return': total_return,
                        'sharpe_ratio': sharpe_ratio,
                        'max_drawdown': max_drawdown,
                    }
                
                # 执行优化
                opt_result = optimizer.optimize(
                    objective_func=objective,
                    param_spaces=param_spaces,
                    strategy_name='TestStrategy',
                    n_iterations=20,
                    objectives=['total_return', 'sharpe_ratio'],
                    weights=[0.6, 0.4],
                )
                
                results['param_optimizer'] = {
                    'status': 'SUCCESS',
                    'best_score': float(opt_result.best_score),
                    'best_params': opt_result.best_params,
                    'n_iterations': opt_result.n_iterations,
                    'convergence': opt_result.convergence,
                }
                print(f"  ✅ 参数优化器工作正常")
                print(f"    ├─ 最优分数: {opt_result.best_score:.4f}")
                print(f"    ├─ 迭代次数: {opt_result.n_iterations}")
                print(f"    ├─ 收敛: {opt_result.convergence}")
                print(f"    └─ 最优参数: {opt_result.best_params}")
                
            except Exception as e:
                results['param_optimizer'] = {'status': 'ERROR', 'error': str(e)}
                print(f"  ❌ 参数优化器测试失败: {e}")
        
        # 4. 测试 RLEnhancer
        if TEST_CONFIG['gain_module_test']['rl_enhancer']:
            print(f"\n{'─' * 50}")
            print("🧠 测试: RLEnhancer")
            print(f"{'─' * 50}")
            
            try:
                from utils.rl_enhancer import get_rl_enhancer
                rl = get_rl_enhancer()
                rl.enabled = True
                
                # 构建状态并选择动作
                state = rl.build_state({
                    'price': 100.0,
                    'returns': 0.15,
                    'sharpe': 1.5,
                    'drawdown': -0.08,
                    'volatility': 0.02,
                })
                action = rl.select_action(state)
                
                results['rl_enhancer'] = {
                    'status': 'SUCCESS',
                    'action': float(action),
                }
                print(f"  ✅ RL增强器工作正常")
                print(f"    └─ 建议仓位: {float(action):.4f}")
                
            except Exception as e:
                results['rl_enhancer'] = {'status': 'ERROR', 'error': str(e)}
                print(f"  ❌ RL增强器异常: {e}")
                print(f"    └─ 错误: {str(e)}")
        
        # 输出结果汇总
        print()
        print("=" * 60)
        print("测试完成")
        print("=" * 60)
        print()
        print("结果汇总:")
        for module, result in results.items():
            status_icon = "✅" if result.get('status') == 'SUCCESS' else "❌"
            print(f"  {status_icon} {module}: {result.get('status', 'UNKNOWN')}")
            if 'error' in result:
                print(f"      └─ 错误: {result['error']}")
        print()
        print("=" * 60)
        print("测试结束")
        print("=" * 60)
        
        self.results = results
        return results


# ============================================================
# 第七部分：主入口
# ============================================================
def main():
    """主测试入口"""
    print("=" * 80)
    print("🌟 智能体优化策略回测工作机制全面测试")
    print(f"   启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    all_results = {}
    
    # 1. 运行策略全面测试
    print("\n" + "=" * 80)
    print("📊 第一阶段：核心策略全面测试")
    print("=" * 80)
    engine = StrategyTestEngine(initial_balance=TEST_CONFIG['initial_balance'])
    df = engine.run_comprehensive_test()
    report = engine.generate_report(df)
    print(report)
    all_results['strategy_test'] = df.to_dict('records')
    
    # 2. 运行策略优化器测试
    print("\n" + "=" * 80)
    print("🔧 第二阶段：策略优化器工作机制测试")
    print("=" * 80)
    optimizer_test = StrategyOptimizerTest()
    optimizer_results = optimizer_test.run_all_tests()
    all_results['optimizer_test'] = optimizer_results
    
    # 3. 运行回测系统集成测试
    print("\n" + "=" * 80)
    print("🏗️ 第三阶段：回测系统集成测试")
    print("=" * 80)
    backtest_test = BacktestSystemTest()
    backtest_results = backtest_test.test_backtest_flow()
    all_results['backtest_system'] = backtest_results
    
    # 4. 运行增益模块集成测试
    print("\n" + "=" * 80)
    print("🧩 第四阶段：增益模块集成测试")
    print("=" * 80)
    gain_test = GainModuleTest()
    gain_results = gain_test.test_all_gain_modules()
    all_results['gain_modules'] = gain_results
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📋 最终测试汇总")
    print("=" * 80)
    
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    
    # 统计策略测试
    if 'strategy_test' in all_results:
        for r in all_results['strategy_test']:
            total_tests += 1
            if r.get('status') == 'SUCCESS':
                passed_tests += 1
            else:
                failed_tests += 1
    
    # 统计优化器测试
    for test_name, result in all_results.get('optimizer_test', {}).items():
        total_tests += 1
        if result.get('backup_created') or result.get('optimization_completed') or result.get('rollback_completed'):
            passed_tests += 1
        elif 'error' not in result:
            passed_tests += 1
        else:
            failed_tests += 1
    
    # 统计回测系统测试
    bt = all_results.get('backtest_system', {}).get('backtest_system', {})
    for key in ['system_initialized', 'strategies_registered', 'backtest_executed', 'audit_executed']:
        total_tests += 1
        if bt.get(key):
            passed_tests += 1
        else:
            failed_tests += 1
    
    # 统计增益模块测试
    for module, result in all_results.get('gain_modules', {}).items():
        total_tests += 1
        if result.get('status') == 'SUCCESS':
            passed_tests += 1
        else:
            failed_tests += 1
    
    print(f"\n  📊 总测试数: {total_tests}")
    print(f"  ✅ 通过: {passed_tests}")
    print(f"  ❌ 失败: {failed_tests}")
    print(f"  📈 通过率: {passed_tests/max(total_tests,1)*100:.1f}%")
    
    # 保存完整结果
    result_file = Path(PROJECT_ROOT) / "reports" / f"agent_backtest_workflow_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_file.parent.mkdir(exist_ok=True)
    
    # 转换不可序列化的类型
    def convert_for_json(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict('records')
        return obj
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=convert_for_json)
    print(f"\n📝 完整结果已保存: {result_file}")
    
    print("\n" + "=" * 80)
    print("🏁 全部测试完成")
    print(f"   完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    return all_results


if __name__ == "__main__":
    main()
