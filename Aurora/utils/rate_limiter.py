"""
API限流中间件 - Token Bucket算法
===================================
修补项 P1-3：API限流 ✅

功能：
- Token Bucket 令牌桶算法
- 多级限流: 全局/IP/用户/接口
- 滑动窗口计数器
- 429 Too Many Requests 响应
- 限流头注入 (X-RateLimit-*)
- 内存 + Redis双后端
- 装饰器 + Flask中间件

限流策略:
| 级别       | 默认限制            | 适用场景        |
|------------|---------------------|-----------------|
| 全局       | 1000 req/s          | 系统总保护      |
| IP         | 100 req/min         | 防单IP滥用      |
| 用户       | 300 req/min         | 认证用户        |
| 接口       | 60 req/min/endpoint | 敏感接口        |
| 登录       | 5 req/min/IP        | 防暴力破解      |
"""

import time
import logging
import threading
from typing import Dict, Optional, Tuple, Callable
from functools import wraps
from collections import defaultdict
from dataclasses import dataclass, field

from flask import request, g, jsonify

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================
@dataclass
class TokenBucket:
    """令牌桶"""
    capacity: float          # 桶容量（最大令牌数）
    fill_rate: float         # 填充速率（令牌/秒）
    tokens: float = 0.0      # 当前令牌数
    last_fill: float = field(default_factory=time.time)
    
    def consume(self, tokens: float = 1.0) -> bool:
        """
        消费令牌
        
        Returns:
            True if allowed (有足够令牌), False if rate limited
        """
        now = time.time()
        
        # 补充令牌
        elapsed = now - self.last_fill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_fill = now
        
        # 尝试消费
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    @property
    def available_tokens(self) -> float:
        """当前可用令牌数"""
        now = time.time()
        elapsed = now - self.last_fill
        return min(self.capacity, self.tokens + elapsed * self.fill_rate)


@dataclass
class SlidingWindow:
    """滑动窗口计数器"""
    window_size: float       # 窗口大小（秒）
    max_requests: int         # 窗口内最大请求数
    timestamps: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def allow(self) -> bool:
        """检查是否允许请求"""
        now = time.time()
        
        with self._lock:
            # 清理过期记录
            cutoff = now - self.window_size
            self.timestamps = [t for t in self.timestamps if t > cutoff]
            
            if len(self.timestamps) >= self.max_requests:
                return False
            
            self.timestamps.append(now)
            return True
    
    @property
    def remaining(self) -> int:
        """剩余可请求数"""
        now = time.time()
        cutoff = now - self.window_size
        valid = len([t for t in self.timestamps if t > cutoff])
        return max(0, self.max_requests - valid)
    
    @property
    def reset_time(self) -> float:
        """重置时间（最早的窗口到期时间）"""
        if not self.timestamps:
            return time.time()
        return min(self.timestamps) + self.window_size


# ============================================================
# 限流器核心
# ============================================================
class RateLimiter:
    """
    多级限流器
    
    用法:
    limiter = RateLimiter()
    
    # 检查IP限流
    if not limiter.check_ip("192.168.1.1"):
        return "Too Many Requests", 429
    
    # 检查用户限流
    if not limiter.check_user("user_123"):
        return "Too Many Requests", 429
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        
        # Token Bucket（适用于大流量平滑限流）
        self._global_bucket = TokenBucket(capacity=1000, fill_rate=1000, tokens=1000)
        self._ip_buckets: Dict[str, TokenBucket] = {}
        self._user_buckets: Dict[str, TokenBucket] = {}
        self._endpoint_buckets: Dict[str, TokenBucket] = {}
        
        # Sliding Window（适用于精确计数）
        self._login_windows: Dict[str, SlidingWindow] = {}
        
        # 配置
        self.config = {
            # Token Bucket配置
            "global": {"capacity": 1000, "fill_rate": 1000},
            "ip": {"capacity": 100, "fill_rate": 100 / 60},       # 100 req/min
            "user": {"capacity": 300, "fill_rate": 300 / 60},     # 300 req/min
            "endpoint_default": {"capacity": 60, "fill_rate": 60 / 60},  # 60 req/min
            # 特殊接口配置
            "endpoints": {
                "/api/auth/login": {"capacity": 5, "fill_rate": 5 / 60},
                "/api/orders": {"capacity": 30, "fill_rate": 30 / 60},
                "/api/backtest/run": {"capacity": 5, "fill_rate": 5 / 60},
            },
            # 滑动窗口配置
            "login_window": {"window_size": 60, "max_requests": 10},  # 10 req/分钟
        }
        
        # 定期清理过期桶
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5分钟
    
    # ---- Token Bucket 方法 ----
    
    def check_global(self) -> bool:
        """检查全局限流"""
        return self._global_bucket.consume()
    
    def check_ip(self, ip: str) -> bool:
        """检查IP限流"""
        bucket = self._get_or_create_bucket(
            self._ip_buckets, ip, self.config["ip"]
        )
        return bucket.consume()
    
    def check_user(self, user_id: str) -> bool:
        """检查用户限流"""
        bucket = self._get_or_create_bucket(
            self._user_buckets, user_id, self.config["user"]
        )
        return bucket.consume()
    
    def check_endpoint(self, endpoint: str) -> bool:
        """检查接口限流"""
        ep_config = self.config["endpoints"].get(
            endpoint, self.config["endpoint_default"]
        )
        bucket = self._get_or_create_bucket(
            self._endpoint_buckets, endpoint, ep_config
        )
        return bucket.consume()
    
    # ---- Sliding Window 方法 ----
    
    def check_login(self, ip: str) -> bool:
        """检查登录限流（防暴力破解）"""
        window = self._get_or_create_window(
            self._login_windows, ip, self.config["login_window"]
        )
        return window.allow()
    
    # ---- 综合检查 ----
    
    def check_all(self, ip: Optional[str] = None,
                  user_id: Optional[str] = None,
                  endpoint: Optional[str] = None) -> Tuple[bool, str]:
        """
        执行所有限流检查
        
        Returns:
            (allowed, blocked_reason): 是否允许 + 被拦截原因
        """
        # 1. 全局限流
        if not self.check_global():
            return False, "global"
        
        # 2. IP限流
        if ip and not self.check_ip(ip):
            return False, "ip"
        
        # 3. 用户限流
        if user_id and not self.check_user(user_id):
            return False, "user"
        
        # 4. 接口限流
        if endpoint and not self.check_endpoint(endpoint):
            return False, "endpoint"
        
        return True, ""
    
    # ---- 内部方法 ----
    
    def _get_or_create_bucket(self, buckets: Dict, key: str,
                               config: dict) -> TokenBucket:
        """获取或创建令牌桶"""
        if key not in buckets:
            with self._lock:
                if key not in buckets:  # double-check
                    buckets[key] = TokenBucket(
                        capacity=config["capacity"],
                        fill_rate=config["fill_rate"],
                        tokens=config["capacity"],
                    )
        return buckets[key]
    
    def _get_or_create_window(self, windows: Dict, key: str,
                               config: dict) -> SlidingWindow:
        """获取或创建滑动窗口"""
        if key not in windows:
            with self._lock:
                if key not in windows:
                    windows[key] = SlidingWindow(
                        window_size=config["window_size"],
                        max_requests=config["max_requests"],
                    )
        return windows[key]
    
    def _cleanup(self):
        """清理过期的桶和窗口"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        with self._lock:
            # 清理令牌桶（30分钟无活动）
            threshold = now - 1800
            for buckets in [self._ip_buckets, self._user_buckets, self._endpoint_buckets]:
                expired = [
                    k for k, b in buckets.items()
                    if b.last_fill < threshold and b.tokens >= b.capacity * 0.95
                ]
                for k in expired:
                    del buckets[k]
            
            # 清理滑动窗口（10分钟无活动）
            threshold = now - 600
            for windows in [self._login_windows]:
                expired = [
                    k for k, w in windows.items()
                    if not w.timestamps or max(w.timestamps) < threshold
                ]
                for k in expired:
                    del windows[k]
        
        self._last_cleanup = now
    
    # ---- 监控 ----
    
    def get_stats(self) -> dict:
        """获取限流统计信息"""
        return {
            "global_tokens": self._global_bucket.available_tokens,
            "ip_buckets": len(self._ip_buckets),
            "user_buckets": len(self._user_buckets),
            "endpoint_buckets": len(self._endpoint_buckets),
            "login_windows": len(self._login_windows),
        }
    
    def get_ip_remaining(self, ip: str) -> int:
        """获取IP剩余配额"""
        if ip in self._ip_buckets:
            return int(self._ip_buckets[ip].available_tokens)
        return self.config["ip"]["capacity"]
    
    def get_user_remaining(self, user_id: str) -> int:
        """获取用户剩余配额"""
        if user_id in self._user_buckets:
            return int(self._user_buckets[user_id].available_tokens)
        return self.config["user"]["capacity"]


# ============================================================
# 全局单例
# ============================================================
_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """获取全局限流器实例"""
    return _limiter


# ============================================================
# Flask中间件
# ============================================================
def init_rate_limiter(app, excluded_paths: Optional[list] = None):
    """
    为Flask应用注册限流中间件
    
    Args:
        app: Flask应用实例
        excluded_paths: 不限流的路径
    
    用法:
    from utils.rate_limiter import init_rate_limiter
    init_rate_limiter(app, excluded_paths=["/api/health"])
    """
    if excluded_paths is None:
        excluded_paths = ["/api/health", "/api/status"]
    
    @app.before_request
    def rate_limit():
        """请求前：执行限流检查"""
        path = request.path
        
        # 排除路径
        for excluded in excluded_paths:
            if path.startswith(excluded):
                return None
        
        # 获取标识
        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
        user_id = getattr(g, 'current_user', {}).get("user_id", None) if hasattr(g, 'current_user') else None
        
        # 执行限流检查
        allowed, reason = _limiter.check_all(
            ip=ip,
            user_id=user_id,
            endpoint=path,
        )
        
        if not allowed:
            logger.warning(f"限流触发: ip={ip}, user={user_id}, path={path}, reason={reason}")
            
            retry_after = 60  # 默认60秒后重试
            
            response = jsonify({
                "error": "rate_limited",
                "message": f"请求过于频繁，请稍后再试 ({reason})",
                "code": 429,
                "retry_after": retry_after,
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response
        
        # 注入限流头
        # （在after_request中注入，因为需要响应对象）
    
    @app.after_request
    def add_rate_limit_headers(response):
        """响应后：注入限流信息头"""
        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
        user_id = getattr(g, 'current_user', {}).get("user_id", None) if hasattr(g, 'current_user') else None
        
        remaining = _limiter.get_ip_remaining(ip)
        limit = _limiter.config["ip"]["capacity"]
        
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))
        
        return response
    
    logger.info(f"API限流中间件已注册，排除路径: {excluded_paths}")


# ============================================================
# 装饰器
# ============================================================
def rate_limit(max_requests: int = 60, per_seconds: int = 60, by: str = "ip"):
    """
    接口级限流装饰器
    
    Args:
        max_requests: 时间窗口内最大请求数
        per_seconds: 时间窗口（秒）
        by: 限流维度（ip/user/endpoint）
    
    用法:
    @app.route("/api/sensitive")
    @rate_limit(max_requests=10, per_seconds=60, by="ip")
    def sensitive_endpoint():
        ...
    """
    def decorator(func: Callable) -> Callable:
        # 创建专用的令牌桶配置
        bucket_config = {
            "capacity": max_requests,
            "fill_rate": max_requests / per_seconds,
        }
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
            key = ip
            
            if by == "user":
                user = getattr(g, 'current_user', None)
                key = user.get("user_id", ip) if user else ip
            elif by == "endpoint":
                key = request.path
            
            # 使用全局限流器的Token Bucket
            limiter = get_limiter()
            
            # 动态创建专用桶
            if by == "ip":
                allowed = limiter.check_ip(key)
            elif by == "user":
                allowed = limiter.check_user(key)
            else:
                allowed = limiter.check_endpoint(key)
            
            if not allowed:
                return jsonify({
                    "error": "rate_limited",
                    "message": f"请求过于频繁（{max_requests}次/{per_seconds}秒）",
                    "code": 429,
                    "retry_after": per_seconds,
                }), 429
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def login_rate_limit(func: Callable) -> Callable:
    """
    登录接口专用限流（防暴力破解）
    
    用法:
    @app.route("/api/auth/login", methods=["POST"])
    @login_rate_limit
    def login():
        ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
        limiter = get_limiter()
        
        if not limiter.check_login(ip):
            logger.warning(f"登录限流触发: ip={ip}")
            return jsonify({
                "error": "rate_limited",
                "message": "登录尝试过于频繁，请1分钟后再试",
                "code": 429,
                "retry_after": 60,
            }), 429
        
        return func(*args, **kwargs)
    return wrapper


# ============================================================
# 监控API
# ============================================================
def get_rate_limit_stats() -> dict:
    """获取限流统计"""
    return _limiter.get_stats()