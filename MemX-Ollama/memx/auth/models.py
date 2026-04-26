
import enum
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field, asdict


class Permission(enum.Enum):
    CHAT = "chat:access"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"
    TENANT_ADMIN = "tenant:admin"
    SYSTEM_ADMIN = "system:admin"
    MODEL_MANAGE = "model:manage"
    AUDIT_READ = "audit:read"


class Role(enum.Enum):
    GUEST = "guest"
    USER = "user"
    TENANT_MANAGER = "tenant_manager"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_PERMISSIONS = {
    Role.GUEST: {
        Permission.CHAT
    },
    Role.USER: {
        Permission.CHAT,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE
    },
    Role.TENANT_MANAGER: {
        Permission.CHAT,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.TENANT_ADMIN
    },
    Role.ADMIN: {
        Permission.CHAT,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.TENANT_ADMIN,
        Permission.MODEL_MANAGE,
        Permission.AUDIT_READ
    },
    Role.SUPER_ADMIN: {
        Permission.CHAT,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.TENANT_ADMIN,
        Permission.SYSTEM_ADMIN,
        Permission.MODEL_MANAGE,
        Permission.AUDIT_READ
    }
}


@dataclass
class User:
    user_id: str
    username: str
    role: Role
    tenant_id: str
    password_hash: Optional[str] = None
    api_key: Optional[str] = None
    api_key_hash: Optional[str] = None
    permissions: Set[Permission] = field(default_factory=set)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['role'] = self.role.value
        d['permissions'] = [p.value for p in self.permissions]
        d['created_at'] = self.created_at.isoformat()
        d['last_login'] = self.last_login.isoformat() if self.last_login else None
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        data = data.copy()
        data['role'] = Role(data['role'])
        data['permissions'] = {Permission(p) for p in data['permissions']}
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['last_login'] = datetime.fromisoformat(data['last_login']) if data.get('last_login') else None
        return cls(**data)
    
    def has_permission(self, permission: Permission) -> bool:
        if not self.is_active:
            return False
        if Permission.SYSTEM_ADMIN in self.permissions:
            return True
        return permission in self.permissions or permission in ROLE_PERMISSIONS.get(self.role, set())
    
    def generate_api_key(self) -> str:
        api_key = f"mk_{secrets.token_urlsafe(32)}"
        self.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        self.api_key = api_key
        return api_key
    
    def verify_api_key(self, api_key: str) -> bool:
        if not self.api_key_hash:
            return False
        return hashlib.sha256(api_key.encode()).hexdigest() == self.api_key_hash


@dataclass
class AccessContext:
    user: User
    tenant_id: str
    resource_type: str
    resource_id: Optional[str] = None
    action: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    risk_score: float = 0.0
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['user'] = self.user.to_dict()
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class AuditLog:
    log_id: str
    user_id: str
    tenant_id: str
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    success: bool
    ip_address: Optional[str]
    user_agent: Optional[str]
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AuditLog':
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class PermissionPolicy:
    policy_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    effect: str
    permissions: List[Permission]
    priority: int = 0
    is_active: bool = True
    
    def evaluate(self, context: AccessContext) -> bool:
        if not self.is_active:
            return False
        
        for key, value in self.conditions.items():
            if key == 'tenant_id' and context.tenant_id != value:
                return False
            if key == 'role' and context.user.role != Role(value):
                return False
            if key == 'risk_threshold' and context.risk_score > value:
                return False
            if key == 'time_range':
                hour = context.timestamp.hour
                if not (value['start'] <= hour < value['end']):
                    return False
        
        return True

