
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from .models import (
    User, Role, Permission, AccessContext, AuditLog, 
    PermissionPolicy, ROLE_PERMISSIONS
)
from .storage import AuthStorage
from .kms import get_hmac_secret
from .tenant import get_tenant_manager, ApprovalRequest
from .metrics import get_auth_metrics

logger = logging.getLogger(__name__)


class PermissionManager:
    def __init__(self, storage: AuthStorage):
        self.storage = storage
        self._init_default_admin()
    
    def _init_default_admin(self):
        admin = self.storage.get_user("admin")
        if not admin:
            admin = User(
                user_id="admin",
                username="admin",
                role=Role.SUPER_ADMIN,
                tenant_id="default",
                is_active=True
            )
            api_key = admin.generate_api_key()
            self.storage.save_user(admin)
            logger.warning(f"默认管理员创建成功，API Key: {api_key}")
            logger.warning("请立即修改默认管理员密钥！")
    
    def authenticate_api_key(self, api_key: str) -> Optional[User]:
        metrics = get_auth_metrics()
        
        with metrics.time_auth("api_key"):
            if not api_key:
                metrics.record_auth_failure("api_key", "missing_key")
                return None
            
            user = self.storage.get_user_by_api_key(api_key)
            if user:
                user.last_login = datetime.utcnow()
                self.storage.save_user(user)
                self._log_audit(
                    user_id=user.user_id,
                    tenant_id=user.tenant_id,
                    action="auth:api_key",
                    success=True,
                    details={"method": "api_key"}
                )
                metrics.record_auth_success("api_key", user.role.value)
                metrics.set_risk_score(user.user_id, 0.0)
            else:
                metrics.record_auth_failure("api_key", "invalid_key")
            return user
    
    def check_permission(
        self,
        user: User,
        permission: Permission,
        tenant_id: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        metrics = get_auth_metrics()
        
        with metrics.time_permission_check(permission.value):
            context = AccessContext(
                user=user,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            context.risk_score = self._calculate_risk_score(context)
            metrics.set_risk_score(user.user_id, context.risk_score)
            
            # 检查是否需要审批
            if context.risk_score > 0.7:
                # 创建审批请求
                tenant_manager = get_tenant_manager()
                approval_request = tenant_manager.create_approval_request(
                    user_id=user.user_id,
                    tenant_id=tenant_id,
                    permission=permission.value,
                    resource_type=resource_type or "unknown",
                    resource_id=resource_id,
                    reason=reason or "高风险操作需要审批",
                    risk_score=context.risk_score
                )
                
                metrics.record_approval_request("pending")
                
                details = {
                    "permission": permission.value,
                    "risk_score": context.risk_score,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "approval_required": True,
                    "approval_request_id": approval_request.request_id
                }
                
                self._log_audit(
                    user_id=user.user_id,
                    tenant_id=tenant_id,
                    action=f"permission:check:{permission.value}",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details
                )
                
                metrics.record_permission_check(permission.value, False)
                return False, details
            
            allowed = self._evaluate_permission(context, permission)
            
            details = {
                "permission": permission.value,
                "risk_score": context.risk_score,
                "resource_type": resource_type,
                "resource_id": resource_id
            }
            
            self._log_audit(
                user_id=user.user_id,
                tenant_id=tenant_id,
                action=f"permission:check:{permission.value}",
                resource_type=resource_type,
                resource_id=resource_id,
                success=allowed,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details
            )
            
            metrics.record_permission_check(permission.value, allowed)
            return allowed, details
    
    def _calculate_risk_score(self, context: AccessContext) -> float:
        score = 0.0
        
        if not context.user.is_active:
            score += 1.0
        
        if context.user.tenant_id != context.tenant_id:
            if not context.user.has_permission(Permission.SYSTEM_ADMIN):
                score += 0.5
        
        if context.ip_address:
            pass
        
        hour = context.timestamp.hour
        if hour < 6 or hour > 22:
            score += 0.1
        
        return min(score, 1.0)
    
    def _evaluate_permission(self, context: AccessContext, permission: Permission) -> bool:
        if not context.user.is_active:
            return False
        
        if context.risk_score > 0.7:
            logger.warning(f"高风险操作被拒绝，风险分数: {context.risk_score}")
            return False
        
        policies = self.storage.get_policies()
        for policy in policies:
            if policy.evaluate(context):
                if policy.effect == "allow":
                    if permission in policy.permissions:
                        logger.info(f"策略允许: {policy.name}")
                        return True
                elif policy.effect == "deny":
                    if permission in policy.permissions:
                        logger.info(f"策略拒绝: {policy.name}")
                        return False
        
        if context.user.tenant_id != context.tenant_id:
            if not context.user.has_permission(Permission.SYSTEM_ADMIN):
                return False
        
        if context.user.has_permission(permission):
            return True
        
        return False
    
    def create_user(
        self,
        username: str,
        role: Role,
        tenant_id: str,
        created_by: str
    ) -> Tuple[User, str]:
        user_id = str(uuid.uuid4())
        user = User(
            user_id=user_id,
            username=username,
            role=role,
            tenant_id=tenant_id,
            is_active=True
        )
        api_key = user.generate_api_key()
        self.storage.save_user(user)
        
        self._log_audit(
            user_id=created_by,
            tenant_id=tenant_id,
            action="user:create",
            success=True,
            details={"target_user": user_id, "role": role.value}
        )
        
        return user, api_key
    
    def update_user_role(
        self,
        user_id: str,
        new_role: Role,
        updated_by: str
    ) -> Optional[User]:
        user = self.storage.get_user(user_id)
        if not user:
            return None
        
        old_role = user.role
        user.role = new_role
        self.storage.save_user(user)
        
        self._log_audit(
            user_id=updated_by,
            tenant_id=user.tenant_id,
            action="user:update_role",
            success=True,
            details={"target_user": user_id, "old_role": old_role.value, "new_role": new_role.value}
        )
        
        return user
    
    def toggle_user_active(
        self,
        user_id: str,
        is_active: bool,
        updated_by: str
    ) -> Optional[User]:
        user = self.storage.get_user(user_id)
        if not user:
            return None
        
        user.is_active = is_active
        self.storage.save_user(user)
        
        self._log_audit(
            user_id=updated_by,
            tenant_id=user.tenant_id,
            action="user:toggle_active",
            success=True,
            details={"target_user": user_id, "is_active": is_active}
        )
        
        return user
    
    def regenerate_api_key(
        self,
        user_id: str,
        requested_by: str
    ) -> Optional[str]:
        user = self.storage.get_user(user_id)
        if not user:
            return None
        
        new_api_key = user.generate_api_key()
        self.storage.save_user(user)
        
        self._log_audit(
            user_id=requested_by,
            tenant_id=user.tenant_id,
            action="user:regenerate_api_key",
            success=True,
            details={"target_user": user_id}
        )
        
        return new_api_key
    
    def _log_audit(
        self,
        user_id: str,
        tenant_id: str,
        action: str,
        success: bool,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        log = AuditLog(
            log_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
            details=details or {}
        )
        self.storage.add_audit_log(log)

