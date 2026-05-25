#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常检测器 - Aurora系统自诊断组件
自动检测系统运行异常、数据异常、交易行为异常
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """系统异常检测器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.anomalies: List[Dict[str, Any]] = []
        self.thresholds = {
            "price_spike_pct": 10.0,
            "volume_spike_pct": 300.0,
            "latency_ms": 5000,
            "error_rate": 0.05,
            "memory_usage_pct": 85.0,
        }

    def detect_system_anomaly(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测系统级异常"""
        results = []
        if metrics.get("memory_usage_pct", 0) > self.thresholds["memory_usage_pct"]:
            results.append({
                "type": "high_memory",
                "severity": "warning",
                "message": f"内存使用率 {metrics['memory_usage_pct']}% 超过阈值",
                "timestamp": datetime.now().isoformat(),
            })
        if metrics.get("error_rate", 0) > self.thresholds["error_rate"]:
            results.append({
                "type": "high_error_rate",
                "severity": "critical",
                "message": f"错误率 {metrics['error_rate']} 超过阈值",
                "timestamp": datetime.now().isoformat(),
            })
        return results

    def detect_data_anomaly(self, data_point: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测数据级异常"""
        results = []
        if data_point.get("price_change_pct", 0) > self.thresholds["price_spike_pct"]:
            results.append({
                "type": "price_spike",
                "severity": "warning",
                "symbol": data_point.get("symbol"),
                "change_pct": data_point["price_change_pct"],
                "timestamp": datetime.now().isoformat(),
            })
        return results

    def get_anomaly_report(self) -> Dict[str, Any]:
        """获取异常报告"""
        return {
            "total_anomalies": len(self.anomalies),
            "anomalies": self.anomalies[-100:],
            "generated_at": datetime.now().isoformat(),
        }


__all__ = ["AnomalyDetector"]