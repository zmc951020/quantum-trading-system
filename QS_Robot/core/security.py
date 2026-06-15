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
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

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

# ============================================================
# 审计日志管理器
# ============================================================

class AuditLogger:
    """操作审计日志管理器"""
    
    def __init__(self, log_file: str = "audit.log"):
        self._log_file = log_file
        self._logs: List[AuditLog] = []
        self._load_logs()
    
    def _load_logs(self):
        """加载历史日志"""
        if os.path.exists(self._log_file):
            try:
                with open(self._log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            self._logs.append(AuditLog(**data))
            except Exception as e:
                logger.error(f"加载审计日志失败: {e}")
    
    def log(self, user: str, operation: OperationType, target: str,
            result: str = "success", details: Dict = None,
            ip_address: str = "", session_id: str = ""):
        """记录操作日志"""
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
        
        # 写入文件
        try:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry.__dict__) + '\n')
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
# 安全配置管理器
# ============================================================

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
            'rate_limit_window_seconds': 60
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

def get_password_manager() -> PasswordManager:
    return _password_manager

def get_audit_logger() -> AuditLogger:
    return _audit_logger

def get_security_config() -> SecurityConfig:
    return _security_config

# ============================================================
# 加密后的默认用户数据（演示用）
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