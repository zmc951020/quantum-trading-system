#!/usr/bin/env python3
"""
傅里叶策略特有指标监控
"""

import numpy as np
import pandas as pd
import time
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

class FourierMonitor:
    """
    傅里叶策略特有指标监控
    - 周期强度监控
    - 相位位置监控
    - 市场状态监控
    - 风险指标监控
    - 性能指标监控
    """
    
    def __init__(self, config=None):
        """
        初始化监控模块
        
        Args:
            config: 配置参数
        """
        if config is None:
            config = {}
        
        # 监控参数
        self.history_length = config.get('history_length', 1000)  # 历史数据长度
        self.update_interval = config.get('update_interval', 1)  # 更新间隔（秒）
        
        # 数据存储
        self.fourier_metrics_history = []
        self.regime_history = []
        self.risk_metrics_history = []
        self.performance_history = []
        self.timestamps = []
        
        # 最近的指标值
        self.latest_metrics = {
            'cycle_strength': 0,
            'phase_position': 0,
            'dominant_periods': [],
            'spectral_entropy': 0,
            'trend_confidence': 0,
            'current_regime': 0,
            'risk_score': 0,
            'portfolio_value': 0,
            'drawdown': 0
        }
    
    def update_metrics(self, fourier_features: Dict, regime: int, risk_score: float, portfolio_value: float, drawdown: float):
        """
        更新监控指标
        
        Args:
            fourier_features: 傅里叶特征
            regime: 市场状态
            risk_score: 风险评分
            portfolio_value: 组合价值
            drawdown: 回撤
        """
        timestamp = datetime.now()
        
        # 更新傅里叶指标历史
        fourier_metrics = {
            'cycle_strength': fourier_features.get('cycle_strength', 0),
            'phase_position': fourier_features.get('phase_position', 0),
            'dominant_periods': fourier_features.get('dominant_periods', []),
            'spectral_entropy': fourier_features.get('spectral_entropy', 0),
            'trend_confidence': fourier_features.get('trend_confidence', 0)
        }
        
        # 更新市场状态历史
        regime_info = {
            'regime': regime,
            'regime_label': self._get_regime_label(regime)
        }
        
        # 更新风险指标历史
        risk_metrics = {
            'risk_score': risk_score,
            'portfolio_value': portfolio_value,
            'drawdown': drawdown
        }
        
        # 存储历史数据
        self.fourier_metrics_history.append(fourier_metrics)
        self.regime_history.append(regime_info)
        self.risk_metrics_history.append(risk_metrics)
        self.timestamps.append(timestamp)
        
        # 保持历史数据长度
        if len(self.fourier_metrics_history) > self.history_length:
            self.fourier_metrics_history.pop(0)
            self.regime_history.pop(0)
            self.risk_metrics_history.pop(0)
            self.timestamps.pop(0)
        
        # 更新最新指标
        self.latest_metrics.update(fourier_metrics)
        self.latest_metrics['current_regime'] = regime
        self.latest_metrics['risk_score'] = risk_score
        self.latest_metrics['portfolio_value'] = portfolio_value
        self.latest_metrics['drawdown'] = drawdown
    
    def _get_regime_label(self, regime: int) -> str:
        """
        获取市场状态标签
        
        Args:
            regime: 市场状态
            
        Returns:
            市场状态标签
        """
        regime_labels = {
            0: 'TRENDING_LOW_VOL',
            1: 'CHOPPY_HIGH_VOL',
            2: 'CRISIS_MODE'
        }
        return regime_labels.get(regime, 'UNKNOWN')
    
    def get_latest_metrics(self) -> Dict:
        """
        获取最新的监控指标
        
        Returns:
            最新的监控指标
        """
        return self.latest_metrics
    
    def get_history(self, metric: str, window: int = None) -> pd.DataFrame:
        """
        获取指定指标的历史数据
        
        Args:
            metric: 指标名称
            window: 时间窗口
            
        Returns:
            历史数据DataFrame
        """
        if window is None:
            window = len(self.timestamps)
        
        window = min(window, len(self.timestamps))
        
        if metric in ['cycle_strength', 'phase_position', 'spectral_entropy', 'trend_confidence']:
            data = [item[metric] for item in self.fourier_metrics_history[-window:]]
        elif metric == 'current_regime':
            data = [item['regime'] for item in self.regime_history[-window:]]
        elif metric in ['risk_score', 'portfolio_value', 'drawdown']:
            data = [item[metric] for item in self.risk_metrics_history[-window:]]
        else:
            return pd.DataFrame()
        
        return pd.DataFrame({
            'timestamp': self.timestamps[-window:],
            metric: data
        })
    
    def generate_report(self) -> Dict:
        """
        生成监控报告
        
        Returns:
            监控报告
        """
        if not self.timestamps:
            return {}
        
        # 计算统计指标
        cycle_strength_df = self.get_history('cycle_strength')
        phase_position_df = self.get_history('phase_position')
        risk_score_df = self.get_history('risk_score')
        portfolio_df = self.get_history('portfolio_value')
        
        report = {
            'timestamp': datetime.now(),
            'latest_metrics': self.latest_metrics,
            'statistics': {
                'cycle_strength': {
                    'mean': cycle_strength_df['cycle_strength'].mean() if not cycle_strength_df.empty else 0,
                    'std': cycle_strength_df['cycle_strength'].std() if not cycle_strength_df.empty else 0,
                    'max': cycle_strength_df['cycle_strength'].max() if not cycle_strength_df.empty else 0,
                    'min': cycle_strength_df['cycle_strength'].min() if not cycle_strength_df.empty else 0
                },
                'phase_position': {
                    'mean': phase_position_df['phase_position'].mean() if not phase_position_df.empty else 0,
                    'std': phase_position_df['phase_position'].std() if not phase_position_df.empty else 0,
                    'max': phase_position_df['phase_position'].max() if not phase_position_df.empty else 0,
                    'min': phase_position_df['phase_position'].min() if not phase_position_df.empty else 0
                },
                'risk_score': {
                    'mean': risk_score_df['risk_score'].mean() if not risk_score_df.empty else 0,
                    'std': risk_score_df['risk_score'].std() if not risk_score_df.empty else 0,
                    'max': risk_score_df['risk_score'].max() if not risk_score_df.empty else 0,
                    'min': risk_score_df['risk_score'].min() if not risk_score_df.empty else 0
                },
                'portfolio_value': {
                    'mean': portfolio_df['portfolio_value'].mean() if not portfolio_df.empty else 0,
                    'std': portfolio_df['portfolio_value'].std() if not portfolio_df.empty else 0,
                    'max': portfolio_df['portfolio_value'].max() if not portfolio_df.empty else 0,
                    'min': portfolio_df['portfolio_value'].min() if not portfolio_df.empty else 0
                }
            },
            'regime_distribution': self._calculate_regime_distribution()
        }
        
        return report
    
    def _calculate_regime_distribution(self) -> Dict:
        """
        计算市场状态分布
        
        Returns:
            市场状态分布
        """
        if not self.regime_history:
            return {}
        
        regime_counts = {0: 0, 1: 0, 2: 0}
        for item in self.regime_history:
            regime = item['regime']
            if regime in regime_counts:
                regime_counts[regime] += 1
        
        total = sum(regime_counts.values())
        distribution = {}
        for regime, count in regime_counts.items():
            distribution[self._get_regime_label(regime)] = count / total if total > 0 else 0
        
        return distribution
    
    def plot_metrics(self, metrics: List[str], window: int = 100):
        """
        绘制监控指标
        
        Args:
            metrics: 要绘制的指标列表
            window: 时间窗口
        """
        if not self.timestamps:
            return
        
        window = min(window, len(self.timestamps))
        
        fig, axes = plt.subplots(len(metrics), 1, figsize=(12, 3 * len(metrics)))
        if len(metrics) == 1:
            axes = [axes]
        
        for i, metric in enumerate(metrics):
            df = self.get_history(metric, window)
            if df.empty:
                continue
            
            ax = axes[i]
            ax.plot(df['timestamp'], df[metric])
            ax.set_title(metric.replace('_', ' ').title())
            ax.set_xlabel('Time')
            ax.set_ylabel(metric)
            ax.grid(True)
            
            # 格式化时间轴
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            fig.autofmt_xdate()
        
        plt.tight_layout()
        plt.show()
    
    def check_anomalies(self) -> List[Dict]:
        """
        检查异常情况
        
        Returns:
            异常列表
        """
        anomalies = []
        
        # 检查周期强度异常
        if self.latest_metrics['cycle_strength'] > 0.9:
            anomalies.append({
                'type': 'high_cycle_strength',
                'message': f'周期强度异常高: {self.latest_metrics["cycle_strength"]:.2f}',
                'severity': 'warning',
                'timestamp': datetime.now()
            })
        
        # 检查相位位置异常
        if abs(self.latest_metrics['phase_position']) > 3:
            anomalies.append({
                'type': 'extreme_phase_position',
                'message': f'相位位置异常: {self.latest_metrics["phase_position"]:.2f}',
                'severity': 'warning',
                'timestamp': datetime.now()
            })
        
        # 检查风险评分异常
        if self.latest_metrics['risk_score'] > 80:
            anomalies.append({
                'type': 'high_risk_score',
                'message': f'风险评分异常高: {self.latest_metrics["risk_score"]:.2f}',
                'severity': 'warning',
                'timestamp': datetime.now()
            })
        
        # 检查市场状态异常
        if self.latest_metrics['current_regime'] == 2:
            anomalies.append({
                'type': 'crisis_mode',
                'message': '市场处于危机模式',
                'severity': 'critical',
                'timestamp': datetime.now()
            })
        
        # 检查回撤异常
        if self.latest_metrics['drawdown'] > 0.15:
            anomalies.append({
                'type': 'high_drawdown',
                'message': f'回撤异常高: {self.latest_metrics["drawdown"]:.2%}',
                'severity': 'critical',
                'timestamp': datetime.now()
            })
        
        return anomalies
    
    def save_history(self, filename: str):
        """
        保存历史数据
        
        Args:
            filename: 文件名
        """
        # 创建DataFrame
        data = []
        for i, timestamp in enumerate(self.timestamps):
            row = {
                'timestamp': timestamp,
                'cycle_strength': self.fourier_metrics_history[i]['cycle_strength'],
                'phase_position': self.fourier_metrics_history[i]['phase_position'],
                'spectral_entropy': self.fourier_metrics_history[i]['spectral_entropy'],
                'trend_confidence': self.fourier_metrics_history[i]['trend_confidence'],
                'regime': self.regime_history[i]['regime'],
                'regime_label': self.regime_history[i]['regime_label'],
                'risk_score': self.risk_metrics_history[i]['risk_score'],
                'portfolio_value': self.risk_metrics_history[i]['portfolio_value'],
                'drawdown': self.risk_metrics_history[i]['drawdown']
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)
    
    def load_history(self, filename: str):
        """
        加载历史数据
        
        Args:
            filename: 文件名
        """
        try:
            df = pd.read_csv(filename)
            
            # 清空现有数据
            self.fourier_metrics_history = []
            self.regime_history = []
            self.risk_metrics_history = []
            self.timestamps = []
            
            # 加载数据
            for _, row in df.iterrows():
                timestamp = pd.to_datetime(row['timestamp'])
                
                fourier_metrics = {
                    'cycle_strength': row['cycle_strength'],
                    'phase_position': row['phase_position'],
                    'dominant_periods': [],  # 从CSV加载时不包含主导周期
                    'spectral_entropy': row['spectral_entropy'],
                    'trend_confidence': row['trend_confidence']
                }
                
                regime_info = {
                    'regime': row['regime'],
                    'regime_label': row['regime_label']
                }
                
                risk_metrics = {
                    'risk_score': row['risk_score'],
                    'portfolio_value': row['portfolio_value'],
                    'drawdown': row['drawdown']
                }
                
                self.fourier_metrics_history.append(fourier_metrics)
                self.regime_history.append(regime_info)
                self.risk_metrics_history.append(risk_metrics)
                self.timestamps.append(timestamp)
        except Exception as e:
            print(f"加载历史数据失败: {e}")
