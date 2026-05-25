#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora 异常交易模式检测器 (Anomaly Detector)
检测异常交易行为：量价背离、高频刷单、非交易时段操作、异常盈亏模式
可作为独立模块运行，也可集成到 trade_security 验证链
"""

import os
import json
import time
from datetime import datetime, timedelta
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
#  数据模型
# ============================================================================

class AnomalyType(Enum):
    """异常类型"""
    VOLUME_PRICE_DIVERGENCE = "量价背离"         # 成交量与价格变动方向不一致
    HIGH_FREQUENCY_SPAM = "高频刷单"             # 短时间内大量订单
    OFF_HOURS_TRADING = "非交易时段操作"          # 在非交易时间尝试下单
    UNUSUAL_PROFIT_LOSS = "异常盈亏模式"          # 单笔盈亏远超正常范围
    RAPID_PRICE_SWING = "价格剧烈波动"            # 短时间内价格异常波动
    CONCENTRATED_POSITION = "集中持仓风险"        # 单票仓位过高
    OVERSIZED_ORDER = "超大单异常"               # 单笔金额远超均值
    FREQUENCY_BURST = "频率突增"                 # 下单频率突然飙升
    PATTERN_ATTACK = "模式攻击"                  # 疑似自动化攻击模式
    DATA_SOURCE_MISMATCH = "数据源不一致"         # 多数据源价格差异过大


@dataclass
class AnomalyRecord:
    """异常记录"""
    anomaly_type: AnomalyType
    timestamp: str
    severity: str  # low / medium / high / critical
    score: float   # 0-100 异常评分
    symbol: str = ""
    details: Dict = field(default_factory=dict)
    suggestion: str = ""


@dataclass
class TradeSnapshot:
    """交易快照（用于滑动窗口分析）"""
    timestamp: float
    symbol: str
    price: float
    volume: int
    amount: float
    direction: str  # buy / sell
    order_type: str  # market / limit


# ============================================================================
#  异常检测器核心
# ============================================================================

class AnomalyDetector:
    """
    异常交易模式检测器
    使用滑动窗口 + 统计方法检测多维异常
    """

    REPORT_FILE = "anomaly_report.json"

    def __init__(self, window_size: int = 100, max_history: int = 1000):
        """
        Args:
            window_size: 滑动窗口大小（最近N笔交易）
            max_history: 最大历史记录数
        """
        self.window_size = window_size
        self.max_history = max_history

        # 滑动窗口
        self.trades: deque = deque(maxlen=max_history)
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

        # 统计基线（运行时动态更新）
        self.baseline = {
            "avg_trade_amount": 0.0,
            "std_trade_amount": 0.0,
            "avg_trades_per_minute": 0.0,
            "avg_volume": 0,
            "avg_price": 0.0,
        }

        # 交易时段配置
        self.trading_hours = {
            "morning_start": "09:30",
            "morning_end": "11:30",
            "afternoon_start": "13:00",
            "afternoon_end": "15:00",
        }

        # 阈值配置
        self.thresholds = {
            "volume_price_divergence_pct": 20.0,      # 量价背离阈值 (%)
            "high_freq_interval_sec": 1.0,             # 高频刷单判定间隔(秒)
            "high_freq_count": 5,                       # 高频刷单判定次数
            "unusual_profit_loss_std": 3.0,             # 异常盈亏标准差倍数
            "rapid_price_swing_pct": 5.0,              # 价格剧烈波动阈值 (%)
            "concentrated_position_pct": 30.0,         # 集中持仓阈值 (%)
            "oversized_order_std": 3.0,                 # 超大单标准差倍数
            "frequency_burst_multiplier": 3.0,          # 频率突增倍数
            "data_source_mismatch_pct": 2.0,           # 数据源差异阈值 (%)
        }

        # 检测记录
        self.anomalies: List[AnomalyRecord] = []
        self._load_config()

    # ----- 配置持久化 -----
    def _load_config(self):
        """从文件加载阈值配置"""
        try:
            if os.path.exists("trade_security_config.json"):
                with open("trade_security_config.json", "r", encoding="utf-8") as f:
                    config = json.load(f)
                if "trading_hours" in config:
                    self.trading_hours = config["trading_hours"]
                if "anomaly_thresholds" in config:
                    self.thresholds.update(config["anomaly_thresholds"])
        except Exception:
            pass

    def _save_report(self):
        """保存异常报告"""
        try:
            report = {
                "generated_at": datetime.now().isoformat(),
                "total_anomalies": len(self.anomalies),
                "by_type": {},
                "recent": [],
            }
            for a in self.anomalies[-50:]:
                t = a.anomaly_type.value
                report["by_type"][t] = report["by_type"].get(t, 0) + 1
                report["recent"].append({
                    "type": t,
                    "timestamp": a.timestamp,
                    "severity": a.severity,
                    "score": a.score,
                    "symbol": a.symbol,
                    "suggestion": a.suggestion,
                })
            with open(self.REPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # =========================================================================
    #  数据输入
    # =========================================================================

    def feed_trade(self, symbol: str, price: float, volume: int, amount: float,
                   direction: str, order_type: str = "market") -> Optional[List[AnomalyRecord]]:
        """
        输入一笔交易，返回检测到的异常列表

        Args:
            symbol: 股票代码
            price: 成交价格
            volume: 成交量(股)
            amount: 成交金额
            direction: 买卖方向 (buy/sell)
            order_type: 订单类型 (market/limit)

        Returns:
            异常列表，无异常则返回 None
        """
        snapshot = TradeSnapshot(
            timestamp=time.time(),
            symbol=symbol,
            price=price,
            volume=volume,
            amount=amount,
            direction=direction,
            order_type=order_type,
        )

        self.trades.append(snapshot)
        self.price_history[symbol].append((snapshot.timestamp, price))
        self._update_baseline()

        new_anomalies = self._detect_all(snapshot)
        if new_anomalies:
            self.anomalies.extend(new_anomalies)
            self._save_report()

        return new_anomalies if new_anomalies else None

    def feed_market_data(self, symbol: str, price: float, volume: int):
        """输入市场数据（用于量价背离检测）"""
        self.price_history[symbol].append((time.time(), price))
        self.volume_history[symbol].append((time.time(), volume))

    def _update_baseline(self):
        """更新统计基线"""
        if len(self.trades) < 10:
            return

        recent = list(self.trades)[-self.window_size:]
        amounts = [t.amount for t in recent]
        prices = [t.price for t in recent]
        volumes = [t.volume for t in recent]

        self.baseline["avg_trade_amount"] = sum(amounts) / len(amounts) if amounts else 0
        self.baseline["std_trade_amount"] = (
            (sum((a - self.baseline["avg_trade_amount"]) ** 2 for a in amounts) / len(amounts)) ** 0.5
            if amounts else 0
        )
        self.baseline["avg_volume"] = sum(volumes) / len(volumes) if volumes else 0
        self.baseline["avg_price"] = sum(prices) / len(prices) if prices else 0

        # 计算平均交易频率（每分钟）
        if len(recent) >= 2:
            time_span = recent[-1].timestamp - recent[0].timestamp
            if time_span > 0:
                self.baseline["avg_trades_per_minute"] = len(recent) / (time_span / 60.0)

    # =========================================================================
    #  检测方法
    # =========================================================================

    def _detect_all(self, snapshot: TradeSnapshot) -> List[AnomalyRecord]:
        """执行所有异常检测"""
        anomalies = []

        detectors = [
            self._detect_volume_price_divergence,
            self._detect_high_frequency_spam,
            self._detect_off_hours_trading,
            self._detect_oversized_order,
            self._detect_concentrated_position,
            self._detect_frequency_burst,
            self._detect_rapid_price_swing,
        ]

        for detector in detectors:
            result = detector(snapshot)
            if result:
                anomalies.append(result)

        return anomalies

    # ---- 检测1: 量价背离 ----
    def _detect_volume_price_divergence(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """
        量价背离：价格大涨但成交量萎缩，或价格大跌但成交量萎缩
        正常情况：量价同向
        异常情况：价涨量缩 或 价跌量缩
        """
        symbol = snapshot.symbol
        hist_prices = list(self.price_history.get(symbol, []))
        hist_volumes = list(self.volume_history.get(symbol, []))

        if len(hist_prices) < 10 or len(hist_volumes) < 10:
            return None

        # 最近一段时间的价格变动
        recent_prices = [p for _, p in hist_prices[-10:]]
        recent_volumes = [v for _, v in hist_volumes[-10:]]

        avg_price_old = sum(recent_prices[:5]) / 5
        avg_price_new = sum(recent_prices[-5:]) / 5
        avg_volume_old = sum(recent_volumes[:5]) / 5 if recent_volumes[:5] else 1
        avg_volume_new = sum(recent_volumes[-5:]) / 5 if recent_volumes[-5:] else 1

        price_change_pct = ((avg_price_new - avg_price_old) / avg_price_old * 100) if avg_price_old > 0 else 0
        volume_change_pct = ((avg_volume_new - avg_volume_old) / avg_volume_old * 100) if avg_volume_old > 0 else 0

        threshold = self.thresholds["volume_price_divergence_pct"]

        # 价涨量缩
        if price_change_pct > threshold and volume_change_pct < -threshold:
            score = min(abs(price_change_pct) + abs(volume_change_pct), 100)
            return AnomalyRecord(
                anomaly_type=AnomalyType.VOLUME_PRICE_DIVERGENCE,
                timestamp=datetime.now().isoformat(),
                severity="high" if score > 60 else "medium",
                score=score,
                symbol=symbol,
                details={
                    "price_change_pct": round(price_change_pct, 2),
                    "volume_change_pct": round(volume_change_pct, 2),
                    "pattern": "价涨量缩",
                },
                suggestion="价格上涨但成交量萎缩，可能为诱多陷阱，建议谨慎操作"
            )

        # 价跌量缩
        if price_change_pct < -threshold and volume_change_pct < -threshold:
            score = min(abs(price_change_pct) + abs(volume_change_pct), 100)
            return AnomalyRecord(
                anomaly_type=AnomalyType.VOLUME_PRICE_DIVERGENCE,
                timestamp=datetime.now().isoformat(),
                severity="medium",
                score=score,
                symbol=symbol,
                details={
                    "price_change_pct": round(price_change_pct, 2),
                    "volume_change_pct": round(volume_change_pct, 2),
                    "pattern": "价跌量缩",
                },
                suggestion="价格下跌但成交量同步萎缩，可能为无量空跌，底部信号需结合其他指标判断"
            )

        return None

    # ---- 检测2: 高频刷单 ----
    def _detect_high_frequency_spam(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """
        高频刷单：短时间内大量同方向订单
        可能是自动化攻击或系统故障
        """
        interval = self.thresholds["high_freq_interval_sec"]
        count_threshold = self.thresholds["high_freq_count"]

        recent_in_window = []
        for t in reversed(self.trades):
            if snapshot.timestamp - t.timestamp <= interval:
                recent_in_window.append(t)
            else:
                break

        if len(recent_in_window) >= count_threshold:
            same_direction = [t for t in recent_in_window if t.direction == snapshot.direction]
            same_symbol = [t for t in recent_in_window if t.symbol == snapshot.symbol]

            score = min(len(recent_in_window) * 15, 100)
            severity = "critical" if len(recent_in_window) >= count_threshold * 2 else "high"

            # 检查是否为模式化攻击（精确间隔）
            if len(recent_in_window) >= 3:
                intervals = []
                for i in range(len(recent_in_window) - 1):
                    intervals.append(recent_in_window[i].timestamp - recent_in_window[i + 1].timestamp)
                if intervals and max(intervals) - min(intervals) < 0.1:  # 间隔高度一致
                    return AnomalyRecord(
                        anomaly_type=AnomalyType.PATTERN_ATTACK,
                        timestamp=datetime.now().isoformat(),
                        severity="critical",
                        score=95,
                        symbol=snapshot.symbol,
                        details={
                            "trades_in_window": len(recent_in_window),
                            "same_direction": len(same_direction),
                            "same_symbol": len(same_symbol),
                            "interval_pattern": "精确周期性",
                        },
                        suggestion="检测到精确周期性订单，疑似自动化攻击脚本，建议立即暂停该账户并启用验证码验证"
                    )

            return AnomalyRecord(
                anomaly_type=AnomalyType.HIGH_FREQUENCY_SPAM,
                timestamp=datetime.now().isoformat(),
                severity=severity,
                score=score,
                symbol=snapshot.symbol,
                details={
                    "trades_in_window": len(recent_in_window),
                    "window_seconds": interval,
                    "same_direction": len(same_direction),
                    "same_symbol": len(same_symbol),
                },
                suggestion=f"{interval}秒内{len(recent_in_window)}笔交易，疑似高频刷单，建议限流处理"
            )

        return None

    # ---- 检测3: 非交易时段操作 ----
    def _detect_off_hours_trading(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """检测非交易时段的下单操作"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # 周末检查
        if now.weekday() >= 5:
            return AnomalyRecord(
                anomaly_type=AnomalyType.OFF_HOURS_TRADING,
                timestamp=now.isoformat(),
                severity="medium",
                score=80,
                symbol=snapshot.symbol,
                details={"weekday": now.strftime("%A"), "time": current_time},
                suggestion="周末非交易日，A股市场休市，订单将在下一交易日执行"
            )

        # 交易时段检查
        ms = self.trading_hours.get("morning_start", "09:30")
        me = self.trading_hours.get("morning_end", "11:30")
        as_ = self.trading_hours.get("afternoon_start", "13:00")
        ae = self.trading_hours.get("afternoon_end", "15:00")

        in_morning = ms <= current_time <= me
        in_afternoon = as_ <= current_time <= ae

        if not in_morning and not in_afternoon:
            # 判断是盘前还是盘后
            if current_time < ms:
                context = "盘前"
            elif me < current_time < as_:
                context = "午间休市"
            else:
                context = "盘后"

            return AnomalyRecord(
                anomaly_type=AnomalyType.OFF_HOURS_TRADING,
                timestamp=now.isoformat(),
                severity="low",
                score=50,
                symbol=snapshot.symbol,
                details={
                    "current_time": current_time,
                    "trading_context": context,
                    "morning_session": f"{ms}-{me}",
                    "afternoon_session": f"{as_}-{ae}",
                },
                suggestion=f"当前为{context}，非A股连续竞价时段，订单可能延迟成交"
            )

        return None

    # ---- 检测4: 超大单异常 ----
    def _detect_oversized_order(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """检测远超均值的超大单"""
        avg = self.baseline.get("avg_trade_amount", 0)
        std = self.baseline.get("std_trade_amount", 0)

        if avg <= 0 or std <= 0 or len(self.trades) < 20:
            return None

        std_multiplier = self.thresholds["oversized_order_std"]
        threshold = avg + std_multiplier * std

        if snapshot.amount > threshold:
            deviation = (snapshot.amount - avg) / std
            score = min(deviation * 15, 100)

            severity = "critical" if deviation > 5 else "high" if deviation > 4 else "medium"

            return AnomalyRecord(
                anomaly_type=AnomalyType.OVERSIZED_ORDER,
                timestamp=datetime.now().isoformat(),
                severity=severity,
                score=score,
                symbol=snapshot.symbol,
                details={
                    "order_amount": snapshot.amount,
                    "avg_amount": round(avg, 2),
                    "std_deviation": round(deviation, 1),
                    "threshold": round(threshold, 2),
                },
                suggestion=f"订单金额{snapshot.amount:.0f}远超均值{avg:.0f}（{deviation:.1f}σ），建议人工审核后执行"
            )

        return None

    # ---- 检测5: 集中持仓风险 ----
    def _detect_concentrated_position(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """检测同一标的集中持仓风险"""
        symbol = snapshot.symbol
        threshold_pct = self.thresholds["concentrated_position_pct"]

        recent = list(self.trades)[-self.window_size:]
        if len(recent) < 10:
            return None

        total_amount = sum(t.amount for t in recent)
        symbol_amount = sum(t.amount for t in recent if t.symbol == symbol)

        if total_amount > 0:
            concentration = (symbol_amount / total_amount) * 100
            if concentration > threshold_pct:
                score = min(concentration, 100)
                return AnomalyRecord(
                    anomaly_type=AnomalyType.CONCENTRATED_POSITION,
                    timestamp=datetime.now().isoformat(),
                    severity="high" if concentration > 50 else "medium",
                    score=score,
                    symbol=symbol,
                    details={
                        "concentration_pct": round(concentration, 1),
                        "symbol_amount": symbol_amount,
                        "total_window_amount": total_amount,
                        "window_size": len(recent),
                    },
                    suggestion=f"交易集中在{symbol}（占比{concentration:.1f}%），建议分散持仓降低风险"
                )

        return None

    # ---- 检测6: 频率突增 ----
    def _detect_frequency_burst(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """检测下单频率突然飙升"""
        baseline_rate = self.baseline.get("avg_trades_per_minute", 0)

        if baseline_rate <= 0:
            return None

        # 计算最近1分钟的交易频率
        one_min_ago = snapshot.timestamp - 60
        recent_count = sum(1 for t in self.trades if t.timestamp >= one_min_ago)

        multiplier = self.thresholds["frequency_burst_multiplier"]
        if recent_count > baseline_rate * multiplier:
            ratio = recent_count / baseline_rate
            score = min(ratio * 20, 100)
            return AnomalyRecord(
                anomaly_type=AnomalyType.FREQUENCY_BURST,
                timestamp=datetime.now().isoformat(),
                severity="high" if ratio > 5 else "medium",
                score=score,
                symbol=snapshot.symbol,
                details={
                    "current_rate": recent_count,
                    "baseline_rate": round(baseline_rate, 2),
                    "ratio": round(ratio, 1),
                },
                suggestion=f"交易频率突增{ratio:.1f}倍，请确认是否为正常策略执行，建议检查策略参数"
            )

        return None

    # ---- 检测7: 价格剧烈波动 ----
    def _detect_rapid_price_swing(self, snapshot: TradeSnapshot) -> Optional[AnomalyRecord]:
        """检测短时间内价格剧烈波动"""
        symbol = snapshot.symbol
        hist = list(self.price_history.get(symbol, []))

        if len(hist) < 20:
            return None

        # 最近5分钟内的价格变化
        five_min_ago = snapshot.timestamp - 300
        recent_window = [p for t, p in hist if t >= five_min_ago]

        if len(recent_window) < 5:
            return None

        high = max(recent_window)
        low = min(recent_window)
        mid = recent_window[len(recent_window) // 2]

        if mid > 0:
            swing_pct = ((high - low) / mid) * 100
            threshold = self.thresholds["rapid_price_swing_pct"]

            if swing_pct > threshold:
                score = min(swing_pct * 8, 100)
                return AnomalyRecord(
                    anomaly_type=AnomalyType.RAPID_PRICE_SWING,
                    timestamp=datetime.now().isoformat(),
                    severity="high" if swing_pct > threshold * 2 else "medium",
                    score=score,
                    symbol=symbol,
                    details={
                        "swing_pct": round(swing_pct, 2),
                        "high": round(high, 2),
                        "low": round(low, 2),
                        "window_seconds": 300,
                    },
                    suggestion=f"5分钟内价格波动{swing_pct:.1f}%，建议暂停该标的交易观察"
                )

        return None

    # =========================================================================
    #  批量分析与报告
    # =========================================================================

    def get_summary(self) -> dict:
        """获取异常汇总"""
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        by_symbol = defaultdict(int)

        for a in self.anomalies[-200:]:
            by_type[a.anomaly_type.value] += 1
            by_severity[a.severity] += 1
            if a.symbol:
                by_symbol[a.symbol] += 1

        return {
            "total_anomalies": len(self.anomalies),
            "recent_200": {
                "by_type": dict(by_type),
                "by_severity": dict(by_severity),
                "by_symbol": dict(by_symbol),
            },
            "baseline": self.baseline,
            "active_thresholds": self.thresholds,
            "trading_hours": self.trading_hours,
        }

    def get_alerts(self, min_severity: str = "medium") -> List[dict]:
        """获取需要告警的异常"""
        severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_rank = severity_rank.get(min_severity, 1)

        alerts = []
        for a in self.anomalies[-50:]:
            if severity_rank.get(a.severity, 0) >= min_rank:
                alerts.append({
                    "type": a.anomaly_type.value,
                    "timestamp": a.timestamp,
                    "severity": a.severity,
                    "score": a.score,
                    "symbol": a.symbol,
                    "suggestion": a.suggestion,
                })

        return alerts[-10:]  # 只返回最近10条

    def reset(self):
        """重置检测器"""
        self.trades.clear()
        self.price_history.clear()
        self.volume_history.clear()
        self.anomalies.clear()
        self.baseline = {
            "avg_trade_amount": 0.0,
            "std_trade_amount": 0.0,
            "avg_trades_per_minute": 0.0,
            "avg_volume": 0,
            "avg_price": 0.0,
        }


# ============================================================================
#  全局单例
# ============================================================================

_anomaly_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """获取全局异常检测器单例"""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


# ============================================================================
#  命令行测试
# ============================================================================

if __name__ == "__main__":
    import random

    detector = AnomalyDetector()

    print("=" * 60)
    print("  Aurora 异常交易检测器 - 功能测试")
    print("=" * 60)

    # 模拟正常交易
    print("\n1. 模拟正常交易...")
    stocks = ["600519.SH", "000858.SZ", "601318.SH", "000333.SZ"]
    for i in range(30):
        symbol = random.choice(stocks)
        price = random.uniform(10, 200)
        volume = random.randint(100, 10000)
        amount = price * volume
        direction = random.choice(["buy", "sell"])

        anomalies = detector.feed_trade(symbol, price, volume, amount, direction)
        detector.feed_market_data(symbol, price, volume)

        if anomalies:
            for a in anomalies:
                print(f"  ⚠ [{a.severity}] {a.anomaly_type.value}: {a.symbol} - {a.suggestion[:50]}...")
        time.sleep(0.05)

    # 模拟高频刷单
    print("\n2. 模拟高频刷单攻击...")
    for i in range(10):
        anomalies = detector.feed_trade("600519.SH", 150.0, 1000, 150000, "buy", "market")
        if anomalies:
            for a in anomalies:
                print(f"  🚨 [{a.severity}] {a.anomaly_type.value}: score={a.score:.0f} - {a.suggestion[:60]}...")
        time.sleep(0.1)

    # 模拟超大单
    print("\n3. 模拟超大单...")
    anomalies = detector.feed_trade("000858.SZ", 120.0, 500000, 60000000, "buy", "market")
    if anomalies:
        for a in anomalies:
            print(f"  📊 [{a.severity}] {a.anomaly_type.value}: score={a.score:.0f} - {a.suggestion[:60]}...")

    # 打印摘要
    print("\n4. 检测摘要:")
    summary = detector.get_summary()
    print(f"  总异常数: {summary['total_anomalies']}")
    print(f"  按类型: {json.dumps(summary['recent_200']['by_type'], ensure_ascii=False)}")
    print(f"  按严重度: {json.dumps(summary['recent_200']['by_severity'], ensure_ascii=False)}")
    print(f"  统计基线: avg_amount={summary['baseline']['avg_trade_amount']:.0f}")

    alerts = detector.get_alerts("medium")
    if alerts:
        print(f"\n  需要关注的告警 ({len(alerts)}条):")
        for alert in alerts:
            print(f"    [{alert['severity']}] {alert['type']} - {alert['suggestion']}")

    print("\n" + "=" * 60)
    print("  测试完成")