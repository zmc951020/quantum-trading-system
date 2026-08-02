#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志密钥迁移测试
==================
验证 AuditLogger 在密钥迁移场景下的行为：
  1. 历史日志（无 _sig 字段）应能加载而不报篡改
  2. 历史 _sig 验证失败应能加载而不报篡改（密钥迁移期）
  3. 提供 re_sign_legacy_logs() 方法用当前密钥补签
  4. 迁移完成后再次出现无签名日志视为篡改

TDD 红灯：本测试在迁移机制未实现时必须失败。
"""
import os
import sys
import json
import hmac
import hashlib
import pytest
from pathlib import Path

QS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QS_ROOT))


@pytest.fixture
def migrated_env(tmp_path, monkeypatch):
    """隔离的密钥环境（含迁移标记文件支持）"""
    from core import security
    security.AuditLogger._HMAC_KEY = None
    key_file = tmp_path / ".audit_hmac_key"
    monkeypatch.setattr(security.AuditLogger, '_KEY_FILE', str(key_file))
    # 迁移标记文件路径
    migrated_file = tmp_path / ".audit_migrated"
    monkeypatch.setattr(security.AuditLogger, '_MIGRATED_FILE', str(migrated_file))
    monkeypatch.delenv('AUDIT_HMAC_KEY', raising=False)
    yield tmp_path
    security.AuditLogger._HMAC_KEY = None


def _write_log_line(log_file: str, entry: dict, sig: str = None):
    """写入一行日志（可选签名）"""
    data = dict(entry)
    if sig is not None:
        data['_sig'] = sig
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')


def test_legacy_log_without_sig_loads_without_tamper_error(migrated_env, caplog):
    """无 _sig 字段的历史日志加载时应记录 INFO（不报篡改 ERROR）"""
    from core.security import AuditLogger

    log_file = str(migrated_env / "audit.log")
    _write_log_line(log_file, {
        "timestamp": "2026-06-15T02:53:16.959973",
        "user": "admin",
        "operation": "login",
        "target": "admin",
        "result": "success",
        "details": {"role": "admin"},
        "ip_address": "127.0.0.1",
        "session_id": "abc-123",
    })  # 无 _sig

    import logging
    with caplog.at_level(logging.ERROR):
        logger = AuditLogger(log_file=log_file)
        # 不应有 ERROR 级别的"签名不匹配"
        error_msgs = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
        assert not any("签名不匹配" in m or "篡改" in m for m in error_msgs), \
            f"历史日志被误报为篡改: {error_msgs}"
    assert len(logger._logs) == 1, "历史日志未加载"


def test_legacy_log_with_invalid_sig_loads_without_tamper_error(migrated_env, caplog):
    """有 _sig 但验证失败的日志（密钥迁移期）应能加载而不报篡改 ERROR"""
    from core.security import AuditLogger

    log_file = str(migrated_env / "audit.log")
    entry = {
        "timestamp": "2026-06-15T02:53:16.959973",
        "user": "admin",
        "operation": "login",
        "target": "admin",
        "result": "success",
        "details": {"role": "admin"},
        "ip_address": "127.0.0.1",
        "session_id": "abc-123",
    }
    # 用一个错误的密钥签名（模拟旧密钥签的日志）
    wrong_key = b'wrong_old_key_32_bytes_padding!!!!!!'[:32]
    raw = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode('utf-8')
    wrong_sig = hmac.new(wrong_key, raw, hashlib.sha256).hexdigest()
    _write_log_line(log_file, entry, sig=wrong_sig)

    import logging
    with caplog.at_level(logging.ERROR):
        AuditLogger(log_file=log_file)
        error_msgs = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
        assert not any("签名不匹配" in m or "篡改" in m for m in error_msgs), \
            f"密钥迁移期日志被误报为篡改: {error_msgs}"


def test_re_sign_legacy_logs_adds_valid_signature(migrated_env):
    """re_sign_legacy_logs() 应为无签名的日志补签当前密钥的签名"""
    from core.security import AuditLogger

    log_file = str(migrated_env / "audit.log")
    _write_log_line(log_file, {
        "timestamp": "2026-06-15T02:53:16.959973",
        "user": "admin",
        "operation": "login",
        "target": "admin",
        "result": "success",
        "details": {},
        "ip_address": "127.0.0.1",
        "session_id": "abc",
    })

    logger = AuditLogger(log_file=log_file)
    assert len(logger._logs) == 1
    # 调用补签方法
    logger.re_sign_legacy_logs()
    # 重新加载验证
    logger._logs.clear()
    logger._load_logs()
    # 重新加载后应能通过验证（无 WARNING）
    assert len(logger._logs) == 1
    # 验证文件中每行都有 _sig
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                assert '_sig' in entry, "补签后日志仍缺少 _sig 字段"


def test_migration_creates_migrated_marker(migrated_env):
    """完成迁移后应创建 .migrated 标记文件"""
    from core.security import AuditLogger

    log_file = str(migrated_env / "audit.log")
    _write_log_line(log_file, {
        "timestamp": "2026-06-15T02:53:16.959973",
        "user": "admin",
        "operation": "login",
        "target": "admin",
        "result": "success",
        "details": {},
        "ip_address": "127.0.0.1",
        "session_id": "abc",
    })

    logger = AuditLogger(log_file=log_file)
    logger.re_sign_legacy_logs()

    migrated_file = Path(AuditLogger._MIGRATED_FILE)
    assert migrated_file.exists(), "迁移完成后未创建 .migrated 标记文件"


def test_post_migration_tamper_detected(migrated_env, caplog):
    """迁移完成后，再次出现无签名日志应视为篡改（报 ERROR）"""
    from core.security import AuditLogger

    log_file = str(migrated_env / "audit.log")
    # 先迁移
    _write_log_line(log_file, {
        "timestamp": "2026-06-15T02:53:16.959973",
        "user": "admin",
        "operation": "login",
        "target": "admin",
        "result": "success",
        "details": {},
        "ip_address": "127.0.0.1",
        "session_id": "abc",
    })
    logger = AuditLogger(log_file=log_file)
    logger.re_sign_legacy_logs()

    # 迁移后再添加一条无签名日志（模拟攻击者删除签名）
    _write_log_line(log_file, {
        "timestamp": "2026-08-02T10:00:00.000000",
        "user": "attacker",
        "operation": "admin_action",
        "target": "system",
        "result": "success",
        "details": {},
        "ip_address": "127.0.0.1",
        "session_id": "hack",
    })  # 无 _sig

    # 重置 _logs 重新加载
    import logging
    AuditLogger._HMAC_KEY = None  # 强制重新加载密钥
    with caplog.at_level(logging.ERROR):
        AuditLogger(log_file=log_file)
        error_msgs = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("篡改" in m or "签名不匹配" in m or "无签名" in m for m in error_msgs), \
            f"迁移后无签名日志未被识别为篡改: {error_msgs}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
