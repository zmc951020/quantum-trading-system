#!/usr/bin/env python3
"""
监控模块（增量模块集成版）
实现 BaseModule 标准接口，无缝集成到 Aurora 系统中

功能：
1. 系统健康检查与监控
2. 策略性能追踪
3. 数据源健康监控
4. 告警管理
5. 监控API端点
6. 与 SystemSwitcher 和 ModuleRegistry 联动
"""

import json
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from collections import deque
import logging

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


class MonitorModule(BaseModule):
    """
    监控模块
    
    提供全面的系统监控：
    - 组件健康检查
    - 性能指标追踪
    - 告警规则与通知
    - 系统资源监控
    - 历史指标存储
    """
    
    def __init__(self, app=None):
        super().__init__(app)
        self.module_name = 'MonitorModule'
        
        # 组件状态
        self._components: Dict[str, Dict] = {}
        
        # 性能指标
        self._metrics: Dict[str, deque] = {}
        self._metric_maxlen = 1000
        
        # 告警规则
        self._alert_rules: List[Dict] = []
        self._active_alerts: List[Dict] = []
        self._alert_history: deque = deque(maxlen=500)
        
        # 监控状态
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_interval = 30  # 监控间隔（秒）
        self._stop_monitor = threading.Event()
        
        # 回调
        self._on_alert_callbacks: List[Callable] = []
        
        # 系统资源
        self._system_stats: Dict = {}
        
        # 数据库管理器引用
        self._db_manager = None
        
        # 初始化默认告警规则
        self._init_default_alert_rules()
        
        logger.info("[MonitorModule] 监控模块已初始化")
    
    def set_database_manager(self, db_manager):
        """设置数据库管理器引用"""
        self._db_manager = db_manager
    
    def _init_default_alert_rules(self):
        """初始化默认告警规则"""
        self._alert_rules = [
            {
                'name': 'high_memory_usage',
                'metric': 'memory_percent',
                'condition': '>',
                'threshold': 85,
                'severity': 'warning',
                'message': '内存使用率超过85%',
            },
            {
                'name': 'high_cpu_usage',
                'metric': 'cpu_percent',
                'condition': '>',
                'threshold': 90,
                'severity': 'warning',
                'message': 'CPU使用率超过90%',
            },
            {
                'name': 'strategy_drawdown',
                'metric': 'strategy_drawdown',
                'condition': '>',
                'threshold': 15,
                'severity': 'critical',
                'message': '策略回撤超过15%',
            },
            {
                'name': 'data_source_down',
                'metric': 'data_source_available',
                'condition': '==',
                'threshold': 0,
                'severity': 'critical',
                'message': '所有数据源不可用',
            },
            {
                'name': 'trade_failure_rate',
                'metric': 'trade_failure_rate',
                'condition': '>',
                'threshold': 5,
                'severity': 'warning',
                'message': '交易失败率超过5%',
            },
        ]
    
    def register_component(self, name: str, check_func: Callable = None):
        """
        注册监控组件
        
        Args:
            name: 组件名称
            check_func: 健康检查函数，返回 (status, message)
        """
        self._components[name] = {
            'name': name,
            'status': 'unknown',
            'message': '未检查',
            'last_checked': None,
            'check_func': check_func,
            'checks_count': 0,
            'fail_count': 0,
        }
        logger.info(f"[MonitorModule] 已注册组件: {name}")
    
    def update_component_status(self, name: str, status: str, message: str = ''):
        """
        更新组件状态
        
        Args:
            name: 组件名称
            status: 'healthy', 'warning', 'critical', 'unknown'
            message: 状态消息
        """
        if name not in self._components:
            self.register_component(name)
        
        self._components[name].update({
            'status': status,
            'message': message,
            'last_checked': datetime.now().isoformat(),
        })
        
        if status != 'healthy':
            self._components[name]['fail_count'] += 1
        
        self._components[name]['checks_count'] += 1
        
        # 自动记录健康检查到数据库
        if self._db_manager:
            try:
                self._db_manager.insert_health_check(
                    component=name,
                    status=status,
                    message=message,
                    details=json.dumps(self._components[name].get('details', {}))
                )
            except Exception as e:
                logger.error(f"[MonitorModule] 健康检查写入数据库失败: {e}")
    
    def record_metric(self, name: str, value: float):
        """
        记录指标值
        
        Args:
            name: 指标名称
            value: 指标值
        """
        if name not in self._metrics:
            self._metrics[name] = deque(maxlen=self._metric_maxlen)
        
        self._metrics[name].append({
            'timestamp': datetime.now().isoformat(),
            'value': value,
        })
        
        # 检查告警规则
        self._check_alerts(name, value)
    
    def get_metric_stats(self, name: str, window: int = 100) -> Dict[str, Any]:
        """
        获取指标统计
        
        Args:
            name: 指标名称
            window: 统计窗口大小
        
        Returns:
            统计信息
        """
        if name not in self._metrics or not self._metrics[name]:
            return {
                'name': name,
                'values': [],
                'avg': 0,
                'min': 0,
                'max': 0,
                'count': 0,
            }
        
        values = [m['value'] for m in list(self._metrics[name])[-window:]]
        
        return {
            'name': name,
            'values': values,
            'avg': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
            'count': len(values),
            'latest': values[-1] if values else 0,
        }
    
    def add_alert_rule(self, rule: Dict):
        """添加告警规则"""
        required = ['name', 'metric', 'condition', 'threshold', 'severity', 'message']
        for field in required:
            if field not in rule:
                raise ValueError(f'告警规则缺少必要字段: {field}')
        
        self._alert_rules.append(rule)
        logger.info(f"[MonitorModule] 已添加告警规则: {rule['name']}")
    
    def on_alert(self, callback: Callable):
        """注册告警回调"""
        self._on_alert_callbacks.append(callback)
    
    def _check_alerts(self, metric_name: str, value: float):
        """检查告警规则"""
        for rule in self._alert_rules:
            if rule['metric'] != metric_name:
                continue
            
            triggered = False
            condition = rule['condition']
            threshold = rule['threshold']
            
            if condition == '>' and value > threshold:
                triggered = True
            elif condition == '<' and value < threshold:
                triggered = True
            elif condition == '>=' and value >= threshold:
                triggered = True
            elif condition == '<=' and value <= threshold:
                triggered = True
            elif condition == '==' and value == threshold:
                triggered = True
            
            if triggered:
                self._trigger_alert(rule, value)
    
    def _trigger_alert(self, rule: Dict, current_value: float):
        """触发告警"""
        # 检查是否已有相同告警在活跃状态
        for alert in self._active_alerts:
            if alert['rule_name'] == rule['name']:
                alert['last_triggered'] = datetime.now().isoformat()
                alert['current_value'] = current_value
                return
        
        alert = {
            'rule_name': rule['name'],
            'severity': rule['severity'],
            'message': rule['message'],
            'metric': rule['metric'],
            'threshold': rule['threshold'],
            'current_value': current_value,
            'triggered_at': datetime.now().isoformat(),
            'last_triggered': datetime.now().isoformat(),
            'acknowledged': False,
            'resolved': False,
        }
        
        self._active_alerts.append(alert)
        self._alert_history.append(alert)
        
        # 记录到数据库
        if self._db_manager:
            try:
                self._db_manager.insert_system_log(
                    'WARNING', 'MonitorModule',
                    f"告警触发: {rule['message']} (当前值: {current_value})"
                )
            except Exception as e:
                logger.error(f"[MonitorModule] 告警写入数据库失败: {e}")
        
        # 执行回调
        for callback in self._on_alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"[MonitorModule] 告警回调异常: {e}")
        
        logger.warning(f"[MonitorModule] ⚠️ 告警触发 [{rule['severity']}]: {rule['message']} (值: {current_value})")
    
    def acknowledge_alert(self, rule_name: str):
        """确认告警"""
        for alert in self._active_alerts:
            if alert['rule_name'] == rule_name:
                alert['acknowledged'] = True
                logger.info(f"[MonitorModule] 告警已确认: {rule_name}")
                return True
        return False
    
    def resolve_alert(self, rule_name: str):
        """解决告警"""
        for i, alert in enumerate(self._active_alerts):
            if alert['rule_name'] == rule_name:
                alert['resolved'] = True
                alert['resolved_at'] = datetime.now().isoformat()
                self._active_alerts.pop(i)
                logger.info(f"[MonitorModule] 告警已解决: {rule_name}")
                return True
        return False
    
    def get_component_status(self) -> Dict[str, Any]:
        """获取所有组件状态"""
        return {
            'components': self._components,
            'summary': {
                'total': len(self._components),
                'healthy': sum(1 for c in self._components.values() if c['status'] == 'healthy'),
                'warning': sum(1 for c in self._components.values() if c['status'] == 'warning'),
                'critical': sum(1 for c in self._components.values() if c['status'] == 'critical'),
                'unknown': sum(1 for c in self._components.values() if c['status'] == 'unknown'),
            }
        }
    
    def get_active_alerts(self) -> List[Dict]:
        """获取活跃告警"""
        return self._active_alerts
    
    def get_alert_history(self, limit: int = 50) -> List[Dict]:
        """获取告警历史"""
        history = list(self._alert_history)
        return history[-limit:]
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统整体健康状态"""
        components = self.get_component_status()['summary']
        alerts = len(self._active_alerts)
        
        # 计算整体健康分
        total = components['total']
        if total == 0:
            score = 100
        else:
            healthy_weight = components['healthy'] * 100
            warning_weight = components['warning'] * 70
            critical_weight = components['critical'] * 30
            unknown_weight = components['unknown'] * 50
            score = (healthy_weight + warning_weight + critical_weight + unknown_weight) / total
        
        # 告警惩罚
        score -= alerts * 5
        
        score = max(0, min(100, score))
        
        if score >= 80:
            overall = 'healthy'
        elif score >= 60:
            overall = 'warning'
        else:
            overall = 'critical'
        
        return {
            'overall': overall,
            'score': round(score, 1),
            'components': components,
            'active_alerts': alerts,
            'checked_at': datetime.now().isoformat(),
        }
    
    def start_background_monitor(self):
        """启动后台监控线程"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._background_monitor_loop,
            daemon=True,
            name='MonitorModule-Background'
        )
        self._monitor_thread.start()
        logger.info("[MonitorModule] 后台监控已启动")
    
    def _background_monitor_loop(self):
        """后台监控循环"""
        while not self._stop_monitor.is_set():
            try:
                self._collect_system_stats()
                
                # 自动检查所有注册组件
                for name, comp in self._components.items():
                    if comp.get('check_func'):
                        try:
                            status, msg = comp['check_func']()
                            self.update_component_status(name, status, msg)
                        except Exception as e:
                            self.update_component_status(name, 'warning', f'检查失败: {e}')
                
            except Exception as e:
                logger.error(f"[MonitorModule] 后台监控异常: {e}")
            
            self._stop_monitor.wait(self._monitor_interval)
    
    def _collect_system_stats(self):
        """收集系统统计信息"""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            
            self._system_stats = {
                'cpu_percent': cpu,
                'memory_percent': memory,
                'disk_percent': disk,
                'checked_at': datetime.now().isoformat(),
            }
            
            self.record_metric('cpu_percent', cpu)
            self.record_metric('memory_percent', memory)
            self.record_metric('disk_percent', disk)
            
        except ImportError:
            self._system_stats = {
                'cpu_percent': -1,
                'memory_percent': -1,
                'disk_percent': -1,
                'note': 'psutil未安装',
            }
        except Exception as e:
            logger.error(f"[MonitorModule] 系统状态采集失败: {e}")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        if not self._system_stats:
            self._collect_system_stats()
        return self._system_stats
    
    def register_routes(self, app):
        """注册监控模块路由"""
        
        @app.route('/api/monitor/status')
        def monitor_status():
            """获取监控状态"""
            try:
                return json.dumps({
                    'success': True,
                    'data': {
                        'components': self.get_component_status(),
                        'system_health': self.get_system_health(),
                        'system_stats': self.get_system_stats(),
                        'active_alerts': self.get_active_alerts(),
                    }
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取监控状态失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/components')
        def monitor_components():
            """获取组件列表"""
            try:
                return json.dumps({
                    'success': True,
                    'data': self._components,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取组件列表失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/alerts')
        def monitor_alerts():
            """获取告警列表"""
            try:
                include_history = request.args.get('history') == '1'
                limit = int(request.args.get('limit', 50))
                
                data = {
                    'active': self.get_active_alerts(),
                }
                if include_history:
                    data['history'] = self.get_alert_history(limit=limit)
                
                return json.dumps({
                    'success': True,
                    'data': data,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取告警失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/alert/acknowledge', methods=['POST'])
        def monitor_acknowledge_alert():
            """确认告警"""
            try:
                data = request.get_json() if request.is_json else {}
                rule_name = data.get('rule_name', '')
                
                if not rule_name:
                    return json.dumps({
                        'success': False,
                        'message': '缺少告警规则名称',
                    }), 400, {'Content-Type': 'application/json'}
                
                result = self.acknowledge_alert(rule_name)
                return json.dumps({
                    'success': result,
                    'message': '告警已确认' if result else '未找到匹配告警',
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'确认告警失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/alert/resolve', methods=['POST'])
        def monitor_resolve_alert():
            """解决告警"""
            try:
                data = request.get_json() if request.is_json else {}
                rule_name = data.get('rule_name', '')
                
                if not rule_name:
                    return json.dumps({
                        'success': False,
                        'message': '缺少告警规则名称',
                    }), 400, {'Content-Type': 'application/json'}
                
                result = self.resolve_alert(rule_name)
                return json.dumps({
                    'success': result,
                    'message': '告警已解决' if result else '未找到匹配告警',
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'解决告警失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/metrics')
        def monitor_metrics():
            """获取指标数据"""
            try:
                metric_name = request.args.get('name')
                window = int(request.args.get('window', 100))
                
                if metric_name:
                    stats = self.get_metric_stats(metric_name, window)
                    return json.dumps({
                        'success': True,
                        'data': stats,
                    }), 200, {'Content-Type': 'application/json'}
                else:
                    # 返回所有指标概要
                    metrics_summary = {}
                    for name in self._metrics.keys():
                        metrics_summary[name] = self.get_metric_stats(name, window)
                    
                    return json.dumps({
                        'success': True,
                        'data': metrics_summary,
                    }), 200, {'Content-Type': 'application/json'}
                    
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取指标失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/monitor/system')
        def monitor_system():
            """获取系统统计"""
            try:
                return json.dumps({
                    'success': True,
                    'data': self.get_system_stats(),
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取系统统计失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        logger.info("[MonitorModule] 监控路由已注册")
    
    def stop(self):
        """停止监控模块"""
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        super().stop()
    
    def get_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        base = super().get_status()
        base.update({
            'system_health': self.get_system_health(),
            'components_count': len(self._components),
            'active_alerts': len(self._active_alerts),
            'metrics_count': len(self._metrics),
        })
        return base


# 全局实例
_global_monitor_module: Optional[MonitorModule] = None


def get_monitor_module() -> MonitorModule:
    """获取全局监控模块实例"""
    global _global_monitor_module
    if _global_monitor_module is None:
        _global_monitor_module = MonitorModule()
    return _global_monitor_module