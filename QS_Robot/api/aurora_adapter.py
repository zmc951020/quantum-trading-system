# -*- coding: utf-8 -*-
"""
Aurora API 适配器
================
将Aurora API响应转换为统一格式，处理认证和会话管理

Aurora API基础地址: http://127.0.0.1:5002

功能:
1. 自动登录Aurora系统并维护会话
2. 调用Aurora API并转换响应格式
3. 支持所有Aurora API端点
4. 请求缓存和批量合并
5. 接口版本兼容
"""

import json
import os
import time
import requests
from typing import Any, Dict, Optional, List, Union
from urllib.parse import urljoin
from .response_formatter import transform_aurora_response

# Aurora API基础地址
AURORA_BASE_URL = os.environ.get('AURORA_BASE_URL', 'http://127.0.0.1:5002')

# 默认登录凭证（从环境变量读取，避免硬编码）
DEFAULT_CREDENTIALS = {
    "username": os.environ.get('AURORA_USERNAME', 'admin'),
    "password": os.environ.get('AURORA_PASSWORD', 'admin123')
}


class AuroraAPIAdapter:
    """Aurora API适配器

    提供统一的Aurora API调用接口，自动处理认证和响应格式化
    """

    def __init__(self, base_url: str = AURORA_BASE_URL, credentials: Dict = None):
        """初始化Aurora API适配器

        Args:
            base_url: Aurora API基础地址
            credentials: 登录凭证
        """
        self.base_url = base_url.rstrip('/')
        self.credentials = credentials or DEFAULT_CREDENTIALS
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self._authenticated = False
        self._session_cookie = None

        # 请求缓存
        self._cache: Dict[str, tuple] = {}  # key -> (response, timestamp, ttl)

        # 批量请求队列
        self._batch_queue: List[tuple] = []  # [(endpoint, params), ...]

    def _get_cache_key(self, method: str, endpoint: str, params: dict = None) -> str:
        """生成缓存键"""
        return f"{method}:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"

    def _is_cache_valid(self, key: str, ttl: int = 60) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        _, timestamp, cache_ttl = self._cache[key]
        return (time.time() - timestamp) < cache_ttl

    def _get_cached(self, key: str) -> Optional[dict]:
        """获取缓存数据"""
        if key in self._cache:
            response, _, _ = self._cache[key]
            return response
        return None

    def _set_cache(self, key: str, response: dict, ttl: int = 60):
        """设置缓存"""
        self._cache[key] = (response, time.time(), ttl)

    def authenticate(self) -> bool:
        """登录Aurora系统并维护会话

        Returns:
            认证是否成功
        """
        if self._authenticated and self._session_cookie:
            # 验证会话是否有效
            try:
                test_response = self.session.get(
                    f"{self.base_url}/api/health",
                    timeout=5
                )
                if test_response.status_code in [200, 401, 403]:
                    return True
            except:
                pass

        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json=self.credentials,
                timeout=10
            )

            if response.status_code == 200:
                # 保存session cookie
                cookie = response.headers.get('Set-Cookie', '')
                if 'session' in cookie.lower() or cookie:
                    self._session_cookie = cookie.split(';')[0]
                    self.session.headers.update({'Cookie': self._session_cookie})
                self._authenticated = True
                return True

            return False

        except Exception as e:
            print(f"[AuroraAPIAdapter] 认证失败: {e}")
            return False

    def call(self, endpoint: str, method: str = "GET",
             params: dict = None, data: dict = None,
             use_cache: bool = True, cache_ttl: int = 60,
             require_auth: bool = True) -> dict:
        """调用Aurora API

        Args:
            endpoint: API端点 (如: /api/strategy-list)
            method: HTTP方法 (GET, POST, PUT, DELETE)
            params: URL参数
            data: 请求体数据
            use_cache: 是否使用缓存
            cache_ttl: 缓存有效期(秒)
            require_auth: 是否需要认证

        Returns:
            统一格式的API响应
        """
        # 生成缓存键
        cache_key = self._get_cache_key(method, endpoint, params or data)

        # 检查缓存 (仅GET请求)
        if use_cache and method == "GET" and self._is_cache_valid(cache_key, cache_ttl):
            return self._get_cached(cache_key)

        # 确保已认证
        if require_auth and not self._authenticated:
            if not self.authenticate():
                return {
                    "success": False,
                    "error": "Aurora认证失败",
                    "aurora_available": False
                }

        url = urljoin(self.base_url, endpoint.lstrip('/'))

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=30)
            elif method == "POST":
                response = self.session.post(url, json=data, params=params, timeout=60)
            elif method == "PUT":
                response = self.session.put(url, json=data, params=params, timeout=30)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, timeout=30)
            else:
                return {"success": False, "error": f"不支持的HTTP方法: {method}"}

            # 处理响应
            if response.status_code == 401 or response.status_code == 403:
                # 会话过期，重新认证
                self._authenticated = False
                if self.authenticate():
                    return self.call(endpoint, method, params, data, use_cache, cache_ttl, require_auth)
                return {"success": False, "error": "认证已过期，请重新登录"}

            # 解析响应
            try:
                result = response.json()
            except:
                result = {"raw": response.text}

            # 转换响应格式
            transformed = transform_aurora_response(result)
            transformed["_raw_status"] = response.status_code

            # 更新会话cookie
            new_cookie = response.headers.get('Set-Cookie', '')
            if new_cookie and ('session' in new_cookie.lower() or 'token' in new_cookie.lower()):
                self._session_cookie = new_cookie.split(';')[0]
                self.session.headers.update({'Cookie': self._session_cookie})

            # 缓存结果
            if use_cache and method == "GET" and response.status_code == 200:
                self._set_cache(cache_key, transformed, cache_ttl)

            return transformed

        except requests.exceptions.Timeout:
            return {"success": False, "error": "请求超时"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "无法连接到Aurora系统", "aurora_available": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get(self, endpoint: str, params: dict = None, **kwargs) -> dict:
        """GET请求快捷方法"""
        return self.call(endpoint, "GET", params=params, **kwargs)

    def post(self, endpoint: str, data: dict = None, **kwargs) -> dict:
        """POST请求快捷方法"""
        return self.call(endpoint, "POST", data=data, **kwargs)

    def put(self, endpoint: str, data: dict = None, **kwargs) -> dict:
        """PUT请求快捷方法"""
        return self.call(endpoint, "PUT", data=data, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> dict:
        """DELETE请求快捷方法"""
        return self.call(endpoint, "DELETE", **kwargs)

    def is_available(self) -> bool:
        """检查Aurora系统是否可用

        Returns:
            Aurora是否可用
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/health",
                timeout=5
            )
            return response.status_code in [200, 401, 403]
        except:
            return False

    def get_strategy_list(self) -> List[dict]:
        """获取策略列表

        Returns:
            策略列表
        """
        result = self.get("/api/strategy-list", cache_ttl=30)
        if result.get("success"):
            return result.get("result", result.get("data", []))
        return []

    def get_strategy_tree(self) -> dict:
        """获取策略分类树

        Returns:
            策略分类树
        """
        result = self.get("/api/strategy/tree", cache_ttl=60)
        if result.get("success"):
            return result.get("result", result.get("data", {}))
        return {}

    def get_risk_status(self) -> dict:
        """获取风控状态

        Returns:
            风控状态
        """
        result = self.get("/api/risk-control/status", cache_ttl=10)
        if result.get("success"):
            return result.get("result", result.get("data", {}))
        return {}

    def get_backtest_result(self, strategy_name: str, backtest_id: str = None) -> dict:
        """获取回测结果

        Args:
            strategy_name: 策略名称
            backtest_id: 回测ID

        Returns:
            回测结果
        """
        params = {"strategy": strategy_name}
        if backtest_id:
            params["backtest_id"] = backtest_id

        result = self.get("/api/backtest/result", params=params, cache_ttl=0)
        if result.get("success"):
            return result.get("result", result.get("data", {}))
        return {}

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    def close(self):
        """关闭会话"""
        self.session.close()


# 全局单例
_aurora_adapter: Optional[AuroraAPIAdapter] = None

def get_aurora_adapter() -> AuroraAPIAdapter:
    """获取全局Aurora API适配器单例

    Returns:
        AuroraAPIAdapter实例
    """
    global _aurora_adapter
    if _aurora_adapter is None:
        _aurora_adapter = AuroraAPIAdapter()
    return _aurora_adapter
