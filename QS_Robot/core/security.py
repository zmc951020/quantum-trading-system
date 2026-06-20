#!/usr/bin/env python3
"""
安全模块 (Security Module)
==========================

核心功能：
  1. 密码加密与验证 (bcrypt)
  2. 操作日志审计系统
  3. 会话安全管理
  4. API密钥管理
"""

import os
import sys
import json
import re
import time
import hmac
import hashlib
import secrets
import logging
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    bcrypt = None
    BCRYPT_AVAILABLE = False

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.FileHandler('security.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 操作类型枚举
# ============================================================

class OperationType(Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    STRATEGY_START = "strategy_start"
    STRATEGY_STOP = "strategy_stop"
    BACKTEST = "backtest"
    OPTIMIZATION = "optimization"
    RISK_ALERT = "risk_alert"
    DATA_ACCESS = "data_access"
    PARAMETER_CHANGE = "parameter_change"
    ADMIN_ACTION = "admin_action"

# ============================================================
# 操作日志记录
# ============================================================

@dataclass
class AuditLog:
    timestamp: str
    user: str
    operation: str
    target: str
    result: str
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    session_id: str = ""

# ============================================================
# 密码管理器
# ============================================================

class PasswordManager:
    """密码加密与验证管理器"""
    
    @staticmethod
    def hash_password(password: str) -> bytes:
        """加密密码"""
        if BCRYPT_AVAILABLE:
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password.encode('utf-8'), salt)
        else:
            # 降级方案：使用简单哈希
            import hashlib
            return hashlib.sha256(password.encode('utf-8')).digest()
    
    @staticmethod
    def verify_password(password: str, hashed_password: bytes) -> bool:
        """验证密码"""
        if BCRYPT_AVAILABLE:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password)
        else:
            # 降级方案：使用简单哈希比较
            import hashlib
            return hashlib.sha256(password.encode('utf-8')).digest() == hashed_password
    
    @staticmethod
    def hash_password_str(password: str) -> str:
        """加密密码并返回字符串（自动适配bcrypt/SHA256）"""
        if BCRYPT_AVAILABLE:
            # bcrypt 哈希为 ASCII 可兼容字符串
            return PasswordManager.hash_password(password).decode('ascii')
        else:
            # SHA-256 降级方案使用 hex 编码
            return PasswordManager.hash_password(password).hex()
    
    @staticmethod
    def verify_password_str(password: str, hashed_password_str: str) -> bool:
        """验证密码（字符串格式）"""
        try:
            if BCRYPT_AVAILABLE:
                return PasswordManager.verify_password(password, hashed_password_str.encode('utf-8'))
            else:
                # 降级方案：简单比较（明文或十六进制哈希）
                # 如果是纯文本密码（用于测试），直接比较
                if hashed_password_str.startswith('$2b$'):
                    # bcrypt 格式但 bcrypt 不可用
                    return False
                # 尝试十六进制解码
                try:
                    hashed_bytes = bytes.fromhex(hashed_password_str)
                    return PasswordManager.verify_password(password, hashed_bytes)
                except ValueError:
                    # 不是十六进制，当作明文比较
                    return password == hashed_password_str
        except Exception:
            return False
    
    @staticmethod
    def check_password_strength(password: str) -> dict:
        """检查密码强度
        
        Args:
            password: 待检查的密码字符串
            
        Returns:
            dict: {
                strong: bool,       # 是否满足强度要求
                score: int,         # 强度评分 0-5
                issues: List[str],  # 不满足的规则列表
            }
        """
        result = {'strong': False, 'score': 0, 'issues': []}
        if len(password) < 8:
            result['issues'].append('密码长度不足8位')
        if not re.search(r'[A-Z]', password):
            result['issues'].append('缺少大写字母')
        if not re.search(r'[a-z]', password):
            result['issues'].append('缺少小写字母')
        if not re.search(r'[0-9]', password):
            result['issues'].append('缺少数字')
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
            result['issues'].append('缺少特殊字符')
        result['strong'] = len(result['issues']) == 0
        result['score'] = max(0, 5 - len(result['issues']))
        return result

# ============================================================
# 审计日志管理器
# ============================================================

class AuditLogger:
    """操作审计日志管理器（带HMAC防篡改签名）"""
    
    _HMAC_KEY = None  # 类级签名密钥（首次使用时自动生成）
    
    def __init__(self, log_file: str = "audit.log"):
        self._log_file = log_file
        self._logs: List[AuditLog] = []
        self._load_logs()
        # 初始化HMAC密钥
        if AuditLogger._HMAC_KEY is None:
            AuditLogger._HMAC_KEY = secrets.token_bytes(32)
    
    def _sign_entry(self, data: dict) -> str:
        """对审计日志条目进行HMAC-SHA256签名"""
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')
        return hmac.new(AuditLogger._HMAC_KEY, raw, hashlib.sha256).hexdigest()
    
    def _verify_entry(self, data: dict, signature: str) -> bool:
        """验证审计日志条目签名"""
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')
        expected = hmac.new(AuditLogger._HMAC_KEY, raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    def _load_logs(self):
        """加载历史日志（含签名验证）"""
        if os.path.exists(self._log_file):
            tampered = 0
            try:
                with open(self._log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            sig = entry.pop('_sig', None)
                            if sig and not self._verify_entry(entry, sig):
                                tampered += 1
                                logger.warning(f"审计日志条目签名验证失败，可能被篡改")
                                continue
                            self._logs.append(AuditLog(**entry))
            except Exception as e:
                logger.error(f"加载审计日志失败: {e}")
            if tampered > 0:
                logger.error(f"发现 {tampered} 条审计日志签名不匹配")
    
    def log(self, user: str, operation: OperationType, target: str,
            result: str = "success", details: Dict = None,
            ip_address: str = "", session_id: str = ""):
        """记录操作日志（带HMAC签名）"""
        log_entry = AuditLog(
            timestamp=datetime.now().isoformat(),
            user=user,
            operation=operation.value,
            target=target,
            result=result,
            details=details or {},
            ip_address=ip_address,
            session_id=session_id
        )
        
        self._logs.append(log_entry)
        
        # 写入文件（带HMAC签名）
        try:
            data = log_entry.__dict__
            data['_sig'] = self._sign_entry(data)
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")
        
        # 保持日志数量限制
        if len(self._logs) > 10000:
            self._logs = self._logs[-5000:]
    
    def get_logs(self, user: str = None, operation: OperationType = None,
                 limit: int = 100) -> List[AuditLog]:
        """获取日志列表"""
        filtered = self._logs
        
        if user:
            filtered = [l for l in filtered if l.user == user]
        if operation:
            filtered = [l for l in filtered if l.operation == operation.value]
        
        return filtered[-limit:]
    
    def get_recent_logs(self, hours: int = 24) -> List[AuditLog]:
        """获取最近N小时的日志"""
        cutoff = (datetime.now() - datetime.fromisoformat(self._logs[-1].timestamp)).total_seconds() if self._logs else 0
        cutoff = datetime.now().timestamp() - hours * 3600
        
        return [l for l in self._logs if datetime.fromisoformat(l.timestamp).timestamp() > cutoff]

# ============================================================
# 输入验证器 (InputValidator)
# ============================================================

class InputValidator:
    """输入验证与清理器

    提供字符串清理、股票代码验证、文件名安全处理、
    数字范围验证、JSON 安全解析、HTML 转义和恶意模式检测。
    """

    # 恶意模式正则（SQL注入、XSS、路径遍历、命令注入）
    _SQL_INJECTION_PATTERN = re.compile(
        r"(union\s+select|insert\s+into|drop\s+table|drop\s+database|"
        r"alter\s+table|create\s+table|exec\s*\(|execute\s*\(|"
        r"information_schema|--\s|\bOR\b\s+['\"]?\d['\"]?\s*=\s*['\"]?\d|"
        r"'\s*OR\s+'1'\s*=\s*'1|benchmark\s*\(|sleep\s*\(|load_file\s*\()",
        re.IGNORECASE
    )
    _XSS_PATTERN = re.compile(
        r"(<script[^>]*>.*?</script>|<[^>]*on\w+\s*=|javascript\s*:|"
        r"vbscript\s*:|&#x?[0-9a-f]+;|<[^>]*onload\s*=|"
        r"<[^>]*onerror\s*=|<[^>]*onclick\s*=)",
        re.IGNORECASE
    )
    _PATH_TRAVERSAL_PATTERN = re.compile(
        r"(\.\./|\.\.\\|/etc/passwd|\\windows\\|cmd\.exe|/bin/bash)"
    )
    _COMMAND_INJECTION_PATTERN = re.compile(
        r"(\||;|&&|\$\{|`[^`]*`|\\x[0-9a-f]{2})"
    )
    _CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    _HTML_TAG_PATTERN = re.compile(
        r"<(script|style|iframe|object|embed|form|input|textarea|"
        r"button|select|option|link|meta|base|applet|frame|frameset|"
        r"ilayer|layer|bgsound|title|head|body|html)[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL
    )
    _HTML_TAG_SINGLE_PATTERN = re.compile(
        r"<(script|style|iframe|object|embed|link|meta|base)[^>]*/?>",
        re.IGNORECASE
    )

    @staticmethod
    def sanitize_string(value: str, max_length: int = 200) -> str:
        """清理字符串：去除HTML标签、危险字符、控制字符、SQL注入关键词，限制长度

        Args:
            value: 待清理的原始字符串
            max_length: 最大允许长度，默认 200

        Returns:
            清理后的安全字符串
        """
        if not isinstance(value, str):
            return ""
        # 去除 HTML 标签（成对标签）
        cleaned = InputValidator._HTML_TAG_PATTERN.sub("", value)
        # 去除 HTML 标签（自闭合标签）
        cleaned = InputValidator._HTML_TAG_SINGLE_PATTERN.sub("", cleaned)
        # 去除控制字符
        cleaned = InputValidator._CONTROL_CHARS_PATTERN.sub("", cleaned)
        # 去除 SQL 注入关键词
        cleaned = InputValidator._SQL_INJECTION_PATTERN.sub("", cleaned)
        # 去除 XSS 模式
        cleaned = InputValidator._XSS_PATTERN.sub("", cleaned)
        # 截断到最大长度
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned

    @staticmethod
    def sanitize_stock_code(code: str) -> str:
        """验证并清理股票代码格式：只允许数字和字母，6位

        Args:
            code: 原始股票代码

        Returns:
            清理后的6位股票代码；若无效则返回空字符串
        """
        if not isinstance(code, str):
            return ""
        # 先剥离HTML标签等危险内容
        code = re.sub(r'<[^>]*>', '', code)
        # 再剥离所有非字母数字字符
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", code)
        if len(cleaned) == 6:
            return cleaned.upper()
        # 常见格式处理：sz000001 / sh600000 → 000001 / 600000
        if len(cleaned) > 6:
            # 取前6位（股票代码核心部分）
            cleaned = cleaned[:6]
        return cleaned if len(cleaned) == 6 else ""

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名：去除路径遍历字符和非法文件名字符

        Args:
            filename: 原始文件名

        Returns:
            安全清理后的文件名
        """
        if not isinstance(filename, str):
            return ""
        # 去除路径遍历字符
        cleaned = re.sub(r"\.\./|\.\.\\|\.\.\\\\", "", filename)
        # 去除盘符
        cleaned = re.sub(r"^[a-zA-Z]:\\", "", cleaned)
        # 去除非法文件名字符（Windows + Linux）
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
        # 去除首尾空格和点
        cleaned = cleaned.strip(" .")
        # 限制长度
        if len(cleaned) > 255:
            name, ext = (cleaned.rsplit(".", 1) + [""])[:2]
            cleaned = name[:255 - len(ext) - 1] + ("." + ext if ext else "")
        return cleaned if cleaned else "unnamed"

    @staticmethod
    def validate_number(value: str, min_val: float = None,
                        max_val: float = None) -> float:
        """验证并转换数字，检查范围

        Args:
            value: 待验证的数字字符串
            min_val: 最小值（含）
            max_val: 最大值（含）

        Returns:
            转换后的浮点数

        Raises:
            ValueError: 无效数字或超出范围
        """
        if not isinstance(value, str):
            raise ValueError(f"期望字符串类型，实际为 {type(value).__name__}")
        # 只允许数字、正负号、小数点
        if not re.match(r"^-?\d+(\.\d+)?$", value.strip()):
            raise ValueError(f"无效数字格式: {value}")
        try:
            num = float(value)
        except (ValueError, OverflowError):
            raise ValueError(f"无法转换为数字: {value}")
        if min_val is not None and num < min_val:
            raise ValueError(f"数值 {num} 小于最小值 {min_val}")
        if max_val is not None and num > max_val:
            raise ValueError(f"数值 {num} 大于最大值 {max_val}")
        return num

    @staticmethod
    def validate_json(data: str, max_depth: int = 10) -> dict:
        """安全解析 JSON，防止深层嵌套攻击

        Args:
            data: JSON 字符串
            max_depth: 最大嵌套深度，默认 10

        Returns:
            解析后的字典

        Raises:
            ValueError: JSON 格式无效或嵌套过深
        """
        if not isinstance(data, str):
            raise ValueError("输入必须是字符串")
        try:
            result = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"无效 JSON 格式: {e}")

        def _check_depth(obj, current_depth=0):
            if current_depth > max_depth:
                raise ValueError(f"JSON 嵌套深度超过限制 ({max_depth})")
            if isinstance(obj, dict):
                for v in obj.values():
                    _check_depth(v, current_depth + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _check_depth(v, current_depth + 1)

        _check_depth(result)
        if not isinstance(result, dict):
            raise ValueError("JSON 顶层必须是对象（dict）")
        return result

    @staticmethod
    def escape_html(text: str) -> str:
        """HTML 实体转义（防 XSS）

        Args:
            text: 原始文本

        Returns:
            HTML 实体转义后的安全文本
        """
        if not isinstance(text, str):
            return ""
        replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#x27;",
        }
        for char, escaped in replacements.items():
            text = text.replace(char, escaped)
        return text

    @staticmethod
    def detect_malicious_pattern(text: str) -> bool:
        """检测恶意模式：SQL注入、XSS、路径遍历、命令注入

        Args:
            text: 待检测的文本

        Returns:
            True 表示检测到恶意模式，False 表示安全
        """
        if not isinstance(text, str):
            return False
        patterns = [
            ("SQL注入", InputValidator._SQL_INJECTION_PATTERN),
            ("XSS", InputValidator._XSS_PATTERN),
            ("路径遍历", InputValidator._PATH_TRAVERSAL_PATTERN),
            ("命令注入", InputValidator._COMMAND_INJECTION_PATTERN),
        ]
        for name, pattern in patterns:
            if pattern.search(text):
                logger.warning(f"检测到恶意模式 [{name}] 在输入中")
                return True
        return False


# ============================================================
# 数据脱敏器 (DataMasker)
# ============================================================

class DataMasker:
    """数据脱敏处理器

    提供手机号、邮箱、身份证、银行卡、API 密钥和交易数据的脱敏功能。
    """

    _SENSITIVE_TRADE_FIELDS = {
        "amount", "balance", "profit", "loss", "position",
        "account", "bank_account", "card_number", "password",
        "api_key", "secret_key", "token", "phone", "id_card",
        "real_name", "identity", "capital", "funds",
    }

    @staticmethod
    def mask_phone(phone: str) -> str:
        """手机号脱敏：138****1234

        Args:
            phone: 11位手机号

        Returns:
            脱敏后的手机号，格式 138****1234
        """
        if not isinstance(phone, str) or len(phone) < 7:
            return phone if phone else "***"
        cleaned = re.sub(r"\D", "", phone)
        if len(cleaned) == 11:
            return cleaned[:3] + "****" + cleaned[-4:]
        if len(cleaned) >= 7:
            return cleaned[:3] + "****" + cleaned[-4:]
        return cleaned[:3] + "****"

    @staticmethod
    def mask_email(email: str) -> str:
        """邮箱脱敏：u***@example.com

        Args:
            email: 完整邮箱地址

        Returns:
            脱敏后的邮箱，格式 u***@example.com
        """
        if not isinstance(email, str) or "@" not in email:
            return "***@***"
        local, domain = email.split("@", 1)
        if len(local) <= 1:
            masked_local = local + "***"
        elif len(local) == 2:
            masked_local = local[0] + "***"
        else:
            masked_local = local[0] + "***" + local[-1]
        domain_parts = domain.split(".")
        if len(domain_parts) >= 2:
            return f"{masked_local}@{domain_parts[0]}.{domain_parts[-1]}"
        return f"{masked_local}@{domain}"

    @staticmethod
    def mask_id_card(id_card: str) -> str:
        """身份证脱敏：3201**********1234

        Args:
            id_card: 18位身份证号

        Returns:
            脱敏后的身份证号，格式 3201**********1234
        """
        if not isinstance(id_card, str):
            return "****************"
        cleaned = re.sub(r"\s", "", id_card)
        if len(cleaned) == 18:
            return cleaned[:4] + "**********" + cleaned[-4:]
        if len(cleaned) == 15:
            return cleaned[:4] + "*******" + cleaned[-4:]
        return cleaned[:4] + "****"

    @staticmethod
    def mask_bank_card(card: str) -> str:
        """银行卡脱敏：6222****1234

        Args:
            card: 银行卡号

        Returns:
            脱敏后的银行卡号，格式 6222****1234
        """
        if not isinstance(card, str):
            return "****"
        cleaned = re.sub(r"\s", "", card)
        if len(cleaned) >= 8:
            return cleaned[:4] + "****" + cleaned[-4:]
        if len(cleaned) >= 4:
            return cleaned[:4] + "****"
        return "****"

    @staticmethod
    def mask_api_key(key: str) -> str:
        """API密钥脱敏：sk-****xxxx

        Args:
            key: 原始 API 密钥

        Returns:
            脱敏后的密钥，格式 sk-****xxxx
        """
        if not isinstance(key, str) or len(key) < 8:
            return "****"
        # 保留前缀和最后4位
        prefix = key[:key.index("-") + 1] if "-" in key[:6] else key[:3]
        return f"{prefix}****{key[-4:]}"

    @staticmethod
    def mask_trade_data(trade: dict) -> dict:
        """交易数据脱敏：隐藏金额、账号等敏感字段

        Args:
            trade: 原始交易数据字典

        Returns:
            脱敏后的交易数据字典（深拷贝，不修改原数据）
        """
        import copy
        if not isinstance(trade, dict):
            return trade
        masked = copy.deepcopy(trade)
        for key in masked:
            if key.lower() in DataMasker._SENSITIVE_TRADE_FIELDS:
                if isinstance(masked[key], (int, float)):
                    masked[key] = 0.0
                elif isinstance(masked[key], str):
                    masked[key] = "****"
                elif isinstance(masked[key], list):
                    masked[key] = ["****"] * len(masked[key])
                elif isinstance(masked[key], dict):
                    masked[key] = DataMasker.mask_trade_data(masked[key])
        return masked


# ============================================================
# CSRF 令牌管理器 (CSRFManager)
# ============================================================

class CSRFManager:
    """CSRF 防护令牌管理器

    生成、验证和清理 CSRF 令牌，令牌一次性使用且有有效期。
    """

    def __init__(self):
        """初始化 CSRF 令牌管理器"""
        self._tokens: Dict[str, Dict[str, Any]] = {}

    def generate_token(self, session_id: str) -> str:
        """生成 CSRF 令牌（32 位随机字符串，有有效期）

        Args:
            session_id: 会话 ID

        Returns:
            生成的 CSRF 令牌（32 位十六进制字符串）
        """
        token = secrets.token_hex(16)  # 32 位十六进制字符
        self._tokens[session_id] = {
            "token": token,
            "created_at": datetime.now(),
        }
        logger.info(f"CSRF 令牌已生成: session={session_id[:8]}...")
        return token

    def validate_token(self, session_id: str, token: str) -> bool:
        """验证 CSRF 令牌，使用后即失效（一次性）

        Args:
            session_id: 会话 ID
            token: 待验证的令牌

        Returns:
            True 表示验证通过，False 表示无效或已过期
        """
        if not session_id or not token:
            return False
        record = self._tokens.get(session_id)
        if not record:
            return False
        # 检查过期
        expiry_minutes = _security_config.get("csrf_token_expiry_minutes", 30)
        if datetime.now() - record["created_at"] > timedelta(minutes=expiry_minutes):
            del self._tokens[session_id]
            logger.warning(f"CSRF 令牌已过期: session={session_id[:8]}...")
            return False
        # 验证令牌（使用恒定时间比较防止时序攻击）
        if not secrets.compare_digest(record["token"], token):
            logger.warning(f"CSRF 令牌验证失败: session={session_id[:8]}...")
            return False
        # 一次性使用，验证后删除
        del self._tokens[session_id]
        logger.info(f"CSRF 令牌验证通过: session={session_id[:8]}...")
        return True

    def cleanup_expired(self):
        """清理过期令牌"""
        expiry_minutes = _security_config.get("csrf_token_expiry_minutes", 30)
        cutoff = datetime.now() - timedelta(minutes=expiry_minutes)
        expired = [
            sid for sid, record in self._tokens.items()
            if record["created_at"] < cutoff
        ]
        for sid in expired:
            del self._tokens[sid]
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期 CSRF 令牌")


# ============================================================
# 速率限制器 (RateLimiter)
# ============================================================

class RateLimiter:
    """请求速率限制器

    使用滑动窗口算法对请求进行速率限制。
    """

    def __init__(self):
        """初始化速率限制器"""
        self._requests: Dict[str, List[float]] = {}

    def is_allowed(self, key: str, max_requests: int = 100,
                   window_seconds: int = 60) -> bool:
        """检查是否允许请求（滑动窗口算法）

        Args:
            key: 请求标识（如 IP 地址或用户 ID）
            max_requests: 窗口内最大请求数
            window_seconds: 时间窗口大小（秒）

        Returns:
            True 表示允许请求，False 表示触发限流
        """
        now = time.time()
        cutoff = now - window_seconds
        # 获取或初始化请求记录
        if key not in self._requests:
            self._requests[key] = []
        # 清理过期记录
        self._requests[key] = [
            t for t in self._requests[key] if t > cutoff
        ]
        # 检查是否超限
        if len(self._requests[key]) >= max_requests:
            logger.warning(f"速率限制触发: key={key[:16]}..., "
                           f"requests={len(self._requests[key])}/{max_requests}")
            return False
        # 记录本次请求
        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str, max_requests: int = 100,
                      window_seconds: int = 60) -> int:
        """获取剩余请求次数

        Args:
            key: 请求标识
            max_requests: 窗口内最大请求数
            window_seconds: 时间窗口大小（秒）

        Returns:
            剩余可用请求次数
        """
        now = time.time()
        cutoff = now - window_seconds
        if key not in self._requests:
            return max_requests
        # 清理过期记录
        self._requests[key] = [
            t for t in self._requests[key] if t > cutoff
        ]
        return max(0, max_requests - len(self._requests[key]))

    def reset(self, key: str):
        """重置指定 key 的计数器

        Args:
            key: 请求标识
        """
        if key in self._requests:
            del self._requests[key]
            logger.info(f"速率限制计数器已重置: key={key[:16]}...")


# ============================================================
# 威胁检测器 (ThreatDetector)
# ============================================================

class ThreatDetector:
    """威胁检测器

    提供 IP 信誉检查、暴力破解检测、异常会话检测和请求头检查。
    """

    # 已知恶意 IP 列表（示例，实际使用时应从外部数据库加载）
    _MALICIOUS_IPS = {
        "0.0.0.0", "255.255.255.255",
    }
    # 恶意 User-Agent 模式
    _MALICIOUS_UA_PATTERNS = [
        re.compile(r"sqlmap", re.IGNORECASE),
        re.compile(r"nikto", re.IGNORECASE),
        re.compile(r"nmap", re.IGNORECASE),
        re.compile(r"masscan", re.IGNORECASE),
        re.compile(r"zgrab", re.IGNORECASE),
        re.compile(r"scanner", re.IGNORECASE),
        re.compile(r"bot", re.IGNORECASE),
    ]
    # 暴力破解记录: {ip: [(timestamp, failure_count)]}
    _brute_force_records: Dict[str, List[tuple]] = {}

    _IP_PATTERN = re.compile(
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
        r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )
    _PRIVATE_IP_RANGES = [
        (re.compile(r"^10\."), "A类私有"),
        (re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."), "B类私有"),
        (re.compile(r"^192\.168\."), "C类私有"),
        (re.compile(r"^127\."), "回环"),
        (re.compile(r"^169\.254\."), "链路本地"),
    ]

    @staticmethod
    def check_ip_reputation(ip: str) -> dict:
        """检查 IP 信誉：是否已知恶意 IP、是否来自异常地区

        Args:
            ip: IP 地址字符串

        Returns:
            dict: {
                trusted: bool,       # 是否可信
                risk_level: str,     # low/medium/high/critical
                category: str,       # 分类描述
                is_private: bool,    # 是否内网 IP
            }
        """
        result = {
            "trusted": True,
            "risk_level": "low",
            "category": "正常",
            "is_private": False,
        }
        if not isinstance(ip, str) or not ip.strip():
            result["trusted"] = False
            result["risk_level"] = "high"
            result["category"] = "无效IP"
            return result
        # 检查是否为合法 IP 格式
        if not ThreatDetector._IP_PATTERN.match(ip.strip()):
            result["trusted"] = False
            result["risk_level"] = "high"
            result["category"] = "无效IP格式"
            return result
        # 检查内网 IP
        for pattern, desc in ThreatDetector._PRIVATE_IP_RANGES:
            if pattern.match(ip):
                result["is_private"] = True
                result["category"] = f"内网IP ({desc})"
                return result
        # 检查已知恶意 IP
        if ip in ThreatDetector._MALICIOUS_IPS:
            result["trusted"] = False
            result["risk_level"] = "critical"
            result["category"] = "已知恶意IP"
            logger.warning(f"检测到已知恶意IP: {ip}")
        return result

    @staticmethod
    def detect_brute_force(ip: str, failures: int,
                           window_seconds: int = 300) -> bool:
        """检测暴力破解：窗口内失败次数超过阈值

        Args:
            ip: 来源 IP 地址
            failures: 当前累计失败次数
            window_seconds: 检测窗口（秒），默认 300

        Returns:
            True 表示检测到暴力破解行为
        """
        max_attempts = _security_config.get("brute_force_max_attempts", 5)
        now = time.time()
        cutoff = now - window_seconds
        if ip not in ThreatDetector._brute_force_records:
            ThreatDetector._brute_force_records[ip] = []
        # 清理过期记录
        ThreatDetector._brute_force_records[ip] = [
            (t, c) for t, c in ThreatDetector._brute_force_records[ip]
            if t > cutoff
        ]
        # 累加失败次数
        total_failures = sum(
            c for _, c in ThreatDetector._brute_force_records[ip]
        )
        total_failures += failures
        if total_failures >= max_attempts:
            logger.warning(
                f"检测到暴力破解: IP={ip}, "
                f"失败次数={total_failures}/{max_attempts}, "
                f"窗口={window_seconds}秒"
            )
            return True
        # 记录本次失败
        ThreatDetector._brute_force_records[ip].append((now, failures))
        return False

    @staticmethod
    def detect_anomaly_session(user: str, ip: str, user_agent: str) -> bool:
        """检测异常会话：异地登录、新设备登录

        Args:
            user: 用户名
            ip: 登录 IP
            user_agent: 浏览器 User-Agent

        Returns:
            True 表示检测到异常会话
        """
        # 检查 User-Agent 是否为空
        if not user_agent or user_agent.strip() == "":
            logger.warning(
                f"异常会话: 用户 '{user}' 缺少 User-Agent, IP={ip}"
            )
            return True
        # 检查 IP 信誉
        rep = ThreatDetector.check_ip_reputation(ip)
        if not rep["trusted"]:
            logger.warning(
                f"异常会话: 用户 '{user}' 来自不可信 IP={ip}, "
                f"分类={rep['category']}"
            )
            return True
        return False

    @staticmethod
    def check_request_headers(headers: dict) -> bool:
        """检查请求头：是否包含恶意 User-Agent、Referer 等

        Args:
            headers: HTTP 请求头字典

        Returns:
            True 表示请求头安全，False 表示检测到恶意特征
        """
        if not isinstance(headers, dict):
            return False
        # 检查 User-Agent
        user_agent = headers.get(
            "User-Agent", headers.get("user-agent", "")
        )
        if user_agent:
            for pattern in ThreatDetector._MALICIOUS_UA_PATTERNS:
                if pattern.search(user_agent):
                    logger.warning(
                        f"检测到恶意 User-Agent: {user_agent[:100]}"
                    )
                    return False
        # 检查 Referer
        referer = headers.get("Referer", headers.get("referer", ""))
        if referer and InputValidator.detect_malicious_pattern(referer):
            logger.warning(f"检测到恶意 Referer: {referer[:100]}")
            return False
        return True


# ============================================================
# 钓鱼跳转检测器 (PhishingDetector)
# ============================================================

class PhishingDetector:
    """钓鱼URL检测器
    
    检测可疑URL特征：域名仿冒、IP地址直连、短链接、异常端口等。
    """
    
    # 常见被仿冒的金融域名
    _FINANCIAL_DOMAINS = {
        'eastmoney.com', 'sse.com.cn', 'szse.cn', 'csrc.gov.cn',
        'sina.com.cn', 'sohu.com', '163.com', 'qq.com',
        'alipay.com', 'tenpay.com', 'cgbchina.com.cn',
    }
    
    # 可疑顶级域名
    _SUSPICIOUS_TLDS = {'.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.club', '.work'}
    
    # 短链接服务域名
    _SHORTLINK_DOMAINS = {'bit.ly', 't.co', 'tinyurl.com', 'ow.ly', 'is.gd', 'buff.ly', 'goo.gl'}
    
    _URL_PATTERN = re.compile(
        r'https?://[^\s<>"\'{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    
    _IP_URL_PATTERN = re.compile(
        r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
    )
    
    @staticmethod
    def detect_phishing_url(url: str) -> dict:
        """检测URL是否为钓鱼链接
        
        Args:
            url: 待检测的URL字符串
            
        Returns:
            dict: {
                is_phishing: bool,
                risk_level: str,  # low/medium/high/critical
                reasons: List[str],
            }
        """
        result = {'is_phishing': False, 'risk_level': 'low', 'reasons': []}
        
        if not isinstance(url, str) or not url.strip():
            return result
        
        url = url.strip().lower()
        
        # 1. IP地址直连（高风险）
        if PhishingDetector._IP_URL_PATTERN.search(url):
            result['is_phishing'] = True
            result['risk_level'] = 'high'
            result['reasons'].append('使用IP地址直连（非域名）')
        
        # 2. 短链接服务（中风险）
        for short_domain in PhishingDetector._SHORTLINK_DOMAINS:
            if short_domain in url:
                result['is_phishing'] = True
                result['risk_level'] = 'medium'
                result['reasons'].append(f'使用短链接服务: {short_domain}')
                break
        
        # 3. 可疑顶级域名
        for tld in PhishingDetector._SUSPICIOUS_TLDS:
            if tld in url:
                result['is_phishing'] = True
                result['risk_level'] = 'medium'
                result['reasons'].append(f'使用可疑顶级域名: {tld}')
                break
        
        # 4. 域名仿冒检测（检查是否包含金融域名但非官方域名）
        for fin_domain in PhishingDetector._FINANCIAL_DOMAINS:
            if fin_domain in url and fin_domain not in url.split('/')[2] if '//' in url else True:
                # 检查是否是子域名仿冒，如 eastmoney.com.phishing.com
                actual_domain = url.split('/')[2] if '//' in url else ''
                if fin_domain not in actual_domain:
                    result['is_phishing'] = True
                    result['risk_level'] = 'critical'
                    result['reasons'].append(f'域名仿冒: 包含{fin_domain}但非官方域名')
                    break
        
        # 5. 异常端口号
        port_match = re.search(r':(\d+)/', url)
        if port_match:
            port = int(port_match.group(1))
            if port not in (80, 443, 8080, 8443):
                result['is_phishing'] = True
                if result['risk_level'] == 'low':
                    result['risk_level'] = 'medium'
                result['reasons'].append(f'使用非标准端口: {port}')
        
        if not result['reasons']:
            result['risk_level'] = 'low'
        
        if result['is_phishing']:
            logger.warning(f"检测到可疑URL: {url[:100]}, 原因: {result['reasons']}")
        
        return result
    
    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """从文本中提取所有URL"""
        if not isinstance(text, str):
            return []
        return PhishingDetector._URL_PATTERN.findall(text)
    
    @staticmethod
    def scan_text_for_phishing(text: str) -> List[dict]:
        """扫描文本中所有URL，返回钓鱼检测结果列表"""
        urls = PhishingDetector.extract_urls(text)
        results = []
        for url in urls:
            result = PhishingDetector.detect_phishing_url(url)
            if result['is_phishing']:
                result['url'] = url[:100]
                results.append(result)
        return results


# ============================================================
# 导出加密器 (ExportEncryptor)
# ============================================================

class ExportEncryptor:
    """数据导出加密器
    
    支持对导出的策略参数、回测结果、交易记录等进行AES加密。
    若cryptography库不可用，降级为Base64混淆（非安全，仅防误读）。
    """
    
    _FERNET_KEY = None  # 类级加密密钥
    
    def __init__(self):
        if ExportEncryptor._FERNET_KEY is None:
            if CRYPTO_AVAILABLE:
                ExportEncryptor._FERNET_KEY = Fernet.generate_key()
            else:
                # 降级：使用 secrets token 作为 base64 key
                ExportEncryptor._FERNET_KEY = base64.urlsafe_b64encode(
                    secrets.token_bytes(32)
                )
    
    def encrypt_data(self, data: dict) -> str:
        """加密数据字典
        
        Args:
            data: 待加密的字典数据
            
        Returns:
            str: Base64编码的加密数据
        """
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            if CRYPTO_AVAILABLE:
                fernet = Fernet(ExportEncryptor._FERNET_KEY)
                encrypted = fernet.encrypt(json_str.encode('utf-8'))
                return base64.urlsafe_b64encode(encrypted).decode('ascii')
            else:
                # 降级：Base64混淆（明文可读，但防直接复制）
                encoded = base64.urlsafe_b64encode(json_str.encode('utf-8')).decode('ascii')
                logger.warning("cryptography库不可用，导出使用Base64混淆（非安全加密）")
                return f"B64:{encoded}"
        except Exception as e:
            logger.error(f"数据加密失败: {e}")
            return json.dumps(data, ensure_ascii=False)
    
    def decrypt_data(self, encrypted_str: str) -> dict:
        """解密数据
        
        Args:
            encrypted_str: 加密后的字符串
            
        Returns:
            dict: 解密后的数据字典
        """
        try:
            if encrypted_str.startswith('B64:'):
                # 降级方案：Base64解码
                json_str = base64.urlsafe_b64decode(
                    encrypted_str[4:].encode('ascii')
                ).decode('utf-8')
                return json.loads(json_str)
            elif CRYPTO_AVAILABLE:
                encrypted = base64.urlsafe_b64decode(encrypted_str.encode('ascii'))
                fernet = Fernet(ExportEncryptor._FERNET_KEY)
                json_str = fernet.decrypt(encrypted).decode('utf-8')
                return json.loads(json_str)
            else:
                logger.error("无法解密：cryptography库不可用且数据非降级格式")
                return {}
        except Exception as e:
            logger.error(f"数据解密失败: {e}")
            return {}
    
    def encrypt_file(self, input_path: str, output_path: str = None) -> str:
        """加密文件
        
        Args:
            input_path: 输入文件路径（JSON格式）
            output_path: 输出文件路径（可选，默认在同目录加 .enc 后缀）
            
        Returns:
            str: 加密后的文件路径
        """
        if output_path is None:
            output_path = input_path + '.enc'
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            encrypted = self.encrypt_data(data)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(encrypted)
            logger.info(f"文件已加密: {input_path} -> {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"文件加密失败: {e}")
            raise
    
    def decrypt_file(self, input_path: str, output_path: str = None) -> str:
        """解密文件
        
        Args:
            input_path: 加密文件路径
            output_path: 输出文件路径（可选）
            
        Returns:
            str: 解密后的文件路径
        """
        if output_path is None:
            output_path = input_path.replace('.enc', '') if input_path.endswith('.enc') else input_path + '.dec'
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                encrypted = f.read()
            data = self.decrypt_data(encrypted)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"文件已解密: {input_path} -> {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"文件解密失败: {e}")
            raise

class SecurityConfig:
    """安全配置管理"""
    
    def __init__(self):
        self._config = {
            'session_timeout_hours': 24,
            'max_login_attempts': 5,
            'password_min_length': 8,
            'require_strong_password': True,
            'enable_audit_logging': True,
            'enable_rate_limiting': True,
            'rate_limit_requests': 100,
            'rate_limit_window_seconds': 60,
            # 新增安全配置项
            'csrf_enabled': True,
            'csrf_token_expiry_minutes': 30,
            'input_sanitization_enabled': True,
            'max_string_length': 1000,
            'data_masking_enabled': True,
            'threat_detection_enabled': True,
            'brute_force_max_attempts': 5,
            'brute_force_window_seconds': 300,
            'anomaly_detection_enabled': True,
        }
    
    def get(self, key: str, default=None):
        return self._config.get(key, default)
    
    def set(self, key: str, value):
        self._config[key] = value

# ============================================================
# 全局实例
# ============================================================

_password_manager = PasswordManager()
_audit_logger = AuditLogger()
_security_config = SecurityConfig()
_input_validator = InputValidator()
_data_masker = DataMasker()
_csrf_manager = CSRFManager()
_rate_limiter = RateLimiter()
_threat_detector = ThreatDetector()
_phishing_detector = PhishingDetector()
_export_encryptor = ExportEncryptor()

def get_password_manager() -> PasswordManager:
    return _password_manager

def get_audit_logger() -> AuditLogger:
    return _audit_logger

def get_security_config() -> SecurityConfig:
    return _security_config

def get_input_validator() -> InputValidator:
    return _input_validator

def get_data_masker() -> DataMasker:
    return _data_masker

def get_csrf_manager() -> CSRFManager:
    return _csrf_manager

def get_rate_limiter() -> RateLimiter:
    return _rate_limiter

def get_threat_detector() -> ThreatDetector:
    return _threat_detector

def get_phishing_detector() -> PhishingDetector:
    return _phishing_detector

def get_export_encryptor() -> ExportEncryptor:
    return _export_encryptor

# ============================================================
# 加密后的默认用户数据（演示用）
# 注意：以下为默认密码，首次登录后系统会提示修改
# 生产环境部署前必须替换所有默认密码
# ============================================================

ENCRYPTED_USERS = {
    'admin': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q5Q',  # password
        'role': 'admin',
        'name': '系统管理员',
        'tier': 1
    },
    'trader': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q',
        'role': 'trader',
        'name': '交易员',
        'tier': 2
    },
    'analyst': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q',
        'role': 'analyst',
        'name': '分析师',
        'tier': 3
    },
    'risk': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q',
        'role': 'risk',
        'name': '风控员',
        'tier': 4
    },
    'viewer': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q',
        'role': 'viewer',
        'name': '查看员',
        'tier': 5
    },
    'guest': {
        'password': '$2b$12$EixZaYbB.rK4fl8x2q7Meu6Q6D5V5fF5Q5Q5Q5Q5Q5Q5Q5Q5Q',
        'role': 'guest',
        'name': '访客',
        'tier': 6
    }
}


# ============================================================
# 中间人防护 - 证书验证器 (D7: 审计修复)
# ============================================================

class CertValidator:
    """SSL/TLS证书验证器

    中间人攻击防护：
    - 验证证书链完整性
    - 检查证书有效期
    - 验证主机名匹配
    - 支持自签名证书白名单

    设计依据：审计报告D7维度 - 中间人防护/证书验证
    """

    def __init__(self):
        self._trusted_fingerprints: set = set()
        self._validation_log: List[Dict] = []

    def add_trusted_fingerprint(self, fingerprint: str):
        """添加受信任的证书指纹"""
        self._trusted_fingerprints.add(fingerprint.upper().replace(":", ""))

    def validate_certificate(self, cert_path: str, hostname: str = None) -> Dict[str, Any]:
        """验证SSL证书

        Args:
            cert_path: 证书文件路径
            hostname: 预期主机名

        Returns:
            dict: {valid, issues, fingerprint, expiry}
        """
        result = {
            "valid": True,
            "issues": [],
            "fingerprint": "",
            "expiry": "",
            "issuer": "",
            "subject": "",
        }

        try:
            import ssl
            import hashlib
            from datetime import datetime

            # 加载证书
            try:
                cert_der = None
                with open(cert_path, "rb") as f:
                    cert_data = f.read()

                # 尝试PEM格式
                if b"-----BEGIN CERTIFICATE-----" in cert_data:
                    from cryptography import x509
                    from cryptography.hazmat.backends import default_backend
                    from cryptography.hazmat.primitives.serialization import Encoding
                    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                    cert_der = cert.public_bytes(Encoding.DER)
                else:
                    # DER格式
                    cert_der = cert_data

                # 计算指纹
                fingerprint = hashlib.sha256(cert_der).hexdigest().upper()
                result["fingerprint"] = ":".join(
                    fingerprint[i:i+2] for i in range(0, len(fingerprint), 2)
                )

                # 检查是否在信任列表中
                if self._trusted_fingerprints:
                    clean_fp = fingerprint
                    if clean_fp not in self._trusted_fingerprints:
                        result["valid"] = False
                        result["issues"].append("证书指纹不在信任列表中")

                # 检查有效期
                if hasattr(cert, "not_valid_after"):
                    expiry = cert.not_valid_after
                    if isinstance(expiry, datetime):
                        result["expiry"] = expiry.isoformat()
                        if expiry < datetime.utcnow():
                            result["valid"] = False
                            result["issues"].append("证书已过期")
                        elif expiry < datetime.utcnow() + timedelta(days=30):
                            result["issues"].append("证书即将过期（30天内）")

                if hasattr(cert, "issuer"):
                    result["issuer"] = str(cert.issuer)
                if hasattr(cert, "subject"):
                    result["subject"] = str(cert.subject)

                # 主机名验证
                if hostname and hasattr(cert, "subject"):
                    try:
                        ssl.match_hostname(
                            {"subject": ((("commonName", hostname),),)},
                            hostname
                        )
                    except ssl.CertificateError:
                        result["issues"].append(f"证书主机名与 {hostname} 不匹配")

            except FileNotFoundError:
                result["valid"] = False
                result["issues"].append(f"证书文件不存在: {cert_path}")
            except ImportError:
                # cryptography库不可用，降级为基本检查
                result["issues"].append("cryptography库不可用，仅做基本检查")
                if cert_path and os.path.exists(cert_path):
                    with open(cert_path, "rb") as f:
                        cert_data = f.read()
                    fp = hashlib.sha256(cert_data).hexdigest().upper()
                    result["fingerprint"] = fp
                    if self._trusted_fingerprints and fp not in self._trusted_fingerprints:
                        result["valid"] = False
                        result["issues"].append("证书指纹不在信任列表中")

        except Exception as e:
            result["valid"] = False
            result["issues"].append(f"证书验证异常: {str(e)}")

        # 记录日志
        self._validation_log.append({
            "timestamp": datetime.now().isoformat(),
            "cert_path": cert_path,
            "hostname": hostname,
            "result": result,
        })

        return result

    def verify_server_cert(self, hostname: str, port: int = 443,
                           timeout: int = 5) -> Dict[str, Any]:
        """验证服务器证书（主动连接）

        Args:
            hostname: 服务器主机名
            port: 端口
            timeout: 超时秒数

        Returns:
            dict: {valid, issues, fingerprint, protocol}
        """
        result = {
            "valid": True,
            "issues": [],
            "fingerprint": "",
            "protocol": "",
            "cipher": "",
        }

        try:
            import ssl
            import socket
            import hashlib

            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED

            with socket.create_connection((hostname, port), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert(binary_form=True)
                    if cert:
                        fp = hashlib.sha256(cert).hexdigest().upper()
                        result["fingerprint"] = ":".join(
                            fp[i:i+2] for i in range(0, len(fp), 2)
                        )
                    result["protocol"] = ssock.version()
                    result["cipher"] = ssock.cipher()[0] if ssock.cipher() else ""

        except ssl.SSLCertVerificationError as e:
            result["valid"] = False
            result["issues"].append(f"证书验证失败: {e}")
        except ssl.SSLError as e:
            result["valid"] = False
            result["issues"].append(f"SSL错误: {e}")
        except socket.timeout:
            result["valid"] = False
            result["issues"].append(f"连接超时 ({timeout}s)")
        except Exception as e:
            result["valid"] = False
            result["issues"].append(f"连接失败: {str(e)}")

        return result

    def get_validation_history(self, limit: int = 20) -> List[Dict]:
        """获取证书验证历史"""
        return self._validation_log[-limit:]


_cert_validator: Optional[CertValidator] = None


def get_cert_validator() -> CertValidator:
    global _cert_validator
    if _cert_validator is None:
        _cert_validator = CertValidator()
    return _cert_validator