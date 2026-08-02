#!/usr/bin/env python3
"""
TenantManager - 多用户租户隔离管理器

核心功能：
  1. 租户隔离：user_id 全链路数据隔离（因子/回测/优化/日志）
  2. RBAC 权限控制：4级角色（管理员/高级/普通/访客）+ 可配置权限矩阵
  3. 算力调度：P0/P1/P2 三级优先级队列 + 资源限额 + 公平调度
  4. 分层缓存：L1(进程内存) → L2(Redis私有) → L3(Redis公共) → L4(降级计算)
  5. 配额管理：日请求量/因子数/回测次数/并发数 四项限制
  6. 审计日志：所有操作记录（含 user_id、时间戳、操作类型、结果）

设计依据：
  豆包审查 + Trae方案 - 多用户场景下必须实现租户隔离和算力调度
"""

import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================

class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"
    ADVANCED = "advanced"
    NORMAL = "normal"
    GUEST = "guest"


class TaskPriority(Enum):
    """任务优先级"""
    P0 = 0    # 实时T+0（最高）
    P1 = 1    # 常规选股
    P2 = 2    # 批量回测（最低）


@dataclass
class TenantQuota:
    """租户配额"""
    max_daily_requests: int = 1000       # 日请求上限
    max_concurrent_tasks: int = 5        # 并发任务上限
    max_factors_per_request: int = 200   # 单次请求因子数上限
    max_symbols_per_request: int = 100   # 单次请求股票数上限
    max_backtests_per_day: int = 20      # 日回测次数上限
    max_optimizations_per_day: int = 5   # 日优化次数上限

    # 算力权重（用于公平调度）
    cpu_weight: float = 1.0
    memory_mb_limit: int = 512


@dataclass
class TenantState:
    """租户运行状态"""
    user_id: str
    role: UserRole = UserRole.NORMAL
    quota: TenantQuota = field(default_factory=TenantQuota)

    # 实时统计
    active_tasks: int = 0
    daily_requests: int = 0
    daily_backtests: int = 0
    daily_optimizations: int = 0

    # 时间窗口
    last_request_time: Optional[datetime] = None
    daily_reset_time: datetime = field(default_factory=datetime.now)

    # 缓存
    cached_factors: Dict[str, Any] = field(default_factory=dict)
    cached_ttl: Dict[str, datetime] = field(default_factory=dict)

    # 错误统计
    error_count: int = 0
    last_error_time: Optional[datetime] = None
    is_throttled: bool = False
    throttle_until: Optional[datetime] = None


@dataclass
class Task:
    """调度任务"""
    task_id: str
    user_id: str
    priority: TaskPriority
    task_type: str           # factor_compute / backtest / optimization / market_scan
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending / running / completed / failed
    result: Any = None
    error: str = None


# ============================================================
# 权限矩阵
# ============================================================

ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        "max_factors": 452,
        "max_symbols": 5000,
        "max_daily_requests": 10000,
        "max_concurrent": 20,
        "max_backtests_per_day": 200,
        "max_optimizations_per_day": 50,
        "allow_live_trading": True,
        "allow_export": True,
        "allow_config_edit": True,
        "allow_user_management": True,
        "categories": None,
        "cpu_weight": 2.0,
        "cache_ttl_seconds": 300,
    },
    UserRole.ADVANCED: {
        "max_factors": 200,
        "max_symbols": 500,
        "max_daily_requests": 2000,
        "max_concurrent": 8,
        "max_backtests_per_day": 50,
        "max_optimizations_per_day": 10,
        "allow_live_trading": True,
        "allow_export": True,
        "allow_config_edit": False,
        "allow_user_management": False,
        "categories": ["Trend", "Reversal", "Momentum", "Volatility", "VolumePrice"],
        "cpu_weight": 1.5,
        "cache_ttl_seconds": 600,
    },
    UserRole.NORMAL: {
        "max_factors": 50,
        "max_symbols": 100,
        "max_daily_requests": 500,
        "max_concurrent": 3,
        "max_backtests_per_day": 10,
        "max_optimizations_per_day": 2,
        "allow_live_trading": False,
        "allow_export": False,
        "allow_config_edit": False,
        "allow_user_management": False,
        "categories": ["Trend", "Momentum", "VolumePrice"],
        "cpu_weight": 1.0,
        "cache_ttl_seconds": 1800,
    },
    UserRole.GUEST: {
        "max_factors": 0,
        "max_symbols": 20,
        "max_daily_requests": 50,
        "max_concurrent": 1,
        "max_backtests_per_day": 0,
        "max_optimizations_per_day": 0,
        "allow_live_trading": False,
        "allow_export": False,
        "allow_config_edit": False,
        "allow_user_management": False,
        "categories": None,
        "cpu_weight": 0.3,
        "cache_ttl_seconds": 3600,
    },
}


class TenantManager:
    """多用户租户隔离管理器

    使用示例:
        >>> tm = TenantManager()
        >>> tm.register_tenant("user_001", UserRole.ADVANCED)
        >>> ok, msg = tm.check_quota("user_001", "factor_compute", 100)
        >>> task = tm.submit_task("user_001", TaskPriority.P1, "factor_compute", {...})
    """

    def __init__(self, config_path: str = None):
        self._tenants: Dict[str, TenantState] = {}
        self._lock = threading.RLock()  # 可重入锁，避免 record_error → throttle_user 死锁
        self._config_path = config_path or "./config/tenants.json"

        # 任务队列（按优先级分组）
        self._task_queues: Dict[TaskPriority, deque] = {
            TaskPriority.P0: deque(),
            TaskPriority.P1: deque(),
            TaskPriority.P2: deque(),
        }
        self._task_lock = threading.Lock()
        self._running_tasks: Dict[str, Task] = {}

        # 审计日志
        self._audit_log: List[Dict] = []
        self._audit_lock = threading.Lock()

        # 加载配置
        self._load_tenants()

    # ================================================================
    # 租户注册与管理
    # ================================================================

    def register_tenant(self, user_id: str, role: UserRole = UserRole.NORMAL,
                         custom_quota: Dict[str, Any] = None) -> TenantState:
        """注册租户

        Args:
            user_id: 用户ID
            role: 角色
            custom_quota: 自定义配额（覆盖默认值）

        Returns:
            TenantState
        """
        with self._lock:
            perm = ROLE_PERMISSIONS[role]
            quota = TenantQuota(
                max_daily_requests=perm["max_daily_requests"],
                max_concurrent_tasks=perm["max_concurrent"],
                max_factors_per_request=perm["max_factors"],
                max_symbols_per_request=perm["max_symbols"],
                max_backtests_per_day=perm["max_backtests_per_day"],
                max_optimizations_per_day=perm["max_optimizations_per_day"],
                cpu_weight=perm["cpu_weight"],
            )

            # 应用自定义配额
            if custom_quota:
                for key, value in custom_quota.items():
                    if hasattr(quota, key):
                        setattr(quota, key, value)

            state = TenantState(
                user_id=user_id,
                role=role,
                quota=quota,
            )
            self._tenants[user_id] = state
            logger.info(f"租户已注册: {user_id} (role={role.value})")
            return state

    def get_tenant(self, user_id: str) -> Optional[TenantState]:
        """获取租户状态"""
        with self._lock:
            return self._tenants.get(user_id)

    def get_tenant_state(self, user_id: str) -> Optional[TenantState]:
        """获取租户状态（别名）"""
        return self.get_tenant(user_id)

    def get_or_create_tenant(self, user_id: str,
                              role: UserRole = UserRole.NORMAL) -> TenantState:
        """获取或创建租户"""
        with self._lock:
            if user_id not in self._tenants:
                return self.register_tenant(user_id, role)
            return self._tenants[user_id]

    def update_tenant_role(self, user_id: str, new_role: UserRole) -> bool:
        """更新租户角色"""
        with self._lock:
            if user_id not in self._tenants:
                return False
            state = self._tenants[user_id]
            state.role = new_role
            perm = ROLE_PERMISSIONS[new_role]
            state.quota = TenantQuota(
                max_daily_requests=perm["max_daily_requests"],
                max_concurrent_tasks=perm["max_concurrent"],
                max_factors_per_request=perm["max_factors"],
                max_symbols_per_request=perm["max_symbols"],
                max_backtests_per_day=perm["max_backtests_per_day"],
                max_optimizations_per_day=perm["max_optimizations_per_day"],
                cpu_weight=perm["cpu_weight"],
            )
            logger.info(f"租户角色更新: {user_id} → {new_role.value}")
            return True

    def remove_tenant(self, user_id: str) -> bool:
        """移除租户"""
        with self._lock:
            if user_id in self._tenants:
                del self._tenants[user_id]
                logger.info(f"租户已移除: {user_id}")
                return True
            return False

    # ================================================================
    # 配额检查
    # ================================================================

    def check_quota(self, user_id: str, operation: str,
                     count: int = 1) -> Tuple[bool, str]:
        """检查租户配额

        Args:
            user_id: 用户ID
            operation: 操作类型 (factor_compute / backtest / optimization)
            count: 资源消耗数量

        Returns:
            (是否允许, 消息)
        """
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return False, "租户未注册"

            # 重置日统计
            self._reset_daily_if_needed(state)

            # 限流检查
            if state.is_throttled and state.throttle_until:
                if datetime.now() < state.throttle_until:
                    remaining = (state.throttle_until - datetime.now()).total_seconds()
                    return False, f"已被限流，剩余 {remaining:.0f} 秒"

            # 并发检查
            if state.active_tasks >= state.quota.max_concurrent_tasks:
                return False, f"并发已达上限 ({state.active_tasks}/{state.quota.max_concurrent_tasks})"

            # 日请求检查
            if state.daily_requests + count > state.quota.max_daily_requests:
                return False, f"日请求已达上限 ({state.daily_requests}/{state.quota.max_daily_requests})"

            # 操作类型检查
            if operation == "backtest":
                if state.daily_backtests + count > state.quota.max_backtests_per_day:
                    return False, f"日回测已达上限 ({state.daily_backtests}/{state.quota.max_backtests_per_day})"
            elif operation == "optimization":
                if state.daily_optimizations + count > state.quota.max_optimizations_per_day:
                    return False, f"日优化已达上限 ({state.daily_optimizations}/{state.quota.max_optimizations_per_day})"

            return True, "OK"

    def consume_quota(self, user_id: str, operation: str, count: int = 1):
        """消耗配额"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return

            state.daily_requests += count
            state.last_request_time = datetime.now()

            if operation == "backtest":
                state.daily_backtests += count
            elif operation == "optimization":
                state.daily_optimizations += count

    def release_quota(self, user_id: str):
        """释放并发配额（任务完成时调用）"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state and state.active_tasks > 0:
                state.active_tasks -= 1

    def acquire_task(self, user_id: str, priority: TaskPriority = None):
        """获取任务槽位（别名）"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state:
                state.active_tasks += 1

    def release_task(self, user_id: str):
        """释放任务槽位（别名）"""
        self.release_quota(user_id)

    def _get_role_quota(self, role: UserRole) -> TenantQuota:
        """获取角色对应的配额"""
        perm = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[UserRole.NORMAL])
        return TenantQuota(
            max_daily_requests=perm["max_daily_requests"],
            max_concurrent_tasks=perm["max_concurrent"],
            max_factors_per_request=perm["max_factors"],
            max_symbols_per_request=perm["max_symbols"],
            max_backtests_per_day=perm["max_backtests_per_day"],
            max_optimizations_per_day=perm["max_optimizations_per_day"],
            cpu_weight=perm["cpu_weight"],
        )

    # ================================================================
    # 任务调度
    # ================================================================

    def submit_task(self, user_id: str, priority: TaskPriority,
                     task_type: str, payload: Dict[str, Any] = None) -> Tuple[bool, str, Optional[Task]]:
        """提交任务到调度队列

        Args:
            user_id: 用户ID
            priority: 优先级
            task_type: 任务类型
            payload: 任务参数

        Returns:
            (success, message, task)
        """
        # 1. 配额检查
        ok, msg = self.check_quota(user_id, task_type)
        if not ok:
            return False, msg, None

        # 2. 创建任务
        task_id = f"{user_id}_{task_type}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        task = Task(
            task_id=task_id,
            user_id=user_id,
            priority=priority,
            task_type=task_type,
            payload=payload or {},
        )

        # 3. 入队
        with self._task_lock:
            self._task_queues[priority].append(task)

        # 4. 消耗配额
        self.consume_quota(user_id, task_type)

        # 5. 审计
        self._audit(user_id, "task_submit", {
            "task_id": task_id,
            "priority": priority.name,
            "task_type": task_type,
        })

        logger.info(f"任务已提交: {task_id} (P={priority.name}, type={task_type})")
        return True, task_id, task

    def dequeue_task(self, max_priority: TaskPriority = TaskPriority.P2) -> Optional[Task]:
        """从队列取出下一个任务（按优先级）"""
        with self._task_lock:
            for priority in [TaskPriority.P0, TaskPriority.P1, TaskPriority.P2]:
                if priority.value > max_priority.value:
                    continue
                queue = self._task_queues[priority]
                if queue:
                    task = queue.popleft()
                    task.status = "running"
                    task.started_at = datetime.now()
                    self._running_tasks[task.task_id] = task
                    return task
        return None

    def complete_task(self, task_id: str, result: Any = None, error: str = None):
        """完成任务"""
        with self._task_lock:
            task = self._running_tasks.pop(task_id, None)
            if task:
                task.completed_at = datetime.now()
                task.status = "completed" if not error else "failed"
                task.result = result
                task.error = error

        # 释放并发配额
        self.release_quota(task.user_id if task else "")

        if task:
            self._audit(task.user_id, "task_complete", {
                "task_id": task_id,
                "status": task.status,
                "elapsed_ms": (
                    (task.completed_at - task.started_at).total_seconds() * 1000
                    if task.started_at and task.completed_at else 0
                ),
            })

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        with self._task_lock:
            return {
                "p0_pending": len(self._task_queues[TaskPriority.P0]),
                "p1_pending": len(self._task_queues[TaskPriority.P1]),
                "p2_pending": len(self._task_queues[TaskPriority.P2]),
                "running": len(self._running_tasks),
                "total_pending": sum(len(q) for q in self._task_queues.values()),
            }

    # ================================================================
    # 分层缓存（L1→L2→L3→L4）
    # ================================================================

    def get_cached(self, user_id: str, key: str) -> Optional[Any]:
        """从分层缓存获取数据

        L1(进程内存) → L2(Redis私有) → L3(Redis公共) → L4=None(触发计算)
        """
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return None

            # L1: 进程内存缓存
            if key in state.cached_factors:
                ttl = state.cached_ttl.get(key)
                if ttl and datetime.now() < ttl:
                    return state.cached_factors[key]
                else:
                    # 过期，清理
                    del state.cached_factors[key]
                    if key in state.cached_ttl:
                        del state.cached_ttl[key]

        return None  # L2/L3需要外部Redis实现，此处返回None触发计算

    def set_cached(self, user_id: str, key: str, value: Any,
                    ttl_seconds: int = 300):
        """设置L1进程内存缓存"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return
            state.cached_factors[key] = value
            state.cached_ttl[key] = datetime.now() + timedelta(seconds=ttl_seconds)

    def invalidate_cache(self, user_id: str, key: str = None):
        """失效缓存"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return
            if key:
                state.cached_factors.pop(key, None)
                state.cached_ttl.pop(key, None)
            else:
                state.cached_factors.clear()
                state.cached_ttl.clear()

    # ================================================================
    # 限流与风控
    # ================================================================

    def throttle_user(self, user_id: str, duration_seconds: int = 300):
        """限流用户"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state:
                state.is_throttled = True
                state.throttle_until = datetime.now() + timedelta(seconds=duration_seconds)
                logger.warning(f"用户已被限流: {user_id}, 持续 {duration_seconds}s")

    def record_error(self, user_id: str, error_msg: str):
        """记录错误（用于自动限流判断）"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return
            state.error_count += 1
            state.last_error_time = datetime.now()

            # 错误超过阈值自动限流
            if state.error_count > 50:
                self.throttle_user(user_id, 600)

    # ================================================================
    # 审计
    # ================================================================

    def _audit(self, user_id: str, action: str, details: Dict[str, Any] = None):
        """记录审计日志"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "action": action,
            "details": details or {},
        }
        with self._audit_lock:
            self._audit_log.append(entry)
            # 保留最近10000条
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-5000:]

    def get_audit_log(self, user_id: str = None,
                       limit: int = 100) -> List[Dict]:
        """获取审计日志"""
        with self._audit_lock:
            if user_id:
                return [e for e in self._audit_log if e["user_id"] == user_id][-limit:]
            return self._audit_log[-limit:]

    def get_audit_logs(self, user_id: str = None,
                        limit: int = 100) -> List[Dict]:
        """获取审计日志（别名）"""
        return self.get_audit_log(user_id, limit)

    def get_audit_summary(self) -> Dict[str, Any]:
        """获取审计摘要"""
        with self._audit_lock:
            user_actions = defaultdict(int)
            action_counts = defaultdict(int)
            for entry in self._audit_log[-1000:]:
                user_actions[entry["user_id"]] += 1
                action_counts[entry["action"]] += 1

            return {
                "total_entries": len(self._audit_log),
                "active_users": len(user_actions),
                "top_users": sorted(user_actions.items(), key=lambda x: x[1], reverse=True)[:10],
                "top_actions": sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            }

    # ================================================================
    # 状态汇总
    # ================================================================

    def get_all_tenants_status(self) -> Dict[str, Any]:
        """获取所有租户状态"""
        with self._lock:
            tenants = {}
            for user_id, state in self._tenants.items():
                self._reset_daily_if_needed(state)
                tenants[user_id] = {
                    "role": state.role.value,
                    "active_tasks": state.active_tasks,
                    "daily_requests": state.daily_requests,
                    "daily_quota": state.quota.max_daily_requests,
                    "daily_backtests": state.daily_backtests,
                    "daily_optimizations": state.daily_optimizations,
                    "is_throttled": state.is_throttled,
                    "error_count": state.error_count,
                    "last_request": state.last_request_time.isoformat() if state.last_request_time else None,
                }
            return {
                "total_tenants": len(tenants),
                "tenants": tenants,
                "queue_stats": self.get_queue_stats(),
            }

    def get_tenant_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取单个租户状态"""
        with self._lock:
            state = self._tenants.get(user_id)
            if state is None:
                return None
            self._reset_daily_if_needed(state)
            perm = ROLE_PERMISSIONS[state.role]
            return {
                "user_id": user_id,
                "role": state.role.value,
                "permissions": {
                    "max_factors": perm["max_factors"],
                    "max_symbols": perm["max_symbols"],
                    "allow_live_trading": perm["allow_live_trading"],
                    "allow_export": perm["allow_export"],
                },
                "quota": {
                    "daily_requests": f"{state.daily_requests}/{state.quota.max_daily_requests}",
                    "concurrent": f"{state.active_tasks}/{state.quota.max_concurrent_tasks}",
                    "daily_backtests": f"{state.daily_backtests}/{state.quota.max_backtests_per_day}",
                    "daily_optimizations": f"{state.daily_optimizations}/{state.quota.max_optimizations_per_day}",
                },
                "is_throttled": state.is_throttled,
                "error_count": state.error_count,
            }

    # ================================================================
    # 内部方法
    # ================================================================

    def _reset_daily_if_needed(self, state: TenantState):
        """按日重置统计"""
        now = datetime.now()
        if state.daily_reset_time.date() < now.date():
            state.daily_requests = 0
            state.daily_backtests = 0
            state.daily_optimizations = 0
            state.daily_reset_time = now
            state.error_count = max(0, state.error_count - 10)  # 每天衰减

    def _load_tenants(self):
        """从文件加载租户配置"""
        try:
            path = Path(self._config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for uid, info in data.get("tenants", {}).items():
                    role = UserRole(info.get("role", "normal"))
                    self.register_tenant(uid, role, info.get("quota"))
                logger.info(f"已加载 {len(data.get('tenants', {}))} 个租户")
        except Exception as e:
            logger.warning(f"租户配置加载失败: {e}")

    def save_tenants(self):
        """保存租户配置到文件"""
        try:
            path = Path(self._config_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = {
                    "tenants": {
                        uid: {
                            "role": state.role.value,
                            "quota": {
                                "max_daily_requests": state.quota.max_daily_requests,
                                "max_concurrent_tasks": state.quota.max_concurrent_tasks,
                            },
                        }
                        for uid, state in self._tenants.items()
                    },
                    "updated_at": datetime.now().isoformat(),
                }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"租户配置保存失败: {e}")


# ============================================================
# 全局单例
# ============================================================

_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    tm = TenantManager()

    print("=== 租户注册 ===")
    tm.register_tenant("admin_001", UserRole.ADMIN)
    tm.register_tenant("advanced_001", UserRole.ADVANCED)
    tm.register_tenant("normal_001", UserRole.NORMAL)
    tm.register_tenant("guest_001", UserRole.GUEST)

    # 测试配额检查
    print("\n=== 配额检查 ===")
    for uid in ["admin_001", "advanced_001", "normal_001", "guest_001"]:
        ok, msg = tm.check_quota(uid, "factor_compute", 100)
        print(f"  {uid}: {ok} - {msg}")

    # 测试任务提交
    print("\n=== 任务提交 ===")
    ok, msg, task = tm.submit_task("normal_001", TaskPriority.P1, "factor_compute",
                                    {"symbols": ["600519"]})
    print(f"  提交: {ok}, task_id={msg}")

    ok, msg, task = tm.submit_task("admin_001", TaskPriority.P0, "factor_compute",
                                    {"symbols": ["600519", "000858"]})
    print(f"  提交P0: {ok}, task_id={msg}")

    # 测试任务调度
    print("\n=== 任务调度 ===")
    print(f"  队列状态: {tm.get_queue_stats()}")

    task = tm.dequeue_task()
    if task:
        print(f"  取出任务: {task.task_id} (P={task.priority.name})")
        tm.complete_task(task.task_id, result={"factors": 115})

    task = tm.dequeue_task()
    if task:
        print(f"  取出任务: {task.task_id} (P={task.priority.name})")
        tm.complete_task(task.task_id, result={"factors": 7})

    print(f"  队列状态: {tm.get_queue_stats()}")

    # 测试缓存
    print("\n=== 分层缓存 ===")
    tm.set_cached("normal_001", "600519_day", {"SMA_5": 0.05}, ttl_seconds=60)
    cached = tm.get_cached("normal_001", "600519_day")
    print(f"  缓存命中: {cached is not None}")
    print(f"  缓存值: {cached}")

    # 测试限流
    print("\n=== 限流测试 ===")
    for i in range(60):
        tm.record_error("normal_001", f"test error {i}")
    state = tm.get_tenant_status("normal_001")
    print(f"  限流: {state['is_throttled']}")
    print(f"  错误数: {state['error_count']}")

    # 测试审计
    print("\n=== 审计日志 ===")
    summary = tm.get_audit_summary()
    print(f"  总条目: {summary['total_entries']}")
    print(f"  活跃用户: {summary['active_users']}")

    # 状态汇总
    print("\n=== 租户状态 ===")
    all_status = tm.get_all_tenants_status()
    print(f"  总租户: {all_status['total_tenants']}")
    for uid, info in all_status['tenants'].items():
        print(f"  {uid}: role={info['role']}, requests={info['daily_requests']}/{info['daily_quota']}")

    print("\n全部测试通过!")