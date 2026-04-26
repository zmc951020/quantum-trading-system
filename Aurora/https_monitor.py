#!/usr/bin/env python3
"""
HTTPS配置和监控工具
用于配置HTTPS证书和系统监控
"""

import os
import ssl
import json
import time
import threading
from datetime import datetime

class HttpsConfig:
    """
    HTTPS配置管理
    """

    def __init__(self, cert_dir='./certs'):
        """
        初始化HTTPS配置

        Args:
            cert_dir: 证书目录
        """
        self.cert_dir = cert_dir
        os.makedirs(cert_dir, exist_ok=True)

    def generate_self_signed_cert(self, domain='localhost'):
        """
        生成自签名证书

        Args:
            domain: 域名

        Returns:
            证书路径
        """
        import subprocess
        
        cert_file = os.path.join(self.cert_dir, f'{domain}.pem')
        key_file = os.path.join(self.cert_dir, f'{domain}.key')
        
        # 生成私钥
        subprocess.run([
            'openssl', 'genrsa', '-out', key_file, '2048'
        ], check=True)
        
        # 生成证书签名请求
        subprocess.run([
            'openssl', 'req', '-new', '-key', key_file, '-out', f'{self.cert_dir}/csr.pem',
            '-subj', f'/CN={domain}/O=AuroraQuant/C=CN'
        ], check=True)
        
        # 生成自签名证书
        subprocess.run([
            'openssl', 'x509', '-req', '-days', '365', '-in', f'{self.cert_dir}/csr.pem',
            '-signkey', key_file, '-out', cert_file
        ], check=True)
        
        # 清理CSR文件
        os.remove(f'{self.cert_dir}/csr.pem')
        
        print(f"自签名证书已生成：")
        print(f"  证书: {cert_file}")
        print(f"  私钥: {key_file}")
        
        return cert_file, key_file

    def get_ssl_context(self, cert_file, key_file):
        """
        获取SSL上下文

        Args:
            cert_file: 证书文件
            key_file: 私钥文件

        Returns:
            SSL上下文
        """
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        return context


class SystemMonitor:
    """
    系统监控器
    """

    def __init__(self, log_dir='./logs'):
        """
        初始化系统监控器

        Args:
            log_dir: 日志目录
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.monitoring_data = {
            'cpu_usage': [],
            'memory_usage': [],
            'disk_usage': [],
            'network_usage': [],
            'api_response_times': [],
            'strategy_performance': []
        }
        self.running = False

    def start_monitoring(self, interval=60):
        """
        开始监控

        Args:
            interval: 监控间隔（秒）
        """
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        print(f"系统监控已启动，间隔 {interval} 秒")

    def stop_monitoring(self):
        """
        停止监控
        """
        self.running = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()
        print("系统监控已停止")

    def _monitor_loop(self, interval):
        """
        监控循环

        Args:
            interval: 监控间隔（秒）
        """
        while self.running:
            try:
                self._collect_metrics()
                self._save_metrics()
            except Exception as e:
                print(f"监控出错: {e}")
            time.sleep(interval)

    def _collect_metrics(self):
        """
        收集系统指标
        """
        import psutil
        
        # 时间戳
        timestamp = datetime.now().isoformat()
        
        # CPU使用率
        cpu_usage = psutil.cpu_percent(interval=1)
        self.monitoring_data['cpu_usage'].append({
            'timestamp': timestamp,
            'value': cpu_usage
        })
        
        # 内存使用率
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        self.monitoring_data['memory_usage'].append({
            'timestamp': timestamp,
            'value': memory_usage
        })
        
        # 磁盘使用率
        disk = psutil.disk_usage('/')
        disk_usage = disk.percent
        self.monitoring_data['disk_usage'].append({
            'timestamp': timestamp,
            'value': disk_usage
        })
        
        # 网络使用率
        net_io = psutil.net_io_counters()
        self.monitoring_data['network_usage'].append({
            'timestamp': timestamp,
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv
        })
        
        # 限制数据长度
        for key in self.monitoring_data:
            if len(self.monitoring_data[key]) > 1000:
                self.monitoring_data[key] = self.monitoring_data[key][-1000:]

    def _save_metrics(self):
        """
        保存监控数据
        """
        metrics_file = os.path.join(self.log_dir, 'system_metrics.json')
        
        # 保存到文件
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(self.monitoring_data, f, indent=2, ensure_ascii=False)

    def get_metrics(self):
        """
        获取监控数据

        Returns:
            监控数据
        """
        return self.monitoring_data

    def check_health(self):
        """
        检查系统健康状态

        Returns:
            健康状态
        """
        import psutil
        
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'metrics': {
                'cpu': psutil.cpu_percent(interval=1),
                'memory': psutil.virtual_memory().percent,
                'disk': psutil.disk_usage('/').percent
            }
        }
        
        # 检查阈值
        if health['metrics']['cpu'] > 90:
            health['status'] = 'warning'
            health['message'] = 'CPU使用率过高'
        elif health['metrics']['memory'] > 90:
            health['status'] = 'warning'
            health['message'] = '内存使用率过高'
        elif health['metrics']['disk'] > 90:
            health['status'] = 'warning'
            health['message'] = '磁盘使用率过高'
        
        return health


class AlertManager:
    """
    告警管理器
    """

    def __init__(self, log_dir='./logs'):
        """
        初始化告警管理器

        Args:
            log_dir: 日志目录
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.alerts = []

    def add_alert(self, level, message, source):
        """
        添加告警

        Args:
            level: 告警级别 (info, warning, error, critical)
            message: 告警消息
            source: 告警来源
        """
        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            'source': source
        }
        
        self.alerts.append(alert)
        self._save_alert(alert)
        self._notify_alert(alert)
        
        # 限制告警数量
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]

    def _save_alert(self, alert):
        """
        保存告警

        Args:
            alert: 告警信息
        """
        alerts_file = os.path.join(self.log_dir, 'alerts.json')
        
        # 读取现有告警
        existing_alerts = []
        if os.path.exists(alerts_file):
            with open(alerts_file, 'r', encoding='utf-8') as f:
                try:
                    existing_alerts = json.load(f)
                except:
                    pass
        
        # 添加新告警
        existing_alerts.append(alert)
        
        # 限制告警数量
        if len(existing_alerts) > 1000:
            existing_alerts = existing_alerts[-1000:]
        
        # 保存
        with open(alerts_file, 'w', encoding='utf-8') as f:
            json.dump(existing_alerts, f, indent=2, ensure_ascii=False)

    def _notify_alert(self, alert):
        """
        通知告警

        Args:
            alert: 告警信息
        """
        # 这里可以添加邮件、短信等通知方式
        print(f"[{alert['level'].upper()}] {alert['message']} - {alert['source']} - {alert['timestamp']}")

    def get_alerts(self, level=None):
        """
        获取告警

        Args:
            level: 告警级别（可选）

        Returns:
            告警列表
        """
        if level:
            return [alert for alert in self.alerts if alert['level'] == level]
        return self.alerts


if __name__ == '__main__':
    # 测试HTTPS配置
    https_config = HttpsConfig()
    # cert_file, key_file = https_config.generate_self_signed_cert('aurora-quant.local')
    
    # 测试系统监控
    monitor = SystemMonitor()
    monitor.start_monitoring(interval=10)
    
    # 测试告警
    alert_manager = AlertManager()
    alert_manager.add_alert('info', '系统启动', 'system')
    
    # 运行一段时间后停止
    try:
        time.sleep(30)
    finally:
        monitor.stop_monitoring()
        print("监控数据已保存")