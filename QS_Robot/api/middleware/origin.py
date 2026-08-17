# -*- coding: utf-8 -*-
"""来源检查中间件"""
from flask import request, jsonify
from functools import wraps
from api.response_formatter import APIResponse
import logging
logger = logging.getLogger(__name__)


def check_origin(f):
    """检查请求来源 - 开发环境仅允许本地"""
    @wraps(f)
    def decorated(*args, **kwargs):
        origin = request.headers.get('Origin', '')
        if origin:
            from urllib.parse import urlparse
            hostname = urlparse(origin).hostname or ''
            allowed = ['localhost', '127.0.0.1', '::1']
            if not any(a in hostname for a in allowed):
                logger.warning(f"Blocked unauthorized origin: {origin}")
                return jsonify(APIResponse.error("未授权的请求来源", code="ORIGIN_BLOCKED")), 403
        return f(*args, **kwargs)
    return decorated
