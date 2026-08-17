# -*- coding: utf-8 -*-
"""CSRF防护中间件"""
from flask import request, jsonify
from functools import wraps
from api.response_formatter import APIResponse


def require_csrf(f):
    """CSRF防护装饰器 — 验证X-CSRF-Token头"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = request.headers.get('X-CSRF-Token', '')
            if not token or len(token) < 8:
                return jsonify(APIResponse.error("CSRF令牌无效")), 403
        return f(*args, **kwargs)
    return decorated
