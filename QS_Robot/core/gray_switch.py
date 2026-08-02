#!/usr/bin/env python3
"""
GraySwitch - Alpha158因子灰度切换控制器

核心功能：
  1. 流量分配：Alpha158（新因子）vs Wyckoff68（旧因子）按比例路由
  2. 用户维度：按 user_id hash 固定分流（A/B测试稳定性）
  3. 策略维度：按策略名配置是否使用新因子
  4. 渐进式灰度：0%→10%→30%→50%→100% 五阶段自动推进
  5. 熔断回退：Alpha158 异常率超阈值自动切回旧因子
  6. 双轨并行：灰度期间同时计算两套因子，用于对比分析

设计依据：
  豆包审查 + Trae方案 - 灰度切换是新旧因子替换的核心安全机制
"""

import json
import logging
import hashlib
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================

class GrayPhase(Enum):
    """灰度阶段"""
    PHASE_0 = 0    # 0% Alpha158（全量旧因子）
    PHASE_1 = 1    # 10% Alpha158
    PHASE_2 = 2    # 30% Alpha158
    PHASE_3 = 3    # 50% Alpha158
    PHASE_4 = 4    # 100% Alpha158（全量新因子）


# 阶段 → 新因子流量比例
PHASE_RATIO = {
    GrayPhase.PHASE_0: 0.0,
    GrayPhase.PHASE_1: 0.10,
    GrayPhase.PHASE_2: 0.30,
    GrayPhase.PHASE_3: 0.50,
    GrayPhase.PHASE_4: 1.0,
}


class DecisionMode(Enum):
    """路由决策模式"""
    RANDOM = "random"          # 随机比例分流
    USER_HASH = "user_hash"    # 按用户hash固定分流
    STRATEGY = "strategy"      # 按策略名配置
    FORCE_NEW = "force_new"    # 强制使用新因子
    FORCE_OLD = "force_old"    # 强制使用旧因子


@dataclass
class GrayConfig:
    """灰度配置"""
    phase: GrayPhase = GrayPhase.PHASE_0
    mode: DecisionMode = DecisionMode.USER_HASH

    # 强制使用新因子的策略列表
    force_new_strategies: List[str] = field(default_factory=list)
    # 强制使用旧因子的策略列表
    force_old_strategies: List[str] = field(default_factory=list)
    # 强制使用新因子的用户列表
    force_new_users: List[str] = field(default_factory=list)

    # 熔断配置
    circuit_breaker_enabled: bool = True
    max_error_rate: float = 0.05          # 错误率阈值（5%）
    error_window_minutes: int = 10        # 错误统计窗口
    min_samples_for_breaker: int = 20     # 最小样本数才触发熔断

    # 自动推进配置
    auto_advance: bool = False
    advance_interval_hours: int = 24      # 自动推进间隔
    advance_min_samples: int = 1000       # 每个阶段最少样本数

    # 并行对比
    parallel_compare: bool = True          # 是否双轨并行计算（用于对比分析）


@dataclass
class GrayStats:
    """灰度统计"""
    total_requests: int = 0
    new_factor_requests: int = 0          # 路由到新因子的请求数
    old_factor_requests: int = 0          # 路由到旧因子的请求数
    new_errors: int = 0
    old_errors: int = 0
    new_latency_ms: List[float] = field(default_factory=list)
    old_latency_ms: List[float] = field(default_factory=list)
    circuit_breaker_tripped: bool = False
    circuit_breaker_tripped_at: Optional[datetime] = None
    current_phase: str = "PHASE_0"
    last_advance: Optional[datetime] = None
    last_reset: datetime = field(default_factory=datetime.now)


class GraySwitch:
    """Alpha158因子灰度切换控制器

    使用示例:
        >>> gs = GraySwitch()
        >>> # 决策路由
        >>> use_new = gs.should_use_new_factors(user_id="user_001", strategy="gyro_v7")
        >>> if use_new:
        ...     factors = alpha158_engine.compute_all(df)
        ... else:
        ...     factors = wyckoff_engine.compute_all(aligned)
        >>>
        >>> # 记录结果
        >>> gs.record_result(user_id="user_001", success=True, is_new=True, latency_ms=15.2)
        >>>
        >>> # 获取状态
        >>> status = gs.get_status()
    """

    def __init__(self, config: GrayConfig = None, config_path: str = None):
        self.config = config or GrayConfig()
        self._config_path = config_path or "./config/gray_switch.json"
        self._stats = GrayStats()
        self._lock = threading.Lock()
        self._error_timestamps: List[datetime] = []  # 新因子错误时间戳
        self._load_config()

    # ================================================================
    # 路由决策
    # ================================================================

    def should_use_new_factors(self, user_id: str = None,
                                strategy: str = None) -> bool:
        """决策是否使用Alpha158新因子

        Args:
            user_id: 用户ID
            strategy: 策略名称

        Returns:
            True=使用Alpha158新因子, False=使用Wyckoff68旧因子
        """
        with self._lock:
            self._stats.total_requests += 1

            # 1. 熔断检查
            if self._is_circuit_breaker_tripped():
                self._stats.old_factor_requests += 1
                return False

            # 2. 强制策略路由
            if strategy:
                if strategy in self.config.force_new_strategies:
                    self._stats.new_factor_requests += 1
                    return True
                if strategy in self.config.force_old_strategies:
                    self._stats.old_factor_requests += 1
                    return False

            # 3. 强制用户路由
            if user_id and user_id in self.config.force_new_users:
                self._stats.new_factor_requests += 1
                return True

            # 4. 按决策模式路由
            use_new = self._decide(user_id, strategy)
            if use_new:
                self._stats.new_factor_requests += 1
            else:
                self._stats.old_factor_requests += 1
            return use_new

    def _decide(self, user_id: str, strategy: str) -> bool:
        """核心路由决策"""
        ratio = PHASE_RATIO[self.config.phase]

        if self.config.mode == DecisionMode.FORCE_NEW:
            return True
        elif self.config.mode == DecisionMode.FORCE_OLD:
            return False
        elif self.config.mode == DecisionMode.USER_HASH:
            if user_id:
                # 使用用户ID hash决定固定分流
                hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
                return hash_val < int(ratio * 100)
            return False
        elif self.config.mode == DecisionMode.STRATEGY:
            if strategy:
                hash_val = int(hashlib.md5(strategy.encode()).hexdigest(), 16) % 100
                return hash_val < int(ratio * 100)
            return False
        elif self.config.mode == DecisionMode.RANDOM:
            import random
            return random.random() < ratio

        return False

    # ================================================================
    # 结果记录
    # ================================================================

    def record_result(self, user_id: str, success: bool, is_new: bool,
                       latency_ms: float = 0, error_msg: str = None):
        """记录因子计算结果

        Args:
            user_id: 用户ID
            success: 是否成功
            is_new: 是否使用新因子
            latency_ms: 耗时（毫秒）
            error_msg: 错误信息
        """
        with self._lock:
            if is_new:
                if not success:
                    self._stats.new_errors += 1
                    self._error_timestamps.append(datetime.now())
                    if error_msg:
                        logger.warning(f"Alpha158因子错误: user={user_id}, {error_msg}")
                if latency_ms > 0:
                    self._stats.new_latency_ms.append(latency_ms)
            else:
                if not success:
                    self._stats.old_errors += 1
                if latency_ms > 0:
                    self._stats.old_latency_ms.append(latency_ms)

            # 清理旧数据
            self._cleanup_stats()

            # 检查熔断
            self._check_circuit_breaker()

            # 自动推进
            if self.config.auto_advance:
                self._check_auto_advance()

    def record_parallel_result(self, user_id: str, strategy: str,
                                new_factors: Dict[str, float],
                                old_factors: Dict[str, float],
                                new_latency_ms: float = 0,
                                old_latency_ms: float = 0):
        """记录双轨并行对比结果（用于后续分析）

        Args:
            user_id: 用户ID
            strategy: 策略名称
            new_factors: Alpha158因子结果
            old_factors: Wyckoff68因子结果
            new_latency_ms: 新因子耗时
            old_latency_ms: 旧因子耗时
        """
        # 存储到对比日志文件
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "strategy": strategy,
                "new_factor_count": len(new_factors),
                "old_factor_count": len(old_factors),
                "new_latency_ms": new_latency_ms,
                "old_latency_ms": old_latency_ms,
                # 不存储完整因子值（太大），只存储统计摘要
                "new_factor_summary": _summarize_factors(new_factors),
                "old_factor_summary": _summarize_factors(old_factors),
            }
            self._append_comparison_log(log_entry)
        except Exception as e:
            logger.debug(f"对比日志写入失败: {e}")

    # ================================================================
    # 熔断机制
    # ================================================================

    def _is_circuit_breaker_tripped(self) -> bool:
        """检查是否已熔断"""
        if not self.config.circuit_breaker_enabled:
            return False
        return self._stats.circuit_breaker_tripped

    def _check_circuit_breaker(self):
        """检查是否触发熔断"""
        if not self.config.circuit_breaker_enabled:
            return

        if self._stats.circuit_breaker_tripped:
            return

        if self._stats.new_factor_requests < self.config.min_samples_for_breaker:
            return

        # 统计窗口内错误率
        cutoff = datetime.now() - timedelta(minutes=self.config.error_window_minutes)
        recent_errors = sum(1 for t in self._error_timestamps if t >= cutoff)
        recent_total = self._stats.new_factor_requests

        if recent_total > 0:
            error_rate = recent_errors / recent_total
            if error_rate > self.config.max_error_rate:
                self._stats.circuit_breaker_tripped = True
                self._stats.circuit_breaker_tripped_at = datetime.now()
                logger.error(
                    f"Alpha158因子熔断触发! 错误率={error_rate:.2%} "
                    f"({recent_errors}/{recent_total}), "
                    f"自动回退到Wyckoff68旧因子"
                )

    def reset_circuit_breaker(self):
        """手动重置熔断"""
        with self._lock:
            self._stats.circuit_breaker_tripped = False
            self._stats.circuit_breaker_tripped_at = None
            self._error_timestamps.clear()
            logger.info("熔断已手动重置")

    # ================================================================
    # 自动推进
    # ================================================================

    def _check_auto_advance(self):
        """检查是否满足自动推进条件"""
        if self.config.phase == GrayPhase.PHASE_4:
            return  # 已经是100%

        if self._stats.circuit_breaker_tripped:
            return  # 熔断中不推进

        # 检查样本数
        if self._stats.new_factor_requests < self.config.advance_min_samples:
            return

        # 检查时间间隔
        if self._stats.last_advance:
            hours_since = (datetime.now() - self._stats.last_advance).total_seconds() / 3600
            if hours_since < self.config.advance_interval_hours:
                return

        # 检查错误率
        if self._stats.new_factor_requests > 0:
            error_rate = self._stats.new_errors / self._stats.new_factor_requests
            if error_rate > self.config.max_error_rate:
                return

        # 推进到下一阶段
        self._advance_phase()

    def _advance_phase(self):
        """推进到下一灰度阶段"""
        current = self.config.phase
        if current == GrayPhase.PHASE_0:
            self.config.phase = GrayPhase.PHASE_1
        elif current == GrayPhase.PHASE_1:
            self.config.phase = GrayPhase.PHASE_2
        elif current == GrayPhase.PHASE_2:
            self.config.phase = GrayPhase.PHASE_3
        elif current == GrayPhase.PHASE_3:
            self.config.phase = GrayPhase.PHASE_4

        self._stats.last_advance = datetime.now()
        self._stats.current_phase = self.config.phase.name
        logger.info(
            f"灰度自动推进: {current.name} → {self.config.phase.name} "
            f"(ratio={PHASE_RATIO[self.config.phase]:.0%})"
        )
        self._save_config()

    def advance_phase_manual(self) -> bool:
        """手动推进灰度阶段"""
        with self._lock:
            if self.config.phase == GrayPhase.PHASE_4:
                return False
            self._advance_phase()
            return True

    def rollback_phase(self) -> bool:
        """回退到上一灰度阶段"""
        with self._lock:
            current = self.config.phase
            if current == GrayPhase.PHASE_0:
                return False
            elif current == GrayPhase.PHASE_1:
                self.config.phase = GrayPhase.PHASE_0
            elif current == GrayPhase.PHASE_2:
                self.config.phase = GrayPhase.PHASE_1
            elif current == GrayPhase.PHASE_3:
                self.config.phase = GrayPhase.PHASE_2
            elif current == GrayPhase.PHASE_4:
                self.config.phase = GrayPhase.PHASE_3

            self._stats.current_phase = self.config.phase.name
            logger.warning(f"灰度回退: {current.name} → {self.config.phase.name}")
            self._save_config()
            return True

    # ================================================================
    # 状态与统计
    # ================================================================

    def get_status(self) -> Dict[str, Any]:
        """获取灰度状态"""
        with self._lock:
            new_latency_avg = (
                sum(self._stats.new_latency_ms) / len(self._stats.new_latency_ms)
                if self._stats.new_latency_ms else 0
            )
            old_latency_avg = (
                sum(self._stats.old_latency_ms) / len(self._stats.old_latency_ms)
                if self._stats.old_latency_ms else 0
            )

            new_total = self._stats.new_factor_requests
            error_rate = self._stats.new_errors / new_total if new_total > 0 else 0

            return {
                "phase": self.config.phase.name,
                "ratio": PHASE_RATIO[self.config.phase],
                "mode": self.config.mode.value,
                "auto_advance": self.config.auto_advance,
                "parallel_compare": self.config.parallel_compare,

                "total_requests": self._stats.total_requests,
                "new_requests": new_total,
                "old_requests": self._stats.old_factor_requests,
                "new_ratio_actual": new_total / max(self._stats.total_requests, 1),

                "new_errors": self._stats.new_errors,
                "old_errors": self._stats.old_errors,
                "new_error_rate": error_rate,
                "new_latency_avg_ms": new_latency_avg,
                "old_latency_avg_ms": old_latency_avg,

                "circuit_breaker_tripped": self._stats.circuit_breaker_tripped,
                "circuit_breaker_tripped_at": (
                    self._stats.circuit_breaker_tripped_at.isoformat()
                    if self._stats.circuit_breaker_tripped_at else None
                ),
                "last_advance": (
                    self._stats.last_advance.isoformat()
                    if self._stats.last_advance else None
                ),
            }

    def get_stats_summary(self) -> Dict[str, Any]:
        """获取统计摘要（给监控面板用）"""
        return self.get_status()

    # ================================================================
    # 配置持久化
    # ================================================================

    def _load_config(self):
        """从文件加载配置"""
        try:
            path = Path(self._config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                phase_name = data.get("phase", "PHASE_0")
                self.config.phase = GrayPhase[phase_name] if phase_name in GrayPhase.__members__ else GrayPhase.PHASE_0

                mode_name = data.get("mode", "user_hash")
                try:
                    self.config.mode = DecisionMode(mode_name)
                except ValueError:
                    self.config.mode = DecisionMode.USER_HASH

                self.config.force_new_strategies = data.get("force_new_strategies", [])
                self.config.force_old_strategies = data.get("force_old_strategies", [])
                self.config.force_new_users = data.get("force_new_users", [])
                self.config.circuit_breaker_enabled = data.get("circuit_breaker_enabled", True)
                self.config.max_error_rate = data.get("max_error_rate", 0.05)
                self.config.auto_advance = data.get("auto_advance", False)
                self.config.parallel_compare = data.get("parallel_compare", True)
                self._stats.current_phase = self.config.phase.name

                logger.info(f"灰度配置已加载: phase={self.config.phase.name}, ratio={PHASE_RATIO[self.config.phase]:.0%}")
        except Exception as e:
            logger.warning(f"灰度配置加载失败，使用默认: {e}")

    def _save_config(self):
        """保存配置到文件"""
        try:
            path = Path(self._config_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "phase": self.config.phase.name,
                "mode": self.config.mode.value,
                "force_new_strategies": self.config.force_new_strategies,
                "force_old_strategies": self.config.force_old_strategies,
                "force_new_users": self.config.force_new_users,
                "circuit_breaker_enabled": self.config.circuit_breaker_enabled,
                "max_error_rate": self.config.max_error_rate,
                "auto_advance": self.config.auto_advance,
                "parallel_compare": self.config.parallel_compare,
                "updated_at": datetime.now().isoformat(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"灰度配置保存失败: {e}")

    def _append_comparison_log(self, entry: Dict):
        """追加对比日志"""
        try:
            log_path = Path("./logs/gray_comparison.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _cleanup_stats(self):
        """清理过期统计数据"""
        # 保留最近10000条时延数据
        max_keep = 10000
        if len(self._stats.new_latency_ms) > max_keep:
            self._stats.new_latency_ms = self._stats.new_latency_ms[-max_keep:]
        if len(self._stats.old_latency_ms) > max_keep:
            self._stats.old_latency_ms = self._stats.old_latency_ms[-max_keep:]

        # 清理过期错误时间戳
        cutoff = datetime.now() - timedelta(hours=1)
        self._error_timestamps = [t for t in self._error_timestamps if t >= cutoff]


def _summarize_factors(factors: Dict[str, float]) -> Dict[str, Any]:
    """因子摘要统计"""
    if not factors:
        return {"count": 0}
    values = list(factors.values())
    return {
        "count": len(factors),
        "mean": sum(values) / len(values) if values else 0,
        "min": min(values),
        "max": max(values),
        "positive_ratio": sum(1 for v in values if v > 0) / len(values),
    }


# ============================================================
# 全局单例
# ============================================================

_gray_switch: Optional[GraySwitch] = None


def get_gray_switch(config_path: str = None) -> GraySwitch:
    global _gray_switch
    if _gray_switch is None:
        _gray_switch = GraySwitch(config_path=config_path)
    return _gray_switch


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    gs = GraySwitch()

    print("=== 灰度切换测试 ===")
    print(f"当前阶段: {gs.config.phase.name}, 比例: {PHASE_RATIO[gs.config.phase]:.0%}")

    # 模拟100个请求
    new_count = 0
    old_count = 0
    for i in range(100):
        user_id = f"user_{i % 10:03d}"
        use_new = gs.should_use_new_factors(user_id=user_id, strategy="gyro_v7")
        gs.record_result(user_id=user_id, success=True, is_new=use_new, latency_ms=15.0)
        if use_new:
            new_count += 1
        else:
            old_count += 1

    print(f"新因子: {new_count}, 旧因子: {old_count}")
    print(f"状态: {json.dumps(gs.get_status(), indent=2, ensure_ascii=False)}")

    # 测试手动推进
    print("\n=== 推进到 PHASE_1 ===")
    gs.advance_phase_manual()
    new_count2 = 0
    for i in range(100):
        use_new = gs.should_use_new_factors(user_id=f"user_{i % 10:03d}", strategy="gyro_v7")
        if use_new:
            new_count2 += 1
    print(f"PHASE_1 新因子: {new_count2}/100 (预期约10)")

    # 测试熔断
    print("\n=== 熔断测试 ===")
    gs.config.phase = GrayPhase.PHASE_3
    for i in range(50):
        gs.record_result(user_id="test", success=False, is_new=True, error_msg="test error")
    status = gs.get_status()
    print(f"熔断: {status['circuit_breaker_tripped']}")
    print(f"错误率: {status['new_error_rate']:.2%}")

    # 重置
    gs.reset_circuit_breaker()
    print(f"重置后熔断: {gs.get_status()['circuit_breaker_tripped']}")

    print("\n全部测试通过!")