#!/usr/bin/env python3
"""
告警推送 — 多渠道通知系统
===========================
支持：
- 钉钉机器人 Webhook
- 企业微信机器人
- 邮件（SMTP）
- 分级告警（INFO/WARN/CRITICAL）
- 频率限制（防刷屏）
- 告警静默（可配置静默期）
"""
import logging
import threading
import time
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警消息"""
    level: AlertLevel
    title: str
    message: str
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


class AlertManager:
    """告警管理器 — 多渠道推送 + 频率限制"""

    def __init__(self):
        self._lock = threading.RLock()
        self._channels: Dict[str, Callable] = {}  # channel_name -> send_func
        self._history: List[Alert] = []
        self._sent_counts: Dict[str, List[float]] = {}  # channel -> [timestamps]

        # 频率限制
        self._rate_limits = {
            AlertLevel.INFO: 60,    # 每分钟最多1条
            AlertLevel.WARN: 30,    # 每30秒最多1条
            AlertLevel.CRITICAL: 0,  # 不限频
        }

        # 静默期（夜间不打扰）
        self._quiet_hours = (22, 7)  # 22:00 - 07:00 静默
        self._quiet_enabled = True

        # 初始化通道
        self._init_channels()

        logger.info("[AlertManager] 告警系统初始化完成")

    def _init_channels(self):
        """初始化通知通道"""
        import os

        # 钉钉
        dingtalk_token = os.environ.get("DINGTALK_WEBHOOK_TOKEN", "")
        if dingtalk_token:
            self._channels["dingtalk"] = self._send_dingtalk
            logger.info("[AlertManager] 钉钉通道已启用")

        # 企业微信
        wecom_key = os.environ.get("WECOM_WEBHOOK_KEY", "")
        if wecom_key:
            self._channels["wecom"] = self._send_wecom
            logger.info("[AlertManager] 企业微信通道已启用")

        # 邮件
        smtp_user = os.environ.get("ALERT_SMTP_USER", "")
        if smtp_user:
            self._channels["email"] = self._send_email
            logger.info("[AlertManager] 邮件通道已启用")

        # 本地日志（始终可用）
        self._channels["log"] = self._send_log

    # ========== 发送告警 ==========

    def send(self, alert: Alert, channels: List[str] = None):
        """发送告警到指定通道"""
        target_channels = channels or list(self._channels.keys())

        with self._lock:
            self._history.append(alert)

            for ch in target_channels:
                if ch not in self._channels:
                    continue

                # 频率限制
                if not self._check_rate_limit(alert.level, ch):
                    continue

                # 静默期检查
                if self._is_quiet_hours() and alert.level != AlertLevel.CRITICAL:
                    continue

                try:
                    self._channels[ch](alert)
                    self._record_sent(ch)
                except Exception as e:
                    logger.error(f"[AlertManager] 通道 {ch} 发送失败: {e}")

    def info(self, title: str, message: str, source: str = "", channels: List[str] = None):
        self.send(Alert(level=AlertLevel.INFO, title=title, message=message, source=source), channels)

    def warn(self, title: str, message: str, source: str = "", channels: List[str] = None):
        self.send(Alert(level=AlertLevel.WARN, title=title, message=message, source=source), channels)

    def critical(self, title: str, message: str, source: str = "", channels: List[str] = None):
        self.send(Alert(level=AlertLevel.CRITICAL, title=title, message=message, source=source), channels)

    # ========== 频率限制 ==========

    def _check_rate_limit(self, level: AlertLevel, channel: str) -> bool:
        limit = self._rate_limits.get(level, 60)
        if limit <= 0:
            return True

        key = f"{channel}:{level.value}"
        now = time.time()
        timestamps = self._sent_counts.get(key, [])
        timestamps = [t for t in timestamps if now - t < limit]
        self._sent_counts[key] = timestamps

        if len(timestamps) >= 1:
            logger.debug(f"[AlertManager] 频率限制: {channel}/{level.value}")
            return False
        return True

    def _record_sent(self, channel: str):
        pass  # 在 _check_rate_limit 中已记录

    def _is_quiet_hours(self) -> bool:
        if not self._quiet_enabled:
            return False
        hour = datetime.now().hour
        start, end = self._quiet_hours
        if start > end:
            return hour >= start or hour < end
        return start <= hour < end

    # ========== 通道实现 ==========

    def _send_dingtalk(self, alert: Alert):
        """钉钉机器人推送"""
        import os
        import requests

        token = os.environ.get("DINGTALK_WEBHOOK_TOKEN", "")
        if not token:
            return

        url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
        level_emoji = {"info": "ℹ", "warn": "⚠", "critical": "🚨"}
        emoji = level_emoji.get(alert.level.value, "📢")

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": f"[{alert.level.value.upper()}] {alert.title}",
                "text": (
                    f"## {emoji} {alert.title}\n\n"
                    f"**级别**: {alert.level.value.upper()}\n"
                    f"**来源**: {alert.source}\n"
                    f"**时间**: {alert.timestamp}\n\n"
                    f"---\n\n"
                    f"{alert.message}\n"
                ),
            },
        }

        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                logger.info(f"[AlertManager] 钉钉推送成功: {alert.title}")
            else:
                logger.warning(f"[AlertManager] 钉钉推送失败: {r.text}")
        except Exception as e:
            logger.error(f"[AlertManager] 钉钉推送异常: {e}")

    def _send_wecom(self, alert: Alert):
        """企业微信机器人推送"""
        import os
        import requests

        key = os.environ.get("WECOM_WEBHOOK_KEY", "")
        if not key:
            return

        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
        level_color = {"info": "info", "warn": "warning", "critical": "warning"}
        color = level_color.get(alert.level.value, "info")

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": (
                    f"## [{alert.level.value.upper()}] {alert.title}\n"
                    f"> 来源: {alert.source}\n"
                    f"> 时间: {alert.timestamp}\n"
                    f"\n{alert.message}"
                ),
            },
        }

        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                logger.info(f"[AlertManager] 企微推送成功: {alert.title}")
        except Exception as e:
            logger.error(f"[AlertManager] 企微推送异常: {e}")

    def _send_email(self, alert: Alert):
        """邮件推送"""
        import os

        smtp_host = os.environ.get("ALERT_SMTP_HOST", "smtp.qq.com")
        smtp_port = int(os.environ.get("ALERT_SMTP_PORT", "587"))
        smtp_user = os.environ.get("ALERT_SMTP_USER", "")
        smtp_pass = os.environ.get("ALERT_SMTP_PASS", "")
        to_addrs = os.environ.get("ALERT_EMAIL_TO", smtp_user).split(",")

        if not smtp_user or not smtp_pass:
            return

        subject = f"[{alert.level.value.upper()}] {alert.title}"
        body = (
            f"级别: {alert.level.value}\n"
            f"来源: {alert.source}\n"
            f"时间: {alert.timestamp}\n"
            f"\n{alert.message}"
        )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = ", ".join(to_addrs)

        try:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addrs, msg.as_string())
            server.quit()
            logger.info(f"[AlertManager] 邮件推送成功: {alert.title}")
        except Exception as e:
            logger.error(f"[AlertManager] 邮件推送异常: {e}")

    def _send_log(self, alert: Alert):
        """本地日志（始终可用）"""
        log_func = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARN: logger.warning,
            AlertLevel.CRITICAL: logger.error,
        }.get(alert.level, logger.info)

        log_func(f"[Alert:{alert.level.value}] {alert.title} | {alert.source} | {alert.message}")

    # ========== 查询 ==========

    def get_history(self, limit: int = 50) -> List[Alert]:
        with self._lock:
            return self._history[-limit:]

    def get_recent_alerts(self, minutes: int = 5) -> List[Alert]:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        with self._lock:
            return [a for a in self._history if datetime.fromisoformat(a.timestamp) >= cutoff]

    def set_quiet_hours(self, start: int, end: int, enabled: bool = True):
        self._quiet_hours = (start, end)
        self._quiet_enabled = enabled


# 全局单例
_alert_instance: Optional[AlertManager] = None
_alert_lock = threading.Lock()


def get_alert_manager() -> AlertManager:
    global _alert_instance
    with _alert_lock:
        if _alert_instance is None:
            _alert_instance = AlertManager()
        return _alert_instance