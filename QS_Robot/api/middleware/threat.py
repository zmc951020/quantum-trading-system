# -*- coding: utf-8 -*-
"""威胁检测中间件"""
from flask import request, jsonify, g
from functools import wraps
from api.response_formatter import APIResponse
import logging
logger = logging.getLogger(__name__)


def check_threat(f):
    """威胁检测装饰器 — 记录所有敏感请求来源"""
    @wraps(f)
    def decorated(*args, **kwargs):
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.info(f"[威胁检测] {request.method} {request.path} from {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated


def gateway_threat_check():
    """蓝图级威胁检测 — 对所有 /api/* 请求生效"""
    try:
        from core.security import get_threat_detector
        detector = get_threat_detector()
        client_ip = request.remote_addr
        reputation = detector.check_ip_reputation(client_ip)
        if not reputation.get('safe', True):
            logger.warning(f"Blocked malicious IP: {client_ip}")
            return jsonify(APIResponse.error("访问被拒绝", code="IP_BLOCKED")), 403
        if not detector.check_request_headers(dict(request.headers)):
            logger.warning(f"Suspicious headers from {client_ip}")
            return jsonify(APIResponse.error("请求头异常", code="SUSPICIOUS_HEADERS")), 400
    except Exception:
        pass
