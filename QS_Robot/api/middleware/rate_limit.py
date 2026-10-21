# -*- coding: utf-8 -*-
"""请求频率限制中间件"""
from functools import wraps

from api.response_formatter import APIResponse
from flask import jsonify, request


def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """请求频率限制装饰器 — 自动清理过期条目防止内存泄漏"""
    def decorator(f):
        _rate_cache = {}
        _last_cleanup = [0]

        @wraps(f)
        def decorated(*args, **kwargs):
            import time as _time
            client_ip = request.remote_addr or "unknown"
            now = _time.time()
            key = f"{client_ip}:{request.path}"

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
