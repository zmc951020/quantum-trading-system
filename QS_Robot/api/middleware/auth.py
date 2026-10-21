# -*- coding: utf-8 -*-
"""认证中间件"""
import logging
from functools import wraps

from api.response_formatter import APIResponse
from flask import g, jsonify, request

logger = logging.getLogger(__name__)


def require_auth(f):
    """请求鉴权装饰器 - 验证会话有效性 + 安全增强"""
    @wraps(f)
    def decorated(*args, **kwargs):
        session_id = request.cookies.get('session_id')
        if not session_id:
            session_id = request.headers.get('X-Session-Id')

        if not session_id:
            return jsonify(APIResponse.unauthorized("未登录，请先登录")), 401

        try:
            from ui.shared.session import get_session
            session = get_session(session_id)
            if not session:
                return jsonify(APIResponse.unauthorized("会话已过期，请重新登录")), 401
            g.user = session.get('user', {})
            g.username = session.get('username', 'unknown')
        except ImportError as e:
            logger.critical(f"认证服务导入失败，拒绝所有请求: {e}")
            return jsonify(APIResponse.error("认证服务不可用，系统维护中", code="AUTH_SERVICE_UNAVAILABLE")), 503

        return f(*args, **kwargs)
    return decorated


def get_session():
    """获取当前会话"""
    from ui.shared.session import get_session as _get_session
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-Id')
    return _get_session(session_id)
