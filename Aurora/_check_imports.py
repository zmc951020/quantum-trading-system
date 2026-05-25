# coding: utf-8
import os
import importlib.util
import traceback

# 检查所有 __init__.py 的导入链
packages = {}

for root, dirs, files in os.walk("."):
    # 跳过隐藏目录和虚拟环境
    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != "xbk-docker"]
    if "__init__.py" in files:
        pkg_name = root[2:].replace(os.sep, ".") or "root"
        packages[pkg_name] = os.path.join(root, "__init__.py")

print("=" * 60)
print("当前存在的包 __init__.py:")
for name, path in sorted(packages.items()):
    print(f"  {name} -> {path}")

print()
print("=" * 60)
print("导入验证:")
for pkg_name, init_path in sorted(packages.items()):
    print(f"\n--- {pkg_name} ---")
    try:
        with open(init_path, "r", encoding="utf-8") as f:
            content = f.read()
        for line in content.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("from .") and "import" in line_stripped:
                # 提取模块名
                parts = line_stripped.split()
                if len(parts) >= 3:
                    module_name = parts[1].lstrip(".")
                    full_name = f"{pkg_name.replace('root','')}.{module_name}".strip(".")
                    print(f"  from .{module_name} import ...", end="")
                    if importlib.util.find_spec(full_name):
                        print("  OK")
                    else:
                        print(f"  FAILED (need: {full_name}.py)")
    except Exception as e:
        print(f"  ERROR: {e}")