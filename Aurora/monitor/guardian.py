# coding: utf-8
"""
进程守护与状态快照模块
======================
功能:
  - 主进程健康心跳监控
  - 子进程/线程存活检测
  - 内存/CPU超限告警
  - 交易状态快照（定时保存，支持断点恢复）
  - 自动重启异常进程
  - 告警事件推送（企业微信/邮件/日志）
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_GUARDIAN_CONFIG = {
    "heartbeat_interval": 5,         # 心跳间隔秒
    "snapshot_interval": 60,         # 快照间隔秒
    "max_memory_mb": 4096,           # 内存上限 MB
    "max_cpu_percent": 90,           # CPU上限 %
    "max_consecutive_timeouts": 3,   # 连续超时次数触发重启
    "auto_restart": False,           # 是否自动重启（默认关闭，需要人工确认）
    "snapshot_dir": "snapshots",     # 快照保存目录
    "alert_channels": ["log"],       # 告警渠道: log, wework, email
}


@dataclass
class HealthStatus:
    """健康状态快照"""
    timestamp: str = ""
    process_id: int = 0
    uptime_seconds: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    active_threads: int = 0
    # 交易状态
    pending_orders: int = 0
    total_positions: int = 0
    daily_pnl: float = 0.0
    circuit_breaker_state: str = "normal"
    # 异常计数
    error_count: int = 0
    warning_count: int = 0
    last_error: str = ""
    # 额外数据
    extra: Dict[str, Any] = field(default_factory=dict)


class AlertManager:
    """告警管理器 — 多通道推送"""
    
    def __init__(self, channels: List[str] = None):
        self._channels = channels or ["log"]
        self._alert_history: List[Dict] = []
        self._max_history = 500
        self._lock = threading.Lock()
        # 告警去重（相同类型5分钟内不重复）
        self._last_alert_time: Dict[str, float] = {}
        self._alert_cooldown = 300  # 5分钟

    def send(self, alert_type: str, message: str, level: str = "WARNING", data: Dict = None):
        """
        发送告警
        
        Args:
            alert_type: 告警类型标识
            message: 告警内容
            level: CRITICAL / ERROR / WARNING / INFO
            data: 附加数据
        """
        now = time.time()
        
        # 去重检查
        if alert_type in self._last_alert_time:
            if now - self._last_alert_time[alert_type] < self._alert_cooldown:
                return  # 冷却期内跳过
        self._last_alert_time[alert_type] = now
        
        alert = {
            "type": alert_type,
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        
        with self._lock:
            self._alert_history.append(alert)
            if len(self._alert_history) > self._max_history:
                self._alert_history = self._alert_history[-self._max_history:]
        
        # 根据渠道推送
        for channel in self._channels:
            if channel == "log":
                self._send_log(alert)
            elif channel == "wework":
                self._send_wework(alert)
            elif channel == "email":
                self._send_email(alert)
            elif channel == "stdout":
                self._send_stdout(alert)

    def _send_log(self, alert: Dict):
        level = alert["level"]
        msg = f"[{alert['type']}] {alert['message']}"
        if level == "CRITICAL":
            logger.critical(msg)
        elif level == "ERROR":
            logger.error(msg)
        elif level == "WARNING":
            logger.warning(msg)
        else:
            logger.info(msg)

    def _send_stdout(self, alert: Dict):
        """控制台输出告警"""
        prefix = {"CRITICAL": "🔴", "ERROR": "🟠", "WARNING": "🟡", "INFO": "🔵"}.get(alert["level"], "⚪")
        print(f"{prefix} [{alert['type']}] {alert['message']}", file=sys.stderr)

    def _send_wework(self, alert: Dict):
        """企业微信推送"""
        try:
            # 尝试使用 wework-bot MCP 服务推送
            import json as _json
            msg_content = f"**{alert['type']}** [{alert['level']}]\n{alert['message']}\n时间: {alert['timestamp']}"
            # 如果配置了webhook，在这里调用
            webhook_url = os.environ.get("WEWORK_WEBHOOK_URL", "")
            if webhook_url:
                import urllib.request
                payload = _json.dumps({
                    "msgtype": "markdown",
                    "markdown": {"content": msg_content}
                }).encode("utf-8")
                req = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.debug("企业微信告警推送失败: %s", e)

    def _send_email(self, alert: Dict):
        """邮件告警"""
        try:
            smtp_config = {
                "host": os.environ.get("SMTP_HOST", ""),
                "port": int(os.environ.get("SMTP_PORT", "587")),
                "user": os.environ.get("SMTP_USER", ""),
                "password": os.environ.get("SMTP_PASSWORD", ""),
                "to": os.environ.get("ALERT_EMAIL_TO", ""),
            }
            if not all([smtp_config["host"], smtp_config["user"], smtp_config["to"]]):
                return  # 未配置邮件
            
            import smtplib
            from email.mime.text import MIMEText
            
            subject = f"[Aurora风控] {alert['type']} - {alert['level']}"
            body = f"{alert['message']}\n时间: {alert['timestamp']}"
            
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = smtp_config["user"]
            msg["To"] = smtp_config["to"]
            
            with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=10) as server:
                server.starttls()
                server.login(smtp_config["user"], smtp_config["password"])
                server.sendmail(smtp_config["user"], [smtp_config["to"]], msg.as_string())
        except Exception as e:
            logger.debug("邮件告警推送失败: %s", e)

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return list(self._alert_history[-limit:])


class ProcessGuardian:
    """
    进程守护者
    ==========
    独立线程运行，持续监控主进程和子组件的健康状态。
    """

    def __init__(
        self,
        config: Dict = None,
        alert_manager: AlertManager = None,
        state_collector: Callable = None,
    ):
        self._config = {**DEFAULT_GUARDIAN_CONFIG, **(config or {})}
        self._alert = alert_manager or AlertManager()
        self._state_collector = state_collector  # 状态采集回调
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._heartbeat_count: int = 0
        self._snapshot_count: int = 0
        self._consecutive_timeouts: int = 0
        self._last_heartbeat: float = 0.0
        self._snapshots: List[HealthStatus] = []
        self._lock = threading.Lock()
        self._error_count: int = 0
        
        # 子组件注册
        self._components: Dict[str, Dict] = {}  # name -> {"check_fn": callable, "restart_fn": callable}

        # 确保快照目录存在
        snap_dir = self._config["snapshot_dir"]
        if not os.path.exists(snap_dir):
            os.makedirs(snap_dir, exist_ok=True)

    def register_component(self, name: str, check_fn: Callable, restart_fn: Callable = None):
        """
        注册监控组件
        
        Args:
            name: 组件名称
            check_fn: 健康检查函数，返回 (bool, str)
            restart_fn: 重启函数
        """
        self._components[name] = {"check_fn": check_fn, "restart_fn": restart_fn}
        logger.info("注册监控组件: %s", name)

    def start(self):
        """启动守护线程"""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._guardian_loop, daemon=True, name="Guardian")
        self._thread.start()
        logger.info("进程守护已启动 PID=%d", os.getpid())
        self._alert.send("GUARDIAN_START", f"进程守护启动 PID={os.getpid()}", "INFO")

    def stop(self):
        """停止守护线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("进程守护已停止")

    def heartbeat(self):
        """供主进程调用，报告心跳"""
        self._last_heartbeat = time.time()
        self._consecutive_timeouts = 0

    def _guardian_loop(self):
        """守护主循环"""
        while self._running:
            try:
                self._check_health()
                # 定时快照
                if self._heartbeat_count % max(1, self._config["snapshot_interval"] // self._config["heartbeat_interval"]) == 0:
                    self._take_snapshot()
                self._heartbeat_count += 1
            except Exception as e:
                self._error_count += 1
                logger.error("守护循环异常: %s\n%s", e, traceback.format_exc())
            time.sleep(self._config["heartbeat_interval"])

    def _check_health(self):
        """健康检查"""
        now = time.time()
        issues = []

        # 1. 主进程心跳超时检测
        heartbeat_timeout = self._config["heartbeat_interval"] * 3
        if self._last_heartbeat > 0 and now - self._last_heartbeat > heartbeat_timeout:
            self._consecutive_timeouts += 1
            issues.append(f"主进程心跳超时 (连续{self._consecutive_timeouts}次)")
            if self._consecutive_timeouts >= self._config["max_consecutive_timeouts"]:
                self._alert.send(
                    "MAIN_PROCESS_TIMEOUT",
                    f"主进程连续{self._consecutive_timeouts}次心跳超时，可能已挂死",
                    "CRITICAL",
                )

        # 2. 内存检查
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / 1024 / 1024
            if mem_mb > self._config["max_memory_mb"]:
                issues.append(f"内存超限: {mem_mb:.0f}MB > {self._config['max_memory_mb']}MB")
                self._alert.send(
                    "MEMORY_HIGH",
                    f"内存使用 {mem_mb:.0f}MB 超限 {self._config['max_memory_mb']}MB",
                    "WARNING",
                )
            cpu_pct = process.cpu_percent(interval=0.1)
            if cpu_pct > self._config["max_cpu_percent"]:
                issues.append(f"CPU超限: {cpu_pct:.1f}% > {self._config['max_cpu_percent']}%")
        except ImportError:
            pass  # psutil 未安装

        # 3. 子组件健康检查
        for name, comp in self._components.items():
            try:
                ok, msg = comp["check_fn"]()
                if not ok:
                    issues.append(f"组件 {name}: {msg}")
                    self._alert.send("COMPONENT_UNHEALTHY", f"组件 {name} 异常: {msg}", "ERROR")
                    if self._config["auto_restart"] and comp.get("restart_fn"):
                        try:
                            comp["restart_fn"]()
                            self._alert.send("COMPONENT_RESTART", f"组件 {name} 已自动重启", "WARNING")
                        except Exception as re:
                            self._alert.send("COMPONENT_RESTART_FAIL", f"组件 {name} 重启失败: {re}", "CRITICAL")
            except Exception as ce:
                issues.append(f"组件 {name} 检查异常: {ce}")

        # 4. 总体健康状态判断
        if issues:
            logger.warning("健康检查发现 %d 个问题: %s", len(issues), "; ".join(issues))

    def _take_snapshot(self):
        """保存状态快照"""
        snap = HealthStatus(
            timestamp=datetime.now().isoformat(),
            process_id=os.getpid(),
            uptime_seconds=time.time() - self._start_time,
            memory_mb=0.0,
            cpu_percent=0.0,
            active_threads=threading.active_count(),
            error_count=self._error_count,
            last_error="",
        )

        # 尝试获取详细资源用量
        try:
            import psutil
            process = psutil.Process(os.getpid())
            snap.memory_mb = process.memory_info().rss / 1024 / 1024
            snap.cpu_percent = process.cpu_percent(interval=0.1)
        except ImportError:
            pass

        # 如果有状态采集回调，收集交易状态
        if self._state_collector:
            try:
                state = self._state_collector()
                if isinstance(state, dict):
                    snap.pending_orders = state.get("pending_orders", 0)
                    snap.total_positions = state.get("total_positions", 0)
                    snap.daily_pnl = state.get("daily_pnl", 0.0)
                    snap.circuit_breaker_state = state.get("circuit_breaker", "normal")
                    snap.extra = state.get("extra", {})
            except Exception as e:
                logger.debug("状态采集失败: %s", e)

        with self._lock:
            self._snapshots.append(snap)
            # 保留最近100个快照
            if len(self._snapshots) > 100:
                self._snapshots = self._snapshots[-100:]

        self._snapshot_count += 1

        # 持久化到磁盘
        snap_file = os.path.join(
            self._config["snapshot_dir"],
            f"snapshot_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        try:
            with open(snap_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snap), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("快照写入失败: %s", e)

    def get_latest_snapshot(self) -> Optional[HealthStatus]:
        """获取最近快照"""
        with self._lock:
            return self._snapshots[-1] if self._snapshots else None

    def get_status(self) -> Dict[str, Any]:
        """获取守护状态"""
        snap = self.get_latest_snapshot()
        return {
            "running": self._running,
            "uptime_seconds": time.time() - self._start_time if self._start_time > 0 else 0,
            "heartbeat_count": self._heartbeat_count,
            "snapshot_count": self._snapshot_count,
            "consecutive_timeouts": self._consecutive_timeouts,
            "components": list(self._components.keys()),
            "latest_snapshot": asdict(snap) if snap else None,
            "alert_count": len(self._alert.get_recent_alerts(0)),
        }

    def load_latest_snapshot_from_disk(self) -> Optional[Dict]:
        """从磁盘加载最近快照（用于断点恢复）"""
        snap_dir = self._config["snapshot_dir"]
        if not os.path.exists(snap_dir):
            return None
        files = sorted(
            [f for f in os.listdir(snap_dir) if f.endswith(".jsonl")],
            reverse=True
        )
        for f in files:
            path = os.path.join(snap_dir, f)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
                if lines:
                    return json.loads(lines[-1])
            except Exception:
                continue
        return None


# 方便外部使用的信号监控
class SignalHandler:
    """信号处理器 — 优雅退出"""
    
    def __init__(self, on_shutdown: Callable = None):
        self._on_shutdown = on_shutdown or (lambda: None)
        self._received_signal = False
        
    def register(self):
        """注册信号处理器"""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        if hasattr(signal, 'SIGBREAK'):  # Windows
            signal.signal(signal.SIGBREAK, self._handle_signal)
        logger.info("信号处理器已注册 (SIGINT/SIGTERM)")
    
    def _handle_signal(self, signum, frame):
        if self._received_signal:
            logger.warning("收到第二次信号，强制退出")
            os._exit(1)
        self._received_signal = True
        logger.info("收到退出信号 %d，开始优雅关闭...", signum)
        try:
            self._on_shutdown()
        except Exception as e:
            logger.error("关闭回调异常: %s", e)
        sys.exit(0)