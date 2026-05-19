#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库维护调度模块
提供定时备份、归档、压缩等数据库维护功能
支持独立运行和集成到主应用
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database_manager import get_database_manager

logger = logging.getLogger(__name__)


class DatabaseMaintenanceScheduler:
    """数据库维护调度器"""

    def __init__(self, db_manager=None, config: Dict = None):
        """
        初始化维护调度器

        Args:
            db_manager: 数据库管理器实例（None则使用全局实例）
            config: 配置字典，支持以下键：
                - backup_interval_hours: 备份间隔（小时），默认24
                - archive_interval_days: 归档间隔（天），默认7
                - archive_retention_days: 归档保留天数，默认90
                - vacuum_interval_days: 压缩间隔（天），默认30
                - backup_dir: 备份目录，默认 data/backups
                - max_backup_count: 最大备份数量，默认10
                - enable_auto_maintenance: 是否启用自动维护，默认True
        """
        self.db = db_manager or get_database_manager()
        self.config = {
            'backup_interval_hours': 24,
            'archive_interval_days': 7,
            'archive_retention_days': 90,
            'vacuum_interval_days': 30,
            'backup_dir': os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'data', 'backups'
            ),
            'max_backup_count': 10,
            'enable_auto_maintenance': True,
        }
        if config:
            self.config.update(config)

        self._running = False
        self._thread = None
        self._last_backup_time = None
        self._last_archive_time = None
        self._last_vacuum_time = None
        self._lock = threading.Lock()

        # 从数据库加载上次维护时间
        self._load_maintenance_times()

    def _load_maintenance_times(self):
        """从数据库加载上次维护时间"""
        try:
            last_backup = self.db.get_config('maintenance_last_backup')
            last_archive = self.db.get_config('maintenance_last_archive')
            last_vacuum = self.db.get_config('maintenance_last_vacuum')

            if last_backup:
                self._last_backup_time = datetime.fromisoformat(last_backup)
            if last_archive:
                self._last_archive_time = datetime.fromisoformat(last_archive)
            if last_vacuum:
                self._last_vacuum_time = datetime.fromisoformat(last_vacuum)
        except Exception as e:
            logger.warning(f"[DBMaintenance] 加载维护时间失败: {e}")

    def _save_maintenance_time(self, key: str, time_value: datetime):
        """保存维护时间到数据库"""
        try:
            self.db.set_config(f'maintenance_{key}', time_value.isoformat(),
                               f'上次{key}时间')
        except Exception as e:
            logger.warning(f"[DBMaintenance] 保存维护时间失败: {e}")

    def _cleanup_old_backups(self):
        """清理旧备份，保留最近N个"""
        try:
            backup_dir = self.config['backup_dir']
            if not os.path.exists(backup_dir):
                return

            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith('trading_system_backup_') and f.endswith('.db')
            ], reverse=True)

            max_count = self.config['max_backup_count']
            if len(backups) > max_count:
                for old_backup in backups[max_count:]:
                    old_path = os.path.join(backup_dir, old_backup)
                    os.remove(old_path)
                    logger.info(f"[DBMaintenance] 删除旧备份: {old_backup}")
        except Exception as e:
            logger.error(f"[DBMaintenance] 清理旧备份失败: {e}")

    def perform_backup(self) -> Optional[str]:
        """
        执行数据库备份

        Returns:
            备份文件路径，失败返回None
        """
        try:
            logger.info("[DBMaintenance] 开始数据库备份...")
            backup_path = self.db.backup_database()

            if backup_path:
                self._last_backup_time = datetime.now()
                self._save_maintenance_time('last_backup', self._last_backup_time)
                self._cleanup_old_backups()
                logger.info(f"[DBMaintenance] 数据库备份完成: {backup_path}")

                # 记录维护日志
                self.db.insert_system_log(
                    'INFO', 'DBMaintenance',
                    f'数据库备份完成: {os.path.basename(backup_path)}',
                    f'大小: {self.db.get_database_size().get("megabytes", 0)} MB'
                )
            else:
                logger.error("[DBMaintenance] 数据库备份失败")

            return backup_path
        except Exception as e:
            logger.error(f"[DBMaintenance] 备份异常: {e}")
            return None

    def perform_archive(self) -> Dict:
        """
        执行旧数据归档

        Returns:
            各表删除的记录数
        """
        try:
            days = self.config['archive_retention_days']
            logger.info(f"[DBMaintenance] 开始归档{days}天前的数据...")

            results = self.db.archive_old_records(days=days)
            total = sum(results.values())

            self._last_archive_time = datetime.now()
            self._save_maintenance_time('last_archive', self._last_archive_time)

            logger.info(f"[DBMaintenance] 归档完成，共删除{total}条记录")

            if total > 0:
                self.db.insert_system_log(
                    'INFO', 'DBMaintenance',
                    f'数据归档完成，删除{total}条旧记录',
                    json.dumps(results, ensure_ascii=False)
                )

            return results
        except Exception as e:
            logger.error(f"[DBMaintenance] 归档异常: {e}")
            return {}

    def perform_vacuum(self) -> bool:
        """
        执行数据库压缩

        Returns:
            是否成功
        """
        try:
            before_size = self.db.get_database_size()
            logger.info(f"[DBMaintenance] 开始数据库压缩 (当前: {before_size.get('megabytes', 0)} MB)...")

            success = self.db.vacuum_database()

            if success:
                after_size = self.db.get_database_size()
                saved = before_size.get('megabytes', 0) - after_size.get('megabytes', 0)

                self._last_vacuum_time = datetime.now()
                self._save_maintenance_time('last_vacuum', self._last_vacuum_time)

                logger.info(f"[DBMaintenance] 数据库压缩完成，释放 {saved:.2f} MB")

                self.db.insert_system_log(
                    'INFO', 'DBMaintenance',
                    f'数据库压缩完成，释放 {saved:.2f} MB',
                    f'压缩前: {before_size.get("megabytes", 0)} MB, 压缩后: {after_size.get("megabytes", 0)} MB'
                )

            return success
        except Exception as e:
            logger.error(f"[DBMaintenance] 压缩异常: {e}")
            return False

    def check_and_maintain(self) -> Dict:
        """
        检查并执行所有需要的维护操作

        Returns:
            维护结果字典
        """
        results = {'backup': None, 'archive': None, 'vacuum': None}
        now = datetime.now()

        with self._lock:
            # 检查是否需要备份
            if (self._last_backup_time is None or
                    (now - self._last_backup_time).total_seconds() >=
                    self.config['backup_interval_hours'] * 3600):
                results['backup'] = self.perform_backup()
            else:
                next_backup = self._last_backup_time + timedelta(
                    hours=self.config['backup_interval_hours'])
                logger.debug(f"[DBMaintenance] 下次备份: {next_backup}")

            # 检查是否需要归档
            if (self._last_archive_time is None or
                    (now - self._last_archive_time).days >=
                    self.config['archive_interval_days']):
                results['archive'] = self.perform_archive()
            else:
                next_archive = self._last_archive_time + timedelta(
                    days=self.config['archive_interval_days'])
                logger.debug(f"[DBMaintenance] 下次归档: {next_archive}")

            # 检查是否需要压缩
            if (self._last_vacuum_time is None or
                    (now - self._last_vacuum_time).days >=
                    self.config['vacuum_interval_days']):
                results['vacuum'] = self.perform_vacuum()
            else:
                next_vacuum = self._last_vacuum_time + timedelta(
                    days=self.config['vacuum_interval_days'])
                logger.debug(f"[DBMaintenance] 下次压缩: {next_vacuum}")

        return results

    def get_maintenance_status(self) -> Dict:
        """
        获取维护状态

        Returns:
            维护状态字典
        """
        now = datetime.now()
        status = {
            'last_backup': self._last_backup_time.isoformat() if self._last_backup_time else None,
            'last_archive': self._last_archive_time.isoformat() if self._last_archive_time else None,
            'last_vacuum': self._last_vacuum_time.isoformat() if self._last_vacuum_time else None,
            'next_backup': None,
            'next_archive': None,
            'next_vacuum': None,
            'is_running': self._running,
            'config': self.config,
        }

        if self._last_backup_time:
            status['next_backup'] = (
                self._last_backup_time + timedelta(hours=self.config['backup_interval_hours'])
            ).isoformat()
        if self._last_archive_time:
            status['next_archive'] = (
                self._last_archive_time + timedelta(days=self.config['archive_interval_days'])
            ).isoformat()
        if self._last_vacuum_time:
            status['next_vacuum'] = (
                self._last_vacuum_time + timedelta(days=self.config['vacuum_interval_days'])
            ).isoformat()

        # 添加数据库大小信息
        try:
            status['database_size'] = self.db.get_database_size()
            status['database_stats'] = self.db.get_database_stats()
        except:
            pass

        return status

    def start_auto_maintenance(self, interval_minutes: int = 60):
        """
        启动自动维护线程

        Args:
            interval_minutes: 检查间隔（分钟）
        """
        if self._running:
            logger.warning("[DBMaintenance] 自动维护已在运行")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._maintenance_loop,
            args=(interval_minutes,),
            daemon=True,
            name='DBMaintenanceThread'
        )
        self._thread.start()
        logger.info(f"[DBMaintenance] 自动维护已启动 (检查间隔: {interval_minutes}分钟)")

    def stop_auto_maintenance(self):
        """停止自动维护线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("[DBMaintenance] 自动维护已停止")

    def _maintenance_loop(self, interval_minutes: int):
        """维护循环"""
        while self._running:
            try:
                self.check_and_maintain()
            except Exception as e:
                logger.error(f"[DBMaintenance] 维护循环异常: {e}")

            # 等待指定间隔
            for _ in range(interval_minutes * 60):
                if not self._running:
                    break
                time.sleep(1)


# ==================== 独立运行入口 ====================

def run_once():
    """单次运行所有维护任务"""
    scheduler = DatabaseMaintenanceScheduler()
    print("=" * 60)
    print("  数据库维护 - 单次运行")
    print("=" * 60)

    results = scheduler.check_and_maintain()

    print(f"\n备份结果: {'成功' if results.get('backup') else '跳过/失败'}")
    if results.get('backup'):
        print(f"  备份路径: {results['backup']}")

    print(f"归档结果: {'成功' if results.get('archive') else '跳过/失败'}")
    if results.get('archive'):
        total = sum(results['archive'].values())
        print(f"  删除记录: {total}")

    print(f"压缩结果: {'成功' if results.get('vacuum') else '跳过/失败'}")

    status = scheduler.get_maintenance_status()
    print(f"\n数据库大小: {status.get('database_size', {}).get('megabytes', 0)} MB")
    print(f"上次备份: {status.get('last_backup', '从未')}")
    print(f"上次归档: {status.get('last_archive', '从未')}")
    print(f"上次压缩: {status.get('last_vacuum', '从未')}")

    print("\n✅ 维护完成！")


def run_daemon(interval_minutes: int = 60):
    """以守护进程模式运行"""
    scheduler = DatabaseMaintenanceScheduler()
    print(f"数据库维护守护进程启动 (检查间隔: {interval_minutes}分钟)")
    print("按 Ctrl+C 停止...")

    try:
        scheduler.start_auto_maintenance(interval_minutes=interval_minutes)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        scheduler.stop_auto_maintenance()
        print("维护守护进程已停止")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='数据库维护工具')
    parser.add_argument('--mode', choices=['once', 'daemon'], default='once',
                        help='运行模式: once=单次运行, daemon=守护进程')
    parser.add_argument('--interval', type=int, default=60,
                        help='守护进程检查间隔（分钟），默认60')
    parser.add_argument('--backup-interval', type=int, default=24,
                        help='备份间隔（小时），默认24')
    parser.add_argument('--archive-interval', type=int, default=7,
                        help='归档间隔（天），默认7')
    parser.add_argument('--retention-days', type=int, default=90,
                        help='归档保留天数，默认90')
    parser.add_argument('--vacuum-interval', type=int, default=30,
                        help='压缩间隔（天），默认30')
    parser.add_argument('--max-backups', type=int, default=10,
                        help='最大备份数量，默认10')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'logs', 'db_maintenance.log'
                ),
                encoding='utf-8'
            )
        ]
    )

    config = {
        'backup_interval_hours': args.backup_interval,
        'archive_interval_days': args.archive_interval,
        'archive_retention_days': args.retention_days,
        'vacuum_interval_days': args.vacuum_interval,
        'max_backup_count': args.max_backups,
    }

    # 设置全局配置
    import utils.db_maintenance as dbm
    dbm.DatabaseMaintenanceScheduler.config_defaults = config

    if args.mode == 'once':
        run_once()
    else:
        run_daemon(interval_minutes=args.interval)
