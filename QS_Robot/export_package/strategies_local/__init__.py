# strategies_local - 完整策略实现包
# 从Aurora主应用复制的完整策略实现
# 替换QS-Robot中的简单stub版本

import sys
import os

# 添加Aurora主目录到Python路径，解决傅里叶RL等策略的依赖问题
_AURORA_ROOT = r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora"
if os.path.exists(_AURORA_ROOT) and _AURORA_ROOT not in sys.path:
    sys.path.insert(0, _AURORA_ROOT)

from .strategy_base import StrategyBase

# 导入所有完整策略（修正后的正确路径和类名）
try:
    from .golden_bowl_ice_break import GoldenBowlIceBreakStrategy
except ImportError as e:
    print(f"[strategies_local] 金碗破冰导入失败: {e}")
    GoldenBowlIceBreakStrategy = None

try:
    from .ml_range_grid import MLRangeGridTrading as MLRangeGridStrategy
except ImportError as e:
    print(f"[strategies_local] ML范围网格导入失败: {e}")
    MLRangeGridStrategy = None

try:
    from .high_return_grid import HighReturnGridTrading as HighReturnGridStrategy
except ImportError as e:
    print(f"[strategies_local] 高收益网格导入失败: {e}")
    HighReturnGridStrategy = None

try:
    from .bernoulli_coanda_strategy import BernoulliCoandaStrategy
except ImportError as e:
    print(f"[strategies_local] 伯努利柯安达导入失败: {e}")
    BernoulliCoandaStrategy = None

try:
    from .gyro_precession_strategy import GyroCompleteStrategy as GyroPrecessionStrategy
except ImportError as e:
    print(f"[strategies_local] 陀螺进动导入失败: {e}")
    GyroPrecessionStrategy = None

try:
    from .multi_factor_resonance import MultiFactorResonanceStrategy
except ImportError as e:
    print(f"[strategies_local] 多因子共振导入失败: {e}")
    MultiFactorResonanceStrategy = None

try:
    from .final_market_adaptive import FinalMarketAdaptiveGrid as FinalMarketAdaptiveStrategy
except ImportError as e:
    print(f"[strategies_local] 最终市场自适应导入失败: {e}")
    FinalMarketAdaptiveStrategy = None

try:
    from .fund_allocation import DCAStrategy as FundAllocationStrategy
except ImportError as e:
    print(f"[strategies_local] 定投资金配置导入失败: {e}")
    FundAllocationStrategy = None

try:
    from .adaptive_range_grid import AdaptiveRangeGridTrading as AdaptiveRangeGridStrategy
except ImportError as e:
    print(f"[strategies_local] 自适应范围网格导入失败: {e}")
    AdaptiveRangeGridStrategy = None

try:
    from .gyro_minute_strategy_v6_optimized import GyroMinuteStrategyV6Optimized as GyroV6OptimizedStrategy
except ImportError as e:
    print(f"[strategies_local] 陀螺V6导入失败: {e}")
    GyroV6OptimizedStrategy = None

try:
    from .downtrend_optimized import DownMarketStrategy as DowntrendOptimizedStrategy
except ImportError as e:
    print(f"[strategies_local] 下跌市场优化导入失败: {e}")
    DowntrendOptimizedStrategy = None

try:
    from .newton_momentum_enhanced import NewtonMomentumEnhanced as NewtonMomentumEnhancedStrategy
except ImportError as e:
    print(f"[strategies_local] 牛顿动量导入失败: {e}")
    NewtonMomentumEnhancedStrategy = None

try:
    from .thermodynamic_entropy_enhanced import ThermodynamicEntropyEnhanced as ThermodynamicEntropyEnhancedStrategy
except ImportError as e:
    print(f"[strategies_local] 热力学熵导入失败: {e}")
    ThermodynamicEntropyEnhancedStrategy = None

try:
    from .ppo_trading_agent import TradingAgent as PPOTradingAgentStrategy
except ImportError as e:
    print(f"[strategies_local] PPO交易智能体导入失败: {e}")
    PPOTradingAgentStrategy = None

try:
    from .rl_adaptive_param_strategy import RLAdaptiveParamStrategy
except ImportError as e:
    print(f"[strategies_local] RL自适应参数导入失败: {e}")
    RLAdaptiveParamStrategy = None

try:
    from .fourier_rl_strategy import FourierRLStrategy
except ImportError as e:
    print(f"[strategies_local] 傅里叶RL导入失败: {e}")
    FourierRLStrategy = None

try:
    from .fractal_chaos_strategy import FractalChaosStrategy
except ImportError as e:
    print(f"[strategies_local] 分形混沌导入失败: {e}")
    FractalChaosStrategy = None

try:
    from .fluid_dynamics_strategy import FluidDynamicsStrategy
except ImportError as e:
    print(f"[strategies_local] 流体动力学导入失败: {e}")
    FluidDynamicsStrategy = None

try:
    from .final_grid_executor import GridExecutor as FinalGridExecutorStrategy
except ImportError as e:
    print(f"[strategies_local] 最终网格执行器导入失败: {e}")
    FinalGridExecutorStrategy = None

try:
    from .final_market_classifier import MarketClassifier as FinalMarketClassifierStrategy
except ImportError as e:
    print(f"[strategies_local] 最终市场分类器导入失败: {e}")
    FinalMarketClassifierStrategy = None

try:
    from .final_optimized_strategy import DynamicGridStrategy as FinalOptimizedStrategy
except ImportError as e:
    print(f"[strategies_local] 最终优化策略导入失败: {e}")
    FinalOptimizedStrategy = None

try:
    from .optimized_strategy_deepseek import ImprovedTradingAgent as OptimizedStrategyDeepSeek
except ImportError as e:
    print(f"[strategies_local] DeepSeek优化策略导入失败: {e}")
    OptimizedStrategyDeepSeek = None

try:
    from .adaptive_ml_strategy import AdaptiveMLStrategy
except ImportError as e:
    print(f"[strategies_local] 自适应ML策略导入失败: {e}")
    AdaptiveMLStrategy = None

# QS-Robot原生策略（第5组）
try:
    from .shepherd_rotation_strategy import ShepherdRotationStrategy
except ImportError as e:
    print(f"[strategies_local] 牧羊人轮动策略导入失败: {e}")
    ShepherdRotationStrategy = None

try:
    from .special_forces_strategy import SpecialForcesStrategy
except ImportError as e:
    print(f"[strategies_local] 特种兵策略导入失败: {e}")
    SpecialForcesStrategy = None

try:
    from .vibe_chanlun import SignalEngine as VibeChanlunStrategy
except ImportError as e:
    print(f"[strategies_local] Vibe缠论策略导入失败: {e}")
    VibeChanlunStrategy = None

try:
    from .vibe_ml_strategy import SignalEngine as VibeMLStrategy
except ImportError as e:
    print(f"[strategies_local] Vibe ML策略导入失败: {e}")
    VibeMLStrategy = None

try:
    from .vibe_multi_factor import SignalEngine as VibeMultiFactorStrategy
except ImportError as e:
    print(f"[strategies_local] Vibe多因子策略导入失败: {e}")
    VibeMultiFactorStrategy = None


# 策略注册表（键名与create_strategy_factory_v11接收的名称一致）
# 对于需要base_price等初始化参数的策略，用lambda包装提供默认值
STRATEGY_REGISTRY = {
    "golden_bowl_ice_break": GoldenBowlIceBreakStrategy,
    "ml_range_grid": (lambda: MLRangeGridStrategy(base_price=10.0)) if MLRangeGridStrategy else None,
    "high_return_grid": HighReturnGridStrategy,
    "bernoulli_coanda_strategy": BernoulliCoandaStrategy,
    "gyro_precession_strategy": GyroPrecessionStrategy,
    "multi_factor_resonance": MultiFactorResonanceStrategy,
    "final_market_adaptive": (lambda: FinalMarketAdaptiveStrategy(base_price=10.0)) if FinalMarketAdaptiveStrategy else None,
    "fund_allocation": FundAllocationStrategy,
    "adaptive_range_grid": (lambda: AdaptiveRangeGridStrategy(base_price=10.0)) if AdaptiveRangeGridStrategy else None,
    "gyro_minute_strategy_v6_optimized": GyroV6OptimizedStrategy,  # 无参数可初始化，base_price有默认值
    "downtrend_optimized": DowntrendOptimizedStrategy,
    "newton_momentum_enhanced": (lambda: NewtonMomentumEnhancedStrategy(base_price=10.0)) if NewtonMomentumEnhancedStrategy else None,
    "thermodynamic_entropy_enhanced": (lambda: ThermodynamicEntropyEnhancedStrategy(base_price=10.0)) if ThermodynamicEntropyEnhancedStrategy else None,
    "ppo_trading_agent": PPOTradingAgentStrategy,
    "rl_adaptive_param_strategy": RLAdaptiveParamStrategy,
    "fourier_rl_strategy": FourierRLStrategy,
    "fractal_chaos_strategy": FractalChaosStrategy,
    "fluid_dynamics_strategy": FluidDynamicsStrategy,
    "final_grid_executor": (lambda: FinalGridExecutorStrategy(base_price=10.0)) if FinalGridExecutorStrategy else None,
    "final_market_classifier": FinalMarketClassifierStrategy,
    "final_optimized_strategy": FinalOptimizedStrategy,
    "optimized_strategy_deepseek": OptimizedStrategyDeepSeek,
    "adaptive_ml_strategy": AdaptiveMLStrategy,
    # QS-Robot原生策略（第5组，5个）
    "shepherd_rotation_strategy": ShepherdRotationStrategy,
    "special_forces_strategy": SpecialForcesStrategy,
    "vibe_chanlun": VibeChanlunStrategy,
    "vibe_ml_strategy": VibeMLStrategy,
    "vibe_multi_factor": VibeMultiFactorStrategy,
}

success_count = len([k for k, v in STRATEGY_REGISTRY.items() if v is not None])
print(f"[strategies_local] 已加载 {success_count}/{len(STRATEGY_REGISTRY)} 个完整策略")
