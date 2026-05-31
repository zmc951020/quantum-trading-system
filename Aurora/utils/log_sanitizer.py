# coding: utf-8
"""
日志脱敏工具
===========
功能:
  - 自动检测并脱敏日志中的敏感信息
  - 支持: 密码、API Key、Token、手机号、身份证号、银行卡号
  - 可作为 logging.Filter 或独立函数使用
  - 白名单模式: 仅允许输出指定的非敏感字段
"""

import logging
import os
import re
from typing import Any, Dict, Optional

# ── 敏感信息正则模式 ──
SENSITIVE_PATTERNS = [
    # API Key / Token (各类常见格式)
    (re.compile(r'(api[_-]?key|apikey|api_secret|secret_key|access_token|auth_token)\s*[=:]\s*["\']?([\w\-_\.]{8,})["\']?', re.IGNORECASE),
     r'\1=***REDACTED***'),
    # 密码 (password=xxx, passwd=xxx, pwd=xxx)
    (re.compile(r'(password|passwd|pwd)\s*[=:]\s*["\']?([^\s,;}"\']{3,})["\']?', re.IGNORECASE),
     r'\1=***REDACTED***'),
    # Bearer Token
    (re.compile(r'Bearer\s+([\w\-_\.]{20,})', re.IGNORECASE),
     r'Bearer ***REDACTED***'),
    # 手机号 (中国大陆)
    (re.compile(r'\b1[3-9]\d{9}\b'),
     lambda m: m.group()[:3] + '****' + m.group()[-4:]),
    # 身份证号
    (re.compile(r'\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dxX]\b'),
     lambda m: m.group()[:6] + '********' + m.group()[-4:]),
    # 银行卡号
    (re.compile(r'\b\d{16,19}\b'),
     lambda m: m.group()[:4] + ' **** **** ' + m.group()[-4:]),
    # IP 地址（可选脱敏）
    (re.compile(r'(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})'),
     lambda m: f'{m.group(1)}.{m.group(2)}.*.*'),
    # Redis/Mongo/MySQL 连接字符串
    (re.compile(r'(redis|mongodb|mysql|postgresql)://[^:]+:([^@]+)@', re.IGNORECASE),
     r'\1://***:***@'),
    # 私钥片段
    (re.compile(r'-----BEGIN (RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC )?PRIVATE KEY-----'),
     '-----BEGIN PRIVATE KEY-----***REDACTED***-----END PRIVATE KEY-----'),
    # JWT Token
    (re.compile(r'eyJ[\w\-_]{20,}\.[\w\-_]{20,}\.[\w\-_]{20,}'),
     lambda m: m.group()[:20] + '...***REDACTED***'),
]

# 可信任字段白名单（不会被脱敏）
SAFE_FIELDS = {
    'timestamp', 'date', 'time', 'level', 'module', 'logger',
    'symbol', 'code', 'price', 'volume', 'amount', 'quantity',
    'side', 'status', 'order_id', 'trade_id', 'reason',
    'version', 'interval', 'period', 'source',
    'open', 'high', 'low', 'close', 'volume', 'amount',
    'rsi', 'macd', 'ma', 'ema', 'sma', 'boll', 'kdj',
    'signal', 'action', 'type', 'name', 'id',
}


class LogSanitizer(logging.Filter):
    """
    logging.Filter 实现 — 可直接添加到任何 logger
    用法:
        logger.addFilter(LogSanitizer())
    """
    def __init__(self, redact_ip: bool = False):
        super().__init__()
        self._redact_ip = redact_ip
        self._patterns = list(SENSITIVE_PATTERNS)
        if not redact_ip:
            # 移除 IP 脱敏规则
            self._patterns = [
                (p, r) for p, r in self._patterns
                if '(\d{1,3})\\.(\d{1,3})\\.(\d{1,3})\\.(\d{1,3})' not in p.pattern
            ]

    def filter(self, record: logging.LogRecord) -> bool:
        """对每条日志记录进行脱敏"""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = sanitize_text(record.msg, self._patterns)
        if record.args:
            # 检查格式化参数
            if isinstance(record.args, dict):
                record.args = {
                    k: sanitize_text(str(v), self._patterns) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_text(str(a), self._patterns) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def sanitize_text(text: str, patterns: list = None) -> str:
    """
    对文本进行脱敏处理
    
    Args:
        text: 原始文本
        patterns: 自定义脱敏规则，默认使用 SENSITIVE_PATTERNS
    
    Returns:
        脱敏后的文本
    """
    if not text or not isinstance(text, str):
        return text
    
    patterns = patterns or SENSITIVE_PATTERNS
    
    result = text
    for pattern, replacement in patterns:
        try:
            if callable(replacement):
                result = pattern.sub(replacement, result)
            else:
                result = pattern.sub(replacement, result)
        except Exception:
            # 正则替换失败不中断
            continue
    
    return result


def sanitize_dict(data: Dict[str, Any], safe_fields: set = None) -> Dict[str, Any]:
    """
    对字典值进行脱敏，保留白名单字段原名
    
    Args:
        data: 原始字典
        safe_fields: 安全字段集合（这些字段不做脱敏）
    
    Returns:
        脱敏后的字典
    """
    if not data:
        return data
    
    safe_fields = safe_fields or SAFE_FIELDS
    result = {}
    
    for key, value in data.items():
        if key.lower() in {s.lower() for s in safe_fields}:
            result[key] = value  # 安全字段原样保留
        elif isinstance(value, str):
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value, safe_fields)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                sanitize_dict(v, safe_fields) if isinstance(v, dict)
                else sanitize_text(str(v)) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value
    
    return result


def mask_api_key(key: str, visible_chars: int = 4) -> str:
    """
    遮罩 API Key，仅保留首尾各 visible_chars 字符
    示例: "sk-abc123def456ghi789" -> "sk-a***6789"
    """
    if not key or len(key) <= visible_chars * 2:
        return "*" * min(len(key), 8)
    
    prefix = key[:visible_chars]
    suffix = key[-visible_chars:]
    masked_len = len(key) - visible_chars * 2
    return f"{prefix}{'*' * min(masked_len, 8)}{suffix}"


def mask_password(password: str) -> str:
    """遮罩密码为固定长度星号"""
    return "*" * 8


def is_sensitive_key(key: str) -> bool:
    """判断 key 是否为敏感字段名"""
    sensitive_keywords = [
        'password', 'passwd', 'pwd', 'secret', 'token', 'api_key',
        'apikey', 'api_secret', 'private_key', 'privkey', 'credential',
        'auth', 'authorization', 'access_token',
    ]
    key_lower = key.lower().replace('-', '_').replace(' ', '_')
    for kw in sensitive_keywords:
        if kw in key_lower:
            return True
    return False


def configure_root_logger(redact_ip: bool = False):
    """
    一键配置根 logger 脱敏
    用法: configure_root_logger()
    """
    sanitizer = LogSanitizer(redact_ip=redact_ip)
    root = logging.getLogger()
    root.addFilter(sanitizer)
    # 避免重复添加
    existing_filters = [f for f in root.filters if isinstance(f, LogSanitizer)]
    if len(existing_filters) > 1:
        for f in existing_filters[:-1]:
            root.removeFilter(f)
    return sanitizer


# ── 使用示例 ──
if __name__ == "__main__":
    # 测试脱敏
    test_cases = [
        "用户登录: username=admin, password=SuperSecret123",
        "API调用: api_key=sk-abc123def456ghi789jkl",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "手机号: 13812345678 身份证: 110101199001011234",
        "mongodb://admin:secretpass@localhost:27017/trading",
        "正常数据: symbol=000001.SZ price=12.50 volume=10000",
    ]
    
    print("=" * 60)
    print("日志脱敏测试")
    print("=" * 60)
    for case in test_cases:
        sanitized = sanitize_text(case)
        print(f"原文: {case}")
        print(f"脱敏: {sanitized}")
        print("-" * 40)
    
    print("\nAPI Key 遮罩测试:")
    print(f"sk-abc123def456ghi789 -> {mask_api_key('sk-abc123def456ghi789')}")
    print(f"short -> {mask_api_key('abcd')}")
    
    print("\n配置 root logger 脱敏...")
    configure_root_logger()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")
    logger.info("密码验证: password=MyP@ssw0rd123, api_key=sk-live-abcdef123456")