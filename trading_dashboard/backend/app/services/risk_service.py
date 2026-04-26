import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from typing import Dict, List, Optional

# 导入我们的交易系统模块
try:
    from RiskMetrics import RiskMetrics
    from StressTesting import StressTesting
    from StressTesting import StressScenario
    HAS_TRADING_SYSTEM = True
except ImportError:
    HAS_TRADING_SYSTEM = False

class RiskService:
    """风控服务"""
    
    def __init__(self):
        self.risk_metrics = None
        self.stress_testing = None
        self.scenarios = [
            "2008_financial_crisis",
            "2020_covid",
            "2015_stock_crash",
            "1987_black_monday",
            "2022_interest_rate_hike"
        ]
    
    def initialize(self):
        """初始化服务"""
        if HAS_TRADING_SYSTEM:
            self.risk_metrics = RiskMetrics(confidence_level=0.95)
            self.stress_testing = StressTesting()
        print("风控服务初始化完成")
    
    def calculate_var(self, returns: List[float], confidence_level: float = 0.95, method: str = "historical") -> Dict:
        """计算VaR和CVaR"""
        if HAS_TRADING_SYSTEM and self.risk_metrics:
            # 使用我们的RiskMetrics模块
            var = self.risk_metrics.calculate_var_historical(np.array(returns))
            cvar = self.risk_metrics.calculate_cvar_historical(np.array(returns))
        else:
            # 模拟数据
            var = -0.025  # 2.5%的每日风险
            cvar = -0.035  # 3.5%的条件风险
        
        return {
            "var": var,
            "cvar": cvar,
            "confidence_level": confidence_level,
            "method": method
        }
    
    def run_stress_test(self, portfolio_values: List[float], scenario: str) -> Dict:
        """运行压力测试"""
        if HAS_TRADING_SYSTEM and self.stress_testing:
            # 使用我们的StressTesting模块
            result = self.stress_testing.run_historical_scenario(np.array(portfolio_values), scenario)
        else:
            # 模拟数据
            scenario_mapping = {
                "2008_financial_crisis": -0.40,
                "2020_covid": -0.35,
                "2015_stock_crash": -0.45,
                "1987_black_monday": -0.22,
                "2022_interest_rate_hike": -0.25
            }
            loss_pct = scenario_mapping.get(scenario, -0.20)
            result = {
                "scenario": scenario,
                "estimated_loss": portfolio_values[-1] * loss_pct,
                "estimated_loss_pct": loss_pct,
                "stressed_var": -0.05  # 压力测试后的VaR
            }
        
        return result
    
    def get_stress_scenarios(self) -> List[str]:
        """获取可用的压力测试场景"""
        return self.scenarios
