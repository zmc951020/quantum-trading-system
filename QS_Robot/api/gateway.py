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
from .aurora_core_adapter import get_aurora_adapter, AuroraCoreAdapter
from .response_formatter import APIResponse
from core.system_health_checker import get_health_checker

# 创建API网关蓝图
api_gateway = Blueprint('api_gateway', __name__, url_prefix='/api')

# 全局适配器实例
_adapter: Optional[AuroraCoreAdapter] = None


def get_adapter() -> AuroraCoreAdapter:
    """获取Aurora核心适配器（直接导入模式）"""
    global _adapter
    if _adapter is None:
        _adapter = get_aurora_adapter()
    return _adapter


def require_auth(f):
    """请求鉴权装饰器 - 验证会话有效性"""
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
        except ImportError:
            pass

        return f(*args, **kwargs)
    return decorated


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
def strategy_start(name):
    """启动策略"""
    data = request.get_json(silent=True) or {}
    result = get_adapter().start_strategy(name, data.get("params"))
    return jsonify(result)


@api_gateway.route('/strategy/<name>/stop', methods=['POST'])
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
# 券商相关
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

@api_gateway.route('/broker/cancel_order', methods=['POST'])
@require_auth
def broker_cancel_order():
    """撤单 — 代理到5002 /api/stock/remove"""
    data = request.get_json(silent=True) or {}
    return jsonify(get_adapter().broker_cancel_order_local(data))

@api_gateway.route('/broker/positions', methods=['GET'])
def broker_positions():
    """券商持仓 — 代理到5002 /api/positions"""
    return jsonify(get_adapter().get_broker_positions())

@api_gateway.route('/broker/account', methods=['GET'])
@require_auth
def broker_account():
    """券商账户 — 代理到5002 /api/accounts"""
    return jsonify(get_adapter().get_broker_account())


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
# 股票池管理（5002代理）
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