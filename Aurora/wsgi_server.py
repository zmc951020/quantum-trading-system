# coding: utf-8
"""Aurora WSGI Server 入口 - 生产级Gunicorn启动入口

用法:
    gunicorn wsgi_server:application -w 4 -b 0.0.0.0:8000
"""
from main import create_app

application = create_app()