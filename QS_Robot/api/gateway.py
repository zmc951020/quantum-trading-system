# -*- coding: utf-8 -*-
"""
API 网关 — 直接导入模式（豆包方案A）
=====================================
统一API网关层，通过直接导入Aurora模块替代HTTP代理

功能:
1. 统一鉴权管理
2. 请求路由分发
3. Aurora核心直接调用（同进程）
4. 本地API直通
5. 请求限流

模块拆分:
- 中间件: api/middleware/ (auth, csrf, rate_limit, sanitize, origin, threat)
- 验证器: api/validators/ (input_validator, data_masker)
- 路由:   api/routes/ (19个领域模块)
"""

import logging
import os
import time
from functools import wraps
from typing import Optional

from core.security import (
    get_csrf_manager,
    get_data_masker,
    get_input_validator,
    get_rate_limiter,
    get_threat_detector,
)
from core.system_health_checker import get_health_checker
from flask import Blueprint, g, jsonify, request

from .aurora_core_adapter import AURORA_BACKEND, AuroraCoreAdapter, get_aurora_adapter
from .response_formatter import APIResponse

logger = logging.getLogger(__name__)

# 创建API网关蓝图
api_gateway = Blueprint('api_gateway', __name__, url_prefix='/api')

# 全局适配器实例
_adapter: Optional[AuroraCoreAdapter] = None


@api_gateway.before_request
def gateway_threat_check():
    """蓝图级威胁检测 — 对所有 /api/* 请求生效"""
    try:
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


def get_adapter() -> AuroraCoreAdapter:
    """获取Aurora核心适配器（直接导入模式）"""
    global _adapter
    if _adapter is None:
        _adapter = get_aurora_adapter()
    return _adapter


# ============================================================
# 注册所有子路由（从拆分后的模块加载）
# 中间件: api/middleware/ | 验证器: api/validators/ | 路由: api/routes/
# ============================================================
from api.routes import register_all_routes

register_all_routes(api_gateway)