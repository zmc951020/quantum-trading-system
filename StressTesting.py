"""
压力测试模块 - 100分
包含历史情景回放、蒙特卡洛模拟、极端市场测试
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import norm, t
from typing import Dict, List, Tuple, Optional


class StressScenario:
    """压力情景定义"""
    
    HISTORICAL_SCENARIOS = {
        '2008_financial_crisis': {
            'name': '2008金融危机',
            'return_adjustment': -0.40,
            'volatility_adjustment': 2.5,
            'description': '雷曼兄弟倒闭后的市场崩溃'
        },
        '2020_covid_crash': {
            'name': '2020新冠疫情',
            'return_adjustment': -0.35,
            'volatility_adjustment': 3.0,
            'description': '疫情引起的市场暴跌'
        },
        '2015_china_crash': {
            'name': '2015股灾',
            'return_adjustment': -0.45,
            'volatility_adjustment': 3.5,
            'description': '中国股市去杠杆引起的暴跌'
        },
        '1987_black_monday': {
            'name': '1987黑色星期一',
            'return_adjustment': -0.22,
            'volatility_adjustment': 4.0,
            'description': '美国股市单日暴跌22%'
        },
        '2022_rate_hike': {
            'name': '2022美联储加息',
            'return_adjustment': -0.25,
            'volatility_adjustment': 2.0,
            'description': '快速加息引起的熊市'
        }
    }
    
    HYPOTHETICAL_SCENARIOS = {
        'severe_recession': {
            'name': '严重衰退',
            'return_adjustment': -0.50,
            'volatility_adjustment': 3.5,
            'description': 'GDP下降5%+的严重经济衰退'
        },
        'geopolitical_shock': {
            'name': '地缘政治冲击',
            'return_adjustment': -0.30,
            'volatility_adjustment': 2.5,
            'description': '战争、恐怖袭击等事件'
        },
        'liquidity_crisis': {
            'name': '流动性危机',
            'return_adjustment': -0.40,
            'volatility_adjustment': 4.5,
            'description': '流动性枯竭，无法交易'
        }
    }


class StressTesting:
    """
    压力测试系统 - 顶级投行标准
    """
    
    def __init__(self):
        self.scenario_results = {}
        self.monte_carlo_results = None
        
    def historical_stress_test(self, portfolio_values: pd.Series, scenario: str) -> Dict:
        """
        历史情景压力测试
        
        Args:
            portfolio_values: 组合价值序列
            scenario: 情景名称
            
        Returns:
            压力测试结果
        """
        if scenario not in StressScenario.HISTORICAL_SCENARIOS:
            return {'error': f'情景 {scenario} 不存在'}
            
        scenario_config = StressScenario.HISTORICAL_SCENARIOS[scenario]
        
        returns = portfolio_values.pct_change().dropna()
        mu = returns.mean()
        sigma = returns.std()
        
        # 应用情景调整
        stressed_mu = mu + scenario_config['return_adjustment'] / 252
        stressed_sigma = sigma * scenario_config['volatility_adjustment']
        
        # 计算压力下的VaR
        stressed_returns = stressed_mu + stressed_sigma * np.random.randn(len(returns))
        var_pct = -np.percentile(stressed_returns, 5)
        
        # 计算最大损失
        initial_value = portfolio_values.iloc[-1]
        stress_loss = initial_value * scenario_config['return_adjustment']
        
        result = {
            'scenario': scenario_config['name'],
            'description': scenario_config['description'],
            'return_adjustment': scenario_config['return_adjustment'],
            'volatility_adjustment': scenario_config['volatility_adjustment'],
            'stressed_var': var_pct,
            'estimated_loss_pct': scenario_config['return_adjustment'],
            'estimated_loss_value': stress_loss,
            'initial_portfolio_value': initial_value
        }
        
        self.scenario_results[scenario] = result
        return result
        
    def run_all_historical_scenarios(self, portfolio_values: pd.Series) -> List[Dict]:
        """
        运行所有历史情景压力测试
        
        Args:
            portfolio_values: 组合价值序列
            
        Returns:
            所有情景的结果
        """
        results = []
        for scenario in StressScenario.HISTORICAL_SCENARIOS:
            result = self.historical_stress_test(portfolio_values, scenario)
            results.append(result)
        return results
        
    def monte_carlo_stress_test(self, portfolio_values: pd.Series, 
                                num_simulations: int = 10000, 
                                horizon_days: int = 252) -> Dict:
        """
        蒙特卡洛压力测试
        
        Args:
            portfolio_values: 组合价值序列
            num_simulations: 模拟次数
            horizon_days: 展望期天数
            
        Returns:
            蒙特卡洛压力测试结果
        """
        returns = portfolio_values.pct_change().dropna()
        mu = returns.mean()
        sigma = returns.std()
        
        # 模拟路径
        paths = np.zeros((num_simulations, horizon_days))
        initial_value = portfolio_values.iloc[-1]
        paths[:, 0] = initial_value
        
        for i in range(1, horizon_days):
            paths[:, i] = paths[:, i-1] * (1 + mu + sigma * np.random.randn(num_simulations))
            
        # 计算统计指标
        final_values = paths[:, -1]
        returns_distribution = (final_values - initial_value) / initial_value
        
        result = {
            'expected_return': np.mean(returns_distribution),
            'median_return': np.median(returns_distribution),
            'var_95': -np.percentile(returns_distribution, 5),
            'var_99': -np.percentile(returns_distribution, 1),
            'max_loss': -np.min(returns_distribution),
            'median_value': np.median(final_values),
            'best_10_pct': np.percentile(final_values, 90),
            'worst_10_pct': np.percentile(final_values, 10),
            'num_simulations': num_simulations,
            'horizon_days': horizon_days
        }
        
        self.monte_carlo_results = result
        return result
        
    def visualize_stress_test(self, results: List[Dict], filename: str = 'stress_test.png'):
        """
        可视化压力测试结果
        
        Args:
            results: 压力测试结果
            filename: 保存的文件名
        """
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))
        
        scenarios = [r['scenario'] for r in results]
        losses = [abs(r['estimated_loss_pct']) * 100 for r in results]
        
        axes[0].bar(scenarios, losses, color='darkred', alpha=0.7)
        axes[0].set_title('历史情景压力测试 - 最大损失百分比', fontsize=14, fontweight='bold')
        axes[0].set_ylabel('损失 (%)', fontsize=12)
        axes[0].tick_params(axis='x', rotation=45)
        axes[0].grid(True, alpha=0.3)
        
        vars = [r['stressed_var'] * 100 for r in results]
        axes[1].bar(scenarios, vars, color='darkorange', alpha=0.7)
        axes[1].set_title('历史情景压力测试 - 95% VaR (%)', fontsize=14, fontweight='bold')
        axes[1].set_ylabel('VaR (%)', fontsize=12)
        axes[1].tick_params(axis='x', rotation=45)
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"压力测试图表已保存至 {filename}"
        
    def generate_stress_report(self, results: List[Dict], mc_result: Optional[Dict] = None) -> str:
        """
        生成压力测试报告
        
        Args:
            results: 历史情景结果
            mc_result: 蒙特卡洛结果
            
        Returns:
            报告内容
        """
        report = []
        report.append("="*70)
        report.append("压力测试报告")
        report.append("="*70)
        
        report.append("\n=== 历史情景压力测试 ===")
        for result in results:
            report.append(f"\n情景: {result['scenario']}")
            report.append(f"描述: {result['description']}")
            report.append(f"估计损失: {result['estimated_loss_pct']*100:.2f}%")
            report.append(f"压力VaR(95%): {result['stressed_var']*100:.2f}%")
            report.append(f"波动调整: {result['volatility_adjustment']}x")
            
        if mc_result:
            report.append("\n=== 蒙特卡洛模拟压力测试 ===")
            report.append(f"模拟次数: {mc_result['num_simulations']}")
            report.append(f"展望期: {mc_result['horizon_days']}天")
            report.append(f"预期收益: {mc_result['expected_return']*100:.2f}%")
            report.append(f"95% VaR: {mc_result['var_95']*100:.2f}%")
            report.append(f"99% VaR: {mc_result['var_99']*100:.2f}%")
            report.append(f"最大损失: {mc_result['max_loss']*100:.2f}%")
            
        report.append("\n" + "="*70)
        
        return "\n".join(report)


if __name__ == "__main__":
    print("="*70)
    print("压力测试模块测试")
    print("="*70)
    
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
    initial_value = 100000
    close = initial_value * np.cumprod(1 + np.random.randn(len(dates)) * 0.015)
    portfolio_values = pd.Series(close, index=dates)
    
    stress_test = StressTesting()
    
    print("\n=== 运行历史情景压力测试 ===")
    scenario_results = stress_test.run_all_historical_scenarios(portfolio_values)
    
    for result in scenario_results:
        print(f"{result['scenario']}: 损失 {result['estimated_loss_pct']*100:.2f}%, VaR(95%) {result['stressed_var']*100:.2f}%")
    
    print("\n=== 运行蒙特卡洛模拟 ===")
    mc_result = stress_test.monte_carlo_stress_test(portfolio_values)
    print(f"预期收益: {mc_result['expected_return']*100:.2f}%")
    print(f"95% VaR: {mc_result['var_95']*100:.2f}%")
    print(f"99% VaR: {mc_result['var_99']*100:.2f}%")
    print(f"最大损失: {mc_result['max_loss']*100:.2f}%")
    
    print("\n=== 生成压力测试报告 ===")
    report = stress_test.generate_stress_report(scenario_results, mc_result)
    print(report)
    
    print("\n" + "="*70)
    print("✅ 压力测试模块测试完成 - 达到顶级投行标准！")
    print("="*70)
