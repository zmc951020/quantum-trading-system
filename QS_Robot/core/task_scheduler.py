#!/usr/bin/env python3
"""
任务调度器（Task Scheduler）

核心能力：
  1. 基于 APScheduler 的定时任务管理
  2. 支持多种触发器：cron、interval、date
  3. 任务持久化到文件
  4. 支持并发任务执行
  5. 任务状态跟踪和日志记录

支持的任务类型：
  - 策略优化任务
  - 回测任务
  - 数据更新任务
  - 自定义任务
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 任务状态枚举
# ============================================================

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class TaskType(Enum):
    OPTIMIZATION = "optimization"
    BACKTEST = "backtest"
    DATA_UPDATE = "data_update"
    CUSTOM = "custom"

# ============================================================
# 任务数据类
# ============================================================

@dataclass
class Task:
    """任务定义"""
    id: str
    name: str
    task_type: TaskType
    func: Callable
    args: List = field(default_factory=list)
    kwargs: Dict = field(default_factory=dict)
    trigger_type: str = "interval"  # cron, interval, date
    trigger_args: Dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    last_result: Any = None
    last_error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """转换为可序列化的字典"""
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type.value,
            "trigger_type": self.trigger_type,
            "trigger_args": self.trigger_args,
            "status": self.status.value,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

# ============================================================
# 调度器日志
# ============================================================

@dataclass
class TaskLog:
    """任务执行日志"""
    task_id: str
    timestamp: datetime
    level: str  # INFO, WARNING, ERROR
    message: str

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message
        }

# ============================================================
# 任务调度器核心类
# ============================================================

class TaskScheduler:
    """任务调度器"""

    def __init__(self, config_path: str = None):
        self._scheduler = None
        self._tasks: Dict[str, Task] = {}
        self._logs: List[TaskLog] = []
        self._lock = threading.Lock()
        self._config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "scheduler_config.json"
        )
        self._init_scheduler()
        self._load_tasks()

    def _init_scheduler(self):
        """初始化 APScheduler"""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.memory import MemoryJobStore
            from apscheduler.executors.pool import ThreadPoolExecutor

            self._scheduler = BackgroundScheduler(
                jobstores={"default": MemoryJobStore()},
                executors={
                    "default": ThreadPoolExecutor(max_workers=5),
                    "processpool": {"type": "processpool", "max_workers": 2}
                },
                job_defaults={
                    "coalesce": False,
                    "max_instances": 3
                }
            )
            self._scheduler.start()
            print(f"[TaskScheduler] APScheduler已启动")
        except ImportError:
            print(f"[TaskScheduler] APScheduler未安装，使用简单调度器")
            self._scheduler = None

    def _load_tasks(self):
        """从配置文件加载任务"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    for task_data in config.get("tasks", []):
                        task = Task(
                            id=task_data["id"],
                            name=task_data["name"],
                            task_type=TaskType(task_data["task_type"]),
                            func=lambda: None,  # 函数不能序列化，需要重新注册
                            trigger_type=task_data["trigger_type"],
                            trigger_args=task_data["trigger_args"],
                            status=TaskStatus(task_data["status"]),
                            run_count=task_data.get("run_count", 0),
                            created_at=datetime.fromisoformat(task_data["created_at"]),
                            updated_at=datetime.fromisoformat(task_data["updated_at"])
                        )
                        self._tasks[task.id] = task
                print(f"[TaskScheduler] 已加载 {len(self._tasks)} 个任务")
        except Exception as e:
            print(f"[TaskScheduler] 加载任务配置失败: {e}")

    def _save_tasks(self):
        """保存任务到配置文件"""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            config = {
                "tasks": [task.to_dict() for task in self._tasks.values()],
                "last_updated": datetime.now().isoformat()
            }
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[TaskScheduler] 保存任务配置失败: {e}")

    def _log(self, task_id: str, level: str, message: str):
        """记录任务日志"""
        self._logs.append(TaskLog(
            task_id=task_id,
            timestamp=datetime.now(),
            level=level,
            message=message
        ))
        # 保留最近1000条日志
        if len(self._logs) > 1000:
            self._logs = self._logs[-1000:]

    # --------------------------------------------------------
    # 任务管理
    # --------------------------------------------------------

    def add_task(self, name: str, task_type: TaskType, func: Callable,
                 trigger_type: str = "interval", trigger_args: Dict = None,
                 args: List = None, kwargs: Dict = None) -> str:
        """添加任务"""
        task_id = f"{task_type.value}_{int(time.time())}"

        task = Task(
            id=task_id,
            name=name,
            task_type=task_type,
            func=func,
            args=args or [],
            kwargs=kwargs or {},
            trigger_type=trigger_type,
            trigger_args=trigger_args or {}
        )

        with self._lock:
            self._tasks[task_id] = task

            # 在APScheduler中注册任务
            if self._scheduler:
                try:
                    if trigger_type == "interval":
                        self._scheduler.add_job(
                            self._run_task_wrapper,
                            trigger="interval",
                            id=task_id,
                            args=[task_id],
                            **trigger_args
                        )
                    elif trigger_type == "cron":
                        self._scheduler.add_job(
                            self._run_task_wrapper,
                            trigger="cron",
                            id=task_id,
                            args=[task_id],
                            **trigger_args
                        )
                    elif trigger_type == "date":
                        self._scheduler.add_job(
                            self._run_task_wrapper,
                            trigger="date",
                            id=task_id,
                            args=[task_id],
                            run_date=trigger_args.get("run_date")
                        )

                    job = self._scheduler.get_job(task_id)
                    if job:
                        task.next_run = job.next_run
                    task.status = TaskStatus.PENDING
                    self._log(task_id, "INFO", f"任务已添加: {name}")
                except Exception as e:
                    self._log(task_id, "ERROR", f"注册任务失败: {e}")

            self._save_tasks()

        return task_id

    def remove_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id in self._tasks:
                if self._scheduler:
                    self._scheduler.remove_job(task_id)
                del self._tasks[task_id]
                self._save_tasks()
                self._log(task_id, "INFO", "任务已删除")
                return True
        return False

    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        with self._lock:
            if task_id in self._tasks:
                if self._scheduler:
                    self._scheduler.pause_job(task_id)
                self._tasks[task_id].status = TaskStatus.PAUSED
                self._tasks[task_id].updated_at = datetime.now()
                self._save_tasks()
                self._log(task_id, "INFO", "任务已暂停")
                return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        with self._lock:
            if task_id in self._tasks:
                if self._scheduler:
                    self._scheduler.resume_job(task_id)
                    job = self._scheduler.get_job(task_id)
                    if job:
                        self._tasks[task_id].next_run = job.next_run
                self._tasks[task_id].status = TaskStatus.PENDING
                self._tasks[task_id].updated_at = datetime.now()
                self._save_tasks()
                self._log(task_id, "INFO", "任务已恢复")
                return True
        return False

    def run_task_now(self, task_id: str) -> Any:
        """立即运行任务"""
        if task_id not in self._tasks:
            return None
        return self._run_task(task_id)

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        """获取所有任务列表"""
        return list(self._tasks.values())

    # --------------------------------------------------------
    # 任务执行
    # --------------------------------------------------------

    def _run_task_wrapper(self, task_id: str):
        """任务执行包装器（用于APScheduler调用）"""
        self._run_task(task_id)

    def _run_task(self, task_id: str) -> Any:
        """执行任务"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        with self._lock:
            task.status = TaskStatus.RUNNING
            task.last_run = datetime.now()
            task.updated_at = datetime.now()

        try:
            self._log(task_id, "INFO", f"开始执行任务: {task.name}")
            result = task.func(*task.args, **task.kwargs)
            task.last_result = result
            task.run_count += 1
            task.status = TaskStatus.COMPLETED
            self._log(task_id, "INFO", f"任务执行成功: {task.name}")
            return result

        except Exception as e:
            task.last_error = str(e)
            task.status = TaskStatus.FAILED
            self._log(task_id, "ERROR", f"任务执行失败: {e}")
            return None

        finally:
            with self._lock:
                if self._scheduler:
                    job = self._scheduler.get_job(task_id)
                    if job:
                        task.next_run = job.next_run
                self._save_tasks()

    # --------------------------------------------------------
    # 快捷方法
    # --------------------------------------------------------

    def schedule_daily_task(self, name: str, task_type: TaskType, func: Callable,
                            hour: int = 9, minute: int = 30,
                            args: List = None, kwargs: Dict = None) -> str:
        """添加每日定时任务"""
        return self.add_task(
            name=name,
            task_type=task_type,
            func=func,
            trigger_type="cron",
            trigger_args={"hour": hour, "minute": minute},
            args=args,
            kwargs=kwargs
        )

    def schedule_hourly_task(self, name: str, task_type: TaskType, func: Callable,
                             minute: int = 0, args: List = None, kwargs: Dict = None) -> str:
        """添加每小时定时任务"""
        return self.add_task(
            name=name,
            task_type=task_type,
            func=func,
            trigger_type="cron",
            trigger_args={"minute": minute},
            args=args,
            kwargs=kwargs
        )

    def schedule_interval_task(self, name: str, task_type: TaskType, func: Callable,
                               minutes: int = 60, args: List = None, kwargs: Dict = None) -> str:
        """添加间隔任务"""
        return self.add_task(
            name=name,
            task_type=task_type,
            func=func,
            trigger_type="interval",
            trigger_args={"minutes": minutes},
            args=args,
            kwargs=kwargs
        )

    def schedule_once_task(self, name: str, task_type: TaskType, func: Callable,
                           run_date: datetime, args: List = None, kwargs: Dict = None) -> str:
        """添加一次性任务"""
        return self.add_task(
            name=name,
            task_type=task_type,
            func=func,
            trigger_type="date",
            trigger_args={"run_date": run_date},
            args=args,
            kwargs=kwargs
        )

    # --------------------------------------------------------
    # 日志和统计
    # --------------------------------------------------------

    def get_logs(self, task_id: str = None, limit: int = 100) -> List[TaskLog]:
        """获取任务日志"""
        logs = self._logs
        if task_id:
            logs = [l for l in logs if l.task_id == task_id]
        return logs[-limit:]

    def get_stats(self) -> Dict:
        """获取调度器统计信息"""
        stats = {
            "total_tasks": len(self._tasks),
            "running_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING),
            "pending_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING),
            "completed_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED),
            "paused_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.PAUSED),
            "total_runs": sum(t.run_count for t in self._tasks.values()),
            "log_count": len(self._logs)
        }
        return stats

# ============================================================
# 全局调度器
# ============================================================

_global_scheduler = None
_global_scheduler_lock = threading.Lock()

def get_task_scheduler() -> TaskScheduler:
    """获取任务调度器单例"""
    global _global_scheduler
    if _global_scheduler is None:
        with _global_scheduler_lock:
            if _global_scheduler is None:
                _global_scheduler = TaskScheduler()
    return _global_scheduler

# ============================================================
# 示例任务
# ============================================================

def sample_data_update_task():
    """示例数据更新任务"""
    print(f"[{datetime.now()}] 执行数据更新任务...")
    # 这里可以添加实际的数据更新逻辑
    return {"success": True, "message": "数据更新完成"}

def sample_strategy_optimization_task(strategy_name: str):
    """示例策略优化任务"""
    print(f"[{datetime.now()}] 执行策略优化: {strategy_name}")
    return {"success": True, "strategy": strategy_name, "result": "优化完成"}

# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    scheduler = get_task_scheduler()

    # 添加示例任务
    task_id1 = scheduler.schedule_interval_task(
        name="数据更新测试",
        task_type=TaskType.DATA_UPDATE,
        func=sample_data_update_task,
        minutes=1
    )
    print(f"添加任务: {task_id1}")

    task_id2 = scheduler.schedule_daily_task(
        name="策略优化测试",
        task_type=TaskType.OPTIMIZATION,
        func=sample_strategy_optimization_task,
        hour=10,
        minute=0,
        args=["TestStrategy"]
    )
    print(f"添加任务: {task_id2}")

    # 列出任务
    tasks = scheduler.list_tasks()
    print(f"\n任务列表 ({len(tasks)}):")
    for task in tasks:
        print(f"  {task.id}: {task.name} - {task.status.value}")

    # 获取统计
    stats = scheduler.get_stats()
    print(f"\n统计信息:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 立即运行一次
    print("\n立即运行任务...")
    result = scheduler.run_task_now(task_id1)
    print(f"任务结果: {result}")

    print("\n调度器运行中... (按 Ctrl+C 停止)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止调度器")
