#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能监控调度系统
根据交易时间动态调整健康检查频率，避免影响交易性能
"""

import time
import threading
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable
from collections import deque


class TradingTimeManager:
    """
    交易时间管理器
    管理交易时段的判断和调度
    """

    PRE_MARKET_START = dt_time(9, 0)
    PRE_MARKET_END = dt_time(9, 30)
    MORNING_START = dt_time(9, 30)
    MORNING_END = dt_time(11, 30)
    LUNCH_START = dt_time(11, 30)
    LUNCH_END = dt_time(13, 0)
    AFTERNOON_START = dt_time(13, 0)
    AFTERNOON_END = dt_time(15, 0)
    POST_MARKET_START = dt_time(15, 0)
    POST_MARKET_END = dt_time(18, 0)
    MAINTENANCE_START = dt_time(18, 0)
    MAINTENANCE_END = dt_time(9, 0)

    def __init__(self):
        self.weekend_days = {5, 6}

    def get_current_period(self) -> str:
        now = datetime.now().time()
        weekday = datetime.now().weekday()

        if weekday in self.weekend_days:
            return 'maintenance'

        if self.PRE_MARKET_START <= now < self.PRE_MARKET_END:
            return 'pre_market'
        elif self.MORNING_START <= now < self.MORNING_END:
            return 'trading_morning'
        elif self.LUNCH_START <= now < self.LUNCH_END:
            return 'lunch'
        elif self.AFTERNOON_START <= now < self.AFTERNOON_END:
            return 'trading_afternoon'
        elif self.POST_MARKET_START <= now < self.POST_MARKET_END:
            return 'post_market'
        else:
            return 'maintenance'

    def is_trading_hours(self) -> bool:
        period = self.get_current_period()
        return period in ['trading_morning', 'trading_afternoon']

    def get_health_check_interval(self) -> int:
        period = self.get_current_period()
        interval_map = {
            'trading_morning': 300,
            'trading_afternoon': 300,
            'pre_market': 60,
            'lunch': 120,
            'post_market': 120,
            'maintenance': 600
        }
        return interval_map.get(period, 600)

    def get_risk_check_interval(self) -> int:
        period = self.get_current_period()
        interval_map = {
            'trading_morning': 30,
            'trading_afternoon': 30,
            'pre_market': 120,
            'lunch': 300,
            'post_market': 300,
            'maintenance': 600
        }
        return interval_map.get(period, 600)


class HealthCheckTask:
    def __init__(self, name: str, check_func: Callable, interval: int = 60):
        self.name = name
        self.check_func = check_func
        self.interval = interval
        self.last_run = 0
        self.results = deque(maxlen=24)
        self.enabled = True

    def run(self):
        try:
            result = self.check_func()
            self.results.append({
                'timestamp': datetime.now().isoformat(),
                'status': result.get('status', 'unknown'),
                'message': result.get('message', ''),
                'details': result.get('details', {})
            })
            self.last_run = time.time()
            return result
        except Exception as e:
            self.results.append({
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'message': str(e),
                'details': {}
            })
            self.last_run = time.time()
            return {'status': 'error', 'message': str(e)}

    def should_run(self) -> bool:
        if not self.enabled:
            return False
        return time.time() - self.last_run >= self.interval

    def get_status_summary(self) -> Dict:
        if not self.results:
            return {'status': 'unknown', 'count': 0}

        status_counts = {}
        for r in self.results:
            status = r['status']
            status_counts[status] = status_counts.get(status, 0) + 1

        latest = self.results[-1]
        return {
            'status': latest['status'],
            'count': len(self.results),
            'status_counts': status_counts,
            'last_run': latest['timestamp']
        }


class MonitoringScheduler:
    def __init__(self):
        self.trading_time_manager = TradingTimeManager()
        self.tasks = []
        self.running = False
        self.thread = None
        self.report_callbacks = []
        self.last_report_time = 0
        self.report_interval = 3600

    def add_task(self, task: HealthCheckTask):
        self.tasks.append(task)

    def remove_task(self, name: str):
        self.tasks = [t for t in self.tasks if t.name != name]

    def get_task(self, name: str) -> Optional[HealthCheckTask]:
        for task in self.tasks:
            if task.name == name:
                return task
        return None

    def update_task_intervals(self):
        health_interval = self.trading_time_manager.get_health_check_interval()
        risk_interval = self.trading_time_manager.get_risk_check_interval()

        for task in self.tasks:
            if 'risk' in task.name.lower():
                task.interval = risk_interval
            else:
                task.interval = health_interval

    def run_all_tasks(self):
        results = {}
        for task in self.tasks:
            if task.should_run():
                results[task.name] = task.run()
        return results

    def generate_report(self) -> Dict:
        report = {
            'timestamp': datetime.now().isoformat(),
            'period': self.trading_time_manager.get_current_period(),
            'is_trading': self.trading_time_manager.is_trading_hours(),
            'tasks': {},
            'summary': {
                'healthy': 0,
                'warning': 0,
                'critical': 0,
                'error': 0
            }
        }

        for task in self.tasks:
            summary = task.get_status_summary()
            report['tasks'][task.name] = summary
            status = summary.get('status', 'unknown')
            if status in report['summary']:
                report['summary'][status] += 1

        return report

    def _scheduler_loop(self):
        while self.running:
            try:
                self.update_task_intervals()
                results = self.run_all_tasks()

                now = time.time()
                if now - self.last_report_time >= self.report_interval:
                    report = self.generate_report()
                    self.last_report_time = now

                    for callback in self.report_callbacks:
                        try:
                            callback(report)
                        except Exception as e:
                            print(f"[MonitoringScheduler] 报告回调失败: {e}")

                time.sleep(1)
            except Exception as e:
                print(f"[MonitoringScheduler] 调度器循环异常: {e}")
                time.sleep(5)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        print(f"[MonitoringScheduler] 监控调度器已启动")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print(f"[MonitoringScheduler] 监控调度器已停止")

    def add_report_callback(self, callback: Callable):
        self.report_callbacks.append(callback)

    def get_status(self) -> Dict:
        return {
            'running': self.running,
            'task_count': len(self.tasks),
            'current_period': self.trading_time_manager.get_current_period(),
            'is_trading': self.trading_time_manager.is_trading_hours()
        }


global_monitoring_scheduler = None

def get_monitoring_scheduler() -> MonitoringScheduler:
    global global_monitoring_scheduler
    if global_monitoring_scheduler is None:
        global_monitoring_scheduler = MonitoringScheduler()
    return global_monitoring_scheduler


def check_system_health():
    import psutil
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()

    status = 'healthy'
    message = '系统状态正常'

    if cpu_percent > 80:
        status = 'warning'
        message = f"CPU使用率过高: {cpu_percent}%"
    if memory.percent > 80:
        status = 'warning' if status == 'healthy' else 'critical'
        message = f"{message}; 内存使用率过高: {memory.percent}%"

    return {
        'status': status,
        'message': message,
        'details': {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available': round(memory.available / (1024**3), 2)
        }
    }


def check_network_status():
    try:
        import urllib.request
        urllib.request.urlopen('https://www.baidu.com', timeout=5)
        return {'status': 'healthy', 'message': '网络连接正常'}
    except Exception as e:
        return {'status': 'critical', 'message': f"网络连接异常: {str(e)}"}


def check_database_status():
    """检查数据库状态"""
    try:
        from utils.database_manager import get_database_manager
        db = get_database_manager()
        stats = db.get_database_stats()
        
        # 分析数据库状态
        total_records = sum(stats.values()) if stats else 0
        
        return {
            'status': 'healthy',
            'message': f'数据库正常，共 {total_records} 条记录',
            'details': stats
        }
    except Exception as e:
        return {
            'status': 'critical',
            'message': f'数据库异常: {str(e)}',
            'details': {}
        }

def check_security_status():
    """检查安全状态"""
    try:
        from risk.data_source_risk_control import get_security_control
        security = get_security_control()
        
        # 获取安全摘要（如果有）
        summary = {}
        if hasattr(security, 'get_security_summary'):
            summary = security.get_security_summary()
        
        return {
            'status': 'healthy',
            'message': '安全模块正常运行',
            'details': summary
        }
    except Exception as e:
        return {
            'status': 'warning',
            'message': f'安全模块检查: {str(e)}',
            'details': {}
        }

def check_full_system_health():
    """检查完整系统健康状态"""
    try:
        from monitor.system_health import get_system_health_monitor
        monitor = get_system_health_monitor()
        result = monitor.check_all_modules()
        
        overall_status = result.get('overall_status', 'unknown')
        
        return {
            'status': str(overall_status),
            'message': f'系统健康检查完成，状态: {overall_status}',
            'details': result
        }
    except Exception as e:
        return {
            'status': 'critical',
            'message': f'系统健康检查失败: {str(e)}',
            'details': {}
        }

def initialize_default_tasks():
    """初始化默认健康检查任务"""
    scheduler = get_monitoring_scheduler()
    
    # 注册基础检查任务
    scheduler.add_task(HealthCheckTask('system_resources', check_system_health))
    scheduler.add_task(HealthCheckTask('network', check_network_status))
    scheduler.add_task(HealthCheckTask('database', check_database_status))
    scheduler.add_task(HealthCheckTask('security', check_security_status))
    scheduler.add_task(HealthCheckTask('full_health', check_full_system_health))
    
    print(f"[MonitoringScheduler] 已初始化 {len(scheduler.tasks)} 个检查任务")


if __name__ == '__main__':
    initialize_default_tasks()
    scheduler = get_monitoring_scheduler()

    def print_report(report):
        print("\n=== 监控报告 ===")
        print(f"时间: {report['timestamp']}")
        print(f"时段: {report['period']}")
        print(f"交易中: {report['is_trading']}")
        print(f"摘要: {report['summary']}")
        for task_name, task_summary in report['tasks'].items():
            print(f"  {task_name}: {task_summary['status']}")

    scheduler.add_report_callback(print_report)
    scheduler.start()

    print("监控调度器测试运行中...")
    time.sleep(10)

    status = scheduler.get_status()
    print(f"\n调度器状态: {status}")

    report = scheduler.generate_report()
    print_report(report)

    scheduler.stop()
