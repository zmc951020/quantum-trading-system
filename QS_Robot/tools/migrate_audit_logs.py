#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志密钥迁移脚本
==================
一次性脚本：用当前持久化密钥为所有历史审计日志重新签名
执行后创建 .migrated 标记文件，之后无签名日志视为篡改

使用方法：python tools/migrate_audit_logs.py
"""
import sys
import os
import logging

# 静默 logging 输出，避免干扰
logging.disable(logging.CRITICAL)

# 将 QS_Robot 根目录加入路径
QS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QS_ROOT)

# 切换到 QS_Robot 工作目录（确保 audit.log 路径正确）
os.chdir(QS_ROOT)

from core.security import AuditLogger, get_audit_logger


def main():
    """执行密钥迁移"""
    # 使用模块级单例（与 server.py 一致的 log_file 路径）
    logger = get_audit_logger()
    print(f"[1/4] 迁移前：已加载 {len(logger._logs)} 条日志")
    print(f"[2/4] 迁移标记是否存在: {logger._is_migrated()}")

    if logger._is_migrated():
        print("[3/4] 已迁移过，跳过")
        print("[4/4] 完成（无操作）")
        return 0

    # 执行迁移
    count = logger.re_sign_legacy_logs()
    print(f"[3/4] 已重新签名 {count} 条历史日志")

    # 重新加载验证
    logger._logs.clear()
    logger._load_logs()
    print(f"[4/4] 迁移后：已加载 {len(logger._logs)} 条日志")
    print(f"      迁移标记: {logger._is_migrated()}")
    print("\n✅ 迁移完成。之后无签名日志将视为篡改。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
