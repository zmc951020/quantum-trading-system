#!/usr/bin/env python3
"""JT-003: 密钥硬编码扫描
扫描所有.py和.json配置文件，检测硬编码的密钥、密码、Token
"""
import sys
import os
import re
from pathlib import Path

# 扫描路径
SCAN_PATHS = [
    Path(r"d:\Gupiao\升级vscode\QS_Robot"),
    Path(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora"),
]

# 危险模式
SECRET_PATTERNS = [
    # API Key / Token
    (r'(?i)(api[_-]?key|api[_-]?secret|api[_-]?token)\s*[:=]\s*["\']([A-Za-z0-9+/=_-]{20,})["\']', "API密钥"),
    # 密码
    (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'](?!\$\{)(?!os\.environ)(?!config\[)([^"\']{3,})["\']', "密码"),
    # 私钥
    (r'-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----', "私钥"),
    # JWT Secret
    (r'(?i)(jwt[_-]?secret|secret[_-]?key)\s*[:=]\s*["\']([A-Za-z0-9+/=_-]{10,})["\']', "JWT密钥"),
    # 数据库密码
    (r'(?i)(mongodb|mysql|postgresql)://[^:]+:([^@]+)@', "数据库连接密码"),
    # Access Token
    (r'(?i)(access[_-]?token|auth[_-]?token)\s*[:=]\s*["\']([A-Za-z0-9+/=_-]{15,})["\']', "访问令牌"),
    # 券商标识
    (r'(?i)(broker[_-]?key|broker[_-]?secret)\s*[:=]\s*["\']([A-Za-z0-9+/=_-]{10,})["\']', "券商密钥"),
]

# 排除模式（环境变量引用、配置引用等安全用法）
SAFE_PATTERNS = [
    r'os\.environ',
    r'os\.getenv',
    r'\$\{[A-Z_]+[^}]*\}',  # Docker Compose / shell 变量引用
    r'config\[["\']',
    r'\.env',
    r'YOUR_',
    r'your_',
    r'<your',
    r'example',
    r'placeholder',
    r'xxxx',
    r'\*\*\*',
]

# 排除目录
EXCLUDE_DIRS = {
    '__pycache__', '.git', 'node_modules', 'logs', 'reports',
    'qlib_data', '.pytest_cache', 'venv', 'env', '.venv',
    'docs', 'archive', 'backup',
}

# 排除文件
EXCLUDE_FILES = {
    'check_secrets.py',  # 本文件自身
    'log_sanitizer.py',  # 日志脱敏器，内含测试用密码模式
}


def is_safe_context(line: str) -> bool:
    """检查是否在安全上下文（环境变量引用等）"""
    return any(re.search(p, line) for p in SAFE_PATTERNS)


def scan_file(filepath: Path) -> list:
    """扫描单个文件"""
    findings = []
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return findings

    lines = content.split('\n')
    for lineno, line in enumerate(lines, 1):
        if is_safe_context(line):
            continue
        for pattern, secret_type in SECRET_PATTERNS:
            match = re.search(pattern, line)
            if match:
                # 提取匹配值（脱敏显示）
                matched_text = match.group(0)
                if len(matched_text) > 60:
                    matched_text = matched_text[:57] + "..."
                findings.append({
                    "file": str(filepath),
                    "line": lineno,
                    "type": secret_type,
                    "snippet": matched_text.strip(),
                })
                break  # 每行只报告一次
    return findings


def main():
    print("[JT-003] 密钥硬编码扫描")
    print()

    all_findings = []
    scanned_files = 0

    for scan_path in SCAN_PATHS:
        if not scan_path.exists():
            print(f"  ⚠️ 路径不存在: {scan_path}")
            continue

        for filepath in scan_path.rglob("*"):
            if filepath.name in EXCLUDE_FILES:
                continue
            if any(d in filepath.parts for d in EXCLUDE_DIRS):
                continue
            if filepath.suffix not in ('.py', '.json', '.yaml', '.yml', '.cfg', '.ini', '.conf'):
                continue

            scanned_files += 1
            findings = scan_file(filepath)
            all_findings.extend(findings)

    # 输出结果
    print(f"  扫描文件: {scanned_files} 个")
    print(f"  发现问题: {len(all_findings)} 个")
    print()

    if all_findings:
        print("  ⚠️ 发现以下硬编码密钥:")
        print()
        for f in all_findings:
            print(f"  [{f['type']}] {f['file']}:{f['line']}")
            print(f"    {f['snippet']}")
            print()

        print(f"  ❌ 未通过 - 发现 {len(all_findings)} 处硬编码密钥")
        print(f"  建议: 使用环境变量 os.environ.get('KEY') 或配置文件引用")
        return False
    else:
        print("  ✅ 通过 - 未发现硬编码密钥")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)