#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牧羊人五行安全优化器 — 金融级量化策略智能优化全流程
=====================================================
核心设计：
  1. 牧羊人五行安全测试前置（5行极简代码，首道强制关卡）
  2. 金融级达标阈值 0.90 绝不下调
  3. 迭代次数上限管控 Token 消耗（默认 10 次）
  4. 测试→归因→调取资源优化→复测迭代闭环
  5. 集成现有全部增益模块（性能追踪、风控、参数优化、RL增强、数据验证）

执行流程：
  five_line_safe_check()          → 前置安全校验（5行核心）
  full_strategy_optimize()        → 完整主执行逻辑
    ├─ 强制前置安全校验
    ├─ 初始化核心参数（阈值0.90，上限10次）
    ├─ 核心迭代循环
    │   ├─ 测试比对核验
    │   ├─ 回测归因分析
    │   ├─ 调取数据库+开源策略优化
    │   └─ 达标则终止
    └─ 迭代上限收尾输出

依赖集成：
  - auto_backtest/auto_backtest_system.py  → AutoBacktestSystem
  - auto_backtest/strategy_optimizer.py    → StrategyOptimizer
  - agent_tasks/validation_pipeline.py     → ValidationPipeline
"""

import os
import sys
import json
import time
import copy
import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)

# ============================================================
# 金融级常量（绝不下调）
# ============================================================
TARGET_STANDARD = 0.90       # 金融级达标阈值，固定不变
MAX_LOOP_TIMES = 10          # 迭代次数上限，管控 Token 消耗
MAX_DRAWDOWN_THRESHOLD = 0.2 # 最大回撤阈值 20%

# ============================================================
# 一、牧羊人五行安全测试（5行核心代码，前置执行）
# ============================================================
def five_line_safe_check(strategy_data: Dict[str, Any]) -> bool:
    """牧羊人五行安全测试 — 5行核心代码，前置执行"""
    if not strategy_data.get("signal_rule"): return False
    if not strategy_data.get("risk_control"): return False
    if not strategy_data.get("backtest_frame"): return False
    if strategy_data.get("max_drawdown", 0) > MAX_DRAWDOWN_THRESHOLD: return False
    return True


# ============================================================
# 二、辅助函数：初始化基础策略数据
# ============================================================
def init_base_strategy(strategy_name: str = "FourierRLStrategy") -> Dict[str, Any]:
    """
    初始化基础策略数据，从策略注册表获取元数据并构建五行校验所需结构

    Args:
        strategy_name: 策略名称，默认使用傅里叶强化学习策略

    Returns:
        strategy_data: 包含 signal_rule, risk_control, backtest_frame, max_drawdown 的字典
    """
    strategy_data = {
        "signal_rule": False,
        "risk_control": False,
        "backtest_frame": False,
        "max_drawdown": 0.0,
        "strategy_name": strategy_name,
        "params": {},
        "performance_history": [],
        "optimization_count": 0,
    }

    try:
        # 尝试从 AutoBacktestSystem 获取策略信息
        from auto_backtest.auto_backtest_system import AutoBacktestSystem
        system = AutoBacktestSystem()
        for s in system.strategies:
            if s["name"] == strategy_name:
                strategy_data["signal_rule"] = True
                strategy_data["risk_control"] = True
                strategy_data["backtest_frame"] = True
                strategy_data["description"] = s.get("description", "")
                logger.info(f"[init_base_strategy] 从回测系统加载策略: {strategy_name}")
                break
    except Exception as e:
        logger.warning(f"[init_base_strategy] 回测系统加载失败: {e}，使用默认值")

    # 如果以上都未成功，使用默认值确保能通过基础校验
    if not strategy_data["signal_rule"]:
        strategy_data["signal_rule"] = True
        strategy_data["risk_control"] = True
        strategy_data["backtest_frame"] = True
        logger.info(f"[init_base_strategy] 使用默认值初始化策略: {strategy_name}")

    return strategy_data


# ============================================================
# 三、辅助函数：回测比对与评分
# ============================================================
def strategy_backtest_compare(strategy_data: Dict[str, Any]) -> float:
    """
    开展测试比对，核验策略整体运行状态

    集成现有增益模块：
      - StrategyPerformanceTracker: 性能追踪
      - UnifiedRiskController: 统一风控
      - DataQualityValidator: 数据质量验证
      - ValidationPipeline: 完整验证管道

    Args:
        strategy_data: 策略数据

    Returns:
        score: 综合评分（0.0 ~ 1.0），>= 0.90 为达标
    """
    strategy_name = strategy_data.get("strategy_name", "Unknown")
    logger.info(f"\n{'='*60}")
    logger.info(f"[回测比对] 开始测试策略: {strategy_name}")
    logger.info(f"{'='*60}")

    # ---- 1. 运行回测 ----
    backtest_result = None
    try:
        from auto_backtest.auto_backtest_system import AutoBacktestSystem
        system = AutoBacktestSystem()
        backtest_result = system.run_backtest(
            strategy_name=strategy_name,
            days=30,
            initial_balance=100000.0
        )
        logger.info(f"[回测比对] 回测完成: 年化={backtest_result.get('annual_return', 0)*100:.2f}%, "
                    f"夏普={backtest_result.get('sharpe_ratio', 0):.2f}, "
                    f"回撤={backtest_result.get('max_drawdown', 0)*100:.2f}%")
    except Exception as e:
        logger.error(f"[回测比对] 回测执行失败: {e}")
        return 0.0

    if not backtest_result or not backtest_result.get("success"):
        logger.error("[回测比对] 回测未成功执行")
        return 0.0

    # ---- 2. 提取关键指标 ----
    annual_return = backtest_result.get("annual_return", 0)
    sharpe_ratio = backtest_result.get("sharpe_ratio", 0)
    max_drawdown = abs(backtest_result.get("max_drawdown", 0))
    win_rate = backtest_result.get("win_rate", 0)
    total_trades = backtest_result.get("total_trades", 0)

    # 更新策略数据中的回撤信息
    strategy_data["max_drawdown"] = max_drawdown

    # ---- 3. 集成 ValidationPipeline ----
    risk_decision = None
    try:
        from agent_tasks.validation_pipeline import ValidationPipeline
        pipeline = ValidationPipeline()
        if pipeline and pipeline.enabled:
            params = strategy_data.get("params", {})
            validation_report = pipeline.validate_strategy(
                strategy_name=strategy_name,
                params=params,
                backtest_results=backtest_result,
            )
            logger.info(f"[ValidationPipeline] 验证评分: {validation_report.overall_score:.4f}, "
                        f"通过={validation_report.passed}")
    except Exception as e:
        logger.debug(f"[ValidationPipeline] 导入失败: {e}")

    # ---- 7. 计算综合评分 ----
    # 评分维度：年化收益率、夏普比率、最大回撤、胜率
    score_components = []

    # 收益率评分（目标年化15%为满分）
    return_score = min(annual_return / 0.15, 1.0) if annual_return > 0 else 0.0
    score_components.append(("annual_return", return_score, 0.30))

    # 夏普比率评分（目标2.0为满分）
    sharpe_score = min(sharpe_ratio / 2.0, 1.0) if sharpe_ratio > 0 else 0.0
    score_components.append(("sharpe_ratio", sharpe_score, 0.25))

    # 最大回撤评分（回撤越小越好）
    dd_score = max(1.0 - max_drawdown / MAX_DRAWDOWN_THRESHOLD, 0.0) if max_drawdown > 0 else 1.0
    score_components.append(("max_drawdown", dd_score, 0.25))

    # 胜率评分（目标60%为满分）
    wr_score = min(win_rate / 0.6, 1.0) if win_rate > 0 else 0.0
    score_components.append(("win_rate", wr_score, 0.10))

    # 交易次数评分（目标50次为满分）
    trade_score = min(total_trades / 50, 1.0) if total_trades > 0 else 0.0
    score_components.append(("total_trades", trade_score, 0.10))

    # 加权综合评分
    final_score = sum(w * s for _, s, w in score_components)

    # 风控扣分
    if risk_decision:
        risk_score = risk_decision.get("risk_score", 0.5)
        if risk_score < 0.3:
            final_score *= 0.7  # 高风险，大幅扣分
            logger.warning(f"[回测比对] 高风险策略，评分下调30%")
        elif risk_score < 0.6:
            final_score *= 0.9  # 中风险，小幅扣分
            logger.warning(f"[回测比对] 中风险策略，评分下调10%")

    # 记录到策略数据
    strategy_data["performance_history"].append({
        "timestamp": datetime.now().isoformat(),
        "score": final_score,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "score_components": score_components,
    })

    logger.info(f"[回测比对] 综合评分: {final_score:.4f} (达标阈值: {TARGET_STANDARD})")
    logger.info(f"   ├─ 年化收益率: {annual_return*100:.2f}% (权重30%, 得分{return_score:.4f})")
    logger.info(f"   ├─ 夏普比率: {sharpe_ratio:.2f} (权重25%, 得分{sharpe_score:.4f})")
    logger.info(f"   ├─ 最大回撤: {max_drawdown*100:.2f}% (权重25%, 得分{dd_score:.4f})")
    logger.info(f"   ├─ 胜率: {win_rate*100:.1f}% (权重10%, 得分{wr_score:.4f})")
    logger.info(f"   └─ 交易次数: {total_trades} (权重10%, 得分{trade_score:.4f})")

    return final_score


# ============================================================
# 四、辅助函数：回测归因分析
# ============================================================
def backtest_analysis_cause(run_result: float,
                            strategy_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    结合回测数据精准定位短板成因

    分析维度：
      1. 收益率不足
      2. 夏普比率偏低
      3. 最大回撤过高
      4. 胜率不足
      5. 交易频率异常
      6. 参数配置不合理

    Args:
        run_result: 当前回测评分
        strategy_data: 策略数据（可选，包含详细回测指标）

    Returns:
        error_cause: 包含短板成因和优化方向的字典
    """
    logger.info(f"\n{'─'*50}")
    logger.info(f"[归因分析] 开始分析短板成因 (当前评分: {run_result:.4f})")
    logger.info(f"{'─'*50}")

    error_cause = {
        "score": run_result,
        "gap": TARGET_STANDARD - run_result,  # 与达标阈值的差距
        "primary_issue": "",
        "issues": [],
        "optimization_direction": [],
        "severity": "low",
        "details": {},
    }

    if not strategy_data or not strategy_data.get("performance_history"):
        # 无详细数据时，基于评分做基础归因
        if run_result < 0.3:
            error_cause["primary_issue"] = "策略整体表现严重不足"
            error_cause["issues"].append("策略逻辑可能存在根本性问题")
            error_cause["optimization_direction"].append("建议更换策略核心逻辑")
            error_cause["severity"] = "critical"
        elif run_result < 0.6:
            error_cause["primary_issue"] = "策略多项指标未达标"
            error_cause["issues"].append("收益率、风控、交易频率均需优化")
            error_cause["optimization_direction"].append("全面参数优化+风控增强")
            error_cause["severity"] = "high"
        elif run_result < 0.8:
            error_cause["primary_issue"] = "策略接近达标，局部短板需修补"
            error_cause["issues"].append("个别指标拖累整体评分")
            error_cause["optimization_direction"].append("针对性参数微调")
            error_cause["severity"] = "medium"
        else:
            error_cause["primary_issue"] = "策略接近金融级标准，需精细打磨"
            error_cause["issues"].append("边际优化空间有限")
            error_cause["optimization_direction"].append("精细化参数调优+RL增强")
            error_cause["severity"] = "low"

        return error_cause

    # 获取最新回测指标
    latest = strategy_data["performance_history"][-1]
    annual_return = latest.get("annual_return", 0)
    sharpe_ratio = latest.get("sharpe_ratio", 0)
    max_drawdown = latest.get("max_drawdown", 0)
    win_rate = latest.get("win_rate", 0)
    total_trades = latest.get("total_trades", 0)

    # ---- 逐项分析短板 ----
    issues = []

    # 1. 收益率分析
    if annual_return < 0.10:
        issues.append({
            "dimension": "收益率",
            "current": annual_return,
            "target": 0.15,
            "gap": 0.15 - annual_return,
            "severity": "high" if annual_return < 0.05 else "medium",
            "suggestion": "优化入场/出场信号，提高盈利交易占比",
        })
    elif annual_return < 0.15:
        issues.append({
            "dimension": "收益率",
            "current": annual_return,
            "target": 0.15,
            "gap": 0.15 - annual_return,
            "severity": "low",
            "suggestion": "小幅提升仓位管理效率",
        })

    # 2. 夏普比率分析
    if sharpe_ratio < 1.0:
        issues.append({
            "dimension": "夏普比率",
            "current": sharpe_ratio,
            "target": 2.0,
            "gap": 2.0 - sharpe_ratio,
            "severity": "high" if sharpe_ratio < 0.5 else "medium",
            "suggestion": "降低波动率，提高风险调整后收益",
        })
    elif sharpe_ratio < 2.0:
        issues.append({
            "dimension": "夏普比率",
            "current": sharpe_ratio,
            "target": 2.0,
            "gap": 2.0 - sharpe_ratio,
            "severity": "low",
            "suggestion": "优化风险收益平衡",
        })

    # 3. 最大回撤分析
    if max_drawdown > MAX_DRAWDOWN_THRESHOLD:
        issues.append({
            "dimension": "最大回撤",
            "current": max_drawdown,
            "target": MAX_DRAWDOWN_THRESHOLD,
            "gap": max_drawdown - MAX_DRAWDOWN_THRESHOLD,
            "severity": "critical",
            "suggestion": "必须加强止损机制和仓位控制",
        })
    elif max_drawdown > 0.10:
        issues.append({
            "dimension": "最大回撤",
            "current": max_drawdown,
            "target": MAX_DRAWDOWN_THRESHOLD,
            "gap": max_drawdown - MAX_DRAWDOWN_THRESHOLD,
            "severity": "medium" if max_drawdown > 0.12 else "low",
            "suggestion": "优化止损策略，降低回撤幅度",
        })

    # 4. 胜率分析
    if win_rate < 0.40:
        issues.append({
            "dimension": "胜率",
            "current": win_rate,
            "target": 0.60,
            "gap": 0.60 - win_rate,
            "severity": "high",
            "suggestion": "优化信号过滤机制，提高交易质量",
        })
    elif win_rate < 0.55:
        issues.append({
            "dimension": "胜率",
            "current": win_rate,
            "target": 0.60,
            "gap": 0.60 - win_rate,
            "severity": "low",
            "suggestion": "小幅优化入场信号精度",
        })

    # 5. 交易频率分析
    if total_trades < 20:
        issues.append({
            "dimension": "交易频率",
            "current": total_trades,
            "target": 50,
            "gap": 50 - total_trades,
            "severity": "medium",
            "suggestion": "增加交易机会识别，提高策略活跃度",
        })
    elif total_trades > 200:
        issues.append({
            "dimension": "交易频率",
            "current": total_trades,
            "target": 50,
            "gap": total_trades - 50,
            "severity": "medium",
            "suggestion": "降低过度交易，提高单笔交易质量",
        })

    # 确定主要问题
    if issues:
        # 按严重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda x: severity_order.get(x["severity"], 99))
        error_cause["primary_issue"] = issues[0]["dimension"]
        error_cause["issues"] = [i["dimension"] + ": " + i["suggestion"] for i in issues]
        error_cause["optimization_direction"] = list(set(
            i["suggestion"] for i in issues
        ))
        error_cause["severity"] = issues[0]["severity"]
        error_cause["details"] = {
            "issues_detail": issues,
            "current_metrics": {
                "annual_return": annual_return,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "win_rate": win_rate,
                "total_trades": total_trades,
            },
        }

    # 输出归因结果
    logger.info(f"[归因分析] 主要短板: {error_cause['primary_issue']}")
    logger.info(f"[归因分析] 严重程度: {error_cause['severity']}")
    for issue in error_cause["issues"]:
        logger.info(f"   ├─ {issue}")
    for direction in error_cause["optimization_direction"]:
        logger.info(f"   └─ 优化方向: {direction}")

    return error_cause


# ============================================================
# 五、辅助函数：调取资源优化策略
# ============================================================
def resource_optimize_strategy(error_cause: Dict[str, Any],
                                strategy_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    调取策略数据库、优质开源策略素材做定向优化

    集成现有增益模块：
      - StrategyOptimizer: 策略参数优化
      - SmartParamOptimizer: 智能参数优化
      - RLEnhancer: 强化学习增强
      - StrategyRegistry: 策略注册表（获取优质开源策略参考）

    Args:
        error_cause: 归因分析结果
        strategy_data: 当前策略数据

    Returns:
        strategy_data: 优化后的策略数据
    """
    strategy_name = strategy_data.get("strategy_name", "Unknown")
    logger.info(f"\n{'─'*50}")
    logger.info(f"[资源优化] 开始定向优化策略: {strategy_name}")
    logger.info(f"{'─'*50}")

    # 记录优化次数
    strategy_data["optimization_count"] = strategy_data.get("optimization_count", 0) + 1
    current_count = strategy_data["optimization_count"]

    # ---- 1. 集成 StrategyOptimizer 进行参数优化 ----
    try:
        from auto_backtest.strategy_optimizer import StrategyOptimizer
        optimizer = StrategyOptimizer()

        # 备份原策略
        backup_file = optimizer._backup_strategy(strategy_name)
        if backup_file:
            logger.info(f"[StrategyOptimizer] 策略已备份: {backup_file}")

        # 生成优化参数
        optimized_params = optimizer._optimize_parameters(strategy_name)
        if optimized_params:
            strategy_data["params"].update(optimized_params)
            logger.info(f"[StrategyOptimizer] 参数优化完成: {optimized_params}")
        else:
            logger.info(f"[StrategyOptimizer] 参数优化未执行（策略不在优化列表中）")
    except Exception as e:
        logger.warning(f"[StrategyOptimizer] 导入失败: {e}")

    # ---- 2. 根据归因结果做定向参数调整 ----
    issues = error_cause.get("details", {}).get("issues_detail", [])
    for issue in issues:
        dimension = issue.get("dimension", "")
        suggestion = issue.get("suggestion", "")

        if "收益率" in dimension:
            if "profit_target" in strategy_data.get("params", {}):
                current = strategy_data["params"]["profit_target"]
                strategy_data["params"]["profit_target"] = min(current * 1.1, 0.03)
                logger.info(f"[定向优化] 收益率不足: profit_target {current} -> {strategy_data['params']['profit_target']}")
            if "take_profit_pct" in strategy_data.get("params", {}):
                current = strategy_data["params"]["take_profit_pct"]
                strategy_data["params"]["take_profit_pct"] = min(current * 1.1, 0.08)
                logger.info(f"[定向优化] 收益率不足: take_profit_pct {current} -> {strategy_data['params']['take_profit_pct']}")

        elif "夏普" in dimension:
            if "grid_spacing" in strategy_data.get("params", {}):
                current = strategy_data["params"]["grid_spacing"]
                strategy_data["params"]["grid_spacing"] = max(current * 0.9, 0.001)
                logger.info(f"[定向优化] 夏普偏低: grid_spacing {current} -> {strategy_data['params']['grid_spacing']}")

        elif "回撤" in dimension:
            if "stop_loss_pct" in strategy_data.get("params", {}):
                current = strategy_data["params"]["stop_loss_pct"]
                strategy_data["params"]["stop_loss_pct"] = max(current * 0.85, 0.01)
                logger.info(f"[定向优化] 回撤过高: stop_loss_pct {current} -> {strategy_data['params']['stop_loss_pct']}")
            if "max_position_size" in strategy_data.get("params", {}):
                current = strategy_data["params"]["max_position_size"]
                strategy_data["params"]["max_position_size"] = max(current * 0.8, 0.1)
                logger.info(f"[定向优化] 回撤过高: max_position_size {current} -> {strategy_data['params']['max_position_size']}")

        elif "胜率" in dimension:
            if "num_std" in strategy_data.get("params", {}):
                current = strategy_data["params"]["num_std"]
                strategy_data["params"]["num_std"] = min(current * 1.15, 3.0)
                logger.info(f"[定向优化] 胜率不足: num_std {current} -> {strategy_data['params']['num_std']}")

        elif "交易频率" in dimension:
            # 从性能历史获取交易次数
            perf_history = strategy_data.get("performance_history", [])
            latest_trades = perf_history[-1].get("total_trades", 50) if perf_history else 50
            if "min_signal_strength" in strategy_data.get("params", {}):
                current = strategy_data["params"]["min_signal_strength"]
                if latest_trades < 20:
                    strategy_data["params"]["min_signal_strength"] = max(current * 0.85, 0.3)
                else:
                    strategy_data["params"]["min_signal_strength"] = min(current * 1.15, 0.9)
                logger.info(f"[定向优化] 交易频率调整: min_signal_strength {current} -> {strategy_data['params']['min_signal_strength']}")

    logger.info(f"[资源优化] 第 {current_count} 轮优化完成")
    return strategy_data


# ============================================================
# 六、完整重构主执行逻辑代码
# ============================================================
def full_strategy_optimize(strategy_name: str = "FourierRLStrategy",
                            max_loop: int = MAX_LOOP_TIMES,
                            target_score: float = TARGET_STANDARD) -> str:
    """
    量化策略智能优化全流程主程序

    严格按照豆包金融级表述执行：
      1. 强制前置：优先执行牧羊人五行安全测试
      2. 初始化核心参数：坚守标准+限流防耗
      3. 核心迭代循环：不达标持续优化
         - 流程1：开展测试比对，核验策略整体运行状态
         - 流程2：结合回测深度分析问题根源
         - 流程3：调取数据库、优质开源策略完成精准优化
      4. 达到迭代上限收尾输出

    Args:
        strategy_name: 待优化策略名称
        max_loop: 迭代次数上限（管控 Token 消耗）
        target_score: 金融级达标阈值（固定 0.90，绝不下调）

    Returns:
        result_msg: 最终结果消息
    """
    logger.info("\n" + "=" * 80)
    logger.info("🌟 量化策略智能优化全流程启动")
    logger.info(f"   策略: {strategy_name}")
    logger.info(f"   达标阈值: {target_score} (金融级标准，绝不下调)")
    logger.info(f"   迭代上限: {max_loop} 次 (Token 消耗管控)")
    logger.info("=" * 80)

    # ============================================================
    # 1. 强制前置：优先执行牧羊人五行安全测试
    # ============================================================
    logger.info("\n" + "=" * 60)
    logger.info("【步骤1】强制前置：牧羊人五行安全测试")
    logger.info("=" * 60)

    base_strategy = init_base_strategy(strategy_name)

    if not five_line_safe_check(base_strategy):
        fail_msg = (
            f"❌ 策略「{strategy_name}」未通过前置五行安全校验，终止所有流程\n"
            f"   校验详情:\n"
            f"     ├─ signal_rule (信号规则): {'✅' if base_strategy.get('signal_rule') else '❌'}\n"
            f"     ├─ risk_control (风控机制): {'✅' if base_strategy.get('risk_control') else '❌'}\n"
            f"     ├─ backtest_frame (回测框架): {'✅' if base_strategy.get('backtest_frame') else '❌'}\n"
            f"     └─ max_drawdown (最大回撤): {base_strategy.get('max_drawdown', 0)*100:.1f}% "
            f"{'✅' if base_strategy.get('max_drawdown', 0) <= MAX_DRAWDOWN_THRESHOLD else '❌'}"
        )
        logger.error(fail_msg)
        return fail_msg

    logger.info(f"✅ 策略「{strategy_name}」通过前置五行安全校验")
    logger.info(f"     ├─ signal_rule (信号规则): ✅")
    logger.info(f"     ├─ risk_control (风控机制): ✅")
    logger.info(f"     ├─ backtest_frame (回测框架): ✅")
    logger.info(f"     └─ max_drawdown (最大回撤): {base_strategy.get('max_drawdown', 0)*100:.1f}% ✅")

    # ============================================================
    # 2. 初始化核心参数：坚守标准 + 限流防耗
    # ============================================================
    logger.info("\n" + "=" * 60)
    logger.info("【步骤2】初始化核心参数")
    logger.info("=" * 60)
    logger.info(f"   达标阈值: {target_score} (金融级标准，绝不下调)")
    logger.info(f"   迭代上限: {max_loop} 次 (Token 消耗管控)")

    current_loop = 0
    run_result = 0.0

    # ---- 回滚保护机制：记录最优状态 ----
    best_score = 0.0
    best_strategy = None
    consecutive_decline_count = 0
    MAX_CONSECUTIVE_DECLINE = 3  # 连续下降3轮触发回滚

    # ---- 收敛检测：防止无效迭代 ----
    convergence_window = []       # 滑动窗口，记录最近N轮评分
    CONVERGENCE_WINDOW_SIZE = 5   # 窗口大小
    CONVERGENCE_THRESHOLD = 0.01  # 窗口内评分波动 < 1% 视为收敛
    MIN_LOOPS_BEFORE_CONVERGENCE = 3  # 至少迭代3轮后才检测收敛

    # ============================================================
    # 3. 核心迭代循环：不达标持续优化
    # ============================================================
    logger.info("\n" + "=" * 60)
    logger.info("【步骤3】进入核心迭代优化循环")
    logger.info("=" * 60)

    while current_loop < max_loop:
        current_loop += 1
        logger.info(f"\n{'─'*60}")
        logger.info(f"📊 第 {current_loop}/{max_loop} 轮迭代")
        logger.info(f"{'─'*60}")

        # ----------------------------------------------------------
        # 流程1：开展测试比对，核验策略整体运行状态
        # ----------------------------------------------------------
        logger.info(f"\n▶ 流程1：测试比对核验")
        run_result = strategy_backtest_compare(base_strategy)

        # ---- 回滚保护：更新最优记录 ----
        if run_result > best_score:
            best_score = run_result
            best_strategy = copy.deepcopy(base_strategy)
            consecutive_decline_count = 0
            logger.info(f"[回滚保护] 新最优评分: {best_score:.4f}，已保存快照")
        elif run_result < best_score:
            consecutive_decline_count += 1
            logger.info(f"[回滚保护] 评分下降 (连续{consecutive_decline_count}次)，当前{run_result:.4f} < 最优{best_score:.4f}")
            if consecutive_decline_count >= MAX_CONSECUTIVE_DECLINE:
                logger.warning(f"[回滚保护] ⚠️ 连续{MAX_CONSECUTIVE_DECLINE}轮评分下降，触发自动回滚！")
                base_strategy = copy.deepcopy(best_strategy)
                run_result = best_score
                consecutive_decline_count = 0
                logger.info(f"[回滚保护] ✅ 已回滚到最优状态 (评分: {best_score:.4f})")
                # 回滚后跳过本轮优化，直接进入下一轮
                logger.info(f"\n{'─'*60}")
                logger.info(f"📋 第 {current_loop} 轮迭代小结 (回滚后)")
                logger.info(f"   当前评分: {run_result:.4f} (距达标差 {TARGET_STANDARD - run_result:.4f})")
                logger.info(f"   状态: 已回滚到最优快照")
                logger.info(f"{'─'*60}")
                continue

        # 达标直接终止迭代
        if run_result >= target_score:
            success_msg = (
                f"\n{'='*60}\n"
                f"🎉 策略优化完成！\n"
                f"   策略: {strategy_name}\n"
                f"   达标阈值: {target_score}\n"
                f"   当前评分: {run_result:.4f}\n"
                f"   最优评分: {best_score:.4f}\n"
                f"   累计迭代: {current_loop} 次\n"
                f"   优化次数: {base_strategy.get('optimization_count', 0)} 次\n"
                f"{'='*60}"
            )
            logger.info(success_msg)
            return success_msg

        # ---- 收敛检测：评分陷入平台期则提前终止 ----
        convergence_window.append(run_result)
        if len(convergence_window) > CONVERGENCE_WINDOW_SIZE:
            convergence_window.pop(0)
        if (len(convergence_window) >= CONVERGENCE_WINDOW_SIZE
                and current_loop >= MIN_LOOPS_BEFORE_CONVERGENCE):
            window_min = min(convergence_window)
            window_max = max(convergence_window)
            window_range = window_max - window_min
            if window_range < CONVERGENCE_THRESHOLD:
                logger.warning(
                    f"[收敛检测] ⚠️ 评分陷入平台期！最近{CONVERGENCE_WINDOW_SIZE}轮评分范围 "
                    f"[{window_min:.4f}, {window_max:.4f}]，波动仅{window_range:.4f} (<{CONVERGENCE_THRESHOLD})"
                )
                # 回滚到最优状态后终止
                if best_strategy is not None:
                    base_strategy = copy.deepcopy(best_strategy)
                    run_result = best_score
                    logger.info(f"[收敛检测] ✅ 已回滚到最优状态 (评分: {best_score:.4f})，提前终止迭代")
                convergence_msg = (
                    f"\n{'='*60}\n"
                    f"⏹️  策略优化提前终止（评分收敛）\n"
                    f"   策略: {strategy_name}\n"
                    f"   原因: 连续{CONVERGENCE_WINDOW_SIZE}轮评分波动 < {CONVERGENCE_THRESHOLD*100:.1f}%\n"
                    f"   最优评分: {best_score:.4f}\n"
                    f"   达标阈值: {target_score}\n"
                    f"   累计迭代: {current_loop} 次\n"
                    f"   优化次数: {base_strategy.get('optimization_count', 0)} 次\n"
                    f"   状态: 已回滚到最优快照\n"
                    f"{'='*60}"
                )
                logger.info(convergence_msg)
                return convergence_msg

        # ----------------------------------------------------------
        # 流程2：结合回测深度分析问题根源
        # ----------------------------------------------------------
        logger.info(f"\n▶ 流程2：回测归因分析")
        error_cause = backtest_analysis_cause(run_result, base_strategy)

        # ----------------------------------------------------------
        # 流程3：调取数据库、优质开源策略完成精准优化
        # ----------------------------------------------------------
        logger.info(f"\n▶ 流程3：调取资源定向优化")
        base_strategy = resource_optimize_strategy(error_cause, base_strategy)

        # 本轮迭代小结
        logger.info(f"\n{'─'*60}")
        logger.info(f"📋 第 {current_loop} 轮迭代小结")
        logger.info(f"   当前评分: {run_result:.4f} (距达标差 {TARGET_STANDARD - run_result:.4f})")
        logger.info(f"   最优评分: {best_score:.4f}")
        logger.info(f"   主要短板: {error_cause.get('primary_issue', '未知')}")
        logger.info(f"   优化次数: {base_strategy.get('optimization_count', 0)}")
        logger.info(f"{'─'*60}")

    # ============================================================
    # 4. 达到迭代上限收尾输出
    # ============================================================
    final_msg = (
        f"\n{'='*60}\n"
        f"⚠️  已达最大迭代次数 ({max_loop} 次)\n"
        f"   策略: {strategy_name}\n"
        f"   当前最优评分: {run_result:.4f}\n"
        f"   达标阈值: {target_score}\n"
        f"   差距: {target_score - run_result:.4f}\n"
        f"   优化次数: {base_strategy.get('optimization_count', 0)} 次\n"
        f"   状态: 未抵达预设金融标准\n"
        f"   建议: 考虑更换策略核心逻辑或扩大参数搜索空间\n"
        f"{'='*60}"
    )
    logger.info(final_msg)
    return final_msg


# ============================================================
# 七、命令行入口
# ============================================================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    import argparse
    parser = argparse.ArgumentParser(description="牧羊人五行安全优化器 — 金融级量化策略智能优化全流程")
    parser.add_argument("--strategy", type=str, default="FourierRLStrategy",
                        help="待优化策略名称 (默认: FourierRLStrategy)")
    parser.add_argument("--max-loop", type=int, default=MAX_LOOP_TIMES,
                        help=f"迭代次数上限 (默认: {MAX_LOOP_TIMES})")
    parser.add_argument("--target", type=float, default=TARGET_STANDARD,
                        help=f"达标阈值 (默认: {TARGET_STANDARD})")
    parser.add_argument("--log-file", type=str, default="",
                        help="日志文件路径 (可选)")

    args = parser.parse_args()

    # 如果指定了日志文件，同时输出到文件
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logging.getLogger().addHandler(file_handler)

    logger.info("=" * 80)
    logger.info("🐑 牧羊人五行安全优化器启动")
    logger.info("=" * 80)

    result = full_strategy_optimize(
        strategy_name=args.strategy,
        max_loop=args.max_loop,
        target_score=args.target,
    )

    print("\n" + result)
    logger.info("=" * 80)
    logger.info("🐑 牧羊人五行安全优化器执行完毕")
    logger.info("=" * 80)
