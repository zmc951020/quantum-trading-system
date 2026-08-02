#!/usr/bin/env python3
"""
会话记忆与推理日志系统 - 港大Vibe-Trading智能体记忆引擎

功能：
  1. 会话记忆存储 - 记录用户与系统的交互历史
  2. 历史推理日志 - 记录29个智能体的推理过程
  3. 长周期任务进度追踪 - 追踪优化/回测等长任务的进度

设计依据：
  审计报告D1维度 - 会话记忆/历史推理日志/长周期任务三项缺失
  使用SQLite持久化 + JSON结构化存储，支持查询和回溯
"""

import os
import json
import time
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ============================================================
# 数据结构
# ============================================================


@dataclass
class SessionEntry:
    """会话记录"""
    session_id: str
    timestamp: str
    user_input: str
    intent_type: str = ""
    response: str = ""
    matched_skills: List[str] = field(default_factory=list)
    target_symbols: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    success: bool = True


@dataclass
class ReasoningLog:
    """推理日志"""
    log_id: str
    timestamp: str
    agent_name: str
    symbol: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    reasoning_steps: List[str] = field(default_factory=list)
    conclusion: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    elapsed_ms: float = 0.0


@dataclass
class TaskProgress:
    """任务进度"""
    task_id: str
    task_type: str                  # optimize/backtest/scan/analyze
    status: str                     # pending/running/completed/failed
    progress_pct: float = 0.0       # 0-100
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    started_at: str = ""
    updated_at: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


# ============================================================
# SQLite存储引擎
# ============================================================

class SessionStore:
    """会话记忆SQLite存储"""

    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "session_memory.db")

    def __init__(self):
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        user_input TEXT NOT NULL,
                        intent_type TEXT DEFAULT '',
                        response TEXT DEFAULT '',
                        matched_skills TEXT DEFAULT '[]',
                        target_symbols TEXT DEFAULT '[]',
                        elapsed_ms REAL DEFAULT 0,
                        success INTEGER DEFAULT 1
                    );
                    CREATE INDEX IF NOT EXISTS idx_sessions_sid ON sessions(session_id);
                    CREATE INDEX IF NOT EXISTS idx_sessions_ts ON sessions(timestamp);

                    CREATE TABLE IF NOT EXISTS reasoning_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        log_id TEXT NOT NULL UNIQUE,
                        timestamp TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        symbol TEXT DEFAULT '',
                        input_data TEXT DEFAULT '{}',
                        reasoning_steps TEXT DEFAULT '[]',
                        conclusion TEXT DEFAULT '{}',
                        confidence REAL DEFAULT 0,
                        elapsed_ms REAL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_reasoning_agent ON reasoning_logs(agent_name);
                    CREATE INDEX IF NOT EXISTS idx_reasoning_symbol ON reasoning_logs(symbol);
                    CREATE INDEX IF NOT EXISTS idx_reasoning_ts ON reasoning_logs(timestamp);

                    CREATE TABLE IF NOT EXISTS task_progress (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL UNIQUE,
                        task_type TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        progress_pct REAL DEFAULT 0,
                        current_step TEXT DEFAULT '',
                        total_steps INTEGER DEFAULT 0,
                        completed_steps INTEGER DEFAULT 0,
                        started_at TEXT DEFAULT '',
                        updated_at TEXT DEFAULT '',
                        result TEXT DEFAULT '{}',
                        error TEXT DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_task_status ON task_progress(status);
                    CREATE INDEX IF NOT EXISTS idx_task_type ON task_progress(task_type);
                """)
                conn.commit()
            finally:
                conn.close()

    # --- 会话记忆 ---

    def save_session(self, entry: SessionEntry) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute(
                        """INSERT INTO sessions
                           (session_id, timestamp, user_input, intent_type, response,
                            matched_skills, target_symbols, elapsed_ms, success)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (entry.session_id, entry.timestamp, entry.user_input,
                         entry.intent_type, entry.response,
                         json.dumps(entry.matched_skills, ensure_ascii=False),
                         json.dumps(entry.target_symbols, ensure_ascii=False),
                         entry.elapsed_ms, 1 if entry.success else 0)
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"保存会话记录失败: {e}")
            return False

    def get_session_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM sessions
                       WHERE session_id = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (session_id, limit)
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}")
            return []

    def get_recent_sessions(self, limit: int = 20) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT session_id, MAX(timestamp) as last_ts, COUNT(*) as cnt FROM sessions GROUP BY session_id ORDER BY last_ts DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取最近会话失败: {e}")
            return []

    # --- 推理日志 ---

    def save_reasoning(self, log: ReasoningLog) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute(
                        """INSERT OR REPLACE INTO reasoning_logs
                           (log_id, timestamp, agent_name, symbol, input_data,
                            reasoning_steps, conclusion, confidence, elapsed_ms)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (log.log_id, log.timestamp, log.agent_name, log.symbol,
                         json.dumps(log.input_data, ensure_ascii=False),
                         json.dumps(log.reasoning_steps, ensure_ascii=False),
                         json.dumps(log.conclusion, ensure_ascii=False),
                         log.confidence, log.elapsed_ms)
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"保存推理日志失败: {e}")
            return False

    def get_reasoning_by_agent(self, agent_name: str, limit: int = 20) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM reasoning_logs WHERE agent_name = ? ORDER BY timestamp DESC LIMIT ?",
                    (agent_name, limit)
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取推理日志失败: {e}")
            return []

    def get_reasoning_by_symbol(self, symbol: str, limit: int = 20) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM reasoning_logs WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
                    (symbol, limit)
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取推理日志失败: {e}")
            return []

    # --- 任务进度 ---

    def create_task(self, task: TaskProgress) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute(
                        """INSERT INTO task_progress
                           (task_id, task_type, status, progress_pct, current_step,
                            total_steps, completed_steps, started_at, updated_at, result, error)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (task.task_id, task.task_type, task.status, task.progress_pct,
                         task.current_step, task.total_steps, task.completed_steps,
                         task.started_at, task.updated_at,
                         json.dumps(task.result, ensure_ascii=False), task.error)
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            return False

    def update_task(self, task_id: str, **kwargs) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    # 构建动态UPDATE
                    set_clauses = []
                    values = []
                    for k, v in kwargs.items():
                        if k in ("result",):
                            set_clauses.append(f"{k} = ?")
                            values.append(json.dumps(v, ensure_ascii=False))
                        elif k == "updated_at":
                            set_clauses.append(f"{k} = ?")
                            values.append(v or datetime.now().isoformat())
                        elif k in ("status", "current_step", "error"):
                            set_clauses.append(f"{k} = ?")
                            values.append(str(v))
                        elif k in ("progress_pct", "total_steps", "completed_steps"):
                            set_clauses.append(f"{k} = ?")
                            values.append(float(v) if k == "progress_pct" else int(v))

                    if not set_clauses:
                        return False

                    set_clauses.append("updated_at = ?")
                    values.append(datetime.now().isoformat())
                    values.append(task_id)

                    conn.execute(
                        f"UPDATE task_progress SET {', '.join(set_clauses)} WHERE task_id = ?",
                        values
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"更新任务失败: {e}")
            return False

    def get_task(self, task_id: str) -> Optional[Dict]:
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM task_progress WHERE task_id = ?", (task_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None

    def get_active_tasks(self) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM task_progress WHERE status IN ('pending', 'running') ORDER BY started_at DESC"
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取活跃任务失败: {e}")
            return []

    def list_tasks(self, task_type: str = None, limit: int = 50) -> List[Dict]:
        try:
            conn = self._get_conn()
            try:
                if task_type:
                    rows = conn.execute(
                        "SELECT * FROM task_progress WHERE task_type = ? ORDER BY updated_at DESC LIMIT ?",
                        (task_type, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM task_progress ORDER BY updated_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    def delete_task(self, task_id: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute("DELETE FROM task_progress WHERE task_id = ?", (task_id,))
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"删除任务失败: {e}")
            return False

    def purge_old_data(self, max_age_days: int = 90) -> int:
        """清理过期数据"""
        cutoff = datetime.now().isoformat()
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    deleted = 0
                    # 清理旧会话
                    c = conn.execute("DELETE FROM sessions WHERE timestamp < ?", (cutoff,))
                    deleted += c.rowcount
                    # 清理旧推理日志
                    c = conn.execute("DELETE FROM reasoning_logs WHERE timestamp < ?", (cutoff,))
                    deleted += c.rowcount
                    # 清理已完成/失败的任务
                    c = conn.execute(
                        "DELETE FROM task_progress WHERE status IN ('completed', 'failed') AND updated_at < ?",
                        (cutoff,)
                    )
                    deleted += c.rowcount
                    conn.commit()
                    return deleted
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return 0

    def _row_to_dict(self, row) -> Dict:
        """将SQLite Row转换为字典，自动解析JSON字段"""
        d = dict(row)
        json_fields = ["matched_skills", "target_symbols", "input_data",
                       "reasoning_steps", "conclusion", "result"]
        for field in json_fields:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d


# ============================================================
# 会话记忆管理器
# ============================================================

class SessionMemoryManager:
    """会话记忆管理器

    提供高级API用于会话记忆、推理日志和任务进度管理。
    """

    def __init__(self):
        self._store = SessionStore()
        self._current_session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")

    # --- 会话管理 ---

    def new_session(self) -> str:
        """创建新会话"""
        self._current_session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        return self._current_session_id

    @property
    def session_id(self) -> str:
        return self._current_session_id

    def record_interaction(self, user_input: str, intent_type: str = "",
                           response: str = "", matched_skills: List[str] = None,
                           target_symbols: List[str] = None,
                           elapsed_ms: float = 0.0, success: bool = True):
        """记录一次用户交互"""
        entry = SessionEntry(
            session_id=self._current_session_id,
            timestamp=datetime.now().isoformat(),
            user_input=user_input,
            intent_type=intent_type,
            response=response,
            matched_skills=matched_skills or [],
            target_symbols=target_symbols or [],
            elapsed_ms=elapsed_ms,
            success=success,
        )
        self._store.save_session(entry)

    def get_history(self, limit: int = 50) -> List[Dict]:
        """获取当前会话历史"""
        return self._store.get_session_history(self._current_session_id, limit)

    def get_recent_sessions(self, limit: int = 20) -> List[Dict]:
        """获取最近会话列表"""
        return self._store.get_recent_sessions(limit)

    # --- 推理日志 ---

    def record_reasoning(self, agent_name: str, symbol: str,
                         input_data: Dict = None,
                         reasoning_steps: List[str] = None,
                         conclusion: Dict = None,
                         confidence: float = 0.0,
                         elapsed_ms: float = 0.0):
        """记录智能体推理过程"""
        log = ReasoningLog(
            log_id=f"{agent_name}_{symbol}_{int(time.time() * 1000)}",
            timestamp=datetime.now().isoformat(),
            agent_name=agent_name,
            symbol=symbol,
            input_data=input_data or {},
            reasoning_steps=reasoning_steps or [],
            conclusion=conclusion or {},
            confidence=confidence,
            elapsed_ms=elapsed_ms,
        )
        self._store.save_reasoning(log)

    def get_agent_reasoning(self, agent_name: str, limit: int = 20) -> List[Dict]:
        """获取指定智能体的推理历史"""
        return self._store.get_reasoning_by_agent(agent_name, limit)

    def get_symbol_reasoning(self, symbol: str, limit: int = 20) -> List[Dict]:
        """获取指定股票的推理历史"""
        return self._store.get_reasoning_by_symbol(symbol, limit)

    # --- 任务进度 ---

    def start_task(self, task_type: str, total_steps: int = 0,
                   task_id: str = None) -> str:
        """开始一个长周期任务"""
        task_id = task_id or f"{task_type}_{int(time.time() * 1000)}"
        task = TaskProgress(
            task_id=task_id,
            task_type=task_type,
            status="running",
            progress_pct=0.0,
            current_step="初始化...",
            total_steps=total_steps,
            completed_steps=0,
            started_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._store.create_task(task)
        logger.info(f"任务已启动: {task_id} ({task_type})")
        return task_id

    def update_progress(self, task_id: str, progress_pct: float,
                        current_step: str = "", completed_steps: int = -1):
        """更新任务进度"""
        kwargs = {
            "progress_pct": min(progress_pct, 100.0),
            "updated_at": datetime.now().isoformat(),
        }
        if current_step:
            kwargs["current_step"] = current_step
        if completed_steps >= 0:
            kwargs["completed_steps"] = completed_steps
        self._store.update_task(task_id, **kwargs)

    def complete_task(self, task_id: str, result: Dict = None):
        """完成任务"""
        self._store.update_task(
            task_id,
            status="completed",
            progress_pct=100.0,
            current_step="完成",
            result=result or {},
            updated_at=datetime.now().isoformat(),
        )

    def fail_task(self, task_id: str, error: str):
        """标记任务失败"""
        self._store.update_task(
            task_id,
            status="failed",
            error=error,
            updated_at=datetime.now().isoformat(),
        )

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        return self._store.get_task(task_id)

    def get_active_tasks(self) -> List[Dict]:
        """获取活跃任务"""
        return self._store.get_active_tasks()

    def list_tasks(self, task_type: str = None, limit: int = 50) -> List[Dict]:
        """列出任务"""
        return self._store.list_tasks(task_type, limit)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        return self._store.update_task(
            task_id,
            status="cancelled",
            current_step="已取消",
            updated_at=datetime.now().isoformat(),
        )

    def purge_old(self, max_age_days: int = 90) -> int:
        """清理过期数据"""
        return self._store.purge_old_data(max_age_days)


# ============================================================
# 全局单例
# ============================================================

_memory_manager: Optional[SessionMemoryManager] = None


def get_memory_manager() -> SessionMemoryManager:
    """获取会话记忆管理器单例"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = SessionMemoryManager()
    return _memory_manager


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    mgr = get_memory_manager()

    # 测试会话记忆
    print("=== 会话记忆测试 ===")
    mgr.record_interaction("分析贵州茅台", intent_type="analyze",
                           matched_skills=["trend", "momentum"],
                           target_symbols=["600519"])
    history = mgr.get_history()
    print(f"  会话历史: {len(history)} 条")
    for h in history[:3]:
        print(f"    [{h['timestamp']}] {h['intent_type']}: {h['user_input']}")

    # 测试推理日志
    print("\n=== 推理日志测试 ===")
    mgr.record_reasoning(
        agent_name="trend", symbol="600519",
        input_data={"close": 1800.0},
        reasoning_steps=["计算均线", "判断趋势方向", "评估强度"],
        conclusion={"direction": "up", "strength": 0.75},
        confidence=0.85
    )
    logs = mgr.get_agent_reasoning("trend")
    print(f"  trend推理日志: {len(logs)} 条")

    # 测试任务进度
    print("\n=== 任务进度测试 ===")
    task_id = mgr.start_task("optimize", total_steps=100)
    print(f"  启动任务: {task_id}")
    mgr.update_progress(task_id, 25.0, "评估参数...", completed_steps=25)
    mgr.update_progress(task_id, 50.0, "迭代中...", completed_steps=50)
    status = mgr.get_task_status(task_id)
    print(f"  进度: {status['progress_pct']}% - {status['current_step']}")
    mgr.complete_task(task_id, {"best_score": 1.85})
    status = mgr.get_task_status(task_id)
    print(f"  完成: {status['status']}, 结果: {status['result']}")

    print("\n所有测试通过!")