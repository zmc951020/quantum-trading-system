#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库管理模块（增强版）
基于SQLite的轻量级数据库支持
支持策略参数持久化、回测结果存储、性能指标追踪、数据质量校验
包含连接池支持，提升并发性能
"""

import sqlite3
import os
import json
import shutil
import queue
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple


class ConnectionPool:
    """SQLite连接池，支持多线程安全复用"""

    def __init__(self, db_path: str, max_connections: int = 5, timeout: float = 10.0):
        """
        初始化连接池

        Args:
            db_path: 数据库文件路径
            max_connections: 最大连接数，默认5
            timeout: 获取连接超时时间（秒），默认10
        """
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=max_connections)
        self._active_count = 0
        self._lock = threading.Lock()
        self._closed = False

        # 预创建连接
        for _ in range(max_connections):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=-8000')  # 8MB cache
        conn.execute('PRAGMA busy_timeout=5000')
        return conn

    def acquire(self) -> sqlite3.Connection:
        """
        从池中获取一个连接

        Returns:
            数据库连接对象

        Raises:
            TimeoutError: 如果超时无法获取连接
        """
        if self._closed:
            raise RuntimeError("连接池已关闭")

        try:
            conn = self._pool.get(timeout=self.timeout)
            return conn
        except queue.Empty:
            raise TimeoutError(
                f"获取数据库连接超时（{self.timeout}秒），"
                f"最大连接数: {self.max_connections}"
            )

    def release(self, conn: sqlite3.Connection):
        """
        归还连接到池中

        Args:
            conn: 要归还的连接
        """
        if self._closed:
            conn.close()
            return

        try:
            # 检查连接是否有效
            conn.execute('SELECT 1')
            self._pool.put_nowait(conn)
        except (sqlite3.Error, AttributeError):
            # 连接已失效，创建新连接替代
            try:
                conn.close()
            except:
                pass
            new_conn = self._create_connection()
            self._pool.put_nowait(new_conn)

    def close_all(self):
        """关闭所有连接"""
        self._closed = True
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except (queue.Empty, sqlite3.Error):
                break

    @property
    def size(self) -> int:
        """当前池中可用连接数"""
        return self._pool.qsize()

    @property
    def is_closed(self) -> bool:
        """连接池是否已关闭"""
        return self._closed


class DatabaseManager:
    """SQLite数据库管理器（增强版，支持连接池）"""

    def __init__(self, db_path: str = None, use_connection_pool: bool = True,
                 max_pool_connections: int = 5):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径（默认: data/trading_system.db）
            use_connection_pool: 是否使用连接池（默认True）
            max_pool_connections: 连接池最大连接数（默认5）
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'trading_system.db')

        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.db_path = db_path
        self.use_connection_pool = use_connection_pool
        self.conn = None
        self._pool = None

        if use_connection_pool:
            self._pool = ConnectionPool(db_path, max_connections=max_pool_connections)

        self._initialize_database()

    def _initialize_database(self):
        """初始化数据库表（兼容旧表 + 新增表）"""
        try:
            self.connect()

            # === 原有表结构（保持兼容） ===
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

            # === 新增表结构 ===

            # 策略参数持久化
            self._execute('''
                CREATE TABLE IF NOT EXISTS strategy_params (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    param_key TEXT NOT NULL,
                    param_value TEXT NOT NULL,
                    param_type TEXT DEFAULT 'string',
                    description TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(strategy_name, param_key)
                )
            ''')

            # 回测结果存储
            self._execute('''
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    initial_balance REAL NOT NULL,
                    final_balance REAL NOT NULL,
                    total_return REAL NOT NULL,
                    annualized_return REAL,
                    max_drawdown REAL,
                    sharpe_ratio REAL,
                    win_rate REAL,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    profit_factor REAL,
                    config_json TEXT,
                    created_at TEXT NOT NULL
                )
            ''')

            # 性能指标追踪
            self._execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    symbol TEXT,
                    period TEXT
                )
            ''')

            # 数据质量校验日志
            self._execute('''
                CREATE TABLE IF NOT EXISTS data_quality_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    symbol TEXT,
                    status TEXT NOT NULL,
                    score REAL,
                    issues TEXT,
                    details TEXT
                )
            ''')

            # === 索引优化 ===
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_strategy_params_name ON strategy_params(strategy_name)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy ON backtest_results(strategy_name)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_backtest_results_created ON backtest_results(created_at)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_performance_metrics_strategy ON performance_metrics(strategy_name)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_performance_metrics_time ON performance_metrics(timestamp)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_data_quality_time ON data_quality_logs(timestamp)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_trade_records_time ON trade_records(timestamp)
            ''')
            self._execute('''
                CREATE INDEX IF NOT EXISTS idx_health_checks_time ON health_checks(timestamp)
            ''')

            self.commit()
        except Exception as e:
            print(f"[DatabaseManager] 初始化数据库失败: {e}")
        finally:
            self.close()

    def connect(self):
        """获取数据库连接（兼容旧版接口）"""
        if self.use_connection_pool and self._pool:
            if self.conn is None:
                self.conn = self._pool.acquire()
        else:
            if self.conn is None:
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row

    def close(self):
        """关闭/归还数据库连接（兼容旧版接口）"""
        if self.use_connection_pool and self._pool and self.conn:
            self._pool.release(self.conn)
            self.conn = None
        elif self.conn:
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

    def close_pool(self):
        """关闭连接池（仅连接池模式）"""
        if self._pool:
            self._pool.close_all()
            self._pool = None

    # ==================== 原有方法（保持兼容） ====================

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

            tables = ['system_logs', 'trade_records', 'health_checks',
                      'security_events', 'system_config', 'strategy_params',
                      'backtest_results', 'performance_metrics', 'data_quality_logs']
            for table in tables:
                cursor = self._execute(f'SELECT COUNT(*) as count FROM {table}')
                row = cursor.fetchone()
                stats[f'{table}_count'] = row['count'] if row else 0

            # 添加数据库大小信息
            try:
                size_bytes = os.path.getsize(self.db_path)
                stats['database_size_bytes'] = size_bytes
                stats['database_size_mb'] = round(size_bytes / (1024 * 1024), 2)
            except:
                pass

            return stats
        except Exception as e:
            print(f"[DatabaseManager] 获取数据库统计失败: {e}")
            return {}
        finally:
            self.close()

    # ==================== 新增：策略参数管理 ====================

    def save_strategy_params(self, strategy_name: str, params_dict: Dict[str, Any],
                            descriptions: Dict[str, str] = None) -> bool:
        """
        批量保存策略参数

        Args:
            strategy_name: 策略名称
            params_dict: 参数字典 {key: value}
            descriptions: 参数字典 {key: description}

        Returns:
            是否成功
        """
        try:
            self.connect()
            now = datetime.now().isoformat()

            for key, value in params_dict.items():
                param_type = type(value).__name__
                param_value = str(value)
                description = (descriptions or {}).get(key, None)

                cursor = self._execute('''
                    UPDATE strategy_params SET param_value = ?, param_type = ?,
                    description = ?, updated_at = ? WHERE strategy_name = ? AND param_key = ?
                ''', (param_value, param_type, description, now, strategy_name, key))

                if cursor.rowcount == 0:
                    self._execute('''
                        INSERT INTO strategy_params (strategy_name, param_key, param_value, param_type, description, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (strategy_name, key, param_value, param_type, description, now))

            self.commit()
            return True
        except Exception as e:
            print(f"[DatabaseManager] 保存策略参数失败: {e}")
            return False
        finally:
            self.close()

    def load_strategy_params(self, strategy_name: str) -> Dict[str, Any]:
        """
        加载策略参数

        Args:
            strategy_name: 策略名称

        Returns:
            参数字典
        """
        try:
            self.connect()
            cursor = self._execute('''
                SELECT param_key, param_value, param_type FROM strategy_params
                WHERE strategy_name = ?
            ''', (strategy_name,))
            rows = cursor.fetchall()

            params = {}
            for row in rows:
                key = row['param_key']
                value = row['param_value']
                param_type = row['param_type']

                # 类型转换
                if param_type == 'int':
                    params[key] = int(value)
                elif param_type == 'float':
                    params[key] = float(value)
                elif param_type == 'bool':
                    params[key] = value.lower() in ('true', '1', 'yes')
                elif param_type in ('list', 'dict'):
                    try:
                        params[key] = json.loads(value)
                    except:
                        params[key] = value
                else:
                    params[key] = value

            return params
        except Exception as e:
            print(f"[DatabaseManager] 加载策略参数失败: {e}")
            return {}
        finally:
            self.close()

    def delete_strategy_params(self, strategy_name: str) -> bool:
        """
        删除策略参数

        Args:
            strategy_name: 策略名称

        Returns:
            是否成功
        """
        try:
            self.connect()
            self._execute('DELETE FROM strategy_params WHERE strategy_name = ?', (strategy_name,))
            self.commit()
            return True
        except Exception as e:
            print(f"[DatabaseManager] 删除策略参数失败: {e}")
            return False
        finally:
            self.close()

    def get_all_strategies(self) -> List[str]:
        """
        获取所有有参数存储的策略名称列表

        Returns:
            策略名称列表
        """
        try:
            self.connect()
            cursor = self._execute('SELECT DISTINCT strategy_name FROM strategy_params')
            return [row['strategy_name'] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] 获取策略列表失败: {e}")
            return []
        finally:
            self.close()

    # ==================== 新增：回测结果管理 ====================

    def save_backtest_result(self, result_dict: Dict) -> bool:
        """
        保存回测结果

        Args:
            result_dict: 回测结果字典，包含:
                - strategy_name, symbol, start_date, end_date
                - initial_balance, final_balance, total_return
                - annualized_return, max_drawdown, sharpe_ratio (可选)
                - win_rate, total_trades, winning_trades, losing_trades
                - profit_factor (可选), config_json (可选)

        Returns:
            是否成功
        """
        try:
            self.connect()
            self._execute('''
                INSERT INTO backtest_results (
                    strategy_name, symbol, start_date, end_date,
                    initial_balance, final_balance, total_return,
                    annualized_return, max_drawdown, sharpe_ratio,
                    win_rate, total_trades, winning_trades, losing_trades,
                    profit_factor, config_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result_dict.get('strategy_name', ''),
                result_dict.get('symbol', ''),
                result_dict.get('start_date', ''),
                result_dict.get('end_date', ''),
                result_dict.get('initial_balance', 0),
                result_dict.get('final_balance', 0),
                result_dict.get('total_return', 0),
                result_dict.get('annualized_return'),
                result_dict.get('max_drawdown'),
                result_dict.get('sharpe_ratio'),
                result_dict.get('win_rate', 0),
                result_dict.get('total_trades', 0),
                result_dict.get('winning_trades', 0),
                result_dict.get('losing_trades', 0),
                result_dict.get('profit_factor'),
                json.dumps(result_dict.get('config', {}), ensure_ascii=False) if result_dict.get('config') else None,
                datetime.now().isoformat()
            ))
            self.commit()
            return True
        except Exception as e:
            print(f"[DatabaseManager] 保存回测结果失败: {e}")
            return False
        finally:
            self.close()

    def get_backtest_results(self, strategy_name: str = None, limit: int = 10,
                            sort_by: str = 'created_at', ascending: bool = False) -> List[Dict]:
        """
        获取回测结果

        Args:
            strategy_name: 策略名称（可选，None表示所有策略）
            limit: 返回数量
            sort_by: 排序字段
            ascending: 是否升序

        Returns:
            回测结果列表
        """
        try:
            self.connect()
            order = 'ASC' if ascending else 'DESC'

            if strategy_name:
                cursor = self._execute(f'''
                    SELECT * FROM backtest_results
                    WHERE strategy_name = ?
                    ORDER BY {sort_by} {order}
                    LIMIT ?
                ''', (strategy_name, limit))
            else:
                cursor = self._execute(f'''
                    SELECT * FROM backtest_results
                    ORDER BY {sort_by} {order}
                    LIMIT ?
                ''', (limit,))

            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] 获取回测结果失败: {e}")
            return []
        finally:
            self.close()

    def get_best_backtest_result(self, strategy_name: str,
                                metric: str = 'total_return') -> Optional[Dict]:
        """
        获取最佳回测结果

        Args:
            strategy_name: 策略名称
            metric: 评估指标（total_return, sharpe_ratio, win_rate等）

        Returns:
            最佳回测结果
        """
        try:
            self.connect()
            cursor = self._execute(f'''
                SELECT * FROM backtest_results
                WHERE strategy_name = ?
                ORDER BY {metric} DESC
                LIMIT 1
            ''', (strategy_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"[DatabaseManager] 获取最佳回测结果失败: {e}")
            return None
        finally:
            self.close()

    def delete_backtest_results(self, strategy_name: str = None,
                               before_date: str = None) -> int:
        """
        删除回测结果

        Args:
            strategy_name: 策略名称（可选）
            before_date: 删除此日期之前的结果（可选）

        Returns:
            删除的记录数
        """
        try:
            self.connect()
            if strategy_name and before_date:
                cursor = self._execute('''
                    DELETE FROM backtest_results
                    WHERE strategy_name = ? AND created_at < ?
                ''', (strategy_name, before_date))
            elif strategy_name:
                cursor = self._execute('''
                    DELETE FROM backtest_results WHERE strategy_name = ?
                ''', (strategy_name,))
            elif before_date:
                cursor = self._execute('''
                    DELETE FROM backtest_results WHERE created_at < ?
                ''', (before_date,))
            else:
                cursor = self._execute('DELETE FROM backtest_results')

            self.commit()
            return cursor.rowcount
        except Exception as e:
            print(f"[DatabaseManager] 删除回测结果失败: {e}")
            return 0
        finally:
            self.close()

    # ==================== 新增：性能指标追踪 ====================

    def save_performance_metric(self, strategy_name: str, metric_name: str,
                               metric_value: float, symbol: str = None,
                               period: str = None) -> bool:
        """
        保存性能指标

        Args:
            strategy_name: 策略名称
            metric_name: 指标名称
            metric_value: 指标值
            symbol: 交易标的（可选）
            period: 时间周期（可选）

        Returns:
            是否成功
        """
        try:
            self.connect()
            self._execute('''
                INSERT INTO performance_metrics (timestamp, strategy_name, metric_name,
                                                metric_value, symbol, period)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), strategy_name, metric_name,
                  metric_value, symbol, period))
            self.commit()
            return True
        except Exception as e:
            print(f"[DatabaseManager] 保存性能指标失败: {e}")
            return False
        finally:
            self.close()

    def get_performance_metrics(self, strategy_name: str, metric_name: str = None,
                               limit: int = 100, since: str = None) -> List[Dict]:
        """
        获取性能指标

        Args:
            strategy_name: 策略名称
            metric_name: 指标名称（可选）
            limit: 返回数量
            since: 起始时间（ISO格式）

        Returns:
            性能指标列表
        """
        try:
            self.connect()
            if metric_name and since:
                cursor = self._execute('''
                    SELECT * FROM performance_metrics
                    WHERE strategy_name = ? AND metric_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (strategy_name, metric_name, since, limit))
            elif metric_name:
                cursor = self._execute('''
                    SELECT * FROM performance_metrics
                    WHERE strategy_name = ? AND metric_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (strategy_name, metric_name, limit))
            elif since:
                cursor = self._execute('''
                    SELECT * FROM performance_metrics
                    WHERE strategy_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (strategy_name, since, limit))
            else:
                cursor = self._execute('''
                    SELECT * FROM performance_metrics
                    WHERE strategy_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (strategy_name, limit))

            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] 获取性能指标失败: {e}")
            return []
        finally:
            self.close()

    def get_performance_summary(self, strategy_name: str) -> Dict:
        """
        获取性能摘要

        Args:
            strategy_name: 策略名称

        Returns:
            性能摘要字典
        """
        try:
            self.connect()
            cursor = self._execute('''
                SELECT metric_name,
                       AVG(metric_value) as avg_value,
                       MAX(metric_value) as max_value,
                       MIN(metric_value) as min_value,
                       COUNT(*) as count
                FROM performance_metrics
                WHERE strategy_name = ?
                GROUP BY metric_name
            ''', (strategy_name,))

            summary = {}
            for row in cursor.fetchall():
                summary[row['metric_name']] = {
                    'avg': round(row['avg_value'], 4) if row['avg_value'] else 0,
                    'max': round(row['max_value'], 4) if row['max_value'] else 0,
                    'min': round(row['min_value'], 4) if row['min_value'] else 0,
                    'count': row['count']
                }

            return summary
        except Exception as e:
            print(f"[DatabaseManager] 获取性能摘要失败: {e}")
            return {}
        finally:
            self.close()

    # ==================== 新增：数据质量日志 ====================

    def log_data_quality(self, check_type: str, data_source: str, status: str,
                        score: float = None, issues: str = None,
                        symbol: str = None, details: str = None) -> bool:
        """
        记录数据质量校验结果

        Args:
            check_type: 校验类型
            data_source: 数据源
            status: 状态（pass/fail/warning）
            score: 质量评分（0-100）
            issues: 问题描述
            symbol: 交易标的
            details: 详细信息

        Returns:
            是否成功
        """
        try:
            self.connect()
            self._execute('''
                INSERT INTO data_quality_logs (timestamp, check_type, data_source,
                                              symbol, status, score, issues, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), check_type, data_source,
                  symbol, status, score, issues, details))
            self.commit()
            return True
        except Exception as e:
            print(f"[DatabaseManager] 记录数据质量日志失败: {e}")
            return False
        finally:
            self.close()

    def get_data_quality_logs(self, limit: int = 50, status: str = None,
                             check_type: str = None) -> List[Dict]:
        """
        获取数据质量日志

        Args:
            limit: 返回数量
            status: 按状态筛选
            check_type: 按校验类型筛选

        Returns:
            数据质量日志列表
        """
        try:
            self.connect()
            if status and check_type:
                cursor = self._execute('''
                    SELECT * FROM data_quality_logs
                    WHERE status = ? AND check_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (status, check_type, limit))
            elif status:
                cursor = self._execute('''
                    SELECT * FROM data_quality_logs
                    WHERE status = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (status, limit))
            elif check_type:
                cursor = self._execute('''
                    SELECT * FROM data_quality_logs
                    WHERE check_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (check_type, limit))
            else:
                cursor = self._execute('''
                    SELECT * FROM data_quality_logs
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))

            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] 获取数据质量日志失败: {e}")
            return []
        finally:
            self.close()

    def get_data_quality_summary(self) -> Dict:
        """
        获取数据质量摘要

        Returns:
            数据质量摘要
        """
        try:
            self.connect()
            cursor = self._execute('''
                SELECT check_type, status, COUNT(*) as count
                FROM data_quality_logs
                GROUP BY check_type, status
            ''')

            summary = {}
            for row in cursor.fetchall():
                ct = row['check_type']
                if ct not in summary:
                    summary[ct] = {'pass': 0, 'fail': 0, 'warning': 0, 'total': 0}
                summary[ct][row['status']] = row['count']
                summary[ct]['total'] += row['count']

            return summary
        except Exception as e:
            print(f"[DatabaseManager] 获取数据质量摘要失败: {e}")
            return {}
        finally:
            self.close()

    # ==================== 新增：数据库维护功能 ====================

    def vacuum_database(self) -> bool:
        """
        压缩数据库

        Returns:
            是否成功
        """
        try:
            self.connect()
            self.conn.execute('VACUUM')
            self.commit()
            print(f"[DatabaseManager] 数据库压缩完成")
            return True
        except Exception as e:
            print(f"[DatabaseManager] 数据库压缩失败: {e}")
            return False
        finally:
            self.close()

    def backup_database(self, backup_path: str = None) -> Optional[str]:
        """
        备份数据库

        Args:
            backup_path: 备份路径（可选，默认自动生成）

        Returns:
            备份文件路径，失败返回None
        """
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_dir = os.path.join(os.path.dirname(self.db_path), 'backups')
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, f'trading_system_backup_{timestamp}.db')

            # 确保连接关闭后再复制
            self.close()
            shutil.copy2(self.db_path, backup_path)
            print(f"[DatabaseManager] 数据库已备份到: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"[DatabaseManager] 数据库备份失败: {e}")
            return None

    def get_database_size(self) -> Dict:
        """
        获取数据库大小信息

        Returns:
            大小信息字典
        """
        try:
            size_bytes = os.path.getsize(self.db_path)
            return {
                'path': self.db_path,
                'bytes': size_bytes,
                'kilobytes': round(size_bytes / 1024, 2),
                'megabytes': round(size_bytes / (1024 * 1024), 2)
            }
        except Exception as e:
            print(f"[DatabaseManager] 获取数据库大小失败: {e}")
            return {'bytes': 0, 'kilobytes': 0, 'megabytes': 0}

    def archive_old_records(self, days: int = 90) -> Dict:
        """
        归档旧记录（删除指定天数前的数据）

        Args:
            days: 保留天数

        Returns:
            各表删除的记录数
        """
        try:
            self.connect()
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            results = {}

            tables = {
                'system_logs': 'timestamp',
                'health_checks': 'timestamp',
                'security_events': 'timestamp',
                'performance_metrics': 'timestamp',
                'data_quality_logs': 'timestamp'
            }

            for table, time_col in tables.items():
                cursor = self._execute(f'DELETE FROM {table} WHERE {time_col} < ?', (cutoff,))
                results[table] = cursor.rowcount

            self.commit()
            print(f"[DatabaseManager] 归档完成，共删除 {sum(results.values())} 条旧记录")
            return results
        except Exception as e:
            print(f"[DatabaseManager] 归档失败: {e}")
            return {}
        finally:
            self.close()

    # ==================== 新增：查询增强 ====================

    def query_trade_records(self, strategy_name: str = None, symbol: str = None,
                           start_time: str = None, end_time: str = None,
                           status: str = None, limit: int = 100) -> List[Dict]:
        """
        高级查询交易记录

        Args:
            strategy_name: 策略名称
            symbol: 交易标的
            start_time: 起始时间
            end_time: 结束时间
            status: 状态
            limit: 返回数量

        Returns:
            交易记录列表
        """
        try:
            self.connect()
            conditions = []
            params = []

            if strategy_name:
                conditions.append('strategy_name = ?')
                params.append(strategy_name)
            if symbol:
                conditions.append('symbol = ?')
                params.append(symbol)
            if start_time:
                conditions.append('timestamp >= ?')
                params.append(start_time)
            if end_time:
                conditions.append('timestamp <= ?')
                params.append(end_time)
            if status:
                conditions.append('status = ?')
                params.append(status)

            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            params.append(limit)
            cursor = self._execute(f'''
                SELECT * FROM trade_records
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            ''', tuple(params))

            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] 查询交易记录失败: {e}")
            return []
        finally:
            self.close()

    # ==================== 新增：批量操作 ====================

    def bulk_insert_trade_records(self, records: List[Dict]) -> int:
        """
        批量插入交易记录

        Args:
            records: 交易记录字典列表

        Returns:
            插入的记录数
        """
        try:
            self.connect()
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()

            data = []
            for r in records:
                data.append((
                    now, r.get('strategy_name', ''), r.get('symbol', ''),
                    r.get('order_type', ''), r.get('direction', ''),
                    r.get('price', 0), r.get('quantity', 0), r.get('amount', 0),
                    r.get('status', ''), r.get('profit'), r.get('closed_at')
                ))

            cursor.executemany('''
                INSERT INTO trade_records (timestamp, strategy_name, symbol, order_type,
                                          direction, price, quantity, amount, status, profit, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            self.commit()
            return len(data)
        except Exception as e:
            print(f"[DatabaseManager] 批量插入交易记录失败: {e}")
            return 0
        finally:
            self.close()

    def bulk_insert_performance_metrics(self, metrics: List[Dict]) -> int:
        """
        批量插入性能指标

        Args:
            metrics: 性能指标字典列表

        Returns:
            插入的记录数
        """
        try:
            self.connect()
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()

            data = []
            for m in metrics:
                data.append((
                    now, m.get('strategy_name', ''), m.get('metric_name', ''),
                    m.get('metric_value', 0), m.get('symbol'), m.get('period')
                ))

            cursor.executemany('''
                INSERT INTO performance_metrics (timestamp, strategy_name, metric_name,
                                                metric_value, symbol, period)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', data)
            self.commit()
            return len(data)
        except Exception as e:
            print(f"[DatabaseManager] 批量插入性能指标失败: {e}")
            return 0
        finally:
            self.close()

    # ==================== 新增：数据库健康检查 ====================

    def check_database_health(self) -> Dict:
        """
        检查数据库健康状态

        Returns:
            健康状态字典
        """
        try:
            self.connect()
            health = {
                'status': 'healthy',
                'checks': {}
            }

            # 检查数据库文件完整性
            try:
                cursor = self._execute('PRAGMA integrity_check')
                integrity = cursor.fetchone()[0]
                health['checks']['integrity'] = integrity
                if integrity != 'ok':
                    health['status'] = 'degraded'
            except Exception as e:
                health['checks']['integrity'] = f'error: {e}'
                health['status'] = 'error'

            # 检查各表状态
            tables = ['system_logs', 'trade_records', 'health_checks',
                      'security_events', 'system_config', 'strategy_params',
                      'backtest_results', 'performance_metrics', 'data_quality_logs']
            table_stats = {}
            for table in tables:
                try:
                    cursor = self._execute(f'SELECT COUNT(*) as count FROM {table}')
                    row = cursor.fetchone()
                    table_stats[table] = row['count'] if row else 0
                except Exception as e:
                    table_stats[table] = f'error: {e}'
                    health['status'] = 'degraded'
            health['checks']['table_stats'] = table_stats

            # 检查数据库大小
            try:
                size_info = self.get_database_size()
                health['checks']['size_mb'] = size_info['megabytes']
            except Exception as e:
                health['checks']['size_mb'] = f'error: {e}'

            # 检查连接池状态
            if self._pool:
                health['checks']['pool_size'] = self._pool.size
                health['checks']['pool_closed'] = self._pool.is_closed

            return health
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            self.close()

    def repair_database(self) -> bool:
        """
        尝试修复数据库

        Returns:
            是否成功
        """
        try:
            self.connect()
            # 执行完整性检查
            cursor = self._execute('PRAGMA integrity_check')
            result = cursor.fetchone()[0]

            if result != 'ok':
                print(f"[DatabaseManager] 数据库需要修复: {result}")
                # 尝试重建
                self.conn.execute('VACUUM')
                self.conn.execute('REINDEX')
                self.commit()

                # 再次检查
                cursor = self._execute('PRAGMA integrity_check')
                result = cursor.fetchone()[0]
                if result == 'ok':
                    print(f"[DatabaseManager] 数据库修复成功")
                    return True
                else:
                    print(f"[DatabaseManager] 数据库修复失败: {result}")
                    return False
            else:
                print(f"[DatabaseManager] 数据库状态正常，无需修复")
                return True
        except Exception as e:
            print(f"[DatabaseManager] 数据库修复过程出错: {e}")
            return False
        finally:
            self.close()


# ==================== 便捷函数 ====================

def get_db_manager(db_path: str = None, use_pool: bool = True) -> DatabaseManager:
    """
    获取数据库管理器实例（便捷工厂函数）

    Args:
        db_path: 数据库路径
        use_pool: 是否使用连接池

    Returns:
        DatabaseManager实例
    """
    return DatabaseManager(db_path, use_connection_pool=use_pool)


def test_database():
    """数据库功能测试"""
    print("=" * 60)
    print("数据库功能测试")
    print("=" * 60)

    # 创建测试数据库
    test_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'test_trading.db')
    db = DatabaseManager(test_path, use_connection_pool=True)

    try:
        # 测试1: 基本操作
        print("\n[测试1] 基本操作...")
        db.set_config('test_key', 'test_value', '测试配置')
        value = db.get_config('test_key')
        assert value == 'test_value', f"配置读写失败: {value}"
        print("  ✓ 配置读写正常")

        # 测试2: 策略参数
        print("\n[测试2] 策略参数管理...")
        params = {
            'risk_level': 0.5,
            'max_position': 10000,
            'stop_loss': 0.02,
            'strategy_name': 'test_strategy'
        }
        assert db.save_strategy_params('test_strategy', params), "保存策略参数失败"
        loaded = db.load_strategy_params('test_strategy')
        assert loaded.get('risk_level') == 0.5, f"参数加载错误: {loaded}"
        print("  ✓ 策略参数读写正常")

        # 测试3: 回测结果
        print("\n[测试3] 回测结果管理...")
        result = {
            'strategy_name': 'test_strategy',
            'symbol': '000001.SH',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'initial_balance': 100000,
            'final_balance': 120000,
            'total_return': 0.2,
            'annualized_return': 0.2,
            'max_drawdown': 0.1,
            'sharpe_ratio': 1.5,
            'win_rate': 0.6,
            'total_trades': 100,
            'winning_trades': 60,
            'losing_trades': 40,
            'profit_factor': 1.8
        }
        assert db.save_backtest_result(result), "保存回测结果失败"
        results = db.get_backtest_results('test_strategy')
        assert len(results) > 0, "获取回测结果失败"
        print("  ✓ 回测结果读写正常")

        # 测试4: 性能指标
        print("\n[测试4] 性能指标追踪...")
        assert db.save_performance_metric('test_strategy', 'sharpe_ratio', 1.5), "保存性能指标失败"
        metrics = db.get_performance_metrics('test_strategy', 'sharpe_ratio')
        assert len(metrics) > 0, "获取性能指标失败"
        summary = db.get_performance_summary('test_strategy')
        assert 'sharpe_ratio' in summary, "获取性能摘要失败"
        print("  ✓ 性能指标追踪正常")

        # 测试5: 数据质量日志
        print("\n[测试5] 数据质量日志...")
        assert db.log_data_quality('completeness', 'test_source', 'pass', 95.0), "记录数据质量日志失败"
        logs = db.get_data_quality_logs(status='pass')
        assert len(logs) > 0, "获取数据质量日志失败"
        summary = db.get_data_quality_summary()
        assert 'completeness' in summary, "获取数据质量摘要失败"
        print("  ✓ 数据质量日志正常")

        # 测试6: 数据库统计
        print("\n[测试6] 数据库统计...")
        stats = db.get_database_stats()
        assert 'strategy_params_count' in stats, "获取数据库统计失败"
        print(f"  ✓ 数据库统计正常: {stats}")

        # 测试7: 数据库维护
        print("\n[测试7] 数据库维护...")
        size = db.get_database_size()
        assert size['bytes'] > 0, "获取数据库大小失败"
        print(f"  ✓ 数据库大小: {size['megabytes']} MB")

        # 测试8: 高级查询
        print("\n[测试8] 高级查询...")
        records = db.query_trade_records(strategy_name='test_strategy')
        assert isinstance(records, list), "高级查询失败"
        print("  ✓ 高级查询正常")

        # 测试9: 数据库健康检查
        print("\n[测试9] 数据库健康检查...")
        health = db.check_database_health()
        assert health['status'] in ('healthy', 'degraded'), f"健康检查失败: {health}"
        print(f"  ✓ 数据库健康状态: {health['status']}")

        # 测试10: 批量操作
        print("\n[测试10] 批量操作...")
        bulk_records = [
            {'strategy_name': 'test_strategy', 'symbol': '000001.SH',
             'order_type': 'market', 'direction': 'buy', 'price': 10.0,
             'quantity': 100, 'amount': 1000, 'status': 'filled'}
        ]
        count = db.bulk_insert_trade_records(bulk_records)
        assert count == 1, f"批量插入失败: {count}"
        print("  ✓ 批量操作正常")

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        db.close_pool()
        try:
            os.remove(test_path)
        except:
            pass


if __name__ == '__main__':
    test_database()
