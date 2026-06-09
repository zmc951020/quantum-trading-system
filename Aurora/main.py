#!/usr/bin/env python3
"""
Aurora 量化交易系统主入口
"""

import logging
import click
import os
import sys
import time
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

# 添加Aurora目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入策略和模型
try:
    from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
    from strategies.ml_range_grid import MLRangeGridTrading
    from strategies.grid_trading import GridTrading
    from strategies.trend_trading import MovingAveragesStrategy, RSIStrategy
    from strategies.multi_factor_resonance import MultiFactorResonanceStrategy
    from strategies.fund_allocation import DCAStrategy, MLFundAllocator
    from strategies.strategy_base import StrategyManager
    from strategies.fourier_rl_strategy import FourierRLStrategy
    from strategies.huijin_value_strategy import HuijinValueStrategy
    from ml.trend_prediction import TrendPredictor
    from risk.risk_management import RiskManager
    
    STRATEGIES_AVAILABLE = True
except ImportError as e:
    logger.error(f"导入策略模块失败: {str(e)}")
    STRATEGIES_AVAILABLE = False

# 导入系统健康监控和安全模块
health_monitor = None
monitoring_scheduler = None
database_manager = None
security_control = None

try:
    from monitor.system_health import get_system_health_monitor
    health_monitor = get_system_health_monitor()
    logger.info("[OK] system_health_monitor imported successfully")
except Exception as e:
    logger.warning(f"[WARNING] system_health_monitor import failed: {e}")

try:
    from monitor.scheduler import get_monitoring_scheduler, initialize_default_tasks
    initialize_default_tasks()
    monitoring_scheduler = get_monitoring_scheduler()
    logger.info("[OK] monitoring_scheduler imported successfully")
except Exception as e:
    logger.warning(f"[WARNING] monitoring_scheduler import failed: {e}")

try:
    from utils.database_manager import get_db_manager
    database_manager = get_db_manager()
    logger.info("[OK] database_manager imported successfully")
except Exception as e:
    logger.warning(f"[WARNING] database_manager import failed: {e}")

try:
    from risk.data_source_risk_control import get_security_control
    security_control = get_security_control()
    logger.info("[OK] security_control imported successfully")
except Exception as e:
    logger.warning(f"[WARNING] security_control import failed: {e}")

class AuroraSystem:
    """
    Aurora 量化交易系统
    """
    
    def __init__(self):
        """
        初始化系统
        """
        self.initial_balance = float(os.getenv('INITIAL_BALANCE', 100000))
        self.current_balance = self.initial_balance
        self.trade_interval = int(os.getenv('TRADE_INTERVAL', 1))
        self.data_frequency = os.getenv('DATA_FREQUENCY', '1m')
        
        # 初始化策略
        self.strategies = {}
        self.fund_allocator = None
        self.risk_manager = None
        self.strategy_manager = StrategyManager()
        
        # 初始化新模块
        self.health_monitor = health_monitor
        self.monitoring_scheduler = monitoring_scheduler
        self.database_manager = database_manager
        self.security_control = security_control
        
        # 记录系统启动日志
        if self.database_manager:
            try:
                self.database_manager.insert_system_log(
                    'INFO', 'AuroraSystem', '系统初始化', 'Aurora 量化交易系统正在初始化'
                )
            except Exception as e:
                logger.warning(f"记录系统日志失败: {e}")
        
        self._initialize_strategies()
        
        # 启动监控调度器
        if self.monitoring_scheduler:
            try:
                self.monitoring_scheduler.start()
                logger.info("监控调度器已启动")
            except Exception as e:
                logger.warning(f"启动监控调度器失败: {e}")
    
    def _initialize_strategies(self):
        """
        初始化策略
        """
        try:
            # 初始化最终市场自适应网格策略
            base_price = float(os.getenv('BASE_PRICE', 100))
            self.strategies['final_market_adaptive'] = FinalMarketAdaptiveGrid(
                base_price=base_price,
                initial_balance=self.initial_balance
            )
            
            # 初始化机器学习横盘网格策略
            self.strategies['ml_range_grid'] = MLRangeGridTrading(
                base_price=base_price,
                initial_balance=self.initial_balance
            )
            
            # 初始化傅里叶策略
            self.strategies['fourier_rl'] = FourierRLStrategy(
                base_price=base_price,
                initial_balance=self.initial_balance
            )

            # 初始化汇金价值AI轮动策略
            self.strategies['huijin_value'] = HuijinValueStrategy(
                initial_balance=max(self.initial_balance, 3000000)
            )

            # 初始化资金分配器
            self.fund_allocator = MLFundAllocator(initial_balance=self.initial_balance)
            self.fund_allocator.add_strategy('final_market_adaptive', self.strategies['final_market_adaptive'], 0.4)
            self.fund_allocator.add_strategy('ml_range_grid', self.strategies['ml_range_grid'], 0.3)
            self.fund_allocator.add_strategy('fourier_rl', self.strategies['fourier_rl'], 0.3)
            
            # 初始化风险管理
            self.risk_manager = RiskManager(
                confidence_level=float(os.getenv('CONFIDENCE_LEVEL', 0.95))
            )
            
            # 注册策略到策略管理器
            for name, strategy in self.strategies.items():
                self.strategy_manager.register_strategy(name, strategy)
            
            # 默认激活傅里叶策略
            self.strategy_manager.select_strategy('fourier_rl')
            
            logger.info("策略初始化完成")
            
        except Exception as e:
            logger.error(f"初始化策略失败: {str(e)}")
    
    def generate_test_data(self, length=1000, start_price=100):
        """
        生成测试数据
        """
        dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
        returns = np.random.normal(0, 0.01, length)
        # 添加趋势和周期
        trend = np.linspace(0, 0.2, length)  # 20%的长期趋势
        cycle = 0.08 * np.sin(np.linspace(0, 6 * np.pi, length))  # 周期性波动
        returns = returns + trend + cycle
        prices = start_price * (1 + returns).cumprod()
        return pd.Series(prices, index=dates)
    
    def run_backtest(self):
        """
        运行回测
        """
        logger.info("开始回测")
        
        # 生成测试数据
        data = self.generate_test_data(length=1000)
        logger.info(f"生成测试数据: {len(data)} 个数据点")
        
        # 优化资金分配
        logger.info("优化资金分配")
        self.fund_allocator.optimize_with_machine_learning(
            data,
            max_queue_size=50,
            convergence_threshold=0.0001,
            convergence_patience=100,
            parallel_workers=4
        )
        
        # 运行策略
        logger.info("运行策略")
        for i, price in enumerate(data):
            timestamp = data.index[i]
            
            # 使用策略管理器更新当前激活的策略
            if self.strategy_manager:
                self.strategy_manager.update_price(price, data.iloc[:i+1] if i >= 100 else None)
            
            # 更新所有策略
            for name, strategy in self.strategies.items():
                strategy.update_price(price, data.iloc[:i+1] if i >= 100 else None)
            
            # 更新资金分配器
            if self.fund_allocator:
                self.fund_allocator.update(price, timestamp)
        
        # 计算性能
        final_price = data.iloc[-1]
        
        # 最终市场自适应网格策略性能
        if 'final_market_adaptive' in self.strategies:
            final_perf = self.strategies['final_market_adaptive'].get_performance()
            logger.info(f"最终市场自适应网格策略性能: 收益率 = {final_perf['total_return'] * 100:.2f}%, 夏普比率 = {final_perf['sharpe_ratio']:.2f}, 胜率 = {final_perf['win_rate'] * 100:.2f}%")
        
        # 机器学习横盘网格策略性能
        if 'ml_range_grid' in self.strategies:
            ml_perf = self.strategies['ml_range_grid'].get_performance()
            logger.info(f"机器学习横盘网格策略性能: 收益率 = {ml_perf['total_return'] * 100:.2f}%, 夏普比率 = {ml_perf['sharpe_ratio']:.2f}, 胜率 = {ml_perf['win_rate'] * 100:.2f}%")
        
        # 傅里叶策略性能
        fourier_perf = None
        if 'fourier_rl' in self.strategies:
            fourier_perf = self.strategies['fourier_rl'].get_performance()
            logger.info(f"傅里叶策略性能: 收益率 = {fourier_perf['total_return'] * 100:.2f}%, 夏普比率 = {fourier_perf['sharpe_ratio']:.2f}, 胜率 = {fourier_perf['win_rate'] * 100:.2f}%")
        
        # 策略管理器活跃策略性能
        if self.strategy_manager:
            active_perf = self.strategy_manager.get_active_performance()
            if active_perf:
                logger.info(f"活跃策略性能: 收益率 = {active_perf.get('total_return', 0) * 100:.2f}%, 夏普比率 = {active_perf.get('sharpe_ratio', 0):.2f}, 胜率 = {active_perf.get('win_rate', 0) * 100:.2f}%")
        
        # 资金分配器性能
        if self.fund_allocator:
            fund_perf = self.fund_allocator.get_performance(final_price)
            logger.info(f"资金分配器性能: 收益率 = {fund_perf['overall']['return']:.2f}%")
        
        logger.info("回测完成")
        
        return {
            'final_market_adaptive_performance': final_perf if 'final_market_adaptive' in self.strategies else None,
            'ml_range_grid_performance': ml_perf if 'ml_range_grid' in self.strategies else None,
            'fourier_rl_performance': fourier_perf if 'fourier_rl' in self.strategies else None,
            'fund_performance': fund_perf if self.fund_allocator else None
        }
    
    def start_trading(self):
        """
        启动交易系统
        """
        logger.info("启动 Aurora 量化交易系统")
        
        # 运行启动前健康检测
        if not self._run_pre_flight_check():
            logger.error("启动前检测失败，系统退出")
            return
        
        # 这里将实现实盘交易逻辑
        # 目前使用测试数据进行模拟
        self.run_backtest()
        
        logger.info("Aurora 量化交易系统启动完成")
    
    def _run_pre_flight_check(self) -> bool:
        """
        启动前预检 - 检查系统各模块状态
        
        Returns:
            True if all checks pass, False otherwise
        """
        logger.info("🛫 运行启动前健康检测...")
        
        checks = [
            ("模块完整性", self._check_module_dependencies),
            ("配置完整性", self._check_configuration),
            ("数据连接", self._check_data_sources),
            ("风险控制", self._check_risk_control),
            ("端口可用性", self._check_port_availability)
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            logger.info(f"  检查 {check_name}...")
            try:
                passed, message = check_func()
                if passed:
                    logger.info(f"    ✅ {message}")
                else:
                    logger.warning(f"    ⚠️ {message}")
                    all_passed = False
            except Exception as e:
                logger.error(f"    ❌ {check_name}检查异常: {str(e)}")
                all_passed = False
        
        if all_passed:
            logger.info("✅ 所有启动前检测通过")
        else:
            logger.warning("⚠️ 部分检测未通过，请检查日志")
        
        return all_passed
    
    def _check_module_dependencies(self) -> tuple:
        """检查模块依赖"""
        required_modules = [
            'strategies', 'ml', 'risk', 'data'
        ]
        
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                return False, f"缺少模块: {module}"
        
        return True, "所有模块依赖正常"
    
    def _check_configuration(self) -> tuple:
        """检查配置完整性"""
        required_env_vars = [
            'INITIAL_BALANCE', 'TRADE_INTERVAL', 'DATA_SOURCE'
        ]
        
        missing_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            return False, f"缺少环境变量: {', '.join(missing_vars)}"
        
        return True, "配置完整性检查通过"
    
    def _check_data_sources(self) -> tuple:
        """检查数据连接"""
        try:
            from data import get_multi_data_source_manager
            mgr = get_multi_data_source_manager()
            if mgr:
                status = mgr.get_status()
                if status.get('sources'):
                    return True, f"数据连接正常，可用数据源: {list(status['sources'].keys())}"
                return False, "数据源为空"
            return False, "数据管理器未初始化"
        except Exception as e:
            return False, f"数据连接检查失败: {str(e)}"
    
    def _check_risk_control(self) -> tuple:
        """检查风险控制配置"""
        try:
            from risk import get_data_source_risk_control
            risk_ctrl = get_data_source_risk_control()
            if risk_ctrl:
                return True, "风险控制模块正常"
            return False, "风险控制模块未初始化"
        except Exception as e:
            return False, f"风险控制检查失败: {str(e)}"
    
    def _check_port_availability(self) -> tuple:
        """检查端口可用性"""
        try:
            from utils.port_manager import get_port_manager
            pm = get_port_manager()
            
            # 检查默认端口
            ports = [5000, 8000, 8080]
            available_ports = [p for p in ports if pm.is_port_available(p)]
            
            if available_ports:
                return True, f"可用端口: {available_ports}"
            return False, "所有默认端口都被占用"
        except Exception as e:
            return False, f"端口检查失败: {str(e)}"
    
    def train_models(self):
        """
        训练模型
        """
        logger.info("开始训练模型")
        
        # 生成训练数据
        data = self.generate_test_data(length=2000)
        
        # 训练趋势预测模型
        try:
            trend_model = TrendPredictor()
            trend_model.train(data)
            logger.info("趋势预测模型训练完成")
        except Exception as e:
            logger.error(f"训练模型失败: {str(e)}")
        
        logger.info("模型训练完成")
    
    def optimize_strategies(self):
        """
        优化策略参数
        """
        logger.info("开始优化策略参数")
        
        # 生成测试数据
        data = self.generate_test_data(length=1000)
        
        # 优化资金分配
        if self.fund_allocator:
            self.fund_allocator.optimize_with_machine_learning(
                data,
                max_queue_size=100,
                convergence_threshold=0.00005,
                convergence_patience=200,
                parallel_workers=8
            )
            logger.info("资金分配优化完成")
        
        logger.info("策略参数优化完成")

@click.group()
def cli():
    """Aurora 量化交易系统"""
    pass

@cli.command()
def start():
    """启动交易系统"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    system.start_trading()

@cli.command()
def backtest():
    """运行回测"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    system.run_backtest()

@cli.command()
def train():
    """训练模型"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    system.train_models()

@cli.command()
def optimize():
    """优化策略参数"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    system.optimize_strategies()

# ============ 韬定律集群集成 ============

@cli.command()
@click.option('--strategy', '-s', default='all', 
              help='策略名称 (all/单个策略名)')
@click.option('--market-data', '-m', is_flag=True, default=False,
              help='使用市场数据进行回测评估')
def tau_optimize(strategy, market_data):
    """🔬 韬定律集群优化 - 使用空间折叠技术深度优化策略参数"""
    print("\n" + "=" * 80)
    print("🔬 韬定律策略优化器集群")
    print("=" * 80)
    
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    # 初始化系统
    system = AuroraSystem()
    
    # 导入性能分析器
    try:
        from monitor.strategy_optimizer import StrategyPerformanceAnalyzer
        analyzer = StrategyPerformanceAnalyzer()
    except ImportError as e:
        print(f"❌ 无法导入优化器: {e}")
        return
    
    # 生成测试数据
    data = system.generate_test_data(length=1000) if market_data else None
    
    if strategy == 'all':
        # 批量优化所有策略
        print(f"\n🎯 批量优化: 所有 {len(system.strategies)} 个策略")
        result = analyzer.optimize_all_strategies(
            strategy_manager=system.strategy_manager,
            market_data=data
        )
        
        if result.get('success'):
            print(f"\n✅ 批量优化完成")
            print(f"   总策略数: {result.get('total_strategies', 0)}")
            print(f"   成功优化: {result.get('successful', 0)}")
            print(f"   显著改善: {result.get('improved', 0)}")
            
            # 显示排名
            ranking = result.get('ranking', [])
            if ranking:
                print(f"\n🏆 策略评分排名:")
                for i, (name, score) in enumerate(ranking[:5], 1):
                    print(f"   {i}. {name}: {score:.4f}")
        else:
            print(f"❌ 批量优化失败: {result.get('error', '未知错误')}")
    else:
        # 优化单个策略
        if strategy not in system.strategies:
            print(f"❌ 策略 '{strategy}' 不存在")
            print(f"   可用策略: {', '.join(system.strategies.keys())}")
            return
        
        print(f"\n🎯 目标策略: {strategy}")
        result = analyzer.optimize_with_tau_cluster(
            strategy_name=strategy,
            strategy_instance=system.strategies[strategy],
            market_data=data
        )
        
        if result.get('success'):
            print(f"\n✅ 优化完成")
            print(f"   方法: {result.get('optimization_method', 'unknown')}")
            print(f"   评分: {result.get('best_score', 0):.4f}")
            print(f"   改进: {result.get('improvement', 0):+.4f}")
            
            # 应用优化结果
            if click.confirm("\n是否应用优化后的参数到策略?", default=True):
                applied = analyzer.apply_tau_optimization(strategy, system.strategies[strategy])
                if applied:
                    print(f"✅ 参数已应用到策略 '{strategy}'")
                else:
                    print(f"⚠️  参数应用失败")
        else:
            print(f"❌ 优化失败: {result.get('error', '未知错误')}")
    
    print("\n" + "=" * 80)

@cli.command()
def tau_status():
    """ℹ️  检查韬定律集群状态"""
    print("\n" + "=" * 80)
    print("ℹ️  韬定律集群状态检查")
    print("=" * 80)
    
    try:
        from monitor.strategy_optimizer import check_tau_cluster_available
        status = check_tau_cluster_available()
        
        if status['available']:
            print(f"✅ 韬定律集群可用")
            details = status.get('status', {})
            print(f"   优化次数: {details.get('optimization_count', 0)}")
            print(f"   总评估次数: {details.get('total_evaluations', 0)}")
            print(f"   集群模块: {'可用' if details.get('tau_cluster_available', False) else '不可用 (降级为简化优化器)'}")
            print(f"   参数存储: {'已连接' if details.get('param_store_available', False) else '未连接'}")
            print(f"\n💡 使用方法:")
            print(f"   python main.py tau-optimize --strategy all")
            print(f"   python main.py tau-optimize --strategy fourier_rl")
            print(f"   python main.py tau-optimize --strategy final_market_adaptive --market-data")
        else:
            print(f"⚠️  韬定律集群不可用")
            print(f"   原因: {status.get('error', '未知')}")
            print(f"   提示: 将韬定律集群目录添加到 Python 路径")
    except Exception as e:
        print(f"❌ 检查失败: {e}")
    
    print("=" * 80)

@cli.command()
@click.argument('strategy_name')
def tau_apply(strategy_name):
    """✅ 应用韬定律优化后的参数到策略"""
    print(f"\n应用优化参数到策略: {strategy_name}")
    
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用")
        return
    
    system = AuroraSystem()
    
    if strategy_name not in system.strategies:
        print(f"❌ 策略 '{strategy_name}' 不存在")
        return
    
    try:
        from monitor.strategy_optimizer import StrategyPerformanceAnalyzer
        analyzer = StrategyPerformanceAnalyzer()
        
        applied = analyzer.apply_tau_optimization(
            strategy_name,
            system.strategies[strategy_name]
        )
        
        if applied:
            print(f"✅ 成功应用参数到 '{strategy_name}'")
        else:
            print(f"⚠️  没有找到优化历史或应用失败")
            print(f"   请先运行: python main.py tau-optimize --strategy {strategy_name}")
    except Exception as e:
        print(f"❌ 应用失败: {e}")

@cli.command()
def list_strategies():
    """列出所有可用策略"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    strategies = system.strategy_manager.list_strategies()
    logger.info("可用策略:")
    for i, strategy in enumerate(strategies):
        logger.info(f"{i+1}. {strategy}")

@cli.command()
def select_strategy(strategy_name):
    """选择策略"""
    if not STRATEGIES_AVAILABLE:
        logger.error("策略模块不可用，请检查依赖安装")
        return
    
    system = AuroraSystem()
    success = system.strategy_manager.select_strategy(strategy_name)
    if success:
        logger.info(f"成功选择策略: {strategy_name}")
    else:
        logger.error(f"策略 {strategy_name} 不存在")

@cli.command()
def web():
    """启动Web可视化界面"""
    logger.info("启动Web可视化界面...")
    try:
        from visualization import app
        host = os.getenv('WEB_HOST', '0.0.0.0')
        port = int(os.getenv('WEB_PORT', 5000))
        logger.info(f"Web服务启动于 http://{host}:{port}")
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.error(f"启动Web服务失败: {str(e)}")

@cli.command()
@click.option('--host', default='0.0.0.0', help='监听地址')
@click.option('--port', default=5000, help='监听端口')
@click.option('--debug', is_flag=True, help='调试模式')
def serve(host, port, debug):
    """启动Web服务（带参数）"""
    logger.info(f"启动Web服务: {host}:{port}")
    try:
        from visualization import app
        logger.info(f"Web服务启动于 http://{host}:{port}")
        app.run(host=host, port=port, debug=debug)
    except Exception as e:
        logger.error(f"启动Web服务失败: {str(e)}")

if __name__ == "__main__":
    cli()
