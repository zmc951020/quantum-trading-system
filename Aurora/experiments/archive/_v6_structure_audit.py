#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 结构审查：自动提取类/方法/入口，对比 V5"""
import ast, os, sys
from collections import defaultdict

TARGETS = {
    "V5": "shepherd_v5_comprehensive.py",
    "V6": "shepherd_v6_comprehensive.py",
}

def analyze_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    classes = []
    functions = []  # top-level functions only
    dataclasses = []
    total_methods = 0
    methods_by_class = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            cls_info = {
                "name": node.name,
                "line": node.lineno,
                "methods": [],
                "is_dataclass": False,
            }
            # Check for @dataclass decorator
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "dataclass":
                    cls_info["is_dataclass"] = True
                    break
                if isinstance(dec, ast.Call) and hasattr(dec.func, "id") and dec.func.id == "dataclass":
                    cls_info["is_dataclass"] = True
                    break

            for body_item in node.body:
                if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cls_info["methods"].append(body_item.name)
                    total_methods += 1
            classes.append(cls_info)
            methods_by_class[node.name] = cls_info["methods"]
            if cls_info["is_dataclass"]:
                dataclasses.append(node.name)

    # Top-level function detection: walk module body only
    top_funcs = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            top_funcs.append(node.name)

    return {
        "path": path,
        "total_lines": len(source.splitlines()),
        "classes": classes,
        "total_classes": len(classes),
        "dataclasses": dataclasses,
        "total_dataclasses": len(dataclasses),
        "total_methods": total_methods,
        "methods_by_class": methods_by_class,
        "top_level_functions": top_funcs,
        "total_top_funcs": len(top_funcs),
    }

def main():
    results = {}
    for label, fname in TARGETS.items():
        if os.path.exists(fname):
            r = analyze_file(fname)
            results[label] = r
        else:
            print(f"❌ {label}: {fname} 不存在!")

    print("=" * 80)
    print("🔍 Shepherd V5 vs V6 结构审查报告")
    print("=" * 80)

    for label in ["V5", "V6"]:
        if label not in results:
            continue
        r = results[label]
        print(f"\n── {label} ──")
        print(f"  总行数: {r['total_lines']}")
        print(f"  类总数: {r['total_classes']}")
        print(f"  @dataclass: {r['total_dataclasses']} 个 → {r['dataclasses']}")
        print(f"  方法总数: {r['total_methods']}")
        print(f"  顶层函数: {r['total_top_funcs']} 个 → {r['top_level_functions']}")
        print(f"\n  类明细:")
        for cls in r["classes"]:
            tag = "@dataclass" if cls["is_dataclass"] else "class"
            print(f"    {tag:>12} {cls['name']} ({len(cls['methods'])} methods) → {cls['methods']}")

    # ── 对比 ──
    if "V5" in results and "V6" in results:
        v5 = results["V5"]
        v6 = results["V6"]
        print("\n" + "=" * 80)
        print("📊 V5 → V6 对比")
        print("=" * 80)
        # Class comparison
        v5_cls = {c["name"] for c in v5["classes"]}
        v6_cls = {c["name"] for c in v6["classes"]}
        added_cls = v6_cls - v5_cls
        removed_cls = v5_cls - v6_cls
        if added_cls:
            print(f"  新增类: {added_cls}")
        if removed_cls:
            print(f"  移除类: {removed_cls}")
        if not added_cls and not removed_cls:
            print(f"  类集合: 无变化")

        # Method comparison
        v5_all_m = set()
        for cls_name, methods in v5["methods_by_class"].items():
            for m in methods:
                v5_all_m.add(f"{cls_name}.{m}")
        v6_all_m = set()
        for cls_name, methods in v6["methods_by_class"].items():
            for m in methods:
                v6_all_m.add(f"{cls_name}.{m}")
        added_m = v6_all_m - v5_all_m
        removed_m = v5_all_m - v6_all_m
        if added_m:
            print(f"  新增方法 ({len(added_m)}):")
            for m in sorted(added_m):
                print(f"    + {m}")
        if removed_m:
            print(f"  移除方法 ({len(removed_m)}):")
            for m in sorted(removed_m):
                print(f"    - {m}")

        print(f"\n  总行数: {v5['total_lines']} → {v6['total_lines']} (Δ={v6['total_lines']-v5['total_lines']:+d})")
        print(f"  类数: {v5['total_classes']} → {v6['total_classes']}")
        print(f"  方法数: {v5['total_methods']} → {v6['total_methods']}")

    # ── V6 资格审查要点 ──
    if "V6" in results:
        v6 = results["V6"]
        print("\n" + "=" * 80)
        print("✅ V6 资格审查")
        print("=" * 80)
        has_main = "demo_v6_full_flow" in v6["top_level_functions"] or any(
            "demo_v6_full_flow" in src for src in [v6["path"]]
        )
        has_ifmain = False
        with open(v6["path"], "r", encoding="utf-8") as f:
            has_ifmain = 'if __name__ == "__main__"' in f.read()
        print(f"  main入口(demo_v6_full_flow): {'✅' if has_main else '❌'}")
        print(f"  if __name__ == '__main__':  {'✅' if has_ifmain else '❌'}")
        print(f"  @dataclass 数据模型: {v6['total_dataclasses']} 个")
        print(f"  顶层函数入口: {v6['top_level_functions']}")
        print(f"  类数量 ≥ V5: {'✅' if v6['total_classes'] >= results['V5']['total_classes'] else '⚠️'}")
        print(f"  方法数量 ≥ V5: {'✅' if v6['total_methods'] >= results['V5']['total_methods'] else '⚠️'}")

if __name__ == "__main__":
    main()