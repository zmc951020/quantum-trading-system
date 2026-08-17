# -*- coding: utf-8 -*-
"""user_routes - API网关路由"""
from flask import request, jsonify
from api.response_formatter import APIResponse
from api.aurora_core_adapter import get_aurora_adapter, AURORA_BACKEND

from api.middleware.auth import require_auth
from api.middleware.csrf import require_csrf
from api.middleware.rate_limit import rate_limit
from api.middleware.sanitize import sanitize_input
from api.middleware.origin import check_origin
from api.middleware.threat import check_threat
from api.validators import get_input_validator, get_data_masker

import logging
import os
import time
logger = logging.getLogger(__name__)


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/users', methods=['GET'])
    @require_auth
    def users_list():
        result = get_adapter().get_users()
        return jsonify(APIResponse.success({"users": result}))


    @api_gateway.route('/users', methods=['POST'])
    @require_auth
    def users_create():
        data = request.get_json(silent=True) or {}
        result = get_adapter().create_user(data)
        return jsonify(result)


    @api_gateway.route('/users/<username>', methods=['PUT'])
    @require_auth
    def users_update(username):
        data = request.get_json(silent=True) or {}
        result = get_adapter().update_user(username, data)
        return jsonify(result)


    @api_gateway.route('/users/<username>', methods=['DELETE'])
    @require_auth
    def users_delete(username):
        result = get_adapter().delete_user(username)
        return jsonify(result)


    @api_gateway.route('/users/<username>/disable', methods=['POST'])
    @require_auth
    def users_disable(username):
        result = get_adapter().disable_user(username)
        return jsonify(result)


    @api_gateway.route('/users/<username>/enable', methods=['POST'])
    @require_auth
    def users_enable(username):
        result = get_adapter().enable_user(username)
        return jsonify(result)


    @api_gateway.route('/users/<username>/reset-password', methods=['POST'])
    @require_auth
    def users_reset_password(username):
        data = request.get_json(silent=True) or {}
        result = get_adapter().reset_user_password(username, data.get("password"))
        return jsonify(result)


    # ============================================================

