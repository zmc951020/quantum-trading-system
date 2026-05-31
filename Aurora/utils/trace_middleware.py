"""
全链路trace_id中间件 + 请求上下文追踪

修补项 P1-4：全链路trace_id ✅ 已修补

功能：
- 每个请求自动生成 trace_id
- 支持X-Trace-Id请求头传播
- 注入到Flask g对象
- 日志格式化集成
- 请求耗时统计
"""
import uuid
import time
import logging
import functools
from typing import Optional, Callable
from contextvars import ContextVar

# ContextVar 支持异步上下文传播
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_request_start_var: ContextVar[Optional[float]] = ContextVar("request_start", default=None)

logger = logging.getLogger(__name__)


class TraceContext:
    """全链路追踪上下文"""
    
    trace_id: str
    parent_span_id: Optional[str] = None
    request_path: str = ""
    request_method: str = ""
    user_id: Optional[str] = None
    start_time: float = 0.0
    
    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or self._generate_trace_id()
        self.start_time = time.time()
    
    @staticmethod
    def _generate_trace_id() -> str:
        """生成唯一trace_id: 32位hex"""
        return uuid.uuid4().hex
    
    def get(self) -> "TraceContext":
        """获取当前上下文"""
        return self


def init_trace_middleware(app):
    """
    为Flask应用注册trace中间件
    
    用法:
    from utils.trace_middleware import init_trace_middleware
    init_trace_middleware(app)
    """
    
    @app.before_request
    def before_request():
        """请求前：生成trace_id"""
        from flask import request, g
        
        # 优先使用上游传入的trace_id
        trace_id = request.headers.get("X-Trace-Id") or TraceContext._generate_trace_id()
        short_id = trace_id[:8]  # 短ID用于日志
        
        _trace_id_var.set(trace_id)
        _request_start_var.set(time.time())
        
        ctx = TraceContext(trace_id)
        ctx.request_path = request.path
        ctx.request_method = request.method
        ctx.start_time = time.time()
        
        g.trace_id = trace_id
        g.trace_short = short_id
        g.request_start = ctx.start_time
        
        logger.debug(f"[{short_id}] → {request.method} {request.path}")
    
    @app.after_request
    def after_request(response):
        """请求后：注入trace_id到响应头 + 记录耗时"""
        from flask import g, request
        
        trace_id = getattr(g, 'trace_id', None) or _trace_id_var.get()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        
        start_time = getattr(g, 'request_start', None)
        if start_time:
            elapsed_ms = (time.time() - start_time) * 1000
            response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
            short_id = trace_id[:8] if trace_id else "unknown"
            status = response.status_code
            if status >= 400:
                logger.warning(f"[{short_id}] ← {status} {request.method} {request.path} ({elapsed_ms:.1f}ms)")
            else:
                logger.debug(f"[{short_id}] ← {status} {request.method} {request.path} ({elapsed_ms:.1f}ms)")
        
        return response


def get_trace_id() -> str:
    """获取当前请求的trace_id"""
    tid = _trace_id_var.get()
    if tid:
        return tid
    # 尝试从Flask g获取
    try:
        from flask import g
        return getattr(g, 'trace_id', 'unknown')
    except Exception:
        return 'unknown'


def get_elapsed_ms() -> float:
    """获取当前请求已耗时（毫秒）"""
    start = _request_start_var.get()
    if start:
        return (time.time() - start) * 1000
    return 0.0


class TraceFormatter(logging.Formatter):
    """带trace_id的日志格式化器"""
    
    def format(self, record):
        trace_id = get_trace_id()
        short_id = trace_id[:8] if trace_id != 'unknown' else '--------'
        record.trace_short = short_id
        record.trace_id = trace_id
        return super().format(record)


def setup_trace_logging():
    """配置全局trace日志格式"""
    handler = logging.StreamHandler()
    handler.setFormatter(TraceFormatter(
        '[%(asctime)s] [%(trace_short)s] %(levelname)s %(name)s: %(message)s'
    ))
    logging.getLogger().handlers = [handler]
    logger.info("Trace日志格式已配置")