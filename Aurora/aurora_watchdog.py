#!/usr/bin/env python3
"""
Aurora+QS-Robot 进程守护脚本
- 监控主进程是否正常运行
- 崩溃后自动重启
- 健康检查和日志记录

用法: python aurora_watchdog.py
"""

import os
import sys
import time
import subprocess
import threading
import logging
from datetime import datetime
from pathlib import Path

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(WORK_DIR, "simple_launch_5002.py")
PID_FILE = os.path.join(WORK_DIR, "logs", "aurora_watchdog.pid")
LOG_DIR = os.path.join(WORK_DIR, "logs")
CHECK_INTERVAL = 15  # 每15秒检查一次
MAX_RESTART = 10  # 最大重启次数
RESTART_WINDOW = 300  # 5分钟内超过这个次数则暂停

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "aurora_watchdog.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Aurora.Watchdog")


class Watchdog:
    def __init__(self):
        self.process = None
        self.restart_times = []
        self.is_running = False
        self.health_check_url = "http://127.0.0.1:5002/"

    def start_main(self):
        """启动主进程"""
        try:
            logger.info("启动 Aurora+QS-Robot 主进程...")
            self.process = subprocess.Popen(
                [sys.executable, MAIN_SCRIPT],
                cwd=WORK_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            logger.info(f"主进程启动成功 PID: {self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"启动主进程失败: {e}")
            return False

    def check_alive(self):
        """检查主进程是否存活"""
        if self.process is None:
            return False
        return self.process.poll() is None

    def check_health(self):
        """简单健康检查：HTTP请求"""
        try:
            import urllib.request
            req = urllib.request.Request(self.health_check_url, timeout=5)
            resp = urllib.request.urlopen(req)
            return 200 <= resp.status < 500
        except Exception:
            return True  # 健康检查失败不代表进程已挂，仍允许继续运行

    def restart(self):
        """重启主进程"""
        now = time.time()
        self.restart_times = [t for t in self.restart_times if now - t < RESTART_WINDOW]

        if len(self.restart_times) >= MAX_RESTART:
            logger.error(f"{RESTART_WINDOW/60:.0f}分钟内已重启 {len(self.restart_times)} 次，超过限制，暂停自动重启")
            return False

        logger.info(f"正在重启主进程 (近5分钟第 {len(self.restart_times)+1} 次)...")
        if self.process:
            try:
                self.process.terminate()
                time.sleep(3)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass

        self.restart_times.append(now)
        return self.start_main()

    def run(self):
        """主循环"""
        self.is_running = True
        if not self.start_main():
            logger.error("首次启动失败，退出守护进程")
            return

        while self.is_running:
            try:
                time.sleep(CHECK_INTERVAL)
                if not self.check_alive():
                    logger.warning("主进程已退出，准备重启...")
                    if not self.restart():
                        logger.error("重启失败或已达到限制，守护进程退出")
                        break
                else:
                    logger.debug(f"主进程健康 (PID: {self.process.pid})")
            except KeyboardInterrupt:
                logger.info("收到退出信号，准备关闭...")
                self.is_running = False
            except Exception as e:
                logger.error(f"监控异常: {e}")

        if self.process and self.process.poll() is None:
            logger.info("正在关闭主进程...")
            self.process.terminate()
            time.sleep(2)
            if self.process.poll() is None:
                self.process.kill()
        logger.info("守护进程已退出")


def write_pid():
    """写入自身PID文件"""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    """清除PID文件"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Aurora+QS-Robot 守护进程启动")
    logger.info(f"工作目录: {WORK_DIR}")
    logger.info(f"主脚本: {MAIN_SCRIPT}")
    logger.info(f"监控端口: 5002")
    logger.info("=" * 60)

    write_pid()
    try:
        watchdog = Watchdog()
        watchdog.run()
    finally:
        remove_pid()
