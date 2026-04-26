import threading
from typing import Optional, Dict, Any

# 线程本地存储，传递任务上下文
_local = threading.local()

def get_current_task() -> Optional[Dict[str, Any]]:
    """获取当前线程的任务上下文"""
    return getattr(_local, "current_task", None)

def set_current_task(task: Dict[str, Any]):
    """设置当前线程的任务上下文"""
    setattr(_local, "current_task", task)

def clear_current_task():
    """清除任务上下文"""
    if hasattr(_local, "current_task"):
        delattr(_local, "current_task")
