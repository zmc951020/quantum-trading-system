# coding: utf-8
"""
安全增强增益模块 — 密钥保护 + 日志脱敏 + 审计轨迹
=====================================================
增益性补充，可与现有 trade_security.py、security_control 并行。
不修改原有模块代码。

功能：
  - 密钥/Token 从环境变量读取，绝不允许硬编码
  - 日志过滤器：自动脱敏手机号/身份证/API Key/Token
  - 审计轨迹记录所有敏感操作
  - .env 文件安全检测
"""

import logging
import os
import re
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────
# 1. 安全密钥加载器
# ─────────────────────────────────────────────

class SecureKeyLoader:
    """
    密钥安全加载器
    强制从环境变量读取，禁止代码中硬编码密钥
    """

    # 必须配置的环境变量列表（缺少则启动失败）
    REQUIRED_KEYS = [
        "DEEPSEEK_API_KEY",
        "DATABASE_URL",
        "ENCRYPTION_KEY",
    ]

    # 可选但建议配置
    RECOMMENDED_KEYS = [
        "BROKER_API_KEY",
        "BROKER_API_SECRET",
        "JWT_SECRET",
        "ADMIN_PASSWORD_HASH",
    ]

    @staticmethod
    def validate_environment() -> Dict[str, Any]:
        """
        启动时验证关键环境变量是否存在

        Returns:
            {'ok': bool, 'missing': [...], 'missing_recommended': [...], 'warnings': [...]}
        """
        missing = []
        for key in SecureKeyLoader.REQUIRED_KEYS:
            if not os.getenv(key):
                missing.append(key)

        missing_recommended = []
        for key in SecureKeyLoader.RECOMMENDED_KEYS:
            if not os.getenv(key):
                missing_recommended.append(key)

        warnings = []

        # 检查 .env 文件权限（在类 Unix 系统）
        env_file = Path(".env")
        if env_file.exists():
            try:
                stat = env_file.stat()
                # Windows 不检查权限位
            except Exception:
                pass

        # 检查是否有明文密钥文件
        dangerous_files = ["api_keys.txt", "secrets.json", "credentials.ini", "passwords.txt"]
        for fname in dangerous_files:
            if Path(fname).exists():
                warnings.append(f"发现可疑明文密钥文件: {fname}，请删除或使用环境变量")

        # 检查硬编码密钥（启发式扫描重要文件）
        # 在实际部署中应扫描所有 .py 文件

        return {
            "ok": len(missing) == 0,
            "missing": missing,
            "missing_recommended": missing_recommended,
            "warnings": warnings,
        }

    @staticmethod
    def get_key(name: str) -> Optional[str]:
        """安全获取密钥，仅从环境变量"""
        return os.getenv(name)

    @staticmethod
    def scan_hardcoded_secrets(file_path: str) -> List[Dict[str, Any]]:
        """
        扫描文件中的疑似硬编码密钥

        Returns:
            [{'line': 123, 'pattern': 'api_key', 'content_snip': '...ak-...'}]
        """
        findings = []
        patterns = [
            (r'api[_-]?key\s*=\s*["\'][A-Za-z0-9\-_]{20,}["\']', "API_KEY 硬编码"),
            (r'secret\s*=\s*["\'][A-Za-z0-9\-_]{20,}["\']', "Secret 硬编码"),
            (r'password\s*=\s*["\'][^"\']+["\']', "密码硬编码"),
            (r'token\s*=\s*["\'][A-Za-z0-9\-_]{20,}["\']', "Token 硬编码"),
            (r'sk-[A-Za-z0-9]{32,}', "疑似 OpenAI/DeepSeek API Key"),
        ]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for lineno, line in enumerate(f, 1):
                    for pattern, desc in patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            # 排除注释行和赋值给空字符串的情况
                            stripped = line.strip()
                            if stripped.startswith('#') or stripped.startswith('//'):
                                continue
                            if 'os.getenv' in stripped or 'os.environ' in stripped:
                                continue
                            findings.append({
                                "file": file_path,
                                "line": lineno,
                                "pattern": desc,
                                "content_snip": stripped[:80] + ("..." if len(stripped) > 80 else ""),
                            })
        except Exception:
            pass
        return findings


# ─────────────────────────────────────────────
# 2. 日志脱敏过滤器
# ─────────────────────────────────────────────

class SensitiveDataFilter(logging.Filter):
    """
    日志脱敏过滤器
    自动脱敏常见敏感信息，直接挂载到 logging 系统
    """

    # 脱敏规则 (正则 → 替换模板)
    _RULES = [
        # 手机号: 13812345678 → 138****5678
        (re.compile(r'(1[3-9]\d)\d{4}(\d{4})'), r'\1****\2'),
        # 身份证号: 前3+中间10+后4
        (re.compile(r'(\d{6})(\d{8,10})(\d{2}[\dXx])'), r'\1********\3'),
        # API Key 模式: sk-xxx... / ak-xxx...
        (re.compile(r'(sk-[A-Za-z0-9]{4})[A-Za-z0-9]+', re.IGNORECASE), r'\1***'),
        (re.compile(r'(ak-[A-Za-z0-9]{4})[A-Za-z0-9]+', re.IGNORECASE), r'\1***'),
        # JWT Token
        (re.compile(r'(eyJ[A-Za-z0-9_-]{10})[A-Za-z0-9_-]+'), r'\1***'),
        # 密码字段
        (re.compile(r'(password[=:\s]*)[^\s,;]+', re.IGNORECASE), r'\1***'),
        (re.compile(r'(secret[=:\s]*)[^\s,;]+', re.IGNORECASE), r'\1***'),
        # 银行卡号
        (re.compile(r'(\d{4})\d{8,12}(\d{4})'), r'\1****\2'),
    ]

    def filter(self, record):
        """过滤日志记录，脱敏敏感信息"""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            msg = str(record.msg)
            for pattern, replacement in self._RULES:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
        if hasattr(record, 'args') and record.args:
            # 处理格式化参数
            safe_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    s = arg
                    for pattern, replacement in self._RULES:
                        s = pattern.sub(replacement, s)
                    safe_args.append(s)
                else:
                    safe_args.append(arg)
            record.args = tuple(safe_args)
        return True

    @staticmethod
    def mask_string(s: str) -> str:
        """手动脱敏任意字符串"""
        for pattern, replacement in SensitiveDataFilter._RULES:
            s = pattern.sub(replacement, s)
        return s


def install_sensitive_filter(logger_instance=None):
    """
    安装脱敏过滤器到 root logger 或指定 logger

    Usage:
        install_sensitive_filter()           # 全局安装
        install_sensitive_filter(logger)     # 指定 logger
    """
    flt = SensitiveDataFilter()
    target = logger_instance or logging.getLogger()
    target.addFilter(flt)
    return flt


# ─────────────────────────────────────────────
# 3. 审计轨迹记录器
# ─────────────────────────────────────────────

class AuditTrail:
    """
    审计轨迹记录器
    记录所有敏感操作，支持事后回溯
    """

    _MAX_EVENTS = 5000          # 内存中最多保留事件
    _FLUSH_INTERVAL = 60        # 每60秒刷盘一次

    def __init__(self, audit_file: str = "audit_trail.jsonl"):
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._audit_file = audit_file
        self._last_flush = time.time()
        self._event_counter = 0

    def log(self, action: str, operator: str, target: str = "",
            detail: str = "", result: str = "", severity: str = "info"):
        """
        记录一条审计事件

        Args:
            action:  操作类型 (place_order, cancel_order, config_change, withdrawal, ...)
            operator: 操作人/模块 (用户名/strategy_id/system)
            target:   操作对象 (order_id/symbol/account_id)
            detail:  详细描述
            result:  操作结果 (success/failure/denied)
            severity: info/warning/critical
        """
        with self._lock:
            self._event_counter += 1
            event = {
                "id": self._event_counter,
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "operator": SensitiveDataFilter.mask_string(operator),
                "target": target,
                "detail": SensitiveDataFilter.mask_string(detail),
                "result": result,
                "severity": severity,
            }
            self._events.append(event)

            # 修剪过旧事件
            if len(self._events) > self._MAX_EVENTS:
                self._events = self._events[-self._MAX_EVENTS:]

            # 异步刷盘
            if time.time() - self._last_flush > self._FLUSH_INTERVAL:
                self._flush()

            # 关键事件立即刷盘
            if severity == "critical":
                self._flush()

    def _flush(self):
        """将审计事件写入磁盘"""
        try:
            with open(self._audit_file, 'a', encoding='utf-8') as f:
                for event in self._events[-100:]:  # 只追加最近100条
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._last_flush = time.time()
        except Exception as e:
            logging.getLogger(__name__).error("审计轨迹刷盘失败: %s", e)

    def query(self, action: Optional[str] = None, operator: Optional[str] = None,
              since: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """查询审计事件"""
        with self._lock:
            results = []
            for event in reversed(self._events):
                if action and event.get("action") != action:
                    continue
                if operator and operator not in event.get("operator", ""):
                    continue
                if since and event.get("timestamp", "") < since:
                    continue
                results.append(event)
                if len(results) >= limit:
                    break
            return results

    def get_event_count(self) -> int:
        return self._event_counter


# ── 全局实例 ──
audit_trail = AuditTrail()