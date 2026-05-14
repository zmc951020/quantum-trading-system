"""
ML模块初始化文件
提供机器学习管理器的统一入口
"""

from .ml_manager import MLManager

# 全局ML管理器实例
_ml_manager = None

def get_ml_manager():
    """
    获取全局ML管理器实例
    
    Returns:
        MLManager: 机器学习管理器实例
    """
    global _ml_manager
    if _ml_manager is None:
        _ml_manager = MLManager()
    return _ml_manager

__all__ = ['get_ml_manager', 'MLManager']
