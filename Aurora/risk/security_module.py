#!/usr/bin/env python3
"""
安全控制模块（增量模块集成版）
实现 BaseModule 标准接口，无缝集成到 Aurora 系统中

功能：
1. 输入验证（XSS/SQL注入/命令注入检测）
2. 交易订单验证
3. 安全事件记录
4. 安全状态API
5. 白名单/黑名单管理
6. 与 SystemSwitcher 和 ModuleRegistry 联动
"""

import re
import json
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class BaseModule:
    """增量模块基类（本地定义，避免循环导入）"""
    
    def __init__(self, app=None):
        self.app = app
        self.enabled = False
        self.module_name = self.__class__.__name__
    
    def register_routes(self, app):
        pass
    
    def register_hooks(self, app):
        pass
    
    def start(self):
        self.enabled = True
        logger.info(f"[{self.module_name}] 已启动")
    
    def stop(self):
        self.enabled = False
        logger.info(f"[{self.module_name}] 已停止")
    
    def get_status(self) -> Dict[str, Any]:
        return {
            'name': self.module_name,
            'enabled': self.enabled,
        }


class SecurityModule(BaseModule):
    """
    安全控制模块
    
    提供全面的安全防护：
    - 输入验证与清洗
    - 攻击检测（XSS, SQL注入, 命令注入）
    - 交易订单安全验证
    - 安全事件审计
    - 访问频率限制
    """
    
    # 可疑模式定义
    XSS_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript\s*:',
        r'on\w+\s*=',
        r'<iframe[^>]*>',
        r'<img[^>]*onerror\s*=',
        r'document\.cookie',
        r'window\.location',
        r'eval\s*\(',
        r'expression\s*\(',
        r'<embed[^>]*>',
        r'<object[^>]*>',
        r'<link[^>]*>',
        r'<style[^>]*>',
    ]
    
    SQL_INJECTION_PATTERNS = [
        r"('\s*(\bOR\b|\bAND\b)\s*'\d*'\s*=\s*'\d*)",
        r"('\s*OR\s+'\d*'\s*=\s*'\d*)",
        r"(--\s*\w*)",
        r"(;\s*\bDROP\b\s+)",
        r"(;\s*\bDELETE\b\s+)",
        r"(;\s*\bINSERT\b\s+)",
        r"(;\s*\bUPDATE\b\s+)",
        r"(UNION\s+SELECT)",
        r"(SELECT\s+.*\s+FROM\s+)",
        r"('\s*;\s*)",
        r"(/\*.*\*/)",
    ]
    
    COMMAND_INJECTION_PATTERNS = [
        r'[;&|`]\s*(cat|rm|wget|curl|nc|bash|sh|python|perl|php)\b',
        r'\$\([^)]*\)',
        r'`[^`]*`',
        r'&&\s*\w+',
        r'\|\|\s*\w+',
    ]
    
    def __init__(self, app=None):
        super().__init__(app)
        self.module_name = 'SecurityModule'
        
        # 安全统计
        self._total_checks = 0
        self._blocked_attempts = 0
        self._security_events: list = []
        self._max_events = 1000
        
        # 频率限制
        self._request_counts: Dict[str, list] = defaultdict(list)
        self._rate_limit_window = 60  # 60秒窗口
        self._rate_limit_max = 100  # 每窗口最大请求数
        
        # 白名单IP
        self._whitelist_ips: set = set()
        
        # 数据库管理器引用（延迟初始化）
        self._db_manager = None
        
        logger.info("[SecurityModule] 安全控制模块已初始化")
    
    def set_database_manager(self, db_manager):
        """设置数据库管理器引用"""
        self._db_manager = db_manager
    
    def add_whitelist_ip(self, ip: str):
        """添加白名单IP"""
        self._whitelist_ips.add(ip)
        logger.info(f"[SecurityModule] 已添加白名单IP: {ip}")
    
    def remove_whitelist_ip(self, ip: str):
        """移除白名单IP"""
        self._whitelist_ips.discard(ip)
    
    def is_whitelisted(self, ip: str) -> bool:
        """检查IP是否在白名单中"""
        return ip in self._whitelist_ips
    
    def check_rate_limit(self, ip: str) -> Tuple[bool, str]:
        """
        检查频率限制
        
        Returns:
            (是否允许, 消息)
        """
        if ip in self._whitelist_ips:
            return True, '白名单IP'
        
        now = datetime.now()
        cutoff = now - timedelta(seconds=self._rate_limit_window)
        
        # 清理过期记录
        self._request_counts[ip] = [
            t for t in self._request_counts[ip] if t > cutoff
        ]
        
        count = len(self._request_counts[ip])
        
        if count >= self._rate_limit_max:
            return False, f'请求频率超限 ({count}/{self._rate_limit_window}s)'
        
        self._request_counts[ip].append(now)
        return True, 'OK'
    
    # ── 反向代理/匿名访问检测 ──
    
    REVERSE_PROXY_HEADERS = [
        'X-Forwarded-For',
        'X-Real-IP',
        'X-Forwarded-Host',
        'X-Forwarded-Proto',
        'Via',
        'Forwarded',
    ]
    
    SUSPICIOUS_IP_RANGES = [
        # 已知匿名代理/数据中心 IP 范围（示例）
        ('10.0.0.0', '10.255.255.255'),       # 私有网络
        ('172.16.0.0', '172.31.255.255'),      # 私有网络
        ('192.168.0.0', '192.168.255.255'),    # 私有网络
    ]
    
    ANONYMIZER_DOMAINS = [
        'proxy', 'vpn', 'tor', 'anonymizer',
        'anonymous', 'hide', 'cloak',
    ]
    
    def detect_reverse_proxy(self, headers: Dict[str, str], client_ip: str = '') -> Tuple[bool, str, Dict[str, Any]]:
        """
        检测反向代理和匿名访问
        
        Args:
            headers: 请求头字典
            client_ip: 客户端IP
        
        Returns:
            (是否合法, 消息, 检测详情)
        """
        details = {
            'proxy_headers_detected': [],
            'ip_in_private_range': False,
            'suspicious_anonymizer': False,
            'risk_level': 'low',
        }
        
        # 1. 检测反向代理头
        for header in self.REVERSE_PROXY_HEADERS:
            if header in headers:
                details['proxy_headers_detected'].append(header)
        
        # 2. 检查客户端 IP 是否在私有/可疑网段
        if client_ip:
            try:
                parts = client_ip.split('.')
                if len(parts) == 4:
                    ip_int = (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])
                    for start, end in self.SUSPICIOUS_IP_RANGES:
                        s_parts = start.split('.')
                        e_parts = end.split('.')
                        s_int = (int(s_parts[0]) << 24) + (int(s_parts[1]) << 16) + (int(s_parts[2]) << 8) + int(s_parts[3])
                        e_int = (int(e_parts[0]) << 24) + (int(e_parts[1]) << 16) + (int(e_parts[2]) << 8) + int(e_parts[3])
                        if s_int <= ip_int <= e_int:
                            details['ip_in_private_range'] = True
                            break
            except Exception:
                pass
        
        # 3. 检查 Host 头是否包含匿名代理特征
        host = headers.get('Host', '').lower()
        for keyword in self.ANONYMIZER_DOMAINS:
            if keyword in host:
                details['suspicious_anonymizer'] = True
                break
        
        # 4. 综合风险评估
        risk_score = 0
        if len(details['proxy_headers_detected']) >= 2:
            risk_score += 30
        elif len(details['proxy_headers_detected']) == 1:
            risk_score += 10
        
        if details['ip_in_private_range']:
            risk_score += 25
        
        if details['suspicious_anonymizer']:
            risk_score += 40
        
        if risk_score >= 50:
            details['risk_level'] = 'high'
        elif risk_score >= 30:
            details['risk_level'] = 'medium'
        else:
            details['risk_level'] = 'low'
        
        is_safe = risk_score < 50
        
        if not is_safe:
            self._record_security_event(
                'reverse_proxy_detected',
                f'检测到可疑反向代理/匿名访问，风险分数={risk_score}',
                details
            )
        
        msg = f'代理检测完成，风险等级={details["risk_level"]}，分数={risk_score}'
        return is_safe, msg, details
    
    def detect_suspicious_input(self, value: str) -> Tuple[bool, str]:
        """
        检测可疑输入
        
        Args:
            value: 输入字符串
        
        Returns:
            (是否安全, 检测结果描述)
        """
        if not value or not isinstance(value, str):
            return True, 'OK'
        
        self._total_checks += 1
        
        # XSS检测
        for pattern in self.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                self._blocked_attempts += 1
                return False, f'检测到XSS攻击模式: {pattern}'
        
        # SQL注入检测
        for pattern in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                self._blocked_attempts += 1
                return False, f'检测到SQL注入模式: {pattern}'
        
        # 命令注入检测
        for pattern in self.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                self._blocked_attempts += 1
                return False, f'检测到命令注入模式: {pattern}'
        
        return True, 'OK'
    
    def validate_input_dict(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证字典中所有输入
        
        Args:
            data: 输入数据字典
        
        Returns:
            (是否安全, 错误消息)
        """
        if not data:
            return True, 'OK'
        
        for key, value in data.items():
            if isinstance(value, str):
                is_safe, message = self.detect_suspicious_input(value)
                if not is_safe:
                    self._record_security_event(
                        'suspicious_input',
                        f'字段 {key}: {message}',
                        {'key': key, 'value_preview': value[:50]}
                    )
                    return False, f'字段 "{key}" 包含可疑内容: {message}'
            
            elif isinstance(value, dict):
                is_safe, message = self.validate_input_dict(value)
                if not is_safe:
                    return False, message
            
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        is_safe, message = self.detect_suspicious_input(item)
                        if not is_safe:
                            return False, f'列表项包含可疑内容: {message}'
        
        return True, 'OK'
    
    def validate_trade_order(self, order_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证交易订单
        
        Args:
            order_data: 订单数据
        
        Returns:
            (是否有效, 消息)
        """
        if not order_data:
            return False, '订单数据为空'
        
        required_fields = ['symbol', 'quantity', 'price', 'direction']
        for field in required_fields:
            if field not in order_data:
                return False, f'缺少必要字段: {field}'
        
        symbol = order_data.get('symbol', '')
        quantity = order_data.get('quantity', 0)
        price = order_data.get('price', 0)
        direction = order_data.get('direction', '')
        
        # 验证股票代码格式
        if not re.match(r'^[A-Za-z0-9.]+$', str(symbol)):
            return False, f'无效的股票代码: {symbol}'
        
        # 验证数量
        try:
            qty = float(quantity)
            if qty <= 0 or qty > 10000000:
                return False, f'无效的数量: {quantity}'
        except (ValueError, TypeError):
            return False, f'数量格式错误: {quantity}'
        
        # 验证价格
        try:
            prc = float(price)
            if prc <= 0 or prc > 1000000:
                return False, f'无效的价格: {price}'
        except (ValueError, TypeError):
            return False, f'价格格式错误: {price}'
        
        # 验证方向
        if direction not in ('buy', 'sell', 'long', 'short', 'close'):
            return False, f'无效的交易方向: {direction}'
        
        # 验证输入内容（防注入）
        is_safe, message = self.validate_input_dict(order_data)
        if not is_safe:
            return False, message
        
        return True, '订单验证通过'
    
    def _record_security_event(self, event_type: str, message: str, 
                                details: Dict = None):
        """记录安全事件"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'message': message,
            'details': details or {},
        }
        
        self._security_events.append(event)
        
        # 限制事件数量
        if len(self._security_events) > self._max_events:
            self._security_events = self._security_events[-self._max_events:]
        
        # 同时写入数据库
        if self._db_manager:
            try:
                self._db_manager.insert_security_event(
                    event_type=event_type,
                    source_ip='system',
                    message=message,
                    details=json.dumps(details) if details else ''
                )
            except Exception as e:
                logger.error(f"[SecurityModule] 数据库写入失败: {e}")
        
        logger.warning(f"[SecurityModule] 安全事件 [{event_type}]: {message}")
    
    def get_security_summary(self) -> Dict[str, Any]:
        """获取安全摘要"""
        return {
            'total_checks': self._total_checks,
            'blocked_attempts': self._blocked_attempts,
            'total_events': len(self._security_events),
            'recent_events': self._security_events[-10:],
            'whitelist_count': len(self._whitelist_ips),
            'rate_limited_ips': len(self._request_counts),
        }
    
    def get_security_events(self, limit: int = 50, event_type: str = None) -> list:
        """
        获取安全事件列表
        
        Args:
            limit: 返回数量限制
            event_type: 过滤事件类型
        
        Returns:
            事件列表
        """
        events = self._security_events
        
        if event_type:
            events = [e for e in events if e['type'] == event_type]
        
        return events[-limit:]
    
    def register_routes(self, app):
        """注册安全模块路由"""
        
        @app.route('/api/security/status')
        def security_status():
            """获取安全状态"""
            try:
                return json.dumps({
                    'success': True,
                    'data': self.get_security_summary(),
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取安全状态失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/security/events')
        def security_events():
            """获取安全事件"""
            try:
                event_type = request.args.get('type')
                limit = int(request.args.get('limit', 50))
                events = self.get_security_events(limit=limit, event_type=event_type)
                
                return json.dumps({
                    'success': True,
                    'data': events,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取安全事件失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/security/whitelist', methods=['GET', 'POST', 'DELETE'])
        def security_whitelist():
            """白名单管理"""
            try:
                if request.method == 'GET':
                    return json.dumps({
                        'success': True,
                        'data': list(self._whitelist_ips),
                    }), 200, {'Content-Type': 'application/json'}
                
                elif request.method == 'POST':
                    data = request.get_json() if request.is_json else {}
                    ip = data.get('ip', '')
                    if not ip:
                        return json.dumps({
                            'success': False,
                            'message': '缺少IP参数',
                        }), 400, {'Content-Type': 'application/json'}
                    self.add_whitelist_ip(ip)
                    return json.dumps({
                        'success': True,
                        'message': f'已添加白名单IP: {ip}',
                    }), 200, {'Content-Type': 'application/json'}
                
                elif request.method == 'DELETE':
                    data = request.get_json() if request.is_json else {}
                    ip = data.get('ip', '')
                    if not ip:
                        return json.dumps({
                            'success': False,
                            'message': '缺少IP参数',
                        }), 400, {'Content-Type': 'application/json'}
                    self.remove_whitelist_ip(ip)
                    return json.dumps({
                        'success': True,
                        'message': f'已移除白名单IP: {ip}',
                    }), 200, {'Content-Type': 'application/json'}
                    
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'白名单操作失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        logger.info("[SecurityModule] 安全路由已注册")
    
    def get_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        base = super().get_status()
        base.update(self.get_security_summary())
        return base


# 装饰器：输入验证
def validate_api_input(*fields_to_check):
    """
    API输入验证装饰器
    
    用法:
        @app.route('/api/some-endpoint')
        @validate_api_input()
        def some_endpoint():
            ...
    """
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, jsonify
            security = get_security_module()
            
            # 获取请求数据
            if request.is_json:
                data = request.get_json() or {}
            elif request.form:
                data = request.form.to_dict()
            elif request.args:
                data = request.args.to_dict()
            else:
                data = {}
            
            # 频率限制检查
            client_ip = request.remote_addr or '127.0.0.1'
            allowed, msg = security.check_rate_limit(client_ip)
            if not allowed:
                return jsonify({
                    'success': False,
                    'message': '请求过于频繁，请稍后重试',
                    'error': msg,
                }), 429
            
            # 输入验证
            is_safe, message = security.validate_input_dict(data)
            if not is_safe:
                return jsonify({
                    'success': False,
                    'message': '检测到可疑输入',
                    'error': message,
                }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# 全局实例
_global_security_module: Optional[SecurityModule] = None


def get_security_module() -> SecurityModule:
    """获取全局安全模块实例"""
    global _global_security_module
    if _global_security_module is None:
        _global_security_module = SecurityModule()
    return _global_security_module