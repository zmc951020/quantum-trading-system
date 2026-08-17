# -*- coding: utf-8 -*-
"""monitor_routes - API网关路由"""
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

    @api_gateway.route('/monitor/database-stats', methods=['GET'])
    @require_auth
    def monitor_database_stats():
        result = get_adapter().get_database_stats()
        return jsonify(result)


    # ============================================================

