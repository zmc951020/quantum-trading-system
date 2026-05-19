#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库管理模块
基于SQLite的轻量级数据库支持
"""

import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional


class DatabaseManager:
    """SQLite数据库管理器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'trading_system.db')

        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.db_path = db_path
        self.conn = None
        self._initialize_database()

    def _initialize_database(self):
        """初始化数据库表"""
        try:
            self.connect()

            self._execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS trade_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    profit REAL,
                    closed_at TEXT
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    details TEXT
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source_ip TEXT,
                    message TEXT NOT NULL,
                    details TEXT
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TEXT NOT NULL
                )
            ''')

            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 初始化数据库失败: {e}")
        finally:
            self.close()

    def connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _execute(self, query: str, params: tuple = None):
        if params is None:
            params = ()
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor

    def commit(self):
        if self.conn:
            self.conn.commit()

    def insert_system_log(self, level: str, module: str, message: str, details: str = None):
        try:
            self.connect()
            self._execute('''
                INSERT INTO system_logs (timestamp, level, module, message, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), level, module, message, details))
            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 插入日志失败: {e}")
        finally:
            self.close()

    def insert_trade_record(self, strategy_name: str, symbol: str, order_type: str,
                           direction: str, price: float, quantity: float, amount: float,
                           status: str, profit: float = None, closed_at: str = None):
        try:
            self.connect()
            self._execute('''
                INSERT INTO trade_records (timestamp, strategy_name, symbol, order_type,
                                          direction, price, quantity, amount, status, profit, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), strategy_name, symbol, order_type,
                  direction, price, quantity, amount, status, profit, closed_at))
            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 插入交易记录失败: {e}")
        finally:
            self.close()

    def insert_health_check(self, component: str, status: str, message: str = None, details: str = None):
        try:
            self.connect()
            self._execute('''
                INSERT INTO health_checks (timestamp, component, status, message, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), component, status, message, details))
            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 插入健康检查记录失败: {e}")
        finally:
            self.close()

    def insert_security_event(self, event_type: str, source_ip: str, message: str, details: str = None):
        try:
            self.connect()
            self._execute('''
                INSERT INTO security_events (timestamp, event_type, source_ip, message, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), event_type, source_ip, message, details))
            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 插入安全事件失败: {e}")
        finally:
            self.close()

    def set_config(self, key: str, value: str, description: str = None):
        try:
            self.connect()
            cursor = self._execute('''
                UPDATE system_config SET value = ?, description = ?, updated_at = ? WHERE key = ?
            ''', (value, description, datetime.now().isoformat(), key))

            if cursor.rowcount == 0:
                self._execute('''
                    INSERT INTO system_config (key, value, description, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (key, value, description, datetime.now().isoformat()))

            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 设置配置失败: {e}")
        finally:
            self.close()

    def get_config(self, key: str) -> Optional[str]:
        try:
            self.connect()
            cursor = self._execute('SELECT value FROM system_config WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
        except Exception as e:
            print(f"[DatabaseManager] 获取配置失败: {e}")
            return None
        finally:
            self.close()

    def get_database_stats(self) -> Dict:
        try:
            self.connect()
            stats = {}

            tables = ['system_logs', 'trade_records', 'health_checks', 'security_events', 'system_config']
            for table in tables:
                cursor = self._execute(f'SELECT COUNT(*) as count FROM {table}')
                row = cursor.fetchone()
                stats[f'{table}_count'] = row['count'] if row else 0

            return stats
        except Exception as e:
            print(f"[DatabaseManager] 获取数据库统计失败: {e}")
            return {}
        finally:
            self.close()


global_database_manager = None

def get_database_manager() -> DatabaseManager:
    global global_database_manager
    if global_database_manager is None:
        global_database_manager = DatabaseManager()
    return global_database_manager


if __name__ == '__main__':
    db = get_database_manager()
    db.insert_system_log('INFO', 'DatabaseManager', '数据库测试启动', '测试数据')
    db.set_config('test_key', 'test_value', '测试配置')
    value = db.get_config('test_key')
    print(f"配置值: {value}")
    stats = db.get_database_stats()
    print(f"数据库统计: {stats}")
    print("[DatabaseManager] 测试完成")
