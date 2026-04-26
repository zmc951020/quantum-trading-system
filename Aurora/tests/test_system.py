#!/usr/bin/env python3
"""
系统功能和性能测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 测试配置类
class TestConfig:
    """测试配置"""
    
    # ==================== 数据生成配置 ====================
    DATA_LENGTH = 1000  # 数据长度
    START_PRICE = 100.0  # 起始价格
    VOLATILITY = 0.01  # 波动率
    # 数据频率: 'S'=秒级, 'T'=分钟, 'H'=小时, 'D'=日度
    # 注意：秒级数据会产生大量数据点，请谨慎使用
    DATA_FREQUENCY = 'D'  
    
    # ==================== 初始资金配置 ====================
    INITIAL_BALANCE = 100000.0
    
    # ==================== 网格交易配置 ====================
    GRID_SPACING = 0.01  # 网格间距
    
    # ==================== 资金分配配置 ====================
    DEFAULT_ALLOCATION = 0.5  # 默认分配比例
    
    # ==================== 机器学习优化配置 ====================
    ML_OPTIMIZATION_ITERATIONS = 10000  # 机器学习优化迭代次数
    ML_PRINT_INTERVAL = 1000  # 打印间隔
    
    # ==================== 交易频率控制（合规性） ====================
    # 重要说明：
    # 1. 数据频率 ≠ 交易频率
    #    - 数据频率：多久获取一次价格数据（如每秒、每分钟）
    #    - 交易频率：策略实际执行交易的次数，由策略逻辑决定
    # 2. 在每个数据点上，策略可以执行0次、1次或多次交易（只要满足策略条件）
    # 3. 以下参数用于合规性控制，限制最大交易次数
    
    MAX_TRADES_PER_MINUTE = None  # 每分钟最大交易次数，None表示不限制
    MAX_TRADES_PER_HOUR = None    # 每小时最大交易次数，None表示不限制
    MAX_TRADES_PER_DAY = None      # 每天最大交易次数，None表示不限制
    MAX_TRADE_AMOUNT = None        # 单次最大交易金额，None表示不限制
    
    # ==================== 随机种子（用于可复现性） ====================
    RANDOM_SEED = 42

# 尝试导入模块
MODULES = {}
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

try:
    from strategies.grid_trading import GridTrading, MonteCarloSimulation, MLGridTrading
    MODULES['GridTrading'] = GridTrading
    MODULES['MonteCarloSimulation'] = MonteCarloSimulation
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
    from risk.risk_management import RiskManager
    MODULES['RiskManager'] = RiskManager
except ImportError as e:
    print(f"警告: 导入风险管理模块失败: {str(e)}")

try:
    from ml.dynamic_grid import MLBasedGridTrading
    from ml.trend_prediction import AdaptiveTradingStrategy
    MODULES['MLBasedGridTrading'] = MLBasedGridTrading
    MODULES['AdaptiveTradingStrategy'] = AdaptiveTradingStrategy
except ImportError as e:
    print(f"警告: 导入机器学习模块失败: {str(e)}")

try:
    from utils.monitoring import TradeMonitor, PerformanceEvaluator, ReportGenerator
    MODULES['TradeMonitor'] = TradeMonitor
    MODULES['PerformanceEvaluator'] = PerformanceEvaluator
    MODULES['ReportGenerator'] = ReportGenerator
except ImportError as e:
    print(f"警告: 导入监控模块失败: {str(e)}")

try:
    from config.config import config
    MODULES['config'] = config
except ImportError as e:
    print(f"警告: 导入配置模块失败: {str(e)}")

# 简单监控类
class SimpleMonitor:
    """简单监控器"""
    def __init__(self):
        self.trades = []
        self.balance_history = []
        self.position_history = []
        self.timestamps = []
    
    def record_trade(self, timestamp, action, quantity, price, balance, position):
        self.trades.append({
            "timestamp": timestamp, 
            "action": action, 
            "quantity": quantity, 
            "price": price, 
            "balance": balance, 
            "position": position
        })
        self.balance_history.append(balance)
        self.position_history.append(position)
        self.timestamps.append(timestamp)
    
    def get_trades(self):
        return pd.DataFrame(self.trades)
    
    def get_balance_history(self):
        return pd.DataFrame({
            "timestamp": self.timestamps, 
            "balance": self.balance_history, 
            "position": self.position_history
        })

class SimpleEvaluator:
    """简单评估器"""
    def evaluate(self, balance_history, trades):
        return {
            "total_return": 0, 
            "sharpe_ratio": 0, 
            "max_drawdown": 0, 
            "win_rate": 0, 
            "total_trades": 0, 
            "average_return": 0, 
            "volatility": 0
        }

class SimpleReportGenerator:
    """简单报告生成器"""
    def generate_report(self, metrics, trades, balance_history, file_path):
        print(f"报告生成失败: 监控模块不可用")

class SystemTester:
    """
    系统测试器
    """
    
    def __init__(self, config: Optional[TestConfig] = None):
        """
        初始化系统测试器
        
        Args:
            config: 测试配置
        """
        self.config = config or TestConfig()
        
        # 设置随机种子
        np.random.seed(self.config.RANDOM_SEED)
        
        # 使用MODULES字典中的模块
        self.monitor = MODULES.get('TradeMonitor', None)
        self.evaluator = MODULES.get('PerformanceEvaluator', None)
        self.report_generator = MODULES.get('ReportGenerator', None)
        
        # 如果监控模块不可用，使用简单的监控
        if self.monitor is None:
            self.monitor = SimpleMonitor()
        else:
            self.monitor = self.monitor()
        
        if self.evaluator is None:
            self.evaluator = SimpleEvaluator()
        else:
            self.evaluator = self.evaluator()
        
        if self.report_generator is None:
            self.report_generator = SimpleReportGenerator()
        else:
            self.report_generator = self.report_generator()
    
    def generate_test_data(
        self, 
        length: Optional[int] = None, 
        start_price: Optional[float] = None, 
        volatility: Optional[float] = None,
        freq: Optional[str] = None
    ) -> pd.Series:
        """
        生成测试数据
        
        Args:
            length: 数据长度
            start_price: 起始价格
            volatility: 波动率
            freq: 数据频率: 'S'=秒级, 'T'=分钟, 'H'=小时, 'D'=日度
            
        Returns:
            测试数据
        """
        length = length or self.config.DATA_LENGTH
        start_price = start_price or self.config.START_PRICE
        volatility = volatility or self.config.VOLATILITY
        freq = freq or self.config.DATA_FREQUENCY
        
        # 根据频率计算起始时间
        if freq == 'S':
            # 秒级数据
            start_time = datetime.now() - timedelta(seconds=length)
        elif freq == 'T':
            # 分钟级数据
            start_time = datetime.now() - timedelta(minutes=length)
        elif freq == 'H':
            # 小时级数据
            start_time = datetime.now() - timedelta(hours=length)
        else:
            # 日度数据
            start_time = datetime.now() - timedelta(days=length)
        
        dates = pd.date_range(start=start_time, periods=length, freq=freq)
        returns = np.random.normal(0, volatility, length)
        prices = start_price * (1 + returns).cumprod()
        return pd.Series(prices, index=dates)
    
    def test_models(self, data: pd.Series):
        """
        测试交易模型
        
        Args:
            data: 测试数据
        """
        print("测试交易模型...")
        
        try:
            # 测试ARMA模型
            if 'ARMA_Model' in MODULES:
                arma_model = MODULES['ARMA_Model']()
                arma_model.fit(data)
                arma_pred = arma_model.predict(steps=5)
                print(f"ARMA模型预测结果: {arma_pred}")
            else:
                print("ARMA模型不可用")
        except Exception as e:
            print(f"ARMA模型测试失败: {str(e)}")
        
        try:
            # 测试SARIMA模型
            if 'SARIMA_Model' in MODULES:
                sarima_model = MODULES['SARIMA_Model']()
                sarima_model.fit(data)
                sarima_pred = sarima_model.predict(steps=5)
                print(f"SARIMA模型预测结果: {sarima_pred}")
            else:
                print("SARIMA模型不可用")
        except Exception as e:
            print(f"SARIMA模型测试失败: {str(e)}")
        
        try:
            # 测试LSTM模型
            if 'LSTM_Model' in MODULES:
                lstm_model = MODULES['LSTM_Model']()
                lstm_model.fit(data)
                lstm_pred = lstm_model.predict(steps=5)
                print(f"LSTM模型预测结果: {lstm_pred}")
            else:
                print("LSTM模型不可用")
        except Exception as e:
            print(f"LSTM模型测试失败: {str(e)}")
    
    def _run_strategy_backtest(self, strategy, data: pd.Series, strategy_name: str, min_data_window: int = 20):
        """
        运行策略回测的通用方法
        
        Args:
            strategy: 策略实例
            data: 测试数据
            strategy_name: 策略名称
            min_data_window: 最小数据窗口
        """
        for i, price in enumerate(data):
            # 传递当前数据窗口进行市场类型检测
            current_data = data.iloc[:i+1] if i+1 >= min_data_window else data
            result = strategy.update_price(price, data=current_data)
            timestamp = data.index[i]
            self.monitor.record_trade(
                timestamp=timestamp,
                action=result['action'],
                quantity=result.get('quantity', 0),
                price=price,
                balance=result['balance'],
                position=result['position']
            )
    
    def test_grid_trading(self, data: pd.Series):
        """
        测试网格化交易策略
        
        Args:
            data: 测试数据
        """
        print("测试网格化交易策略...")
        
        try:
            if 'GridTrading' in MODULES:
                grid_trading = MODULES['GridTrading'](
                    base_price=data.iloc[0], 
                    grid_spacing=self.config.GRID_SPACING
                )
                
                self._run_strategy_backtest(grid_trading, data, "grid", min_data_window=20)
                
                performance = grid_trading.get_performance()
                print(f"网格化交易策略性能: {performance}")
            else:
                print("网格化交易策略不可用")
        except Exception as e:
            print(f"网格化交易策略测试失败: {str(e)}")
    
    def test_trend_trading(self, data: pd.Series):
        """
        测试趋势交易策略
        
        Args:
            data: 测试数据
        """
        print("测试趋势交易策略...")
        
        try:
            if 'MovingAveragesStrategy' in MODULES and 'RSIStrategy' in MODULES and 'TrendSwitchingStrategy' in MODULES:
                ma_strategy = MODULES['MovingAveragesStrategy']()
                rsi_strategy = MODULES['RSIStrategy']()
                trend_strategy = MODULES['TrendSwitchingStrategy']()
                
                signals = ma_strategy.generate_signals(data)
                print(f"移动平均线策略信号数量: {len(signals[signals['signal'] != 0])}")
                
                rsi_signals = rsi_strategy.generate_signals(data)
                print(f"RSI策略信号数量: {len(rsi_signals[rsi_signals['signal'] != 0])}")
                
                combined_signal = trend_strategy.get_combined_signal(data)
                print(f"组合信号: {combined_signal}")
                
                recommended_strategy = trend_strategy.switch_strategy(data)
                print(f"推荐策略: {recommended_strategy}")
            else:
                print("趋势交易策略不可用")
        except Exception as e:
            print(f"趋势交易策略测试失败: {str(e)}")
    
    def test_fund_allocation(self, data: pd.Series):
        """
        测试资金配置策略
        
        Args:
            data: 测试数据
        """
        print("测试资金配置策略...")
        
        try:
            if 'FundAllocator' in MODULES and 'DCAStrategy' in MODULES and 'HFTStrategy' in MODULES:
                allocator = MODULES['FundAllocator'](initial_balance=self.config.INITIAL_BALANCE)
                dca_strategy = MODULES['DCAStrategy']()
                hft_strategy = MODULES['HFTStrategy']()
                
                allocator.add_strategy("dca", dca_strategy, self.config.DEFAULT_ALLOCATION)
                allocator.add_strategy("hft", hft_strategy, self.config.DEFAULT_ALLOCATION)
                
                for i, price in enumerate(data):
                    timestamp = data.index[i]
                    results = allocator.update(price, timestamp)
                
                performance = allocator.get_performance(data.iloc[-1])
                print(f"传统资金配置策略性能: {performance}")
            else:
                print("资金配置策略不可用")
        except Exception as e:
            print(f"资金配置策略测试失败: {str(e)}")
    
    def test_ml_fund_allocation(self, data: pd.Series):
        """
        测试基于机器学习的资金配置策略
        
        Args:
            data: 测试数据
        """
        print("测试基于机器学习的资金配置策略...")
        
        try:
            if 'MLFundAllocator' in MODULES and 'DCAStrategy' in MODULES and 'GridTrading' in MODULES:
                ml_allocator = MODULES['MLFundAllocator'](initial_balance=self.config.INITIAL_BALANCE)
                dca_strategy = MODULES['DCAStrategy']()
                grid_strategy = MODULES['GridTrading'](
                    base_price=data.iloc[0], 
                    grid_spacing=self.config.GRID_SPACING
                )
                
                ml_allocator.add_strategy("dca", dca_strategy, self.config.DEFAULT_ALLOCATION)
                ml_allocator.add_strategy("grid", grid_strategy, self.config.DEFAULT_ALLOCATION)
                
                # 执行机器学习优化
                ml_allocator.optimize_with_machine_learning(
                    data, 
                    iterations=self.config.ML_OPTIMIZATION_ITERATIONS
                )
                
                for i, price in enumerate(data):
                    timestamp = data.index[i]
                    results = ml_allocator.update(price, timestamp)
                
                performance = ml_allocator.get_performance(data.iloc[-1])
                print(f"基于机器学习的资金配置策略性能: {performance}")
            else:
                print("基于机器学习的资金配置策略不可用")
        except Exception as e:
            print(f"基于机器学习的资金配置策略测试失败: {str(e)}")
    
    def test_risk_management(self, data: pd.Series):
        """
        测试风险管理模块
        
        Args:
            data: 测试数据
        """
        print("测试风险管理模块...")
        
        try:
            if 'RiskManager' in MODULES:
                risk_manager = MODULES['RiskManager']()
                returns = data.pct_change().dropna()
                
                var_historical = risk_manager.calculate_var_historical(returns)
                print(f"历史VaR: {var_historical:.4f}")
                
                var_parametric = risk_manager.calculate_var_parametric(returns)
                print(f"参数法VaR: {var_parametric:.4f}")
                
                es_historical = risk_manager.calculate_es_historical(returns)
                print(f"历史ES: {es_historical:.4f}")
                
                es_parametric = risk_manager.calculate_es_parametric(returns)
                print(f"参数法ES: {es_parametric:.4f}")
                
                greeks = risk_manager.calculate_greeks(
                    option_price=5, 
                    underlying_price=100, 
                    strike_price=100, 
                    time_to_expiry=1, 
                    risk_free_rate=0.05, 
                    volatility=0.2
                )
                print(f"期权希腊字母: {greeks}")
            else:
                print("风险管理模块不可用")
        except Exception as e:
            print(f"风险管理模块测试失败: {str(e)}")
    
    def test_ml_based_grid(self, data: pd.Series):
        """
        测试基于机器学习的网格化交易
        
        Args:
            data: 测试数据
        """
        print("测试基于机器学习的网格化交易...")
        
        try:
            if 'MLBasedGridTrading' in MODULES:
                ml_grid = MODULES['MLBasedGridTrading'](base_price=data.iloc[0])
                ml_grid.train_model(data)
                
                for i, price in enumerate(data):
                    result = ml_grid.update_price(price, data.iloc[:i+1])
                    timestamp = data.index[i]
                    self.monitor.record_trade(
                        timestamp=timestamp,
                        action=result['action'],
                        quantity=result.get('quantity', 0),
                        price=price,
                        balance=result['balance'],
                        position=result['position']
                    )
                
                performance = ml_grid.get_performance()
                print(f"基于机器学习的网格化交易性能: {performance}")
            else:
                print("基于机器学习的网格化交易不可用")
        except Exception as e:
            print(f"基于机器学习的网格化交易测试失败: {str(e)}")
    
    def test_ml_grid_trading(self, data: pd.Series):
        """
        测试基于机器学习的优化网格化交易策略
        
        Args:
            data: 测试数据
        """
        print("测试基于机器学习的优化网格化交易策略...")
        
        try:
            if 'MLGridTrading' in MODULES:
                ml_grid_trading = MODULES['MLGridTrading'](base_price=data.iloc[0])
                
                self._run_strategy_backtest(ml_grid_trading, data, "ml_grid", min_data_window=20)
                
                performance = ml_grid_trading.get_performance()
                print(f"基于机器学习的优化网格化交易性能: {performance}")
            else:
                print("基于机器学习的优化网格化交易不可用")
        except Exception as e:
            print(f"基于机器学习的优化网格化交易测试失败: {str(e)}")
    
    def test_multi_factor_resonance(self, data: pd.Series):
        """
        测试多因子共振策略
        
        Args:
            data: 测试数据
        """
        print("测试多因子共振策略...")
        
        try:
            if 'MultiFactorResonanceStrategy' in MODULES:
                multi_factor_strategy = MODULES['MultiFactorResonanceStrategy'](
                    initial_balance=self.config.INITIAL_BALANCE
                )
                
                self._run_strategy_backtest(multi_factor_strategy, data, "multi_factor", min_data_window=120)
                
                performance = multi_factor_strategy.get_performance(data.iloc[-1])
                print(f"多因子共振策略性能: {performance}")
            else:
                print("多因子共振策略不可用")
        except Exception as e:
            print(f"多因子共振策略测试失败: {str(e)}")
    
    def test_adaptive_trading(self, data: pd.Series):
        """
        测试自适应交易策略
        
        Args:
            data: 测试数据
        """
        print("测试自适应交易策略...")
        
        try:
            if 'AdaptiveTradingStrategy' in MODULES:
                adaptive_strategy = MODULES['AdaptiveTradingStrategy']()
                adaptive_strategy.train_models(data)
                
                for i, price in enumerate(data):
                    timestamp = data.index[i]
                    result = adaptive_strategy.update_price(price, data, timestamp)
                    self.monitor.record_trade(
                        timestamp=timestamp,
                        action=result['action'],
                        quantity=result.get('quantity', 0),
                        price=price,
                        balance=result['balance'],
                        position=result['position']
                    )
                
                performance = adaptive_strategy.get_performance(data.iloc[-1])
                print(f"自适应交易策略性能: {performance}")
            else:
                print("自适应交易策略不可用")
        except Exception as e:
            print(f"自适应交易策略测试失败: {str(e)}")
    
    def test_system(self, data: Optional[pd.Series] = None):
        """
        测试整个系统
        
        Args:
            data: 测试数据（可选，如果不提供则自动生成）
        """
        print("=" * 60)
        print("开始测试整个系统...")
        print("=" * 60)
        
        # 打印配置信息
        freq_desc = {
            'S': '秒级',
            'T': '分钟级', 
            'H': '小时级',
            'D': '日度'
        }
        print(f"\n【测试配置】")
        print(f"  数据频率: {freq_desc.get(self.config.DATA_FREQUENCY, self.config.DATA_FREQUENCY)}")
        print(f"  数据长度: {self.config.DATA_LENGTH} 条")
        print(f"  初始资金: {self.config.INITIAL_BALANCE:.2f}")
        print(f"  机器学习优化迭代: {self.config.ML_OPTIMIZATION_ITERATIONS} 次")
        print(f"\n【重要说明】")
        print(f"  • 数据频率 ≠ 交易频率")
        print(f"  • 数据频率：每{freq_desc.get(self.config.DATA_FREQUENCY, self.config.DATA_FREQUENCY)}获取一次价格")
        print(f"  • 交易频率：由策略逻辑决定，每个数据点可交易0次、1次或多次")
        print(f"  • 交易次数限制：{self._get_trade_limit_desc()}")
        print("=" * 60)
        
        # 生成或使用测试数据
        if data is None:
            data = self.generate_test_data()
        print(f"\n测试数据: {len(data)} 条，频率: {self.config.DATA_FREQUENCY}")
        print(f"时间范围: {data.index[0]} 至 {data.index[-1]}")
        
        # 测试各个模块
        self.test_models(data)
        self.test_grid_trading(data)
        self.test_trend_trading(data)
        self.test_fund_allocation(data)
        self.test_ml_fund_allocation(data)
        self.test_risk_management(data)
        self.test_ml_based_grid(data)
        self.test_ml_grid_trading(data)
        self.test_multi_factor_resonance(data)
        self.test_adaptive_trading(data)
        
        # 评估系统性能
        balance_history = self.monitor.get_balance_history()
        trades = self.monitor.get_trades()
        
        if not balance_history.empty:
            metrics = self.evaluator.evaluate(balance_history['balance'], trades)
            print("\n" + "=" * 60)
            print("系统性能评估:")
            print("=" * 60)
            for key, value in metrics.items():
                print(f"{key}: {value}")
            
            # 生成报告
            self.report_generator.generate_report(
                metrics=metrics,
                trades=trades,
                balance_history=balance_history,
                file_path="reports/performance_report.txt"
            )
        
        print("\n" + "=" * 60)
        print("系统测试完成！")
        print("=" * 60)
    
    def _get_trade_limit_desc(self) -> str:
        """获取交易限制描述"""
        limits = []
        if self.config.MAX_TRADES_PER_MINUTE is not None:
            limits.append(f"每分钟最多{self.config.MAX_TRADES_PER_MINUTE}次")
        if self.config.MAX_TRADES_PER_HOUR is not None:
            limits.append(f"每小时最多{self.config.MAX_TRADES_PER_HOUR}次")
        if self.config.MAX_TRADES_PER_DAY is not None:
            limits.append(f"每天最多{self.config.MAX_TRADES_PER_DAY}次")
        if self.config.MAX_TRADE_AMOUNT is not None:
            limits.append(f"单次最大金额{self.config.MAX_TRADE_AMOUNT:.2f}")
        
        return "、".join(limits) if limits else "无限制（由策略逻辑决定）"

def main():
    """主函数"""
    # 创建报告目录
    import os
    os.makedirs("reports", exist_ok=True)
    
    # 创建测试配置
    config = TestConfig()
    
    # ==================== 配置示例（根据需要取消注释） ====================
    
    # 示例1：使用分钟级数据
    # config.DATA_FREQUENCY = 'T'
    # config.DATA_LENGTH = 1440  # 一天的分钟数
    
    # 示例2：使用秒级数据（注意：会产生大量数据）
    # config.DATA_FREQUENCY = 'S'
    # config.DATA_LENGTH = 3600  # 一小时的秒数
    
    # 示例3：设置交易频率限制（合规性控制）
    # config.MAX_TRADES_PER_MINUTE = 10  # 每分钟最多10次交易
    # config.MAX_TRADES_PER_DAY = 1000    # 每天最多1000次交易
    # config.MAX_TRADE_AMOUNT = 10000      # 单次交易最大10000元
    
    # 示例4：调整机器学习优化迭代次数
    # config.ML_OPTIMIZATION_ITERATIONS = 5000
    # config.ML_PRINT_INTERVAL = 500
    
    # ========================================================================
    
    # 创建测试器并运行测试
    tester = SystemTester(config)
    tester.test_system()

if __name__ == "__main__":
    main()
