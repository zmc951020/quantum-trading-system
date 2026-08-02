#!/usr/bin/env python3
"""
盈亏学习模块 (PnL Learner)
============================
从实盘交易结果中学习，更新智能体权重，形成正反馈闭环。

核心逻辑：
  1. 收集实盘盈亏数据
  2. 提取交易特征（市场环境、持仓时长、波动率等）
  3. 按特征分组，计算各智能体在不同场景下的准确率
  4. 更新智能体权重（盈利场景提权，亏损场景降权）
  5. 定期（每周）输出权重更新报告
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PnLLearner:
    """盈亏学习器
    
    从实盘交易结果中学习，优化智能体权重分配。
    """
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(PROJECT_ROOT, 'data')
        self._data_dir = data_dir
        self._trades_file = os.path.join(data_dir, 'live_trades', 'trades.json')
        self._weights_file = os.path.join(data_dir, 'agent_weights.json')
        self._learning_file = os.path.join(data_dir, 'pnl_learning.json')
        os.makedirs(os.path.dirname(self._trades_file), exist_ok=True)
    
    def record_trade(self, trade: Dict[str, Any]):
        """记录一笔实盘交易
        
        Args:
            trade: {
                symbol, strategy_name, entry_time, exit_time,
                entry_price, exit_price, shares, pnl, pnl_pct,
                agent_votes: [{agent_name, vote, confidence}],
                market_regime: str,  # 'bull'/'bear'/'range'
                volatility: float,
            }
        """
        trades = self._load_trades()
        trade['recorded_at'] = datetime.now().isoformat()
        trades.append(trade)
        
        # 保留最近 500 笔
        if len(trades) > 500:
            trades = trades[-500:]
        
        try:
            with open(self._trades_file, 'w', encoding='utf-8') as f:
                json.dump(trades, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[PnL] 记录交易失败: {e}")
    
    def _load_trades(self) -> List[Dict]:
        try:
            if os.path.exists(self._trades_file):
                with open(self._trades_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def _load_weights(self) -> Dict[str, float]:
        try:
            if os.path.exists(self._weights_file):
                with open(self._weights_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_weights(self, weights: Dict[str, float]):
        try:
            with open(self._weights_file, 'w', encoding='utf-8') as f:
                json.dump(weights, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[PnL] 保存权重失败: {e}")
    
    def learn_from_trades(self, lookback_days: int = 90) -> Dict[str, Any]:
        """从历史交易中学习并更新智能体权重
        
        Args:
            lookback_days: 回溯天数
            
        Returns:
            dict: 学习报告
        """
        trades = self._load_trades()
        if not trades:
            return {'success': False, 'message': '无交易数据', 'changes': {}}
        
        cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        recent_trades = [t for t in trades if t.get('recorded_at', '') >= cutoff]
        
        if not recent_trades:
            return {'success': False, 'message': f'近{lookback_days}天无交易', 'changes': {}}
        
        # 按场景分组计算各智能体准确率
        agent_stats = defaultdict(lambda: {'correct': 0, 'total': 0, 'by_regime': {}})
        
        for trade in recent_trades:
            is_profitable = trade.get('pnl', 0) > 0
            regime = trade.get('market_regime', 'unknown')
            agent_votes = trade.get('agent_votes', [])
            
            for av in agent_votes:
                agent_name = av.get('agent_name', '')
                vote = av.get('vote', '')
                
                if not agent_name:
                    continue
                
                agent_stats[agent_name]['total'] += 1
                
                # 判断投票是否正确
                was_correct = False
                if is_profitable and '买入' in str(vote):
                    was_correct = True
                elif not is_profitable and ('卖出' in str(vote) or '观望' in str(vote)):
                    was_correct = True
                
                if was_correct:
                    agent_stats[agent_name]['correct'] += 1
                
                # 按市场环境统计
                if regime not in agent_stats[agent_name]['by_regime']:
                    agent_stats[agent_name]['by_regime'][regime] = {'correct': 0, 'total': 0}
                agent_stats[agent_name]['by_regime'][regime]['total'] += 1
                if was_correct:
                    agent_stats[agent_name]['by_regime'][regime]['correct'] += 1
        
        # 计算新权重
        current_weights = self._load_weights()
        new_weights = {}
        changes = {}
        
        for agent_name, stats in agent_stats.items():
            if stats['total'] < 3:  # 最少3笔交易才更新
                new_weights[agent_name] = current_weights.get(agent_name, 1.0)
                continue
            
            accuracy = stats['correct'] / stats['total']
            old_weight = current_weights.get(agent_name, 1.0)
            
            # 准确率映射到权重 [0.5, 2.0]
            # 50% 准确率 → 权重 1.0, 75% → 1.5, 25% → 0.75
            new_weight = 0.5 + accuracy * 2.0
            new_weight = round(max(0.3, min(2.5, new_weight)), 3)
            
            # 指数移动平均平滑
            lr = 0.3
            smoothed = old_weight * (1 - lr) + new_weight * lr
            new_weights[agent_name] = round(smoothed, 3)
            
            changes[agent_name] = {
                'old_weight': old_weight,
                'new_weight': round(smoothed, 3),
                'delta': round(smoothed - old_weight, 3),
                'accuracy': round(accuracy, 3),
                'total_trades': stats['total'],
                'by_regime': {
                    r: {
                        'accuracy': round(s['correct'] / max(s['total'], 1), 3),
                        'trades': s['total'],
                    }
                    for r, s in stats['by_regime'].items()
                },
            }
        
        # 保存权重
        self._save_weights(new_weights)
        
        # 保存学习报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'lookback_days': lookback_days,
            'total_trades_analyzed': len(recent_trades),
            'profitable_trades': sum(1 for t in recent_trades if t.get('pnl', 0) > 0),
            'agents_updated': len(changes),
            'changes': changes,
            'summary': self._generate_summary(changes),
        }
        
        try:
            with open(self._learning_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
        logger.info(f"[PnL] 学习完成: {len(recent_trades)} 笔交易, "
                   f"更新 {len(changes)} 个智能体权重")
        
        return {'success': True, 'report': report}
    
    def _generate_summary(self, changes: Dict) -> Dict:
        """生成学习摘要"""
        if not changes:
            return {'message': '无变化'}
        
        upgraded = [name for name, c in changes.items() if c['delta'] > 0.01]
        downgraded = [name for name, c in changes.items() if c['delta'] < -0.01]
        top_agents = sorted(changes.items(), key=lambda x: -x[1]['accuracy'])[:3]
        
        return {
            'upgraded': len(upgraded),
            'downgraded': len(downgraded),
            'upgraded_names': upgraded[:5],
            'downgraded_names': downgraded[:5],
            'top_agents': [{'name': n, 'accuracy': c['accuracy']} for n, c in top_agents],
            'advice': self._generate_advice(changes),
        }
    
    def _generate_advice(self, changes: Dict) -> str:
        """生成建议"""
        if not changes:
            return "暂无足够数据生成建议"
        
        avg_accuracy = sum(c['accuracy'] for c in changes.values()) / len(changes)
        if avg_accuracy > 0.65:
            return "整体智能体准确率较高，建议保持当前配置"
        elif avg_accuracy > 0.50:
            return "智能体准确率中等，建议关注低准确率智能体的特征偏好"
        else:
            return "智能体整体准确率偏低，建议审查市场环境和数据质量"
    
    def get_learning_report(self) -> Dict[str, Any]:
        """获取最近的学习报告"""
        try:
            if os.path.exists(self._learning_file):
                with open(self._learning_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {'message': '无学习报告'}
    
    def get_agent_weights(self) -> Dict[str, float]:
        """获取当前智能体权重"""
        return self._load_weights()


# 全局单例
_pnl_learner: Optional[PnLLearner] = None

def get_pnl_learner() -> PnLLearner:
    global _pnl_learner
    if _pnl_learner is None:
        _pnl_learner = PnLLearner()
    return _pnl_learner