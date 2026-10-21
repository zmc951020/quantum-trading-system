# -*- coding: utf-8 -*-
"""security_routes - API网关路由"""
import logging
import os
import time

from api.aurora_core_adapter import AURORA_BACKEND, get_aurora_adapter
from api.middleware.auth import require_auth
from api.middleware.csrf import require_csrf
from api.middleware.origin import check_origin
from api.middleware.rate_limit import rate_limit
from api.middleware.sanitize import sanitize_input
from api.middleware.threat import check_threat
from api.response_formatter import APIResponse
from api.validators import get_data_masker, get_input_validator
from flask import jsonify, request

logger = logging.getLogger(__name__)

from core.security import get_csrf_manager


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/trade/security/config', methods=['GET'])
    @require_auth
    def trade_security_config():
        result = get_adapter().get_trade_security_config()
        return jsonify(result)


    @api_gateway.route('/trade/security/add-ip', methods=['POST'])
    @require_auth
    def trade_add_ip():
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "")
        result = get_adapter().add_ip_whitelist(ip)
        return jsonify(result)


    @api_gateway.route('/trade/security/add-api-key', methods=['POST'])
    @require_auth
    def trade_add_api_key():
        data = request.get_json(silent=True) or {}
        result = get_adapter().add_api_key(data)
        return jsonify(result)


    @api_gateway.route('/security/config', methods=['GET'])
    @require_auth
    def security_config():
        result = get_adapter().get_security_config()
        return jsonify(result)


    @api_gateway.route('/security/whitelist/add', methods=['POST'])
    @require_auth
    def security_whitelist_add():
        data = request.get_json(silent=True) or {}
        result = get_adapter().add_whitelist(data)
        return jsonify(result)


    @api_gateway.route('/security/whitelist/remove', methods=['POST'])
    @require_auth
    def security_whitelist_remove():
        data = request.get_json(silent=True) or {}
        result = get_adapter().remove_whitelist(data)
        return jsonify(result)


    @api_gateway.route('/security/whitelist/list', methods=['GET'])
    @require_auth
    def security_whitelist_list():
        """获取IP白名单列表"""
        result = get_adapter().get_ip_whitelist()
        return jsonify(result)


    @api_gateway.route('/security/audit-logs', methods=['GET'])
    @require_auth
    def security_audit_logs():
        """获取安全审计日志"""
        limit = request.args.get('limit', 50, type=int)
        result = get_adapter().get_audit_logs(limit)
        return jsonify(result)


    @api_gateway.route('/security/off-hours', methods=['POST'])
    @require_auth
    def security_off_hours():
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled", False)
        result = get_adapter().set_off_hours(enabled)
        return jsonify(result)


    @api_gateway.route('/security/location-check', methods=['POST'])
    @require_auth
    def security_location_check():
        data = request.get_json(silent=True) or {}
        result = get_adapter().check_location(data)
        return jsonify(result)


    @api_gateway.route('/security/all-check', methods=['POST'])
    @require_auth
    def security_all_check():
        result = get_adapter().check_all_security()
        return jsonify(result)


    @api_gateway.route('/security/config-update', methods=['POST'])
    @require_auth
    def security_config_update():
        data = request.get_json(silent=True) or {}
        result = get_adapter().update_security_config(data)
        return jsonify(result)



    @api_gateway.route('/security/csrf-token', methods=['GET'])
    @require_auth
    def get_csrf_token():
        """获取CSRF令牌"""
        csrf_mgr = get_csrf_manager()
        session_id = request.cookies.get('session_id', '')
        token = csrf_mgr.generate_token(session_id)
        return jsonify(APIResponse.success({"csrf_token": token}))



