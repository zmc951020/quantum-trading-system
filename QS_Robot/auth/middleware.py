"""认证中间件：请求拦截、Token校验、RBAC鉴权、防钓鱼"""
from functools import wraps
from flask import request, jsonify

from auth.jwt_manager import verify_token
from auth.rbac import has_permission


def _before_request():
    """请求前钩子：防钓鱼检查"""
    from auth.phishing_defense import phishing
    phishing.evaluate(request)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.cookies.get("auth_token", "")
        if not token:
            return jsonify({"success": False, "error": "未认证"}), 401
        payload = verify_token(token)
        if payload is None:
            return jsonify({"success": False, "error": "Token无效或已过期"}), 401
        request.user = payload
        return f(*args, **kwargs)
    return decorated


def require_permission(permission: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                return jsonify({"success": False, "error": "未认证"}), 401
            payload = verify_token(token)
            if payload is None:
                return jsonify({"success": False, "error": "Token无效"}), 401
            role = payload.get("role", "viewer")
            if not has_permission(role, permission):
                return jsonify({"success": False, "error": f"权限不足: {permission}"}), 403
            request.user = payload
            return f(*args, **kwargs)
        return decorated
    return decorator