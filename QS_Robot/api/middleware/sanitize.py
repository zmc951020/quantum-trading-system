# -*- coding: utf-8 -*-
"""输入净化中间件"""
import re
from functools import wraps

from flask import request


def sanitize_input(f):
    """输入净化装饰器 — 清理请求参数中的危险字符"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'PATCH'):
            if request.is_json:
                data = request.get_json(silent=True)
                if isinstance(data, dict):
                    _sanitize_dict(data)
            elif request.form:
                pass
        if request.args:
            _sanitize_args = {k: _sanitize_value(v) for k, v in request.args.items()}
            request.sanitized_args = _sanitize_args
        return f(*args, **kwargs)
    return decorated


def _sanitize_value(value: str) -> str:
    """输入净化：白名单模式，移除不可打印字符，限制长度"""
    if not isinstance(value, str):
        return value
    if len(value) > 4096:
        value = value[:4096]
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
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
