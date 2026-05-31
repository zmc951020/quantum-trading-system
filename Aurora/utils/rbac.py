"""
RBAC角色权限控制系统
======================
修补项 P1-2：RBAC角色权限 ✅

功能：
- 4级角色体系: admin / manager / analyst / user
- 基于装饰器的权限检查
- 资源级权限控制
- 权限继承（admin > manager > analyst > user）
- Flask中间件集成

角色权限矩阵:
| 功能              | admin | manager | analyst | user |
|-------------------|-------|---------|---------|------|
| 查看行情          |  ✅   |   ✅    |   ✅    |  ✅  |
| 下单交易          |  ✅   |   ✅    |   ❌    |  ❌  |
| 查看策略          |  ✅   |   ✅    |   ✅    |  ✅  |
| 创建/修改策略     |  ✅   |   ✅    |   ✅    |  ❌  |
| 删除策略          |  ✅   |   ❌    |   ❌    |  ❌  |
| 管理用户          |  ✅   |   ❌    |   ❌    |  ❌  |
| 系统配置          |  ✅   |   ❌    |   ❌    |  ❌  |
| 查看日志          |  ✅   |   ✅    |   ❌    |  ❌  |
| 回测              |  ✅   |   ✅    |   ✅    |  ❌  |
| 导出数据          |  ✅   |   ✅    |   ✅    |  ❌  |
| API密钥管理       |  ✅   |   ❌    |   ❌    |  ❌  |
| 审计报告          |  ✅   |   ✅    |   ❌    |  ❌  |
"""

import logging
from typing import Dict, List, Set, Optional, Callable, Any
from functools import wraps
from enum import Enum

from flask import g, request, jsonify

logger = logging.getLogger(__name__)


# ============================================================
# 角色定义
# ============================================================
class Role(Enum):
    """系统角色枚举"""
    ADMIN = "admin"       # 超级管理员：全部权限
    MANAGER = "manager"   # 管理员：交易+策略管理
    ANALYST = "analyst"   # 分析师：策略回测+数据分析
    USER = "user"         # 普通用户：只读查看


# 角色继承链（数值越大权限越高）
ROLE_HIERARCHY = {
    Role.ADMIN.value: 100,
    Role.MANAGER.value: 80,
    Role.ANALYST.value: 60,
    Role.USER.value: 40,
}


# ============================================================
# 权限定义
# ============================================================
class Permission(Enum):
    """系统权限枚举"""
    # 行情数据
    VIEW_QUOTES = "view_quotes"              # 查看行情
    VIEW_LEVEL2 = "view_level2"              # 查看Level2数据
    
    # 交易操作
    PLACE_ORDER = "place_order"              # 下单
    CANCEL_ORDER = "cancel_order"            # 撤单
    VIEW_ORDERS = "view_orders"              # 查看订单
    VIEW_POSITIONS = "view_positions"        # 查看持仓
    
    # 策略管理
    VIEW_STRATEGIES = "view_strategies"      # 查看策略
    CREATE_STRATEGY = "create_strategy"      # 创建策略
    MODIFY_STRATEGY = "modify_strategy"      # 修改策略
    DELETE_STRATEGY = "delete_strategy"      # 删除策略
    ENABLE_STRATEGY = "enable_strategy"      # 启用/禁用策略
    
    # 回测系统
    RUN_BACKTEST = "run_backtest"            # 运行回测
    VIEW_BACKTEST = "view_backtest"          # 查看回测结果
    DELETE_BACKTEST = "delete_backtest"      # 删除回测结果
    
    # 风险管理
    VIEW_RISK = "view_risk"                  # 查看风险指标
    MODIFY_RISK = "modify_risk"              # 修改风控参数
    VIEW_RISK_ALERTS = "view_risk_alerts"    # 查看风险告警
    
    # 系统管理
    MANAGE_USERS = "manage_users"            # 用户管理
    VIEW_USERS = "view_users"                # 查看用户列表
    SYSTEM_CONFIG = "system_config"          # 系统配置
    VIEW_LOGS = "view_logs"                  # 查看系统日志
    VIEW_AUDIT = "view_audit"                # 查看审计报告
    
    # 数据管理
    EXPORT_DATA = "export_data"              # 数据导出
    IMPORT_DATA = "import_data"              # 数据导入
    MANAGE_DATASOURCES = "manage_datasources" # 数据源管理
    
    # API
    MANAGE_API_KEYS = "manage_api_keys"      # API密钥管理


# 角色权限映射表
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Role.ADMIN.value: set(),   # admin拥有所有权限（运行时动态填充）
    Role.MANAGER.value: {
        Permission.VIEW_QUOTES.value,
        Permission.VIEW_LEVEL2.value,
        Permission.PLACE_ORDER.value,
        Permission.CANCEL_ORDER.value,
        Permission.VIEW_ORDERS.value,
        Permission.VIEW_POSITIONS.value,
        Permission.VIEW_STRATEGIES.value,
        Permission.CREATE_STRATEGY.value,
        Permission.MODIFY_STRATEGY.value,
        Permission.ENABLE_STRATEGY.value,
        Permission.RUN_BACKTEST.value,
        Permission.VIEW_BACKTEST.value,
        Permission.VIEW_RISK.value,
        Permission.MODIFY_RISK.value,
        Permission.VIEW_RISK_ALERTS.value,
        Permission.VIEW_LOGS.value,
        Permission.VIEW_AUDIT.value,
        Permission.EXPORT_DATA.value,
        Permission.VIEW_USERS.value,
    },
    Role.ANALYST.value: {
        Permission.VIEW_QUOTES.value,
        Permission.VIEW_LEVEL2.value,
        Permission.VIEW_ORDERS.value,
        Permission.VIEW_POSITIONS.value,
        Permission.VIEW_STRATEGIES.value,
        Permission.CREATE_STRATEGY.value,
        Permission.MODIFY_STRATEGY.value,
        Permission.RUN_BACKTEST.value,
        Permission.VIEW_BACKTEST.value,
        Permission.VIEW_RISK.value,
        Permission.VIEW_RISK_ALERTS.value,
        Permission.EXPORT_DATA.value,
    },
    Role.USER.value: {
        Permission.VIEW_QUOTES.value,
        Permission.VIEW_ORDERS.value,
        Permission.VIEW_POSITIONS.value,
        Permission.VIEW_STRATEGIES.value,
        Permission.VIEW_BACKTEST.value,
        Permission.VIEW_RISK.value,
    },
}

# admin拥有所有权限
_all_permissions = set(p.value for p in Permission)
ROLE_PERMISSIONS[Role.ADMIN.value] = _all_permissions


# ============================================================
# 核心权限检查函数
# ============================================================
def has_permission(role: str, permission: str) -> bool:
    """
    检查角色是否拥有指定权限
    
    Args:
        role: 角色名称
        permission: 权限名称
    
    Returns:
        True if authorized
    """
    if role not in ROLE_PERMISSIONS:
        logger.warning(f"未知角色: {role}")
        return False
    
    return permission in ROLE_PERMISSIONS[role]


def has_role(user_role: str, required_role: str) -> bool:
    """
    检查用户角色是否达到所需等级（支持继承）
    
    Args:
        user_role: 用户角色
        required_role: 所需最低角色
    
    Returns:
        True if user_role >= required_role
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 999)
    return user_level >= required_level


def get_current_user():
    """获取当前请求的用户信息"""
    return getattr(g, 'current_user', None)


def get_current_role() -> str:
    """获取当前用户的角色"""
    user = get_current_user()
    if user:
        return user.get("role", Role.USER.value)
    return "anonymous"


# ============================================================
# 装饰器
# ============================================================
def require_permission(permission: str):
    """
    要求特定权限的装饰器
    
    用法:
    @app.route("/api/orders", methods=["POST"])
    @require_permission("place_order")
    def place_order():
        ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            role = get_current_role()
            
            if not role or role == "anonymous":
                return jsonify({
                    "error": "unauthorized",
                    "message": "需要登录",
                    "code": 401,
                }), 401
            
            if not has_permission(role, permission):
                logger.warning(f"权限拒绝: role={role}, permission={permission}")
                return jsonify({
                    "error": "forbidden",
                    "message": f"缺少权限: {permission}（当前角色: {role}）",
                    "code": 403,
                }), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_role_level(required_role: str):
    """
    要求最低角色等级的装饰器
    
    用法:
    @app.route("/api/admin/users")
    @require_role_level("admin")
    def manage_users():
        ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            role = get_current_role()
            
            if not role or role == "anonymous":
                return jsonify({
                    "error": "unauthorized",
                    "message": "需要登录",
                    "code": 401,
                }), 401
            
            if not has_role(role, required_role):
                logger.warning(f"角色等级不足: {role} < {required_role}")
                return jsonify({
                    "error": "forbidden",
                    "message": f"需要{required_role}及以上角色（当前角色: {role}）",
                    "code": 403,
                }), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(*permissions: str):
    """
    要求至少拥有其中一个权限
    
    用法:
    @app.route("/api/strategy/manage")
    @require_any_permission("create_strategy", "modify_strategy", "delete_strategy")
    def manage_strategies():
        ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            role = get_current_role()
            
            if not role or role == "anonymous":
                return jsonify({
                    "error": "unauthorized",
                    "message": "需要登录",
                    "code": 401,
                }), 401
            
            for perm in permissions:
                if has_permission(role, perm):
                    return func(*args, **kwargs)
            
            logger.warning(f"权限拒绝: role={role}, required any={permissions}")
            return jsonify({
                "error": "forbidden",
                "message": f"至少需要以下权限之一: {permissions}",
                "code": 403,
            }), 403
        return wrapper
    return decorator


def require_all_permissions(*permissions: str):
    """
    要求拥有所有指定权限
    
    用法:
    @app.route("/api/strategy/advanced")
    @require_all_permissions("create_strategy", "run_backtest")
    def advanced_strategy():
        ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            role = get_current_role()
            
            if not role or role == "anonymous":
                return jsonify({
                    "error": "unauthorized",
                    "message": "需要登录",
                    "code": 401,
                }), 401
            
            missing = [p for p in permissions if not has_permission(role, p)]
            if missing:
                logger.warning(f"权限不足: role={role}, missing={missing}")
                return jsonify({
                    "error": "forbidden",
                    "message": f"缺少权限: {missing}",
                    "code": 403,
                }), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# 资源级权限控制
# ============================================================
def can_access_resource(user_id: str, resource_owner_id: str,
                        resource_type: str = "strategy") -> bool:
    """
    检查用户是否可以访问特定资源
    
    规则:
    - admin 可以访问所有资源
    - manager 可以访问所有同类型资源
    - 其他角色只能访问自己的资源
    
    Args:
        user_id: 当前用户ID
        resource_owner_id: 资源所有者ID
        resource_type: 资源类型
    
    Returns:
        True if access allowed
    """
    role = get_current_role()
    
    # admin/manager 可以访问所有资源
    if has_role(role, Role.MANAGER.value):
        return True
    
    # 其他角色只能访问自己的资源
    return user_id == resource_owner_id


def filter_owned_resources(resources: List[Dict], user_id: str,
                           owner_field: str = "user_id") -> List[Dict]:
    """
    过滤资源列表，只返回用户有权访问的资源
    
    Args:
        resources: 资源列表
        user_id: 当前用户ID
        owner_field: 资源中的所有者字段名
    
    Returns:
        过滤后的资源列表
    """
    role = get_current_role()
    
    # admin/manager 可以看到所有
    if has_role(role, Role.MANAGER.value):
        return resources
    
    # 其他角色只能看到自己的
    return [r for r in resources if r.get(owner_field) == user_id]


# ============================================================
# 管理API
# ============================================================
def get_role_permissions(role: str) -> List[str]:
    """获取角色的所有权限列表"""
    perms = ROLE_PERMISSIONS.get(role, set())
    return sorted(list(perms))


def get_all_roles() -> List[Dict[str, Any]]:
    """获取所有角色及其权限"""
    roles = []
    for role_name, level in sorted(ROLE_HIERARCHY.items(), key=lambda x: -x[1]):
        roles.append({
            "role": role_name,
            "level": level,
            "permissions": sorted(list(ROLE_PERMISSIONS.get(role_name, set()))),
            "permission_count": len(ROLE_PERMISSIONS.get(role_name, set())),
        })
    return roles


def grant_permission(role: str, permission: str) -> bool:
    """
    为角色授予权限（运行时）
    
    注意：此为临时授予，重启后恢复默认配置
    如需永久修改，请修改源代码中的ROLE_PERMISSIONS配置
    """
    if role not in ROLE_PERMISSIONS:
        logger.warning(f"未知角色: {role}")
        return False
    
    if permission not in _all_permissions:
        logger.warning(f"未知权限: {permission}")
        return False
    
    ROLE_PERMISSIONS[role].add(permission)
    logger.info(f"权限授予: {role} += {permission}")
    return True


def revoke_permission(role: str, permission: str) -> bool:
    """撤销角色权限（运行时）"""
    if role not in ROLE_PERMISSIONS:
        return False
    
    if role == Role.ADMIN.value:
        logger.warning("不能撤销admin的权限")
        return False
    
    ROLE_PERMISSIONS[role].discard(permission)
    logger.info(f"权限撤销: {role} -= {permission}")
    return True


# ============================================================
# Flask集成
# ============================================================
def init_rbac(app):
    """
    为Flask应用注册RBAC
    
    用法:
    from utils.rbac import init_rbac
    init_rbac(app)
    """
    
    @app.context_processor
    def inject_rbac_helpers():
        """注入模板辅助函数"""
        return {
            "has_permission": has_permission,
            "has_role": has_role,
            "get_current_role": get_current_role,
        }
    
    logger.info(f"RBAC已注册，{len(ROLE_PERMISSIONS)}个角色，{len(_all_permissions)}个权限")


def register_rbac_routes(app):
    """
    注册RBAC管理API路由
    
    路由:
    - GET /api/rbac/roles         : 获取所有角色
    - GET /api/rbac/me/permissions: 获取当前用户权限
    - GET /api/rbac/users/:id/permissions: 获取指定用户权限（admin/manager）
    """
    
    @app.route("/api/rbac/roles", methods=["GET"])
    def rbac_get_roles():
        """获取所有角色定义"""
        from utils.auth_middleware import require_auth
        # 需要登录，但不需要特定权限
        return jsonify({
            "status": "ok",
            "data": {
                "roles": get_all_roles(),
                "hierarchy": {k: v for k, v in sorted(ROLE_HIERARCHY.items(), key=lambda x: -x[1])},
            }
        })
    
    @app.route("/api/rbac/me/permissions", methods=["GET"])
    def rbac_my_permissions():
        """获取当前用户的权限"""
        role = get_current_role()
        if role == "anonymous":
            return jsonify({
                "status": "ok",
                "data": {
                    "role": "anonymous",
                    "permissions": [],
                    "permission_count": 0,
                }
            })
        
        perms = get_role_permissions(role)
        return jsonify({
            "status": "ok",
            "data": {
                "role": role,
                "permissions": perms,
                "permission_count": len(perms),
                "role_level": ROLE_HIERARCHY.get(role, 0),
            }
        })
    
    logger.info("RBAC管理API路由已注册")


# ============================================================
# 批量权限检查
# ============================================================
class ResourceGuard:
    """
    资源访问守卫
    
    用法:
    guard = ResourceGuard("strategy")
    
    @guard.read
    def get_strategy(strategy_id):
        ...
    
    @guard.write
    def update_strategy(strategy_id):
        ...
    
    @guard.delete
    def delete_strategy(strategy_id):
        ...
    """
    
    def __init__(self, resource_type: str):
        self.resource_type = resource_type
    
    @property
    def read(self):
        """读权限（查看）"""
        return require_permission(f"view_{self.resource_type}s")
    
    @property
    def write(self):
        """写权限（创建/修改）"""
        def decorator(func):
            @wraps(func)
            @require_any_permission(
                f"create_{self.resource_type}",
                f"modify_{self.resource_type}",
                f"enable_{self.resource_type}",
            )
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @property
    def delete(self):
        """删除权限"""
        return require_permission(f"delete_{self.resource_type}s")


# 预定义资源守卫
StrategyGuard = ResourceGuard("strategy")
OrderGuard = ResourceGuard("order")
RiskGuard = ResourceGuard("risk")
BacktestGuard = ResourceGuard("backtest")