# -*- coding: utf-8 -*-
"""broker_routes - API网关路由"""
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


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/broker/login', methods=['POST'])
    @require_auth
    def broker_login():
        """券商登录 — 5003本地实现（5002无/login端点）"""
        data = request.get_json(silent=True) or {}
        return jsonify(get_adapter().broker_login_local(data))


    @api_gateway.route('/broker/logout', methods=['POST'])
    def broker_logout():
        """券商登出 — 5003本地实现"""
        return jsonify(get_adapter().broker_logout_local())


    @api_gateway.route('/broker/order', methods=['POST'])
    @require_auth
    def broker_order():
        """券商下单 — 代理到5002 /api/stock/add"""
        data = request.get_json(silent=True) or {}
        return jsonify(get_adapter().broker_order_local(data))


    @api_gateway.route('/broker/positions', methods=['GET'])
    def broker_positions():
        """券商持仓 — 代理到5002 /api/positions"""
        return jsonify(get_adapter().get_broker_positions())


    # ============================================================

    @api_gateway.route('/broker/account', methods=['GET'])
    @require_auth
    @check_threat
    def broker_account():
        """获取账户信息（本地模拟券商）"""
        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        return jsonify(APIResponse.success(broker.get_account()))



    @api_gateway.route('/broker/submit_order', methods=['POST'])
    @require_auth
    @check_threat
    @require_csrf
    @sanitize_input
    @rate_limit(max_requests=10, window_seconds=60)
    def broker_submit_order():
        """提交订单（含风控检查+Vibe复核）"""
        data = request.get_json(silent=True) or {}
        validator = get_input_validator()

        symbol = validator.sanitize_stock_code(data.get('symbol', ''))
        side = data.get('side', 'buy')
        order_type = data.get('order_type', 'limit')
        price = validator.validate_number(data.get('price', 0), min_val=0.01)
        quantity = validator.validate_number(data.get('quantity', 100), min_val=100)
        vibe_verified = data.get('vibe_verified', False)

        if not symbol:
            return jsonify(APIResponse.error("无效的股票代码")), 400

        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        result = broker.submit_order_with_risk_check(
            symbol, side, order_type, price, int(quantity), vibe_verified
        )

        # 脱敏处理
        masker = get_data_masker()
        if result.get('order'):
            result['order'] = masker.mask_trade_data(result['order'])

        return jsonify(APIResponse.success(result))



    @api_gateway.route('/broker/batch_submit', methods=['POST'])
    @require_auth
    @check_threat
    @require_csrf
    @sanitize_input
    @rate_limit(max_requests=5, window_seconds=300)
    def broker_batch_submit():
        """批量提交订单（精选股票池一键下单）"""
        data = request.get_json(silent=True) or {}
        orders = data.get('orders', [])
        verify_all = data.get('verify_all', True)

        if not orders:
            return jsonify(APIResponse.error("订单列表为空")), 400

        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        result = broker.batch_submit(orders, verify_all)

        return jsonify(APIResponse.success(result))



    @api_gateway.route('/broker/orders', methods=['GET'])
    @require_auth
    @check_threat
    def broker_orders():
        """查询订单列表"""
        symbol = request.args.get('symbol', '')
        status = request.args.get('status', '')
        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        orders = broker.broker.get_orders(symbol=symbol or None, status=status or None)
        return jsonify(APIResponse.success({"orders": orders}))



    @api_gateway.route('/broker/cancel_order', methods=['POST'])
    @require_auth
    @check_threat
    @require_csrf
    def broker_cancel_order():
        """撤单（本地模拟券商）"""
        data = request.get_json(silent=True) or {}
        order_id = data.get('order_id', '')
        if not order_id:
            return jsonify(APIResponse.error("订单ID不能为空")), 400
        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        result = broker.broker.cancel_order(order_id)
        return jsonify(APIResponse.success(result))



    @api_gateway.route('/broker/transactions', methods=['GET'])
    @require_auth
    @check_threat
    def broker_transactions():
        """交易历史"""
        from core.broker_connector import get_broker_connector
        broker = get_broker_connector()
        txs = broker.get_transaction_history()
        masker = get_data_masker()
        txs = [masker.mask_trade_data(tx) for tx in txs]
        return jsonify(APIResponse.success({"transactions": txs}))


    # ============================================================

    @api_gateway.route('/broker/list', methods=['GET'])
    @require_auth
    def broker_list():
        """券商列表"""
        result = get_adapter().get_broker_list()
        return jsonify(result)


    @api_gateway.route('/broker/switch', methods=['POST'])
    @require_auth
    def broker_switch():
        """切换券商"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().switch_broker(data.get("broker_type", ""))
        return jsonify(result)


    @api_gateway.route('/broker/health', methods=['GET'])
    @require_auth
    def broker_health():
        """券商健康"""
        result = get_adapter().get_broker_health()
        return jsonify(result)


    @api_gateway.route('/broker/pool', methods=['GET'])
    @require_auth
    def broker_pool():
        """券商股票池"""
        result = get_adapter().get_broker_pool()
        return jsonify(result)


    @api_gateway.route('/broker/pool/add', methods=['POST'])
    @require_auth
    def broker_pool_add():
        """添加券商股票"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().add_broker_pool(data.get("symbol", ""), data.get("meta"))
        return jsonify(result)


    @api_gateway.route('/broker/pool/remove', methods=['POST'])
    @require_auth
    def broker_pool_remove():
        """移除券商股票"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().remove_broker_pool(data.get("symbol", ""))
        return jsonify(result)


    @api_gateway.route('/broker/pool/sync', methods=['GET'])
    @require_auth
    def broker_pool_sync():
        """同步券商股票池"""
        result = get_adapter().sync_broker_pool()
        return jsonify(result)


    @api_gateway.route('/broker/switch-history', methods=['GET'])
    @require_auth
    def broker_switch_history():
        """券商切换历史"""
        result = get_adapter().get_broker_switch_history()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/broker-pool', methods=['GET'])
    @require_auth
    def external_broker_pool():
        """券商池 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/broker-pool", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    # ============================================================

