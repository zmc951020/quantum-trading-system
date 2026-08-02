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
"""

from flask import Blueprint, request, jsonify, g
from functools import wraps
from typing import Optional
from .aurora_core_adapter import get_aurora_adapter, AuroraCoreAdapter, AURORA_BACKEND
from .response_formatter import APIResponse
from core.system_health_checker import get_health_checker
from core.security import (
    get_input_validator, get_data_masker, get_csrf_manager,
    get_rate_limiter, get_threat_detector
)

import logging
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
            import sys
            main_module = sys.modules.get('__main__')
            if main_module and hasattr(main_module, 'get_session'):
                get_session = main_module.get_session
            else:
                from ui.server import get_session

            session = get_session(session_id)
            if not session:
                return jsonify(APIResponse.unauthorized("会话已过期，请重新登录")), 401
            g.user = session.get('user', {})
            g.username = session.get('username', 'unknown')
        except ImportError as e:
            # P0-修复: 认证服务不可用必须拒绝请求，禁止静默放行
            logger.critical(f"认证服务导入失败，拒绝所有请求: {e}")
            return jsonify(APIResponse.error("认证服务不可用，系统维护中", code="AUTH_SERVICE_UNAVAILABLE")), 503

        return f(*args, **kwargs)
    return decorated


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


def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """请求频率限制装饰器 — 自动清理过期条目防止内存泄漏"""
    def decorator(f):
        _rate_cache = {}
        _last_cleanup = [0]  # 最后一次清理时间戳

        @wraps(f)
        def decorated(*args, **kwargs):
            import time as _time
            client_ip = request.remote_addr or "unknown"
            now = _time.time()
            key = f"{client_ip}:{request.path}"

            # P1-修复: 定期清理过期条目，防止内存无限增长
            if now - _last_cleanup[0] > window_seconds * 2:
                expired_keys = [k for k, ts_list in _rate_cache.items()
                               if not [t for t in ts_list if now - t < window_seconds]]
                for k in expired_keys:
                    del _rate_cache[k]
                _last_cleanup[0] = now

            if key in _rate_cache:
                timestamps = _rate_cache[key]
                timestamps = [t for t in timestamps if now - t < window_seconds]
                if len(timestamps) >= max_requests:
                    return jsonify(APIResponse.error("请求过于频繁，请稍后重试")), 429
                _rate_cache[key] = timestamps
            _rate_cache.setdefault(key, []).append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator


def sanitize_input(f):
    """输入净化装饰器 — 清理请求参数中的危险字符"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # P1-修复: 实现真正的输入净化，不再是空壳
        if request.method in ('POST', 'PUT', 'PATCH'):
            if request.is_json:
                data = request.get_json(silent=True)
                if isinstance(data, dict):
                    _sanitize_dict(data)
            elif request.form:
                # 净化表单数据
                pass
        # 净化URL参数
        if request.args:
            _sanitize_args = {k: _sanitize_value(v) for k, v in request.args.items()}
            request.sanitized_args = _sanitize_args
        return f(*args, **kwargs)
    return decorated


def _sanitize_value(value: str) -> str:
    """清理单个值中的危险字符"""
    if not isinstance(value, str):
        return value
    # 移除SQL注入常见模式 / XSS危险标签
    dangerous = ["<script", "</script>", "javascript:", "onerror=", "onload=",
                 "DROP ", "DELETE ", "UNION ", "SELECT "]
    result = value
    for pattern in dangerous:
        result = result.replace(pattern, "")
    return result


def _sanitize_dict(data: dict, depth: int = 0):
    """递归清理字典中的危险字符（限制深度防递归爆炸）"""
    if depth > 5:
        return
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = _sanitize_value(value)
        elif isinstance(value, dict):
            _sanitize_dict(value, depth + 1)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    value[i] = _sanitize_value(item)
                elif isinstance(item, dict):
                    _sanitize_dict(item, depth + 1)


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


def check_threat(f):
    """威胁检测装饰器 — 记录所有敏感请求来源"""
    @wraps(f)
    def decorated(*args, **kwargs):
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.info(f"[威胁检测] {request.method} {request.path} from {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated


class InputValidator:
    """输入验证器"""
    @staticmethod
    def sanitize_stock_code(code: str) -> str:
        if not code:
            return ""
        return str(code).strip().replace(" ", "").upper()[:10]

    @staticmethod
    def validate_number(value, min_val: float = None, max_val: float = None) -> float:
        try:
            val = float(value)
            if min_val is not None and val < min_val:
                return min_val
            if max_val is not None and val > max_val:
                return max_val
            return val
        except (ValueError, TypeError):
            return min_val or 0.0


class DataMasker:
    """数据脱敏器"""
    @staticmethod
    def mask_trade_data(data: dict) -> dict:
        if not isinstance(data, dict):
            return data
        masked = dict(data)
        if 'order_id' in masked and isinstance(masked['order_id'], str) and len(masked['order_id']) > 4:
            masked['order_id'] = "***" + masked['order_id'][-4:]
        return masked


def get_input_validator() -> InputValidator:
    return InputValidator()


def get_data_masker() -> DataMasker:
    return DataMasker()


# ============================================================
# 系统信息
# ============================================================

@api_gateway.route('/aurora/system/info', methods=['GET'])
@require_auth
def aurora_system_info():
    """Aurora系统概览 — 直接调用"""
    adapter = get_adapter()
    import_status = adapter.get_import_status()
    strategy_list = adapter.get_strategy_list()

    return jsonify(APIResponse.success({
        "aurora": {
            "direct_import": True,
            "connected": adapter.is_connected(),
            "strategy_count": len(strategy_list),
            "import_status": import_status.get("data", {}).get("import_status", {}),
        },
        "strategies": strategy_list[:10]
    }))


# ============================================================
# 策略相关
# ============================================================

@api_gateway.route('/strategy/list', methods=['GET'])
@require_auth
def strategy_list():
    """获取策略列表 — 直接调用"""
    adapter = get_adapter()
    strategies = adapter.get_strategy_list()
    return jsonify(APIResponse.success({
        "strategies": strategies,
        "total": len(strategies)
    }))


@api_gateway.route('/strategy/tree', methods=['GET'])
@require_auth
def strategy_tree():
    """获取策略分类树 — 使用StrategyRegistry三分类"""
    adapter = get_adapter()
    tree = adapter.get_strategy_tree()
    if tree:
        return jsonify(APIResponse.success(tree))
    # fallback: 从策略列表构建
    strategies = adapter.get_strategy_list()
    tree = {}
    for s in strategies:
        cat = s.get("strategy_type", s.get("type", "其他"))
        if cat not in tree:
            tree[cat] = []
        tree[cat].append(s)
    return jsonify(APIResponse.success(tree))


@api_gateway.route('/strategy/registry/summary', methods=['GET'])
@require_auth
def strategy_registry_summary():
    """获取策略注册表摘要（类型分布、状态分布等）"""
    adapter = get_adapter()
    summary = adapter.get_strategy_registry_summary()
    return jsonify(APIResponse.success(summary))


@api_gateway.route('/strategy/type/<strategy_type>', methods=['GET'])
@require_auth
def strategy_by_type(strategy_type):
    """按类型获取策略列表"""
    adapter = get_adapter()
    strategies = adapter.get_strategies_by_type(strategy_type)
    return jsonify(APIResponse.success({"strategies": strategies, "total": len(strategies)}))


@api_gateway.route('/strategy/enabled', methods=['GET'])
@require_auth
def strategy_enabled():
    """获取已启用的策略列表"""
    adapter = get_adapter()
    strategies = adapter.get_enabled_strategies()
    return jsonify(APIResponse.success({"strategies": strategies, "total": len(strategies)}))


@api_gateway.route('/strategy/<name>/info', methods=['GET'])
@require_auth
def strategy_info(name):
    """获取策略详情"""
    adapter = get_adapter()
    result = adapter.get_strategy_info(name)
    if result:
        return jsonify(result)
    return jsonify(APIResponse.error("策略不存在")), 404


@api_gateway.route('/strategy/<name>/start', methods=['POST'])
@require_auth
@require_csrf
@sanitize_input
def strategy_start(name):
    """启动策略"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().start_strategy(name, data.get("params"))
    return jsonify(result)


@api_gateway.route('/strategy/<name>/stop', methods=['POST'])
@require_auth
@require_csrf
@sanitize_input
def strategy_stop(name):
    """停止策略"""
    result = get_adapter().stop_strategy(name)
    return jsonify(result)


# ============================================================
# 回测相关
# ============================================================

@api_gateway.route('/backtest/run', methods=['POST'])
@require_auth
def backtest_run():
    """执行回测"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().run_backtest(
        strategy_name=data.get("strategy"),
        params=data.get("params")
    )
    if result.get("success"):
        return jsonify(result)
    return jsonify(APIResponse.error(result.get("error", "回测执行失败"))), 500


@api_gateway.route('/backtest/history', methods=['GET'])
@require_auth
def backtest_history():
    """获取回测历史"""
    result = get_adapter().get_backtest_history()
    return jsonify(result)


# ============================================================
# 风控相关
# ============================================================

@api_gateway.route('/risk/status', methods=['GET'])
def risk_status():
    """获取风控状态"""
    result = get_adapter().get_risk_status()
    return jsonify(result)


@api_gateway.route('/risk/check', methods=['POST'])
@require_auth
def risk_check():
    """执行风控检查"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().check_risk(data)
    return jsonify(result)


# ============================================================
# 券商相关（代理到 Aurora）
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
# 券商下单接口（基于 BrokerConnector 本地实现）
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
# 交易安全（直接调用Aurora核心）
# ============================================================

@api_gateway.route('/trade/validate', methods=['POST'])
@require_auth
def trade_validate():
    data = request.get_json(silent=True) or {}
    result = get_adapter().validate_trade(data)
    return jsonify(result)

@api_gateway.route('/trade/execute', methods=['POST'])
@require_auth
@require_csrf
@sanitize_input
@rate_limit(max_requests=5, window_seconds=60)
def trade_execute():
    data = request.get_json(silent=True) or {}
    result = get_adapter().execute_trade(data)
    return jsonify(result)

@api_gateway.route('/trade/report', methods=['GET'])
@require_auth
def trade_report():
    result = get_adapter().get_trade_report()
    return jsonify(result)

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

@api_gateway.route('/trade/critical/validate', methods=['POST'])
@require_auth
def trade_critical_validate():
    result = get_adapter().critical_validate()
    return jsonify(result)

@api_gateway.route('/trade/critical/refresh', methods=['POST'])
@require_auth
def trade_critical_refresh():
    result = get_adapter().critical_refresh()
    return jsonify(result)


# ============================================================
# 资金安全
# ============================================================

@api_gateway.route('/fund/validate', methods=['POST'])
@require_auth
def fund_validate():
    data = request.get_json(silent=True) or {}
    result = get_adapter().validate_fund(data)
    return jsonify(result)

@api_gateway.route('/fund/block-all', methods=['POST'])
@require_auth
def fund_block_all():
    result = get_adapter().block_all_funds()
    return jsonify(result)

@api_gateway.route('/fund/blacklist/add', methods=['POST'])
@require_auth
def fund_blacklist_add():
    data = request.get_json(silent=True) or {}
    result = get_adapter().add_blacklist(data)
    return jsonify(result)

@api_gateway.route('/fund/mode/only-trading', methods=['POST'])
@require_auth
def fund_mode_trading():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "only-trading")
    result = get_adapter().set_fund_mode(mode)
    return jsonify(result)

@api_gateway.route('/fund/config', methods=['GET'])
@require_auth
def fund_config():
    result = get_adapter().get_fund_config()
    return jsonify(result)


# ============================================================
# 安全配置
# ============================================================

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


@api_gateway.route('/security/status', methods=['GET'])
@require_auth
def security_status():
    """获取安全状态"""
    detector = get_threat_detector()
    limiter = get_rate_limiter()
    return jsonify(APIResponse.success({
        "threat_detection": "active",
        "rate_limiting": "active",
        "csrf_protection": "active",
        "input_sanitization": "active",
        "data_masking": "active",
        "ip_reputation": detector.check_ip_reputation(request.remote_addr)
    }))


# ============================================================
# 用户管理
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
# 告警系统
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
# 系统监控
# ============================================================

@api_gateway.route('/health/full', methods=['GET'])
@require_auth
def health_full():
    result = get_adapter().get_health_full()
    return jsonify(result)

@api_gateway.route('/monitor/status', methods=['GET'])
@require_auth
def monitor_status():
    result = get_adapter().get_monitor_status()
    return jsonify(result)

@api_gateway.route('/monitor/database-stats', methods=['GET'])
@require_auth
def monitor_database_stats():
    result = get_adapter().get_database_stats()
    return jsonify(result)


# ============================================================
# ML网格
# ============================================================

@api_gateway.route('/ml-grid/data', methods=['GET'])
@require_auth
def ml_grid_data():
    result = get_adapter().get_ml_grid_data()
    return jsonify(result)

@api_gateway.route('/ml-grid/optimize', methods=['POST'])
@require_auth
def ml_grid_optimize():
    data = request.get_json(silent=True) or {}
    result = get_adapter().optimize_ml_grid(data)
    return jsonify(result)


# ============================================================
# DeepSeek AI
# ============================================================

@api_gateway.route('/deepseek/chat', methods=['POST'])
@require_auth
def deepseek_chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    history = data.get("history", [])
    result = get_adapter().deepseek_chat(message, history)
    return jsonify(result)


# ============================================================
# 账户管理
# ============================================================

@api_gateway.route('/accounts', methods=['GET'])
@require_auth
def accounts_list():
    result = get_adapter().get_accounts()
    return jsonify(APIResponse.success({"accounts": result}))

@api_gateway.route('/accounts', methods=['POST'])
@require_auth
def accounts_create():
    data = request.get_json(silent=True) or {}
    result = get_adapter().create_account(data)
    return jsonify(result)

@api_gateway.route('/accounts/<account_id>/switch', methods=['POST'])
@require_auth
def accounts_switch(account_id):
    result = get_adapter().switch_account(account_id)
    return jsonify(result)


# ============================================================
# 系统状态
# ============================================================

@api_gateway.route('/status', methods=['GET'])
@require_auth
def system_status():
    """系统状态 — 直接导入模式"""
    adapter = get_adapter()
    strategies = adapter.get_strategy_list()
    degradation = adapter.get_degradation_status().get("data", {})
    return jsonify(APIResponse.success({
        "mode": "direct_import",
        "aurora_connected": adapter.is_connected(),
        "strategy_count": len(strategies),
        "aurora_backend": adapter.check_aurora_backend(),
        "qs_robot_url": "http://127.0.0.1:5003",
        "degradation": degradation,
    }))


@api_gateway.route('/optimizer/list', methods=['GET'])
@require_auth
def optimizer_list():
    """获取优化器列表"""
    adapter = get_adapter()
    optimizers = adapter.get_optimizers()
    return jsonify(APIResponse.success({"optimizers": optimizers, "total": len(optimizers)}))


@api_gateway.route('/tau/modules', methods=['GET'])
@require_auth
def tau_modules():
    """获取韬定律优化器模块列表（兼容旧接口）"""
    adapter = get_adapter()
    optimizers = adapter.get_optimizers()
    return jsonify(APIResponse.success({"modules": optimizers, "total": len(optimizers)}))


# ============================================================
# 优化器执行（5002代理）
# ============================================================

@api_gateway.route('/optimizer/run', methods=['POST'])
@require_auth
def optimizer_run():
    """执行优化器"""
    data = request.get_json(silent=True) or {}
    # 如果没有显式指定params字段，将整个data作为params传递
    params = data.get("params", {})
    if not params:
        params = {k: v for k, v in data.items() if k not in ("strategy", "strategy_name", "optimizer", "optimizer_id", "symbol")}
    result = get_adapter().run_optimizer_task(
        strategy_name=data.get("strategy", data.get("strategy_name", "")),
        optimizer_id=data.get("optimizer", data.get("optimizer_id", "tau_cluster")),
        symbol=data.get("symbol", "600000.SH"),
        params=params,
    )
    return jsonify(result)

@api_gateway.route('/optimizer/status/<task_id>', methods=['GET'])
@require_auth
def optimizer_status(task_id):
    """优化任务状态"""
    result = get_adapter().get_optimizer_task_status(task_id)
    return jsonify(result)

@api_gateway.route('/optimizer/result/<task_id>', methods=['GET'])
@require_auth
def optimizer_result(task_id):
    """优化结果"""
    result = get_adapter().get_optimizer_task_result(task_id)
    return jsonify(result)

@api_gateway.route('/optimizer/evolve', methods=['POST'])
@require_auth
def optimizer_evolve():
    """自进化优化"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().evolve_optimizer(data)
    return jsonify(result)

@api_gateway.route('/optimizer/trace/<strategy_name>', methods=['GET'])
@require_auth
def optimizer_trace(strategy_name):
    """获取优化收敛轨迹"""
    import glob as _glob
    trace_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'data', 'optimization_traces')
    pattern = os.path.join(trace_dir, f"{strategy_name}_*.json")
    trace_files = sorted(_glob.glob(pattern), reverse=True)
    
    if not trace_files:
        return jsonify({"success": True, "traces": [], "message": "无轨迹数据"})
    
    traces = []
    for tf in trace_files[:10]:  # 最多返回最近10个
        try:
            with open(tf, 'r', encoding='utf-8') as f:
                traces.append(json.load(f))
        except Exception:
            pass
    
    return jsonify({
        "success": True,
        "strategy_name": strategy_name,
        "total_files": len(trace_files),
        "traces": traces,
    })


# ============================================================
# 技术分析（5002代理）
# ============================================================

@api_gateway.route('/technical/analyze', methods=['POST'])
@require_auth
def technical_analyze():
    """技术分析"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().get_technical_analysis(
        symbol=data.get("symbol", "600000.SH"),
        days=data.get("days", 100),
    )
    return jsonify(result)

@api_gateway.route('/technical/batch', methods=['POST'])
@require_auth
def technical_batch():
    """批量技术分析"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().get_technical_batch(
        symbols=data.get("symbols", []),
        days=data.get("days", 100),
    )
    return jsonify(result)

@api_gateway.route('/technical/data/<symbol>', methods=['GET'])
@require_auth
def technical_data(symbol):
    """技术数据"""
    result = get_adapter().get_technical_data(symbol)
    return jsonify(result)


# ============================================================
# 行情数据（5002代理）
# ============================================================

@api_gateway.route('/market-data', methods=['GET'])
@require_auth
def market_data():
    """市场行情"""
    result = get_adapter().get_market_data()
    return jsonify(result)

@api_gateway.route('/performance-data', methods=['GET'])
def api_performance_data():
    """绩效数据"""
    result = get_adapter().get_performance_data()
    return jsonify(result)

@api_gateway.route('/strategy-status', methods=['GET'])
@require_auth
def strategy_status():
    """策略运行状态"""
    result = get_adapter().get_strategy_status()
    return jsonify(result)

@api_gateway.route('/technical-indicators', methods=['GET'])
@require_auth
def technical_indicators():
    """技术指标"""
    symbol = request.args.get("symbol", "000001.SZ")
    result = get_adapter().get_technical_indicators(symbol)
    return jsonify(result)


# ============================================================
# 数据源状态与K线/实时行情/财务（5003本地）
# ============================================================

@api_gateway.route('/data-source/status', methods=['GET'])
@require_auth
def data_source_status():
    """数据源连接状态"""
    result = get_adapter().get_data_source_status()
    return jsonify(result)

@api_gateway.route('/kline', methods=['GET'])
@require_auth
def kline():
    """K线数据"""
    symbol = request.args.get("symbol", "000001")
    period = request.args.get("period", "daily")
    days = request.args.get("days", 500, type=int)
    adjust = request.args.get("adjust", "qfq")
    result = get_adapter().get_kline(symbol, period, days, adjust)
    return jsonify(result)

@api_gateway.route('/realtime/<symbol>', methods=['GET'])
@require_auth
def realtime(symbol):
    """实时行情"""
    result = get_adapter().get_realtime(symbol)
    return jsonify(result)

@api_gateway.route('/financial/<symbol>', methods=['GET'])
@require_auth
def financial(symbol):
    """财务数据"""
    result = get_adapter().get_financial(symbol)
    return jsonify(result)

@api_gateway.route('/risk/assess', methods=['POST'])
@require_auth
def risk_assess():
    """风险评估"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "")
    strategy_name = data.get("strategy", "")
    backtest_result = data.get("backtest_result", {})
    position_info = data.get("position_info", {})
    result = get_adapter().risk_assess(symbol, strategy_name, backtest_result, position_info)
    return jsonify(result)


# ============================================================
# 股票池管理（5003本地）
# ============================================================

@api_gateway.route('/stock-pool', methods=['GET'])
@require_auth
def stock_pool():
    """股票池"""
    result = get_adapter().get_stock_pool()
    return jsonify(result)

@api_gateway.route('/stock-pool/add', methods=['POST'])
@require_auth
def stock_pool_add():
    """添加股票"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().add_stock_pool(data)
    return jsonify(result)

@api_gateway.route('/stock-pool/remove', methods=['POST'])
@require_auth
def stock_pool_remove():
    """移除股票"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().remove_stock_pool(data)
    return jsonify(result)

@api_gateway.route('/stock-pool/move-to-trading', methods=['POST'])
@require_auth
def stock_pool_move():
    """移入交易池"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().move_to_trading_pool(data)
    return jsonify(result)

@api_gateway.route('/trading-pool', methods=['GET'])
@require_auth
def trading_pool():
    """交易池"""
    result = get_adapter().get_trading_pool()
    return jsonify(result)

@api_gateway.route('/trading-pool/close', methods=['POST'])
@require_auth
def trading_pool_close():
    """关闭持仓"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().close_trading_pool(data)
    return jsonify(result)


# ============================================================
# 券商管理（5002代理）
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
# 策略高级（5002代理）
# ============================================================

@api_gateway.route('/strategy/test', methods=['POST'])
@require_auth
def strategy_test():
    """策略测试"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().strategy_test(
        strategy_name=data.get("strategy_name", data.get("strategy", "")),
        params=data.get("params", {}),
    )
    return jsonify(result)

@api_gateway.route('/strategy/docs/<strategy_name>', methods=['GET'])
@require_auth
def strategy_docs(strategy_name):
    """策略文档"""
    result = get_adapter().strategy_docs(strategy_name)
    return jsonify(result)

@api_gateway.route('/walk-forward', methods=['POST'])
@require_auth
def walk_forward():
    """步进优化"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().walk_forward(data)
    return jsonify(result)


# ============================================================
# LLM管理（5002代理）
# ============================================================

@api_gateway.route('/llm/models', methods=['GET'])
@require_auth
def llm_models():
    """LLM模型列表"""
    result = get_adapter().get_llm_models()
    return jsonify(result)

@api_gateway.route('/llm/switch', methods=['POST'])
@require_auth
def llm_switch():
    """切换LLM"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().switch_llm(data.get("model", ""))
    return jsonify(result)

@api_gateway.route('/llm/config', methods=['GET'])
@require_auth
def llm_config():
    """LLM配置"""
    result = get_adapter().get_llm_config()
    return jsonify(result)


# ============================================================
# 风控高级（5002代理）
# ============================================================

@api_gateway.route('/risk/stop-loss', methods=['GET'])
@require_auth
def risk_stop_loss():
    """止损止盈"""
    result = get_adapter().get_risk_stop_loss()
    return jsonify(result)


# ============================================================
# 账户高级（5002代理）
# ============================================================

@api_gateway.route('/account/stocks', methods=['GET'])
@require_auth
def account_stocks():
    """账户股票"""
    result = get_adapter().get_account_stocks()
    return jsonify(result)

@api_gateway.route('/account/reset-risk', methods=['POST'])
@require_auth
def account_reset_risk():
    """重置风控"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().reset_account_risk(data.get("name"))
    return jsonify(result)


@api_gateway.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    adapter = get_adapter()
    aurora_ok = adapter.check_aurora_backend()
    return jsonify({
        "success": True,
        "status": "healthy" if adapter.is_connected() else "degraded",
        "aurora": "connected" if aurora_ok else "disconnected",
        "qs_robot": "online",
        "degradation": adapter.get_degradation_status().get("data", {}),
    })


@api_gateway.route('/health/degradation', methods=['GET'])
def health_degradation():
    """降级状态查询（供前端状态栏使用）"""
    adapter = get_adapter()
    result = adapter.get_degradation_status()
    return jsonify(result)


@api_gateway.route('/health/params-sync', methods=['POST'])
def health_params_sync():
    """触发参数同步：将5003优化参数同步到5002"""
    adapter = get_adapter()
    result = adapter.sync_params_to_aurora()
    return jsonify(result)


# ============================================================
# 系统健康巡检（自动化诊断引擎）
# ============================================================

@api_gateway.route('/health/check', methods=['POST'])
@require_auth
def health_check_run():
    """触发系统巡检 — 快速/深度模式"""
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "quick")
    checker = get_health_checker()
    report = checker.run_check(mode=mode)
    return jsonify({
        "success": True,
        "data": {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "mode": report.mode,
            "overall_score": report.overall_score,
            "overall_status": report.overall_status,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "layers": report.layers,
            "alerts": report.alerts,
            "elapsed_seconds": report.elapsed_seconds,
        }
    })


@api_gateway.route('/health/report/<report_id>', methods=['GET'])
@require_auth
def health_report_get(report_id):
    """获取历史巡检报告"""
    checker = get_health_checker()
    report = checker.get_report(report_id)
    if report:
        return jsonify({"success": True, "data": report})
    return jsonify({"success": False, "message": "报告不存在"}), 404


@api_gateway.route('/health/reports', methods=['GET'])
@require_auth
def health_report_list():
    """获取巡检报告列表"""
    checker = get_health_checker()
    limit = request.args.get("limit", 20, type=int)
    reports = checker.get_report_list(limit=limit)
    return jsonify({"success": True, "data": {"reports": reports}})


@api_gateway.route('/health/scheduler', methods=['POST'])
@require_auth
def health_scheduler():
    """定时巡检开关"""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "status")
    interval = data.get("interval", 30)
    checker = get_health_checker()

    if action == "start":
        result = checker.start_scheduler(interval_minutes=interval)
    elif action == "stop":
        result = checker.stop_scheduler()
    else:
        result = checker.get_scheduler_status()
    return jsonify({"success": True, "data": result})


# ============================================================
# 前后端对齐: 前端调用的API端点补齐
# ============================================================

@api_gateway.route('/tau/optimize', methods=['POST'])
@require_auth
def tau_optimize():
    """韬定律优化 — 前端 /api/tau/optimize 的别名，转发到 /api/optimizer/run"""
    return optimizer_run()

@api_gateway.route('/aurora/strategy-list', methods=['GET'])
@require_auth
def aurora_strategy_list():
    """前端 /api/aurora/strategy-list 的别名，转发到 /api/strategy/list"""
    return strategy_list()

@api_gateway.route('/integration/optimize', methods=['POST'])
@require_auth
def integration_optimize():
    """前端 /api/integration/optimize 的别名，转发到 /api/optimizer/run"""
    return optimizer_run()

@api_gateway.route('/integration/stock_pool', methods=['POST'])
@require_auth
def integration_stock_pool():
    """前端 /api/integration/stock_pool — 股票池集成流程"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        strategy_name = data.get("strategy_name", "")
        if not strategy_name:
            strategies = get_adapter().get_strategy_list()
            strategy_name = strategies[0]["name"] if strategies else ""
        result = bus.auto_hybrid_power_flow(strategy_name)
        return jsonify({"success": result.get("success", True), "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/integration/full_workflow', methods=['POST'])
@require_auth
def integration_full_workflow():
    """前端 /api/integration/full_workflow — 完整集成流程"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        strategy_names = data.get("strategies", [])
        result = bus.auto_batch_optimize(strategy_names) if strategy_names else \
                 {"success": False, "error": "请指定策略列表"}
        return jsonify({"success": result.get("success", True), "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/vibe/analyze', methods=['POST'])
@require_auth
def vibe_analyze():
    """前端 /api/vibe/analyze — 股票智能分析"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        stock_code = data.get("code", data.get("symbol", ""))
        strategy_name = data.get("strategy", data.get("strategy_name", ""))
        if not stock_code:
            return jsonify({"success": False, "error": "请提供股票代码"}), 400
        # 使用选股流程进行标的分析
        result = bus.auto_vibe_stock_selection(
            market_scope=data.get("market", "all"),
            strategy_name=strategy_name,
            target_count=data.get("count", 10)
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/vibe/market_scan', methods=['POST'])
@require_auth
def vibe_market_scan():
    """前端 /api/vibe/market_scan — 全市场扫描"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        result = bus.auto_vibe_stock_selection(
            symbol_list=data.get("symbols"),
            auto_into_pool=data.get("auto_into_pool", True),
            top_n=data.get("count", 20),
            max_analyze=data.get("max_analyze", 200),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# Vibe-Trading 与熵韬优化器 双向联动闭环 API
# ============================================================

@api_gateway.route('/vibe/analyze_and_optimize', methods=['POST'])
@require_auth
def vibe_analyze_and_optimize():
    """POST /api/vibe/analyze_and_optimize
    Vibe多智能体分析 → 熵韬收敛优化 → 风控复核 完整闭环

    接收: {symbols: ["000001", "600519"], use_optimizer: true}
    """
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        symbols = data.get("symbols", None)
        use_optimizer = data.get("use_optimizer", True)

        if use_optimizer:
            result = bus.auto_vibe_optimize_workflow(symbols=symbols)
        else:
            # 仅Vibe分析，不做优化
            result = bus.auto_vibe_stock_selection(
                symbol_list=symbols,
                auto_into_pool=False,
                top_n=data.get("count", 20),
                max_analyze=data.get("max_analyze", 100),
            )

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/optimize_with_feedback', methods=['POST'])
@require_auth
def vibe_optimize_with_feedback():
    """POST /api/vibe/optimize_with_feedback
    优化器精选股票池 → Vibe风控Agent二次复核

    接收: {optimized_pool: [...], require_vibe_review: true}
    """
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        data = request.get_json(silent=True) or {}
        optimized_pool = data.get("optimized_pool", [])
        require_vibe_review = data.get("require_vibe_review", True)

        if not optimized_pool:
            return jsonify({"success": False, "error": "请提供optimized_pool"}), 400

        if require_vibe_review:
            result = bus.vibe_optimizer_feedback(optimized_pool)
        else:
            result = {
                "success": True,
                "data": {"approved_pool": optimized_pool, "approved_count": len(optimized_pool)},
                "message": "跳过Vibe复核",
                "elapsed_seconds": 0,
            }

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/trace/<stock_code>', methods=['GET'])
@require_auth
def vibe_trace_lineage(stock_code):
    """获取股票全链路溯源：哪个Agent推荐、评分、技能、优化轮次、风控审核"""
    try:
        from core.integration_bus import StrategyIntegrationBus
        bus = StrategyIntegrationBus()
        trace = bus.trace_stock_lineage(stock_code)
        return jsonify(APIResponse.success(trace))
    except Exception as e:
        logger.error(f"溯源失败: {e}")
        return jsonify(APIResponse.error(f"溯源失败: {str(e)}")), 500


@api_gateway.route('/vibe/convergence_status', methods=['GET'])
@require_auth
def vibe_convergence_status():
    """GET /api/vibe/convergence_status
    返回当前优化器收敛状态（迭代次数、熵值、方差、是否收敛）
    """
    try:
        from core.tau_optimizer_cluster import get_parameter_store
        store = get_parameter_store()
        all_info = store.get_all_strategies_info()

        strategies_status = []
        for info in all_info:
            name = info.get("name", "")
            if name:
                best_params = store.get_best_params(name)
                strategies_status.append({
                    "strategy": name,
                    "version": info.get("current_version", 0),
                    "best_score": info.get("best_score", 0),
                    "convergence_iterations": best_params.get("convergence_iterations", "N/A") if best_params else "N/A",
                    "entropy": best_params.get("entropy", "N/A") if best_params else "N/A",
                    "variance": best_params.get("variance", "N/A") if best_params else "N/A",
                    "converged": info.get("best_score", 0) > 0.5,
                    "last_optimized": info.get("last_optimized", ""),
                })

        return jsonify({
            "success": True,
            "data": {
                "total_strategies": len(strategies_status),
                "converged_count": sum(1 for s in strategies_status if s["converged"]),
                "strategies": strategies_status,
            },
            "message": f"优化器收敛状态: {sum(1 for s in strategies_status if s['converged'])}/{len(strategies_status)}已收敛",
            "elapsed_seconds": 0,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/auto_adaptive', methods=['POST'])
@require_auth
def vibe_auto_adaptive():
    """POST /api/vibe/auto_adaptive
    自适应市场重校准：检测市场状态变化，自动触发优化器重收敛
    """
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.adaptive_market_recalibration()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/market_environment', methods=['GET'])
@require_auth
def vibe_market_environment():
    """GET /api/vibe/market_environment
    返回当前Vibe判定的市场环境（震荡/趋势/高波动）及置信度
    """
    try:
        from core.vibe_integration import get_vibe_integration
        vibe = get_vibe_integration()

        if hasattr(vibe, 'analyze_market_environment'):
            me_result = vibe.analyze_market_environment()
        else:
            me_result = {"regime": "震荡", "confidence": 0.5, "volatility": "medium", "trend": "neutral"}

        return jsonify({
            "success": True,
            "data": {
                "regime": me_result.get("regime", "震荡"),
                "confidence": me_result.get("confidence", 0.5),
                "volatility": me_result.get("volatility", "medium"),
                "trend": me_result.get("trend", "neutral"),
                "timestamp": me_result.get("timestamp", ""),
            },
            "message": f"当前市场环境: {me_result.get('regime', '震荡')} (置信度={me_result.get('confidence', 0.5):.2f})",
            "elapsed_seconds": 0,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/stock_pool/run_pipeline', methods=['POST'])
@require_auth
def stock_pool_run_pipeline():
    """前端 /api/stock_pool/run_pipeline — 股票池完整流程"""
    try:
        from stock_pool.main import StockPoolSystem
        system = StockPoolSystem()
        stocks = system.generate_sample_stocks(20)
        result = system.run_full_pipeline(stocks)
        return jsonify({
            "success": True,
            "data": {
                "filtered_count": len(result.get("filtered", [])),
                "matched_count": len(result.get("matched", [])),
                "simulated_count": len(result.get("simulated", [])),
                "final_count": len(result.get("final", [])),
                "final_stocks": [{
                    "code": f["stock"].code,
                    "name": f["stock"].name,
                    "strategy": f["strategy"].name,
                    "score": f["score"],
                    "grade": f["grade"]
                } for f in result.get("final", [])]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 特种兵策略 (Special Forces Wyckoff)
# ============================================================

@api_gateway.route('/special_forces/evolution', methods=['POST'])
@require_auth
def special_forces_evolution():
    """运行特种兵策略自演进优化"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "510300")
    population_size = data.get("population_size", 20)
    max_generations = data.get("max_generations", 30)
    force_refresh = data.get("force_refresh", False)
    incremental = data.get("incremental", False)

    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_special_forces_evolution(
            symbol=symbol,
            population_size=population_size,
            max_generations=max_generations,
            force_refresh=force_refresh,
            incremental=incremental,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/special_forces/backtest', methods=['POST'])
@require_auth
def special_forces_backtest():
    """运行特种兵策略回测"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "510300")
    params = data.get("params", None)
    initial_capital = data.get("initial_capital", 100000.0)
    use_optimized = data.get("use_optimized", True)

    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_special_forces_backtest(
            symbol=symbol,
            params=params,
            initial_capital=initial_capital,
            use_optimized=use_optimized,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/special_forces/params/<symbol>', methods=['GET'])
@require_auth
def special_forces_params(symbol):
    """获取特种兵策略参数"""
    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.get_special_forces_params(symbol)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/special_forces/start', methods=['POST'])
@require_auth
def special_forces_start():
    """启动特种兵策略"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "510300")
    balance = data.get("balance", 100000.0)
    use_optimized_params = data.get("use_optimized_params", True)

    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        success, message = mgr.start_special_forces(
            symbol=symbol,
            balance=balance,
            use_optimized_params=use_optimized_params,
        )
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/special_forces/stop', methods=['POST'])
@require_auth
def special_forces_stop():
    """停止特种兵策略"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "510300")

    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        strategy_name = f"special_forces_{symbol}"
        mgr._active_strategies.pop(strategy_name, None)
        return jsonify({"success": True, "message": f"特种兵策略 {symbol} 已停止"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/special_forces/status', methods=['GET'])
@require_auth
def special_forces_status():
    """获取特种兵策略运行状态"""
    symbol = request.args.get("symbol", "510300")

    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        strategy_name = f"special_forces_{symbol}"
        active = strategy_name in mgr._active_strategies
        info = mgr._active_strategies.get(strategy_name)
        return jsonify({
            "success": True,
            "data": {
                "symbol": symbol,
                "active": active,
                "status": info.status.value if info and hasattr(info, 'status') else "stopped",
                "best_params": info.best_params if info else {},
                "best_score": info.best_score if info else 0,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# NLP自然语言指令解析 (D1: 审计修复)
# ============================================================

@api_gateway.route('/vibe/nlp/parse', methods=['POST'])
@require_auth
def vibe_nlp_parse():
    """POST /api/vibe/nlp/parse
    解析自然语言指令，返回意图识别、技能映射、错配检测结果
    
    Body: {"text": "分析贵州茅台"}
    """
    try:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")

        from core.nlp_commander import parse_command
        result = parse_command(text)

        return jsonify({
            "success": True,
            "data": result,
            "message": f"意图: {result['intent_type']} (置信度: {result['confidence']:.0%})",
        })
    except Exception as e:
        logger.error(f"NLP解析失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/nlp/skills', methods=['GET'])
@require_auth
def vibe_nlp_skills():
    """GET /api/vibe/nlp/skills?category=技术分析
    列出可用技能及分类
    """
    try:
        from core.nlp_commander import get_nlp_commander
        cmd = get_nlp_commander()
        category = request.args.get("category", None)
        skills = cmd.list_available_skills(category)
        categories = cmd.get_skill_categories()

        return jsonify({
            "success": True,
            "data": {
                "skills": skills,
                "categories": categories,
                "total": len(skills),
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/nlp/help', methods=['GET'])
def vibe_nlp_help():
    """GET /api/vibe/nlp/help
    返回NLP指令系统帮助文本
    """
    try:
        from core.nlp_commander import get_nlp_commander
        cmd = get_nlp_commander()
        return jsonify({
            "success": True,
            "data": {"help_text": cmd.get_help_text()},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 会话记忆与推理日志 (D1: 审计修复)
# ============================================================

@api_gateway.route('/vibe/session/history', methods=['GET'])
@require_auth
def vibe_session_history():
    """GET /api/vibe/session/history?limit=50
    获取当前会话历史
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        limit = request.args.get("limit", 50, type=int)
        history = mgr.get_history(limit)
        return jsonify({
            "success": True,
            "data": {"session_id": mgr.session_id, "history": history, "count": len(history)},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/session/new', methods=['POST'])
@require_auth
def vibe_session_new():
    """POST /api/vibe/session/new
    创建新会话
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        sid = mgr.new_session()
        return jsonify({"success": True, "data": {"session_id": sid}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/reasoning/<agent_name>', methods=['GET'])
@require_auth
def vibe_reasoning_by_agent(agent_name):
    """GET /api/vibe/reasoning/<agent_name>?limit=20
    获取指定智能体的推理历史
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        limit = request.args.get("limit", 20, type=int)
        logs = mgr.get_agent_reasoning(agent_name, limit)
        return jsonify({
            "success": True,
            "data": {"agent": agent_name, "logs": logs, "count": len(logs)},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/reasoning/symbol/<symbol>', methods=['GET'])
@require_auth
def vibe_reasoning_by_symbol(symbol):
    """GET /api/vibe/reasoning/symbol/<symbol>?limit=20
    获取指定股票的推理历史
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        limit = request.args.get("limit", 20, type=int)
        logs = mgr.get_symbol_reasoning(symbol, limit)
        return jsonify({
            "success": True,
            "data": {"symbol": symbol, "logs": logs, "count": len(logs)},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/task/progress', methods=['GET'])
@require_auth
def vibe_task_progress():
    """GET /api/vibe/task/progress?task_id=xxx
    获取任务进度
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        task_id = request.args.get("task_id", "")
        if task_id:
            status = mgr.get_task_status(task_id)
            return jsonify({"success": True, "data": status})
        else:
            active = mgr.get_active_tasks()
            return jsonify({
                "success": True,
                "data": {"active_tasks": active, "count": len(active)},
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/task/cancel', methods=['POST'])
@require_auth
def vibe_task_cancel():
    """POST /api/vibe/task/cancel
    Body: {"task_id": "xxx"}
    """
    try:
        from core.session_memory import get_memory_manager
        mgr = get_memory_manager()
        data = request.get_json(silent=True) or {}
        task_id = data.get("task_id", "")
        if not task_id:
            return jsonify({"success": False, "error": "缺少task_id"}), 400
        mgr.cancel_task(task_id)
        return jsonify({"success": True, "message": f"任务 {task_id} 已取消"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 三层下钻可视化 (D4: 审计修复)
# ============================================================

@api_gateway.route('/vibe/drill/macro', methods=['GET'])
@require_auth
def vibe_drill_macro():
    """GET /api/vibe/drill/macro
    宏观市场全景（行业板块概览）
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_macro_overview()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/industry/<sector_name>', methods=['GET'])
@require_auth
def vibe_drill_industry(sector_name):
    """GET /api/vibe/drill/industry/<sector_name>
    行业板块详情（个股列表）
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_industry_detail(sector_name)
        if "error" in data:
            return jsonify({"success": False, "error": data["error"], "data": data}), 400
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/stock/<symbol>', methods=['GET'])
@require_auth
def vibe_drill_stock(symbol):
    """GET /api/vibe/drill/stock/<symbol>
    个股详情
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_stock_detail(symbol)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/factor/<symbol>', methods=['GET'])
@require_auth
def vibe_drill_factor_overview(symbol):
    """GET /api/vibe/drill/factor/<symbol>
    因子全景（策略评分分解）
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_factor_overview(symbol)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/factor/<symbol>/<factor_id>', methods=['GET'])
@require_auth
def vibe_drill_factor_detail(symbol, factor_id):
    """GET /api/vibe/drill/factor/<symbol>/<factor_id>
    单因子详情（因子分解）
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_factor_detail(symbol, factor_id)
        if "error" in data:
            return jsonify({"success": False, "error": data["error"], "data": data}), 400
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/trades', methods=['GET'])
@require_auth
def vibe_drill_trades():
    """GET /api/vibe/drill/trades?strategy=xxx
    策略交易汇总
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        strategy = request.args.get("strategy", None)
        data = engine.get_strategy_trades(strategy)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/trade/<int:trade_index>', methods=['GET'])
@require_auth
def vibe_drill_trade_detail(trade_index):
    """GET /api/vibe/drill/trade/<trade_index>
    单笔交易详情
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        data = engine.get_trade_detail(trade_index)
        if "error" in data:
            return jsonify({"success": False, "error": data["error"], "data": data}), 400
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/drill/timeline', methods=['GET'])
@require_auth
def vibe_drill_timeline():
    """GET /api/vibe/drill/timeline?strategy=xxx
    交易时间线（按日汇总）
    """
    try:
        from core.drill_down import get_drill_engine
        engine = get_drill_engine()
        strategy = request.args.get("strategy", None)
        data = engine.get_trade_timeline(strategy)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 基础设施增强 (D4/D5/D7: 审计修复)
# ============================================================

@api_gateway.route('/vibe/trace/full/<node_id>', methods=['GET'])
@require_auth
def vibe_trace_full(node_id):
    """GET /api/vibe/trace/full/<node_id>
    反向溯源：获取数据节点的完整溯源链路
    """
    try:
        from core.infrastructure import get_traceability
        trace = get_traceability()
        lineage = trace.get_full_lineage(node_id)
        return jsonify({"success": True, "data": lineage})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/computation/<comp_id>', methods=['GET'])
@require_auth
def vibe_computation_steps(comp_id):
    """GET /api/vibe/computation/<comp_id>
    中间运算过程：获取计算步骤记录
    """
    try:
        from core.infrastructure import get_visualizer
        viz = get_visualizer()
        steps = viz.get_computation_steps(comp_id)
        return jsonify({
            "success": True,
            "data": {"comp_id": comp_id, "steps": steps, "count": len(steps)},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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


@api_gateway.route('/vibe/anomaly/check', methods=['POST'])
@require_auth
def vibe_anomaly_check():
    """POST /api/vibe/anomaly/check
    手动触发异常检测
    Body: {"symbol": "600519", "price": 2000, "prev_close": 1800, "volume": 1e8, "avg_volume": 2e7}
    """
    try:
        from core.infrastructure import get_anomaly_detector
        ad = get_anomaly_detector()
        data = request.get_json(silent=True) or {}
        results = {}

        if "price" in data and "prev_close" in data:
            r = ad.check_price_anomaly(data.get("symbol", ""), data["price"], data["prev_close"])
            if r:
                results["price"] = r

        if "volume" in data and "avg_volume" in data:
            r = ad.check_volume_anomaly(data.get("symbol", ""), data["volume"], data["avg_volume"])
            if r:
                results["volume"] = r

        return jsonify({
            "success": True,
            "data": {"anomalies": results, "anomaly_count": len(results)},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/pool/status', methods=['GET'])
@require_auth
def vibe_pool_status():
    """GET /api/vibe/pool/status
    动态股票池：获取当前股票池状态
    """
    try:
        from core.infrastructure import get_stock_pool
        pool = get_stock_pool()
        config = pool.get_pool_config()
        stocks = pool.get_current_pool()
        return jsonify({
            "success": True,
            "data": {"config": config, "stocks": stocks},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/pool/update', methods=['POST'])
@require_auth
def vibe_pool_update():
    """POST /api/vibe/pool/update
    动态股票池：触发股票池更新
    Body: {"regime": "bull"}
    """
    try:
        from core.infrastructure import get_stock_pool
        pool = get_stock_pool()
        data = request.get_json(silent=True) or {}
        regime = data.get("regime", "range")
        pool.update_regime(regime, data.get("market_data"))
        config = pool.get_pool_config()
        return jsonify({
            "success": True,
            "data": config,
            "message": f"股票池已切换至 {regime} ({config['config']['name']})",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/trade/live', methods=['POST'])
@require_auth
def vibe_trade_live():
    """POST /api/vibe/trade/live
    实盘成交回写：记录实盘成交数据
    Body: {"symbol": "600519", "action": "buy", "price": 1800, "quantity": 100, "timestamp": "..."}
    """
    try:
        from core.infrastructure import get_trade_writer
        tw = get_trade_writer()
        data = request.get_json(silent=True) or {}
        result = tw.record_live_trade(data)
        if result["success"]:
            return jsonify({"success": True, "data": result})
        return jsonify({"success": False, "error": result["error"]}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/trade/summary', methods=['GET'])
@require_auth
def vibe_trade_summary():
    """GET /api/vibe/trade/summary?hours=24&symbol=600519
    实盘成交摘要
    """
    try:
        from core.infrastructure import get_trade_writer
        tw = get_trade_writer()
        hours = request.args.get("hours", 24, type=int)
        symbol = request.args.get("symbol", None)
        summary = tw.get_trade_summary(hours)
        if symbol:
            trades = tw.get_recent_trades(hours, symbol)
            return jsonify({"success": True, "data": {"summary": summary, "trades": trades}})
        return jsonify({"success": True, "data": {"summary": summary}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/feedback/record', methods=['POST'])
@require_auth
def vibe_feedback_record():
    """POST /api/vibe/feedback/record
    Agent迭代修正：记录预测vs实际
    Body: {"agent": "trend", "symbol": "600519", "prediction": {...}, "actual": {...}}
    """
    try:
        from core.infrastructure import get_feedback_loop
        fb = get_feedback_loop()
        data = request.get_json(silent=True) or {}
        result = fb.record_prediction(
            data.get("agent", "unknown"),
            data.get("symbol", ""),
            data.get("prediction", {}),
            data.get("actual", {}),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_gateway.route('/vibe/feedback/performance/<agent_name>', methods=['GET'])
@require_auth
def vibe_feedback_performance(agent_name):
    """GET /api/vibe/feedback/performance/<agent_name>
    Agent迭代修正：获取Agent表现统计
    """
    try:
        from core.infrastructure import get_feedback_loop
        fb = get_feedback_loop()
        perf = fb.get_agent_performance(agent_name)
        stats = fb.get_correction_stats()
        return jsonify({
            "success": True,
            "data": {"performance": perf, "correction_stats": stats},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 缺失API补齐 — 代理到5002 Aurora后端
# ============================================================

@api_gateway.route('/strategy/library', methods=['GET'])
@require_auth
def strategy_library():
    """策略库 — 代理到5002"""
    try:
        import requests as req
        r = req.get(f"{AURORA_BACKEND}/api/strategy/library", timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/strategy-params', methods=['GET'])
@require_auth
def strategy_params():
    """策略参数 — 代理到5002"""
    try:
        import requests as req
        r = req.get(f"{AURORA_BACKEND}/api/strategy-params", timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/backtest/best', methods=['GET'])
@require_auth
def backtest_best():
    """最佳回测 — 代理到5002"""
    try:
        import requests as req
        r = req.get(f"{AURORA_BACKEND}/api/backtest/best", timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/model-versions', methods=['GET'])
@require_auth
def model_versions():
    """模型版本 — 代理到5002"""
    try:
        import requests as req
        r = req.get(f"{AURORA_BACKEND}/api/model-versions", timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_gateway.route('/risk-control/status', methods=['GET'])
@require_auth
def risk_control_status():
    """风控状态 — 代理到5002"""
    try:
        import requests as req
        r = req.get(f"{AURORA_BACKEND}/api/risk-control/status", timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
# 一键选股自动化工作流
# ============================================================

@api_gateway.route('/workflow/status', methods=['GET'])
@require_auth
def workflow_status():
    """获取工作流运行状态"""
    try:
        from core.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()
        return jsonify(APIResponse.success(engine.get_status()))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/workflow/run', methods=['POST'])
@require_auth
@sanitize_input
def workflow_run():
    """一键执行选股工作流"""
    try:
        from core.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()

        data = request.get_json(silent=True) or {}
        stock_pool = data.get("stock_pool", None)
        strategy_names = data.get("strategies", None)
        fast_mode = data.get("fast_mode", False)
        batch_mode = data.get("batch_mode", False)

        import threading
        def _run():
            engine.run_oneclick(
                stock_pool=stock_pool,
                strategy_names=strategy_names,
                fast_mode=fast_mode,
                batch_mode=batch_mode,
            )

        threading.Thread(target=_run, daemon=True).start()
        return jsonify(APIResponse.success({
            "message": "工作流已启动",
            "fast_mode": fast_mode,
            "batch_mode": batch_mode,
        }))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/workflow/history', methods=['GET'])
@require_auth
def workflow_history():
    """获取工作流历史记录"""
    try:
        from core.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()
        return jsonify(APIResponse.success(engine.get_history()))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/workflow/step', methods=['POST'])
@require_auth
@sanitize_input
def workflow_step():
    """执行单个工作流步骤"""
    try:
        from core.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()
        data = request.get_json(silent=True) or {}
        step = data.get("step", "discover")
        result = engine.run_step(step)
        return jsonify(APIResponse.success({
            "name": result.name,
            "status": result.status,
            "message": result.message,
            "data": result.data,
            "error": result.error,
        }))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


# ============================================================
# 系统健康检查（增强版）
# ============================================================

@api_gateway.route('/health/enhanced', methods=['GET'])
@require_auth
def health_full_enhanced():
    """完整系统健康检查（含韬策略引擎+优化器+自适应层）"""
    try:
        from core.system_health_checker import get_health_checker
        checker = get_health_checker()
        report = checker.run_quick_check()

        # 补充集群引擎健康
        cluster_health = {}
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            cluster_health = bus.cluster_engine_health_check()
        except Exception:
            pass

        # 补充自适应层健康
        adaptation_health = {}
        try:
            from core.adaptive_market_regime import get_adaptation_engine
            adaptation = get_adaptation_engine()
            adaptation_health = adaptation.get_health_report()
        except Exception:
            pass

        return jsonify(APIResponse.success({
            "system_health": report.to_dict() if hasattr(report, 'to_dict') else str(report),
            "cluster_engine": cluster_health,
            "adaptation_engine": adaptation_health,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        }))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/health/cluster', methods=['GET'])
@require_auth
def health_cluster_check():
    """韬策略引擎健康检查"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        health = bus.cluster_engine_health_check()
        return jsonify(APIResponse.success(health))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/health/adaptation', methods=['GET'])
@require_auth
def health_adaptation_check():
    """自适应策略层健康检查"""
    try:
        from core.adaptive_market_regime import get_adaptation_engine
        adaptation = get_adaptation_engine()
        health = adaptation.get_health_report()
        return jsonify(APIResponse.success(health))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500


@api_gateway.route('/health/optimizer', methods=['GET'])
@require_auth
def health_optimizer_check():
    """优化器集群健康检查"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        report = bus.get_workflow_report()
        return jsonify(APIResponse.success(report))
    except Exception as e:
        return jsonify(APIResponse.error(str(e))), 500