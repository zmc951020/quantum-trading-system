# -*- coding: utf-8 -*-
"""
Aurora API 适配层
================
提供统一API网关、响应格式化和Aurora API适配功能

目录结构:
    api/
    ├── __init__.py          # 模块导出
    ├── gateway.py           # API网关
    ├── aurora_adapter.py    # Aurora API适配器
    ├── response_formatter.py # 统一响应格式化
    └── routes/              # 路由模块
        ├── __init__.py
        ├── strategy_routes.py
        ├── backtest_routes.py
        ├── risk_routes.py
        └── broker_routes.py

使用方式:
    from api.gateway import api_gateway
    from api.response_formatter import APIResponse
    from api.aurora_adapter import AuroraAPIAdapter
"""

from .response_formatter import APIResponse
from .aurora_adapter import AuroraAPIAdapter
from .gateway import api_gateway

__all__ = [
    'APIResponse',
    'AuroraAPIAdapter',
    'api_gateway',
]
