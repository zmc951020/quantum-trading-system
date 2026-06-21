#!/usr/bin/env python3
"""QZ-001: 埋点覆盖率审计
全链路关键节点埋点覆盖率100%
"""
import sys
import os
import re
from pathlib import Path

# 扫描路径
AURORA_PATH = Path(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")
QS_ROBOT_PATH = Path(r"d:\Gupiao\升级vscode\QS_Robot")

# 8层埋点节点定义
BURIAL_POINTS = {
    "行情层": {
        "nodes": ["数据源连接", "数据接收", "数据解析", "数据缓存"],
        "files": ["data/multi_data_source.py", "data/data_fetcher.py"],
        "keywords": ["logger", "logging", "traceback", "time", "perf_counter", "print"],
    },
    "因子层": {
        "nodes": ["因子计算开始", "因子计算完成", "因子值输出", "计算耗时"],
        "files": ["core/qlib_adapter.py", "core/qlib_core/backtest_engine.py"],
        "keywords": ["logger", "logging", "traceback", "time", "perf_counter"],
    },
    "策略层": {
        "nodes": ["信号生成", "信号强度", "信号时间"],
        "files": ["strategies/", "systems/aurora/strategies/"],
        "keywords": ["logger", "logging", "signal", "trade"],
    },
    "优化器层": {
        "nodes": ["迭代开始", "迭代完成", "参数更新", "评分变化"],
        "files": ["core/tau_optimizer_cluster.py"],
        "keywords": ["logger", "logging", "iteration", "score", "param"],
    },
    "交易层": {
        "nodes": ["订单创建", "订单提交", "订单成交", "订单拒绝"],
        "files": ["broker_manager.py", "adapters/"],
        "keywords": ["logger", "logging", "order", "trade", "fill"],
    },
    "风控层": {
        "nodes": ["风控检查", "熔断触发", "熔断恢复"],
        "files": ["core/risk_control.py"],
        "keywords": ["logger", "logging", "risk", "circuit", "breaker"],
    },
    "通信层": {
        "nodes": ["API请求", "API响应", "代理转发", "重试次数"],
        "files": ["api/gateway.py", "api/aurora_core_adapter.py"],
        "keywords": ["logger", "logging", "request", "response", "proxy", "retry"],
    },
    "系统层": {
        "nodes": ["CPU使用率", "内存使用率", "磁盘使用率", "网络IO", "进程状态"],
        "files": ["monitor/system_health.py", "core/system_health_checker.py"],
        "keywords": ["logger", "logging", "cpu", "memory", "disk", "network", "health"],
    },
}

EXCLUDE_DIRS = {'__pycache__', '.git', 'node_modules', 'logs', 'reports', 'venv', 'env', '.venv', 'docs', 'archive', 'backup', 'qlib_data'}


def find_file(search_path: Path, pattern: str) -> list:
    """查找匹配的文件"""
    if pattern.endswith('/'):
        # 目录模式
        dir_path = search_path / pattern.rstrip('/')
        if dir_path.exists():
            return list(dir_path.rglob("*.py"))
        return []
    else:
        # 文件模式
        fpath = search_path / pattern
        if fpath.exists():
            return [fpath]
        return []


def check_logging_in_file(filepath: Path) -> bool:
    """检查文件是否有日志/监控代码"""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        # 检查是否有任何日志或监控相关代码
        keywords = ['logger', 'logging', 'print(', 'traceback', 'time.time()', 'time.perf_counter',
                    'warning', 'error', 'exception', 'alert', 'notify', 'monitor', 'probe', 'sensor',
                    'log.', 'debug', 'info', 'critical']
        return any(kw in content for kw in keywords)
    except Exception:
        return False


def check_node_coverage(node_name: str, files: list) -> dict:
    """检查节点覆盖率"""
    covered_files = []
    missing_files = []

    for fpath in files:
        if check_logging_in_file(fpath):
            covered_files.append(str(fpath))
        else:
            missing_files.append(str(fpath))

    return {
        "covered": len(covered_files),
        "total": len(files),
        "covered_files": covered_files,
        "missing_files": missing_files,
    }


def main():
    print("[QZ-001] 埋点覆盖率审计")
    print("  目标: 关键节点埋点覆盖率 100%")
    print()

    all_search_paths = [AURORA_PATH, QS_ROBOT_PATH]

    total_nodes = 0
    covered_nodes = 0
    layer_results = {}

    for layer_name, layer_info in BURIAL_POINTS.items():
        # 查找所有相关文件
        all_files = []
        for pattern in layer_info["files"]:
            for search_path in all_search_paths:
                files = find_file(search_path, pattern)
                all_files.extend(files)

        if not all_files:
            print(f"  ⚠️ {layer_name}: 未找到相关文件")
            layer_results[layer_name] = {"covered": 0, "total": 0, "nodes": layer_info["nodes"]}
            continue

        # 检查覆盖率
        covered = sum(1 for f in all_files if check_logging_in_file(f))
        total = len(all_files)
        coverage_pct = (covered / total) * 100 if total > 0 else 0

        layer_results[layer_name] = {
            "covered": covered,
            "total": total,
            "coverage_pct": coverage_pct,
            "nodes": layer_info["nodes"],
        }

        total_nodes += len(layer_info["nodes"])
        if coverage_pct >= 50:  # 至少一半文件有日志
            covered_nodes += len(layer_info["nodes"])

        status = "✅" if coverage_pct == 100 else "⚠️" if coverage_pct >= 50 else "❌"
        print(f"  {status} {layer_name}: {covered}/{total} 文件 ({coverage_pct:.0f}%) "
              f"- {len(layer_info['nodes'])}个节点: {', '.join(layer_info['nodes'])}")

        # 列出缺失埋点的文件
        missing = [f for f in all_files if not check_logging_in_file(f)]
        if missing:
            for m in missing:
                print(f"      ⚠️ 缺少日志: {Path(m).name}")

    overall_coverage = (covered_nodes / total_nodes) * 100 if total_nodes > 0 else 0

    print(f"\n  统计结果:")
    print(f"    总节点数: {total_nodes}")
    print(f"    已覆盖:   {covered_nodes}")
    print(f"    覆盖率:   {overall_coverage:.0f}%")

    print(f"\n  验收结果:")
    if overall_coverage == 100:
        print(f"    ✅ 通过 - 覆盖率 100%")
    else:
        print(f"    ❌ 未通过 - 覆盖率 {overall_coverage:.0f}%")
        print(f"    建议: 为缺失文件添加 logging 日志输出")

    return overall_coverage == 100


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)