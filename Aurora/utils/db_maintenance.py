#!/usr/bin/env python3
"""
数据库自动维护调度器 (Database Maintenance Scheduler)
====================================================
Aurora 量化交易系统 - 数据库备份/归档/压缩的自动化调度模块

功能：
1. 定时自动备份数据库（可配置间隔和保留份数）
2. 旧数据自动归档（将过期数据移到归档表）
3. 定期 VACUUM 压缩和空间回收
4. 维护状态查询和历史记录
5. 与 system_switcher 和 module_registry 联动

被引用于: visualization.py, production_start.py, main.py, real_time_trading.py, cron_backup.ps1/.sh
"""

import os
import sys
import json
import shutil
import sqlite3
import logging
import threading
import time as _time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)


class DatabaseMaintenanceScheduler:
    """
    数据库自动维护调度器
    
    提供自动备份、归档和压缩功能的定时调度。
    支持手动触发和自动定时两种模式。
    采用线程安全的单例模式。
    
    用法:
        scheduler = DatabaseMaintenanceScheduler(db_path='path/to/db')
        scheduler.start_auto_maintenance()  # 启动自动维护
        scheduler.stop_auto_maintenance()   # 停止自动维护
        scheduler.perform_backup()           # 手动备份
        scheduler.perform_archive()          # 手动归档
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = None, config: Dict = None):
        """
        初始化调度器
        
        Args:
            db_path: 数据库文件路径（默认使用 trading_system.db）
            config: 维护配置（可选，覆盖默认值）
        """
        if getattr(self, '_initialized', False):
            return
        
        self._initialized = True
        
        # 确定数据库路径
        if db_path:
            self.db_path = db_path
        else:
            # 查找项目根目录下的数据库（多种尝试方式）
            project_root = os.getcwd()
            search_paths = [
                os.path.join(project_root, 'aurora_backtest.db'),
                os.path.join(project_root, 'data', 'trading_system.db'),
                os.path.join(project_root, 'trading_system.db'),
            ]
            self.db_path = ''
            for candidate in search_paths:
                if os.path.exists(candidate):
                    self.db_path = candidate
                    break
            if not self.db_path:
                self.db_path = search_paths[0]  # 回退到默认路径
        
        # 确保数据库路径是绝对路径
        self.db_path = os.path.abspath(self.db_path)
        
        # 默认配置
        self.config = {
            'backup_interval_hours': 24,          # 备份间隔（小时）
            'archive_interval_hours': 6,          # 归档间隔（小时）
            'vacuum_interval_hours': 12,          # 压缩间隔（小时）
            'max_backups': 7,                     # 最大保留备份份数
            'archive_days': 90,                   # 归档多少天以前的数据
            'backup_dir': None,                   # 备份目录（None=自动创建）
            'enable_auto_maintenance': True,      # 是否启用自动维护
            'archive_tables': [                   # 需要归档的表配置
                {'table': 'system_logs', 'date_col': 'timestamp', 'keep_days': 90},
                {'table': 'health_checks', 'date_col': 'timestamp', 'keep_days': 90},
                {'table': 'security_events', 'date_col': 'timestamp', 'keep_days': 90},
                {'table': 'trade_records', 'date_col': 'timestamp', 'keep_days': 90},
            ],
        }
        
        # 合并用户配置
        if config:
            self.config.update(config)
        
        # 备份目录
        if not self.config['backup_dir']:
            self.config['backup_dir'] = os.path.join(
                os.path.dirname(self.db_path), 'backups'
            )
        
        # 维护状态
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        self._maintenance_status = {
            'is_running': False,
            'last_backup': None,
            'last_archive': None,
            'last_vacuum': None,
            'next_backup': None,
            'next_archive': None,
            'next_vacuum': None,
            'database_size': {},
            'total_backups': 0,
            'failed_backups': 0,
        }
        
        # 确保目录存在
        os.makedirs(self.config['backup_dir'], exist_ok=True)
        
        logger.info(f"[DB-Maintenance] 调度器已初始化 (db_path={self.db_path})")
    
    # ================================================================
    #  数据库连接辅助
    # ================================================================
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def _get_db_size(self) -> Dict[str, Any]:
        """获取数据库文件大小信息"""
        result = {
            'path': self.db_path,
            'exists': False,
            'size_bytes': 0,
            'megabytes': 0,
        }
        if os.path.exists(self.db_path):
            size_bytes = os.path.getsize(self.db_path)
            result.update({
                'exists': True,
                'size_bytes': size_bytes,
                'megabytes': round(size_bytes / (1024 * 1024), 2),
            })
        return result
    
    # ================================================================
    #  备份功能
    # ================================================================
    
    def perform_backup(self) -> Optional[str]:
        """
        执行数据库备份
        
        使用 SQLite 原生 backup API 进行热备份，
        备份文件命名格式: trading_system_backup_YYYYMMDD_HHMMSS.db
        
        Returns:
            备份文件路径，失败返回 None
        """
        try:
            if not os.path.exists(self.db_path):
                logger.error(f"[DB-Maintenance] 数据库文件不存在: {self.db_path}")
                self._maintenance_status['failed_backups'] += 1
                return None
            
            # 生成备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'trading_system_backup_{timestamp}.db'
            backup_path = os.path.join(self.config['backup_dir'], backup_name)
            
            logger.info(f"[DB-Maintenance] 开始备份: {backup_path}")
            
            # 使用 SQLite 原生备份 API
            source = sqlite3.connect(self.db_path)
            dest = sqlite3.connect(backup_path)
            source.backup(dest)
            source.close()
            dest.close()
            
            # 更新维护状态
            now = datetime.now().isoformat()
            self._maintenance_status['last_backup'] = backup_path
            self._maintenance_status['next_backup'] = (
                datetime.now() + timedelta(hours=self.config['backup_interval_hours'])
            ).isoformat()
            self._maintenance_status['total_backups'] += 1
            
            # 清理旧备份
            self._cleanup_old_backups()
            
            logger.info(f"[DB-Maintenance] 备份完成: {backup_path} "
                        f"({os.path.getsize(backup_path) / (1024*1024):.2f} MB)")
            
            return backup_path
            
        except Exception as e:
            logger.error(f"[DB-Maintenance] 备份失败: {e}")
            self._maintenance_status['failed_backups'] += 1
            return None
    
    def _cleanup_old_backups(self) -> None:
        """清理超过保留数量的旧备份文件"""
        max_backups = self.config['max_backups']
        backup_dir = self.config['backup_dir']
        
        try:
            # 列出所有备份文件
            backup_files = []
            for f in os.listdir(backup_dir):
                if f.startswith('trading_system_backup_') and f.endswith('.db'):
                    full_path = os.path.join(backup_dir, f)
                    mtime = os.path.getmtime(full_path)
                    backup_files.append((mtime, full_path))
            
            # 按修改时间排序（旧的在前）
            backup_files.sort()
            
            # 删除超出限制的旧备份
            while len(backup_files) > max_backups:
                _, old_file = backup_files.pop(0)
                os.remove(old_file)
                logger.info(f"[DB-Maintenance] 清理旧备份: {old_file}")
                
        except Exception as e:
            logger.warning(f"[DB-Maintenance] 清理旧备份失败: {e}")
    
    # ================================================================
    #  归档功能
    # ================================================================
    
    def perform_archive(self) -> Dict[str, int]:
        """
        执行数据归档
        
        将超过 archive_days 天的数据归档到带归档后缀的表中
        （例如 system_logs → system_logs_archive）。
        同时保留原表结构，只删除已归档的数据。
        
        Returns:
            各表归档记录数，例如 {'system_logs': 1500, 'trade_records': 320}
        """
        archive_counts = {}
        
        try:
            if not os.path.exists(self.db_path):
                logger.error(f"[DB-Maintenance] 数据库文件不存在: {self.db_path}")
                return archive_counts
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            archive_days = self.config['archive_days']
            cutoff = (datetime.now() - timedelta(days=archive_days)).isoformat()
            
            for table_cfg in self.config['archive_tables']:
                table = table_cfg['table']
                date_col = table_cfg['date_col']
                archive_table = f'{table}_archive'
                
                try:
                    # 检查原表是否存在
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)
                    )
                    if not cursor.fetchone():
                        logger.debug(f"[DB-Maintenance] 表 {table} 不存在，跳过归档")
                        continue
                    
                    # 创建归档表（如果不存在）
                    cursor.execute(
                        f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)
                    )
                    create_sql = cursor.fetchone()
                    if create_sql:
                        archive_sql = create_sql[0].replace(
                            f'CREATE TABLE {table}',
                            f'CREATE TABLE IF NOT EXISTS {archive_table}'
                        )
                        cursor.execute(archive_sql)
                    
                    # 移动数据到归档表
                    cursor.execute(
                        f"INSERT INTO {archive_table} SELECT * FROM {table} WHERE {date_col} < ?",
                        (cutoff,)
                    )
                    moved_count = cursor.rowcount
                    
                    if moved_count > 0:
                        # 从原表删除已归档的数据
                        cursor.execute(
                            f"DELETE FROM {table} WHERE {date_col} < ?",
                            (cutoff,)
                        )
                        archive_counts[table] = moved_count
                        logger.info(f"[DB-Maintenance] 归档完成: {table} "
                                    f"→ {archive_table} ({moved_count} 条)")
                    else:
                        logger.debug(f"[DB-Maintenance] {table} 无需归档数据")
                
                except Exception as e:
                    logger.error(f"[DB-Maintenance] 归档表 {table} 失败: {e}")
                    conn.rollback()
            
            conn.commit()
            conn.close()
            
            # 更新维护状态
            now = datetime.now().isoformat()
            self._maintenance_status['last_archive'] = now
            self._maintenance_status['next_archive'] = (
                datetime.now() + timedelta(hours=self.config['archive_interval_hours'])
            ).isoformat()
            
            total = sum(archive_counts.values())
            if total > 0:
                logger.info(f"[DB-Maintenance] 归档总计: {total} 条记录 "
                            f"(分布在 {len(archive_counts)} 张表)")
            
            return archive_counts
            
        except Exception as e:
            logger.error(f"[DB-Maintenance] 归档失败: {e}")
            return archive_counts
    
    # ================================================================
    #  压缩功能
    # ================================================================
    
    def perform_vacuum(self) -> bool:
        """
        执行数据库 VACUUM 压缩
        
        回收已删除数据的空间，重建索引。
        VACUUM 会锁定数据库，建议在低负载时执行。
        
        Returns:
            是否成功
        """
        try:
            if not os.path.exists(self.db_path):
                logger.error(f"[DB-Maintenance] 数据库文件不存在: {self.db_path}")
                return False
            
            size_before = os.path.getsize(self.db_path)
            
            logger.info(f"[DB-Maintenance] 开始 VACUUM (当前大小: {size_before / (1024*1024):.2f} MB)")
            
            conn = self._get_connection()
            conn.execute('VACUUM')
            conn.close()
            
            size_after = os.path.getsize(self.db_path)
            saved = size_before - size_after
            
            # 更新维护状态
            now = datetime.now().isoformat()
            self._maintenance_status['last_vacuum'] = now
            self._maintenance_status['next_vacuum'] = (
                datetime.now() + timedelta(hours=self.config['vacuum_interval_hours'])
            ).isoformat()
            
            logger.info(f"[DB-Maintenance] VACUUM 完成 "
                        f"({size_before / (1024*1024):.2f} MB → "
                        f"{size_after / (1024*1024):.2f} MB, "
                        f"释放 {saved / (1024*1024):.2f} MB)")
            
            return True
            
        except Exception as e:
            logger.error(f"[DB-Maintenance] VACUUM 失败: {e}")
            return False
    
    # ================================================================
    #  完整维护
    # ================================================================
    
    def perform_full_maintenance(self) -> Dict[str, Any]:
        """
        执行完整数据库维护流程
        
        顺序: 备份 → 归档 → 压缩
        确保在任何步骤失败时不影响后续步骤。
        
        Returns:
            维护结果报告
        """
        logger.info("[DB-Maintenance] === 开始完整维护 ===")
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'backup': False,
            'archive': {},
            'vacuum': False,
            'database_size': self._get_db_size(),
        }
        
        # 1. 备份
        backup_path = self.perform_backup()
        result['backup'] = backup_path is not None
        result['backup_path'] = backup_path
        
        # 2. 归档
        archive_result = self.perform_archive()
        result['archive'] = archive_result
        result['archive_total'] = sum(archive_result.values())
        
        # 3. 压缩
        vacuum_result = self.perform_vacuum()
        result['vacuum'] = vacuum_result
        
        logger.info(f"[DB-Maintenance] === 完整维护完成: "
                    f"备份={'✅' if result['backup'] else '❌'}, "
                    f"归档={result['archive_total']}条, "
                    f"压缩={'✅' if result['vacuum'] else '❌'} ===")
        
        return result
    
    # ================================================================
    #  自动维护调度
    # ================================================================
    
    def start_auto_maintenance(self) -> bool:
        """
        启动自动维护定时器
        
        启动后台线程，按配置的间隔自动执行备份/归档/压缩。
        如果已在运行则忽略。
        
        Returns:
            是否成功启动
        """
        if self._running:
            logger.warning("[DB-Maintenance] 自动维护已在运行中")
            return False
        
        if not self.config['enable_auto_maintenance']:
            logger.info("[DB-Maintenance] 自动维护已禁用（配置）")
            return False
        
        self._running = True
        self._stop_event.clear()
        self._maintenance_status['is_running'] = True
        
        # 设置首次维护时间
        now = datetime.now()
        self._maintenance_status['next_backup'] = (
            now + timedelta(hours=self.config['backup_interval_hours'])
        ).isoformat()
        self._maintenance_status['next_archive'] = (
            now + timedelta(hours=self.config['archive_interval_hours'])
        ).isoformat()
        self._maintenance_status['next_vacuum'] = (
            now + timedelta(hours=self.config['vacuum_interval_hours'])
        ).isoformat()
        
        self._thread = threading.Thread(
            target=self._maintenance_loop,
            daemon=True,
            name='DB-Maintenance-Scheduler'
        )
        self._thread.start()
        
        logger.info("[DB-Maintenance] 自动维护已启动 "
                    f"(备份/{self.config['backup_interval_hours']}h, "
                    f"归档/{self.config['archive_interval_hours']}h, "
                    f"压缩/{self.config['vacuum_interval_hours']}h)")
        
        return True
    
    def _maintenance_loop(self) -> None:
        """自动维护循环（在后台线程中运行）"""
        last_backup = datetime.now()
        last_archive = datetime.now()
        last_vacuum = datetime.now()
        
        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                
                # 检查是否需要备份
                backup_interval = timedelta(hours=self.config['backup_interval_hours'])
                if now - last_backup >= backup_interval:
                    logger.info("[DB-Maintenance] 触发定时备份...")
                    self.perform_backup()
                    last_backup = now
                
                # 检查是否需要归档
                archive_interval = timedelta(hours=self.config['archive_interval_hours'])
                if now - last_archive >= archive_interval:
                    logger.info("[DB-Maintenance] 触发定时归档...")
                    self.perform_archive()
                    last_archive = now
                
                # 检查是否需要压缩
                vacuum_interval = timedelta(hours=self.config['vacuum_interval_hours'])
                if now - last_vacuum >= vacuum_interval:
                    logger.info("[DB-Maintenance] 触发定时压缩...")
                    self.perform_vacuum()
                    last_vacuum = now
                
                # 每60秒检查一次
                for _ in range(60):
                    if self._stop_event.is_set():
                        break
                    _time.sleep(1)
                    
            except Exception as e:
                logger.error(f"[DB-Maintenance] 维护循环异常: {e}")
                _time.sleep(60)  # 异常后等待1分钟再重试
        
        self._maintenance_status['is_running'] = False
        logger.info("[DB-Maintenance] 自动维护已停止")
    
    def stop_auto_maintenance(self) -> bool:
        """
        停止自动维护定时器
        
        Returns:
            是否成功停止
        """
        if not self._running:
            logger.warning("[DB-Maintenance] 自动维护未在运行")
            return False
        
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        
        self._running = False
        self._maintenance_status['is_running'] = False
        
        logger.info("[DB-Maintenance] 自动维护已停止")
        return True
    
    # ================================================================
    #  状态查询
    # ================================================================
    
    def get_maintenance_status(self) -> Dict[str, Any]:
        """
        获取维护状态
        
        Returns:
            维护状态字典，包含：is_running, last_backup, last_archive,
            last_vacuum, next_backup, next_archive, next_vacuum,
            database_size, total_backups, failed_backups
        """
        status = dict(self._maintenance_status)
        status['database_size'] = self._get_db_size()
        
        # 列出所有备份文件
        backup_dir = self.config['backup_dir']
        if os.path.isdir(backup_dir):
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith('trading_system_backup_') and f.endswith('.db')
            ])
            status['available_backups'] = backups
            status['backup_count'] = len(backups)
        else:
            status['available_backups'] = []
            status['backup_count'] = 0
        
        return status
    
    def get_maintenance_history(self, limit: int = 20) -> List[Dict]:
        """
        获取维护历史记录（从日志中提取）
        
        Args:
            limit: 最大返回条数
        
        Returns:
            维护历史记录列表
        """
        history = []
        
        # 从 system_logs 中查询维护相关日志
        try:
            if os.path.exists(self.db_path):
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # 检查 system_logs 表是否存在
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='system_logs'"
                )
                if cursor.fetchone():
                    cursor.execute(
                        """SELECT timestamp, level, message 
                           FROM system_logs 
                           WHERE message LIKE '%DB-Maintenance%' 
                           ORDER BY id DESC LIMIT ?""",
                        (limit,)
                    )
                    for row in cursor.fetchall():
                        history.append({
                            'timestamp': row[0],
                            'level': row[1],
                            'message': row[2],
                        })
                
                conn.close()
        except Exception as e:
            logger.debug(f"[DB-Maintenance] 获取维护历史失败: {e}")
        
        return history
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        获取数据库详细信息
        
        Returns:
            数据库信息字典：包含大小、表列表、记录数等
        """
        info = {
            'path': self.db_path,
            'size': self._get_db_size(),
            'tables': {},
        }
        
        try:
            if os.path.exists(self.db_path):
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # 获取所有表
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    
                    # 获取表的列信息
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [row[1] for row in cursor.fetchall()]
                    
                    info['tables'][table] = {
                        'rows': count,
                        'columns': columns,
                    }
                
                conn.close()
        except Exception as e:
            logger.error(f"[DB-Maintenance] 获取数据库信息失败: {e}")
        
        return info
    
    # ================================================================
    #  兼容性方法（与 db_maintenance 旧接口兼容）
    # ================================================================
    
    def backup(self) -> Optional[str]:
        """backup 是 perform_backup 的别名"""
        return self.perform_backup()
    
    def archive(self) -> Dict[str, int]:
        """archive 是 perform_archive 的别名"""
        return self.perform_archive()
    
    def vacuum(self) -> bool:
        """vacuum 是 perform_vacuum 的别名"""
        return self.perform_vacuum()
    
    def status(self) -> Dict[str, Any]:
        """status 是 get_maintenance_status 的别名"""
        return self.get_maintenance_status()


# ================================================================
#  便捷函数（与 cron_backup.ps1/.sh 兼容）
# ================================================================

def get_maintenance_scheduler(db_path: str = None) -> DatabaseMaintenanceScheduler:
    """
    获取全局维护调度器实例
    
    Args:
        db_path: 数据库路径
    
    Returns:
        DatabaseMaintenanceScheduler 单例实例
    """
    return DatabaseMaintenanceScheduler(db_path=db_path)


def start_auto_maintenance(db_path: str = None) -> bool:
    """
    启动自动维护（便捷函数）
    
    Args:
        db_path: 数据库路径
    
    Returns:
        是否成功启动
    """
    scheduler = get_maintenance_scheduler(db_path)
    return scheduler.start_auto_maintenance()


def stop_auto_maintenance() -> bool:
    """
    停止自动维护（便捷函数）
    
    Returns:
        是否成功停止
    """
    scheduler = DatabaseMaintenanceScheduler()
    return scheduler.stop_auto_maintenance()


def perform_backup(db_path: str = None) -> Optional[str]:
    """
    执行备份（便捷函数）
    
    Args:
        db_path: 数据库路径
    
    Returns:
        备份文件路径
    """
    scheduler = get_maintenance_scheduler(db_path)
    return scheduler.perform_backup()


def perform_archive(db_path: str = None) -> Dict[str, int]:
    """
    执行归档（便捷函数）
    
    Args:
        db_path: 数据库路径
    
    Returns:
        各表归档记录数
    """
    scheduler = get_maintenance_scheduler(db_path)
    return scheduler.perform_archive()


def perform_vacuum(db_path: str = None) -> bool:
    """
    执行压缩（便捷函数）
    
    Args:
        db_path: 数据库路径
    
    Returns:
        是否成功
    """
    scheduler = get_maintenance_scheduler(db_path)
    return scheduler.perform_vacuum()


# ================================================================
#  模块自检
# ================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  数据库维护调度器 - 自检")
    print("=" * 60)
    
    scheduler = DatabaseMaintenanceScheduler()
    
    # 状态
    print("\n📊 当前状态")
    print("-" * 40)
    status = scheduler.get_maintenance_status()
    print(f"  数据库路径: {scheduler.db_path}")
    print(f"  数据库存在: {os.path.exists(scheduler.db_path)}")
    if os.path.exists(scheduler.db_path):
        print(f"  数据库大小: {status['database_size']['megabytes']} MB")
    print(f"  备份目录: {scheduler.config['backup_dir']}")
    
    # 数据库信息
    print("\n📋 数据库信息")
    print("-" * 40)
    info = scheduler.get_database_info()
    for table, table_info in info['tables'].items():
        print(f"  {table}: {table_info['rows']} 行")
    
    # 测试备份（仅在数据库存在时）
    if os.path.exists(scheduler.db_path):
        print("\n💾 测试备份...")
        backup_path = scheduler.perform_backup()
        if backup_path:
            print(f"  ✅ 备份成功: {os.path.basename(backup_path)}")
        else:
            print(f"  ❌ 备份失败")
        
        print("\n🗄️ 测试归档...")
        archive_result = scheduler.perform_archive()
        if archive_result:
            total = sum(archive_result.values())
            print(f"  ✅ 归档 {total} 条记录")
        else:
            print(f"  无数据需要归档")
        
        print("\n🔧 测试压缩...")
        if scheduler.perform_vacuum():
            print(f"  ✅ 压缩完成")
        else:
            print(f"  ❌ 压缩失败")
    
    print("\n" + "=" * 60)
    print("  自检完成")
    print("=" * 60)