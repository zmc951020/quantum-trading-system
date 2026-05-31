"""数据库连接池优化器
P3-3修补项 - 连接池参数调优/慢查询监控/死锁检测
"""
import sqlite3, time, os, threading, logging
from queue import Queue
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DEFAULT_POOL_CONFIG = {
    "pool_size": int(os.getenv("AURORA_DB_POOL_SIZE", "5")),
    "timeout": float(os.getenv("AURORA_DB_TIMEOUT", "30.0")),
    "check_same_thread": False,
    "isolation_level": None,
    "cached_statements": 100,
}

QUERY_LOG_THRESHOLD_MS = 100
SLOW_QUERY_LOG_THRESHOLD_MS = 500

class ConnectionPool:
    """SQLite连接池，支持WAL模式和多线程"""

    def __init__(self, db_path="aurora_backtest.db", pool_size=None):
        self.db_path = db_path
        self.pool_size = pool_size or DEFAULT_POOL_CONFIG["pool_size"]
        self._pool = Queue(maxsize=self.pool_size)
        self._created = 0
        self._lock = threading.Lock()
        self._stats = {"total_connections": 0, "peak_connections": 0, "slow_queries": 0, "total_queries": 0}
        self._init_pool()

    def _create_connection(self):
        conn = sqlite3.connect(self.db_path, **{k: v for k, v in DEFAULT_POOL_CONFIG.items() if k != "pool_size"})
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        self._created += 1
        self._stats["total_connections"] += 1
        self._stats["peak_connections"] = max(self._stats["peak_connections"], self._created)
        return conn

    def _init_pool(self):
        for _ in range(min(2, self.pool_size)):
            self._pool.put(self._create_connection())

    def get_connection(self, timeout=None):
        timeout = timeout or DEFAULT_POOL_CONFIG["timeout"]
        try:
            conn = self._pool.get(timeout=timeout)
            try:
                conn.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                conn = self._create_connection()
            return conn
        except Exception:
            return self._create_connection()

    def return_connection(self, conn):
        try:
            if self._pool.qsize() < self.pool_size:
                self._pool.put(conn)
            else:
                conn.close()
                self._created -= 1
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def get_stats(self):
        return dict(self._stats)

    def close_all(self):
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            conn.close()
            self._created -= 1

db_pool = ConnectionPool()

class QueryProfiler:
    """慢查询监控器"""

    @staticmethod
    def profile_query(cursor, sql, params=None):
        import traceback
        db_pool._stats["total_queries"] += 1
        start = time.perf_counter()
        cursor.execute(sql, params or ())
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > SLOW_QUERY_LOG_THRESHOLD_MS:
            db_pool._stats["slow_queries"] += 1
            logger.warning(f"[慢查询 {elapsed_ms:.1f}ms] {sql[:200]} caller={traceback.extract_stack()[-3].name}")
        elif elapsed_ms > QUERY_LOG_THRESHOLD_MS:
            logger.debug(f"[查询 {elapsed_ms:.1f}ms] {sql[:100]}")
        return cursor

class DeadlockDetector:
    """死锁检测器"""

    def __init__(self, timeout_seconds=30):
        self.timeout = timeout_seconds

    def execute_with_timeout(self, cursor, sql, params=None):
        start = time.time()
        try:
            cursor.execute(sql, params or ())
        except sqlite3.OperationalError as e:
            elapsed = time.time() - start
            if "database is locked" in str(e).lower() and elapsed < self.timeout:
                logger.warning(f"检测到数据库锁竞争: {sql[:100]}")
            raise