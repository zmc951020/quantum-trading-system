
import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional
from .models import User, AuditLog, PermissionPolicy, Role, Permission
from .kms import get_kms_manager
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class AuthStorage:
    def __init__(self, data_dir: str = "./data/auth"):
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.audit_file = os.path.join(data_dir, "audit.json")
        self.policies_file = os.path.join(data_dir, "policies.json")
        self.cache_encryption_key = self._get_encryption_key()
        self._fernet = Fernet(self.cache_encryption_key)
        self._lock = threading.Lock()
        self._init_storage()
        self._init_redis()
    
    def _init_redis(self):
        """初始化Redis连接池"""
        try:
            import redis
            self.redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=int(os.getenv("REDIS_DB", 2)),
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=3,
                retry_on_timeout=True,
                max_connections=50,
                health_check_interval=30
            )
            # 测试连接
            self.redis_client.ping()
            logger.info("Redis连接成功")
        except Exception as e:
            logger.warning(f"Redis连接失败，使用本地缓存: {e}")
            self.redis_client = None
    
    def _get_encryption_key(self) -> bytes:
        """获取缓存加密密钥"""
        kms = get_kms_manager()
        key_str = kms.get_key("cache_encryption_key")
        if not key_str:
            key = Fernet.generate_key()
            kms.set_key("cache_encryption_key", key.decode())
            logger.warning("缓存加密密钥不存在，已生成新密钥")
            return key
        return key_str.encode()
    
    def _init_storage(self):
        os.makedirs(self.data_dir, exist_ok=True)
        
        if not os.path.exists(self.users_file):
            self._save_users({})
        
        if not os.path.exists(self.audit_file):
            self._save_audit_logs([])
        
        if not os.path.exists(self.policies_file):
            self._save_policies([])
    
    def _load_users(self) -> Dict[str, User]:
        with self._lock:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {k: User.from_dict(v) for k, v in data.items()}
            return {}
    
    def _save_users(self, users: Dict[str, User]):
        with self._lock:
            data = {k: v.to_dict() for k, v in users.items()}
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _encrypt_data(self, data: Dict) -> str:
        """加密数据"""
        try:
            json_data = json.dumps(data)
            encrypted = self._fernet.encrypt(json_data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"数据加密失败: {e}")
            raise
    
    def _decrypt_data(self, encrypted_data: str) -> Dict:
        """解密数据"""
        try:
            decrypted = self._fernet.decrypt(encrypted_data.encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"数据解密失败: {e}")
            raise
    
    def _load_audit_logs(self) -> List[AuditLog]:
        with self._lock:
            if os.path.exists(self.audit_file):
                with open(self.audit_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [AuditLog.from_dict(d) for d in data]
            return []
    
    def _save_audit_logs(self, logs: List[AuditLog]):
        with self._lock:
            data = [log.to_dict() for log in logs]
            with open(self.audit_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_encrypted_cache(self, cache_file: str) -> Dict:
        """加载加密的本地缓存"""
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    encrypted_data = f.read()
                    if encrypted_data:
                        return self._decrypt_data(encrypted_data)
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
        return {}
    
    def _save_encrypted_cache(self, cache_file: str, data: Dict):
        """保存加密的本地缓存"""
        try:
            encrypted_data = self._encrypt_data(data)
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def _load_policies(self) -> List[PermissionPolicy]:
        with self._lock:
            if os.path.exists(self.policies_file):
                with open(self.policies_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
    
    def _save_policies(self, policies: List[PermissionPolicy]):
        with self._lock:
            data = [
                {
                    "policy_id": p.policy_id,
                    "name": p.name,
                    "description": p.description,
                    "conditions": p.conditions,
                    "effect": p.effect,
                    "permissions": [perm.value for perm in p.permissions],
                    "priority": p.priority,
                    "is_active": p.is_active
                }
                for p in policies
            ]
            with open(self.policies_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_user(self, user_id: str) -> Optional[User]:
        users = self._load_users()
        return users.get(user_id)
    
    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        import hashlib
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        users = self._load_users()
        for user in users.values():
            if user.api_key_hash == api_key_hash and user.is_active:
                return user
        return None
    
    def save_user(self, user: User):
        users = self._load_users()
        users[user.user_id] = user
        self._save_users(users)
        logger.info(f"用户已保存: {user.user_id}")
    
    def delete_user(self, user_id: str) -> bool:
        users = self._load_users()
        if user_id in users:
            del users[user_id]
            self._save_users(users)
            logger.info(f"用户已删除: {user_id}")
            return True
        return False
    
    def list_users(self, tenant_id: Optional[str] = None) -> List[User]:
        users = self._load_users()
        if tenant_id:
            return [u for u in users.values() if u.tenant_id == tenant_id]
        return list(users.values())
    
    def add_audit_log(self, log: AuditLog):
        logs = self._load_audit_logs()
        logs.append(log)
        if len(logs) > 10000:
            logs = logs[-10000:]
        self._save_audit_logs(logs)
    
    def get_audit_logs(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        logs = self._load_audit_logs()
        
        if tenant_id:
            logs = [l for l in logs if l.tenant_id == tenant_id]
        if user_id:
            logs = [l for l in logs if l.user_id == user_id]
        if start_time:
            logs = [l for l in logs if l.timestamp >= start_time]
        if end_time:
            logs = [l for l in logs if l.timestamp <= end_time]
        
        return sorted(logs, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def get_policies(self) -> List[PermissionPolicy]:
        data = self._load_policies()
        policies = []
        for p_data in data:
            policies.append(PermissionPolicy(
                policy_id=p_data['policy_id'],
                name=p_data['name'],
                description=p_data['description'],
                conditions=p_data['conditions'],
                effect=p_data['effect'],
                permissions=[Permission(p) for p in p_data['permissions']],
                priority=p_data.get('priority', 0),
                is_active=p_data.get('is_active', True)
            ))
        return sorted(policies, key=lambda x: -x.priority)
    
    def save_policy(self, policy: PermissionPolicy):
        policies = self.get_policies()
        existing = next((p for p in policies if p.policy_id == policy.policy_id), None)
        if existing:
            policies.remove(existing)
        policies.append(policy)
        self._save_policies(policies)
        logger.info(f"策略已保存: {policy.policy_id}")
    
    def delete_policy(self, policy_id: str) -> bool:
        policies = self.get_policies()
        filtered = [p for p in policies if p.policy_id != policy_id]
        if len(filtered) < len(policies):
            self._save_policies(filtered)
            logger.info(f"策略已删除: {policy_id}")
            return True
        return False

