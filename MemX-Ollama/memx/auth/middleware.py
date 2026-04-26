
from functools import wraps
from typing import Optional, Callable, Any
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .manager import PermissionManager
from .models import Permission, User
from .storage import AuthStorage

security = HTTPBearer(auto_error=False)

_auth_storage: Optional[AuthStorage] = None
_perm_manager: Optional[PermissionManager] = None


def get_auth_storage() -> AuthStorage:
    global _auth_storage
    if _auth_storage is None:
        _auth_storage = AuthStorage()
    return _auth_storage

def get_permission_manager() -> PermissionManager:
    global _perm_manager
    if _perm_manager is None:
        _perm_manager = PermissionManager(get_auth_storage())
    return _perm_manager


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    perm_manager: PermissionManager = Depends(get_permission_manager)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="未提供认证凭证"
        )
    
    user = perm_manager.authenticate_api_key(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="无效的API密钥"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="用户已被禁用"
        )
    
    return user

def require_permission(permission: Permission):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取依赖注入的对象
            current_user = kwargs.get('current_user')
            perm_manager = kwargs.get('perm_manager')
            
            if not current_user or not perm_manager:
                # 重新获取依赖
                from fastapi import Depends
                from .manager import PermissionManager
                from .storage import AuthStorage
                
                def get_auth_storage() -> AuthStorage:
                    return AuthStorage()
                
                def get_permission_manager() -> PermissionManager:
                    return PermissionManager(get_auth_storage())
                
                current_user = await get_current_user()
                perm_manager = get_permission_manager()
            
            tenant_id = kwargs.get('tenant_id') or getattr(current_user, 'tenant_id', 'default')
            
            ip_address = None
            user_agent = None
            resource_type = '/chat'
            
            # 不尝试获取Request对象，避免ChatRequest导致的错误
            
            allowed, details = perm_manager.check_permission(
                user=current_user,
                permission=permission,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=None,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"权限不足: 需要 {permission.value}"
                )
            
            kwargs['current_user'] = current_user
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

