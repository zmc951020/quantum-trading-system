#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源安全风控模块
集成到现有五层风控系统，保护数据源安全
"""

import time
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque

class DataSourceRiskControl:
    """
    数据源安全风控模块
    在现有五层风控系统基础上，添加数据源保护层
    """

    def __init__(self,
                 max_price_change_pct: float = 0.20,
                 max_volume_change_pct: float = 5.0,
                 min_data_sources: int = 2,
                 data_staleness_seconds: int = 300,
                 cross_validation_threshold: float = 0.01):
        """
        初始化数据源风控模块

        Args:
            max_price_change_pct: 单次价格最大变化百分比（20%）
            max_volume_change_pct: 成交量最大变化倍数（5倍）
            min_data_sources: 最小可用数据源数量
            data_staleness_seconds: 数据过期时间（秒）
            cross_validation_threshold: 交叉验证阈值（1%差异）
        """
        # 价格验证参数
        self.max_price_change_pct = max_price_change_pct
        self.max_volume_change_pct = max_volume_change_pct

        # 数据源验证参数
        self.min_data_sources = min_data_sources
        self.data_staleness_seconds = data_staleness_seconds
        self.cross_validation_threshold = cross_validation_threshold

        # 数据源状态跟踪
        self.data_source_status = {}  # source_name -> {last_update, is_healthy, consecutive_failures}
        self.price_history = deque(maxlen=100)  # 历史价格，用于验证
        self.last_valid_price = None

        # 告警记录
        self.alerts = []

        # 统计数据
        self.stats = {
            'total_checks': 0,
            'failed_checks': 0,
            'alerts_triggered': 0,
            'data_source_failures': {}
        }

        print("[DataSourceRiskControl] 数据源风控模块初始化完成")
        print(f"   最大价格变化: {max_price_change_pct*100}%")
        print(f"   交叉验证阈值: {cross_validation_threshold*100}%")
        print(f"   数据过期时间: {data_staleness_seconds}秒")

    def validate_realtime_data(self, data: Dict, source_name: str = 'unknown') -> Tuple[bool, str]:
        """
        验证实时数据的有效性

        Args:
            data: 实时数据字典 {'symbol', 'price', 'volume', 'timestamp', ...}
            source_name: 数据源名称

        Returns:
            (is_valid, message)
        """
        self.stats['total_checks'] += 1

        # 1. 检查必要字段
        if not data or 'price' not in data:
            return self._record_failure(source_name, "缺少价格字段")

        price = data.get('price', 0)
        volume = data.get('volume', 0)
        timestamp = data.get('timestamp', datetime.now())

        # 2. 检查价格是否有效
        if price <= 0:
            return self._record_failure(source_name, f"无效价格: {price}")

        # 3. 检查价格是否异常波动
        if self.last_valid_price is not None:
            price_change = abs(price - self.last_valid_price) / self.last_valid_price

            if price_change > self.max_price_change_pct:
                msg = f"价格异常波动: {price_change*100:.2f}% (阈值: {self.max_price_change_pct*100}%)"
                self._trigger_alert(source_name, 'PRICE_ANOMALY', msg, {
                    'price': price,
                    'last_price': self.last_valid_price,
                    'change_pct': price_change
                })
                return False, msg

        # 4. 检查时间戳
        if isinstance(timestamp, datetime):
            age = (datetime.now() - timestamp).total_seconds()
            if age > self.data_staleness_seconds:
                msg = f"数据过期: {age:.0f}秒前 (阈值: {self.data_staleness_seconds}秒)"
                self._trigger_alert(source_name, 'STALE_DATA', msg, {'age_seconds': age})
                return False, msg

        # 5. 更新状态
        self._record_success(source_name)
        self.last_valid_price = price
        self.price_history.append({'price': price, 'volume': volume, 'timestamp': timestamp, 'source': source_name})

        return True, "数据有效"

    def validate_historical_data(self, df: pd.DataFrame, source_name: str = 'unknown') -> Tuple[bool, str]:
        """
        验证历史数据的有效性

        Args:
            df: 历史数据DataFrame
            source_name: 数据源名称

        Returns:
            (is_valid, message)
        """
        if df is None or df.empty:
            return self._record_failure(source_name, "历史数据为空")

        # 1. 检查必要列
        required_cols = ['close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return self._record_failure(source_name, f"缺少必要列: {missing_cols}")

        # 2. 检查价格范围
        if (df['close'] <= 0).any():
            return self._record_failure(source_name, "包含无效价格")

        # 3. 检查价格连续性（不应该有超过50%的跳空）
        if len(df) > 1:
            returns = df['close'].pct_change().dropna()
            extreme_returns = returns[abs(returns) > self.max_price_change_pct]

            if len(extreme_returns) > len(returns) * 0.1:  # 超过10%的极端收益
                msg = f"历史数据包含过多极端价格变动: {len(extreme_returns)}/{len(returns)}"
                self._trigger_alert(source_name, 'HISTORICAL_ANOMALY', msg, {
                    'extreme_count': len(extreme_returns),
                    'total_count': len(returns)
                })
                return False, msg

        # 4. 检查数据完整性
        expected_rows = len(df)
        actual_rows = df.dropna().shape[0]
        if actual_rows < expected_rows * 0.95:  # 允许5%的缺失
            msg = f"数据完整性不足: {actual_rows}/{expected_rows}"
            self._trigger_alert(source_name, 'INCOMPLETE_DATA', msg)
            return False, msg

        self._record_success(source_name)
        return True, "历史数据有效"

    def cross_validate_sources(self, data_dict: Dict[str, Dict]) -> Tuple[bool, str, Dict]:
        """
        交叉验证多个数据源的数据

        Args:
            data_dict: 数据源名称 -> 数据字典

        Returns:
            (is_valid, message, details)
        """
        if len(data_dict) < 2:
            return True, "数据源不足，跳过交叉验证", {}

        sources = list(data_dict.keys())
        prices = [data_dict[s].get('price', 0) for s in sources if data_dict[s].get('price', 0) > 0]

        if len(prices) < 2:
            return True, "有效价格不足，跳过交叉验证", {}

        # 计算价格差异
        max_price = max(prices)
        min_price = min(prices)
        avg_price = np.mean(prices)
        price_diff_pct = (max_price - min_price) / avg_price if avg_price > 0 else 0

        details = {
            'sources': sources,
            'prices': prices,
            'max_price': max_price,
            'min_price': min_price,
            'avg_price': avg_price,
            'diff_pct': price_diff_pct
        }

        if price_diff_pct > self.cross_validation_threshold:
            msg = f"数据源价格差异过大: {price_diff_pct*100:.2f}%"
            self._trigger_alert('CROSS_VALIDATION', 'SOURCE_DISCREPANCY', msg, details)
            return False, msg, details

        return True, "交叉验证通过", details

    def check_data_source_health(self) -> Dict:
        """
        检查所有数据源健康状态

        Returns:
            健康状态字典
        """
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'overall_status': 'healthy',
            'recommendations': []
        }

        for source_name, status in self.data_source_status.items():
            age = (datetime.now() - status['last_update']).total_seconds() if status.get('last_update') else float('inf')

            source_health = {
                'is_healthy': status.get('is_healthy', False),
                'last_update': status.get('last_update').isoformat() if status.get('last_update') else None,
                'consecutive_failures': status.get('consecutive_failures', 0),
                'data_age_seconds': age
            }

            # 判断健康状态
            if not status.get('is_healthy', False):
                source_health['status'] = 'unhealthy'
                health_report['overall_status'] = 'degraded'
            elif age > self.data_staleness_seconds:
                source_health['status'] = 'stale'
                health_report['overall_status'] = 'degraded'
            else:
                source_health['status'] = 'healthy'

            health_report['sources'][source_name] = source_health

        # 生成建议
        healthy_count = sum(1 for s in health_report['sources'].values() if s['status'] == 'healthy')
        if healthy_count < self.min_data_sources:
            health_report['recommendations'].append(f"可用数据源不足: {healthy_count}/{self.min_data_sources}")
            health_report['overall_status'] = 'critical'

        return health_report

    def get_trusted_price(self, data_dict: Dict[str, Dict]) -> Optional[float]:
        """
        从多个数据源中获取可信价格

        Args:
            data_dict: 数据源名称 -> 数据字典

        Returns:
            可信价格，如果没有有效数据返回None
        """
        valid_prices = []

        for source_name, data in data_dict.items():
            is_valid, msg = self.validate_realtime_data(data, source_name)
            if is_valid and data.get('price', 0) > 0:
                valid_prices.append({
                    'source': source_name,
                    'price': data['price'],
                    'confidence': self._get_source_confidence(source_name)
                })

        if not valid_prices:
            # 返回最后一个有效价格
            if self.last_valid_price:
                return self.last_valid_price
            return None

        # 加权平均，可信度高的数据源权重更大
        total_weight = sum(p['confidence'] for p in valid_prices)
        if total_weight == 0:
            return valid_prices[0]['price'] if valid_prices else None

        trusted_price = sum(p['price'] * p['confidence'] for p in valid_prices) / total_weight
        return trusted_price

    def _get_source_confidence(self, source_name: str) -> float:
        """获取数据源可信度"""
        status = self.data_source_status.get(source_name, {})

        # 基础可信度
        base_confidence = 0.5

        # 根据健康状态调整
        if status.get('is_healthy', False):
            base_confidence += 0.3

        # 根据连续失败次数降低
        failures = status.get('consecutive_failures', 0)
        base_confidence -= min(failures * 0.1, 0.3)

        return max(0.1, min(1.0, base_confidence))

    def _record_success(self, source_name: str):
        """记录成功的数据获取"""
        if source_name not in self.data_source_status:
            self.data_source_status[source_name] = {
                'is_healthy': True,
                'consecutive_failures': 0,
                'last_update': datetime.now()
            }
        else:
            self.data_source_status[source_name]['is_healthy'] = True
            self.data_source_status[source_name]['consecutive_failures'] = 0
            self.data_source_status[source_name]['last_update'] = datetime.now()

    def _record_failure(self, source_name: str, reason: str) -> Tuple[bool, str]:
        """记录失败的数据获取"""
        self.stats['failed_checks'] += 1

        if source_name not in self.data_source_status:
            self.data_source_status[source_name] = {
                'is_healthy': False,
                'consecutive_failures': 1,
                'last_update': None
            }
        else:
            self.data_source_status[source_name]['consecutive_failures'] += 1
            if self.data_source_status[source_name]['consecutive_failures'] >= 3:
                self.data_source_status[source_name]['is_healthy'] = False

        # 记录失败统计
        if source_name not in self.stats['data_source_failures']:
            self.stats['data_source_failures'][source_name] = 0
        self.stats['data_source_failures'][source_name] += 1

        return False, f"数据源 {source_name} 失败: {reason}"

    def _trigger_alert(self, source_name: str, alert_type: str, message: str, details: Dict = None):
        """触发告警"""
        self.stats['alerts_triggered'] += 1

        alert = {
            'timestamp': datetime.now().isoformat(),
            'source': source_name,
            'type': alert_type,
            'message': message,
            'details': details or {}
        }

        self.alerts.append(alert)

        # 只保留最近100条告警
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

        print(f"[ALERT] {source_name} - {alert_type}: {message}")

    def get_stats(self) -> Dict:
        """获取统计数据"""
        return {
            **self.stats,
            'current_valid_price': self.last_valid_price,
            'alert_count': len(self.alerts),
            'recent_alerts': self.alerts[-5:] if self.alerts else []
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            'total_checks': 0,
            'failed_checks': 0,
            'alerts_triggered': 0,
            'data_source_failures': {}
        }
        self.alerts.clear()
        print("[DataSourceRiskControl] 统计数据已重置")


class EnhancedSecurityControl(DataSourceRiskControl):
    """
    增强型安全控制模块
    在数据源风控基础上添加安全检测和输入过滤功能
    """
    
    def __init__(self):
        super().__init__()
        
        # 安全规则配置
        self.security_rules = {
            'max_request_rate': 100,  # 每分钟最大请求数
            'max_concurrent_sessions': 10,  # 最大并发会话数
            'allowed_origin_patterns': ['localhost', '127.0.0.1', '192.168.'],  # 允许的来源模式
            'suspicious_patterns': [
                '../', '..\\', '/etc/', 'C:\\',  # 路径遍历
                'DROP ', 'UNION ', 'SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ',  # SQL注入
                '<script', '</script>', 'javascript:',  # XSS攻击
                'eval(', 'exec(', 'system(', 'shell_exec('  # 命令执行
            ],
            'max_input_length': 10000,  # 最大输入长度
            'api_key_pattern': r'^sk-[a-zA-Z0-9]{20,}$'  # API密钥格式
        }
        
        # 安全状态跟踪
        self.request_timestamps = deque(maxlen=60)  # 最近60秒的请求时间戳
        self.active_sessions = set()
        self.blocked_ips = set()
        self.security_events = deque(maxlen=100)
    
    def detect_suspicious_input(self, input_data: str) -> Tuple[bool, str]:
        """
        检测可疑输入（防注入攻击）
        
        Args:
            input_data: 要检测的输入字符串
            
        Returns:
            (是否安全, 消息)
        """
        if not isinstance(input_data, str):
            input_data = str(input_data)
        
        # 检查长度
        if len(input_data) > self.security_rules['max_input_length']:
            return False, f"输入过长（{len(input_data)}字符）"
        
        # 检查可疑模式
        for pattern in self.security_rules['suspicious_patterns']:
            if pattern.lower() in input_data.lower():
                self._record_security_event('suspicious_input', f"检测到可疑模式: {pattern}")
                return False, f"检测到可疑输入模式: {pattern}"
        
        return True, "输入安全"
    
    def validate_api_request(self, request_data: Dict) -> Tuple[bool, str]:
        """
        验证API请求安全性
        
        Args:
            request_data: 请求数据字典
            
        Returns:
            (是否安全, 消息)
        """
        # 检查请求来源
        if 'origin' in request_data:
            origin = request_data['origin']
            allowed = any(pattern in origin for pattern in self.security_rules['allowed_origin_patterns'])
            if not allowed:
                self._record_security_event('unauthorized_origin', f"未授权来源: {origin}")
                return False, f"未授权的请求来源: {origin}"
        
        # 检查请求频率
        now = datetime.now().timestamp()
        self.request_timestamps.append(now)
        
        # 计算最近60秒的请求数
        recent_requests = sum(1 for t in self.request_timestamps if now - t <= 60)
        if recent_requests > self.security_rules['max_request_rate']:
            self._record_security_event('rate_limit', f"请求频率超限: {recent_requests}/分钟")
            return False, f"请求频率过高，请稍后重试"
        
        # 检查并发会话数
        if len(self.active_sessions) > self.security_rules['max_concurrent_sessions']:
            self._record_security_event('session_limit', f"并发会话超限: {len(self.active_sessions)}")
            return False, "当前系统繁忙，请稍后重试"
        
        return True, "请求验证通过"
    
    def validate_api_key(self, api_key: str) -> Tuple[bool, str]:
        """
        验证API密钥格式
        
        Args:
            api_key: API密钥
            
        Returns:
            (是否有效, 消息)
        """
        import re
        
        if not api_key:
            return False, "API密钥不能为空"
        
        # 检查格式
        if not re.match(self.security_rules['api_key_pattern'], api_key):
            return False, "API密钥格式不正确"
        
        # 检查密钥长度
        if len(api_key) < 20:
            return False, "API密钥长度不足"
        
        return True, "API密钥验证通过"
    
    def validate_trade_order(self, order_data: Dict) -> Tuple[bool, str]:
        """
        验证交易订单安全性
        
        Args:
            order_data: 订单数据
            
        Returns:
            (是否安全, 消息)
        """
        # 验证价格
        price = order_data.get('price', 0)
        if price <= 0:
            return False, "订单价格必须大于0"
        
        # 验证数量
        quantity = order_data.get('quantity', 0)
        if quantity <= 0:
            return False, "订单数量必须大于0"
        
        # 验证金额
        amount = price * quantity
        if amount > 10000000:  # 1000万限制
            self._record_security_event('large_order', f"大额订单: {amount}")
            return False, "订单金额超限"
        
        # 验证订单类型
        order_type = order_data.get('type', '')
        if order_type not in ['market', 'limit', 'stop']:
            return False, f"未知订单类型: {order_type}"
        
        return True, "订单验证通过"
    
    def add_session(self, session_id: str):
        """添加会话"""
        self.active_sessions.add(session_id)
    
    def remove_session(self, session_id: str):
        """移除会话"""
        self.active_sessions.discard(session_id)
    
    def block_ip(self, ip_address: str, reason: str):
        """阻止IP"""
        self.blocked_ips.add(ip_address)
        self._record_security_event('ip_blocked', f"IP已阻止: {ip_address} - {reason}")
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """检查IP是否被阻止"""
        return ip_address in self.blocked_ips
    
    def _record_security_event(self, event_type: str, message: str):
        """记录安全事件"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'message': message
        }
        self.security_events.append(event)
        print(f"[SECURITY] {event_type}: {message}")
    
    def get_security_summary(self) -> Dict:
        """获取安全状态摘要"""
        now = datetime.now().timestamp()
        recent_requests = sum(1 for t in self.request_timestamps if now - t <= 60)
        
        return {
            'request_rate': recent_requests,
            'active_sessions': len(self.active_sessions),
            'blocked_ips': len(self.blocked_ips),
            'recent_security_events': list(self.security_events)[-10:]
        }


# 全局实例
global_data_source_risk_control = None
global_security_control = None

def get_data_source_risk_control() -> DataSourceRiskControl:
    """获取全局数据源风控实例"""
    global global_data_source_risk_control
    if global_data_source_risk_control is None:
        global_data_source_risk_control = DataSourceRiskControl()
    return global_data_source_risk_control

def get_security_control() -> EnhancedSecurityControl:
    """获取全局安全控制实例"""
    global global_security_control
    if global_security_control is None:
        global_security_control = EnhancedSecurityControl()
    return global_security_control
