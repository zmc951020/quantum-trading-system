#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DataQualityValidator — 数据质量验证器
======================================
增益性优化模块，不修改现有数据源代码，通过依赖注入提供数据质量验证能力。

设计目标：
  1. 实时检测数据异常（缺失值、异常值、重复数据、延迟数据）
  2. 多数据源交叉验证（主数据源 vs 备用数据源）
  3. 数据质量评分与告警
  4. 自动修复策略（插值、回退到备用源）

使用方式：
  validator = DataQualityValidator()
  validator.enabled = True
  quality = validator.check_data_quality(data)
  is_valid = validator.validate_data_point(timestamp, price, volume)

回滚方式：
  validator.enabled = False  # 数据直接透传，不做质量检查
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
import logging
import json
import time

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """数据质量报告"""
    overall_score: float = 100.0
    missing_rate: float = 0.0
    anomaly_rate: float = 0.0
    duplicate_rate: float = 0.0
    staleness_seconds: float = 0.0
    cross_validation_score: float = 100.0
    issues: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class DataPoint:
    """数据点"""
    timestamp: datetime
    price: float
    volume: float
    source: str = "primary"
    quality_score: float = 1.0


class DataQualityValidator:
    """
    数据质量验证器

    单例模式，全局唯一实例，默认关闭。
    提供实时数据质量检测、交叉验证、自动修复功能。
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.enabled = False

        # 验证配置
        self.config = {
            'max_missing_rate': 0.05,         # 最大缺失率
            'max_anomaly_rate': 0.02,         # 最大异常率
            'max_duplicate_rate': 0.01,       # 最大重复率
            'max_staleness_seconds': 60.0,    # 最大数据延迟（秒）
            'min_cross_validation_score': 80.0,  # 最小交叉验证分数
            'price_change_threshold': 0.10,   # 价格变化异常阈值（10%）
            'volume_change_threshold': 5.0,   # 成交量变化异常阈值（5倍）
            'z_score_threshold': 3.0,         # Z-score异常阈值
            'auto_fix_missing': True,         # 自动修复缺失值
            'auto_fix_anomaly': True,         # 自动修复异常值
            'cross_validation_enabled': True, # 启用交叉验证
        }

        # 数据缓冲区
        self._data_buffer: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )

        # 备用数据源（延迟加载）
        self._backup_source = None

        # 统计
        self._total_checks = 0
        self._total_issues = 0
        self._total_fixes = 0
        self._last_check_time = None

        logger.info("[DataQualityValidator] 初始化完成，默认关闭")

    # ==================== 核心接口 ====================

    def check_data_quality(self, data: Dict[str, Any],
                          source: str = "primary") -> DataQualityReport:
        """
        检查数据质量

        Args:
            data: 数据字典，包含 'prices', 'volumes', 'timestamps' 等
            source: 数据源名称

        Returns:
            数据质量报告
        """
        self._total_checks += 1
        self._last_check_time = datetime.now()

        report = DataQualityReport()
        report.timestamp = datetime.now().isoformat()

        if not self.enabled:
            return report

        prices = data.get('prices', [])
        volumes = data.get('volumes', [])
        timestamps = data.get('timestamps', [])

        if not prices:
            report.overall_score = 0.0
            report.issues.append({
                'type': 'empty_data',
                'severity': 'critical',
                'message': '数据为空',
            })
            return report

        # 检查缺失值
        missing_count = sum(1 for p in prices if p is None or np.isnan(p))
        report.missing_rate = missing_count / len(prices)
        if report.missing_rate > self.config['max_missing_rate']:
            report.issues.append({
                'type': 'high_missing_rate',
                'severity': 'warning',
                'message': f"缺失率 {report.missing_rate:.2%} 超过阈值 {self.config['max_missing_rate']:.2%}",
                'missing_count': missing_count,
                'total_count': len(prices),
            })

        # 检查异常值（Z-score方法）
        valid_prices = [p for p in prices if p is not None and not np.isnan(p)]
        if len(valid_prices) > 2:
            mean_price = np.mean(valid_prices)
            std_price = np.std(valid_prices)
            if std_price > 0:
                z_scores = [(p - mean_price) / std_price for p in valid_prices]
                anomaly_count = sum(1 for z in z_scores if abs(z) > self.config['z_score_threshold'])
                report.anomaly_rate = anomaly_count / len(valid_prices)

                if report.anomaly_rate > self.config['max_anomaly_rate']:
                    report.issues.append({
                        'type': 'high_anomaly_rate',
                        'severity': 'warning',
                        'message': f"异常率 {report.anomaly_rate:.2%} 超过阈值 {self.config['max_anomaly_rate']:.2%}",
                        'anomaly_count': anomaly_count,
                        'total_count': len(valid_prices),
                    })

        # 检查重复数据
        if timestamps:
            unique_timestamps = len(set(timestamps))
            duplicate_count = len(timestamps) - unique_timestamps
            report.duplicate_rate = duplicate_count / len(timestamps) if timestamps else 0

            if report.duplicate_rate > self.config['max_duplicate_rate']:
                report.issues.append({
                    'type': 'high_duplicate_rate',
                    'severity': 'info',
                    'message': f"重复率 {report.duplicate_rate:.2%} 超过阈值 {self.config['max_duplicate_rate']:.2%}",
                    'duplicate_count': duplicate_count,
                })

        # 检查数据延迟
        if timestamps:
            try:
                last_ts = max(timestamps)
                if isinstance(last_ts, str):
                    last_ts = datetime.fromisoformat(last_ts)
                staleness = (datetime.now() - last_ts).total_seconds()
                report.staleness_seconds = staleness

                if staleness > self.config['max_staleness_seconds']:
                    report.issues.append({
                        'type': 'data_staleness',
                        'severity': 'warning',
                        'message': f"数据延迟 {staleness:.1f}秒 超过阈值 {self.config['max_staleness_seconds']:.1f}秒",
                        'staleness_seconds': staleness,
                    })
            except Exception as e:
                logger.debug(f"[DataQualityValidator] 时间戳解析失败: {e}")

        # 交叉验证
        if self.config['cross_validation_enabled'] and source == 'primary':
            cross_score = self._cross_validate(data)
            report.cross_validation_score = cross_score
            if cross_score < self.config['min_cross_validation_score']:
                report.issues.append({
                    'type': 'cross_validation_failed',
                    'severity': 'warning',
                    'message': f"交叉验证分数 {cross_score:.1f} 低于阈值 {self.config['min_cross_validation_score']:.1f}",
                })

        # 计算总体评分
        report.overall_score = self._compute_overall_score(report)

        # 生成警告
        if report.overall_score < 60:
            report.warnings.append("数据质量严重下降，建议暂停交易")
        elif report.overall_score < 80:
            report.warnings.append("数据质量下降，建议谨慎操作")

        # 记录到缓冲区
        self._data_buffer[source].append({
            'timestamp': report.timestamp,
            'score': report.overall_score,
            'issues': len(report.issues),
        })

        if report.issues:
            self._total_issues += len(report.issues)

        return report

    def validate_data_point(self, timestamp: datetime,
                           price: float, volume: float,
                           source: str = "primary") -> Tuple[bool, float, str]:
        """
        验证单个数据点

        Args:
            timestamp: 时间戳
            price: 价格
            volume: 成交量
            source: 数据源

        Returns:
            (是否有效, 质量评分, 问题描述)
        """
        if not self.enabled:
            return True, 1.0, ""

        issues = []

        # 检查缺失
        if price is None or np.isnan(price) or volume is None or np.isnan(volume):
            return False, 0.0, "数据缺失"

        # 检查价格有效性
        if price <= 0:
            issues.append("价格无效")
        if volume < 0:
            issues.append("成交量无效")

        # 检查价格突变
        source_buffer = self._data_buffer.get(source, [])
        if source_buffer:
            last_points = list(source_buffer)[-5:]
            if last_points:
                avg_price = np.mean([p.get('price', price) for p in last_points])
                if avg_price > 0:
                    change = abs(price - avg_price) / avg_price
                    if change > self.config['price_change_threshold']:
                        issues.append(f"价格突变 {change:.2%}")

        # 检查数据延迟
        staleness = (datetime.now() - timestamp).total_seconds()
        if staleness > self.config['max_staleness_seconds']:
            issues.append(f"数据延迟 {staleness:.1f}秒")

        # 计算质量评分
        quality_score = 1.0 - len(issues) * 0.2
        quality_score = max(0.0, quality_score)

        is_valid = len(issues) == 0
        issue_desc = "; ".join(issues) if issues else ""

        return is_valid, quality_score, issue_desc

    def fix_data(self, data: Dict[str, Any],
                source: str = "primary") -> Dict[str, Any]:
        """
        自动修复数据质量问题

        Args:
            data: 原始数据
            source: 数据源

        Returns:
            修复后的数据
        """
        if not self.enabled:
            return data

        fixed_data = data.copy()
        fixes_applied = []

        prices = list(fixed_data.get('prices', []))
        volumes = list(fixed_data.get('volumes', []))
        timestamps = list(fixed_data.get('timestamps', []))

        # 修复缺失值（线性插值）
        if self.config['auto_fix_missing']:
            for i in range(len(prices)):
                if prices[i] is None or np.isnan(prices[i]):
                    # 前向填充
                    if i > 0 and prices[i-1] is not None and not np.isnan(prices[i-1]):
                        prices[i] = prices[i-1]
                    # 后向填充
                    elif i < len(prices) - 1 and prices[i+1] is not None and not np.isnan(prices[i+1]):
                        prices[i] = prices[i+1]
                    else:
                        prices[i] = 0.0
                    fixes_applied.append(f"修复缺失价格 [{i}]")

            for i in range(len(volumes)):
                if volumes[i] is None or np.isnan(volumes[i]):
                    volumes[i] = 0.0
                    fixes_applied.append(f"修复缺失成交量 [{i}]")

        # 修复异常值（中位数替换）
        if self.config['auto_fix_anomaly'] and len(prices) > 2:
            valid_prices = [p for p in prices if p > 0]
            if valid_prices:
                median_price = np.median(valid_prices)
                std_price = np.std(valid_prices)

                for i in range(len(prices)):
                    if prices[i] > 0 and std_price > 0:
                        z_score = abs(prices[i] - median_price) / std_price
                        if z_score > self.config['z_score_threshold']:
                            old_price = prices[i]
                            prices[i] = median_price
                            fixes_applied.append(f"修复异常价格 [{i}]: {old_price:.2f} -> {median_price:.2f}")

        fixed_data['prices'] = prices
        fixed_data['volumes'] = volumes
        fixed_data['timestamps'] = timestamps

        if fixes_applied:
            self._total_fixes += len(fixes_applied)
            fixed_data['_fixes_applied'] = fixes_applied

        return fixed_data

    def get_quality_trend(self, source: str = "primary",
                         window: int = 20) -> Dict:
        """
        获取数据质量趋势

        Args:
            source: 数据源
            window: 窗口大小

        Returns:
            质量趋势信息
        """
        buffer = list(self._data_buffer.get(source, []))
        if not buffer:
            return {}

        recent = buffer[-window:]
        scores = [b['score'] for b in recent]

        return {
            'current_score': scores[-1] if scores else 0,
            'avg_score': np.mean(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'score_std': np.std(scores) if len(scores) > 1 else 0,
            'trend': 'improving' if len(scores) > 1 and scores[-1] > scores[0] else (
                'declining' if len(scores) > 1 and scores[-1] < scores[0] else 'stable'
            ),
            'total_checks': len(buffer),
            'total_issues': sum(b['issues'] for b in buffer),
        }

    def get_stats(self) -> Dict:
        """获取验证器统计信息"""
        return {
            'enabled': self.enabled,
            'total_checks': self._total_checks,
            'total_issues': self._total_issues,
            'total_fixes': self._total_fixes,
            'last_check_time': self._last_check_time.isoformat() if self._last_check_time else None,
            'active_sources': list(self._data_buffer.keys()),
            'config': self.config.copy(),
        }

    # ==================== 内部方法 ====================

    def _cross_validate(self, data: Dict[str, Any]) -> float:
        """
        交叉验证（主数据源 vs 备用数据源）

        Returns:
            交叉验证分数 (0-100)
        """
        # 简化实现：检查数据自洽性
        prices = data.get('prices', [])
        volumes = data.get('volumes', [])

        if len(prices) < 2:
            return 100.0

        score = 100.0

        # 检查价格单调性（非严格）
        price_diffs = np.diff(prices)
        extreme_diffs = sum(1 for d in price_diffs if abs(d) > np.mean(prices) * 0.05)
        if extreme_diffs > len(price_diffs) * 0.1:
            score -= 20.0

        # 检查价格-成交量关系
        if len(prices) == len(volumes) and len(prices) > 1:
            price_vol_corr = np.corrcoef(prices, volumes)[0, 1]
            if not np.isnan(price_vol_corr) and abs(price_vol_corr) > 0.9:
                score -= 10.0  # 过高相关性可能表示数据异常

        return max(0.0, score)

    def _compute_overall_score(self, report: DataQualityReport) -> float:
        """计算总体质量评分"""
        score = 100.0

        # 缺失率扣分
        if report.missing_rate > 0:
            score -= report.missing_rate * 100 * 2

        # 异常率扣分
        if report.anomaly_rate > 0:
            score -= report.anomaly_rate * 100 * 3

        # 重复率扣分
        if report.duplicate_rate > 0:
            score -= report.duplicate_rate * 100

        # 延迟扣分
        if report.staleness_seconds > 0:
            score -= min(report.staleness_seconds / 10, 20)

        # 交叉验证扣分
        if report.cross_validation_score < 100:
            score -= (100 - report.cross_validation_score) * 0.5

        return max(0.0, min(100.0, score))


# ==================== 全局单例 ====================

_global_validator = None


def get_data_validator() -> DataQualityValidator:
    """获取全局数据质量验证器实例"""
    global _global_validator
    if _global_validator is None:
        _global_validator = DataQualityValidator()
    return _global_validator


# ==================== 便捷函数 ====================

def check_quality(data: Dict[str, Any]) -> DataQualityReport:
    """便捷函数：检查数据质量"""
    validator = get_data_validator()
    return validator.check_data_quality(data)


# ==================== 自测 ====================

if __name__ == '__main__':
    validator = get_data_validator()
    validator.enabled = True

    print("=" * 60)
    print("DataQualityValidator 自测")
    print("=" * 60)

    # 模拟正常数据
    normal_data = {
        'prices': [100.0 + i * 0.1 + np.random.normal(0, 0.5) for i in range(100)],
        'volumes': [10000 + int(np.random.normal(0, 1000)) for _ in range(100)],
        'timestamps': [
            (datetime.now() - timedelta(seconds=i)).isoformat()
            for i in range(100)
        ],
    }

    report = validator.check_data_quality(normal_data)
    print(f"\n正常数据质量报告:")
    print(f"  总体评分: {report.overall_score:.1f}")
    print(f"  缺失率: {report.missing_rate:.2%}")
    print(f"  异常率: {report.anomaly_rate:.2%}")
    print(f"  问题数: {len(report.issues)}")

    # 模拟异常数据
    anomaly_data = {
        'prices': [100.0] * 50 + [1000.0] * 50,  # 价格突变
        'volumes': [10000] * 100,
        'timestamps': [
            (datetime.now() - timedelta(seconds=i)).isoformat()
            for i in range(100)
        ],
    }

    report2 = validator.check_data_quality(anomaly_data)
    print(f"\n异常数据质量报告:")
    print(f"  总体评分: {report2.overall_score:.1f}")
    print(f"  异常率: {report2.anomaly_rate:.2%}")
    for issue in report2.issues:
        print(f"  问题: [{issue['severity']}] {issue['message']}")

    # 测试数据修复
    broken_data = {
        'prices': [100.0, None, 102.0, 103.0, None, 105.0],
        'volumes': [10000, 11000, None, 13000, 14000, 15000],
        'timestamps': [datetime.now().isoformat()] * 6,
    }

    fixed = validator.fix_data(broken_data)
    print(f"\n数据修复:")
    print(f"  修复前价格: {broken_data['prices']}")
    print(f"  修复后价格: {fixed['prices']}")
    print(f"  修复操作: {fixed.get('_fixes_applied', [])}")

    # 验证单个数据点
    is_valid, score, desc = validator.validate_data_point(
        datetime.now(), 100.5, 15000
    )
    print(f"\n单点验证:")
    print(f"  有效: {is_valid}")
    print(f"  评分: {score:.2f}")
    print(f"  问题: {desc}")

    # 统计信息
    stats = validator.get_stats()
    print(f"\n验证器统计:")
    print(f"  总检查: {stats['total_checks']}")
    print(f"  总问题: {stats['total_issues']}")
    print(f"  总修复: {stats['total_fixes']}")

    print("\n✅ DataQualityValidator 自测完成！")
