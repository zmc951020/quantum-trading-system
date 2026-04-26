
import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Tenant:
    """租户信息"""
    tenant_id: str
    name: str
    description: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat()
        d['updated_at'] = self.updated_at.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Tenant':
        data = data.copy()
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)


@dataclass
class ApprovalRequest:
    """权限审批请求"""
    request_id: str
    user_id: str
    tenant_id: str
    permission: str
    resource_type: str
    resource_id: Optional[str]
    reason: str
    status: str  # pending, approved, rejected
    risk_score: float
    requested_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    comments: Optional[str] = None
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['requested_at'] = self.requested_at.isoformat()
        d['approved_at'] = self.approved_at.isoformat() if self.approved_at else None
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ApprovalRequest':
        data = data.copy()
        data['requested_at'] = datetime.fromisoformat(data['requested_at'])
        if data.get('approved_at'):
            data['approved_at'] = datetime.fromisoformat(data['approved_at'])
        return cls(**data)


class TenantManager:
    """租户管理器"""
    
    def __init__(self, data_dir: str = "./data/auth"):
        self.data_dir = data_dir
        self.tenants_file = os.path.join(data_dir, "tenants.json")
        self.approvals_file = os.path.join(data_dir, "approvals.json")
        self._lock = threading.Lock()
        self._init_storage()
    
    def _init_storage(self):
        """初始化存储"""
        os.makedirs(self.data_dir, exist_ok=True)
        
        if not os.path.exists(self.tenants_file):
            self._save_tenants({})
        
        if not os.path.exists(self.approvals_file):
            self._save_approvals([])
    
    def _load_tenants(self) -> Dict[str, Tenant]:
        """加载租户数据"""
        with self._lock:
            if os.path.exists(self.tenants_file):
                with open(self.tenants_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {k: Tenant.from_dict(v) for k, v in data.items()}
            return {}
    
    def _save_tenants(self, tenants: Dict[str, Tenant]):
        """保存租户数据"""
        with self._lock:
            data = {k: v.to_dict() for k, v in tenants.items()}
            with open(self.tenants_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_approvals(self) -> List[ApprovalRequest]:
        """加载审批请求"""
        with self._lock:
            if os.path.exists(self.approvals_file):
                with open(self.approvals_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [ApprovalRequest.from_dict(d) for d in data]
            return []
    
    def _save_approvals(self, approvals: List[ApprovalRequest]):
        """保存审批请求"""
        with self._lock:
            data = [a.to_dict() for a in approvals]
            with open(self.approvals_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_tenant(self, name: str, description: str) -> Tenant:
        """创建租户"""
        tenant_id = f"tenant_{int(datetime.utcnow().timestamp())}_{os.urandom(4).hex()}"
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            description=description
        )
        
        tenants = self._load_tenants()
        tenants[tenant_id] = tenant
        self._save_tenants(tenants)
        
        logger.info(f"租户创建成功: {tenant_id}")
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        tenants = self._load_tenants()
        return tenants.get(tenant_id)
    
    def list_tenants(self, include_inactive: bool = False) -> List[Tenant]:
        """列出所有租户"""
        tenants = self._load_tenants()
        if include_inactive:
            return list(tenants.values())
        return [t for t in tenants.values() if t.is_active]
    
    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        """更新租户信息"""
        tenants = self._load_tenants()
        if tenant_id not in tenants:
            return None
        
        tenant = tenants[tenant_id]
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        tenant.updated_at = datetime.utcnow()
        
        self._save_tenants(tenants)
        logger.info(f"租户更新成功: {tenant_id}")
        return tenant
    
    def deactivate_tenant(self, tenant_id: str) -> bool:
        """停用租户"""
        tenant = self.update_tenant(tenant_id, is_active=False)
        return tenant is not None
    
    def create_approval_request(
        self,
        user_id: str,
        tenant_id: str,
        permission: str,
        resource_type: str,
        resource_id: Optional[str],
        reason: str,
        risk_score: float
    ) -> ApprovalRequest:
        """创建审批请求"""
        request_id = f"approval_{int(datetime.utcnow().timestamp())}_{os.urandom(4).hex()}"
        request = ApprovalRequest(
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            permission=permission,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            status="pending",
            risk_score=risk_score
        )
        
        approvals = self._load_approvals()
        approvals.append(request)
        self._save_approvals(approvals)
        
        logger.info(f"审批请求创建成功: {request_id}")
        return request
    
    def get_approval_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """获取审批请求"""
        approvals = self._load_approvals()
        return next((a for a in approvals if a.request_id == request_id), None)
    
    def list_approval_requests(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[ApprovalRequest]:
        """列出审批请求"""
        approvals = self._load_approvals()
        
        if tenant_id:
            approvals = [a for a in approvals if a.tenant_id == tenant_id]
        if status:
            approvals = [a for a in approvals if a.status == status]
        
        return sorted(approvals, key=lambda x: x.requested_at, reverse=True)[:limit]
    
    def approve_request(
        self,
        request_id: str,
        approver_id: str,
        comments: Optional[str] = None
    ) -> Optional[ApprovalRequest]:
        """批准审批请求"""
        approvals = self._load_approvals()
        for i, request in enumerate(approvals):
            if request.request_id == request_id:
                request.status = "approved"
                request.approved_at = datetime.utcnow()
                request.approved_by = approver_id
                request.comments = comments
                self._save_approvals(approvals)
                logger.info(f"审批请求已批准: {request_id}")
                return request
        return None
    
    def reject_request(
        self,
        request_id: str,
        approver_id: str,
        comments: Optional[str] = None
    ) -> Optional[ApprovalRequest]:
        """拒绝审批请求"""
        approvals = self._load_approvals()
        for i, request in enumerate(approvals):
            if request.request_id == request_id:
                request.status = "rejected"
                request.approved_at = datetime.utcnow()
                request.approved_by = approver_id
                request.comments = comments
                self._save_approvals(approvals)
                logger.info(f"审批请求已拒绝: {request_id}")
                return request
        return None


# 全局租户管理器实例
_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    """获取租户管理器实例"""
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager

