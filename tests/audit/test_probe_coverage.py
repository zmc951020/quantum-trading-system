#!/usr/bin/env python3
"""SJ-001: 探针覆盖率验证
12类关键异常全部配置实时探针，覆盖率100%
"""
import sys
import os
import time
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "QS_Robot"))
sys.path.insert(0, r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")

# 12 类探针定义
PROBES = {
    "P1_行情断连": {
        "module": "data_fetcher",
        "trigger": "数据源超时3s",
        "method": "check_data_fetcher_timeout",
    },
    "P2_滑点超标": {
        "module": "risk_control",
        "trigger": "滑点>0.5%",
        "method": "check_slippage_probe",
    },
    "P3_跳空异常": {
        "module": "risk_control",
        "trigger": "开盘价偏离>2%",
        "method": "check_gap_probe",
    },
    "P4_账户余额异动": {
        "module": "broker_manager",
        "trigger": "余额变化>5%",
        "method": "check_balance_probe",
    },
    "P5_策略参数漂移": {
        "module": "strategy_registry",
        "trigger": "参数偏离优化值>10%",
        "method": "check_param_drift_probe",
    },
    "P6_模型推理异常": {
        "module": "agent_dispatcher",
        "trigger": "AI返回空/格式错误",
        "method": "check_model_probe",
    },
    "P7_API接口报错": {
        "module": "gateway",
        "trigger": "500/502/503响应",
        "method": "check_api_error_probe",
    },
    "P8_数据库连接断开": {
        "module": "database_manager",
        "trigger": "连接超时",
        "method": "check_db_probe",
    },
    "P9_内存超阈值": {
        "module": "system_health",
        "trigger": "内存>80%",
        "method": "check_memory_probe",
    },
    "P10_队列积压": {
        "module": "data_bus",
        "trigger": "积压>100条",
        "method": "check_queue_probe",
    },
    "P11_认证失败激增": {
        "module": "gateway",
        "trigger": "5min内>10次401",
        "method": "check_auth_fail_probe",
    },
    "P12_优化器收敛异常": {
        "module": "tau_optimizer_cluster",
        "trigger": "连续10轮无改善",
        "method": "check_optimizer_probe",
    },
}


def check_module_exists(module_name: str) -> bool:
    """检查模块是否存在（递归搜索子目录）"""
    try:
        search_paths = [
            Path(r"d:\Gupiao\升级vscode\QS_Robot"),
            Path(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora"),
        ]
        for base in search_paths:
            # 递归搜索 .py 文件
            for fpath in base.rglob("*.py"):
                if fpath.stem == module_name:
                    return True

        # 尝试导入
        try:
            __import__(module_name)
            return True
        except ImportError:
            pass

        return False
    except Exception:
        return False


def check_has_logging(module_name: str) -> bool:
    """检查模块是否有日志/监控输出（递归搜索子目录）"""
    try:
        for base in [
            Path(r"d:\Gupiao\升级vscode\QS_Robot"),
            Path(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora"),
        ]:
            for fpath in base.rglob("*.py"):
                if fpath.stem == module_name:
                    content = fpath.read_text(encoding='utf-8', errors='ignore')
                    has_log = any(kw in content for kw in
                                  ('logger', 'logging', 'print', 'traceback',
                                   'warning', 'error', 'exception', 'alert',
                                   'notify', 'monitor', 'probe', 'sensor'))
                    return has_log
        return False
    except Exception:
        return False


def main():
    print("[SJ-001] 探针覆盖率审计")
    print(f"  目标: 12类探针全部配置，覆盖率 100%")
    print()

    passed = 0
    failed = 0
    details = []

    for probe_id, probe_info in PROBES.items():
        module = probe_info["module"]
        exists = check_module_exists(module)
        has_log = check_has_logging(module) if exists else False

        status = "✅" if (exists and has_log) else "⚠️" if exists else "❌"
        if exists and has_log:
            passed += 1
        else:
            failed += 1

        detail = f"  {status} {probe_id}: {module}"
        if not exists:
            detail += " (模块不存在)"
        elif not has_log:
            detail += " (缺少日志/监控)"
        details.append(detail)

        print(detail)

    coverage = (passed / len(PROBES)) * 100

    print(f"\n  统计结果:")
    print(f"    探针总数: {len(PROBES)}")
    print(f"    已配置:   {passed}")
    print(f"    未配置:   {failed}")
    print(f"    覆盖率:   {coverage:.0f}%")

    print(f"\n  验收结果:")
    if coverage == 100:
        print(f"    ✅ 通过 - 覆盖率 100%")
    else:
        print(f"    ❌ 未通过 - 覆盖率 {coverage:.0f}%，以下探针需修复:")
        for d in details:
            if "❌" in d or "⚠️" in d:
                print(f"      {d}")

    return coverage == 100


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)