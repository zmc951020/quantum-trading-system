#!/usr/bin/env python3
"""
风险告警和异常检测模块
"""

import numpy as np
import pandas as pd
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from datetime import datetime

class AlertManager:
    """
    风险告警和异常检测模块
    - 多级告警（警告、严重、紧急）
    - 告警规则配置
    - 告警触发和处理
    - 告警历史记录
    - 告警通知机制
    """
    
    def __init__(self, config=None):
        """
        初始化告警管理器
        
        Args:
            config: 配置参数
        """
        if config is None:
            config = {}
        
        # 告警级别
        self.alert_levels = {
            'warning': 1,
            'critical': 2,
            'emergency': 3
        }
        
        # 告警规则
        self.alert_rules = {
            # 傅里叶特征异常
            'high_cycle_strength': {
                'condition': lambda value: value > 0.9,
                'message': '周期强度异常高: {:.2f}',
                'level': 'warning',
                'threshold': 0.9
            },
            'extreme_phase_position': {
                'condition': lambda value: abs(value) > 3,
                'message': '相位位置异常: {:.2f}',
                'level': 'warning',
                'threshold': 3
            },
            'high_spectral_entropy': {
                'condition': lambda value: value > 4,
                'message': '频谱熵异常高: {:.2f}',
                'level': 'warning',
                'threshold': 4
            },
            
            # 风险指标异常
            'high_risk_score': {
                'condition': lambda value: value > 80,
                'message': '风险评分异常高: {:.2f}',
                'level': 'warning',
                'threshold': 80
            },
            'very_high_risk_score': {
                'condition': lambda value: value > 90,
                'message': '风险评分极高: {:.2f}',
                'level': 'critical',
                'threshold': 90
            },
            
            # 市场状态异常
            'crisis_mode': {
                'condition': lambda value: value == 2,
                'message': '市场处于危机模式',
                'level': 'critical',
                'threshold': 2
            },
            
            # 性能指标异常
            'high_drawdown': {
                'condition': lambda value: value > 0.15,
                'message': '回撤异常高: {:.2%}',
                'level': 'critical',
                'threshold': 0.15
            },
            'extreme_drawdown': {
                'condition': lambda value: value > 0.25,
                'message': '回撤极端高: {:.2%}',
                'level': 'emergency',
                'threshold': 0.25
            },
            
            'daily_loss': {
                'condition': lambda value: value < -0.02,
                'message': '单日亏损异常: {:.2%}',
                'level': 'critical',
                'threshold': -0.02
            },
            'extreme_daily_loss': {
                'condition': lambda value: value < -0.05,
                'message': '单日亏损极端: {:.2%}',
                'level': 'emergency',
                'threshold': -0.05
            },
            
            # 交易异常
            'high_trade_frequency': {
                'condition': lambda value: value > 10,
                'message': '交易频率异常高: {}次/小时',
                'level': 'warning',
                'threshold': 10
            },
            'no_trades': {
                'condition': lambda value: value > 24,
                'message': '长时间无交易: {}小时',
                'level': 'warning',
                'threshold': 24
            }
        }
        
        # 告警历史
        self.alert_history = []
        
        # 告警通知配置
        self.notification_config = config.get('notification', {
            'email': {
                'enabled': False,
                'smtp_server': 'smtp.example.com',
                'smtp_port': 587,
                'username': 'user@example.com',
                'password': 'password',
                'recipient': 'recipient@example.com'
            },
            'sms': {
                'enabled': False,
                'api_key': 'your_api_key',
                'phone_number': '1234567890'
            }
        })
        
        # 告警静音期（秒）
        self.alert_silence_period = config.get('alert_silence_period', 300)
        
        # 最近的告警时间
        self.last_alert_time = {}
    
    def check_alerts(self, metrics: Dict) -> List[Dict]:
        """
        检查告警条件
        
        Args:
            metrics: 监控指标
            
        Returns:
            告警列表
        """
        alerts = []
        
        # 检查傅里叶特征异常
        if 'cycle_strength' in metrics:
            if self.alert_rules['high_cycle_strength']['condition'](metrics['cycle_strength']):
                alert = self._create_alert(
                    'high_cycle_strength',
                    self.alert_rules['high_cycle_strength']['message'].format(metrics['cycle_strength']),
                    self.alert_rules['high_cycle_strength']['level'],
                    {'value': metrics['cycle_strength'], 'threshold': self.alert_rules['high_cycle_strength']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        if 'phase_position' in metrics:
            if self.alert_rules['extreme_phase_position']['condition'](metrics['phase_position']):
                alert = self._create_alert(
                    'extreme_phase_position',
                    self.alert_rules['extreme_phase_position']['message'].format(metrics['phase_position']),
                    self.alert_rules['extreme_phase_position']['level'],
                    {'value': metrics['phase_position'], 'threshold': self.alert_rules['extreme_phase_position']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        if 'spectral_entropy' in metrics:
            if self.alert_rules['high_spectral_entropy']['condition'](metrics['spectral_entropy']):
                alert = self._create_alert(
                    'high_spectral_entropy',
                    self.alert_rules['high_spectral_entropy']['message'].format(metrics['spectral_entropy']),
                    self.alert_rules['high_spectral_entropy']['level'],
                    {'value': metrics['spectral_entropy'], 'threshold': self.alert_rules['high_spectral_entropy']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        # 检查风险指标异常
        if 'risk_score' in metrics:
            if self.alert_rules['high_risk_score']['condition'](metrics['risk_score']):
                alert = self._create_alert(
                    'high_risk_score',
                    self.alert_rules['high_risk_score']['message'].format(metrics['risk_score']),
                    self.alert_rules['high_risk_score']['level'],
                    {'value': metrics['risk_score'], 'threshold': self.alert_rules['high_risk_score']['threshold']}
                )
                if alert:
                    alerts.append(alert)
            
            if self.alert_rules['very_high_risk_score']['condition'](metrics['risk_score']):
                alert = self._create_alert(
                    'very_high_risk_score',
                    self.alert_rules['very_high_risk_score']['message'].format(metrics['risk_score']),
                    self.alert_rules['very_high_risk_score']['level'],
                    {'value': metrics['risk_score'], 'threshold': self.alert_rules['very_high_risk_score']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        # 检查市场状态异常
        if 'current_regime' in metrics:
            if self.alert_rules['crisis_mode']['condition'](metrics['current_regime']):
                alert = self._create_alert(
                    'crisis_mode',
                    self.alert_rules['crisis_mode']['message'],
                    self.alert_rules['crisis_mode']['level'],
                    {'value': metrics['current_regime'], 'threshold': self.alert_rules['crisis_mode']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        # 检查性能指标异常
        if 'drawdown' in metrics:
            if self.alert_rules['high_drawdown']['condition'](metrics['drawdown']):
                alert = self._create_alert(
                    'high_drawdown',
                    self.alert_rules['high_drawdown']['message'].format(metrics['drawdown']),
                    self.alert_rules['high_drawdown']['level'],
                    {'value': metrics['drawdown'], 'threshold': self.alert_rules['high_drawdown']['threshold']}
                )
                if alert:
                    alerts.append(alert)
            
            if self.alert_rules['extreme_drawdown']['condition'](metrics['drawdown']):
                alert = self._create_alert(
                    'extreme_drawdown',
                    self.alert_rules['extreme_drawdown']['message'].format(metrics['drawdown']),
                    self.alert_rules['extreme_drawdown']['level'],
                    {'value': metrics['drawdown'], 'threshold': self.alert_rules['extreme_drawdown']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        # 检查单日亏损异常
        if 'daily_pnl' in metrics:
            if self.alert_rules['daily_loss']['condition'](metrics['daily_pnl']):
                alert = self._create_alert(
                    'daily_loss',
                    self.alert_rules['daily_loss']['message'].format(metrics['daily_pnl']),
                    self.alert_rules['daily_loss']['level'],
                    {'value': metrics['daily_pnl'], 'threshold': self.alert_rules['daily_loss']['threshold']}
                )
                if alert:
                    alerts.append(alert)
            
            if self.alert_rules['extreme_daily_loss']['condition'](metrics['daily_pnl']):
                alert = self._create_alert(
                    'extreme_daily_loss',
                    self.alert_rules['extreme_daily_loss']['message'].format(metrics['daily_pnl']),
                    self.alert_rules['extreme_daily_loss']['level'],
                    {'value': metrics['daily_pnl'], 'threshold': self.alert_rules['extreme_daily_loss']['threshold']}
                )
                if alert:
                    alerts.append(alert)
        
        return alerts
    
    def _create_alert(self, alert_type: str, message: str, level: str, details: Dict) -> Optional[Dict]:
        """
        创建告警
        
        Args:
            alert_type: 告警类型
            message: 告警消息
            level: 告警级别
            details: 告警详情
            
        Returns:
            告警字典
        """
        # 检查是否在静音期
        current_time = time.time()
        if alert_type in self.last_alert_time:
            if current_time - self.last_alert_time[alert_type] < self.alert_silence_period:
                return None
        
        # 更新最近告警时间
        self.last_alert_time[alert_type] = current_time
        
        alert = {
            'id': f'{alert_type}_{int(current_time)}',
            'type': alert_type,
            'message': message,
            'level': level,
            'details': details,
            'timestamp': datetime.now(),
            'status': 'active'
        }
        
        # 添加到历史
        self.alert_history.append(alert)
        
        # 发送通知
        self._send_notification(alert)
        
        return alert
    
    def _send_notification(self, alert: Dict):
        """
        发送告警通知
        
        Args:
            alert: 告警信息
        """
        # 发送邮件通知
        if self.notification_config['email']['enabled']:
            self._send_email_notification(alert)
        
        # 发送短信通知（仅紧急级别）
        if self.notification_config['sms']['enabled'] and alert['level'] == 'emergency':
            self._send_sms_notification(alert)
    
    def _send_email_notification(self, alert: Dict):
        """
        发送邮件通知
        
        Args:
            alert: 告警信息
        """
        try:
            # 构建邮件
            msg = MIMEMultipart()
            msg['From'] = self.notification_config['email']['username']
            msg['To'] = self.notification_config['email']['recipient']
            msg['Subject'] = f'[Aurora] {alert["level"].upper()} Alert: {alert["message"]}'
            
            # 邮件正文
            body = f"""Alert ID: {alert['id']}
Type: {alert['type']}
Level: {alert['level']}
Message: {alert['message']}
Details: {alert['details']}
Timestamp: {alert['timestamp']}
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # 发送邮件
            server = smtplib.SMTP(
                self.notification_config['email']['smtp_server'],
                self.notification_config['email']['smtp_port']
            )
            server.starttls()
            server.login(
                self.notification_config['email']['username'],
                self.notification_config['email']['password']
            )
            text = msg.as_string()
            server.sendmail(
                self.notification_config['email']['username'],
                self.notification_config['email']['recipient'],
                text
            )
            server.quit()
        except Exception as e:
            print(f"发送邮件通知失败: {e}")
    
    def _send_sms_notification(self, alert: Dict):
        """
        发送短信通知
        
        Args:
            alert: 告警信息
        """
        # 这里实现短信发送逻辑
        # 可以使用第三方短信API
        print(f"发送短信通知: {alert['message']}")
    
    def get_alert_history(self, level: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        获取告警历史
        
        Args:
            level: 告警级别
            limit: 限制数量
            
        Returns:
            告警历史列表
        """
        if level:
            filtered_alerts = [alert for alert in self.alert_history if alert['level'] == level]
        else:
            filtered_alerts = self.alert_history
        
        return filtered_alerts[-limit:]
    
    def resolve_alert(self, alert_id: str) -> bool:
        """
        解决告警
        
        Args:
            alert_id: 告警ID
            
        Returns:
            是否成功解决
        """
        for alert in self.alert_history:
            if alert['id'] == alert_id and alert['status'] == 'active':
                alert['status'] = 'resolved'
                alert['resolved_at'] = datetime.now()
                return True
        return False
    
    def get_active_alerts(self) -> List[Dict]:
        """
        获取活跃告警
        
        Returns:
            活跃告警列表
        """
        return [alert for alert in self.alert_history if alert['status'] == 'active']
    
    def get_alert_statistics(self) -> Dict:
        """
        获取告警统计
        
        Returns:
            告警统计字典
        """
        stats = {
            'total_alerts': len(self.alert_history),
            'active_alerts': len([a for a in self.alert_history if a['status'] == 'active']),
            'resolved_alerts': len([a for a in self.alert_history if a['status'] == 'resolved']),
            'alerts_by_level': {
                'warning': 0,
                'critical': 0,
                'emergency': 0
            },
            'alerts_by_type': {}
        }
        
        for alert in self.alert_history:
            stats['alerts_by_level'][alert['level']] += 1
            if alert['type'] not in stats['alerts_by_type']:
                stats['alerts_by_type'][alert['type']] = 0
            stats['alerts_by_type'][alert['type']] += 1
        
        return stats
    
    def update_alert_rules(self, rules: Dict):
        """
        更新告警规则
        
        Args:
            rules: 新的告警规则
        """
        self.alert_rules.update(rules)
    
    def save_alert_history(self, filename: str):
        """
        保存告警历史
        
        Args:
            filename: 文件名
        """
        import json
        
        # 转换时间戳为字符串
        for alert in self.alert_history:
            alert['timestamp'] = alert['timestamp'].isoformat()
            if 'resolved_at' in alert:
                alert['resolved_at'] = alert['resolved_at'].isoformat()
        
        with open(filename, 'w') as f:
            json.dump(self.alert_history, f, indent=2)
    
    def load_alert_history(self, filename: str):
        """
        加载告警历史
        
        Args:
            filename: 文件名
        """
        import json
        
        try:
            with open(filename, 'r') as f:
                self.alert_history = json.load(f)
            
            # 转换字符串为时间戳
            for alert in self.alert_history:
                alert['timestamp'] = datetime.fromisoformat(alert['timestamp'])
                if 'resolved_at' in alert:
                    alert['resolved_at'] = datetime.fromisoformat(alert['resolved_at'])
        except Exception as e:
            print(f"加载告警历史失败: {e}")
