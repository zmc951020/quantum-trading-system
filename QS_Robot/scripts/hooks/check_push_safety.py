# coding: utf-8
"""
推送前安全检查 pre-push 钩子
==============================
在 git push 前执行，检查：
  1. 已跟踪文件中是否混入敏感数据文件（.env / 私钥 / 凭证 / cookie 等）
  2. 未跟踪文件中是否出现敏感文件名（防止误 add / 误推）
命中任一规则 => 打印警告并退出码 1，阻断本次推送（防误推）。

调用方式（由 .git/hooks/pre-push 调用）：
  python check_push_safety.py
退出码 0 = 安全放行；非 0 = 阻断推送。
"""

import os
import re
import subprocess
import sys

# ---- 敏感文件规则 ----
# (正则, 说明)；匹配的是文件名/相对路径。业务代码(.py/.js)即使名字含敏感词也排除。
SENSITIVE_PATTERNS = [
    (r"(^|/|\\)\.env(\.|$)", "环境变量文件 .env"),
    (r"\.(pem|key|p12|pfx|jks)$", "私钥/证书文件"),
    (r"(^|/|\\)id_(rsa|ed25519|ecdsa)(\.pub)?$", "SSH 私钥"),
    (r"(^|/|\\)cookies?\.txt$", "Cookie 文件"),
    (r"(^|/|\\)(credentials?|\.git-credentials)$", "凭据文件"),
    (r"(^|/|\\)(token|tokens?)(\.|$)", "Token 文件"),
    (r"(^|/|\\)(secret|secrets?)(\.|$)", "密钥文件"),
    (r"\.(pcap|keychain|kdbx)$", "密码库/抓包文件"),
    (r"(^|/|\\)(\.npmrc|\.pypirc)$", "包管理器凭据"),
]

# 业务代码扩展名：这些文件即使名字含敏感词也是代码，不阻断
CODE_EXTS = {".py", ".js", ".ts", ".java", ".go", ".c", ".cpp", ".h",
             ".md", ".json", ".yaml", ".yml", ".txt", ".toml", ".cfg",
             ".ini", ".sh", ".ps1", ".bat", ".cmd", ".html", ".css"}


def run(cmd):
    """运行 git 命令并返回行列表"""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return out.stdout.splitlines() if out.returncode == 0 else []
    except Exception:
        return []


def match_sensitive(relpath):
    """对相对路径做敏感匹配；代码文件不做数据级阻断"""
    base = os.path.basename(relpath).lower()
    ext = os.path.splitext(base)[1].lower()
    for pat, desc in SENSITIVE_PATTERNS:
        if re.search(pat, relpath.replace("\\", "/"), re.IGNORECASE):
            # .env 精确命中不豁免；私钥/证书类即使扩展名在 CODE_EXTS 也要查扩展名是否真为密钥
            if ext in CODE_EXTS and not (pat == r"(^|/|\\)\.env(\.|$)"):
                continue
            return desc
    return None


def main():
    root = run(["git", "rev-parse", "--show-toplevel"])
    if not root:
        print("[pre-push] 无法定位仓库根目录，放行")
        return 0
    root = root[0].strip()

    findings = []

    # 1. 已跟踪文件检查
    tracked = run(["git", "ls-files"])
    for f in tracked:
        d = match_sensitive(f)
        if d:
            findings.append(f"[已跟踪] {f}  ({d})")

    # 2. 未跟踪文件检查（含被忽略目录外的新增文件）
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"])
    for f in untracked:
        d = match_sensitive(f)
        if d:
            findings.append(f"[未跟踪] {f}  ({d})")

    if findings:
        print("=" * 60)
        print("!! [pre-push] 推送被阻断：发现敏感文件 !!")
        for f in findings[:20]:
            print("   " + f)
        if len(findings) > 20:
            print(f"   ... 共 {len(findings)} 项")
        print("=" * 60)
        print("处理办法：确认文件用途后，将确认的安全文件加入 .gitignore；")
        print("         切勿用 git add -f 强行入库。")
        return 1

    print(f"[pre-push] 安全检查通过（已跟踪 {len(tracked)} / 未跟踪 {len(untracked)}，无敏感文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
