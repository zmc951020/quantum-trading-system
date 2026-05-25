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

            # --- 新增表：策略参数、回测结果、性能指标、数据质量 ---
            self._execute('''
                CREATE TABLE IF NOT EXISTS strategy_params (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    param_key TEXT NOT NULL,
                    param_value TEXT NOT NULL,
                    description TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(strategy_name, param_key)
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    initial_balance REAL,
                    final_balance REAL,
                    total_return REAL,
                    sharpe_ratio REAL,
                    win_rate REAL,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    extra_data TEXT,
                    created_at TEXT NOT NULL
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    symbol TEXT,
                    period TEXT,
                    timestamp TEXT NOT NULL
                )
            ''')

            self._execute('''
                CREATE TABLE IF NOT EXISTS data_quality_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_type TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score REAL,
                    issues TEXT,
                    symbol TEXT,
                    timestamp TEXT NOT NULL
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

# 别名：兼容新增模块的导入习惯
get_db_manager = get_database_manager


# ==================== 策略参数管理 ====================

def save_strategy_params(self, strategy_name: str, params: Dict, descriptions: Dict = None, version_tag: str = None) -> bool:
    try:
        self.connect()
        now = datetime.now().isoformat()
        for key, value in params.items():
            desc = descriptions.get(key) if descriptions else None
            self._execute('''
                INSERT OR REPLACE INTO strategy_params (strategy_name, param_key, param_value, description, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (strategy_name, key, str(value), desc, now))
        self.commit()
        print(f"[DatabaseManager] 策略 {strategy_name} 的 {len(params)} 个参数已保存")
        return True
    except Exception as e:
        print(f"[DatabaseManager] 保存策略参数失败: {e}")
        return False
    finally:
        self.close()


def load_strategy_params(self, strategy_name: str) -> Dict[str, Any]:
    try:
        self.connect()
        cursor = self._execute(
            'SELECT param_key, param_value FROM strategy_params WHERE strategy_name = ?',
            (strategy_name,)
        )
        params = {}
        for row in cursor.fetchall():
            # 尝试还原原始类型
            val = row['param_value']
            try:
                from ast import literal_eval
                params[row['param_key']] = literal_eval(val)
            except (ValueError, SyntaxError):
                params[row['param_key']] = val
        return params
    except Exception as e:
        print(f"[DatabaseManager] 加载策略参数失败: {e}")
        return {}
    finally:
        self.close()


def delete_strategy_params(self, strategy_name: str) -> bool:
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
    try:
        self.connect()
        cursor = self._execute('SELECT DISTINCT strategy_name FROM strategy_params')
        return [row['strategy_name'] for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DatabaseManager] 获取策略列表失败: {e}")
        return []
    finally:
        self.close()


# ==================== 回测结果管理 ====================

def save_backtest_result(self, result_dict: Dict) -> bool:
    try:
        self.connect()
        import json
        extra = {k: v for k, v in result_dict.items() if k not in (
            'strategy_name', 'symbol', 'start_date', 'end_date',
            'initial_balance', 'final_balance', 'total_return',
            'sharpe_ratio', 'win_rate', 'total_trades',
            'winning_trades', 'losing_trades'
        )}
        self._execute('''
            INSERT INTO backtest_results (
                strategy_name, symbol, start_date, end_date,
                initial_balance, final_balance, total_return,
                sharpe_ratio, win_rate, total_trades,
                winning_trades, losing_trades, config_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result_dict.get('strategy_name', 'unknown'),
            result_dict.get('symbol', ''),
            result_dict.get('start_date', ''),
            result_dict.get('end_date', ''),
            result_dict.get('initial_balance', 0.0),
            result_dict.get('final_balance', 0.0),
            result_dict.get('total_return', 0.0),
            result_dict.get('sharpe_ratio'),
            result_dict.get('win_rate'),
            result_dict.get('total_trades'),
            result_dict.get('winning_trades'),
            result_dict.get('losing_trades'),
            json.dumps(extra) if extra else None,
            datetime.now().isoformat()
        ))
        self.commit()
        return True
    except Exception as e:
        print(f"[DatabaseManager] 保存回测结果失败: {e}")
        return False
    finally:
        self.close()


def get_backtest_results(self, strategy_name: str = None, limit: int = 10) -> List[Dict]:
    try:
        self.connect()
        if strategy_name:
            cursor = self._execute(
                'SELECT * FROM backtest_results WHERE strategy_name = ? ORDER BY created_at DESC LIMIT ?',
                (strategy_name, limit)
            )
        else:
            cursor = self._execute(
                'SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?',
                (limit,)
            )
        results = []
        for row in cursor.fetchall():
            r = dict(row)
            import json
            if r.get('config_json'):
                try:
                    r.update(json.loads(r['config_json']))
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(r)
        return results
    except Exception as e:
        print(f"[DatabaseManager] 获取回测结果失败: {e}")
        return []
    finally:
        self.close()


def get_best_backtest_result(self, strategy_name: str, metric: str = 'total_return') -> Optional[Dict]:
    try:
        self.connect()
        valid_metrics = ['total_return', 'sharpe_ratio', 'win_rate']
        if metric not in valid_metrics:
            metric = 'total_return'
        cursor = self._execute(
            f'SELECT * FROM backtest_results WHERE strategy_name = ? ORDER BY {metric} DESC LIMIT 1',
            (strategy_name,)
        )
        row = cursor.fetchone()
        if row:
            r = dict(row)
            import json
            if r.get('config_json'):
                try:
                    r.update(json.loads(r['config_json']))
                except (json.JSONDecodeError, TypeError):
                    pass
            return r
        return None
    except Exception as e:
        print(f"[DatabaseManager] 获取最佳回测结果失败: {e}")
        return None
    finally:
        self.close()


# ==================== 性能指标管理 ====================

def save_performance_metric(self, strategy_name: str, metric_name: str,
                           metric_value: float, symbol: str = None,
                           period: str = None) -> bool:
    try:
        self.connect()
        self._execute('''
            INSERT INTO performance_metrics (strategy_name, metric_name, metric_value, symbol, period, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (strategy_name, metric_name, metric_value, symbol, period, datetime.now().isoformat()))
        self.commit()
        return True
    except Exception as e:
        print(f"[DatabaseManager] 保存性能指标失败: {e}")
        return False
    finally:
        self.close()


def get_performance_metrics(self, strategy_name: str = None, metric_name: str = None,
                           limit: int = 100) -> List[Dict]:
    try:
        self.connect()
        query = 'SELECT * FROM performance_metrics WHERE 1=1'
        params = []
        if strategy_name:
            query += ' AND strategy_name = ?'
            params.append(strategy_name)
        if metric_name:
            query += ' AND metric_name = ?'
            params.append(metric_name)
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        cursor = self._execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DatabaseManager] 获取性能指标失败: {e}")
        return []
    finally:
        self.close()


def get_performance_summary(self, strategy_name: str) -> Dict:
    try:
        self.connect()
        cursor = self._execute('''
            SELECT metric_name,
                   COUNT(*) as count,
                   AVG(metric_value) as avg_value,
                   MAX(metric_value) as max_value,
                   MIN(metric_value) as min_value
            FROM performance_metrics
            WHERE strategy_name = ?
            GROUP BY metric_name
        ''', (strategy_name,))
        summary = {}
        for row in cursor.fetchall():
            summary[row['metric_name']] = {
                'count': row['count'],
                'avg': row['avg_value'],
                'max': row['max_value'],
                'min': row['min_value']
            }
        return summary
    except Exception as e:
        print(f"[DatabaseManager] 获取性能摘要失败: {e}")
        return {}
    finally:
        self.close()


# ==================== 交易统计 ====================

def get_trade_statistics(self, strategy_name: str) -> Dict:
    try:
        self.connect()
        cursor = self._execute('''
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buy_count,
                SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sell_count,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN profit <= 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(profit) as total_profit,
                AVG(profit) as avg_profit,
                SUM(amount) as total_amount
            FROM trade_records
            WHERE strategy_name = ?
        ''', (strategy_name,))
        row = cursor.fetchone()
        if row:
            total = row['total_trades'] or 0
            wins = row['winning_trades'] or 0
            return {
                'total_trades': total,
                'buy_count': row['buy_count'] or 0,
                'sell_count': row['sell_count'] or 0,
                'winning_trades': wins,
                'losing_trades': row['losing_trades'] or 0,
                'win_rate': wins / total if total > 0 else 0,
                'total_profit': row['total_profit'] or 0,
                'avg_profit': row['avg_profit'] or 0,
                'total_amount': row['total_amount'] or 0
            }
        return {'total_trades': 0, 'win_rate': 0, 'total_profit': 0}
    except Exception as e:
        print(f"[DatabaseManager] 获取交易统计失败: {e}")
        return {'total_trades': 0}
    finally:
        self.close()


# ==================== 数据质量日志 ====================

def log_data_quality(self, check_type: str, data_source: str, status: str,
                    score: float = None, issues: str = None,
                    symbol: str = None) -> bool:
    try:
        self.connect()
        self._execute('''
            INSERT INTO data_quality_logs (check_type, data_source, status, score, issues, symbol, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (check_type, data_source, status, score, issues, symbol, datetime.now().isoformat()))
        self.commit()
        return True
    except Exception as e:
        print(f"[DatabaseManager] 记录数据质量日志失败: {e}")
        return False
    finally:
        self.close()


# --- 将新方法绑定到 DatabaseManager 类 ---
DatabaseManager.save_strategy_params = save_strategy_params
DatabaseManager.load_strategy_params = load_strategy_params
DatabaseManager.delete_strategy_params = delete_strategy_params
DatabaseManager.get_all_strategies = get_all_strategies
DatabaseManager.save_backtest_result = save_backtest_result
DatabaseManager.get_backtest_results = get_backtest_results
DatabaseManager.get_best_backtest_result = get_best_backtest_result
DatabaseManager.save_performance_metric = save_performance_metric
DatabaseManager.get_performance_metrics = get_performance_metrics
DatabaseManager.get_performance_summary = get_performance_summary
DatabaseManager.get_trade_statistics = get_trade_statistics
DatabaseManager.log_data_quality = log_data_quality


if __name__ == '__main__':
    db = get_database_manager()
    db.insert_system_log('INFO', 'DatabaseManager', '数据库测试启动', '测试数据')
    db.set_config('test_key', 'test_value', '测试配置')
    value = db.get_config('test_key')
    print(f"配置值: {value}")
    stats = db.get_database_stats()
    print(f"数据库统计: {stats}")
    print("[DatabaseManager] 测试完成")
