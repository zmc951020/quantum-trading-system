#!/usr/bin/env python3
"""
FileInventoryManager 效能基准测试
评估4个维度：加载速度、查询加速、增量检测、数据库检查
"""
import time
import os
import json


def load_json():
    """测试1：JSON索引加载速度"""
    t0 = time.perf_counter()
    with open('Aurora_file_inventory.json', 'r', encoding='utf-8') as f:
        inv = json.load(f)
    t1 = time.perf_counter()
    files_count = len(inv.get('files', {}))
    dbs_count = len(inv.get('databases', {}))
    json_size = os.path.getsize('Aurora_file_inventory.json')
    return inv, (t1 - t0) * 1000, files_count, dbs_count, json_size


def walk_all_files():
    """测试2A：传统os.walk全量扫描"""
    t0 = time.perf_counter()
    file_count = 0
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules', '.venv', '.vscode')]
        file_count += len(files)
    t1 = time.perf_counter()
    return file_count, (t1 - t0) * 1000


def indexed_check(inv):
    """测试2B：索引定向查询（含关键文件行数验证）"""
    t0 = time.perf_counter()
    file_count = len(inv.get('files', {}))
    checked_lines = 0
    for k, v in inv.get('files', {}).items():
        p = v.get('path', '')
        if os.path.exists(p) and 'expected_min_lines' in v:
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as ff:
                    checked_lines += sum(1 for _ in ff)
            except Exception:
                pass
    t1 = time.perf_counter()
    return file_count, checked_lines, (t1 - t0) * 1000


def incremental_detection(inv):
    """测试3：增量变化检测"""
    critical_files = [(k, v) for k, v in inv.get('files', {}).items()
                      if v.get('importance') in ('critical', 'high')]

    # 首次建立基线
    snapshots = {}
    t0 = time.perf_counter()
    for k, v in critical_files:
        p = v['path']
        if os.path.exists(p):
            st = os.stat(p)
            snapshots[k] = {'size': st.st_size, 'mtime': st.st_mtime}
        else:
            snapshots[k] = {'size': -1, 'mtime': 0}
    t1 = time.perf_counter()
    baseline_ms = (t1 - t0) * 1000

    # 第二次增量检查（仅比对mtime/size，无IO读取）
    t0 = time.perf_counter()
    changed = 0
    missing = 0
    for k, v in critical_files:
        p = v['path']
        if os.path.exists(p):
            st = os.stat(p)
            if (snapshots.get(k, {}).get('size') != st.st_size or
                    snapshots.get(k, {}).get('mtime') != st.st_mtime):
                changed += 1
        else:
            if snapshots.get(k, {}).get('size') != -1:
                missing += 1
    t1 = time.perf_counter()
    check_ms = (t1 - t0) * 1000

    return len(critical_files), baseline_ms, check_ms, changed, missing


def db_health_check(inv):
    """测试4：数据库索引查询"""
    t0 = time.perf_counter()
    results = {}
    for db_key, db_def in inv.get('databases', {}).items():
        p = db_def['path']
        ok = os.path.exists(p)
        size_mb = round(os.path.getsize(p) / (1024 * 1024), 1) if ok else 0
        results[db_key] = {'ok': ok, 'size_mb': size_mb}
    t1 = time.perf_counter()
    return results, (t1 - t0) * 1000


def main():
    print('=' * 65)
    print('  FileInventoryManager 效能基准测试')
    print('  Aurora DS-V3.2T 量化交易专用工作站')
    print('=' * 65)

    # Test 1
    inv, load_ms, files_n, dbs_n, json_sz = load_json()
    print(f'\n[测试1] JSON索引加载: {load_ms:.2f}ms')
    print(f'  注册文件: {files_n} 个 | 数据库: {dbs_n} 个 | JSON: {json_sz} bytes')

    # Test 2
    walk_count, walk_ms = walk_all_files()
    idx_count, lines_checked, idx_ms = indexed_check(inv)
    speedup = walk_ms / idx_ms if idx_ms > 0 else 0
    file_ratio = walk_count / idx_count if idx_count > 0 else 0
    print(f'\n[测试2] 查询方式对比')
    print(f'  方法A - os.walk全量: {walk_ms:.2f}ms ({walk_count} 文件)')
    print(f'  方法B - 索引定向:   {idx_ms:.2f}ms ({idx_count} 文件 | {lines_checked} 行验证)')
    print(f'  时间加速比: {speedup:.1f}x | 文件数缩减: {file_ratio:.1f}x')

    # Test 3
    crit_n, base_ms, incr_ms, chg, miss = incremental_detection(inv)
    print(f'\n[测试3] 增量变化检测')
    print(f'  关键文件: {crit_n} 个 | 基线建立: {base_ms:.2f}ms')
    print(f'  二次检查: {incr_ms:.2f}ms | 变化: {chg} | 缺失: {miss}')
    print(f'  增量加速比: {base_ms/incr_ms:.1f}x (vs 重新基线)')

    # Test 4
    db_results, db_ms = db_health_check(inv)
    print(f'\n[测试4] 数据库健康检查: {db_ms:.2f}ms')
    for k, v in db_results.items():
        status = 'OK' if v['ok'] else 'MISSING'
        print(f'  {k}: {status} ({v["size_mb"]}MB)')

    # Summary
    total_infra_ms = load_ms + idx_ms + incr_ms + db_ms
    total_walk_ms = load_ms + walk_ms + base_ms + db_ms  # 假设传统也用同样的JSON加载
    print(f'\n{"=" * 65}')
    print(f'  总结：一次完整健康检查')
    print(f'  索引方案总耗时: {total_infra_ms:.0f}ms')
    print(f'  传统方案总耗时: {total_walk_ms:.0f}ms')
    print(f'  效能收益: {total_walk_ms - total_infra_ms:.0f}ms 节省')
    print(f'  加速比: {total_walk_ms/total_infra_ms:.1f}x')
    print('=' * 65)


if __name__ == '__main__':
    main()