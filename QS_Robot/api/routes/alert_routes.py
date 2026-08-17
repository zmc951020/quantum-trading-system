# -*- coding: utf-8 -*-
"""alert_routes - API网关路由"""
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

    @api_gateway.route('/alerts', methods=['GET'])
    @require_auth
    def alerts_list():
        result = get_adapter().get_alerts()
        return jsonify(APIResponse.success({"alerts": result}))


    @api_gateway.route('/alerts/read', methods=['POST'])
    @require_auth
    def alerts_read():
        data = request.get_json(silent=True) or {}
        alert_id = data.get("id", "")
        result = get_adapter().mark_alert_read(alert_id)
        return jsonify(result)


    @api_gateway.route('/alerts/send', methods=['POST'])
    @require_auth
    def alerts_send():
        data = request.get_json(silent=True) or {}
        result = get_adapter().send_alert(data)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/vibe/anomaly/alerts', methods=['GET'])
    @require_auth
    def vibe_anomaly_alerts():
        """GET /api/vibe/anomaly/alerts?hours=24&severity=high
        异常数据预警：获取告警列表
        """
        try:
            from core.infrastructure import get_anomaly_detector
            ad = get_anomaly_detector()
            hours = request.args.get("hours", 24, type=int)
            severity = request.args.get("severity", None)
            alerts = ad.get_recent_alerts(hours, severity)
            summary = ad.get_alert_summary()
            return jsonify({
                "success": True,
                "data": {"alerts": alerts, "summary": summary, "count": len(alerts)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



