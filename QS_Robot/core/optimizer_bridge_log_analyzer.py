"""
优化器桥接日志分析脚本
=====================
针对 optimizer_bridge_mock.js 的23个日志点，自动统计高频错误场景并输出报告。

23个日志点清单:
  [OptimizerBridge] 面板打开...                  (info)
  [OptimizerBridge] 面板状态:                     (info)
  [OptimizerBridge] 开始填充下拉框...             (info)
  [OptimizerBridge] 策略数据源:                   (info)
  [OptimizerBridge] allStrategies为空             (warn)
  [OptimizerBridge] 优化器数据源:                 (info)
  [OptimizerBridge] /api/optimizer/list 请求失败  (warn)
  [OptimizerBridge] 策略切换:                     (info)
  [OptimizerBridge] 策略详情:                     (info)
  [OptimizerBridge] 未找到策略详情                (warn)
  [OptimizerBridge] 执行优化:                     (info)
  [OptimizerBridge] 参数不完整, 终止执行          (warn)
  [OptimizerBridge] API响应:                      (info)
  [OptimizerBridge] 优化成功:                     (info)
  [OptimizerBridge] 优化失败:                     (error)
  [OptimizerBridge] 网络错误:                     (error)
  [OptimizerBridge Mock] 策略未选择               (info)
  [OptimizerBridge Mock] 优化器未选择             (info)
  [OptimizerBridge Mock] 生成Mock数据:            (info)
  [OptimizerBridge Mock] Mock结果:                (info)
  [OptimizerBridgeMock] 工具函数已加载            (info)

用法:
  python core/optimizer_bridge_log_analyzer.py [log_file]
  python core/optimizer_bridge_log_analyzer.py --mock  # 生成模拟日志并分析
"""
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List

LOG_PATTERN = re.compile(
    r'\[OptimizerBridge(?: Mock|Mock)?\]\s+(.*)'
)


# 23个日志点 → 26个日志点（补充3个遗漏）
LOG_POINTS = {
    "面板-打开": {"category": "UI", "severity": "info", "pattern": "面板打开"},
    "面板-状态": {"category": "UI", "severity": "info", "pattern": "面板状态"},
    "面板-关闭": {"category": "UI", "severity": "info", "pattern": "面板已关闭"},                         # 新增
    "面板-填充下拉框": {"category": "UI", "severity": "info", "pattern": "开始填充下拉框"},
    "策略-数据源": {"category": "DATA", "severity": "info", "pattern": "策略数据源"},
    "策略-数据源为空": {"category": "DATA", "severity": "warn", "pattern": "allStrategies为空"},
    "优化器-数据源": {"category": "DATA", "severity": "info", "pattern": "优化器数据源"},
    "优化器-数据源为空": {"category": "DATA", "severity": "warn", "pattern": "优化器数据源为空"},        # 新增
    "优化器-API失败": {"category": "DATA", "severity": "warn", "pattern": "api/optimizer/list 请求失败"},
    "策略-切换": {"category": "UI", "severity": "info", "pattern": "策略切换"},
    "策略-详情": {"category": "DATA", "severity": "info", "pattern": "策略详情"},
    "策略-未找到": {"category": "DATA", "severity": "warn", "pattern": "未找到策略详情"},
    "优化-执行": {"category": "EXEC", "severity": "info", "pattern": "执行优化"},
    "优化-参数不完整": {"category": "EXEC", "severity": "warn", "pattern": "参数不完整"},
    "优化-API响应": {"category": "EXEC", "severity": "info", "pattern": "API响应"},
    "优化-成功": {"category": "EXEC", "severity": "info", "pattern": "优化成功"},
    "优化-失败": {"category": "EXEC", "severity": "error", "pattern": "优化失败"},
    "优化-网络错误": {"category": "EXEC", "severity": "error", "pattern": "网络错误"},
    "Mock-策略未选择": {"category": "MOCK", "severity": "info", "pattern": "策略未选择"},
    "Mock-优化器未选择": {"category": "MOCK", "severity": "info", "pattern": "优化器未选择"},
    "Mock-生成数据": {"category": "MOCK", "severity": "info", "pattern": "生成Mock数据"},
    "Mock-结果": {"category": "MOCK", "severity": "info", "pattern": "Mock结果"},
    "Mock-结果渲染": {"category": "MOCK", "severity": "info", "pattern": "结果渲染"},                     # 新增
    "Mock-工具加载": {"category": "MOCK", "severity": "info", "pattern": "工具函数已加载"},
}


def parse_logs(log_content: str) -> List[Dict[str, Any]]:
    """解析日志内容，提取OptimizerBridge相关日志"""
    entries = []
    for line in log_content.splitlines():
        match = LOG_PATTERN.search(line)
        if not match:
            continue
        message = match.group(1).strip()
        # 识别日志点
        point_name = None
        for name, info in sorted(LOG_POINTS.items(), key=lambda x: -len(x[1]["pattern"])):
            if info["pattern"].lower() in message.lower():
                point_name = name
                break
        entries.append({
            "timestamp": _extract_timestamp(line),
            "message": message,
            "point": point_name or "未知",
            "category": LOG_POINTS.get(point_name, {}).get("category", "UNKNOWN"),
            "severity": LOG_POINTS.get(point_name, {}).get("severity", "info"),
            "raw": line,
        })
    return entries


def _extract_timestamp(line: str) -> str:
    """从日志行提取时间戳"""
    m = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
    return m.group(1) if m else ""


def analyze(entries: List[Dict]) -> Dict[str, Any]:
    """分析日志条目，输出统计报告"""
    if not entries:
        return {"error": "无OptimizerBridge日志条目"}

    total = len(entries)
    severities = Counter(e["severity"] for e in entries)
    categories = Counter(e["category"] for e in entries)
    points = Counter(e["point"] for e in entries)

    # 高频错误场景
    errors = [e for e in entries if e["severity"] in ("error", "warn")]
    error_scenarios = Counter(e["point"] for e in errors)

    # 未触发的日志点
    all_points = set(LOG_POINTS.keys())
    triggered = set(e["point"] for e in entries if e["point"] != "未知")
    missing = all_points - triggered

    # 时序分析
    sequence = _analyze_sequence(entries)

    return {
        "total": total,
        "by_severity": dict(severities),
        "by_category": dict(categories),
        "by_point": dict(points.most_common()),
        "error_scenarios": dict(error_scenarios.most_common()),
        "missing_points": sorted(missing),
        "coverage": f"{len(triggered)}/{len(all_points)} ({len(triggered)/len(all_points)*100:.1f}%)",
        "sequence_violations": sequence["violations"],
        "health_score": _calc_health_score(severities, len(triggered), len(all_points)),
    }


def _analyze_sequence(entries: List[Dict]) -> Dict:
    """分析日志时序，检测异常流程"""
    violations = []
    seen = set()

    for e in entries:
        # 检查"参数不完整"后是否仍出现了"优化成功"
        if e["point"] == "优化-参数不完整":
            if "优化-成功" in seen:
                violations.append("参数不完整前已出现优化成功(时序异常)")
        # 检查"网络错误"是否早于"API响应"
        if e["point"] == "优化-网络错误" and "优化-API响应" not in seen:
            violations.append("网络错误出现在API响应前(可能预检失败)")
        # 检查Mock是否在真实API失败后触发
        if e["point"] == "Mock-生成数据" and "优化-失败" in seen:
            violations.append("Mock降级触发(优化失败后回退到Mock)")
        seen.add(e["point"])

    return {"violations": violations if violations else ["无异常"]}


def _calc_health_score(severities: Counter, triggered: int, total_points: int) -> float:
    """计算健康评分 (0-100)"""
    error_count = severities.get("error", 0)
    warn_count = severities.get("warn", 0)
    info_count = severities.get("info", 0)
    total = error_count + warn_count + info_count
    if total == 0:
        return 100.0

    # 错误扣分: 每个error -15, 每个warn -5
    score = 100.0
    score -= error_count * 15.0
    score -= warn_count * 5.0
    # 覆盖率奖励: 覆盖率 < 80% 扣分
    coverage = triggered / total_points if total_points > 0 else 0
    if coverage < 0.8:
        score -= (0.8 - coverage) * 100

    return max(0.0, min(100.0, round(score, 1)))


def generate_mock_logs() -> str:
    """生成模拟日志用于测试分析脚本"""
    now = datetime.now()
    lines = []

    def log(ts_offset, msg):
        ts = datetime.fromtimestamp(now.timestamp() + ts_offset).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        lines.append(f"{ts} - INFO - [OptimizerBridge] {msg}")

    def log_mock(ts_offset, msg):
        ts = datetime.fromtimestamp(now.timestamp() + ts_offset).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        lines.append(f"{ts} - INFO - [OptimizerBridge Mock] {msg}")

    def log_error(ts_offset, msg):
        ts = datetime.fromtimestamp(now.timestamp() + ts_offset).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        lines.append(f"{ts} - ERROR - [OptimizerBridge] {msg}")

    def log_warn(ts_offset, msg):
        ts = datetime.fromtimestamp(now.timestamp() + ts_offset).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        lines.append(f"{ts} - WARNING - [OptimizerBridge] {msg}")

    def log_mock_init(ts_offset):
        ts = datetime.fromtimestamp(now.timestamp() + ts_offset).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        lines.append(f"{ts} - INFO - [OptimizerBridgeMock] 工具函数已加载: generateOptimizerMockResult, batchGenerateOptimizerMock, generateOptimizerHeatmapMock")

    # 场景1: 正常流程
    log_mock_init(0)
    log(1, "面板打开...")
    log(1.05, "面板状态: block(打开)")
    log(1.1, "开始填充下拉框...")
    log(1.15, "策略数据源: allStrategies, 数量=14")
    log(1.2, "优化器数据源: /api/optimizer/list, 数量=8")
    log(2, "策略切换: fourier_rl")
    log(2.05, "策略详情: {type: rl, version: 2.1, score: 85}")
    log(3, "执行优化: 策略=fourier_rl, 优化器=tau_cluster")
    log(5.2, "API响应: success=True, 耗时=2.18s")
    log(5.21, "优化成功: 夏普=2.83, 参数={\"u\":0.65,\"n\":5}")

    # 场景2: 参数不完整
    log(10, "面板打开...")
    log(10.05, "面板状态: block(打开)")
    log(10.1, "开始填充下拉框...")
    log(10.2, "策略数据源: allStrategies, 数量=14")
    log(10.25, "优化器数据源: /api/optimizer/list, 数量=8")
    log(11, "执行优化: 策略=(空), 优化器=(空)")
    log_warn(11.01, "参数不完整, 终止执行")

    # 场景3: API失败 + Mock降级
    log(15, "面板打开...")
    log(15.05, "面板状态: block(打开)")
    log(15.1, "开始填充下拉框...")
    log(15.2, "策略数据源: allStrategies, 数量=14")
    log_warn(15.25, "/api/optimizer/list 请求失败, 使用默认优化器列表: NetworkError")
    log(16, "策略切换: gyro")
    log(16.05, "策略详情: {type: physics, version: 7.0, score: 92}")
    log(17, "执行优化: 策略=gyro, 优化器=tau_cluster")
    log_error(22, "网络错误: Failed to fetch")
    log_mock(22.5, "策略未选择, 使用默认: mock_strategy")
    log_mock(22.51, "优化器未选择, 使用默认: tau_cluster")
    log_mock(22.52, "生成Mock数据: 策略=mock_strategy, 优化器=tau_cluster")
    log_mock(22.53, "Mock结果: {sharpe: 2.15, drawdown: 7.3, iterations: 145}")

    # 场景4: 正常+Mock混用
    log(25, "面板打开...")
    log(25.05, "面板状态: block(打开)")
    log(25.1, "开始填充下拉框...")
    log(25.2, "策略数据源: allStrategies, 数量=14")
    log(25.25, "优化器数据源: /api/optimizer/list, 数量=8")
    log(26, "策略切换: shepherd_rotation")
    log(26.05, "策略详情: {type: shepherd, version: 6.0, score: 78}")
    log(27, "执行优化: 策略=shepherd_rotation, 优化器=shepherd_optimizer")
    log_error(32, "优化失败: optimizer timeout")
    log_mock(32.5, "生成Mock数据: 策略=shepherd_rotation, 优化器=shepherd_optimizer")
    log_mock(32.51, "Mock结果: {sharpe: 1.89, drawdown: 12.5, iterations: 98}")

    # 场景5: 数据源为空
    log(35, "面板打开...")
    log(35.05, "面板状态: block(打开)")
    log(35.1, "开始填充下拉框...")
    log_warn(35.15, "allStrategies为空，策略下拉框仅含默认选项")
    log_warn(35.2, "/api/optimizer/list 请求失败, 使用默认优化器列表: 401 Unauthorized")

    # 场景6: 面板关闭 + 优化器数据源为空
    log(40, "面板打开...")
    log(40.05, "面板状态: block(打开)")
    log(40.1, "开始填充下拉框...")
    log(40.15, "策略数据源: allStrategies, 数量=0")
    log_warn(40.16, "allStrategies为空，策略下拉框仅含默认选项")
    log(40.2, "优化器数据源: /api/optimizer/list, 数量=0")
    log_warn(40.21, "优化器数据源为空，使用默认优化器列表")
    log(41, "策略切换: nonexistent_strategy")
    log_warn(41.05, "未找到策略详情: nonexistent_strategy")
    log(42, "面板打开...")
    log(42.05, "面板状态: none(关闭)")
    log(42.06, "面板已关闭")

    # 场景7: Mock结果渲染（完整路径）
    log_mock(45, "策略未选择, 使用默认: mock_strategy")
    log_mock(45.01, "优化器未选择, 使用默认: tau_cluster")
    log_mock(45.02, "生成Mock数据: 策略=mock_strategy, 优化器=tau_cluster")
    log_mock(45.03, "Mock结果: {sharpe: 2.83, drawdown: 5.2, iterations: 156}")
    log_mock(45.04, "结果渲染: <span style=...")

    return "\n".join(lines)


def main():
    log_content = None
    if len(sys.argv) > 1 and sys.argv[1] != "--mock":
        # 从文件读取
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            log_content = f.read()
    elif "--mock" in sys.argv:
        log_content = generate_mock_logs()
        print("=== 模拟日志 ===\n" + log_content + "\n")
    else:
        print("用法: python core/optimizer_bridge_log_analyzer.py [--mock] [log_file]")
        print("  --mock  生成模拟日志并分析")
        print("  log_file  分析指定日志文件")
        sys.exit(0)

    entries = parse_logs(log_content)
    report = analyze(entries)

    print("=" * 60)
    print("  优化器桥接日志分析报告")
    print("=" * 60)
    print(f"  总条目: {report['total']}")
    print(f"  覆盖率: {report['coverage']}")
    print(f"  健康评分: {report['health_score']}/100")
    print()
    print("  按严重性:")
    for sev, count in report["by_severity"].items():
        bar = "█" * min(count, 20)
        print(f"    {sev:6s}: {count:3d} {bar}")
    print()
    print("  按分类:")
    for cat, count in report["by_category"].items():
        print(f"    {cat:6s}: {count:3d}")
    print()
    print("  高频错误场景:")
    if report["error_scenarios"]:
        for scenario, count in report["error_scenarios"].items():
            print(f"    ⚠ {scenario}: {count}次")
    else:
        print("    ✅ 无错误场景")
    print()
    print("  未触发的日志点:")
    if report["missing_points"]:
        for pt in report["missing_points"]:
            print(f"    ○ {pt}")
    else:
        print("    ✅ 全覆盖")
    print()
    print("  时序异常:")
    for v in report["sequence_violations"]:
        print(f"    {'⚠' if v != '无异常' else '✅'} {v}")

    # 输出JSON
    print("\n  JSON报告: ", end="")
    json_path = f"data/health_reports/optimizer_bridge_log_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        import os
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json_path)
    except Exception as e:
        print(f"保存失败: {e}")


if __name__ == "__main__":
    main()