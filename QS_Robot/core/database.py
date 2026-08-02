#!/usr/bin/env python3
"""
SQLite 持久化存储模块（Database Module）

核心职责：
  1. 用户数据持久化（密码哈希、角色、状态）
  2. 策略参数版本管理
  3. 交易记录存储
  4. 审计日志持久化
  5. IP白名单管理

设计原则：
  - WAL模式提升并发性能
  - 上下文管理器确保连接正确关闭
  - 线程安全（check_same_thread=False）
  - 所有写操作使用事务
"""

import os
import sqlite3
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# ============================================================
# 数据库管理器
# ============================================================

class DatabaseManager:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(__file__), "..", "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "qs_robot.db")
        self._db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        conn.executescript("""
            -- 用户表
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                last_login_ip TEXT,
                last_login_time TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- 策略参数版本表
            CREATE TABLE IF NOT EXISTS strategy_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                params TEXT NOT NULL,  -- JSON
                score REAL,
                optimizer TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(strategy_name, version)
            );

            -- 交易记录表
            CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy_name TEXT,
                direction TEXT,  -- buy/sell
                price REAL,
                quantity INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending',
                broker TEXT DEFAULT 'paper',
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- 审计日志表
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                action TEXT NOT NULL,
                target TEXT,
                detail TEXT,
                ip TEXT,
                result TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- IP白名单表
            CREATE TABLE IF NOT EXISTS ip_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT UNIQUE NOT NULL,
                label TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- 优化历史表
            CREATE TABLE IF NOT EXISTS optimization_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                optimizer TEXT,
                best_score REAL,
                best_params TEXT,  -- JSON
                iterations INTEGER,
                elapsed_seconds REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_strategy_params_name ON strategy_params(strategy_name);
            CREATE INDEX IF NOT EXISTS idx_trade_records_symbol ON trade_records(symbol);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_ip_whitelist_ip ON ip_whitelist(ip);
        """)
        conn.commit()

    # ============================================================
    # 用户管理
    # ============================================================

    def get_user(self, username: str) -> Optional[Dict]:
        """获取用户信息"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            return dict(row)
        return None

    def get_all_users(self) -> List[Dict]:
        """获取所有用户"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def create_user(self, username: str, password_hash: str, role: str = "user") -> bool:
        """创建用户"""
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_user(self, username: str, **kwargs) -> bool:
        """更新用户信息"""
        allowed = {"password_hash", "role", "status", "last_login_ip", "last_login_time"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [username]
        conn = self._get_conn()
        cursor = conn.execute(f"UPDATE users SET {set_clause} WHERE username = ?", values)
        conn.commit()
        return cursor.rowcount > 0

    def delete_user(self, username: str) -> bool:
        """删除用户"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return cursor.rowcount > 0

    def get_user_count(self) -> int:
        """获取用户总数"""
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # ============================================================
    # 策略参数管理
    # ============================================================

    def get_latest_params(self, strategy_name: str) -> Optional[Dict]:
        """获取策略最新参数"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM strategy_params WHERE strategy_name = ? ORDER BY version DESC LIMIT 1",
            (strategy_name,)
        ).fetchone()
        if row:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            return d
        return None

    def get_param_history(self, strategy_name: str) -> List[Dict]:
        """获取策略参数历史"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM strategy_params WHERE strategy_name = ? ORDER BY version DESC",
            (strategy_name,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            result.append(d)
        return result

    def save_params(self, strategy_name: str, params: dict, score: float = None,
                    optimizer: str = None) -> int:
        """保存策略参数（自动递增版本号）"""
        conn = self._get_conn()
        # 获取当前最大版本
        max_ver = conn.execute(
            "SELECT MAX(version) FROM strategy_params WHERE strategy_name = ?",
            (strategy_name,)
        ).fetchone()[0]
        new_version = (max_ver or 0) + 1
        conn.execute(
            "INSERT INTO strategy_params (strategy_name, version, params, score, optimizer) VALUES (?, ?, ?, ?, ?)",
            (strategy_name, new_version, json.dumps(params, ensure_ascii=False), score, optimizer)
        )
        conn.commit()
        return new_version

    # ============================================================
    # 交易记录
    # ============================================================

    def add_trade(self, symbol: str, direction: str, price: float, quantity: int,
                  strategy_name: str = None, broker: str = "paper") -> int:
        """添加交易记录"""
        amount = price * quantity
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO trade_records (symbol, strategy_name, direction, price, quantity, amount, broker) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol, strategy_name, direction, price, quantity, amount, broker)
        )
        conn.commit()
        return cursor.lastrowid

    def get_trades(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """获取交易记录"""
        conn = self._get_conn()
        if symbol:
            rows = conn.execute(
                "SELECT * FROM trade_records WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trade_records ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_trade_status(self, trade_id: int, status: str) -> bool:
        """更新交易状态"""
        conn = self._get_conn()
        cursor = conn.execute("UPDATE trade_records SET status = ? WHERE id = ?", (status, trade_id))
        conn.commit()
        return cursor.rowcount > 0

    # ============================================================
    # 审计日志
    # ============================================================

    def add_audit_log(self, user: str, action: str, target: str = None,
                      detail: str = None, ip: str = None, result: str = "success") -> int:
        """添加审计日志"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO audit_logs (user, action, target, detail, ip, result) VALUES (?, ?, ?, ?, ?, ?)",
            (user, action, target, detail, ip, result)
        )
        conn.commit()
        return cursor.lastrowid

    def get_audit_logs(self, limit: int = 100, user: str = None) -> List[Dict]:
        """获取审计日志"""
        conn = self._get_conn()
        if user:
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE user = ? ORDER BY created_at DESC LIMIT ?",
                (user, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_audit_count(self) -> int:
        """获取审计日志总数"""
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

    # ============================================================
    # IP白名单管理
    # ============================================================

    def add_ip_whitelist(self, ip: str, label: str = "") -> bool:
        """添加IP白名单"""
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO ip_whitelist (ip, label) VALUES (?, ?)",
                (ip, label)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_ip_whitelist(self, ip: str) -> bool:
        """移除IP白名单"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM ip_whitelist WHERE ip = ?", (ip,))
        conn.commit()
        return cursor.rowcount > 0

    def get_ip_whitelist(self) -> List[Dict]:
        """获取IP白名单"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM ip_whitelist WHERE enabled = 1 ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def is_ip_whitelisted(self, ip: str) -> bool:
        """检查IP是否在白名单中"""
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM ip_whitelist WHERE ip = ? AND enabled = 1", (ip,)).fetchone()
        return row is not None

    # ============================================================
    # 优化历史
    # ============================================================

    def add_optimization(self, strategy_name: str, optimizer: str, best_score: float,
                         best_params: dict, iterations: int, elapsed_seconds: float) -> int:
        """添加优化历史"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO optimization_history (strategy_name, optimizer, best_score, best_params, iterations, elapsed_seconds) VALUES (?, ?, ?, ?, ?, ?)",
            (strategy_name, optimizer, best_score, json.dumps(best_params, ensure_ascii=False), iterations, elapsed_seconds)
        )
        conn.commit()
        return cursor.lastrowid

    def get_optimization_history(self, strategy_name: str = None, limit: int = 50) -> List[Dict]:
        """获取优化历史"""
        conn = self._get_conn()
        if strategy_name:
            rows = conn.execute(
                "SELECT * FROM optimization_history WHERE strategy_name = ? ORDER BY created_at DESC LIMIT ?",
                (strategy_name, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM optimization_history ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["best_params"] = json.loads(d["best_params"])
            result.append(d)
        return result

    # ============================================================
    # 统计
    # ============================================================

    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        conn = self._get_conn()
        return {
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "strategies": conn.execute("SELECT COUNT(DISTINCT strategy_name) FROM strategy_params").fetchone()[0],
            "trades": conn.execute("SELECT COUNT(*) FROM trade_records").fetchone()[0],
            "audit_logs": conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            "optimizations": conn.execute("SELECT COUNT(*) FROM optimization_history").fetchone()[0],
            "ip_whitelist": conn.execute("SELECT COUNT(*) FROM ip_whitelist WHERE enabled=1").fetchone()[0],
        }

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# ============================================================
# 全局单例
# ============================================================

_db: Optional[DatabaseManager] = None
_db_lock = threading.Lock()

def get_db() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = DatabaseManager()
    return _db


# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":
    db = get_db()
    # 创建默认admin用户
    import bcrypt
    if not db.get_user("admin"):
        hash_pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        db.create_user("admin", hash_pw, "admin")
        print("已创建默认admin用户")
    # 统计
    stats = db.get_stats()
    print(f"数据库统计: {stats}")
    db.close()