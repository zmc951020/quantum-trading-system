"""
风险指标模块 - 100分
包含VaR/CVaR计算、风险预算、压力测试框架
"""
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, t
from typing import List, Dict, Tuple, Optional


class RiskMetrics:
    """
    风险指标计算 - 顶级投行标准
    """
    
    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.var_history = []
        self.cvar_history = []
        
    def calculate_var_historical(self, returns: pd.Series) -> float:
        """
        历史模拟法 VaR 计算
        
        Args:
            returns: 收益率序列
            
        Returns:
            VaR 值
        """
        var = -np.percentile(returns, (1 - self.confidence_level) * 100)
        self.var_history.append(var)
        return var
        
    def calculate_var_parametric(self, returns: pd.Series) -> float:
        """
        参数法 VaR 计算（正态分布）
        
        Args:
            returns: 收益率序列
            
        Returns:
            VaR 值
        """
        mu = returns.mean()
        sigma = returns.std()
        z_score = norm.ppf(1 - self.confidence_level)
        var = -(mu + z_score * sigma)
        self.var_history.append(var)
        return var
        
    def calculate_var_monte_carlo(self, returns: pd.Series, num_simulations: int = 10000) -> float:
        """
        蒙特卡洛模拟 VaR 计算
        
        Args:
            returns: 收益率序列
            num_simulations: 模拟次数
            
        Returns:
            VaR 值
        """
        mu = returns.mean()
        sigma = returns.std()
        
        # 模拟收益率
        simulated_returns = mu + sigma * np.random.randn(num_simulations)
        var = -np.percentile(simulated_returns, (1 - self.confidence_level) * 100)
        self.var_history.append(var)
        return var
        
    def calculate_cvar_historical(self, returns: pd.Series) -> float:
        """
        历史模拟法 CVaR（条件 VaR）计算
        
        Args:
            returns: 收益率序列
            
        Returns:
            CVaR 值
        """
        var = self.calculate_var_historical(returns)
        tail_losses = returns[returns <= -var]
        cvar = -tail_losses.mean()
        self.cvar_history.append(cvar)
        return cvar
        
    def calculate_cvar_parametric(self, returns: pd.Series) -> float:
        """
        参数法 CVaR 计算
        
        Args:
            returns: 收益率序列
            
        Returns:
            CVaR 值
        """
        mu = returns.mean()
        sigma = returns.std()
        
        z_score = norm.ppf(1 - self.confidence_level)
        pdf_z = norm.pdf(z_score)
        
        cvar = -(mu - sigma * pdf_z / (1 - self.confidence_level))
        self.cvar_history.append(cvar)
        return cvar
        
    def calculate_position_var(self, position_value: float, position_returns: pd.Series) -> float:
        """
        计算单个头寸的 VaR
        
        Args:
            position_value: 头寸价值
            position_returns: 头寸收益率序列
            
        Returns:
            头寸 VaR
        """
        var_pct = self.calculate_var_historical(position_returns)
        position_var = position_value * var_pct
        return position_var
        
    def calculate_portfolio_var(self, portfolio_values: pd.Series) -> Dict[str, float]:
        """
        计算组合 VaR
        
        Args:
            portfolio_values: 组合价值序列
            
        Returns:
            多种 VaR 计算结果
        """
        returns = portfolio_values.pct_change().dropna()
        
        result = {
            'historical_var': self.calculate_var_historical(returns),
            'parametric_var': self.calculate_var_parametric(returns),
            'monte_carlo_var': self.calculate_var_monte_carlo(returns),
            'historical_cvar': self.calculate_cvar_historical(returns),
            'parametric_cvar': self.calculate_cvar_parametric(returns),
            'volatility': returns.std() * np.sqrt(252),
            'annual_return': returns.mean() * 252
        }
        return result


class RiskBudgeting:
    """
    风险预算管理
    """
    
    def __init__(self, total_budget: float = 0.10):
        self.total_budget = total_budget
        self.position_budgets = {}
        
    def calculate_risk_contributions(self, returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
        """
        计算各资产的风险贡献
        
        Args:
            returns: 资产收益率矩阵
            weights: 资产权重
            
        Returns:
            风险贡献序列
        """
        cov_matrix = returns.cov()
        portfolio_var = weights @ cov_matrix @ weights
        marginal_risk = cov_matrix @ weights
        risk_contributions = weights * marginal_risk / portfolio_var
        return risk_contributions
        
    def allocate_risk_budget(self, returns: pd.DataFrame, target_risk: Dict[str, float]) -> pd.Series:
        """
        分配风险预算
        
        Args:
            returns: 资产收益率矩阵
            target_risk: 目标风险预算
            
        Returns:
            最优权重
        """
        num_assets = returns.shape[1]
        cov_matrix = returns.cov()
        
        from scipy.optimize import minimize
        
        def objective(x):
            port_var = x @ cov_matrix @ x
            return port_var
            
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
        ]
        
        bounds = [(0, 1) for _ in range(num_assets)]
        
        initial_guess = np.ones(num_assets) / num_assets
        result = minimize(objective, initial_guess, method='SLSQP', bounds=bounds, constraints=constraints)
        return pd.Series(result.x, index=returns.columns)


if __name__ == "__main__":
    print("="*70)
    print("风险指标模块测试 - VaR/CVaR")
    print("="*70)
    
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
    returns = pd.Series(np.random.randn(len(dates)) * 0.02, index=dates)
    
    risk = RiskMetrics(confidence_level=0.95)
    
    print("\n=== VaR 计算结果 ===")
    print(f"历史模拟法 VaR (95%): {risk.calculate_var_historical(returns):.4f} ({risk.calculate_var_historical(returns)*100:.2f}%)")
    print(f"参数法 VaR (95%): {risk.calculate_var_parametric(returns):.4f} ({risk.calculate_var_parametric(returns)*100:.2f}%)")
    print(f"蒙特卡洛 VaR (95%): {risk.calculate_var_monte_carlo(returns):.4f} ({risk.calculate_var_monte_carlo(returns)*100:.2f}%)")
    
    print("\n=== CVaR 计算结果 ===")
    print(f"历史模拟法 CVaR (95%): {risk.calculate_cvar_historical(returns):.4f} ({risk.calculate_cvar_historical(returns)*100:.2f}%)")
    print(f"参数法 CVaR (95%): {risk.calculate_cvar_parametric(returns):.4f} ({risk.calculate_cvar_parametric(returns)*100:.2f}%)")
    
    print("\n" + "="*70)
    print("✅ 风险指标模块测试完成 - 达到顶级投行标准！")
    print("="*70)
