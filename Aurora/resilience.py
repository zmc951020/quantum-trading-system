# coding: utf-8
"""
容灾增强增益模块 — Watchdog + 优雅停机 + 心跳监控
======================================================
增益性补充，在系统启动/运行时并行辅助。
不修改原有代码。

功能：
  - SystemWatchdog: 主循环心跳监控，超时自动重启
  - GracefulShutdown: 信号捕获（SIGTERM/SIGINT），等待当前任务完成后安全退出
  - HealthPulse: 健康心跳上报（文件/HTTP endpoint）
  - 异常恢复：记录崩溃前的状态快照
"""

import logging
import os
import signal
import threading
import time
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. 看门狗（主循环心跳监控）
# ─────────────────────────────────────────────

class SystemWatchdog:
    """
    看门狗 — 监控主循环是否存活

    使用方式：
        wd = SystemWatchdog(timeout_sec=120, on_timeout=restart_callback)
        wd.start()

        # 主循环中：
        while running:
            do_work()
            wd.feed()  # 喂狗
    """

    def __init__(self, timeout_sec: float = 120.0, on_timeout: Optional[Callable] = None):
        """
        Args:
            timeout_sec: 超过此秒数未喂狗即超时
            on_timeout: 超时回调 (例如重启服务)
        """
        self._timeout = timeout_sec
        self._last_feed = time.time()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_timeout = on_timeout
        self._timeout_count = 0

    def start(self):
        self._running = True
        self._feed()  # 初始化
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="watchdog")
        self._thread.start()
        logger.info("看门狗已启动，超时阈值: %.0f秒", self._timeout)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("看门狗已停止")

    def feed(self):
        """喂狗 — 主循环每轮调用"""
        with self._lock:
            self._last_feed = time.time()

    def _feed(self):
        self._last_feed = time.time()

    def _watch_loop(self):
        while self._running:
            time.sleep(max(1.0, self._timeout / 4))  # 每 timeout/4 检查一次
            with self._lock:
                elapsed = time.time() - self._last_feed
            if elapsed > self._timeout:
                self._timeout_count += 1
                logger.critical(
                    "看门狗超时! 距上次喂狗 %.0f 秒 (阈值 %.0f 秒), 第 %d 次超时",
                    elapsed, self._timeout, self._timeout_count
                )
                if self._on_timeout:
                    try:
                        self._on_timeout()
                    except Exception as e:
                        logger.error("看门狗超时回调执行失败: %s", e)

    @property
    def status(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self._last_feed
        return {
            "last_feed_ago_sec": round(elapsed, 1),
            "timeout_sec": self._timeout,
            "timeout_count": self._timeout_count,
            "healthy": elapsed < self._timeout,
        }


# ─────────────────────────────────────────────
# 2. 优雅停机
# ─────────────────────────────────────────────

class GracefulShutdown:
    """
    优雅停机 — 接收 SIGTERM/SIGINT 后：
      1. 停止接收新订单
      2. 等待当前订单执行完毕
      3. 保存状态快照
      4. 关闭连接、退出

    使用方式：
        gs = GracefulShutdown(on_shutdown=cleanup_callback)
        gs.register_signals()

        # 主循环中：
        while gs.should_continue():
            ...
    """

    def __init__(self, on_shutdown: Optional[Callable] = None, wait_sec: float = 30.0):
        self._shutdown_flag = threading.Event()
        self._on_shutdown = on_shutdown
        self._wait_sec = wait_sec
        self._registered = False
        self._shutdown_initiated = False

    def register_signals(self):
        """注册信号处理器"""
        if self._registered:
            return
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self._registered = True
        logger.info("优雅停机信号处理器已注册 (SIGTERM/SIGINT)")

    def _signal_handler(self, signum, frame):
        sig_name = signal.Signals(signum).name
        logger.warning("收到信号 %s，开始优雅停机...", sig_name)
        self.initiate_shutdown()

    def initiate_shutdown(self):
        """主动触发优雅停机"""
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        logger.critical("优雅停机已触发！停止接收新订单...")

        # 保存状态快照
        self._save_snapshot()

        # 执行回调
        if self._on_shutdown:
            try:
                self._on_shutdown()
            except Exception as e:
                logger.error("停机回调失败: %s", e)

        # 等待正在进行的任务完成
        logger.info("等待最多 %.0f 秒让当前任务完成...", self._wait_sec)
        time.sleep(min(5, self._wait_sec))  # 给当前任务一点缓冲

        self._shutdown_flag.set()

    def should_continue(self) -> bool:
        """主循环检查 — 返回 False 则退出"""
        return not self._shutdown_flag.is_set()

    def is_shutting_down(self) -> bool:
        return self._shutdown_initiated

    def _save_snapshot(self):
        """保存崩溃前状态快照"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "reason": "graceful_shutdown",
            "pid": os.getpid(),
        }
        try:
            with open("shutdown_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logger.info("停机快照已保存: shutdown_snapshot.json")
        except Exception as e:
            logger.error("保存快照失败: %s", e)


# ─────────────────────────────────────────────
# 3. 健康心跳
# ─────────────────────────────────────────────

class HealthPulse:
    """
    健康心跳 — 定期向文件写入心跳，供监控系统（Prometheus/Grafana/外部脚本）读取

    使用方式：
        hp = HealthPulse(pulse_file="health.json")
        hp.start()

        # 主循环每次迭代后：
        hp.update(loop_count=123, last_trade_time=..., active_positions=5)
    """

    def __init__(self, pulse_file: str = "health_pulse.json", interval_sec: float = 5.0):
        self._pulse_file = pulse_file
        self._interval = interval_sec
        self._data: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="health-pulse")
        self._thread.start()
        logger.info("健康心跳已启动，文件: %s", self._pulse_file)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def update(self, **kwargs):
        """更新心跳数据"""
        with self._lock:
            self._data.update(kwargs)
            self._data["last_update"] = datetime.now().isoformat()

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            with self._lock:
                payload = dict(self._data)
                payload["heartbeat_at"] = datetime.now().isoformat()
                payload["pid"] = os.getpid()
            try:
                with open(self._pulse_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("心跳写入失败: %s", e)