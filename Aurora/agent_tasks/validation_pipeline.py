#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ValidationPipeline — 智能体专家团队验证管道（金融级）
====================================================
增益性优化模块，不修改现有策略代码，通过依赖注入提供9步闭环验证能力。

设计目标：
  1. 数据质量验证（DataQualityValidator）
  2. 参数边界检查
  3. 回测结果验证
  4. 过拟合检测
  5. 蒙特卡洛模拟
  6. VaR风险验证
  7. 压力测试
  8. 风控审计（UnifiedRiskController）
  9. 委员会投票决策

金融级特性：
  - 完整的日志记录与持久化
  - 验证报告数据库存储
  - 重试机制与熔断保护
  - 性能指标监控
  - 并发安全支持
  - 置信区间报告
  - 极端市场情景测试

使用方式：
  pipeline = ValidationPipeline()
  pipeline.enabled = True
  result = pipeline.validate_strategy('StrategyName', params, backtest_results)

回滚方式：
  pipeline.enabled = False  # 跳过所有验证，直接返回通过
"""

import json
import time
import hashlib
import logging
import traceback
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== 枚举与常量 ====================

class ValidationSeverity(Enum):
    """验证严重级别"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ValidationStatus(Enum):
    """验证状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"


# ==================== 数据类 ====================

@dataclass
class ValidationStep:
    """单个验证步骤"""
    name: str
    status: ValidationStatus = ValidationStatus.PENDING
    score: float = 0.0
    weight: float = 1.0
    details: Dict = field(default_factory=dict)
    issues: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    retry_count: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'status': self.status.value,
            'score': self.score,
            'weight': self.weight,
            'details': self.details,
            'issues': self.issues,
            'warnings': self.warnings,
            'duration_ms': self.duration_ms,
            'retry_count': self.retry_count,
        }


@dataclass
class ValidationReport:
    """完整验证报告"""
    strategy_name: str
    params_hash: str
    timestamp: str
    overall_score: float = 0.0
    passed: bool = False
    steps: List[ValidationStep] = field(default_factory=list)
    committee_vote: Dict = field(default_factory=dict)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    total_duration_ms: float = 0.0
    version: str = "2.0.0"

    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'params_hash': self.params_hash,
            'timestamp': self.timestamp,
            'overall_score': self.overall_score,
            'passed': self.passed,
            'steps': [s.to_dict() for s in self.steps],
            'committee_vote': self.committee_vote,
            'summary': self.summary,
            'recommendations': self.recommendations,
            'total_duration_ms': self.total_duration_ms,
            'version': self.version,
        }


@dataclass
class CommitteeVote:
    """委员会投票结果"""
    total_members: int = 4
    approvals: int = 0
    rejections: int = 0
    abstentions: int = 0
    votes: List[Dict] = field(default_factory=list)
    passed: bool = False
    min_approvals: int = 4  # 金融级要求全票通过

    def to_dict(self) -> Dict:
        return {
            'total_members': self.total_members,
            'approvals': self.approvals,
            'rejections': self.rejections,
            'abstentions': self.abstentions,
            'votes': self.votes,
            'passed': self.passed,
            'min_approvals': self.min_approvals,
        }


# ==================== 验证管道主类 ====================

class ValidationPipeline:
    """
    智能体专家团队验证管道

    单例模式，全局唯一实例，默认关闭。
    提供9步闭环验证流程，支持并发执行、重试机制、熔断保护。
    """

    _instance = None
    _initialized = False

    # 金融级验证阈值
    PASS_THRESHOLD = 0.90       # 综合评分 >= 0.90 通过
    BACKTEST_PASS_THRESHOLD = 0.90  # 回测评分 >= 0.90
    OVERFIT_PASS_THRESHOLD = 0.85  # 过拟合检测 >= 0.85
    MONTE_CARLO_PASS_THRESHOLD = 0.80  # 蒙特卡洛 >= 0.80
    VAR_PASS_THRESHOLD = 0.85   # VaR验证 >= 0.85
    STRESS_TEST_PASS_THRESHOLD = 0.80  # 压力测试 >= 0.80
    DATA_QUALITY_PASS_THRESHOLD = 0.90  # 数据质量 >= 0.90
    RISK_AUDIT_PASS_THRESHOLD = 0.85   # 风控审计 >= 0.85
    PARAM_BOUNDARY_PASS_THRESHOLD = 0.90  # 参数边界 >= 0.90

    # 金融级委员会配置
    COMMITTEE_MIN_APPROVALS = 4  # 4票全票通过
    COMMITTEE_TOTAL_MEMBERS = 4

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 100

    # 超时配置（毫秒）
    STEP_TIMEOUT_MS = 30000

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
            'max_retries': self.MAX_RETRIES,
            'retry_delay_ms': self.RETRY_DELAY_MS,
            'step_timeout_ms': self.STEP_TIMEOUT_MS,
            'pass_threshold': self.PASS_THRESHOLD,
            'committee_min_approvals': self.COMMITTEE_MIN_APPROVALS,
            'parallel_execution': True,       # 启用并行执行
            'persist_reports': True,           # 持久化验证报告
            'enable_circuit_breaker': True,    # 启用熔断保护
            'enable_monte_carlo': True,        # 启用蒙特卡洛模拟
            'enable_var_validation': True,     # 启用VaR验证
            'enable_stress_test': True,        # 启用压力测试
            'enable_confidence_interval': True, # 启用置信区间报告
            'monte_carlo_simulations': 10000,  # 蒙特卡洛模拟次数
            'stress_test_scenarios': [         # 压力测试场景
                {'name': '市场崩盘', 'price_drop': -0.30, 'vol_spike': 3.0},
                {'name': '流动性危机', 'price_drop': -0.15, 'vol_spike': 2.0},
                {'name': '黑天鹅事件', 'price_drop': -0.50, 'vol_spike': 5.0},
                {'name': '温和回调', 'price_drop': -0.10, 'vol_spike': 1.5},
                {'name': '极端波动', 'price_drop': -0.25, 'vol_spike': 4.0},
            ],
            'var_confidence_levels': [0.95, 0.99],  # VaR置信度
        }

        # 依赖模块（延迟加载）
        self._data_validator = None
        self._risk_controller = None
        self._db_manager = None

        # 验证历史
        self._validation_history: List[ValidationReport] = []
        self._circuit_breaker_count = 0
        self._circuit_breaker_threshold = 5  # 连续5次失败触发熔断
        self._circuit_breaker_open = False
        self._circuit_breaker_reset_at = None

        # 性能统计
        self._total_validations = 0
        self._total_passed = 0
        self._total_failed = 0
        self._total_duration_ms = 0.0
        self._step_performance: Dict[str, List[float]] = defaultdict(list)

        # 报告存储路径
        self._report_dir = Path("reports/validation")
        self._report_dir.mkdir(parents=True, exist_ok=True)

        # 日志文件处理器
        self._setup_file_logging()

        logger.info("[ValidationPipeline] 初始化完成，默认关闭")
        logger.info(f"[ValidationPipeline] 金融级验证阈值: 综合>={self.PASS_THRESHOLD}, "
                    f"回测>={self.BACKTEST_PASS_THRESHOLD}, "
                    f"过拟合>={self.OVERFIT_PASS_THRESHOLD}, "
                    f"委员会全票通过")

    def _setup_file_logging(self):
        """设置文件日志处理器"""
        try:
            log_dir = Path("logs/validation")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"validation_{datetime.now().strftime('%Y%m%d')}.log"

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"[ValidationPipeline] 文件日志设置失败: {e}")

    # ==================== 属性：延迟加载依赖 ====================

    @property
    def data_validator(self):
        """延迟加载数据质量验证器"""
        if self._data_validator is None:
            try:
                from utils.data_quality_validator import DataQualityValidator
                self._data_validator = DataQualityValidator()
            except Exception as e:
                logger.warning(f"[ValidationPipeline] DataQualityValidator 加载失败: {e}")
        return self._data_validator

    @property
    def risk_controller(self):
        """延迟加载风险控制器"""
        if self._risk_controller is None:
            try:
                from utils.unified_risk_controller import get_risk_controller
                self._risk_controller = get_risk_controller()
            except Exception as e:
                logger.warning(f"[ValidationPipeline] UnifiedRiskController 加载失败: {e}")
        return self._risk_controller

    @property
    def db_manager(self):
        """延迟加载数据库管理器"""
        if self._db_manager is None:
            try:
                from utils.database_manager import DatabaseManager
                self._db_manager = DatabaseManager()
            except Exception as e:
                logger.debug(f"[ValidationPipeline] DatabaseManager 加载失败: {e}")
        return self._db_manager

    # ==================== 核心验证接口 ====================

    def validate_strategy(self, strategy_name: str,
                         params: Dict[str, Any],
                         backtest_results: Dict[str, Any] = None,
                         market_data: Dict[str, Any] = None) -> ValidationReport:
        """
        执行完整的9步闭环验证

        Args:
            strategy_name: 策略名称
            params: 策略参数字典
            backtest_results: 回测结果字典（可选）
            market_data: 市场数据字典（可选）

        Returns:
            验证报告
        """
        self._total_validations += 1
        start_time = time.time()

        # 检查熔断状态
        if self._check_circuit_breaker():
            report = self._create_failed_report(
                strategy_name, params,
                "熔断保护已激活，验证管道暂时关闭"
            )
            return report

        # 生成参数哈希
        params_hash = self._hash_params(params)

        # 创建验证报告
        report = ValidationReport(
            strategy_name=strategy_name,
            params_hash=params_hash,
            timestamp=datetime.now().isoformat(),
        )

        # 如果未启用，直接返回通过
        if not self.enabled:
            report.overall_score = 1.0
            report.passed = True
            report.summary = "验证管道未启用，跳过所有验证"
            return report

        logger.info(f"[ValidationPipeline] 开始验证策略: {strategy_name}")

        try:
            # 定义验证步骤
            steps = [
                self._step_data_quality,
                self._step_param_boundary,
                self._step_backtest_validation,
                self._step_overfit_detection,
                self._step_monte_carlo_simulation,
                self._step_var_validation,
                self._step_stress_test,
                self._step_risk_audit,
                self._step_committee_vote,
            ]

            # 执行验证步骤
            if self.config['parallel_execution'] and len(steps) > 3:
                report.steps = self._execute_steps_parallel(
                    steps, strategy_name, params, backtest_results, market_data
                )
            else:
                report.steps = self._execute_steps_sequential(
                    steps, strategy_name, params, backtest_results, market_data
                )

            # 计算综合评分
            report.overall_score = self._calculate_overall_score(report.steps)

            # 判断是否通过
            report.passed = (
                report.overall_score >= self.config['pass_threshold'] and
                all(s.status == ValidationStatus.PASSED
                    for s in report.steps
                    if s.status != ValidationStatus.SKIPPED)
            )

            # 生成摘要和建议
            report.summary = self._generate_summary(report)
            report.recommendations = self._generate_recommendations(report.steps)

            # 记录性能
            report.total_duration_ms = (time.time() - start_time) * 1000
            self._total_duration_ms += report.total_duration_ms

            # 更新统计
            if report.passed:
                self._total_passed += 1
                self._circuit_breaker_count = 0
            else:
                self._total_failed += 1
                self._circuit_breaker_count += 1

            # 持久化报告
            if self.config['persist_reports']:
                self._persist_report(report)

            # 保存到历史
            self._validation_history.append(report)
            if len(self._validation_history) > 100:
                self._validation_history.pop(0)

            logger.info(f"[ValidationPipeline] 策略 {strategy_name} 验证完成: "
                       f"评分={report.overall_score:.4f}, "
                       f"通过={report.passed}, "
                       f"耗时={report.total_duration_ms:.1f}ms")

        except Exception as e:
            logger.error(f"[ValidationPipeline] 验证异常: {e}\n{traceback.format_exc()}")
            report.overall_score = 0.0
            report.passed = False
            report.summary = f"验证过程发生异常: {str(e)}"
            report.total_duration_ms = (time.time() - start_time) * 1000

        return report

    # ==================== 验证步骤执行 ====================

    def _execute_steps_sequential(self, steps: List[Callable],
                                  strategy_name: str,
                                  params: Dict,
                                  backtest_results: Dict,
                                  market_data: Dict) -> List[ValidationStep]:
        """顺序执行验证步骤"""
        results = []
        for step_func in steps:
            step = self._execute_step_with_retry(
                step_func, strategy_name, params, backtest_results, market_data
            )
            results.append(step)

            # 熔断检查：关键步骤失败则停止
            if (self.config['enable_circuit_breaker'] and
                    step.status == ValidationStatus.FAILED and
                    hasattr(step, 'severity') and
                    step.severity == ValidationSeverity.CRITICAL):
                logger.warning(f"[ValidationPipeline] 关键步骤 {step.name} 失败，触发熔断")
                break

        return results

    def _execute_steps_parallel(self, steps: List[Callable],
                                strategy_name: str,
                                params: Dict,
                                backtest_results: Dict,
                                market_data: Dict) -> List[ValidationStep]:
        """并行执行验证步骤"""
        results = []
        # 委员会投票必须最后执行
        committee_step = steps[-1]
        parallel_steps = steps[:-1]

        with ThreadPoolExecutor(max_workers=min(len(parallel_steps), 4)) as executor:
            future_map = {}
            for step_func in parallel_steps:
                future = executor.submit(
                    self._execute_step_with_retry,
                    step_func, strategy_name, params, backtest_results, market_data
                )
                future_map[future] = step_func

            for future in as_completed(future_map):
                try:
                    step = future.result(timeout=self.config['step_timeout_ms'] / 1000)
                    results.append(step)
                except Exception as e:
                    step_func = future_map[future]
                    step = ValidationStep(name=step_func.__name__)
                    step.status = ValidationStatus.ERROR
                    step.details = {'error': str(e)}
                    results.append(step)

        # 按原始顺序排序
        step_order = {f.__name__: i for i, f in enumerate(parallel_steps)}
        results.sort(key=lambda s: step_order.get(s.name, 999))

        # 执行委员会投票
        committee_result = self._execute_step_with_retry(
            committee_step, strategy_name, params, backtest_results, market_data
        )
        results.append(committee_result)

        return results

    def _execute_step_with_retry(self, step_func: Callable,
                                 strategy_name: str,
                                 params: Dict,
                                 backtest_results: Dict,
                                 market_data: Dict) -> ValidationStep:
        """带重试机制的步骤执行"""
        max_retries = self.config['max_retries']
        retry_delay = self.config['retry_delay_ms'] / 1000

        for attempt in range(max_retries + 1):
            try:
                step = step_func(strategy_name, params, backtest_results, market_data)
                step.retry_count = attempt
                return step
            except Exception as e:
                logger.warning(f"[ValidationPipeline] 步骤 {step_func.__name__} "
                             f"第{attempt + 1}次执行失败: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    step = ValidationStep(name=step_func.__name__)
                    step.status = ValidationStatus.ERROR
                    step.details = {'error': str(e), 'traceback': traceback.format_exc()}
                    step.retry_count = attempt
                    return step

    # ==================== 步骤1: 数据质量验证 ====================

    def _step_data_quality(self, strategy_name: str,
                          params: Dict,
                          backtest_results: Dict,
                          market_data: Dict) -> ValidationStep:
        """步骤1: 数据质量验证"""
        step = ValidationStep(name="数据质量验证", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 1.0

        if self.data_validator and self.data_validator.enabled:
            # 使用数据质量验证器
            data_for_check = market_data or backtest_results or {}
            quality_report = self.data_validator.check_data_quality(data_for_check)

            score = quality_report.overall_score / 100.0
            issues = quality_report.issues

            step.details = {
                'quality_score': quality_report.overall_score,
                'missing_rate': quality_report.missing_rate,
                'anomaly_rate': quality_report.anomaly_rate,
                'duplicate_rate': quality_report.duplicate_rate,
                'staleness_seconds': quality_report.staleness_seconds,
                'cross_validation_score': quality_report.cross_validation_score,
            }
        else:
            # 基础数据检查
            if backtest_results:
                prices = backtest_results.get('prices', [])
                volumes = backtest_results.get('volumes', [])
                returns = backtest_results.get('returns', [])

                if not prices:
                    issues.append({'type': 'empty_prices', 'severity': 'critical',
                                  'message': '回测结果缺少价格数据'})
                    score = 0.0
                elif len(prices) < 20:
                    issues.append({'type': 'insufficient_data', 'severity': 'high',
                                  'message': f'数据点不足: {len(prices)} < 20'})
                    score = max(score - 0.3, 0.0)

                if volumes and len(volumes) > 0:
                    zero_volumes = sum(1 for v in volumes if v == 0)
                    if zero_volumes > len(volumes) * 0.1:
                        issues.append({'type': 'high_zero_volume', 'severity': 'medium',
                                      'message': f'零成交量比例过高: {zero_volumes}/{len(volumes)}'})
                        score = max(score - 0.2, 0.0)

                if returns and len(returns) > 1:
                    # 检查异常回报率
                    returns_arr = np.array(returns)
                    mean = np.mean(returns_arr)
                    std = np.std(returns_arr)
                    if std > 0:
                        z_scores = np.abs((returns_arr - mean) / std)
                        extreme_count = np.sum(z_scores > 3.0)
                        if extreme_count > len(returns) * 0.02:
                            issues.append({'type': 'extreme_returns', 'severity': 'medium',
                                          'message': f'异常回报率比例过高: {extreme_count}/{len(returns)}'})
                            score = max(score - 0.15, 0.0)

        step.score = score
        step.issues = issues
        step.status = ValidationStatus.PASSED if score >= self.DATA_QUALITY_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤2: 参数边界检查 ====================

    def _step_param_boundary(self, strategy_name: str,
                            params: Dict,
                            backtest_results: Dict,
                            market_data: Dict) -> ValidationStep:
        """步骤2: 参数边界检查"""
        step = ValidationStep(name="参数边界检查", weight=1.0)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        warnings_list = []
        score = 1.0

        if not params:
            issues.append({'type': 'empty_params', 'severity': 'critical',
                          'message': '参数字典为空'})
            score = 0.0
        else:
            # 检查数值参数范围
            numeric_params = {k: v for k, v in params.items()
                            if isinstance(v, (int, float)) and not isinstance(v, bool)}

            if numeric_params:
                # 检查负值
                negative_params = {k: v for k, v in numeric_params.items() if v < 0}
                if negative_params:
                    issues.append({'type': 'negative_params', 'severity': 'high',
                                  'message': f'存在负值参数: {negative_params}'})
                    score = max(score - 0.3, 0.0)

                # 检查零值
                zero_params = {k: v for k, v in numeric_params.items() if v == 0}
                if zero_params:
                    warnings_list.append(f'存在零值参数: {list(zero_params.keys())}')

                # 检查极端值
                extreme_params = {k: v for k, v in numeric_params.items()
                                if isinstance(v, (int, float)) and abs(v) > 1e6}
                if extreme_params:
                    issues.append({'type': 'extreme_values', 'severity': 'high',
                                  'message': f'存在极端值参数: {extreme_params}'})
                    score = max(score - 0.3, 0.0)

                # 检查概率参数（0-1范围）
                prob_params = {k: v for k, v in numeric_params.items()
                             if 'rate' in k.lower() or 'ratio' in k.lower()
                             or 'pct' in k.lower() or 'prob' in k.lower()
                             or 'threshold' in k.lower()}
                for k, v in prob_params.items():
                    if not (0 <= v <= 1):
                        issues.append({'type': 'invalid_probability', 'severity': 'medium',
                                      'message': f'概率参数 {k}={v} 不在 [0,1] 范围内'})
                        score = max(score - 0.15, 0.0)

            # 检查字符串参数
            str_params = {k: v for k, v in params.items() if isinstance(v, str)}
            for k, v in str_params.items():
                if not v or v.strip() == '':
                    warnings_list.append(f'字符串参数 {k} 为空')

            # 检查列表参数
            list_params = {k: v for k, v in params.items() if isinstance(v, (list, tuple))}
            for k, v in list_params.items():
                if len(v) == 0:
                    warnings_list.append(f'列表参数 {k} 为空')
                elif len(v) > 1000:
                    warnings_list.append(f'列表参数 {k} 过长: {len(v)} 个元素')

        step.score = score
        step.issues = issues
        step.warnings = warnings_list
        step.details = {
            'total_params': len(params),
            'numeric_params': len([v for v in params.values()
                                  if isinstance(v, (int, float)) and not isinstance(v, bool)]),
            'string_params': len([v for v in params.values() if isinstance(v, str)]),
            'list_params': len([v for v in params.values() if isinstance(v, (list, tuple))]),
        }
        step.status = ValidationStatus.PASSED if score >= self.PARAM_BOUNDARY_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤3: 回测结果验证 ====================

    def _step_backtest_validation(self, strategy_name: str,
                                 params: Dict,
                                 backtest_results: Dict,
                                 market_data: Dict) -> ValidationStep:
        """步骤3: 回测结果验证"""
        step = ValidationStep(name="回测结果验证", weight=2.0)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 0.0

        if not backtest_results:
            issues.append({'type': 'no_backtest_data', 'severity': 'critical',
                          'message': '缺少回测结果数据'})
            step.score = 0.0
            step.issues = issues
            step.status = ValidationStatus.FAILED
            step.duration_ms = (time.time() - step_start) * 1000
            step.completed_at = datetime.now().isoformat()
            return step

        # 提取关键指标
        total_return = backtest_results.get('total_return',
                         backtest_results.get('total_return_pct', 0))
        sharpe_ratio = backtest_results.get('sharpe_ratio', 0)
        max_drawdown = backtest_results.get('max_drawdown', 0)
        win_rate = backtest_results.get('win_rate', 0)
        total_trades = backtest_results.get('total_trades', 0)
        profit_factor = backtest_results.get('profit_factor', 0)
        calmar_ratio = backtest_results.get('calmar_ratio', 0)
        sortino_ratio = backtest_results.get('sortino_ratio', 0)

        # 评分计算
        score_components = []

        # 1. 总收益率评分
        if total_return > 0:
            return_score = min(total_return / 0.5, 1.0)  # 50%收益为满分
        else:
            return_score = 0.0
            issues.append({'type': 'negative_return', 'severity': 'critical',
                          'message': f'总收益率为负: {total_return:.2%}'})
        score_components.append(('total_return', return_score, 0.25))

        # 2. 夏普比率评分
        if sharpe_ratio >= 2.0:
            sharpe_score = 1.0
        elif sharpe_ratio >= 1.0:
            sharpe_score = 0.8
        elif sharpe_ratio >= 0.5:
            sharpe_score = 0.5
        elif sharpe_ratio > 0:
            sharpe_score = 0.3
        else:
            sharpe_score = 0.0
            issues.append({'type': 'low_sharpe', 'severity': 'high',
                          'message': f'夏普比率过低: {sharpe_ratio:.2f}'})
        score_components.append(('sharpe_ratio', sharpe_score, 0.20))

        # 3. 最大回撤评分
        if max_drawdown <= 0.05:
            dd_score = 1.0
        elif max_drawdown <= 0.10:
            dd_score = 0.8
        elif max_drawdown <= 0.20:
            dd_score = 0.5
        elif max_drawdown <= 0.30:
            dd_score = 0.3
        else:
            dd_score = 0.0
            issues.append({'type': 'high_drawdown', 'severity': 'high',
                          'message': f'最大回撤过高: {max_drawdown:.2%}'})
        score_components.append(('max_drawdown', dd_score, 0.20))

        # 4. 胜率评分
        if win_rate >= 0.60:
            wr_score = 1.0
        elif win_rate >= 0.50:
            wr_score = 0.8
        elif win_rate >= 0.40:
            wr_score = 0.5
        elif win_rate >= 0.30:
            wr_score = 0.3
        else:
            wr_score = 0.0
            issues.append({'type': 'low_win_rate', 'severity': 'medium',
                          'message': f'胜率过低: {win_rate:.2%}'})
        score_components.append(('win_rate', wr_score, 0.10))

        # 5. 交易次数评分
        if total_trades >= 50:
            trades_score = 1.0
        elif total_trades >= 30:
            trades_score = 0.8
        elif total_trades >= 10:
            trades_score = 0.5
        elif total_trades > 0:
            trades_score = 0.3
            issues.append({'type': 'insufficient_trades', 'severity': 'medium',
                          'message': f'交易次数不足: {total_trades}'})
        else:
            trades_score = 0.0
            issues.append({'type': 'no_trades', 'severity': 'critical',
                          'message': '回测无交易'})
        score_components.append(('total_trades', trades_score, 0.10))

        # 6. 盈亏比评分
        if profit_factor >= 3.0:
            pf_score = 1.0
        elif profit_factor >= 2.0:
            pf_score = 0.8
        elif profit_factor >= 1.5:
            pf_score = 0.6
        elif profit_factor >= 1.0:
            pf_score = 0.4
        else:
            pf_score = 0.0
            issues.append({'type': 'low_profit_factor', 'severity': 'high',
                          'message': f'盈亏比过低: {profit_factor:.2f}'})
        score_components.append(('profit_factor', pf_score, 0.10))

        # 7. 卡玛比率评分
        if calmar_ratio >= 3.0:
            calmar_score = 1.0
        elif calmar_ratio >= 1.0:
            calmar_score = 0.7
        elif calmar_ratio > 0:
            calmar_score = 0.4
        else:
            calmar_score = 0.0
        score_components.append(('calmar_ratio', calmar_score, 0.05))

        # 计算加权总分
        score = sum(w * s for _, s, w in score_components)

        # 置信区间计算
        confidence_interval = {}
        if self.config['enable_confidence_interval'] and total_trades > 1:
            returns = backtest_results.get('returns', [])
            if returns and len(returns) > 1:
                returns_arr = np.array(returns)
                mean_ret = np.mean(returns_arr)
                std_ret = np.std(returns_arr)
                n = len(returns_arr)
                se = std_ret / np.sqrt(n)
                # 95%置信区间
                ci_95 = (mean_ret - 1.96 * se, mean_ret + 1.96 * se)
                confidence_interval = {
                    'mean_return': mean_ret,
                    'std_return': std_ret,
                    'ci_95_lower': ci_95[0],
                    'ci_95_upper': ci_95[1],
                    'standard_error': se,
                }

        step.score = score
        step.issues = issues
        step.details = {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'profit_factor': profit_factor,
            'calmar_ratio': calmar_ratio,
            'sortino_ratio': sortino_ratio,
            'score_components': score_components,
            'confidence_interval': confidence_interval,
        }
        step.status = ValidationStatus.PASSED if score >= self.BACKTEST_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤4: 过拟合检测 ====================

    def _step_overfit_detection(self, strategy_name: str,
                               params: Dict,
                               backtest_results: Dict,
                               market_data: Dict) -> ValidationStep:
        """步骤4: 过拟合检测"""
        step = ValidationStep(name="过拟合检测", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 1.0

        if not backtest_results:
            step.score = 0.0
            step.issues = [{'type': 'no_data', 'severity': 'critical',
                           'message': '缺少回测数据，无法检测过拟合'}]
            step.status = ValidationStatus.FAILED
            step.duration_ms = (time.time() - step_start) * 1000
            step.completed_at = datetime.now().isoformat()
            return step

        # 1. 夏普比率衰减检测
        in_sample_sharpe = backtest_results.get('in_sample_sharpe', None)
        out_sample_sharpe = backtest_results.get('out_sample_sharpe', None)

        if in_sample_sharpe and out_sample_sharpe:
            sharpe_decay = (in_sample_sharpe - out_sample_sharpe) / max(abs(in_sample_sharpe), 0.01)
            if sharpe_decay > 0.5:
                issues.append({'type': 'high_sharpe_decay', 'severity': 'high',
                              'message': f'夏普比率衰减过高: {sharpe_decay:.2%}'})
                score = max(score - 0.4, 0.0)
            elif sharpe_decay > 0.3:
                issues.append({'type': 'moderate_sharpe_decay', 'severity': 'medium',
                              'message': f'夏普比率中度衰减: {sharpe_decay:.2%}'})
                score = max(score - 0.2, 0.0)
            step.details['sharpe_decay'] = sharpe_decay
            step.details['in_sample_sharpe'] = in_sample_sharpe
            step.details['out_sample_sharpe'] = out_sample_sharpe

        # 2. 参数敏感性分析
        if params:
            param_count = len(params)
            if param_count > 20:
                issues.append({'type': 'too_many_params', 'severity': 'high',
                              'message': f'参数数量过多: {param_count}，增加过拟合风险'})
                score = max(score - 0.3, 0.0)
            elif param_count > 10:
                issues.append({'type': 'many_params', 'severity': 'medium',
                              'message': f'参数数量偏多: {param_count}'})
                score = max(score - 0.15, 0.0)
            step.details['param_count'] = param_count

        # 3. 交易频率检查
        total_trades = backtest_results.get('total_trades', 0)
        if total_trades > 0:
            trading_days = backtest_results.get('trading_days', 252)
            if trading_days > 0:
                trades_per_day = total_trades / trading_days
                if trades_per_day > 10:
                    issues.append({'type': 'high_trade_frequency', 'severity': 'medium',
                                  'message': f'日均交易频率过高: {trades_per_day:.1f}'})
                    score = max(score - 0.15, 0.0)
                step.details['trades_per_day'] = trades_per_day

        # 4. 收益分布偏度检查
        returns = backtest_results.get('returns', [])
        if returns and len(returns) > 30:
            returns_arr = np.array(returns)
            skewness = np.mean(((returns_arr - np.mean(returns_arr)) / np.std(returns_arr)) ** 3)
            kurtosis = np.mean(((returns_arr - np.mean(returns_arr)) / np.std(returns_arr)) ** 4) - 3

            if abs(skewness) > 2:
                issues.append({'type': 'high_skewness', 'severity': 'medium',
                              'message': f'收益分布偏度过高: {skewness:.2f}'})
                score = max(score - 0.1, 0.0)

            if kurtosis > 5:
                issues.append({'type': 'high_kurtosis', 'severity': 'medium',
                              'message': f'收益分布峰度过高: {kurtosis:.2f}'})
                score = max(score - 0.1, 0.0)

            step.details['skewness'] = skewness
            step.details['kurtosis'] = kurtosis

        step.score = score
        step.issues = issues
        step.status = ValidationStatus.PASSED if score >= self.OVERFIT_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤5: 蒙特卡洛模拟 ====================

    def _step_monte_carlo_simulation(self, strategy_name: str,
                                    params: Dict,
                                    backtest_results: Dict,
                                    market_data: Dict) -> ValidationStep:
        """步骤5: 蒙特卡洛模拟"""
        step = ValidationStep(name="蒙特卡洛模拟", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 0.5  # 默认中等分数
        simulation_results = {}

        if not self.config['enable_monte_carlo']:
            step.score = 1.0
            step.status = ValidationStatus.SKIPPED
            step.details = {'reason': '蒙特卡洛模拟已禁用'}
            step.duration_ms = (time.time() - step_start) * 1000
            step.completed_at = datetime.now().isoformat()
            return step

        returns = backtest_results.get('returns', []) if backtest_results else []

        if returns and len(returns) > 20:
            try:
                n_simulations = self.config['monte_carlo_simulations']
                returns_arr = np.array(returns)
                mean_ret = np.mean(returns_arr)
                std_ret = np.std(returns_arr)
                n_periods = len(returns_arr)

                # 执行蒙特卡洛模拟
                simulated_returns = np.random.normal(
                    mean_ret, std_ret,
                    size=(n_simulations, n_periods)
                )
                simulated_cumulative = np.cumprod(1 + simulated_returns, axis=1)

                # 计算统计指标
                final_values = simulated_cumulative[:, -1]
                median_final = np.median(final_values)
                p5_final = np.percentile(final_values, 5)
                p95_final = np.percentile(final_values, 95)
                p1_final = np.percentile(final_values, 1)

                # 计算亏损概率
                loss_probability = np.mean(final_values < 1.0)

                # 计算最大回撤分布
                max_drawdowns = []
                for sim in simulated_cumulative:
                    peak = np.maximum.accumulate(sim)
                    drawdown = (sim - peak) / peak
                    max_drawdowns.append(np.min(drawdown))
                median_max_dd = np.median(max_drawdowns)
                p95_max_dd = np.percentile(max_drawdowns, 5)  # 95% VaR of max drawdown

                simulation_results = {
                    'n_simulations': n_simulations,
                    'median_final_return': float(median_final - 1),
                    'p5_final_return': float(p5_final - 1),
                    'p95_final_return': float(p95_final - 1),
                    'p1_final_return': float(p1_final - 1),
                    'loss_probability': float(loss_probability),
                    'median_max_drawdown': float(median_max_dd),
                    'p95_max_drawdown': float(p95_max_dd),
                }

                # 评分计算
                if loss_probability < 0.05:
                    score = 1.0
                elif loss_probability < 0.10:
                    score = 0.8
                elif loss_probability < 0.20:
                    score = 0.6
                elif loss_probability < 0.30:
                    score = 0.4
                    issues.append({'type': 'high_loss_probability', 'severity': 'high',
                                  'message': f'蒙特卡洛模拟亏损概率过高: {loss_probability:.2%}'})
                else:
                    score = 0.2
                    issues.append({'type': 'very_high_loss_probability', 'severity': 'critical',
                                  'message': f'蒙特卡洛模拟亏损概率极高: {loss_probability:.2%}'})

                # 最大回撤惩罚
                if median_max_dd < -0.30:
                    score = max(score - 0.2, 0.0)
                    issues.append({'type': 'high_simulated_drawdown', 'severity': 'high',
                                  'message': f'蒙特卡洛模拟中位最大回撤过高: {median_max_dd:.2%}'})

            except Exception as e:
                issues.append({'type': 'simulation_error', 'severity': 'medium',
                              'message': f'蒙特卡洛模拟执行异常: {e}'})
                score = 0.3
        else:
            issues.append({'type': 'insufficient_data', 'severity': 'medium',
                          'message': '数据不足，蒙特卡洛模拟结果仅供参考'})
            score = 0.5

        step.score = score
        step.issues = issues
        step.details = simulation_results
        step.status = ValidationStatus.PASSED if score >= self.MONTE_CARLO_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤6: VaR风险验证 ====================

    def _step_var_validation(self, strategy_name: str,
                            params: Dict,
                            backtest_results: Dict,
                            market_data: Dict) -> ValidationStep:
        """步骤6: VaR风险验证"""
        step = ValidationStep(name="VaR风险验证", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 0.5
        var_results = {}

        if not self.config['enable_var_validation']:
            step.score = 1.0
            step.status = ValidationStatus.SKIPPED
            step.details = {'reason': 'VaR验证已禁用'}
            step.duration_ms = (time.time() - step_start) * 1000
            step.completed_at = datetime.now().isoformat()
            return step

        returns = backtest_results.get('returns', []) if backtest_results else []

        if returns and len(returns) > 30:
            try:
                returns_arr = np.array(returns)
                confidence_levels = self.config['var_confidence_levels']

                for conf in confidence_levels:
                    # 历史模拟法VaR
                    var_hs = np.percentile(returns_arr, (1 - conf) * 100)

                    # 参数法VaR（正态分布假设）
                    mean_ret = np.mean(returns_arr)
                    std_ret = np.std(returns_arr)
                    from scipy import stats
                    var_param = mean_ret + stats.norm.ppf(1 - conf) * std_ret

                    # 条件VaR（CVaR/Expected Shortfall）
                    cvar = np.mean(returns_arr[returns_arr <= var_hs])

                    var_results[f'var_{int(conf*100)}_historical'] = float(var_hs)
                    var_results[f'var_{int(conf*100)}_parametric'] = float(var_param)
                    var_results[f'cvar_{int(conf*100)}'] = float(cvar)

                # 评分计算
                var_95 = var_results.get('var_95_historical', 0)
                if var_95 >= -0.02:  # VaR 95% 损失不超过2%
                    score = 1.0
                elif var_95 >= -0.05:
                    score = 0.8
                elif var_95 >= -0.10:
                    score = 0.5
                elif var_95 >= -0.15:
                    score = 0.3
                    issues.append({'type': 'high_var', 'severity': 'high',
                                  'message': f'VaR(95%)过高: {var_95:.2%}'})
                else:
                    score = 0.1
                    issues.append({'type': 'very_high_var', 'severity': 'critical',
                                  'message': f'VaR(95%)极高: {var_95:.2%}'})

                # CVaR检查
                cvar_95 = var_results.get('cvar_95', 0)
                if cvar_95 < -0.10:
                    issues.append({'type': 'high_cvar', 'severity': 'high',
                                  'message': f'CVaR(95%)过高: {cvar_95:.2%}'})
                    score = max(score - 0.2, 0.0)

            except ImportError:
                # scipy不可用，使用简化计算
                for conf in confidence_levels:
                    var_hs = np.percentile(returns_arr, (1 - conf) * 100)
                    var_results[f'var_{int(conf*100)}_historical'] = float(var_hs)
                score = 0.6
                issues.append({'type': 'simplified_var', 'severity': 'low',
                              'message': 'scipy不可用，使用简化VaR计算'})
            except Exception as e:
                issues.append({'type': 'var_calculation_error', 'severity': 'medium',
                              'message': f'VaR计算异常: {e}'})
                score = 0.3
        else:
            issues.append({'type': 'insufficient_data', 'severity': 'medium',
                          'message': '数据不足，VaR验证结果仅供参考'})
            score = 0.5

        step.score = score
        step.issues = issues
        step.details = var_results
        step.status = ValidationStatus.PASSED if score >= self.VAR_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤7: 压力测试 ====================

    def _step_stress_test(self, strategy_name: str,
                         params: Dict,
                         backtest_results: Dict,
                         market_data: Dict) -> ValidationStep:
        """步骤7: 压力测试"""
        step = ValidationStep(name="压力测试", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 1.0
        scenario_results = {}

        if not self.config['enable_stress_test']:
            step.score = 1.0
            step.status = ValidationStatus.SKIPPED
            step.details = {'reason': '压力测试已禁用'}
            step.duration_ms = (time.time() - step_start) * 1000
            step.completed_at = datetime.now().isoformat()
            return step

        returns = backtest_results.get('returns', []) if backtest_results else []

        if returns and len(returns) > 20:
            try:
                returns_arr = np.array(returns)
                mean_ret = np.mean(returns_arr)
                std_ret = np.std(returns_arr)

                scenarios = self.config['stress_test_scenarios']
                worst_case_loss = 0.0

                for scenario in scenarios:
                    name = scenario['name']
                    price_drop = scenario['price_drop']
                    vol_spike = scenario['vol_spike']

                    # 模拟压力情景下的预期损失
                    stressed_std = std_ret * vol_spike
                    expected_loss = mean_ret + price_drop  # 价格冲击 + 正常收益
                    stressed_var = expected_loss - 2 * stressed_std  # 95%置信水平下的损失

                    scenario_results[name] = {
                        'expected_loss': float(expected_loss),
                        'stressed_var_95': float(stressed_var),
                        'price_drop': price_drop,
                        'vol_spike': vol_spike,
                    }

                    worst_case_loss = min(worst_case_loss, stressed_var)

                # 评分计算
                if worst_case_loss >= -0.20:
                    score = 1.0
                elif worst_case_loss >= -0.30:
                    score = 0.8
                elif worst_case_loss >= -0.40:
                    score = 0.6
                elif worst_case_loss >= -0.50:
                    score = 0.4
                    issues.append({'type': 'high_stress_loss', 'severity': 'high',
                                  'message': f'压力测试最坏损失过高: {worst_case_loss:.2%}'})
                else:
                    score = 0.2
                    issues.append({'type': 'extreme_stress_loss', 'severity': 'critical',
                                  'message': f'压力测试最坏损失极端: {worst_case_loss:.2%}'})

                # 检查特定场景
                for name, result in scenario_results.items():
                    if result['stressed_var_95'] < -0.30:
                        issues.append({'type': f'stress_fail_{name}', 'severity': 'medium',
                                      'message': f'压力场景"{name}"下VaR(95%)过低: {result["stressed_var_95"]:.2%}'})

            except Exception as e:
                issues.append({'type': 'stress_test_error', 'severity': 'medium',
                              'message': f'压力测试执行异常: {e}'})
                score = 0.3
        else:
            issues.append({'type': 'insufficient_data', 'severity': 'medium',
                          'message': '数据不足，压力测试结果仅供参考'})
            score = 0.5

        step.score = score
        step.issues = issues
        step.details = {
            'scenarios': scenario_results,
            'worst_case_loss': worst_case_loss if 'worst_case_loss' in dir() else None,
        }
        step.status = ValidationStatus.PASSED if score >= self.STRESS_TEST_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤8: 风控审计 ====================

    def _step_risk_audit(self, strategy_name: str,
                        params: Dict,
                        backtest_results: Dict,
                        market_data: Dict) -> ValidationStep:
        """步骤8: 风控审计"""
        step = ValidationStep(name="风控审计", weight=1.5)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        score = 1.0

        if self.risk_controller and self.risk_controller.enabled:
            try:
                # 使用统一风控控制器进行审计
                risk_report = self.risk_controller.audit_strategy(
                    strategy_name=strategy_name,
                    params=params,
                    backtest_results=backtest_results,
                )

                score = risk_report.get('score', 1.0)
                audit_issues = risk_report.get('issues', [])
                issues.extend(audit_issues)

                step.details = {
                    'risk_score': risk_report.get('score'),
                    'risk_level': risk_report.get('level'),
                    'risk_metrics': risk_report.get('metrics', {}),
                    'violations': risk_report.get('violations', []),
                }
            except Exception as e:
                logger.warning(f"[ValidationPipeline] 风控审计异常: {e}")
                issues.append({'type': 'risk_audit_error', 'severity': 'medium',
                              'message': f'风控审计执行异常: {e}'})
                score = 0.5
        else:
            # 基础风控检查
            if backtest_results:
                max_drawdown = backtest_results.get('max_drawdown', 0)
                if max_drawdown > 0.25:
                    issues.append({'type': 'risk_drawdown_exceeded', 'severity': 'high',
                                  'message': f'最大回撤超过风控阈值: {max_drawdown:.2%} > 25%'})
                    score = max(score - 0.4, 0.0)

                leverage = backtest_results.get('max_leverage', 1.0)
                if leverage > 3.0:
                    issues.append({'type': 'risk_leverage_exceeded', 'severity': 'high',
                                  'message': f'最大杠杆超过风控阈值: {leverage:.1f}x > 3x'})
                    score = max(score - 0.3, 0.0)

                concentration = backtest_results.get('max_concentration', 0)
                if concentration > 0.4:
                    issues.append({'type': 'risk_concentration_exceeded', 'severity': 'medium',
                                  'message': f'持仓集中度超过风控阈值: {concentration:.2%} > 40%'})
                    score = max(score - 0.2, 0.0)

            step.details = {
                'risk_controller_available': False,
                'max_drawdown': backtest_results.get('max_drawdown', 0) if backtest_results else 0,
                'max_leverage': backtest_results.get('max_leverage', 1.0) if backtest_results else 1.0,
            }

        step.score = score
        step.issues = issues
        step.status = ValidationStatus.PASSED if score >= self.RISK_AUDIT_PASS_THRESHOLD else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    # ==================== 步骤9: 委员会投票决策 ====================

    def _step_committee_vote(self, strategy_name: str,
                            params: Dict,
                            backtest_results: Dict,
                            market_data: Dict) -> ValidationStep:
        """步骤9: 委员会投票决策"""
        step = ValidationStep(name="委员会投票决策", weight=2.0)
        step.started_at = datetime.now().isoformat()
        step_start = time.time()

        issues = []
        vote_results = []

        # 获取前8步的验证结果（从历史中获取）
        previous_steps = [s for s in self._validation_history[-1].steps
                         if s.name != "委员会投票决策"] if self._validation_history else []

        # 委员会成员投票
        members = [
            {"name": "数据质量专家", "role": "data_quality"},
            {"name": "风险控制专家", "role": "risk_management"},
            {"name": "策略优化专家", "role": "strategy_optimization"},
            {"name": "合规审计专家", "role": "compliance_audit"},
        ]

        approvals = 0
        rejections = 0
        abstentions = 0

        for member in members:
            vote = self._member_vote(member, previous_steps, backtest_results)
            vote_results.append(vote)

            if vote['decision'] == 'approve':
                approvals += 1
            elif vote['decision'] == 'reject':
                rejections += 1
            else:
                abstentions += 1

        # 计算投票评分
        min_approvals = self.config['committee_min_approvals']
        if approvals >= min_approvals:
            score = 1.0
            passed = True
        elif approvals >= min_approvals - 1:
            score = 0.7
            passed = False
            issues.append({'type': 'committee_insufficient_approvals', 'severity': 'high',
                          'message': f'委员会投票未全票通过: {approvals}/{min_approvals}'})
        else:
            score = 0.3
            passed = False
            issues.append({'type': 'committee_rejected', 'severity': 'critical',
                          'message': f'委员会投票被拒绝: {approvals}/{min_approvals}'})

        step.score = score
        step.issues = issues
        step.details = {
            'vote_results': vote_results,
            'approvals': approvals,
            'rejections': rejections,
            'abstentions': abstentions,
            'min_approvals': min_approvals,
            'passed': passed,
        }
        step.status = ValidationStatus.PASSED if passed else ValidationStatus.FAILED
        step.duration_ms = (time.time() - step_start) * 1000
        step.completed_at = datetime.now().isoformat()

        self._step_performance[step.name].append(step.duration_ms)
        return step

    def _member_vote(self, member: Dict,
                     previous_steps: List[ValidationStep],
                     backtest_results: Dict) -> Dict:
        """委员会成员投票逻辑"""
        decision = 'abstain'
        reasons = []
        confidence = 0.5

        role = member['role']

        if role == 'data_quality':
            # 数据质量专家投票
            data_step = next((s for s in previous_steps if s.name == "数据质量验证"), None)
            if data_step:
                if data_step.status == ValidationStatus.PASSED:
                    decision = 'approve'
                    confidence = data_step.score
                else:
                    decision = 'reject'
                    reasons.append(f'数据质量验证未通过: 评分={data_step.score:.2f}')
                    confidence = 1 - data_step.score

        elif role == 'risk_management':
            # 风险控制专家投票
            risk_step = next((s for s in previous_steps if s.name == "风控审计"), None)
            var_step = next((s for s in previous_steps if s.name == "VaR风险验证"), None)
            stress_step = next((s for s in previous_steps if s.name == "压力测试"), None)

            risk_scores = []
            for s in [risk_step, var_step, stress_step]:
                if s:
                    risk_scores.append(s.score)

            if risk_scores:
                avg_risk_score = np.mean(risk_scores)
                if avg_risk_score >= 0.85:
                    decision = 'approve'
                elif avg_risk_score >= 0.70:
                    decision = 'abstain'
                    reasons.append(f'风险评分中等: {avg_risk_score:.2f}')
                else:
                    decision = 'reject'
                    reasons.append(f'风险评分过低: {avg_risk_score:.2f}')
                confidence = avg_risk_score

        elif role == 'strategy_optimization':
            # 策略优化专家投票
            backtest_step = next((s for s in previous_steps if s.name == "回测结果验证"), None)
            overfit_step = next((s for s in previous_steps if s.name == "过拟合检测"), None)
            mc_step = next((s for s in previous_steps if s.name == "蒙特卡洛模拟"), None)

            perf_scores = []
            for s in [backtest_step, overfit_step, mc_step]:
                if s:
                    perf_scores.append(s.score)

            if perf_scores:
                avg_perf_score = np.mean(perf_scores)
                if avg_perf_score >= 0.85:
                    decision = 'approve'
                elif avg_perf_score >= 0.70:
                    decision = 'abstain'
                    reasons.append(f'策略表现评分中等: {avg_perf_score:.2f}')
                else:
                    decision = 'reject'
                    reasons.append(f'策略表现评分过低: {avg_perf_score:.2f}')
                confidence = avg_perf_score

        elif role == 'compliance_audit':
            # 合规审计专家投票
            param_step = next((s for s in previous_steps if s.name == "参数边界检查"), None)
            all_passed = all(
                s.status == ValidationStatus.PASSED
                for s in previous_steps
                if s.status != ValidationStatus.SKIPPED
            )

            if all_passed and (not param_step or param_step.score >= 0.9):
                decision = 'approve'
                confidence = 1.0
            elif all_passed:
                decision = 'abstain'
                reasons.append('所有步骤通过，但参数检查存在警告')
                confidence = 0.8
            else:
                decision = 'reject'
                failed_steps = [s.name for s in previous_steps
                               if s.status == ValidationStatus.FAILED]
                reasons.append(f'存在未通过的验证步骤: {failed_steps}')
                confidence = 0.3

        return {
            'member': member['name'],
            'role': role,
            'decision': decision,
            'reasons': reasons,
            'confidence': confidence,
        }

    # ==================== 辅助方法 ====================

    def _hash_params(self, params: Dict) -> str:
        """生成参数哈希"""
        try:
            params_str = json.dumps(params, sort_keys=True, default=str)
            return hashlib.sha256(params_str.encode()).hexdigest()[:16]
        except Exception:
            return str(hash(str(params)))

    def _calculate_overall_score(self, steps: List[ValidationStep]) -> float:
        """计算加权综合评分"""
        total_weight = sum(s.weight for s in steps if s.status != ValidationStatus.SKIPPED)
        if total_weight == 0:
            return 0.0

        weighted_score = sum(
            s.score * s.weight
            for s in steps
            if s.status != ValidationStatus.SKIPPED
        )
        return weighted_score / total_weight

    def _generate_summary(self, report: ValidationReport) -> str:
        """生成验证摘要"""
        passed_steps = sum(1 for s in report.steps if s.status == ValidationStatus.PASSED)
        failed_steps = sum(1 for s in report.steps if s.status == ValidationStatus.FAILED)
        skipped_steps = sum(1 for s in report.steps if s.status == ValidationStatus.SKIPPED)
        total_steps = len(report.steps)

        summary_parts = [
            f"策略 {report.strategy_name} 验证完成",
            f"综合评分: {report.overall_score:.2%}",
            f"通过步骤: {passed_steps}/{total_steps}",
        ]

        if failed_steps > 0:
            summary_parts.append(f"失败步骤: {failed_steps}")
        if skipped_steps > 0:
            summary_parts.append(f"跳过步骤: {skipped_steps}")

        if report.passed:
            summary_parts.append("最终结论: ✅ 通过")
        else:
            summary_parts.append("最终结论: ❌ 未通过")

        return " | ".join(summary_parts)

    def _generate_recommendations(self, steps: List[ValidationStep]) -> List[str]:
        """根据验证结果生成改进建议"""
        recommendations = []

        for step in steps:
            if step.status == ValidationStatus.FAILED:
                if step.name == "数据质量验证":
                    recommendations.append("建议检查数据源质量，补充缺失数据，清理异常值")
                elif step.name == "参数边界检查":
                    recommendations.append("建议调整策略参数范围，避免极端值或无效参数")
                elif step.name == "回测结果验证":
                    recommendations.append("建议优化策略逻辑，提升回测表现指标")
                elif step.name == "过拟合检测":
                    recommendations.append("建议减少参数数量，增加样本外测试，降低过拟合风险")
                elif step.name == "蒙特卡洛模拟":
                    recommendations.append("建议优化策略稳健性，降低极端市场条件下的亏损概率")
                elif step.name == "VaR风险验证":
                    recommendations.append("建议加强风险控制，降低VaR和CVaR水平")
                elif step.name == "压力测试":
                    recommendations.append("建议增加对冲机制，提高极端市场情景下的抗风险能力")
                elif step.name == "风控审计":
                    recommendations.append("建议调整风控参数，确保符合风控合规要求")
                elif step.name == "委员会投票决策":
                    recommendations.append("建议全面优化策略，争取委员会全票通过")

            if step.warnings:
                for warning in step.warnings[:3]:  # 最多3条警告
                    recommendations.append(f"[警告] {warning}")

        return recommendations

    def _check_circuit_breaker(self) -> bool:
        """检查熔断状态"""
        if not self.config['enable_circuit_breaker']:
            return False

        if self._circuit_breaker_open:
            # 检查是否到了重置时间
            if self._circuit_breaker_reset_at:
                if datetime.now() >= self._circuit_breaker_reset_at:
                    self._circuit_breaker_open = False
                    self._circuit_breaker_reset_at = None
                    self._circuit_breaker_count = 0
                    logger.info("[ValidationPipeline] 熔断保护已重置")
                    return False
            return True

        if self._circuit_breaker_count >= self._circuit_breaker_threshold:
            self._circuit_breaker_open = True
            self._circuit_breaker_reset_at = datetime.now() + timedelta(minutes=30)
            logger.warning(f"[ValidationPipeline] 熔断保护已激活，持续30分钟")
            return True

        return False

    def _create_failed_report(self, strategy_name: str,
                             params: Dict,
                             reason: str) -> ValidationReport:
        """创建失败报告"""
        return ValidationReport(
            strategy_name=strategy_name,
            params_hash=self._hash_params(params),
            timestamp=datetime.now().isoformat(),
            overall_score=0.0,
            passed=False,
            summary=f"验证失败: {reason}",
        )

    def _persist_report(self, report: ValidationReport) -> bool:
        """持久化验证报告到数据库和文件系统"""
        try:
            # 保存到文件系统
            report_file = self._report_dir / f"{report.strategy_name}_{report.params_hash}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

            # 保存到数据库
            if self.db_manager:
                try:
                    self.db_manager.save_validation_report(report.to_dict())
                except Exception as e:
                    logger.debug(f"[ValidationPipeline] 数据库持久化失败: {e}")

            return True
        except Exception as e:
            logger.warning(f"[ValidationPipeline] 报告持久化失败: {e}")
            return False

    # ==================== 统计与监控接口 ====================

    def get_statistics(self) -> Dict:
        """获取验证管道统计信息"""
        return {
            'total_validations': self._total_validations,
            'total_passed': self._total_passed,
            'total_failed': self._total_failed,
            'pass_rate': self._total_passed / max(self._total_validations, 1),
            'average_duration_ms': self._total_duration_ms / max(self._total_validations, 1),
            'circuit_breaker_open': self._circuit_breaker_open,
            'circuit_breaker_count': self._circuit_breaker_count,
            'step_performance': {
                name: {
                    'avg_duration_ms': np.mean(durations),
                    'max_duration_ms': max(durations),
                    'min_duration_ms': min(durations),
                    'count': len(durations),
                }
                for name, durations in self._step_performance.items()
            },
            'enabled': self.enabled,
        }

    def get_recent_reports(self, n: int = 10) -> List[Dict]:
        """获取最近的验证报告"""
        return [r.to_dict() for r in self._validation_history[-n:]]

    def clear_history(self):
        """清除验证历史"""
        self._validation_history.clear()
        logger.info("[ValidationPipeline] 验证历史已清除")

    def reset_statistics(self):
        """重置统计信息"""
        self._total_validations = 0
        self._total_passed = 0
        self._total_failed = 0
        self._total_duration_ms = 0.0
        self._step_performance.clear()
        self._circuit_breaker_count = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_reset_at = None
        logger.info("[ValidationPipeline] 统计信息已重置")


# ==================== 全局单例访问接口 ====================

_validation_pipeline_instance = None


def get_validation_pipeline() -> ValidationPipeline:
    """获取全局验证管道实例"""
    global _validation_pipeline_instance
    if _validation_pipeline_instance is None:
        _validation_pipeline_instance = ValidationPipeline()
    return _validation_pipeline_instance


def validate_strategy(strategy_name: str,
                     params: Dict[str, Any],
                     backtest_results: Dict[str, Any] = None,
                     market_data: Dict[str, Any] = None) -> ValidationReport:
    """
    快捷验证接口

    Args:
        strategy_name: 策略名称
        params: 策略参数
        backtest_results: 回测结果（可选）
        market_data: 市场数据（可选）

    Returns:
        验证报告
    """
    pipeline = get_validation_pipeline()
    return pipeline.validate_strategy(strategy_name, params, backtest_results, market_data)


def enable_validation():
    """启用验证管道"""
    pipeline = get_validation_pipeline()
    pipeline.enabled = True
    logger.info("[ValidationPipeline] 验证管道已启用")


def disable_validation():
    """禁用验证管道"""
    pipeline = get_validation_pipeline()
    pipeline.enabled = False
    logger.info("[ValidationPipeline] 验证管道已禁用")


# ==================== 测试入口 ====================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logger.info("=" * 60)
    logger.info("ValidationPipeline 自测试")
    logger.info("=" * 60)

    # 创建管道实例
    pipeline = get_validation_pipeline()
    pipeline.enabled = True

    # 测试参数
    test_params = {
        'lookback_period': 20,
        'entry_threshold': 0.02,
        'exit_threshold': -0.01,
        'stop_loss': 0.05,
        'position_size': 0.1,
        'max_positions': 5,
        'use_trailing_stop': True,
        'trailing_stop_pct': 0.03,
    }

    # 测试回测结果
    test_backtest_results = {
        'total_return': 0.35,
        'sharpe_ratio': 1.8,
        'max_drawdown': -0.12,
        'win_rate': 0.58,
        'total_trades': 120,
        'profit_factor': 2.1,
        'calmar_ratio': 2.9,
        'sortino_ratio': 2.2,
        'in_sample_sharpe': 2.1,
        'out_sample_sharpe': 1.6,
        'returns': [0.001 * np.random.randn() for _ in range(252)],
        'prices': [100 * (1 + 0.001 * np.random.randn()) for _ in range(252)],
        'volumes': [1000000 + int(500000 * np.random.randn()) for _ in range(252)],
        'trading_days': 252,
        'max_leverage': 1.5,
        'max_concentration': 0.25,
    }

    # 执行验证
    logger.info("\n开始验证测试策略...")
    report = pipeline.validate_strategy(
        strategy_name="TestStrategy",
        params=test_params,
        backtest_results=test_backtest_results,
    )

    # 输出结果
    logger.info(f"\n验证结果:")
    logger.info(f"  综合评分: {report.overall_score:.4f}")
    logger.info(f"  通过: {report.passed}")
    logger.info(f"  摘要: {report.summary}")
    logger.info(f"  耗时: {report.total_duration_ms:.1f}ms")

    logger.info(f"\n步骤详情:")
    for step in report.steps:
        status_icon = "✅" if step.status == ValidationStatus.PASSED else \
                     "❌" if step.status == ValidationStatus.FAILED else \
                     "⏭️" if step.status == ValidationStatus.SKIPPED else \
                     "⚠️"
        logger.info(f"  {status_icon} {step.name}: 评分={step.score:.4f}, "
                   f"状态={step.status.value}, 耗时={step.duration_ms:.1f}ms")

    if report.recommendations:
        logger.info(f"\n改进建议:")
        for i, rec in enumerate(report.recommendations, 1):
            logger.info(f"  {i}. {rec}")

    # 输出统计
    stats = pipeline.get_statistics()
    logger.info(f"\n管道统计:")
    logger.info(f"  总验证次数: {stats['total_validations']}")
    logger.info(f"  通过率: {stats['pass_rate']:.2%}")
    logger.info(f"  平均耗时: {stats['average_duration_ms']:.1f}ms")
    logger.info(f"  熔断状态: {'已激活' if stats['circuit_breaker_open'] else '正常'}")

    logger.info("\n" + "=" * 60)
    logger.info("自测试完成")
    logger.info("=" * 60)


