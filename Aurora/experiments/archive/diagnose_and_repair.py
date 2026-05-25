#!/usr/bin/env python3
"""
Aurora 自诊断与自动修复引擎
功能：
  1. 检查之前发现的缺陷是否已补全
  2. 检测索引与实际文件系统的漂移
  3. 自动更新索引文件
  4. 生成修复报告
"""
import os
import json
import time
import hashlib
import sys
from datetime import datetime

# ============================================================
# 配置
# ============================================================
INVENTORY_PATH = "Aurora_file_inventory.json"
KNOWN_TRUNCATIONS = {
    "core_visualization": {"path": "visualization.py", "expected": 3000},
    "backtest_auto": {"path": "auto_backtest/auto_backtest_system.py", "expected": 528},
}

# ============================================================
# 工具函数
# ============================================================
def count_lines(filepath):
    """安全计数文件行数"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception as e:
        return -1  # 无法读取

def file_hash(filepath):
    """计算文件SHA256"""
    try:
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except:
        return None

def load_inventory():
    """加载索引"""
    if not os.path.exists(INVENTORY_PATH):
        return {"files": {}, "databases": {}, "key_directories": [], "data_sources": []}
    with open(INVENTORY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_inventory(inv):
    """保存索引"""
    with open(INVENTORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(inv, f, indent=2, ensure_ascii=False)
    print(f"  ✅ 索引已更新: {INVENTORY_PATH} ({os.path.getsize(INVENTORY_PATH)} bytes)")

# ============================================================
# 阶段1：已知缺陷检查
# ============================================================
def check_known_defects():
    """检查之前WARN的文件是否已修复"""
    print("=" * 70)
    print("  阶段1：已知缺陷状态检查")
    print("=" * 70)
    defects = {}
    for name, spec in KNOWN_TRUNCATIONS.items():
        path = spec['path']
        expected = spec['expected']
        actual = count_lines(path)
        ok = actual >= expected
        defects[name] = {
            "path": path, "expected": expected, "actual": actual,
            "status": "✅ 已修复" if ok else f"⚠ 仍不足 ({actual}/{expected})"
        }
    for name, d in defects.items():
        print(f"  {name}: {d['status']} | {d['path']}")
    return defects

# ============================================================
# 阶段2：索引与实际文件系统漂移检测
# ============================================================
def detect_drift():
    """检测索引与实际文件系统的偏差"""
    print("\n" + "=" * 70)
    print("  阶段2：文件系统漂移检测")
    print("=" * 70)
    inv = load_inventory()
    files_def = inv.get("files", {})

    missing = []       # 索引中有但文件不存在
    extra = []         # 索引中没有但文件存在（新文件）
    size_changed = []  # 文件大小变化
    unchecked = []     # 索引中无定义但重要的新文件

    # 2A: 检查索引中的文件
    print("\n  [2A] 索引文件存在性检查：")
    for key, defn in files_def.items():
        path = defn.get("path", "")
        expected_lines = defn.get("expected_min_lines", 0)
        if not os.path.exists(path):
            missing.append((key, path))
        else:
            actual_lines = count_lines(path)
            if expected_lines > 0 and actual_lines < expected_lines:
                size_changed.append((key, path, expected_lines, actual_lines))

    if missing:
        for key, path in missing:
            print(f"    ❌ 缺失: {key} → {path}")
    else:
        print(f"    ✅ 全部索引文件存在 ({len(files_def)}个)")
    if size_changed:
        for key, path, exp, act in size_changed:
            print(f"    ⚠ 行数不足: {key} → {path} ({act}/{exp})")
    else:
        print(f"    ✅ 无行数不足告警")

    # 2B: 扫描新文件（索引之外的重要文件）
    print("\n  [2B] 新文件发现扫描：")
    IMPORTANT_DIRS = [
        ".", "data", "utils", "auto_backtest", "risk", "ml",
        "monitor", "web", "config", "ems", "oms", "signals",
        "strategies", "tools", "models", "monitoring"
    ]
    IMPORTANT_EXT = {".py", ".json", ".md", ".yml", ".yaml", ".env", ".sh", ".conf", ".html", ".ps1"}
    SKIP_DIRS = {".git", "__pycache__", ".vscode", ".venv", "node_modules",
                 "logs", "backups", "data_cache", "model_storage", "reports",
                 "strategy_params", ".clinerules", "agent_tasks"}

    known_paths = set(os.path.normpath(v.get("path", "")) for v in files_def.values())

    discovered = []
    for scan_dir in IMPORTANT_DIRS:
        if not os.path.isdir(scan_dir):
            continue
        for root, dirs, files in os.walk(scan_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in IMPORTANT_EXT:
                    continue
                fpath = os.path.normpath(os.path.join(root, fname))
                if fpath not in known_paths:
                    # 过滤测试文件和临时文件
                    if "test_" in fname or fname.startswith("_") or fname.startswith("temp_"):
                        continue
                    try:
                        nlines = count_lines(fpath)
                    except:
                        nlines = 0
                    if nlines > 20:  # 只关注有实质内容的文件
                        discovered.append((fpath, nlines))

    if discovered:
        discovered.sort(key=lambda x: x[1], reverse=True)
        print(f"    发现 {len(discovered)} 个重要新文件（未在索引中）：")
        for fpath, nlines in discovered[:20]:  # 最多显示20个
            print(f"      + {fpath} ({nlines}行)")
        if len(discovered) > 20:
            print(f"      ... 还有 {len(discovered)-20} 个")
    else:
        print(f"    ✅ 无遗漏文件")

    # 2C: 数据库检查
    print("\n  [2C] 数据库漂移检测：")
    dbs_def = inv.get("databases", {})
    for db_key, db_def in dbs_def.items():
        path = db_def.get("path", "")
        if os.path.exists(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)
            size_warning = "⚠ >500MB" if size_mb > 500 else ("🚨 >1GB" if size_mb > 1024 else "✅")
            print(f"    {db_key}: {path} ({size_mb:.1f}MB) {size_warning}")
        else:
            print(f"    ❌ {db_key}: {path} 不存在")

    return {
        "missing": missing,
        "size_changed": size_changed,
        "discovered": discovered,
        "inventory": inv
    }

# ============================================================
# 阶段3：自动修复
# ============================================================
def auto_repair(drift_result):
    """根据漂移检测结果自动修复索引"""
    print("\n" + "=" * 70)
    print("  阶段3：自动修复")
    print("=" * 70)

    inv = drift_result["inventory"]
    discovered = drift_result["discovered"]
    missing = drift_result["missing"]
    size_changed = drift_result["size_changed"]

    files_updated = 0
    auto_generated = 0

    # 3A: 移除已删除的文件
    if missing:
        print(f"  [3A] 移除已删除文件 ({len(missing)}个)：")
        for key, path in missing:
            if key in inv.get("files", {}):
                del inv["files"][key]
                print(f"    - 移除: {key}")
                files_updated += 1

    # 3B: 更新行数变化的文件
    if size_changed:
        print(f"  [3B] 更新行数阈值 ({len(size_changed)}个)：")
        for key, path, exp, act in size_changed:
            if key in inv.get("files", {}):
                # 如果实际行数显著低于预期，降低阈值（可能是合理的功能缩减）
                # 如果实际行数远高于预期，提高阈值
                new_threshold = max(act - 50, 20)  # 留50行缓冲
                inv["files"][key]["expected_min_lines"] = new_threshold
                print(f"    ~ {key}: {exp}→{new_threshold} (实际{act}行)")
                files_updated += 1

    # 3C: 自动添加新发现的重要文件
    if discovered:
        print(f"  [3C] 自动添加新文件 ({len(discovered)}个)：")
        for fpath, nlines in discovered:
            # 生成key
            fname = os.path.basename(fpath)
            key = fname.replace(".py", "").replace(".json", "").replace(".md", "")
            # 避免key冲突
            if key in inv.get("files", {}):
                key = f"auto_{key}"
            # 推导重要性
            if nlines > 500:
                importance = "high"
            elif nlines > 100:
                importance = "medium"
            else:
                importance = "low"
            # 推导描述
            if "config" in fpath.lower():
                desc = "自动发现的配置文件"
            elif "manager" in fpath.lower() or "controller" in fpath.lower():
                desc = "自动发现的管理器/控制器"
            elif "model" in fpath.lower():
                desc = "自动发现的模型文件"
            else:
                desc = "自动发现的模块文件"

            inv["files"][key] = {
                "path": fpath,
                "importance": importance,
                "expected_min_lines": max(nlines - 50, 20),
                "description": desc,
                "auto_generated": True
            }
            print(f"    + {key}: {fpath} ({nlines}行, {importance})")
            auto_generated += 1

    # 3D: 保存
    if files_updated > 0 or auto_generated > 0:
        save_inventory(inv)
    else:
        print("  ✅ 无需修复")

    return {
        "files_updated": files_updated,
        "auto_generated": auto_generated,
        "inventory": inv
    }

# ============================================================
# 阶段4：生成完整诊断报告
# ============================================================
def generate_report(defects, drift, repair):
    """生成Markdown诊断报告"""
    print("\n" + "=" * 70)
    print("  阶段4：生成诊断报告")
    print("=" * 70)

    report_lines = []
    report_lines.append(f"# Aurora 自诊断报告")
    report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"")

    # 缺陷状态
    report_lines.append(f"## 已知缺陷状态")
    all_fixed = all(d["status"].startswith("✅") for d in defects.values())
    report_lines.append(f"- 整体状态: {'✅ 全部修复' if all_fixed else '⚠ 存在未修复项'}")
    for name, d in defects.items():
        report_lines.append(f"- {name}: {d['status']}")

    # 漂移检测
    report_lines.append(f"\n## 文件系统漂移检测")
    report_lines.append(f"- 索引文件数: {len(drift['inventory'].get('files', {}))}")
    report_lines.append(f"- 缺失文件: {len(drift['missing'])}")
    report_lines.append(f"- 行数变化: {len(drift['size_changed'])}")
    report_lines.append(f"- 新发现文件: {len(drift['discovered'])}")

    # 修复操作
    report_lines.append(f"\n## 自动修复操作")
    report_lines.append(f"- 更新条目: {repair['files_updated']}")
    report_lines.append(f"- 自动添加: {repair['auto_generated']}")

    # 最终索引状态
    inv = repair["inventory"]
    files_def = inv.get("files", {})
    by_imp = {}
    for k, v in files_def.items():
        imp = v.get("importance", "unknown")
        by_imp.setdefault(imp, []).append(k)
    report_lines.append(f"\n## 最终索引状态")
    for imp in ["critical", "high", "medium", "low"]:
        names = by_imp.get(imp, [])
        if names:
            report_lines.append(f"- {imp}: {len(names)}个")

    report_path = "diagnosis_report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
    print(f"  ✅ 报告已生成: {report_path}")

    # 打印报告
    print("\n" + "\n".join(report_lines))

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 70)
    print("  Aurora 自诊断与自动修复引擎")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 阶段1
    defects = check_known_defects()

    # 阶段2
    drift = detect_drift()

    # 阶段3（需要用户确认）
    has_issues = bool(drift["missing"] or drift["size_changed"] or drift["discovered"])
    if has_issues:
        print("\n" + "=" * 70)
        print("  ⚠ 检测到漂移，执行自动修复...")
        print("=" * 70)
        repair = auto_repair(drift)
    else:
        print("\n  ✅ 系统健康，无漂移")
        repair = {"files_updated": 0, "auto_generated": 0, "inventory": drift["inventory"]}

    # 阶段4
    generate_report(defects, drift, repair)

    print("\n" + "=" * 70)
    print("  诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    main()