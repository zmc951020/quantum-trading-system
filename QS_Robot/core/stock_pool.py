#!/usr/bin/env python3
"""
股票池管理模块（Stock Pool Manager）

分层体系：
  ┌─────────────────────────────────────────────────────────┐
  │  观察池(Watchlist) → 候选池(Candidate) → 测试池(Testing)  │
  │                                          ↓              │
  │                           预实盘池(PreLive) → 实盘池(Live)│
  └─────────────────────────────────────────────────────────┘

核心能力：
  1. 分层管理：5个层级，严格准入条件
  2. 条件筛选：PE、流动性、财务指标等多维度筛选
  3. 自动流转：满足条件自动升级到下一级池
  4. 状态追踪：记录每只股票的流转历史
  5. 批量操作：支持从股票池批量启动策略优化/回测
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 股票池层级定义
# ============================================================

class PoolLevel(Enum):
    WATCHLIST = "watchlist"       # 观察池：技术分析选中的股票
    CANDIDATE = "candidate"       # 候选池：满足基础筛选条件
    TESTING = "testing"           # 测试池：正在进行回测验证
    PRELIVE = "prelive"           # 预实盘池：回测通过，等待实盘
    LIVE = "live"                 # 实盘池：真实交易

    def __lt__(self, other):
        order = [PoolLevel.WATCHLIST, PoolLevel.CANDIDATE, PoolLevel.TESTING, 
                 PoolLevel.PRELIVE, PoolLevel.LIVE]
        return order.index(self) < order.index(other)

    def __gt__(self, other):
        order = [PoolLevel.WATCHLIST, PoolLevel.CANDIDATE, PoolLevel.TESTING, 
                 PoolLevel.PRELIVE, PoolLevel.LIVE]
        return order.index(self) > order.index(other)

    def next(self):
        order = [PoolLevel.WATCHLIST, PoolLevel.CANDIDATE, PoolLevel.TESTING, 
                 PoolLevel.PRELIVE, PoolLevel.LIVE]
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else self


class StockSource(Enum):
    """选股来源 - 三类分流+两类种子池入口

    三类分流（直接对比哪类策略更好）：
      AURORA_NATIVE  - 自创策略选股
      VIBE_TRADING   - 港大 Vibe Trading 选股
      THS_IWENCAI    - 同花顺问财/策略选股（已通过量化验证）

    两类种子池（金融大师人工/专家筛选，需通过32策略量化验证才能升级）：
      THS_MASTER_POOL - 金融大师策略股票池入口（教学/演示池）
      THS_EXPERT      - 金融大师专家评点股票池（人工推荐池）
    """
    AURORA_NATIVE = "aurora_native"   # 自创策略选股
    VIBE_TRADING = "vibe_trading"     # 港大 Vibe Trading 选股
    THS_IWENCAI = "ths_iwencai"       # 同花顺问财/策略选股
    THS_MASTER_POOL = "ths_master_pool"  # 金融大师策略股票池（种子池）
    THS_EXPERT = "ths_expert"            # 专家评点股票池（种子池）

    @classmethod
    def seed_sources(cls) -> list:
        """所有种子池来源（需通过验证才能升级为实盘池）"""
        return [cls.THS_MASTER_POOL, cls.THS_EXPERT]

    @classmethod
    def trading_sources(cls) -> list:
        """所有实盘交易类来源（三类分流）"""
        return [cls.AURORA_NATIVE, cls.VIBE_TRADING, cls.THS_IWENCAI]

# ============================================================
# 股票记录
# ============================================================

@dataclass
class StockRecord:
    symbol: str                      # 股票代码
    name: str                        # 股票名称
    level: PoolLevel                 # 当前层级
    added_at: str                    # 加入时间
    last_updated: str                # 最后更新时间
    source: StockSource = StockSource.AURORA_NATIVE  # 选股来源（三类分流）
    strategy_name: str = ""          # 产生信号的策略名
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加信息（PE、行业、财务指标等）
    history: List[Dict[str, Any]] = field(default_factory=list)  # 流转历史
    backtest_results: List[Dict[str, Any]] = field(default_factory=list)  # 回测记录
    risk_score: float = 0.0          # 风控评分
    strategy_params: Dict[str, Any] = field(default_factory=dict)  # 优化后的策略参数

# ============================================================
# 筛选条件配置
# ============================================================

@dataclass
class FilterCondition:
    name: str
    description: str
    field: str
    operator: str  # <, >, <=, >=, ==, in, between
    value: Any
    required: bool = True

# ============================================================
# 股票池管理器
# ============================================================

class StockPoolManager:
    def __init__(self, data_path: str = "data/stock_pools.json"):
        self._data_path = os.path.join(os.path.dirname(__file__), "..", data_path)
        self._pools: Dict[str, StockRecord] = {}  # symbol -> StockRecord
        self._filters: Dict[str, List[FilterCondition]] = {
            "to_candidate": [
                FilterCondition("PE筛选", "PE<20", "pe", "<", 20),
                FilterCondition("市值筛选", "市值>50亿", "market_cap", ">", 50),
                FilterCondition("流动性", "日均成交额>1亿", "avg_volume", ">", 1),
                FilterCondition("非ST", "非ST股票", "is_st", "==", False),
            ],
            "to_testing": [
                FilterCondition("夏普比率", "夏普>1.5", "sharpe", ">", 1.5),
                FilterCondition("最大回撤", "最大回撤<20%", "max_drawdown", "<", 20),
                FilterCondition("胜率", "胜率>50%", "win_rate", ">", 50),
            ],
            "to_prelive": [
                FilterCondition("风控评分", "风控评分>80", "risk_score", ">", 80),
                FilterCondition("策略稳定性", "参数敏感度<0.3", "param_sensitivity", "<", 0.3),
                FilterCondition("样本外验证", "样本外收益>0", "oos_return", ">", 0),
            ],
        }
        self._load()

    def _load(self):
        """从文件加载股票池数据"""
        try:
            if os.path.exists(self._data_path):
                with open(self._data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # StockRecord 期望的字段列表
                valid_fields = {"symbol", "name", "level", "added_at", "last_updated",
                                "source", "strategy_name",
                                "metadata", "history", "backtest_results", "risk_score", "strategy_params"}
                for symbol, record in data.items():
                    # 过滤未知字段，防止旧版本JSON中的废弃字段导致错误
                    record = {k: v for k, v in record.items() if k in valid_fields}
                    # 补充缺失字段的默认值
                    record.setdefault("metadata", {})
                    record.setdefault("history", [])
                    record.setdefault("backtest_results", [])
                    record.setdefault("risk_score", 0.0)
                    record.setdefault("strategy_params", {})
                    record.setdefault("strategy_name", "")
                    record["level"] = PoolLevel(record["level"])
                    # source 兼容旧数据：无则默认 aurora_native
                    src = record.get("source", "aurora_native")
                    record["source"] = StockSource(src) if isinstance(src, str) else (src or StockSource.AURORA_NATIVE)
                    self._pools[symbol] = StockRecord(**record)
        except Exception as e:
            print(f"[StockPool] 加载数据失败，使用空池: {e}")

    def _save(self):
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
            data = {k: vars(v).copy() for k, v in self._pools.items()}
            # 转换枚举为字符串（兼容已保存为字符串的情况）
            for v in data.values():
                if hasattr(v["level"], 'value'):
                    v["level"] = v["level"].value
                if hasattr(v.get("source"), 'value'):
                    v["source"] = v["source"].value
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import traceback
            print(f"[StockPool] 保存失败: {e}")
            traceback.print_exc()

    # ---------- 基础操作 ----------

    def add_stock(self, symbol: str, name: str, level: PoolLevel = PoolLevel.WATCHLIST,
                  metadata: Dict = None, source: StockSource = StockSource.AURORA_NATIVE,
                  strategy_name: str = ""):
        """添加股票到指定池

        Args:
            source: 选股来源（三类分流）
            strategy_name: 产生信号的策略名
        """
        if symbol in self._pools:
            return {"success": False, "error": f"股票 {symbol} 已存在"}

        now = datetime.now().isoformat()
        record = StockRecord(
            symbol=symbol,
            name=name,
            level=level,
            added_at=now,
            last_updated=now,
            source=source,
            strategy_name=strategy_name,
            metadata=metadata or {},
            history=[{
                "timestamp": now,
                "action": "added",
                "level": level.value,
                "source": source.value
            }]
        )
        self._pools[symbol] = record
        self._save()
        return {"success": True, "message": f"已加入{level.value}池（来源：{source.value}）"}

    def remove_stock(self, symbol: str):
        """从所有池中移除股票"""
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}
        
        del self._pools[symbol]
        self._save()
        return {"success": True, "message": "已移除"}

    def update_stock(self, symbol: str, **kwargs):
        """更新股票信息"""
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}
        
        record = self._pools[symbol]
        for k, v in kwargs.items():
            if hasattr(record, k):
                setattr(record, k, v)
        record.last_updated = datetime.now().isoformat()
        self._save()
        return {"success": True}

    # ---------- 条件筛选与自动升级 ----------

    def check_condition(self, symbol: str, filter_key: str) -> bool:
        """检查股票是否满足指定筛选条件"""
        if symbol not in self._pools:
            return False
        
        record = self._pools[symbol]
        conditions = self._filters.get(filter_key, [])
        
        for cond in conditions:
            value = record.metadata.get(cond.field)
            if value is None:
                if cond.required:
                    return False
                continue
            
            # 类型转换：确保 value 与 cond.value 类型一致
            if isinstance(value, str) and isinstance(cond.value, (int, float)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    if cond.required:
                        return False
                    continue
            elif isinstance(value, (int, float)) and isinstance(cond.value, str):
                try:
                    cond.value = float(cond.value)
                except (ValueError, TypeError):
                    if cond.required:
                        return False
                    continue
            
            # 条件判断
            if cond.operator == "<":
                if not (value < cond.value):
                    return False
            elif cond.operator == ">":
                if not (value > cond.value):
                    return False
            elif cond.operator == "<=":
                if not (value <= cond.value):
                    return False
            elif cond.operator == ">=":
                if not (value >= cond.value):
                    return False
            elif cond.operator == "==":
                if value != cond.value:
                    return False
            elif cond.operator == "in":
                if value not in cond.value:
                    return False
            elif cond.operator == "between":
                if not isinstance(cond.value, (list, tuple)) or len(cond.value) != 2:
                    if cond.required:
                        return False
                    continue
                if not (cond.value[0] <= value <= cond.value[1]):
                    return False
        
        return True

    def promote(self, symbol: str, new_level: Optional[PoolLevel] = None) -> Dict:
        """升级股票到更高层级（自动或指定）"""
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}
        
        record = self._pools[symbol]
        target_level = new_level if new_level else record.level.next()
        
        if target_level <= record.level:
            return {"success": False, "error": "目标层级必须高于当前层级"}
        
        # 检查筛选条件
        filter_key = f"to_{target_level.value}"
        if filter_key in self._filters and not self.check_condition(symbol, filter_key):
            return {"success": False, "error": f"未满足{target_level.value}池的筛选条件"}
        
        # 执行升级
        old_level = record.level
        record.level = target_level
        record.last_updated = datetime.now().isoformat()
        record.history.append({
            "timestamp": record.last_updated,
            "action": "promoted",
            "from": old_level.value,
            "to": target_level.value
        })
        
        self._save()
        return {
            "success": True,
            "message": f"{symbol} 从{old_level.value}升级到{target_level.value}",
            "symbol": symbol,
            "old_level": old_level.value,
            "new_level": target_level.value
        }

    def auto_promote_all(self) -> List[Dict]:
        """自动升级所有符合条件的股票"""
        results = []
        for symbol in list(self._pools.keys()):
            result = self.promote(symbol)
            results.append(result)
        return results

    # ---------- 查询 ----------

    def get_pool(self, level: PoolLevel) -> List[StockRecord]:
        """获取指定池的所有股票"""
        return [r for r in self._pools.values() if r.level == level]

    def get_stock(self, symbol: str) -> Optional[StockRecord]:
        """获取单个股票信息"""
        return self._pools.get(symbol)

    def get_all_stocks(self) -> List[StockRecord]:
        """获取所有股票"""
        return list(self._pools.values())

    def get_pool_summary(self) -> Dict[str, int]:
        """获取各池股票数量统计"""
        summary = {level.value: 0 for level in PoolLevel}
        for record in self._pools.values():
            # 处理 level 可能是字符串的情况
            level_value = record.level.value if hasattr(record.level, 'value') else record.level
            if level_value in summary:
                summary[level_value] += 1
        return summary

    def get_stocks_by_source(self, source: StockSource) -> List[StockRecord]:
        """获取指定来源的所有股票（三类分流查询）"""
        return [r for r in self._pools.values() if r.source == source]

    def get_source_summary(self) -> Dict[str, int]:
        """获取各来源股票数量统计（三类对比）"""
        summary = {s.value: 0 for s in StockSource}
        for record in self._pools.values():
            src = record.source.value if hasattr(record.source, 'value') else record.source
            if src in summary:
                summary[src] += 1
        return summary

    def get_source_level_matrix(self) -> Dict[str, Dict[str, int]]:
        """获取 来源×层级 矩阵统计（三类选股+两类种子池在各池的分布）"""
        matrix = {s.value: {l.value: 0 for l in PoolLevel} for s in StockSource}
        for record in self._pools.values():
            src = record.source.value if hasattr(record.source, 'value') else record.source
            lvl = record.level.value if hasattr(record.level, 'value') else record.level
            if src in matrix and lvl in matrix[src]:
                matrix[src][lvl] += 1
        return matrix

    # ---------- 种子池升级流程（金融大师股票池→验证→实盘池）----------

    def add_seed_stock(self, symbol: str, name: str,
                       source: StockSource,
                       strategy_name: str = "",
                       metadata: Dict = None) -> Dict:
        """添加种子池股票（金融大师策略股票池 / 专家评点股票池）

        种子池股票必须经过32策略量化验证才能升级为THS_IWENCAI实盘池
        """
        if source not in StockSource.seed_sources():
            return {"success": False,
                    "error": f"{source} 不是种子池来源，请使用 add_stock"}
        return self.add_stock(
            symbol=symbol, name=name,
            level=PoolLevel.WATCHLIST,
            source=source,
            strategy_name=strategy_name,
            metadata=metadata or {},
        )

    def promote_seed_to_iwencai(self, symbol: str,
                                strategy_name: str = "",
                                validation_result: Dict = None) -> Dict:
        """种子池股票通过量化验证后升级为同花顺实盘池

        Args:
            symbol: 股票代码
            strategy_name: 通过验证的策略名
            validation_result: 验证结果（信号/回测/风控评分）
        """
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}

        record = self._pools[symbol]
        if record.source not in StockSource.seed_sources():
            return {"success": False,
                    "error": f"股票来源 {record.source.value} 非种子池，无需升级"}

        # 记录流转历史
        now = datetime.now().isoformat()
        record.history.append({
            "timestamp": now,
            "action": "seed_promoted",
            "from_source": record.source.value,
            "to_source": StockSource.THS_IWENCAI.value,
            "strategy": strategy_name,
            "validation": validation_result or {},
        })
        # 升级来源 + 记录验证结果
        record.source = StockSource.THS_IWENCAI
        record.strategy_name = strategy_name or record.strategy_name
        if validation_result:
            record.backtest_results.append({
                "timestamp": now,
                "strategy": strategy_name,
                **validation_result,
            })
            risk = validation_result.get("risk_score")
            if risk is not None:
                record.risk_score = float(risk)
        record.last_updated = now
        self._save()
        return {"success": True,
                "message": f"{symbol} 已从种子池升级为THS_IWENCAI实盘池"}

    def get_seed_pool_overview(self) -> Dict[str, Any]:
        """获取种子池整体看板（区分两类种子池+验证进度）"""
        overview = {
            "master_pool": {"total": 0, "promoted": 0, "pending": 0, "stocks": []},
            "expert": {"total": 0, "promoted": 0, "pending": 0, "stocks": []},
            "promoted_to_iwencai": 0,
        }
        for record in self._pools.values():
            # 种子池当前存量（未升级的）
            if record.source == StockSource.THS_MASTER_POOL:
                overview["master_pool"]["total"] += 1
                overview["master_pool"]["pending"] += 1
                overview["master_pool"]["stocks"].append({
                    "symbol": record.symbol, "name": record.name,
                    "added_at": record.added_at,
                    "strategy": record.strategy_name,
                })
            elif record.source == StockSource.THS_EXPERT:
                overview["expert"]["total"] += 1
                overview["expert"]["pending"] += 1
                overview["expert"]["stocks"].append({
                    "symbol": record.symbol, "name": record.name,
                    "added_at": record.added_at,
                    "strategy": record.strategy_name,
                })
            elif record.source == StockSource.THS_IWENCAI:
                # 检查历史是否从种子池升级而来
                for h in record.history:
                    if h.get("action") == "seed_promoted":
                        from_src = h.get("from_source", "")
                        if from_src == StockSource.THS_MASTER_POOL.value:
                            overview["master_pool"]["promoted"] += 1
                        elif from_src == StockSource.THS_EXPERT.value:
                            overview["expert"]["promoted"] += 1
                        overview["promoted_to_iwencai"] += 1
                        break
        return overview

    # ---------- 批量操作接口 ----------

    def batch_promote(self, symbols: List[str], target_level: PoolLevel) -> List[Dict]:
        """批量升级股票到目标池"""
        results = []
        for symbol in symbols:
            result = self.promote(symbol, target_level)
            results.append(result)
        return results

    def batch_add_from_list(self, stocks: List[Dict]):
        """从列表批量添加股票"""
        results = []
        for stock in stocks:
            symbol = stock.get("symbol")
            name = stock.get("name", symbol)
            level = stock.get("level", "watchlist")
            metadata = stock.get("metadata", {})
            result = self.add_stock(symbol, name, PoolLevel(level), metadata)
            results.append(result)
        return results

    # ---------- 回测结果记录 ----------

    def record_backtest(self, symbol: str, backtest_result: Dict):
        """记录股票的回测结果"""
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}
        
        record = self._pools[symbol]
        record.backtest_results.append({
            "timestamp": datetime.now().isoformat(),
            **backtest_result
        })
        
        # 更新 metadata 用于条件判断
        record.metadata["sharpe"] = backtest_result.get("sharpe_ratio", 0)
        record.metadata["max_drawdown"] = backtest_result.get("max_drawdown", 100)
        record.metadata["win_rate"] = backtest_result.get("win_rate", 0)
        
        record.last_updated = datetime.now().isoformat()
        self._save()
        return {"success": True}

    # ---------- 风控评估 ----------

    def set_risk_score(self, symbol: str, score: float):
        """设置风控评分"""
        if symbol not in self._pools:
            return {"success": False, "error": "股票不存在"}
        
        record = self._pools[symbol]
        record.risk_score = score
        record.metadata["risk_score"] = score
        record.last_updated = datetime.now().isoformat()
        self._save()
        return {"success": True}

# ============================================================
# 全局单例
# ============================================================

import threading

_pool_manager = None
_pool_manager_lock = threading.Lock()

def get_stock_pool_manager() -> StockPoolManager:
    global _pool_manager
    if _pool_manager is None:
        with _pool_manager_lock:
            if _pool_manager is None:
                _pool_manager = StockPoolManager()
    return _pool_manager

# ============================================================
# 示例用法
# ============================================================

if __name__ == "__main__":
    spm = get_stock_pool_manager()
    
    # 添加股票到观察池
    spm.add_stock("000001", "平安银行", metadata={"pe": 8.5, "market_cap": 2000, "avg_volume": 5})
    
    # 查询各池统计
    print("池统计:", spm.get_pool_summary())
    
    # 检查是否满足候选池条件
    print("满足候选池条件:", spm.check_condition("000001", "to_candidate"))
    
    # 尝试升级
    result = spm.promote("000001")
    print("升级结果:", result)
    
    # 打印所有股票
    for stock in spm.get_all_stocks():
        print(f"{stock.symbol} ({stock.name}): {stock.level.value}")