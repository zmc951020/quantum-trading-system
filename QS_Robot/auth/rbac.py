"""RBAC角色权限控制"""
from typing import Dict, List, Set

_ROLES: Dict[str, Set[str]] = {
    "admin": {"read", "write", "delete", "trade", "admin", "system"},
    "trader": {"read", "write", "trade"},
    "analyst": {"read", "write"},
    "viewer": {"read"},
}


def has_permission(role: str, permission: str) -> bool:
    return permission in _ROLES.get(role, set())


def get_permissions(role: str) -> Set[str]:
    return _ROLES.get(role, set()).copy()


def add_role(role: str, permissions: Set[str]) -> None:
    _ROLES[role] = permissions


def get_roles() -> List[str]:
    return list(_ROLES.keys())