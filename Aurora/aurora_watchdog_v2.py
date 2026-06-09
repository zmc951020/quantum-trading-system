#!/usr/bin/env python3
"""
Aurora+QS-Robot 进程守护脚本 (Windows优化版)
- 监控主进程是否正常运行
- 崩溃后自动重启
- 健康检查和日志记录

用法: python aurora_watchdog_v2.py
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime

# ========== 配置 ==========
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(WORK_DIR, "simple_launch_5002.py")
LOG_DIR = os.path.join(WORK_DIR, "logs")
PID_FILE = os.path.join(LOG_DIR, "aurora_watchdog.pid")
HEALTH_CHECK_URL = "http://127.0.0.1:5002/"
CHECK_INTERVAL = 20        # 每20秒检查一次
HEALTH_CHECK_INTERVAL = 60  # 每60秒做一次HTTP健康检查
MAX_RESTARTS = 100         # 最大重启次数
RESTART_WINDOW = 600       # 10分钟内超过这个次数则暂停
STARTUP_WAIT = 30          # 启动等待时间（秒）

os.makedirs(LOG_DIR, exist_ok=True)

# ========== 日志配置 ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, "aurora_watchdog.log"),
            encoding='utf-8'
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Watchdog")


class AuroraWatchdog:
    def __init__(self):
        self.process = None
        self.restart_times = []
        self.is_running = False
        self.last_health_check = 0

    def start_main(self):
        """启动主进程 - Windows优化版"""
        try:
            logger.info("=" * 50)
            logger.info(f"启动 Aurora+QS-Robot 主进程...")
            logger.info(f"  脚本: {MAIN_SCRIPT}")
            logger.info(f"  工作目录: {WORK_DIR}")

            # Windows: 不捕获输出，让子进程独立运行
            startupinfo = None
            creationflags = 0
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = 0x00000008  # DETACHED_PROCESS

            # 不重定向stdout/stderr，让子进程自己管理
            self.process = subprocess.Popen(
                [sys.executable, MAIN_SCRIPT],
                cwd=WORK_DIR,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            logger.info(f"✅ 主进程启动成功 PID: {self.process.pid}")
            logger.info(f"   等待 {STARTUP_WAIT} 秒让服务初始化...")

            # 等待启动
            time.sleep(STARTUP_WAIT)

            # 检查是否真的启动成功
            if self.process.poll() is not None:
                logger.error(f"❌ 主进程启动后立即退出 (退出码: {self.process.returncode})")
                self.process = None
                return False

            # HTTP健康检查
            if self._http_health_check():
                logger.info("✅ HTTP健康检查通过")
            else:
                logger.warning("⚠️  HTTP健康检查失败，但进程仍在运行")

            return True

        except Exception as e:
            logger.error(f"❌ 启动主进程失败: {e}")
            return False

    def check_alive(self):
        """检查主进程是否存活"""
        if self.process is None:
            return False
        return self.process.poll() is None

    def _http_health_check(self):
        """HTTP健康检查"""
        try:
            import urllib.request
            req = urllib.request.Request(HEALTH_CHECK_URL, timeout=10)
            resp = urllib.request.urlopen(req, timeout=10)
            return 200 <= resp.status < 500
        except Exception:
            return False

    def check_restart_rate(self):
        """检查重启频率"""
        now = time.time()
        self.restart_times = [t for t in self.restart_times if now - t < RESTART_WINDOW]

        if len(self.restart_times) >= MAX_RESTARTS:
            logger.error(
                f"❌ {RESTART_WINDOW/60:.0f}分钟内已重启 {len(self.restart_times)} 次，"
                f"超过限制，暂停自动重启"
            )
            return False
        return True

    def restart(self):
        """重启主进程"""
        if not self.check_restart_rate():
            return False

        logger.info(
            f"🔄 正在重启主进程 "
            f"(近{RESTART_WINDOW/60:.0f}分钟第 {len(self.restart_times)+1} 次)..."
        )

        # 停止旧进程
        if self.process:
            try:
                if self.process.poll() is None:
                    logger.info("   终止旧进程...")
                    self.process.terminate()
                    time.sleep(5)
                    if self.process.poll() is None:
                        logger.warning("   强制终止...")
                        self.process.kill()
                        time.sleep(2)
            except Exception as e:
                logger.warning(f"   终止进程时出错: {e}")

        self.restart_times.append(time.time())
        return self.start_main()

    def run(self):
        """主监控循环"""
        self.is_running = True
        self.last_health_check = time.time()

        logger.info("=" * 50)
        logger.info("🚀 Aurora+QS-Robot 守护进程启动")
        logger.info(f"   监控端口: 5002")
        logger.info(f"   检查间隔: {CHECK_INTERVAL}秒")
        logger.info(f"   健康检查间隔: {HEALTH_CHECK_INTERVAL}秒")
        logger.info(f"   重启窗口: {RESTART_WINDOW/60:.0f}分钟, 最大重启: {MAX_RESTARTS}次")
        logger.info("=" * 50)

        # 写入PID文件
        try:
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

        # 首次启动
        if not self.start_main():
            logger.error("❌ 首次启动失败，退出守护进程")
            self._cleanup()
            return

        # 主循环
        check_count = 0
        while self.is_running:
            try:
                time.sleep(CHECK_INTERVAL)
                check_count += 1

                if not self.check_alive():
                    logger.warning("⚠️  主进程已退出，准备重启...")
                    if not self.restart():
                        logger.error("❌ 重启失败或已达到限制，守护进程退出")
                        break
                else:
                    # 定期做健康检查
                    now = time.time()
                    if now - self.last_health_check > HEALTH_CHECK_INTERVAL:
                        self.last_health_check = now
                        if self._http_health_check():
                            logger.info(f"✅ 健康检查通过 (PID: {self.process.pid})")
                        else:
                            logger.warning(f"⚠️  健康检查失败，准备重启...")
                            if not self.restart():
                                logger.error("❌ 重启失败或已达到限制，守护进程退出")
                                break

            except KeyboardInterrupt:
                logger.info("收到退出信号 (Ctrl+C)，准备关闭...")
                self.is_running = False
            except Exception as e:
                logger.error(f"❌ 监控异常: {e}")

        # 清理
        self._cleanup()
        logger.info("✅ 守护进程已退出")

    def _cleanup(self):
        """清理"""
        try:
            if self.process and self.process.poll() is None:
                logger.info("正在关闭主进程...")
                self.process.terminate()
                time.sleep(3)
                if self.process.poll() is None:
                    self.process.kill()
        except Exception:
            pass

        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception:
            pass


def main():
    watchdog = AuroraWatchdog()
    watchdog.run()


if __name__ == "__main__":
    main()
