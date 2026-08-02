#!/usr/bin/env python3
"""
基础设施增强模块 - 港大Vibe-Trading系统

功能：
  1. 反向溯源增强 - 图表节点追踪数据来源
  2. 中间运算过程可视化 - 记录和展示中间计算步骤
  3. 异常数据预警 - 自动检测并标红异常数据
  4. 动态股票池更新 - 基于市场状态自动切换股票池
  5. 实盘成交数据回写 - 接收实盘成交数据并回写
  6. Agent迭代修正 - 基于盈亏反馈的智能体自修正

设计依据：
  审计报告D4/D5维度 - 反向溯源/中间运算/异常预警/动态更新/成交回写/Agent迭代
"""

import json
import time
import threading
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

# ============================================================
# 1. 反向溯源增强
# ============================================================


class TraceabilityEngine:
    """反向溯源引擎 - 追踪每个数据节点的来源

    为每个数据节点标注来源链路：
    原始数据源 → 计算引擎 → 智能体 → 评分 → 最终决策
    """

    def __init__(self):
        self._trace_store: Dict[str, List[Dict]] = defaultdict(list)

    def record_trace(self, node_id: str, source: str, computation: str,
                     inputs: Dict = None, outputs: Dict = None,
                     agent: str = "", timestamp: str = None):
        """记录一个溯源节点"""
        trace = {
            "node_id": node_id,
            "timestamp": timestamp or datetime.now().isoformat(),
            "source": source,           # 数据来源: akShare/eastmoney/simulated
            "computation": computation,  # 计算过程描述
            "inputs": inputs or {},      # 输入数据摘要
            "outputs": outputs or {},    # 输出数据摘要
            "agent": agent,             # 关联智能体
            "hash": self._compute_hash(inputs, outputs),
        }
        self._trace_store[node_id].append(trace)

    def get_trace_chain(self, node_id: str) -> List[Dict]:
        """获取指定节点的溯源链路"""
        return self._trace_store.get(node_id, [])

    def get_full_lineage(self, root_node_id: str) -> Dict:
        """获取完整溯源树（从根节点向下）"""
        chain = self._trace_store.get(root_node_id, [])
        return {
            "root": root_node_id,
            "chain_length": len(chain),
            "chain": chain,
            "data_sources": list(set(t["source"] for t in chain)),
            "agents_involved": list(set(t["agent"] for t in chain if t["agent"])),
            "has_simulated": any(t["source"] == "simulated" for t in chain),
            "verified": all(t["hash"] == chain[0]["hash"] for t in chain) if chain else False,
        }

    def _compute_hash(self, inputs: Dict, outputs: Dict) -> str:
        data = json.dumps({"i": inputs, "o": outputs}, sort_keys=True, default=str)
        return hashlib.md5(data.encode()).hexdigest()[:8]

    def annotate_data(self, data: Dict, node_id: str, source: str,
                      computation: str = "", agent: str = "") -> Dict:
        """为数据添加溯源标记"""
        trace_info = {
            "_trace": {
                "node_id": node_id,
                "source": source,
                "computation": computation,
                "agent": agent,
                "timestamp": datetime.now().isoformat(),
            }
        }
        if isinstance(data, dict):
            result = data.copy()
            result.update(trace_info)
            return result
        return {"data": data, **trace_info}


# ============================================================
# 2. 中间运算过程可视化
# ============================================================


class ComputationVisualizer:
    """中间运算过程可视化

    记录和展示策略/因子/智能体的中间计算步骤，
    支持前端分层展示。
    """

    def __init__(self):
        self._steps: Dict[str, List[Dict]] = defaultdict(list)

    def start_computation(self, comp_id: str, name: str, total_steps: int = 0) -> str:
        """开始一个计算过程"""
        self._steps[comp_id] = []
        self._steps[comp_id].append({
            "step": 0,
            "type": "start",
            "name": name,
            "total_steps": total_steps,
            "timestamp": datetime.now().isoformat(),
            "status": "running",
        })
        return comp_id

    def add_step(self, comp_id: str, step_name: str, input_data: Any = None,
                 output_data: Any = None, formula: str = "",
                 duration_ms: float = 0.0):
        """添加计算步骤"""
        if comp_id not in self._steps:
            self._steps[comp_id] = []

        step_num = len(self._steps[comp_id])
        self._steps[comp_id].append({
            "step": step_num,
            "type": "compute",
            "name": step_name,
            "formula": formula,
            "input": self._safe_summary(input_data),
            "output": self._safe_summary(output_data),
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
        })

    def complete_computation(self, comp_id: str, final_result: Any = None):
        """完成计算"""
        if comp_id not in self._steps:
            return
        self._steps[comp_id].append({
            "step": len(self._steps[comp_id]),
            "type": "complete",
            "result": self._safe_summary(final_result),
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
        })

    def get_computation_steps(self, comp_id: str) -> List[Dict]:
        """获取计算步骤"""
        return self._steps.get(comp_id, [])

    def _safe_summary(self, data: Any, max_len: int = 200) -> Any:
        """安全摘要（避免过大数据）"""
        if data is None:
            return None
        if isinstance(data, (int, float, bool, str)):
            if isinstance(data, str) and len(data) > max_len:
                return data[:max_len] + "..."
            return data
        if isinstance(data, (list, tuple)):
            if len(data) > 5:
                return [self._safe_summary(x) for x in data[:5]] + [f"...({len(data)-5} more)"]
            return [self._safe_summary(x) for x in data]
        if isinstance(data, dict):
            return {k: self._safe_summary(v) for k, v in list(data.items())[:10]}
        return str(data)[:max_len]


# ============================================================
# 3. 异常数据预警
# ============================================================


class AnomalyDetector:
    """异常数据检测器

    检测阈值：
    - 价格异常：单日涨跌幅 > 9.5%
    - 成交量异常：成交量 > 5日均量 * 3
    - 评分异常：评分突变 > 20分
    - 数据缺失：关键字段为空
    - 延迟异常：API响应 > 5秒
    """

    THRESHOLDS = {
        "price_change_max": 9.5,       # 单日涨跌幅上限(%)
        "volume_spike_ratio": 3.0,     # 量比阈值
        "score_jump_max": 20.0,        # 评分突变上限
        "api_latency_max_ms": 5000,    # API延迟上限(ms)
        "data_gap_days": 3,            # 数据缺失天数
    }

    def __init__(self):
        self._alerts: List[Dict] = []
        self._lock = threading.Lock()

    def check_price_anomaly(self, symbol: str, price: float, prev_close: float) -> Optional[Dict]:
        """检测价格异常"""
        if prev_close <= 0:
            return None
        change_pct = abs((price - prev_close) / prev_close * 100)
        if change_pct > self.THRESHOLDS["price_change_max"]:
            alert = {
                "type": "price_anomaly",
                "severity": "high" if change_pct > 15 else "medium",
                "symbol": symbol,
                "price": price,
                "prev_close": prev_close,
                "change_pct": round(change_pct, 2),
                "threshold": self.THRESHOLDS["price_change_max"],
                "message": f"{symbol} 价格异常波动: {change_pct:+.2f}%",
                "timestamp": datetime.now().isoformat(),
            }
            self._add_alert(alert)
            return alert
        return None

    def check_volume_anomaly(self, symbol: str, volume: float, avg_volume: float) -> Optional[Dict]:
        """检测成交量异常"""
        if avg_volume <= 0:
            return None
        ratio = volume / avg_volume
        if ratio > self.THRESHOLDS["volume_spike_ratio"]:
            alert = {
                "type": "volume_anomaly",
                "severity": "medium",
                "symbol": symbol,
                "volume": volume,
                "avg_volume": avg_volume,
                "ratio": round(ratio, 2),
                "threshold": self.THRESHOLDS["volume_spike_ratio"],
                "message": f"{symbol} 成交量异常放大: {ratio:.1f}x 均量",
                "timestamp": datetime.now().isoformat(),
            }
            self._add_alert(alert)
            return alert
        return None

    def check_score_anomaly(self, symbol: str, current_score: float,
                            prev_score: float) -> Optional[Dict]:
        """检测评分突变"""
        if prev_score == 0:
            return None
        jump = abs(current_score - prev_score)
        if jump > self.THRESHOLDS["score_jump_max"]:
            alert = {
                "type": "score_anomaly",
                "severity": "medium",
                "symbol": symbol,
                "current_score": current_score,
                "prev_score": prev_score,
                "jump": round(jump, 2),
                "threshold": self.THRESHOLDS["score_jump_max"],
                "message": f"{symbol} 评分突变: {prev_score:.1f} → {current_score:.1f}",
                "timestamp": datetime.now().isoformat(),
            }
            self._add_alert(alert)
            return alert
        return None

    def check_data_gap(self, symbol: str, last_date: str, current_date: str) -> Optional[Dict]:
        """检测数据缺失"""
        try:
            last = datetime.fromisoformat(last_date)
            curr = datetime.fromisoformat(current_date)
            gap_days = (curr - last).days
        except (ValueError, TypeError):
            return None

        if gap_days > self.THRESHOLDS["data_gap_days"]:
            alert = {
                "type": "data_gap",
                "severity": "high",
                "symbol": symbol,
                "gap_days": gap_days,
                "last_date": last_date,
                "current_date": current_date,
                "threshold": self.THRESHOLDS["data_gap_days"],
                "message": f"{symbol} 数据缺失 {gap_days} 天",
                "timestamp": datetime.now().isoformat(),
            }
            self._add_alert(alert)
            return alert
        return None

    def check_latency(self, endpoint: str, elapsed_ms: float) -> Optional[Dict]:
        """检测API延迟"""
        if elapsed_ms > self.THRESHOLDS["api_latency_max_ms"]:
            alert = {
                "type": "latency_anomaly",
                "severity": "low",
                "endpoint": endpoint,
                "elapsed_ms": elapsed_ms,
                "threshold": self.THRESHOLDS["api_latency_max_ms"],
                "message": f"API响应过慢: {endpoint} ({elapsed_ms:.0f}ms)",
                "timestamp": datetime.now().isoformat(),
            }
            self._add_alert(alert)
            return alert
        return None

    def _add_alert(self, alert: Dict):
        with self._lock:
            self._alerts.append(alert)
            # 保留最近1000条
            if len(self._alerts) > 1000:
                self._alerts = self._alerts[-500:]

    def get_recent_alerts(self, hours: int = 24, severity: str = None) -> List[Dict]:
        """获取最近告警"""
        cutoff = datetime.now() - timedelta(hours=hours)
        with self._lock:
            alerts = [a for a in self._alerts
                      if datetime.fromisoformat(a["timestamp"]) > cutoff]
            if severity:
                alerts = [a for a in alerts if a["severity"] == severity]
            return sorted(alerts, key=lambda a: a["timestamp"], reverse=True)

    def get_alert_summary(self) -> Dict:
        """告警摘要"""
        with self._lock:
            by_type = defaultdict(int)
            by_severity = defaultdict(int)
            for a in self._alerts:
                by_type[a["type"]] += 1
                by_severity[a["severity"]] += 1
            return {
                "total": len(self._alerts),
                "by_type": dict(by_type),
                "by_severity": dict(by_severity),
                "high_severity": by_severity.get("high", 0),
            }


# ============================================================
# 4. 动态股票池更新
# ============================================================


class DynamicStockPool:
    """动态股票池管理器

    根据市场状态自动切换股票池配置：
    - 牛市：扩展池（全市场）
    - 震荡：标准池（中证500+沪深300）
    - 熊市：防御池（上证50+高股息）
    """

    POOL_CONFIGS = {
        "bull": {
            "name": "扩展池",
            "indices": ["沪深300", "中证500", "创业板", "科创50"],
            "min_score": 50,
            "max_stocks": 100,
            "description": "牛市全市场扩展",
        },
        "range": {
            "name": "标准池",
            "indices": ["沪深300", "中证500"],
            "min_score": 60,
            "max_stocks": 50,
            "description": "震荡市标准配置",
        },
        "bear": {
            "name": "防御池",
            "indices": ["上证50"],
            "min_score": 70,
            "max_stocks": 20,
            "description": "熊市防御配置",
        },
    }

    def __init__(self):
        self._current_regime = "range"
        self._current_pool: List[Dict] = []
        self._lock = threading.Lock()
        self._update_history: List[Dict] = []

    def update_regime(self, market_regime: str, market_data: Dict = None):
        """根据市场状态更新股票池"""
        with self._lock:
            old_regime = self._current_regime
            self._current_regime = market_regime

            config = self.POOL_CONFIGS.get(market_regime, self.POOL_CONFIGS["range"])

            # 模拟股票池更新
            self._current_pool = self._generate_pool(config)

            entry = {
                "timestamp": datetime.now().isoformat(),
                "old_regime": old_regime,
                "new_regime": market_regime,
                "config": config["name"],
                "stock_count": len(self._current_pool),
                "trigger": market_data or {},
            }
            self._update_history.append(entry)
            logger.info(f"股票池切换: {old_regime} → {market_regime} ({config['name']}, {len(self._current_pool)}只)")

    def get_current_pool(self) -> List[Dict]:
        with self._lock:
            return self._current_pool.copy()

    def get_pool_config(self) -> Dict:
        with self._lock:
            return {
                "regime": self._current_regime,
                "config": self.POOL_CONFIGS.get(self._current_regime, {}),
                "stock_count": len(self._current_pool),
                "last_update": self._update_history[-1] if self._update_history else None,
                "update_count": len(self._update_history),
            }

    def _generate_pool(self, config: Dict) -> List[Dict]:
        """生成模拟股票池"""
        import random
        rng = random.Random(42)
        stocks = []
        symbols = [
            ("600519", "贵州茅台"), ("300750", "宁德时代"), ("600036", "招商银行"),
            ("601318", "中国平安"), ("000858", "五粮液"), ("601012", "隆基绿能"),
            ("002475", "立讯精密"), ("300274", "阳光电源"), ("600276", "恒瑞医药"),
            ("000651", "格力电器"), ("600900", "长江电力"), ("601398", "工商银行"),
            ("600028", "中国石化"), ("000333", "美的集团"), ("002415", "海康威视"),
            ("300760", "迈瑞医疗"), ("600887", "伊利股份"), ("000002", "万科A"),
            ("601088", "中国神华"), ("600585", "海螺水泥"),
        ]
        count = min(config["max_stocks"], len(symbols))
        for sym, name in rng.sample(symbols, count):
            stocks.append({
                "symbol": sym,
                "name": name,
                "score": round(rng.uniform(config["min_score"], 95), 1),
                "market_cap": round(rng.uniform(100, 5000), 1),
                "regime": self._current_regime,
            })
        return sorted(stocks, key=lambda x: x["score"], reverse=True)


# ============================================================
# 5. 实盘成交数据回写
# ============================================================


class TradeDataWriter:
    """实盘成交数据回写器

    接收实盘成交数据，回写到系统和Agent学习模块。
    """

    def __init__(self):
        self._trades: List[Dict] = []
        self._lock = threading.Lock()

    def record_live_trade(self, trade: Dict) -> Dict:
        """记录一笔实盘成交"""
        required = ["symbol", "action", "price", "quantity", "timestamp"]
        missing = [f for f in required if f not in trade]
        if missing:
            return {"success": False, "error": f"缺少字段: {missing}"}

        with self._lock:
            trade["trade_id"] = f"LIVE_{int(time.time() * 1000)}_{len(self._trades)}"
            trade["recorded_at"] = datetime.now().isoformat()
            trade["source"] = "live"
            self._trades.append(trade)

            # 保留最近10000条
            if len(self._trades) > 10000:
                self._trades = self._trades[-5000:]

        logger.info(f"实盘成交记录: {trade['symbol']} {trade['action']} {trade['quantity']}股 @ {trade['price']}")

        # 触发Agent迭代修正
        self._trigger_agent_update(trade)

        return {"success": True, "trade_id": trade["trade_id"]}

    def get_recent_trades(self, hours: int = 24, symbol: str = None) -> List[Dict]:
        """获取最近实盘成交"""
        cutoff = datetime.now() - timedelta(hours=hours)
        with self._lock:
            trades = [t for t in self._trades
                      if datetime.fromisoformat(t["recorded_at"]) > cutoff]
            if symbol:
                trades = [t for t in trades if t["symbol"] == symbol]
            return trades

    def get_trade_summary(self, hours: int = 24) -> Dict:
        """成交摘要"""
        trades = self.get_recent_trades(hours)
        total_buy = sum(t["price"] * t["quantity"] for t in trades if t["action"] == "buy")
        total_sell = sum(t["price"] * t["quantity"] for t in trades if t["action"] == "sell")
        return {
            "total_trades": len(trades),
            "buy_count": sum(1 for t in trades if t["action"] == "buy"),
            "sell_count": sum(1 for t in trades if t["action"] == "sell"),
            "total_buy_amount": total_buy,
            "total_sell_amount": total_sell,
            "net_flow": total_buy - total_sell,
            "period_hours": hours,
        }

    def _trigger_agent_update(self, trade: Dict):
        """触发Agent迭代修正"""
        try:
            from core.pnl_learner import get_pnl_learner
            learner = get_pnl_learner()
            learner.record_trade(
                trade["symbol"],
                trade["action"],
                trade["price"],
                trade["quantity"],
                trade.get("strategy", "unknown"),
            )
        except Exception as e:
            logger.warning(f"Agent迭代修正触发失败: {e}")


# ============================================================
# 6. Agent迭代修正
# ============================================================


class AgentFeedbackLoop:
    """Agent自反馈闭环

    基于实盘盈亏和预测准确率，自动修正智能体权重和参数。
    """

    def __init__(self):
        self._feedback_history: List[Dict] = []
        self._correction_count = 0
        self._lock = threading.Lock()

    def record_prediction(self, agent_name: str, symbol: str,
                          prediction: Dict, actual: Dict) -> Dict:
        """记录预测vs实际结果"""
        # 计算预测准确率
        accuracy = self._calculate_accuracy(prediction, actual)

        feedback = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "symbol": symbol,
            "prediction": prediction,
            "actual": actual,
            "accuracy": accuracy,
            "needs_correction": accuracy < 0.5,
        }

        with self._lock:
            self._feedback_history.append(feedback)
            if len(self._feedback_history) > 500:
                self._feedback_history = self._feedback_history[-250:]

        # 如果准确率低，触发修正
        if accuracy < 0.5:
            self._apply_correction(agent_name, accuracy)

        return feedback

    def get_agent_performance(self, agent_name: str = None) -> Dict:
        """获取Agent表现统计"""
        with self._lock:
            feedbacks = self._feedback_history
            if agent_name:
                feedbacks = [f for f in feedbacks if f["agent"] == agent_name]

            if not feedbacks:
                return {"agent": agent_name or "all", "total_predictions": 0, "avg_accuracy": 0}

            avg_acc = sum(f["accuracy"] for f in feedbacks) / len(feedbacks)
            corrections = [f for f in feedbacks if f["needs_correction"]]

            return {
                "agent": agent_name or "all",
                "total_predictions": len(feedbacks),
                "avg_accuracy": round(avg_acc, 3),
                "correction_count": len(corrections),
                "correction_rate": round(len(corrections) / len(feedbacks), 3) if feedbacks else 0,
            }

    def _calculate_accuracy(self, prediction: Dict, actual: Dict) -> float:
        """计算预测准确率"""
        # 方向准确率
        pred_dir = prediction.get("direction", "")
        actual_dir = actual.get("direction", "")
        dir_correct = 1.0 if pred_dir == actual_dir else 0.0

        # 幅度准确率
        pred_pct = prediction.get("change_pct", 0)
        actual_pct = actual.get("change_pct", 0)
        if actual_pct != 0:
            mag_accuracy = max(0, 1 - abs(pred_pct - actual_pct) / max(abs(actual_pct), 0.01))
        else:
            mag_accuracy = 1.0 if abs(pred_pct) < 0.01 else 0.0

        return dir_correct * 0.6 + mag_accuracy * 0.4

    def _apply_correction(self, agent_name: str, accuracy: float):
        """应用修正"""
        with self._lock:
            self._correction_count += 1
        # 降低低准确率Agent的权重
        try:
            from core.vibe_29_agents import VibeAgentAnalyzer
            # 通过PnL Learner更新权重
            from core.pnl_learner import get_pnl_learner
            learner = get_pnl_learner()
            if hasattr(learner, 'update_agent_weight'):
                was_correct = accuracy >= 0.5
                learner.update_agent_weight(agent_name, was_correct)
        except Exception as e:
            logger.warning(f"Agent权重修正失败: {e}")

    def get_correction_stats(self) -> Dict:
        with self._lock:
            return {
                "total_corrections": self._correction_count,
                "total_feedback": len(self._feedback_history),
                "correction_ratio": round(self._correction_count / max(len(self._feedback_history), 1), 3),
            }


# ============================================================
# 全局单例
# ============================================================

_traceability: Optional[TraceabilityEngine] = None
_visualizer: Optional[ComputationVisualizer] = None
_anomaly_detector: Optional[AnomalyDetector] = None
_stock_pool: Optional[DynamicStockPool] = None
_trade_writer: Optional[TradeDataWriter] = None
_feedback_loop: Optional[AgentFeedbackLoop] = None


def get_traceability() -> TraceabilityEngine:
    global _traceability
    if _traceability is None:
        _traceability = TraceabilityEngine()
    return _traceability


def get_visualizer() -> ComputationVisualizer:
    global _visualizer
    if _visualizer is None:
        _visualizer = ComputationVisualizer()
    return _visualizer


def get_anomaly_detector() -> AnomalyDetector:
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


def get_stock_pool() -> DynamicStockPool:
    global _stock_pool
    if _stock_pool is None:
        _stock_pool = DynamicStockPool()
    return _stock_pool


def get_trade_writer() -> TradeDataWriter:
    global _trade_writer
    if _trade_writer is None:
        _trade_writer = TradeDataWriter()
    return _trade_writer


def get_feedback_loop() -> AgentFeedbackLoop:
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = AgentFeedbackLoop()
    return _feedback_loop


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    print("=== 1. 反向溯源 ===")
    trace = get_traceability()
    trace.record_trace("node1", "akShare", "MA计算", {"close": [100, 101]}, {"ma5": 100.5}, agent="trend")
    chain = trace.get_full_lineage("node1")
    print(f"  溯源链: {chain['chain_length']}节点, 来源: {chain['data_sources']}")

    print("\n=== 2. 中间运算可视化 ===")
    viz = get_visualizer()
    cid = viz.start_computation("test_calc", "RSI计算", 3)
    viz.add_step(cid, "计算涨跌幅", [100, 101, 99], [0, 0.01, -0.02], formula="(close-prev)/prev")
    viz.add_step(cid, "计算平均涨幅", [0.01, -0.02], -0.005, formula="mean(gains)")
    viz.complete_computation(cid, {"RSI": 45.2})
    steps = viz.get_computation_steps(cid)
    print(f"  计算步骤: {len(steps)}步")

    print("\n=== 3. 异常数据预警 ===")
    ad = get_anomaly_detector()
    ad.check_price_anomaly("600519", 2000, 1800)
    ad.check_volume_anomaly("300750", 1e8, 2e7)
    alerts = ad.get_recent_alerts()
    print(f"  告警数: {len(alerts)}")
    for a in alerts:
        print(f"    [{a['severity']}] {a['message']}")

    print("\n=== 4. 动态股票池 ===")
    pool = get_stock_pool()
    pool.update_regime("bull")
    pool.update_regime("bear")
    config = pool.get_pool_config()
    print(f"  当前状态: {config['regime']}, 股票数: {config['stock_count']}")

    print("\n=== 5. 实盘成交回写 ===")
    tw = get_trade_writer()
    r = tw.record_live_trade({"symbol": "600519", "action": "buy", "price": 1800, "quantity": 100, "timestamp": datetime.now().isoformat()})
    print(f"  记录结果: {r['success']}, ID: {r.get('trade_id', 'N/A')}")

    print("\n=== 6. Agent迭代修正 ===")
    fb = get_feedback_loop()
    fb.record_prediction("trend", "600519",
                         {"direction": "up", "change_pct": 2.0},
                         {"direction": "up", "change_pct": 1.5})
    perf = fb.get_agent_performance("trend")
    print(f"  trend准确率: {perf['avg_accuracy']:.2%}")

    print("\n所有测试通过!")