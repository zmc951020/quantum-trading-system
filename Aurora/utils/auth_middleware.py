"""
JWT认证中间件 + Token刷新 + 装饰器
=======================================
修补项 P0-2：JWT认证 ✅

功能：
- JWT HS256 签名/验证
- Access Token + Refresh Token 双令牌机制
- @require_auth 装饰器
- Token 自动刷新
- 用户会话管理
- 黑名单/登出支持
"""

import os
import time
import hashlib
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime, timedelta

import jwt
from flask import request, g, jsonify

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
JWT_SECRET = os.environ.get("JWT_SECRET", "aurora-quantum-jwt-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRE", "60"))       # 1小时
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRE", "7"))         # 7天

# 内存黑名单（生产环境应使用Redis）
_token_blacklist: set = set()


# ============================================================
# Token 核心函数
# ============================================================
def create_access_token(user_id: str, role: str = "user",
                        extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    创建 Access Token
    
    Args:
        user_id: 用户唯一标识
        role: 角色（admin/manager/analyst/user）
        extra_claims: 额外声明
    
    Returns:
        JWT token 字符串
    """
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
        "jti": _generate_jti(user_id),
    }
    if extra_claims:
        payload.update(extra_claims)
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def create_refresh_token(user_id: str) -> str:
    """
    创建 Refresh Token（长期令牌，用于刷新Access Token）
    """
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "type": "refresh",
        "jti": _generate_jti(user_id),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def create_token_pair(user_id: str, role: str = "user",
                      extra_claims: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    同时创建 Access Token + Refresh Token
    
    Returns:
        {"access_token": "...", "refresh_token": "...", "token_type": "Bearer"}
    """
    return {
        "access_token": create_access_token(user_id, role, extra_claims),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证JWT Token
    
    Args:
        token: JWT token 字符串
    
    Returns:
        解码后的payload，失败返回None
    """
    try:
        # 去除 "Bearer " 前缀
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # 检查黑名单
        jti = payload.get("jti")
        if jti and jti in _token_blacklist:
            logger.warning(f"Token已被吊销: jti={jti}")
            return None
        
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"无效Token: {e}")
        return None


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, str]]:
    """
    使用 Refresh Token 换发新的 Access Token
    """
    payload = verify_token(refresh_token)
    if not payload:
        return None
    
    if payload.get("type") != "refresh":
        logger.warning("尝试使用非Refresh Token刷新")
        return None
    
    user_id = payload["sub"]
    role = payload.get("role", "user")
    
    return {
        "access_token": create_access_token(user_id, role),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def revoke_token(token: str) -> bool:
    """
    吊销Token（加入黑名单）
    
    Args:
        token: JWT token 字符串
    
    Returns:
        是否成功吊销
    """
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                            options={"verify_exp": False})  # 即使过期也加入黑名单
        jti = payload.get("jti")
        if jti:
            _token_blacklist.add(jti)
            logger.info(f"Token已吊销: jti={jti}")
            return True
        return False
    except jwt.InvalidTokenError:
        logger.warning("吊销失败：无效Token")
        return False


# ============================================================
# Flask中间件
# ============================================================
def init_auth_middleware(app, excluded_paths: Optional[list] = None):
    """
    为Flask应用注册JWT认证中间件
    
    Args:
        app: Flask应用实例
        excluded_paths: 不需要认证的路径列表（如登录/注册/健康检查）
    
    用法:
    from utils.auth_middleware import init_auth_middleware
    init_auth_middleware(app, excluded_paths=["/api/auth/login", "/api/health"])
    """
    if excluded_paths is None:
        excluded_paths = ["/api/auth/login", "/api/auth/register", "/api/health", "/api/status"]
    
    @app.before_request
    def authenticate():
        """请求前：验证JWT"""
        path = request.path
        
        # 检查排除路径
        for excluded in excluded_paths:
            if path.startswith(excluded):
                return None  # 跳过认证
        
        # 提取Token
        token = _extract_token(request)
        if not token:
            g.current_user = None
            return None  # 不强制拦截，由@require_auth装饰器处理
        
        # 验证Token
        payload = verify_token(token)
        if payload:
            g.current_user = {
                "user_id": payload["sub"],
                "role": payload.get("role", "user"),
                "jti": payload.get("jti"),
                "exp": payload.get("exp"),
            }
        else:
            g.current_user = None
    
    logger.info(f"JWT认证中间件已注册，排除路径: {excluded_paths}")


def _extract_token(req) -> Optional[str]:
    """从请求中提取JWT Token（优先级：Header > Cookie > Query）"""
    # 1. Authorization Header
    auth_header = req.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header
    
    # 2. Cookie
    token = req.cookies.get("access_token")
    if token:
        return f"Bearer {token}"
    
    # 3. Query参数
    token = req.args.get("token")
    if token:
        return f"Bearer {token}"
    
    return None


# ============================================================
# 装饰器
# ============================================================
def require_auth(func: Callable) -> Callable:
    """
    要求JWT认证的装饰器
    
    用法:
    @app.route("/api/protected")
    @require_auth
    def protected():
        return jsonify({"user": g.current_user})
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = getattr(g, 'current_user', None)
        if not user:
            return jsonify({
                "error": "unauthorized",
                "message": "需要有效的JWT令牌",
                "code": 401,
            }), 401
        return func(*args, **kwargs)
    return wrapper


def require_role(*allowed_roles: str) -> Callable:
    """
    要求特定角色的装饰器
    
    用法:
    @app.route("/api/admin")
    @require_auth
    @require_role("admin")
    def admin_only():
        return jsonify({"message": "Welcome admin"})
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = getattr(g, 'current_user', None)
            if not user:
                return jsonify({
                    "error": "unauthorized",
                    "message": "需要有效的JWT令牌",
                    "code": 401,
                }), 401
            
            if user.get("role") not in allowed_roles:
                return jsonify({
                    "error": "forbidden",
                    "message": f"需要角色: {', '.join(allowed_roles)}",
                    "code": 403,
                }), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# Auth API 路由
# ============================================================
def register_auth_routes(app, user_manager=None):
    """
    注册认证相关API路由
    
    路由:
    - POST /api/auth/login     : 登录
    - POST /api/auth/refresh   : 刷新Token
    - POST /api/auth/logout    : 登出
    - GET  /api/auth/me        : 获取当前用户信息
    """
    
    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        """用户登录"""
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        
        if not username or not password:
            return jsonify({
                "error": "bad_request",
                "message": "用户名和密码不能为空",
            }), 400
        
        # 验证用户（需要user_manager注入）
        if user_manager:
            user = user_manager.authenticate(username, password)
            if not user:
                return jsonify({
                    "error": "unauthorized",
                    "message": "用户名或密码错误",
                }), 401
            role = user.get("role", "user")
            user_id = user.get("id", username)
        else:
            # 开发模式：简单验证
            if password != "aurora2024":
                return jsonify({
                    "error": "unauthorized",
                    "message": "用户名或密码错误",
                }), 401
            role = "admin" if username == "admin" else "user"
            user_id = username
        
        # 生成Token对
        tokens = create_token_pair(user_id, role)
        
        logger.info(f"用户登录成功: {user_id} (角色: {role})")
        
        return jsonify({
            "status": "ok",
            "message": "登录成功",
            "data": tokens,
        })
    
    @app.route("/api/auth/refresh", methods=["POST"])
    def auth_refresh():
        """刷新Access Token"""
        data = request.get_json(silent=True) or {}
        refresh_token = data.get("refresh_token", "")
        
        if not refresh_token:
            return jsonify({
                "error": "bad_request",
                "message": "缺少refresh_token",
            }), 400
        
        result = refresh_access_token(refresh_token)
        if not result:
            return jsonify({
                "error": "unauthorized",
                "message": "Refresh Token无效或已过期，请重新登录",
            }), 401
        
        return jsonify({
            "status": "ok",
            "message": "Token刷新成功",
            "data": result,
        })
    
    @app.route("/api/auth/logout", methods=["POST"])
    @require_auth
    def auth_logout():
        """登出（吊销当前Token）"""
        token = _extract_token(request)
        if token:
            revoke_token(token)
        
        # 同时吊销Cookie中的Token
        refresh_token = request.get_json(silent=True) or {}
        rt = refresh_token.get("refresh_token", "")
        if rt:
            revoke_token(rt)
        
        g.current_user = None
        
        return jsonify({
            "status": "ok",
            "message": "已登出",
        })
    
    @app.route("/api/auth/me", methods=["GET"])
    @require_auth
    def auth_me():
        """获取当前用户信息"""
        return jsonify({
            "status": "ok",
            "data": {
                "user_id": g.current_user["user_id"],
                "role": g.current_user["role"],
                "session_expires": g.current_user.get("exp"),
            }
        })
    
    logger.info("Auth API路由已注册")


# ============================================================
# 辅助函数
# ============================================================
def _generate_jti(user_id: str) -> str:
    """生成JWT ID"""
    raw = f"{user_id}:{time.time()}:{os.urandom(8).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_password(password: str) -> str:
    """密码哈希（SHA256 + Salt）"""
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored: str) -> bool:
    """验证密码"""
    try:
        salt, hashed = stored.split(":", 1)
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest() == hashed
    except (ValueError, AttributeError):
        return False