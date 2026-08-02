#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志 HMAC 密钥持久化测试
============================
验证 AuditLogger 的签名密钥在跨实例/跨重启后保持稳定，
确保历史审计日志可被验证（防篡改链条不断裂）。

TDD 红灯：本测试在密钥未持久化时必须失败。
"""
import os
import sys
import json
import shutil
import tempfile
import pytest
from pathlib import Path

# 将 QS_Robot 根目录加入路径
QS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QS_ROOT))


@pytest.fixture
def isolated_key_env(tmp_path, monkeypatch):
    """隔离的密钥环境：使用临时目录，避免污染真实密钥文件"""
    # 重置类级缓存
    from core import security
    security.AuditLogger._HMAC_KEY = None
    # 重定向密钥文件到临时目录
    key_file = tmp_path / ".audit_hmac_key"
    monkeypatch.setattr(security.AuditLogger, '_KEY_FILE', str(key_file))
    # 清除环境变量
    monkeypatch.delenv('AUDIT_HMAC_KEY', raising=False)
    yield tmp_path
    # 清理
    security.AuditLogger._HMAC_KEY = None


def test_hmac_key_persists_across_instances(isolated_key_env):
    """密钥必须在两个 AuditLogger 实例间保持一致（持久化）"""
    from core.security import AuditLogger

    log_file = str(isolated_key_env / "audit1.log")
    logger1 = AuditLogger(log_file=log_file)
    key1 = AuditLogger._HMAC_KEY
    assert key1 is not None, "HMAC密钥未生成"

    # 模拟"重启"：创建新实例，应加载同一密钥
    log_file2 = str(isolated_key_env / "audit2.log")
    logger2 = AuditLogger(log_file=log_file2)
    key2 = AuditLogger._HMAC_KEY

    assert key1 == key2, "HMAC密钥未持久化，跨实例不一致（历史审计日志将无法验证）"


def test_signed_entry_verifiable_after_reinstantiation(isolated_key_env):
    """重启后，旧实例写入的审计日志条目必须仍可验证签名"""
    from core.security import AuditLogger, OperationType

    log_file = str(isolated_key_env / "audit_persist.log")
    logger1 = AuditLogger(log_file=log_file)
    logger1.log(
        user="test_user",
        operation=OperationType.LOGIN,
        target="system",
        result="success",
        ip_address="127.0.0.1",
    )

    # 读取写入的日志条目
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) > 0, "审计日志未写入"
    entry = json.loads(lines[0])
    sig = entry.pop('_sig', None)
    assert sig is not None, "日志条目缺少HMAC签名"

    # 模拟重启：新实例加载同一密钥
    AuditLogger._HMAC_KEY = None
    logger2 = AuditLogger(log_file=str(isolated_key_env / "audit_other.log"))
    # 用新实例的密钥验证旧条目
    expected = logger2._sign_entry(entry)
    assert expected == sig, "重启后旧审计日志签名验证失败（密钥未持久化）"


def test_hmac_key_loads_from_env_variable(monkeypatch, tmp_path):
    """环境变量 AUDIT_HMAC_KEY 设置时必须优先使用"""
    from core import security

    security.AuditLogger._HMAC_KEY = None
    key_file = tmp_path / ".audit_hmac_key"
    monkeypatch.setattr(security.AuditLogger, '_KEY_FILE', str(key_file))
    monkeypatch.setenv('AUDIT_HMAC_KEY', 'test-env-secret-key-32bytes!!')

    log_file = str(tmp_path / "audit_env.log")
    security.AuditLogger(log_file=log_file)
    key = security.AuditLogger._HMAC_KEY
    assert key is not None
    # 环境变量密钥应被采用（前32字节）
    assert key[:len(b'test-env-secret-key-32bytes!')] == b'test-env-secret-key-32bytes!'
    # 环境变量优先时不应创建密钥文件
    assert not key_file.exists(), "环境变量已提供密钥，不应再创建文件"

    security.AuditLogger._HMAC_KEY = None


def test_hmac_key_never_none_after_init(isolated_key_env):
    """初始化后密钥必须非None（修复P0：_HMAC_KEY为None导致审计失败）"""
    from core.security import AuditLogger

    log_file = str(isolated_key_env / "audit_none.log")
    AuditLogger(log_file=log_file)
    assert AuditLogger._HMAC_KEY is not None, "HMAC密钥仍为None，审计日志将无法签名"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
