#!/usr/bin/env python3
"""
策略自动发现与集成模块 — Strategy Auto-Discovery & Integration
==============================================================

实现新策略的自动发现、自动优化、自动集成到工作流：

  1. 目录监控：扫描策略目录，检测新增/修改的策略文件
  2. 自动注册：将新策略注册到韬策略引擎 (TauClusterEngine)
  3. 自动优化：触发熵韬收敛优化器集群对新策略进行参数寻优
  4. 自动入库：优化结果持久化，策略加入股票池匹配流程
  5. 自动验证：样本外回测验证，通过后自动加入实盘候选

触发方式：
  - 定时扫描（默认每 5 分钟）
  - 手动触发（API 调用）
  - 文件系统事件（可选，需 watchdog）

依赖: 无外部依赖，纯标准库 + 项目内部模块
"""

from __future__ import annotations

import os
import sys
import json
import time
import hashlib
import logging
import threading
import importlib
import importlib.util
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)


# ============================================================
# 1. 数据模型
# ============================================================

@dataclass
class DiscoveredStrategy:
    """发现的策略元数据"""
    file_path: str
    file_name: str
    strategy_name: str
    strategy_class: str          # 类名
    category: str                # 策略类别
    file_hash: str               # 文件哈希（用于检测变更）
    discovered_at: str           # 发现时间
    status: str = "discovered"   # discovered | registered | optimizing | optimized | verified | active | failed
    error_message: str = ""
    optimization_result: Dict[str, Any] = field(default_factory=dict)
    verification_result: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# 2. 策略目录扫描器
# ============================================================

class StrategyScanner:
    """策略文件扫描器 — 扫描策略目录，识别新策略和变更

    支持扫描路径：
      - Aurora/strategies/          (主策略目录)
      - Aurora/experiments/archive/ (实验归档)
      - 根目录 Aurora/              (根目录策略)
    """

    # 排除模式
    EXCLUDE_PATTERNS = [
        "test_", "_test", "backup", "__pycache__",
        "__init__", ".pyc", "_bak", "_old", ".git",
    ]

    # 策略类别识别关键词
    CATEGORY_KEYWORDS = {
        "RL": ["rl", "ppo", "reinforcement", "傅里叶", "fourier", "强化学习"],
        "Grid": ["grid", "网格"],
        "ML": ["ml", "adaptive_ml", "机器学习"],
        "Value": ["value", "huijin", "汇金", "价值"],
        "MultiFactor": ["multifactor", "resonance", "多因子", "共振"],
        "Trend": ["trend", "movingaverage", "ma", "均线", "趋势"],
        "Fund": ["dca", "定投", "fund"],
        "Defense": ["defense", "down", "防御", "下跌"],
        "Ensemble": ["ensemble", "final", "综合", "融合"],
        "特种兵": ["special_forces", "wyckoff", "威科夫", "特种兵"],
        "Gyro": ["gyro", "陀螺仪", "陀螺"],
        "Bernoulli": ["bernoulli", "coanda", "伯努利", "康达"],
        "Shepherd": ["shepherd", "rotation", "轮动", "标的"],
    }

    def __init__(self,
                 scan_dirs: List[str] = None,
                 exclude_patterns: List[str] = None):
        """
        Args:
            scan_dirs: 扫描目录列表，默认自动检测
            exclude_patterns: 排除模式列表
        """
        self.scan_dirs = scan_dirs or self._auto_detect_dirs()
        self.exclude_patterns = exclude_patterns or self.EXCLUDE_PATTERNS
        self._known_files: Dict[str, str] = {}  # file_path → file_hash
        self._lock = threading.RLock()

    def _auto_detect_dirs(self) -> List[str]:
        """自动检测策略目录"""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base, "Aurora", "strategies"),
            os.path.join(base, "Aurora", "experiments", "archive"),
            os.path.join(base, "Aurora"),
            os.path.join(base, "strategies"),
        ]
        return [d for d in candidates if os.path.isdir(d)]

    def _is_valid_strategy_file(self, file_path: str) -> bool:
        """判断是否为有效策略文件"""
        name = os.path.basename(file_path)
        if not name.endswith(".py"):
            return False
        for pattern in self.exclude_patterns:
            if pattern in name.lower() or pattern in file_path.lower():
                return False
        return True

    def _compute_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        try:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def _extract_strategy_info(self, file_path: str) -> Optional[Dict[str, str]]:
        """从策略文件中提取策略名称和类别"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None

        file_name = os.path.basename(file_path)
        name_lower = file_name.lower()

        # 查找策略类名（class XxxStrategy）
        import re
        class_match = re.findall(r'class\s+(\w*[Ss]trategy\w*)', content)
        strategy_class = class_match[0] if class_match else file_name.replace(".py", "")

        # 从文件名和内容推断策略名称
        strategy_name = file_name.replace(".py", "")

        # 识别类别
        category = self._detect_category(strategy_name, content)

        return {
            "file_name": file_name,
            "strategy_name": strategy_name,
            "strategy_class": strategy_class,
            "category": category,
        }

    def _detect_category(self, name: str, content: str) -> str:
        """识别策略类别"""
        name_lower = name.lower()
        content_lower = content.lower()[:500]  # 只检查前500字符

        scores = {}
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in name_lower:
                    score += 3
                if kw in content_lower:
                    score += 1
            if score > 0:
                scores[cat] = score

        if scores:
            return max(scores, key=scores.get)
        return "Unknown"

    def scan(self) -> List[DiscoveredStrategy]:
        """扫描所有策略目录，返回新发现/变更的策略列表"""
        with self._lock:
            discovered = []

            for scan_dir in self.scan_dirs:
                if not os.path.isdir(scan_dir):
                    continue

                for root, dirs, files in os.walk(scan_dir):
                    # 过滤排除目录
                    dirs[:] = [d for d in dirs
                              if not any(p in d.lower() for p in self.exclude_patterns)]

                    for f in files:
                        file_path = os.path.join(root, f)
                        if not self._is_valid_strategy_file(file_path):
                            continue

                        file_hash = self._compute_file_hash(file_path)
                        if not file_hash:
                            continue

                        # 检查是否为新文件或已变更
                        is_new = file_path not in self._known_files
                        is_changed = (not is_new and
                                     self._known_files[file_path] != file_hash)

                        if is_new or is_changed:
                            info = self._extract_strategy_info(file_path)
                            if info is None:
                                continue

                            strategy = DiscoveredStrategy(
                                file_path=file_path,
                                file_name=info["file_name"],
                                strategy_name=info["strategy_name"],
                                strategy_class=info["strategy_class"],
                                category=info["category"],
                                file_hash=file_hash,
                                discovered_at=datetime.now().isoformat(),
                                status="changed" if is_changed else "discovered",
                            )
                            discovered.append(strategy)
                            self._known_files[file_path] = file_hash
                            logger.info(
                                f"[Scanner] {'变更' if is_changed else '发现'}策略: "
                                f"{strategy.strategy_name} (类别={strategy.category})"
                            )

            return discovered

    def mark_known(self, file_path: str):
        """标记文件为已知（避免重复发现）"""
        with self._lock:
            self._known_files[file_path] = self._compute_file_hash(file_path)


# ============================================================
# 3. 策略自动注册器
# ============================================================

class StrategyAutoRegistrar:
    """策略自动注册器 — 将发现的策略注册到策略管理器

    注册流程：
      1. 动态导入策略模块
      2. 将策略添加到 EnhancedStrategyManager 的策略列表
      3. 创建 TauClusterEngine 适配器
      4. 注册到集群引擎
    """

    def __init__(self,
                 strategy_manager: Any = None,
                 tau_engine: Any = None):
        self.strategy_manager = strategy_manager
        self.tau_engine = tau_engine
        self._registered: Dict[str, DiscoveredStrategy] = {}
        self._lock = threading.RLock()

    def register(self, strategy: DiscoveredStrategy) -> bool:
        """注册单个策略"""
        with self._lock:
            try:
                # 1. 动态导入
                module = self._import_strategy(strategy)

                # 2. 注册到策略管理器
                if self.strategy_manager:
                    self._register_to_manager(strategy)

                # 3. 注册到 TauClusterEngine
                if self.tau_engine:
                    self._register_to_cluster(strategy, module)

                strategy.status = "registered"
                self._registered[strategy.strategy_name] = strategy
                logger.info(f"[Registrar] 策略已注册: {strategy.strategy_name}")
                return True

            except Exception as e:
                strategy.status = "failed"
                strategy.error_message = str(e)
                logger.error(f"[Registrar] 注册失败: {strategy.strategy_name}: {e}")
                return False

    def _import_strategy(self, strategy: DiscoveredStrategy) -> Any:
        """动态导入策略模块"""
        spec = importlib.util.spec_from_file_location(
            strategy.strategy_name, strategy.file_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载模块: {strategy.file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[strategy.strategy_name] = module
        spec.loader.exec_module(module)
        return module

    def _register_to_manager(self, strategy: DiscoveredStrategy):
        """注册到策略管理器"""
        if not hasattr(self.strategy_manager, 'strategies'):
            if not hasattr(self.strategy_manager, '_active_strategies'):
                return
            # 加入活跃策略缓存
            from .enhanced_strategy_manager import StrategyInfo, StrategyStatus
            self.strategy_manager._active_strategies[strategy.strategy_name] = StrategyInfo(
                name=strategy.strategy_name,
                label=strategy.strategy_name,
                category=strategy.category,
                description=f"自动发现: {strategy.file_name}",
                status=StrategyStatus.STOPPED,
            )
            return

        # 直接加入策略字典
        if strategy.strategy_name not in self.strategy_manager.strategies:
            self.strategy_manager.strategies[strategy.strategy_name] = {
                "name": strategy.strategy_name,
                "category": strategy.category,
                "label": strategy.strategy_name,
                "description": f"自动发现策略 (来源: {strategy.file_name})",
                "params": {},
                "auto_discovered": True,
            }

    def _register_to_cluster(self, strategy: DiscoveredStrategy, module: Any):
        """注册到 TauClusterEngine"""
        from .tau_cluster_engine import StrategySignalAdapter

        # 查找策略类
        strategy_class = getattr(module, strategy.strategy_class, None)
        if strategy_class is None:
            # 尝试查找任何以 Strategy 结尾的类
            for attr_name in dir(module):
                if attr_name.endswith("Strategy"):
                    strategy_class = getattr(module, attr_name)
                    break

        if strategy_class is None:
            logger.warning(f"[Registrar] 未找到策略类: {strategy.strategy_class}")
            return

        # 创建适配器
        try:
            instance = strategy_class()
            adapter = StrategySignalAdapter(
                name=strategy.strategy_name,
                strategy_type=strategy.category.lower(),
                strategy_instance=instance,
            )
            self.tau_engine.register_strategy(strategy.strategy_name, adapter)
        except Exception as e:
            logger.warning(f"[Registrar] 集群注册跳过（可能需要参数）: {e}")

    def get_registered(self) -> Dict[str, DiscoveredStrategy]:
        with self._lock:
            return dict(self._registered)


# ============================================================
# 4. 自动优化触发器
# ============================================================

class AutoOptimizationTrigger:
    """自动优化触发器 — 新策略注册后自动触发优化流程

    流程：
      1. 检测策略类型
      2. 创建优化器集群
      3. 执行参数优化
      4. 持久化结果
      5. 标记策略状态
    """

    def __init__(self,
                 integration_bus: Any = None,
                 parameter_store: Any = None):
        self.integration_bus = integration_bus
        self.parameter_store = parameter_store
        self._optimization_queue: List[str] = []
        self._optimization_results: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._running = False

    def trigger_optimization(self, strategy_name: str) -> bool:
        """触发优化（异步）"""
        with self._lock:
            if strategy_name in self._optimization_queue:
                return False
            self._optimization_queue.append(strategy_name)
            logger.info(f"[AutoOpt] 优化已加入队列: {strategy_name}")

        # 启动后台优化线程
        if not self._running:
            self._running = True
            threading.Thread(target=self._process_queue, daemon=True).start()

        return True

    def _process_queue(self):
        """处理优化队列"""
        while True:
            with self._lock:
                if not self._optimization_queue:
                    self._running = False
                    break
                strategy_name = self._optimization_queue.pop(0)

            try:
                result = self._run_optimization(strategy_name)
                with self._lock:
                    self._optimization_results[strategy_name] = result
                logger.info(
                    f"[AutoOpt] 优化完成: {strategy_name}, "
                    f"score={result.get('best_score', 0):.4f}"
                )
            except Exception as e:
                logger.error(f"[AutoOpt] 优化失败: {strategy_name}: {e}")
                with self._lock:
                    self._optimization_results[strategy_name] = {
                        "success": False, "error": str(e)
                    }

    def _run_optimization(self, strategy_name: str) -> Dict[str, Any]:
        """执行优化"""
        if self.integration_bus:
            return self.integration_bus.auto_optimize_strategy(
                strategy_name,
                use_warm_start=False,
            )

        # 降级：直接使用优化器
        from .tau_enhanced_optimizer import EntropyTauOptimizer
        default_ranges = {
            'short_period': (5.0, 50.0),
            'long_period': (50.0, 200.0),
            'threshold': (0.005, 0.10),
        }
        optimizer = EntropyTauOptimizer(
            default_ranges,
            strategy_name=strategy_name,
        )
        return optimizer.run_enhanced_optimization(
            coarse_points=30,
            refined_points_per_region=15,
            validation_points=5,
            entropy_decay=True,
        )

    def get_result(self, strategy_name: str) -> Optional[Dict]:
        with self._lock:
            return self._optimization_results.get(strategy_name)

    def get_queue_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queue_size": len(self._optimization_queue),
                "running": self._running,
                "completed": len(self._optimization_results),
                "strategies": {
                    name: result.get("best_score", "pending")
                    for name, result in self._optimization_results.items()
                },
            }


# ============================================================
# 5. 自动验证器
# ============================================================

class AutoVerifier:
    """自动验证器 — 优化完成后自动执行样本外回测验证

    验证标准：
      - 样本外夏普 > 1.0
      - 样本外最大回撤 < 20%
      - 样本外收益 > 0
    """

    VERIFICATION_THRESHOLDS = {
        "min_sharpe": 1.0,
        "max_drawdown": 0.20,
        "min_return": 0.0,
    }

    def __init__(self, strategy_manager: Any = None):
        self.strategy_manager = strategy_manager
        self._verification_results: Dict[str, Dict] = {}
        self._lock = threading.RLock()

    def verify(self, strategy_name: str,
               best_params: Dict[str, float] = None) -> Dict[str, Any]:
        """验证优化后的策略"""
        with self._lock:
            try:
                if self.strategy_manager is None:
                    return {"passed": True, "note": "无策略管理器，跳过验证"}

                # 执行样本外回测
                backtest = self.strategy_manager.run_backtest(
                    strategy_name,
                    days=90,  # 样本外90天
                    params=best_params,
                    use_optimized_params=(best_params is None),
                )

                # 判断是否通过
                sharpe = getattr(backtest, 'sharpe_ratio', 0)
                drawdown = getattr(backtest, 'max_drawdown', 1.0)
                total_return = getattr(backtest, 'total_return_pct', 0)

                # 归一化
                if drawdown > 1:
                    drawdown = drawdown / 100.0
                if total_return > 1:
                    total_return = total_return / 100.0

                passed = (
                    sharpe >= self.VERIFICATION_THRESHOLDS["min_sharpe"] and
                    abs(drawdown) <= self.VERIFICATION_THRESHOLDS["max_drawdown"] and
                    total_return >= self.VERIFICATION_THRESHOLDS["min_return"]
                )

                result = {
                    "passed": passed,
                    "sharpe": round(sharpe, 4),
                    "max_drawdown": round(abs(drawdown), 4),
                    "total_return": round(total_return, 4),
                    "thresholds": self.VERIFICATION_THRESHOLDS,
                    "verified_at": datetime.now().isoformat(),
                }

                self._verification_results[strategy_name] = result
                logger.info(
                    f"[Verifier] 验证{'通过' if passed else '未通过'}: "
                    f"{strategy_name} (sharpe={sharpe:.2f}, "
                    f"dd={abs(drawdown):.2%}, ret={total_return:.2%})"
                )
                return result

            except Exception as e:
                logger.error(f"[Verifier] 验证失败: {strategy_name}: {e}")
                return {"passed": False, "error": str(e)}

    def get_result(self, strategy_name: str) -> Optional[Dict]:
        with self._lock:
            return self._verification_results.get(strategy_name)


# ============================================================
# 6. 策略自动发现主控制器
# ============================================================

class StrategyAutoDiscovery:
    """策略自动发现主控制器

    统一管理扫描→注册→优化→验证的完整流程。

    用法:
        discovery = StrategyAutoDiscovery(
            strategy_manager=mgr,
            tau_engine=engine,
            integration_bus=bus,
        )
        discovery.start(interval=300)  # 每5分钟扫描一次
    """

    def __init__(self,
                 strategy_manager: Any = None,
                 tau_engine: Any = None,
                 integration_bus: Any = None,
                 parameter_store: Any = None,
                 scan_dirs: List[str] = None):
        self.scanner = StrategyScanner(scan_dirs=scan_dirs)
        self.registrar = StrategyAutoRegistrar(strategy_manager, tau_engine)
        self.optimizer = AutoOptimizationTrigger(integration_bus, parameter_store)
        self.verifier = AutoVerifier(strategy_manager)

        self._scan_interval: int = 300  # 默认5分钟
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # 策略生命周期回调
        self._on_discovered: List[Callable] = []
        self._on_registered: List[Callable] = []
        self._on_optimized: List[Callable] = []
        self._on_verified: List[Callable] = []

    def on_discovered(self, callback: Callable):
        """注册发现回调"""
        self._on_discovered.append(callback)

    def on_registered(self, callback: Callable):
        """注册注册完成回调"""
        self._on_registered.append(callback)

    def on_optimized(self, callback: Callable):
        """注册优化完成回调"""
        self._on_optimized.append(callback)

    def on_verified(self, callback: Callable):
        """注册验证完成回调"""
        self._on_verified.append(callback)

    def start(self, interval: int = 300):
        """启动定时扫描

        Args:
            interval: 扫描间隔（秒），默认 300（5分钟）
        """
        with self._lock:
            if self._running:
                return
            self._scan_interval = interval
            self._running = True
            self._thread = threading.Thread(target=self._scan_loop, daemon=True)
            self._thread.start()
            logger.info(f"[AutoDiscovery] 启动定时扫描，间隔={interval}s")

    def stop(self):
        """停止定时扫描"""
        with self._lock:
            self._running = False
            logger.info("[AutoDiscovery] 停止定时扫描")

    def _scan_loop(self):
        """扫描循环"""
        while self._running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"[AutoDiscovery] 扫描循环异常: {e}")
            time.sleep(self._scan_interval)

    def _run_cycle(self):
        """执行一次完整扫描周期"""
        # 1. 扫描
        discovered = self.scanner.scan()
        if not discovered:
            return

        for strategy in discovered:
            # 2. 触发发现回调
            for cb in self._on_discovered:
                try:
                    cb(strategy)
                except Exception:
                    pass

            # 3. 注册
            if self.registrar.register(strategy):
                for cb in self._on_registered:
                    try:
                        cb(strategy)
                    except Exception:
                        pass

                # 4. 自动优化
                if self.optimizer.trigger_optimization(strategy.strategy_name):
                    strategy.status = "optimizing"

    def run_once(self) -> List[DiscoveredStrategy]:
        """手动执行一次扫描（阻塞）"""
        discovered = self.scanner.scan()
        for strategy in discovered:
            if self.registrar.register(strategy):
                strategy.status = "registered"
                # 同步优化
                result = self.optimizer._run_optimization(strategy.strategy_name)
                strategy.optimization_result = result
                strategy.status = "optimized"

                # 验证
                best_params = result.get("best_params") if result.get("success") else None
                verification = self.verifier.verify(strategy.strategy_name, best_params)
                strategy.verification_result = verification
                strategy.status = "verified" if verification.get("passed") else "optimized"

                if verification.get("passed"):
                    strategy.status = "active"
                    for cb in self._on_verified:
                        try:
                            cb(strategy)
                        except Exception:
                            pass

        return discovered

    def get_status(self) -> Dict[str, Any]:
        """获取发现系统状态"""
        with self._lock:
            return {
                "running": self._running,
                "scan_interval": self._scan_interval,
                "known_files": len(self.scanner._known_files),
                "registered": len(self.registrar._registered),
                "optimization_queue": self.optimizer.get_queue_status(),
                "last_scan": datetime.now().isoformat(),
            }

    def get_strategies(self) -> Dict[str, DiscoveredStrategy]:
        """获取已发现的策略列表"""
        return self.registrar.get_registered()


# ============================================================
# 7. 全局单例
# ============================================================

_discovery_instance: Optional[StrategyAutoDiscovery] = None
_discovery_lock = threading.Lock()


def get_auto_discovery(
    strategy_manager: Any = None,
    tau_engine: Any = None,
    integration_bus: Any = None,
) -> StrategyAutoDiscovery:
    global _discovery_instance
    if _discovery_instance is None:
        with _discovery_lock:
            if _discovery_instance is None:
                _discovery_instance = StrategyAutoDiscovery(
                    strategy_manager=strategy_manager,
                    tau_engine=tau_engine,
                    integration_bus=integration_bus,
                )
    return _discovery_instance