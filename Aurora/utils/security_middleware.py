"""
安全中间件模块
包含：JWT Token认证 + HMAC-SHA256 API签名验证 + IP限流 + RBAC权限

修补项：
- P0-2: JWT Token认证  ✅ 已修补
- P0-4: API接口签名   ✅ 已修补
- P1-3: API限流中间件  ✅ 已修补
- P1-2: RBAC角色权限   ✅ 已修补
"""
import os
import time
import hmac
import hashlib
import secrets
import functools
import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

import jwt as pyjwt

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# JWT配置
JWT_SECRET = os.getenv("AURORA_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("AURORA_JWT_EXPIRY", "24"))

# HMAC签名配置
HMAC_SECRET = os.getenv("AURORA_HMAC_SECRET", secrets.token_hex(32))
HMAC_ALGORITHM = "sha256"
SIGNATURE_TIMESTAMP_WINDOW = 300  # 5分钟时间窗口防重放

# 限流配置
RATE_LIMIT_PER_MINUTE = int(os.getenv("AURORA_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW = 60  # 60秒窗口

# 管理员token（首次启动时自动生成）
ADMIN_API_KEY = os.getenv("AURORA_ADMIN_KEY", secrets.token_urlsafe(24))


# ============================================================
# 角色定义
# ============================================================

class Role(str, Enum):
    ADMIN = "admin"      # 管理员：全部权限
    TRADER = "trader"    # 交易员：交易+策略
    VIEWER = "viewer"    # 观察者：只读
    ANALYST = "analyst"  # 分析师：回测+分析


# 角色→权限映射
ROLE_PERMISSIONS: Dict[Role, List[str]] = {
    Role.ADMIN: ["*"],  # 全部权限
    Role.TRADER: [
        "trade:execute", "trade:cancel", "trade:view",
        "strategy:start", "strategy:stop", "strategy:view",
        "pool:view", "pool:manage",
        "risk:view",
        "technical:view",
        "broker:view",
    ],
    Role.ANALYST: [
        "backtest:run", "backtest:view",
        "strategy:view", "strategy:optimize",
        "technical:view", "technical:analyze",
        "data:view",
        "report:generate",
    ],
    Role.VIEWER: [
        "trade:view",
        "strategy:view",
        "pool:view",
        "risk:view",
        "technical:view",
        "data:view",
        "report:view",
    ],
}


# ============================================================
# 数据模型
# ============================================================

@dataclass
class UserSession:
    """用户会话"""
    user_id: str
    username: str
    role: Role
    token: str
    created_at: datetime
    expires_at: datetime
    ip_address: str = "127.0.0.1"
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


@dataclass  
class RateLimitEntry:
    """限流记录"""
    count: int = 0
    window_start: float = 0.0
    blocked_until: float = 0.0


# ============================================================
# Token管理器
# ============================================================

class TokenManager:
    """
    JWT Token 管理器
    
    修补项 P0-2：替换session为JWT Token
    """
    
    def __init__(self, secret: str = JWT_SECRET, algorithm: str = JWT_ALGORITHM):
        self.secret = secret
        self.algorithm = algorithm
        self._blacklist: Dict[str, datetime] = {}  # token黑名单
        self._sessions: Dict[str, UserSession] = {}
        logger.info(f"TokenManager已初始化（算法: {algorithm}）")
    
    def create_token(
        self,
        user_id: str,
        username: str,
        role: Role = Role.VIEWER,
        expiration_hours: int = JWT_EXPIRATION_HOURS,
        ip_address: str = "127.0.0.1",
    ) -> Tuple[str, UserSession]:
        """
        创建JWT Token
        
        Returns:
            (token字符串, UserSession对象)
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=expiration_hours)
        
        payload = {
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "iat": now,
            "exp": expires_at,
            "jti": secrets.token_hex(8),  # 唯一标识用于黑名单
            "ip": ip_address,
        }
        
        token = pyjwt.encode(payload, self.secret, algorithm=self.algorithm)
        
        session = UserSession(
            user_id=user_id,
            username=username,
            role=role,
            token=token,
            created_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
        )
        
        self._sessions[payload["jti"]] = session
        logger.info(f"Token已创建: user={username}, role={role.value}, jti={payload['jti']}")
        
        return token, session
    
    def verify_token(self, token: str) -> Optional[UserSession]:
        """
        验证Token有效性
        
        Returns:
            UserSession或None(无效)
        """
        try:
            # 先检查黑名单
            try:
                payload = pyjwt.decode(token, self.secret, algorithms=[self.algorithm], options={"verify_exp": False})
                jti = payload.get("jti")
                if jti in self._blacklist:
                    logger.warning(f"Token在黑名单中: jti={jti}")
                    return None
            except Exception:
                pass
            
            # 完整验证
            payload = pyjwt.decode(token, self.secret, algorithms=[self.algorithm])
            
            role = Role(payload.get("role", "viewer"))
            session = UserSession(
                user_id=payload["user_id"],
                username=payload["username"],
                role=role,
                token=token,
                created_at=datetime.fromtimestamp(payload["iat"]),
                expires_at=datetime.fromtimestamp(payload["exp"]),
                ip_address=payload.get("ip", "127.0.0.1"),
            )
            
            return session
            
        except pyjwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except pyjwt.InvalidTokenError as e:
            logger.warning(f"Token无效: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """
        撤销Token（加入黑名单）
        """
        try:
            payload = pyjwt.decode(token, self.secret, algorithms=[self.algorithm], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                self._blacklist[jti] = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
                logger.info(f"Token已撤销: jti={jti}")
                return True
        except Exception as e:
            logger.error(f"撤销Token失败: {e}")
        return False
    
    def check_permission(self, session: UserSession, required_permission: str) -> bool:
        """
        检查用户是否有指定权限
        
        Args:
            session: 用户会话
            required_permission: 所需权限（如 "trade:execute"）
            
        Returns:
            True=有权限
        """
        if session.is_expired:
            return False
        
        permissions = ROLE_PERMISSIONS.get(session.role, [])
        
        # ADMIN有全部权限
        if "*" in permissions:
            return True
        
        # 精确匹配
        if required_permission in permissions:
            return True
        
        # 通配符匹配
        perm_parts = required_permission.split(":")
        for p in permissions:
            p_parts = p.split(":")
            if len(p_parts) == 2 and p_parts[0] == perm_parts[0]:
                if p_parts[1] == "*" or p_parts[1] == perm_parts[1]:
                    return True
        
        return False
    
    def cleanup_blacklist(self) -> int:
        """
        清理过期黑名单条目
        """
        now = datetime.utcnow()
        to_remove = [jti for jti, exp in self._blacklist.items() if exp < now]
        for jti in to_remove:
            del self._blacklist[jti]
        if to_remove:
            logger.info(f"清理黑名单: {len(to_remove)} 条")
        return len(to_remove)


# ============================================================
# HMAC签名验证器
# ============================================================

class HMACSignatureValidator:
    """
    HMAC-SHA256 API签名验证
    
    修补项 P0-4：API接口签名防重放/篡改
    
    签名算法:
    signature = HMAC-SHA256(secret, timestamp + method + path + body_hash)
    
    请求头要求:
    X-Aurora-Timestamp: Unix时间戳
    X-Aurora-Signature: 签名值
    X-Aurora-Nonce: 随机数（可选，防重放）
    """
    
    def __init__(self, secret: str = HMAC_SECRET):
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self._used_nonces: Dict[str, float] = {}  # nonce防重放
        logger.info("HMAC签名验证器已初始化")
    
    def generate_signature(
        self,
        timestamp: int,
        method: str,
        path: str,
        body: str = "",
        nonce: Optional[str] = None,
    ) -> str:
        """
        生成HMAC签名
        
        Args:
            timestamp: Unix时间戳
            method: HTTP方法
            path: 请求路径
            body: 请求体
            nonce: 随机数
            
        Returns:
            十六进制签名字符串
        """
        # 构建待签名字符串
        body_hash = hashlib.sha256(body.encode()).hexdigest() if body else ""
        message_parts = [
            str(timestamp),
            method.upper(),
            path,
            body_hash,
        ]
        if nonce:
            message_parts.append(nonce)
        
        message = "|".join(message_parts)
        
        signature = hmac.new(
            self.secret,
            message.encode(),
            digestmod=getattr(hashlib, HMAC_ALGORITHM.split("sha")[-1])
        ).hexdigest()
        
        return signature
    
    def verify_request(
        self,
        timestamp: int,
        method: str,
        path: str,
        signature: str,
        body: str = "",
        nonce: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        验证API请求签名
        
        Returns:
            (是否通过, 错误信息)
        """
        # 1. 时间戳校验（防重放）
        now = int(time.time())
        if abs(now - timestamp) > SIGNATURE_TIMESTAMP_WINDOW:
            return False, f"时间戳已过期（窗口±{SIGNATURE_TIMESTAMP_WINDOW}秒）"
        
        # 2. Nonce校验（一次性使用）
        if nonce:
            if nonce in self._used_nonces:
                return False, "Nonce已被使用（可能为重放攻击）"
            self._used_nonces[nonce] = now
        
        # 3. 签名校验
        expected = self.generate_signature(timestamp, method, path, body, nonce)
        
        if not hmac.compare_digest(signature, expected):
            logger.warning(f"签名验证失败: {method} {path}")
            return False, "签名不匹配"
        
        return True, "OK"
    
    def cleanup_nonces(self) -> int:
        """
        清理过期nonce
        """
        now = time.time()
        to_remove = [
            n for n, ts in self._used_nonces.items()
            if now - ts > SIGNATURE_TIMESTAMP_WINDOW + 60
        ]
        for n in to_remove:
            del self._used_nonces[n]
        return len(to_remove)


# ============================================================
# IP限流器
# ============================================================

class RateLimiter:
    """
    滑动窗口 IP 限流
    
    修补项 P1-3：API限流中间件
    """
    
    def __init__(
        self,
        max_requests: int = RATE_LIMIT_PER_MINUTE,
        window_seconds: int = RATE_LIMIT_WINDOW,
        block_duration: int = 300,  # 超限后封禁5分钟
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.block_duration = block_duration
        self._entries: Dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        logger.info(f"RateLimiter已初始化: {max_requests}请求/{window_seconds}秒")
    
    def is_allowed(self, ip: str) -> Tuple[bool, str]:
        """
        检查IP是否允许访问
        
        Returns:
            (是否允许, 信息)
        """
        now = time.time()
        entry = self._entries[ip]
        
        # 检查是否在封禁期
        if entry.blocked_until > now:
            remaining_block = int(entry.blocked_until - now)
            return False, f"IP已被限流，剩余 {remaining_block} 秒"
        
        # 检查窗口是否过期
        if now - entry.window_start > self.window_seconds:
            entry.count = 0
            entry.window_start = now
        
        # 计数
        entry.count += 1
        
        if entry.count > self.max_requests:
            entry.blocked_until = now + self.block_duration
            logger.warning(f"IP {ip} 触发限流，封禁 {self.block_duration} 秒")
            return False, f"请求频率超限（{self.max_requests}次/{self.window_seconds}秒），已封禁"
        
        remaining = self.max_requests - entry.count
        return True, f"OK（剩余 {remaining} 次）"


# ============================================================
# Flask装饰器
# ============================================================

def _get_flask_components():
    """延迟导入Flask组件"""
    try:
        from flask import request, jsonify, g as flask_g
        return request, jsonify, flask_g
    except ImportError:
        return None, None, None


# 全局实例
_token_manager: Optional[TokenManager] = None
_hmac_validator: Optional[HMACSignatureValidator] = None
_rate_limiter: Optional[RateLimiter] = None


def get_token_manager() -> TokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


def get_hmac_validator() -> HMACSignatureValidator:
    global _hmac_validator
    if _hmac_validator is None:
        _hmac_validator = HMACSignatureValidator()
    return _hmac_validator


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def require_auth(permission: Optional[str] = None):
    """
    Flask装饰器：要求JWT认证 + 可选权限校验
    
    用法:
    @app.route('/api/trade/execute')
    @require_auth(permission="trade:execute")
    def execute_trade():
        ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request, jsonify, flask_g = _get_flask_components()
            if request is None:
                return func(*args, **kwargs)
            
            # 1. 获取Token
            auth_header = request.headers.get("Authorization", "")
            token = None
            
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            else:
                token = request.cookies.get("aurora_token") or request.args.get("token")
            
            if not token:
                return jsonify({
                    "status": "error",
                    "code": "AUTH_REQUIRED",
                    "message": "缺少认证Token，请登录后重试"
                }), 401
            
            # 2. 验证Token
            tm = get_token_manager()
            session = tm.verify_token(token)
            
            if session is None:
                return jsonify({
                    "status": "error",
                    "code": "TOKEN_INVALID",
                    "message": "Token无效或已过期，请重新登录"
                }), 401
            
            # 3. 权限校验
            if permission and not tm.check_permission(session, permission):
                return jsonify({
                    "status": "error",
                    "code": "PERMISSION_DENIED",
                    "message": f"权限不足，需要 {permission}"
                }), 403
            
            # 4. 注入用户信息
            flask_g.current_user = session
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_signature(required: bool = False):
    """
    Flask装饰器：验证API请求HMAC签名
    
    用法:
    @app.route('/api/trade/execute')
    @require_signature(required=True)
    def execute_trade():
        ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request, jsonify, _ = _get_flask_components()
            if request is None:
                return func(*args, **kwargs)
            
            timestamp_str = request.headers.get("X-Aurora-Timestamp", "")
            signature = request.headers.get("X-Aurora-Signature", "")
            nonce = request.headers.get("X-Aurora-Nonce")
            
            # 如果没有签名头和required=False，跳过
            if not timestamp_str and not signature:
                if required:
                    return jsonify({
                        "status": "error",
                        "code": "SIGNATURE_REQUIRED",
                        "message": "缺少API签名，请提供X-Aurora-Timestamp和X-Aurora-Signature"
                    }), 401
                return func(*args, **kwargs)
            
            try:
                timestamp = int(timestamp_str)
            except ValueError:
                return jsonify({
                    "status": "error",
                    "code": "INVALID_TIMESTAMP",
                    "message": "时间戳格式无效"
                }), 400
            
            validator = get_hmac_validator()
            body = request.get_data(as_text=True) or ""
            method = request.method
            path = request.path
            
            is_valid, error_msg = validator.verify_request(
                timestamp, method, path, signature, body, nonce
            )
            
            if not is_valid:
                return jsonify({
                    "status": "error",
                    "code": "SIGNATURE_INVALID",
                    "message": f"签名验证失败: {error_msg}"
                }), 401
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_rate_limit():
    """
    Flask装饰器：IP限流
    
    用法:
    @app.route('/api/public/endpoint')
    @require_rate_limit()
    def endpoint():
        ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request, jsonify, _ = _get_flask_components()
            if request is None:
                return func(*args, **kwargs)
            
            # 获取真实IP
            ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip and "," in ip:
                ip = ip.split(",")[0].strip()
            
            rl = get_rate_limiter()
            allowed, msg = rl.is_allowed(ip)
            
            if not allowed:
                return jsonify({
                    "status": "error",
                    "code": "RATE_LIMITED",
                    "message": msg,
                    "retry_after": int(time.time() + 60),
                }), 429
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def create_admin_token() -> Tuple[str, str]:
    """
    生成管理员初始Token
    
    Returns:
        (token, 显示信息)
    """
    tm = get_token_manager()
    token, session = tm.create_token(
        user_id="admin",
        username="admin",
        role=Role.ADMIN,
        expiration_hours=8760,  # 1年
    )
    return token, f"Admin Token已生成（1年有效）: {token[:20]}..."


# ============================================================
# 初始化
# ============================================================

if __name__ == "__main__":
    # 测试
    tm = get_token_manager()
    token, session = tm.create_token("test", "test_user", Role.TRADER)
    print(f"Token: {token}")
    
    verified = tm.verify_token(token)
    print(f"验证通过: {verified is not None}")
    print(f"角色: {verified.role if verified else 'N/A'}")
    
    has_perm = tm.check_permission(session, "trade:execute")
    print(f"交易权限: {has_perm}")
    
    has_admin = tm.check_permission(session, "*")
    print(f"管理员权限: {has_admin}")
    
    # HMAC测试
    hv = get_hmac_validator()
    ts = int(time.time())
    sig = hv.generate_signature(ts, "POST", "/api/test", '{"a":1}')
    print(f"HMAC签名: {sig}")
    
    ok, msg = hv.verify_request(ts, "POST", "/api/test", sig, '{"a":1}')
    print(f"签名验证: {ok} - {msg}")