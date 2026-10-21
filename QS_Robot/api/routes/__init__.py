# -*- coding: utf-8 -*-
"""API 路由统一注册"""


def register_all_routes(api_gateway):
    """注册所有子路由到 API 网关蓝图"""
    from api.routes.alert_routes import register_routes as register_alert_routes
    register_alert_routes(api_gateway)
    from api.routes.backtest_routes import register_routes as register_backtest_routes
    register_backtest_routes(api_gateway)
    from api.routes.broker_routes import register_routes as register_broker_routes
    register_broker_routes(api_gateway)
    from api.routes.health_routes import register_routes as register_health_routes
    register_health_routes(api_gateway)
    from api.routes.market_data_routes import (
        register_routes as register_market_data_routes,
    )
    register_market_data_routes(api_gateway)
    from api.routes.misc_routes import register_routes as register_misc_routes
    register_misc_routes(api_gateway)
    from api.routes.monitor_routes import register_routes as register_monitor_routes
    register_monitor_routes(api_gateway)
    from api.routes.optimizer_routes import register_routes as register_optimizer_routes
    register_optimizer_routes(api_gateway)
    from api.routes.risk_routes import register_routes as register_risk_routes
    register_risk_routes(api_gateway)
    from api.routes.security_routes import register_routes as register_security_routes
    register_security_routes(api_gateway)
    from api.routes.special_forces_routes import (
        register_routes as register_special_forces_routes,
    )
    register_special_forces_routes(api_gateway)
    from api.routes.stock_pool_routes import (
        register_routes as register_stock_pool_routes,
    )
    register_stock_pool_routes(api_gateway)
    from api.routes.strategy_routes import register_routes as register_strategy_routes
    register_strategy_routes(api_gateway)
    from api.routes.technical_routes import register_routes as register_technical_routes
    register_technical_routes(api_gateway)
    from api.routes.trade_routes import register_routes as register_trade_routes
    register_trade_routes(api_gateway)
    from api.routes.user_routes import register_routes as register_user_routes
    register_user_routes(api_gateway)
    from api.routes.vibe_routes import register_routes as register_vibe_routes
    register_vibe_routes(api_gateway)
    from api.routes.workflow_routes import register_routes as register_workflow_routes
    register_workflow_routes(api_gateway)

