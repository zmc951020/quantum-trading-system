#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 主入口
"""
from typing import List
import random
from stock_pool import (
    Stock, Strategy, SmartStockFilter, StrategyStockMatcher,
    PreTradingSimulator, ExpertAgentSystem, VotingSystem,
    CompositeScorer, PoolManager
)


class StockPoolSystem:
    """股票池智能管理系统主类"""
    
    def __init__(self):
        self.filter = SmartStockFilter()
        self.matcher = StrategyStockMatcher()
        self.simulator = PreTradingSimulator()
        self.expert_system = ExpertAgentSystem()
        self.voting_system = VotingSystem()
        self.scorer = CompositeScorer()
        self.pool_manager = PoolManager()
    
    def generate_sample_stocks(self, count: int = 10) -> List[Stock]:
        """生成示例股票数据"""
        stocks = []
        names = ['贵州茅台', '比亚迪', '宁德时代', '招商银行', '平安银行',
                 '格力电器', '美的集团', '五粮液', '泸州老窖', '长城汽车']
        codes = ['600519', '002594', '300750', '600036', '000001',
                 '000651', '000333', '000858', '000568', '601633']
        
        for i in range(min(count, len(names))):
            stock = Stock(
                code=codes[i],
                name=names[i],
                market='SH' if codes[i].startswith('6') else 'SZ',
                price=round(10 + random.random() * 200, 2),
                pe=round(10 + random.random() * 40, 2),
                pb=round(1 + random.random() * 10, 2),
                roe=round(random.random() * 0.3, 4),
                volume=round(50000000 + random.random() * 500000000, 0),
                turnover_rate=round(random.random() * 10, 2),
                volatility=round(0.01 + random.random() * 0.15, 4),
                trend_strength=round(random.random(), 4),
                liquidity_score=round(60 + random.random() * 40, 2),
                quality_score=round(50 + random.random() * 50, 2),
                sector='消费' if i < 4 else '科技',
                industry='白酒' if i in [0, 7, 8] else '汽车' if i in [1, 9] else '金融'
            )
            stocks.append(stock)
        
        return stocks
    
    def run_full_pipeline(self, stocks: List[Stock]) -> dict:
        """运行完整的股票筛选和评估流程"""
        results = {
            'filtered': [],
            'matched': [],
            'simulated': [],
            'evaluated': [],
            'voting': [],
            'final': []
        }
        
        # 1. 智能筛选
        filtered = self.filter.filter_with_scores(stocks)
        results['filtered'] = filtered
        
        # 获取通过筛选的股票
        passed_stocks = [f['stock'] for f in filtered if f['passed']]
        
        # 2. 策略匹配
        matched = self.matcher.match_all(passed_stocks)
        results['matched'] = matched
        
        # 3. 预实盘模拟
        for match_result in matched:
            stock = match_result['stock']
            for match in match_result['matches'][:2]:  # 只模拟前两个最佳匹配
                strategy = match['strategy']
                sim_result = self.simulator.run_simulation(stock, strategy)
                results['simulated'].append({
                    'stock': stock,
                    'strategy': strategy,
                    'simulation': sim_result
                })
        
        # 4. 专家评估
        for sim_result in results['simulated']:
            evaluation = self.expert_system.evaluate(
                sim_result['stock'],
                sim_result['strategy']
            )
            results['evaluated'].append({
                'stock': sim_result['stock'],
                'strategy': sim_result['strategy'],
                'simulation': sim_result['simulation'],
                'evaluation': evaluation
            })
        
        # 5. 综合评分和投票
        for eval_result in results['evaluated']:
            # 将模拟评分归一化到0-100分
            sim_score = min(100, eval_result['simulation'].score * 2.5)  # 0-40分 -> 0-100分
            
            evaluations = {
                'simulation': {'score': sim_score},
                'technical': {'score': eval_result['stock'].quality_score},
                'risk': {'score': eval_result['evaluation']['evaluations']['risk_assessor']['score']},
                'expert': {'score': eval_result['evaluation']['composite_score']},
                'compliance': {'score': 100, 'passed': eval_result['evaluation']['compliance_passed']}
            }
            
            composite = self.scorer.calculate(evaluations)
            
            if composite['passed']:
                # 创建投票提案
                proposal = self.voting_system.create_proposal(
                    eval_result['stock'],
                    eval_result['strategy']
                )
                
                # 模拟投票
                for voter in ['策略分析师', '风控管理员', '交易员']:
                    decision = 'yes' if composite['score'] >= 70 else 'no'
                    self.voting_system.vote(
                        proposal.proposal_id,
                        voter,
                        decision,
                        f"综合评分: {composite['score']}"
                    )
                
                results['voting'].append({
                    'proposal': proposal,
                    'composite': composite
                })
                
                # 添加到实盘池
                self.pool_manager.add_to_pool(eval_result['stock'], 'trading')
                results['final'].append({
                    'stock': eval_result['stock'],
                    'strategy': eval_result['strategy'],
                    'score': composite['score'],
                    'grade': composite['grade']
                })
        
        return results


def main():
    """主函数"""
    print("=" * 60)
    print("股票池智能管理系统 v1.0")
    print("=" * 60)
    
    # 创建系统
    system = StockPoolSystem()
    
    # 生成示例股票
    print("\n1. 生成示例股票...")
    stocks = system.generate_sample_stocks(10)
    print(f"   生成了 {len(stocks)} 只股票")
    
    # 运行完整流程
    print("\n2. 运行完整筛选评估流程...")
    results = system.run_full_pipeline(stocks)
    
    # 输出结果
    print("\n3. 筛选结果:")
    print(f"   筛选前: {len(stocks)} 只")
    print(f"   筛选通过: {len(results['filtered'])} 只")
    
    print("\n4. 模拟测试结果:")
    for sim in results['simulated']:
        stock = sim['stock']
        strategy = sim['strategy']
        result = sim['simulation']
        print(f"   {stock.code} {stock.name} + {strategy.name}:")
        print(f"      收益率: {result.total_return}%, 夏普: {result.sharpe_ratio}, 回撤: {result.max_drawdown}%")
    
    print("\n5. 最终入选实盘池的股票:")
    for final in results['final']:
        print(f"   [{final['grade']}] {final['stock'].code} {final['stock'].name}")
        print(f"      策略: {final['strategy'].name}")
        print(f"      评分: {final['score']}")
    
    # 输出池摘要
    summary = system.pool_manager.get_pool_summary()
    print("\n6. 股票池摘要:")
    for pool_type, info in summary.items():
        print(f"   {pool_type}: {info['count']} 只股票")
    
    print("\n" + "=" * 60)
    print("流程执行完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()