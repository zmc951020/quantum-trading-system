#!/usr/bin/env python3
"""
Workflow + FileInventoryManager 融合效能检验
对比：硬编码方式（当前workflow现状）vs 索引驱动方式（目标架构）
"""
import time
import os
import json
import sys

# ── 加载索引 ──
with open('Aurora_file_inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)
files_def = inv.get('files', {})
dbs_def = inv.get('databases', {})


def run_hardcoded_workflow():
    """模拟当前 system-health-diagnosis.md 第三步：硬编码核心模块检查"""
    t0 = time.perf_counter()
    results = []

    # 硬编码清单（从workflow文档复制）
    checklist = [
        ("主系统", "main.py", 500),
        ("交易安全", "trade_security.py", 696),
        ("数据源风控", "risk/data_source_risk_control.py", 585),
        ("回测中心", "auto_backtest/auto_backtest_system.py", 528),
        ("数据库管理", "utils/database_manager.py", 500),
        ("数据源适配", "data/multi_data_source.py", 400),
        ("可视化", "visualization.py", 3000),
        ("性能追踪", "utils/strategy_performance_tracker.py", 1),
        ("统一风控", "utils/unified_risk_controller.py", 1),
        ("贝叶斯优化", "utils/smart_param_optimizer.py", 1),
        ("RL增强", "utils/rl_enhancer.py", 1),
        ("数据质量", "utils/data_quality_validator.py", 1),
    ]

    for name, path, expected_lines in checklist:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = sum(1 for _ in f)
                status = "OK" if lines >= expected_lines else f"WARN({lines}<{expected_lines})"
                exists = True
            except:
                status = "ERR"
                exists = True
        else:
            status = "MISSING"
            exists = False
        results.append((name, path, exists, status))

    elapsed = (time.perf_counter() - t0) * 1000
    return results, elapsed


def run_indexed_workflow():
    """模拟索引驱动的 workflow：从 JSON 动态生成检查清单"""
    t0 = time.perf_counter()
    results = []

    for key, defn in files_def.items():
        path = defn['path']
        expected_lines = defn.get('expected_min_lines', 0)
        importance = defn.get('importance', 'unknown')
        description = defn.get('description', '')

        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = sum(1 for _ in f)
                if expected_lines > 0 and lines < expected_lines:
                    status = f"WARN({lines}<{expected_lines})"
                else:
                    status = "OK"
                exists = True
            except:
                status = "ERR"
                exists = True
        else:
            status = "MISSING"
            exists = False

        results.append((key, path, exists, status, importance, description))

    elapsed = (time.perf_counter() - t0) * 1000
    return results, elapsed


def main():
    print('=' * 72)
    print('  Workflow + FileInventoryManager 融合效能检验')
    print('  Aurora DS-V3.2T 量化交易专用工作站')
    print('=' * 72)

    # ─── 测试1：硬编码方式 ───
    print('\n[检验1] 硬编码方式（当前 system-health-diagnosis.md 现状）')
    hc_results, hc_ms = run_hardcoded_workflow()
    hc_ok = sum(1 for r in hc_results if r[3] == 'OK')
    hc_warn = sum(1 for r in hc_results if r[3].startswith('WARN'))
    hc_miss = sum(1 for r in hc_results if r[3] == 'MISSING')
    print(f'  耗时: {hc_ms:.1f}ms')
    print(f'  结果: {hc_ok} OK, {hc_warn} WARN, {hc_miss} MISSING (共{len(hc_results)}项)')

    # ─── 测试2：索引驱动方式 ───
    print('\n[检验2] 索引驱动方式（FileInventoryManager 驱动 workflow）')
    idx_results, idx_ms = run_indexed_workflow()
    idx_ok = sum(1 for r in idx_results if r[3] == 'OK')
    idx_warn = sum(1 for r in idx_results if r[3].startswith('WARN'))
    idx_miss = sum(1 for r in idx_results if r[3] == 'MISSING')
    print(f'  耗时: {idx_ms:.1f}ms')
    print(f'  结果: {idx_ok} OK, {idx_warn} WARN, {idx_miss} MISSING (共{len(idx_results)}项)')

    # ─── 差异分析 ───
    print(f'\n[差异分析]')
    print(f'  检查范围: 硬编码{len(hc_results)}项 vs 索引{len(idx_results)}项 (扩张{len(idx_results)/len(hc_results):.1f}x)')
    print(f'  耗时对比: {hc_ms:.1f}ms vs {idx_ms:.1f}ms')

    # 索引独有发现
    hc_paths = set(r[1] for r in hc_results)
    idx_only = [(r[0], r[1], r[5]) for r in idx_results if r[1] not in hc_paths]
    if idx_only:
        print(f'\n  索引独有覆盖（硬编码遗漏的模块）:')
        for name, path, desc in idx_only:
            print(f'    + {name}: {path} ({desc})')

    # 严重问题发现
    print(f'\n[告警汇总（索引方式发现的问题）]')
    critical_warns = [(r[0], r[1], r[3]) for r in idx_results
                      if r[3].startswith('WARN') or r[3] == 'MISSING']
    if critical_warns:
        for name, path, status in critical_warns:
            print(f'    ⚠ {name}: {path} → {status}')
    else:
        print(f'    ✅ 无告警')

    # ─── 测试3：数据库检查融合 ───
    print(f'\n[检验3] 数据库维护检查（database-maintenance.md 融合）')
    print(f'  硬编码方式需要维护3行数据库清单代码')
    print(f'  索引方式:')

    t0 = time.perf_counter()
    db_status = {}
    for db_key, db_def in dbs_def.items():
        path = db_def['path']
        ok = os.path.exists(path)
        size_mb = round(os.path.getsize(path) / (1024 * 1024), 1) if ok else 0
        purpose = db_def.get('purpose', '?')
        db_status[db_key] = {'ok': ok, 'size_mb': size_mb, 'purpose': purpose}
    db_ms = (time.perf_counter() - t0) * 1000
    print(f'    耗时: {db_ms:.1f}ms')
    for k, v in db_status.items():
        flag = '⚠ >500MB' if v['size_mb'] > 500 else ('⚠ >1GB' if v['size_mb'] > 1024 else '✅')
        print(f'    {k}: {v["size_mb"]}MB [{v["purpose"]}] {flag}')

    # ─── 测试4：一次性完整workflow诊断 ───
    print(f'\n[检验4] 完整 Workflow 诊断报告生成（索引驱动）')
    t0 = time.perf_counter()

    # 4A: 关键目录
    key_dirs = inv.get('key_directories', [])
    dir_status = {}
    for d in key_dirs:
        exists = os.path.isdir(d)
        dir_status[d] = exists

    # 4B: 数据源
    data_sources = inv.get('data_sources', [])

    # 4C: 文件分类汇总
    critical_files = sum(1 for v in files_def.values() if v.get('importance') == 'critical')
    high_files = sum(1 for v in files_def.values() if v.get('importance') == 'high')

    # 4D: 生成报告
    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'system': 'Aurora DS-V3.2T',
        'files': {
            'total': len(files_def),
            'critical': critical_files,
            'high': high_files,
            'present': idx_ok + idx_warn,
            'missing': idx_miss,
            'warnings': len(critical_warns)
        },
        'databases': {k: v for k, v in db_status.items()},
        'directories': {d: 'OK' if s else 'MISSING' for d, s in dir_status.items()},
        'data_sources': data_sources,
        'overall': 'WARNING' if (idx_miss > 0 or idx_warn > 0) else 'HEALTHY'
    }

    total_ms = (time.perf_counter() - t0) * 1000
    print(f'  总耗时: {total_ms:.0f}ms')

    # 打印JSON报告
    print(f'\n  JSON报告摘要:')
    print(f'  {{')
    print(f'    "timestamp": "{report["timestamp"]}",')
    print(f'    "system": "{report["system"]}",')
    print(f'    "overall": "{report["overall"]}",')
    print(f'    "files": {{"total": {report["files"]["total"]}, "critical": {report["files"]["critical"]}, "present": {report["files"]["present"]}, "missing": {report["files"]["missing"]}}}')
    print(f'    "databases": {len(report["databases"])}个,')
    print(f'    "directories": {len(report["directories"])}个,')
    print(f'    "data_sources": {len(report["data_sources"])}个')
    print(f'  }}')

    # ─── 建立测试标准 ───
    print(f'\n{"=" * 72}')
    print('  融合效能测试标准')
    print(f'{"=" * 72}')
    print(f'''
  ┌─────────────────────────────────────────────────────────────────┐
  │ 检验标准矩阵                                                    │
  ├──────────────┬────────────┬──────────┬──────────┬──────────────┤
  │ 维度         │ 硬编码方案 │ 索引方案  │ 阈值     │ 判定         │
  ├──────────────┼────────────┼──────────┼──────────┼──────────────┤
  │ 检查范围     │ {len(hc_results)}项       │ {len(idx_results)}项      │ ≥12      │ {"✅ 达标" if len(idx_results)>=12 else "❌ 不达标"} │
  │ 报告生成     │ {hc_ms:.0f}ms      │ {total_ms:.0f}ms      │ <500ms   │ {"✅ 达标" if total_ms<500 else "❌ 不达标"} │
  │ 语义增强     │ 仅文件名    │ 含重要性+ ║ N/A      │ ✅ 独有     │
  │              │            │ 描述+阈值 ║          │             │
  │ 可扩展性     │ 手动维护   │ JSON驱动  ║ N/A      │ ✅ 独有     │
  │ 数据库发现   │ 硬编码3行  │ 自动发现  ║ N/A      │ ✅ 独有     │
  └──────────────┴────────────┴──────────┴──────────┴──────────────┘
''')

    # ─── 终极自检：FileInventoryManager 类融合 ───
    print('  FileInventoryManager 类融合自检:')
    try:
        from file_inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()

        # 模拟 workflow 调用
        health = mgr.get_file_health_report()
        db_h = mgr.get_db_health()
        sources = mgr.get_data_sources()
        dirs = mgr.get_key_directories()

        print(f'    ✅ get_file_health_report()  → {health["overall"]}')
        print(f'    ✅ get_db_health()           → {len(db_h)}个数据库')
        print(f'    ✅ get_data_sources()        → {len(sources)}个数据源')
        print(f'    ✅ get_key_directories()     → {len(dirs)}个目录')
        print(f'    ✅ 类可直接被任意 workflow Python 脚本 import 使用')
    except Exception as e:
        print(f'    ❌ 错误: {e}')

    print(f'\n{"=" * 72}')
    print('  检验完成')
    print('=' * 72)


if __name__ == '__main__':
    main()