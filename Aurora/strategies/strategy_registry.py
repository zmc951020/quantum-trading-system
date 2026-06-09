#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略注册表 (Strategy Registry)
================================
Aurora 量化交易系统的策略注册、发现与管理模块。

功能：
  1. 自动扫描 strategies/ 目录下的策略模块
  2. 维护策略元数据：名称、类型、状态、评分、文件路径
  3. 提供策略的启用/禁用切换
  4. 与数据库 strategy_registry 表同步
  5. 支持策略性能追踪与排名

使用方式：
  from strategies.strategy_registry import STRATEGY_REGISTRY, get_strategy_registry

  registry = get_strategy_registry()
  strategies = registry.list_enabled()
  strategy = registry.get("fourier_rl_strategy")
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

@dataclass
class StrategyMeta:
    """策略元数据"""
    name: str                              # 策略名称（唯一标识）
    display_name: str = ""                 # 显示名称
    file_path: str = ""                    # 策略文件路径
    module_path: str = ""                  # Python 模块路径
    strategy_type: str = "general"         # 策略类型：trend/grid/ml/rl/fourier/composite/physics
    description: str = ""                  # 策略描述
    version: str = "1.0.0"                # 版本号
    author: str = ""                       # 作者
    enabled: bool = True                   # 是否启用
    status: str = "untested"               # 状态：untested/testing/production/deprecated
    tags: List[str] = field(default_factory=list)

    # 性能指标
    performance_score: float = 0.0         # 综合评分（0-100）
    sharpe_ratio: float = 0.0             # 夏普比率
    annual_return: float = 0.0            # 年化收益率（%）
    max_drawdown: float = 0.0             # 最大回撤（%）
    win_rate: float = 0.0                 # 胜率（%）
    total_trades: int = 0                  # 总交易次数
    avg_profit_per_trade: float = 0.0     # 每笔平均收益

    # 元数据
    created_at: str = ""                   # 创建时间
    updated_at: str = ""                   # 更新时间
    last_backtest: str = ""               # 最后回测时间
    parameters: Dict[str, Any] = field(default_factory=dict)  # 策略参数

    # 运行时
    _class_ref: Any = None                # 策略类引用（内部使用）

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "file_path": self.file_path,
            "module_path": self.module_path,
            "strategy_type": self.strategy_type,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "enabled": self.enabled,
            "status": self.status,
            "tags": self.tags,
            "performance_score": self.performance_score,
            "sharpe_ratio": self.sharpe_ratio,
            "annual_return": self.annual_return,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "avg_profit_per_trade": self.avg_profit_per_trade,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_backtest": self.last_backtest,
            "parameters": self.parameters,
        }


# ==================== 策略注册表 ====================

class StrategyRegistry:
    """
    策略注册表 — Aurora 系统的策略管理中心

    特性：
    - 自动扫描策略目录
    - 懒加载策略模块
    - 数据库双向同步
    - 启用/禁用热切换
    - 性能排名与筛选
    """

    def __init__(
        self,
        strategies_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        auto_scan: bool = True,
    ):
        self._strategies: Dict[str, StrategyMeta] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self._db_path = db_path

        # 策略目录
        if strategies_dir is None:
            strategies_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
            )
        self._strategies_dir = Path(strategies_dir)

        # 自动扫描
        if auto_scan:
            self.scan_strategies()

        logger.info(
            f"[StrategyRegistry] 初始化完成 | "
            f"目录={self._strategies_dir} | "
            f"已发现策略={len(self._strategies)}"
        )

    # ==================== 策略发现 ====================

    def scan_strategies(self, directory: Optional[str] = None) -> int:
        """
        扫描策略目录，自动注册所有策略模块

        Args:
            directory: 策略目录路径，默认使用初始化时的路径

        Returns:
            int: 新发现的策略数量
        """
        scan_dir = Path(directory) if directory else self._strategies_dir
        new_count = 0

        for py_file in scan_dir.glob("*.py"):
            # 跳过私有文件和非策略文件
            if py_file.name.startswith("_") or py_file.name.startswith("test_"):
                continue
            if py_file.name in ("strategy_registry.py", "strategy_base.py",
                               "strategy_combiner.py", "__init__.py"):
                continue
            if "request" in py_file.name.lower() or "submit" in py_file.name.lower():
                continue
            # 跳过报告文件
            if "_report_" in py_file.name or py_file.stem.endswith("_report"):
                continue

            module_name = py_file.stem

            # 已存在则跳过
            if module_name in self._strategies:
                continue

            # 尝试推断策略元数据
            try:
                meta = self._infer_strategy_meta(py_file, module_name)
                self._strategies[module_name] = meta
                new_count += 1
                logger.debug(f"[StrategyRegistry] 发现策略: {module_name} ({meta.strategy_type})")
            except Exception as e:
                logger.warning(f"[StrategyRegistry] 扫描 {module_name} 失败: {e}")

        # 从数据库同步
        if self._db_path:
            try:
                self._sync_from_db()
            except Exception as e:
                logger.debug(f"[StrategyRegistry] 数据库同步跳过: {e}")

        logger.info(f"[StrategyRegistry] 扫描完成，新发现 {new_count} 个策略，"
                    f"总计 {len(self._strategies)} 个")
        return new_count

    def _infer_strategy_meta(self, py_file: Path, module_name: str) -> StrategyMeta:
        """从 Python 文件推断策略元数据"""
        # 读取文件前几行查找 docstring
        docstring = ""
        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring += stripped.lstrip("#").strip().strip('"""').strip("'''").strip() + " "
                    if len(docstring) > 200:
                        break
                elif docstring:
                    break
            docstring = docstring.strip()[:200]
        except Exception:
            docstring = ""

        # 从模块名推断类型 (增强：支持物理建模/rl_optimized策略)
        strategy_type = "general"
        name_lower = module_name.lower()
        if "grid" in name_lower:
            strategy_type = "grid"
        elif any(kw in name_lower for kw in ("ml", "machine", "adaptive_ml")):
            strategy_type = "ml"
        elif "fourier" in name_lower:
            strategy_type = "fourier"
        elif "trend" in name_lower or "downtrend" in name_lower or "down" in name_lower:
            strategy_type = "trend"
        elif any(kw in name_lower for kw in ("huijin", "value", "fundamental")):
            strategy_type = "value"
        elif any(kw in name_lower for kw in ("multi", "resonance", "combine")):
            strategy_type = "composite"
        elif any(kw in name_lower for kw in (
            # 物理建模核心关键词
            "newton", "thermodynamic", "fractal", "fluid", "physics", "entropy",
            "hurts", "momentum_enhanced", "reynolds", "vortex", "laminar",
            # 陀螺仪系列
            "gyro", "gyroscope", "gyro_minute", "gyro_precession",
            # 伯努利-康达
            "bernoulli", "coanda",
        )):
            strategy_type = "physics"
        elif any(kw in name_lower for kw in ("rl", "ppo", "reinforcement", "rl_optimized", "rl_adaptive")):
            strategy_type = "rl"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return StrategyMeta(
            name=module_name,
            display_name=module_name.replace("_", " ").title(),
            file_path=str(py_file),
            module_path=f"strategies.{module_name}",
            strategy_type=strategy_type,
            description=docstring or f"Aurora 策略：{module_name}",
            created_at=now,
            updated_at=now,
            parameters={},
        )

    # ==================== 策略访问 ====================

    def get(self, name: str) -> Optional[StrategyMeta]:
        """获取策略元数据"""
        return self._strategies.get(name)

    def list_all(self) -> List[StrategyMeta]:
        """列出所有策略"""
        return list(self._strategies.values())

    def list_enabled(self) -> List[StrategyMeta]:
        """列出已启用的策略"""
        return [m for m in self._strategies.values() if m.enabled]

    def list_by_type(self, strategy_type: str) -> List[StrategyMeta]:
        """按类型列出策略"""
        return [m for m in self._strategies.values()
                if m.strategy_type == strategy_type]

    def list_by_status(self, status: str) -> List[StrategyMeta]:
        """按状态列出策略"""
        return [m for m in self._strategies.values()
                if m.status == status]

    def get_top_performers(self, n: int = 10) -> List[StrategyMeta]:
        """获取评分最高的 N 个策略"""
        sorted_strategies = sorted(
            self._strategies.values(),
            key=lambda m: m.performance_score,
            reverse=True,
        )
        return sorted_strategies[:n]

    def get_names(self) -> List[str]:
        """获取所有策略名称"""
        return list(self._strategies.keys())

    def count(self) -> int:
        """策略总数"""
        return len(self._strategies)

    def count_enabled(self) -> int:
        """已启用策略数"""
        return sum(1 for m in self._strategies.values() if m.enabled)

    # ==================== 策略管理 ====================

    def enable(self, name: str) -> bool:
        """启用策略"""
        meta = self._strategies.get(name)
        if meta:
            meta.enabled = True
            meta.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[StrategyRegistry] 启用策略: {name}")
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用策略"""
        meta = self._strategies.get(name)
        if meta:
            meta.enabled = False
            meta.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[StrategyRegistry] 禁用策略: {name}")
            return True
        return False

    def toggle(self, name: str) -> Optional[bool]:
        """切换策略启用状态，返回新状态"""
        meta = self._strategies.get(name)
        if meta:
            meta.enabled = not meta.enabled
            meta.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[StrategyRegistry] 切换策略 {name} → enabled={meta.enabled}")
            return meta.enabled
        return None

    def update_performance(
        self,
        name: str,
        performance_score: float = 0.0,
        sharpe_ratio: float = 0.0,
        annual_return: float = 0.0,
        max_drawdown: float = 0.0,
        win_rate: float = 0.0,
        total_trades: int = 0,
        **kwargs,
    ) -> bool:
        """更新策略性能指标"""
        meta = self._strategies.get(name)
        if not meta:
            return False

        meta.performance_score = performance_score
        meta.sharpe_ratio = sharpe_ratio
        meta.annual_return = annual_return
        meta.max_drawdown = max_drawdown
        meta.win_rate = win_rate
        meta.total_trades = total_trades
        meta.last_backtest = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 自动更新状态
        if meta.status == "untested" and total_trades > 0:
            meta.status = "testing"
        if performance_score >= 70:
            meta.status = "production"

        logger.info(
            f"[StrategyRegistry] 更新 {name} 性能: "
            f"score={performance_score:.2f}, sharpe={sharpe_ratio:.2f}, "
            f"return={annual_return:.2f}%"
        )
        return True

    def set_status(self, name: str, status: str) -> bool:
        """设置策略状态"""
        valid_statuses = {"untested", "testing", "production", "deprecated", "archived"}
        if status not in valid_statuses:
            logger.error(f"[StrategyRegistry] 无效状态: {status}")
            return False
        meta = self._strategies.get(name)
        if meta:
            meta.status = status
            meta.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True
        return False

    def register(self, meta: StrategyMeta) -> None:
        """手动注册策略"""
        self._strategies[meta.name] = meta
        logger.info(f"[StrategyRegistry] 手动注册: {meta.name}")

    def unregister(self, name: str) -> bool:
        """注销策略"""
        if name in self._strategies:
            del self._strategies[name]
            self._loaded_modules.pop(name, None)
            logger.info(f"[StrategyRegistry] 注销策略: {name}")
            return True
        return False

    # ==================== 模块加载 ====================

    def load_strategy_module(self, name: str) -> Optional[Any]:
        """加载策略模块（懒加载）"""
        meta = self._strategies.get(name)
        if not meta:
            logger.warning(f"[StrategyRegistry] 未找到策略: {name}")
            return None

        if name in self._loaded_modules:
            return self._loaded_modules[name]

        try:
            module = importlib.import_module(meta.module_path)
            self._loaded_modules[name] = module
            logger.debug(f"[StrategyRegistry] 加载模块: {meta.module_path}")
            return module
        except Exception as e:
            logger.error(f"[StrategyRegistry] 加载 {name} 失败: {e}")
            return None

    def get_strategy_class(self, name: str) -> Optional[Type]:
        """获取策略类"""
        module = self.load_strategy_module(name)
        if not module:
            return None

        # 查找策略类（排除导入的类）
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (inspect.isclass(attr)
                    and attr.__module__ == module.__name__
                    and attr_name not in ("ABC", "StrategyBase")):
                # 检查是否有常见的策略方法
                if any(hasattr(attr, m) for m in
                      ("generate_signals", "run", "execute", "predict", "on_bar")):
                    return attr
        return None

    # ==================== 数据库同步 ====================

    def sync_to_db(self, db_path: Optional[str] = None) -> int:
        """同步策略注册表到数据库"""
        path = db_path or self._db_path
        if not path:
            logger.warning("[StrategyRegistry] 未提供数据库路径")
            return 0

        try:
            import sqlite3
            conn = sqlite3.connect(path)
            cursor = conn.cursor()

            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT UNIQUE,
                    file_path TEXT,
                    strategy_type TEXT,
                    enabled INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'untested',
                    performance_score REAL DEFAULT 0,
                    sharpe_ratio REAL DEFAULT 0,
                    annual_return REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    last_backtest TEXT,
                    description TEXT,
                    parameters TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            count = 0
            for meta in self._strategies.values():
                cursor.execute("""
                    INSERT OR REPLACE INTO strategy_registry
                    (strategy_name, file_path, strategy_type, enabled, status,
                     performance_score, sharpe_ratio, annual_return, max_drawdown,
                     win_rate, total_trades, last_backtest, description, parameters,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta.name, meta.file_path, meta.strategy_type,
                    1 if meta.enabled else 0, meta.status,
                    meta.performance_score, meta.sharpe_ratio,
                    meta.annual_return, meta.max_drawdown,
                    meta.win_rate, meta.total_trades,
                    meta.last_backtest or "",
                    meta.description,
                    str(meta.parameters),
                    meta.created_at, meta.updated_at,
                ))
                count += 1

            conn.commit()
            conn.close()
            logger.info(f"[StrategyRegistry] 同步 {count} 条策略到数据库")
            return count
        except Exception as e:
            logger.error(f"[StrategyRegistry] 数据库同步失败: {e}")
            return 0

    def _sync_from_db(self) -> None:
        """从数据库同步策略数据"""
        if not self._db_path:
            return
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_registry'")
            if not cursor.fetchone():
                conn.close()
                return

            cursor.execute("SELECT * FROM strategy_registry")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            for row in rows:
                data = dict(zip(columns, row))
                name = data.get("strategy_name", "")
                if name and name in self._strategies:
                    meta = self._strategies[name]
                    meta.performance_score = data.get("performance_score", 0.0) or 0.0
                    meta.sharpe_ratio = data.get("sharpe_ratio", 0.0) or 0.0
                    meta.annual_return = data.get("annual_return", 0.0) or 0.0
                    meta.max_drawdown = data.get("max_drawdown", 0.0) or 0.0
                    meta.win_rate = data.get("win_rate", 0.0) or 0.0
                    meta.total_trades = data.get("total_trades", 0) or 0
                    meta.status = data.get("status", "untested") or "untested"
                    meta.enabled = bool(data.get("enabled", 1))
                    meta.last_backtest = data.get("last_backtest", "") or ""

            conn.close()
        except Exception as e:
            logger.debug(f"[StrategyRegistry] 从数据库同步失败（可忽略）: {e}")

    # ==================== 导出 ====================

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """导出所有策略为字典列表"""
        return [meta.to_dict() for meta in self._strategies.values()]

    def to_summary(self) -> Dict[str, Any]:
        """导出策略汇总"""
        type_count: Dict[str, int] = {}
        for meta in self._strategies.values():
            t = meta.strategy_type
            type_count[t] = type_count.get(t, 0) + 1

        return {
            "total_strategies": len(self._strategies),
            "enabled_strategies": self.count_enabled(),
            "by_type": type_count,
            "by_status": {
                s: len(self.list_by_status(s))
                for s in ["untested", "testing", "production", "deprecated"]
            },
            "top_performers": [
                {"name": m.name, "score": m.performance_score}
                for m in self.get_top_performers(5)
            ],
        }


# ==================== 全局实例 ====================

# 默认策略目录
DEFAULT_STRATEGIES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
)

# 默认数据库路径
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aurora_backtest.db",
)

# 全局策略注册表单例
STRATEGY_REGISTRY = StrategyRegistry(
    strategies_dir=DEFAULT_STRATEGIES_DIR,
    db_path=DEFAULT_DB_PATH,
    auto_scan=True,
)

_registry_instance: Optional[StrategyRegistry] = None


def get_strategy_registry(
    strategies_dir: Optional[str] = None,
    db_path: Optional[str] = None,
) -> StrategyRegistry:
    """
    获取策略注册表单例

    使用方式：
        from strategies.strategy_registry import get_strategy_registry
        registry = get_strategy_registry()
        enabled = registry.list_enabled()
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = StrategyRegistry(
            strategies_dir=strategies_dir or DEFAULT_STRATEGIES_DIR,
            db_path=db_path or DEFAULT_DB_PATH,
            auto_scan=True,
        )
    return _registry_instance


# ==================== 便捷函数 ====================

def get_enabled_strategies() -> List[StrategyMeta]:
    """快捷方法：获取所有已启用策略"""
    return STRATEGY_REGISTRY.list_enabled()


def get_strategy_names() -> List[str]:
    """快捷方法：获取所有策略名称"""
    return STRATEGY_REGISTRY.get_names()


def get_strategy_list_api() -> List[Dict[str, Any]]:
    """
    API接口：获取策略列表（用于Web前端）
    
    Returns:
        List[Dict]: 策略信息字典列表
    """
    return STRATEGY_REGISTRY.to_dict_list()


def create_strategy(name: str, **kwargs) -> bool:
    """
    创建新策略（预留接口）
    
    Args:
        name: 策略名称
        kwargs: 策略参数
    
    Returns:
        bool: 是否创建成功
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta = StrategyMeta(
            name=name,
            display_name=kwargs.get('display_name', name.replace("_", " ").title()),
            description=kwargs.get('description', ""),
            strategy_type=kwargs.get('strategy_type', 'general'),
            version=kwargs.get('version', '1.0.0'),
            author=kwargs.get('author', ''),
            created_at=now,
            updated_at=now,
            parameters=kwargs.get('parameters', {}),
        )
        STRATEGY_REGISTRY.register(meta)
        return True
    except Exception as e:
        logger.error(f"[StrategyRegistry] 创建策略失败: {e}")
        return False


def get_strategy_info(name: str) -> Optional[Dict[str, Any]]:
    """
    获取策略详细信息
    
    Args:
        name: 策略名称
    
    Returns:
        Dict: 策略信息字典
    """
    meta = STRATEGY_REGISTRY.get(name)
    if meta:
        return meta.to_dict()
    return None


def get_strategies_by_category(category: str) -> List[Dict[str, Any]]:
    """
    按类别获取策略
    
    Args:
        category: 策略类别
    
    Returns:
        List[Dict]: 策略信息字典列表
    """
    return [m.to_dict() for m in STRATEGY_REGISTRY.list_by_type(category)]


def get_strategies_by_regime(regime: str) -> List[Dict[str, Any]]:
    """
    按市场状态获取策略（预留接口）
    
    Args:
        regime: 市场状态
    
    Returns:
        List[Dict]: 策略信息字典列表
    """
    return STRATEGY_REGISTRY.to_dict_list()


def get_recommended_strategies() -> List[Dict[str, Any]]:
    """
    获取推荐策略（预留接口）
    
    Returns:
        List[Dict]: 策略信息字典列表
    """
    return [m.to_dict() for m in STRATEGY_REGISTRY.get_top_performers(10)]


# 🏷️ 三分类API（策略增强核心）
def get_strategy_tree() -> Dict[str, Any]:
    """
    三分类策略树API：按传统/ML/物理建模分类
    
    Returns:
        Dict: {traditional: [...], ml_enhanced: [...], physics_based: [...]}
    """
    all_meta = STRATEGY_REGISTRY.list_all()

    traditional = []
    ml_enhanced = []
    physics_based = []

    for meta in all_meta:
        d = meta.to_dict()
        name_lower = meta.name.lower()

        # 物理建模策略判定
        is_physics = any(kw in name_lower for kw in (
            "newton", "thermodynamic", "fractal", "fluid",
            "physic", "entropy", "reynolds", "vortex", "laminar",
            "momentum_enhanced", "thermo", "fluid_dynamic"
        ))
        # 增强判定：检查描述中是否包含物理关键词
        if not is_physics and meta.description:
            desc_lower = meta.description.lower()
            is_physics = any(kw in desc_lower for kw in (
                "牛顿", "热力学", "分形", "流体", "物理建模",
                "newton", "thermodynamic", "fractal", "fluid"
            ))

        # ML增强策略判定
        is_ml = any(kw in name_lower for kw in (
            "ml_", "adaptive_ml", "rl_optimized", "rl_adaptive",
            "machine_learn", "deep_", "neural"
        ))

        if is_physics:
            physics_based.append(d)
        elif is_ml:
            ml_enhanced.append(d)
        elif meta.strategy_type in ("ml", "rl"):
            ml_enhanced.append(d)
        else:
            traditional.append(d)

    return {
        "traditional": traditional,
        "ml_enhanced": ml_enhanced,
        "physics_based": physics_based,
    }


class StrategyCategory:
    """策略类别枚举（预留）"""
    GENERAL = "general"
    TREND = "trend"
    GRID = "grid"
    ML = "ml"
    RL = "rl"
    FOURIER = "fourier"
    VALUE = "value"
    COMPOSITE = "composite"
    PHYSICS = "physics"


class MarketRegime:
    """市场状态枚举（预留）"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"


# ==================== 自测 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 70)
    print("策略注册表 (StrategyRegistry) 自测")
    print("=" * 70)

    registry = StrategyRegistry(
        strategies_dir=DEFAULT_STRATEGIES_DIR,
        db_path=DEFAULT_DB_PATH,
        auto_scan=True,
    )

    # 1. 扫描结果
    print(f"\n📊 扫描结果: 共 {registry.count()} 个策略")
    print(f"   已启用: {registry.count_enabled()} 个")

    # 2. 类型分布
    summary = registry.to_summary()
    print(f"\n📂 类型分布: {summary['by_type']}")
    print(f"📋 状态分布: {summary['by_status']}")

    # 3. 列出所有策略
    print(f"\n📝 策略列表:")
    print("-" * 70)
    for i, meta in enumerate(registry.list_all(), 1):
        status_icon = "✅" if meta.enabled else "❌"
        print(f"  {i:2d}. {status_icon} {meta.name:<35} "
              f"类型={meta.strategy_type:<12} "
              f"评分={meta.performance_score:.1f} "
              f"状态={meta.status}")

    # 4. 按类型筛选
    print(f"\n🔍 ML 类策略: {len(registry.list_by_type('ml'))} 个")
    for meta in registry.list_by_type("ml"):
        print(f"    - {meta.name}")

    # 5. 性能排名
    print(f"\n🏆 性能排名 TOP 5:")
    for i, meta in enumerate(registry.get_top_performers(5), 1):
        print(f"    {i}. {meta.name:<35} score={meta.performance_score:.2f}")

    # 6. 测试启用/禁用
    if registry.count() > 0:
        test_name = registry.get_names()[0]
        print(f"\n🔄 测试切换: {test_name}")
        old_state = registry.get(test_name).enabled
        registry.toggle(test_name)
        new_state = registry.get(test_name).enabled
        print(f"    {old_state} → {new_state}")
        registry.toggle(test_name)  # 恢复

    # 7. 三分类测试
    print(f"\n🏷️ 三分类策略树:")
    tree = get_strategy_tree()
    for cat, strategies in tree.items():
        print(f"   {cat}: {len(strategies)} 个策略")
        for s in strategies[:3]:
            print(f"      - {s['name']} ({s['strategy_type']})")

    # 8. 同步到数据库
    print(f"\n💾 数据库同步...")
    count = registry.sync_to_db()
    print(f"   已同步 {count} 条记录")

    print("\n" + "=" * 70)
    print("✅ 策略注册表自测完成！")
    print("=" * 70)