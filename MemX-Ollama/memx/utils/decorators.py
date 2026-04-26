import asyncio
import time
import logging
from typing import Callable, Optional, TypeVar
from functools import wraps

T = TypeVar('T')
logger = logging.getLogger(__name__)

def idempotent(func: Callable) -> Callable:
    cache = {}
    
    # 检查是否是异步函数
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 从参数中获取request_id
            request_id = kwargs.get('request_id')
            if not request_id and args:
                request_id = args[0]
            
            if request_id and request_id in cache:
                logger.info(f"幂等命中，请求ID{request_id}，直接返回缓存结果")
                return cache[request_id]
            
            result = await func(*args, **kwargs)
            if request_id:
                cache[request_id] = result
                # 使用异步方式清理缓存
                async def cleanup():
                    await asyncio.sleep(3600)  # 1小时后清理
                    if request_id in cache:
                        del cache[request_id]
                asyncio.create_task(cleanup())
            return result
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 从参数中获取request_id
            request_id = kwargs.get('request_id')
            if not request_id and args:
                request_id = args[0]
            
            if request_id and request_id in cache:
                logger.info(f"幂等命中，请求ID{request_id}，直接返回缓存结果")
                return cache[request_id]
            
            result = func(*args, **kwargs)
            if request_id:
                cache[request_id] = result
                # 使用线程清理缓存
                import threading
                def cleanup():
                    time.sleep(3600)  # 1小时后清理
                    if request_id in cache:
                        del cache[request_id]
                threading.Thread(target=cleanup, daemon=True).start()
            return result
        return sync_wrapper

def circuit_breaker(failure_threshold: int = 5, timeout: int = 60):
    def decorator(func: Callable) -> Callable:
        failure_count = 0
        last_failure_time = 0
        is_open = False
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal failure_count, last_failure_time, is_open
            if is_open:
                if time.time() - last_failure_time > timeout:
                    is_open = False
                    failure_count = 0
                else:
                    logger.warning(f"熔断器触发，函数{func.__name__}降级处理")
                    return func.__defaults__[0] if func.__defaults__ else None
            try:
                result = func(*args, **kwargs)
                failure_count = 0
                return result
            except Exception as e:
                failure_count += 1
                last_failure_time = time.time()
                if failure_count >= failure_threshold:
                    is_open = True
                    logger.error(f"熔断器触发，函数{func.__name__}失败次数超过阈值，熔断{timeout}s")
                raise e
        return wrapper
    return decorator

def validate_input(text: str, max_length: int = 10000) -> str:
    if not text or not text.strip():
        raise ValueError("输入不能为空")
    text = text.strip()
    if len(text) > max_length:
        logger.warning(f"输入超长，截断为{max_length}字符")
        text = text[:max_length]
    return text

def clamp_priority(priority: float) -> float:
    return max(0.0, min(1.0, priority))
