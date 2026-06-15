# -*- coding: utf-8 -*-
"""
统一API响应格式化
================
提供标准化的API响应格式，确保前端接收一致的数据结构

响应格式:
    {
        "success": True/False,
        "code": 200,
        "message": "操作成功",
        "data": {...},
        "timestamp": "2026-06-12T10:30:00"
    }
"""

from datetime import datetime
from typing import Any, Optional, List, Dict

class APIResponse:
    """统一API响应格式化类"""

    @staticmethod
    def success(data: Any = None, message: str = "操作成功") -> dict:
        """成功响应

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            标准成功响应字典
        """
        return {
            "success": True,
            "code": 200,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def error(message: str, code: int = 500, details: Any = None) -> dict:
        """错误响应

        Args:
            message: 错误消息
            code: 错误码
            details: 错误详情

        Returns:
            标准错误响应字典
        """
        return {
            "success": False,
            "code": code,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def paginated(items: List, total: int, page: int = 1, page_size: int = 20) -> dict:
        """分页响应

        Args:
            items: 数据项列表
            total: 总数
            page: 当前页
            page_size: 每页数量

        Returns:
            标准分页响应字典
        """
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": {
                "items": items,
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            },
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def created(data: Any = None, message: str = "创建成功") -> dict:
        """创建成功响应

        Args:
            data: 创建的数据
            message: 成功消息

        Returns:
            标准创建响应字典
        """
        return {
            "success": True,
            "code": 201,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def no_content(message: str = "操作成功，无返回数据") -> dict:
        """无内容响应

        Args:
            message: 消息

        Returns:
            标准无内容响应字典
        """
        return {
            "success": True,
            "code": 204,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def not_found(resource: str = "资源") -> dict:
        """资源不存在响应

        Args:
            resource: 资源类型

        Returns:
            标准404响应字典
        """
        return {
            "success": False,
            "code": 404,
            "message": f"{resource}不存在",
            "details": None,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def unauthorized(message: str = "未授权") -> dict:
        """未授权响应

        Args:
            message: 错误消息

        Returns:
            标准401响应字典
        """
        return {
            "success": False,
            "code": 401,
            "message": message,
            "details": "请先登录",
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def forbidden(message: str = "禁止访问") -> dict:
        """禁止访问响应

        Args:
            message: 错误消息

        Returns:
            标准403响应字典
        """
        return {
            "success": False,
            "code": 403,
            "message": message,
            "details": "权限不足",
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def validation_error(errors: List[Dict[str, str]]) -> dict:
        """验证错误响应

        Args:
            errors: 错误列表

        Returns:
            标准验证错误响应字典
        """
        return {
            "success": False,
            "code": 422,
            "message": "参数验证失败",
            "details": {"errors": errors},
            "timestamp": datetime.now().isoformat()
        }


def transform_aurora_response(response) -> dict:
    """转换Aurora API响应格式为统一格式

    Aurora返回格式: {"success": true, "data": {...}}
    统一格式:       {"success": true, "data": {...}}

    字段映射（仅映射业务字段，不再映射data->result以避免嵌套）:
        - total_return_pct → total_return
        - win_rate → winRate
        - sharpe_ratio → sharpe
        - max_drawdown_pct → max_drawdown
        - total_trades → trades

    Args:
        response: Aurora原始响应 (可能是dict或list)

    Returns:
        转换后的统一格式响应
    """
    # 处理空响应
    if not response:
        return {"success": False, "error": "Empty response"}

    # 处理list类型响应（如策略列表）
    if isinstance(response, list):
        return {
            "success": True,
            "data": response
        }

    # 处理dict类型响应
    if not isinstance(response, dict):
        return {"success": True, "data": response}

    # 字段映射表（不再映射 data -> result，避免双层嵌套）
    FIELD_MAPPING = {
        "total_return_pct": "total_return",
        "win_rate": "winRate",
        "sharpe_ratio": "sharpe",
        "max_drawdown_pct": "max_drawdown",
        "total_trades": "trades",
    }

    def transform_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {FIELD_MAPPING.get(k, k): transform_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [transform_value(item) for item in value]
        else:
            return value

    result = {}
    for key, value in response.items():
        new_key = FIELD_MAPPING.get(key, key)
        result[new_key] = transform_value(value)

    # 确保success字段存在
    if "success" not in result:
        result["success"] = True

    return result
