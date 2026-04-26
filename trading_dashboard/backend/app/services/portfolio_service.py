import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from typing import Dict, List, Optional

class PortfolioService:
    """投资组合服务"""
    
    def __init__(self):
        self.portfolio_data = {
            "portfolio1": {
                "total_value": 1000000.0,
                "total_pnl": 150000.0,
                "total_pnl_pct": 0.15,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.15,
                "positions": [
                    {"symbol": "AAPL", "quantity": 100, "price": 150.0, "weight": 0.25, "pnl": 5000.0},
                    {"symbol": "MSFT", "quantity": 50, "price": 300.0, "weight": 0.30, "pnl": 7500.0},
                    {"symbol": "GOOG", "quantity": 20, "price": 1000.0, "weight": 0.40, "pnl": 10000.0},
                ],
                "cash": 50000.0
            }
        }
    
    def get_portfolio_overview(self, portfolio_id: str) -> Dict:
        """获取投资组合概览"""
        portfolio = self.portfolio_data.get(portfolio_id, self.portfolio_data["portfolio1"])
        
        return {
            "portfolio_id": portfolio_id,
            "total_value": portfolio["total_value"],
            "total_pnl": portfolio["total_pnl"],
            "total_pnl_pct": portfolio["total_pnl_pct"],
            "sharpe_ratio": portfolio["sharpe_ratio"],
            "max_drawdown": portfolio["max_drawdown"]
        }
    
    def get_positions(self, portfolio_id: str) -> Dict:
        """获取持仓信息"""
        portfolio = self.portfolio_data.get(portfolio_id, self.portfolio_data["portfolio1"])
        
        return {
            "portfolio_id": portfolio_id,
            "positions": portfolio["positions"],
            "cash": portfolio["cash"],
            "total_positions": len(portfolio["positions"])
        }
    
    def get_portfolio_history(self) -> Dict:
        """获取投资组合历史数据"""
        # 模拟100天的资金曲线数据
        dates = [f"2024-01-{i:02d}" for i in range(1, 101)]
        values = [1000000.0 * (1 + 0.001 * i + np.random.normal(0, 0.005)) for i in range(100)]
        
        return {
            "dates": dates,
            "values": values
        }
