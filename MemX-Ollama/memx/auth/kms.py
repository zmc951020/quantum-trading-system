
import os
import json
import base64
from cryptography.fernet import Fernet
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class KMSManager:
    """密钥管理服务，用于安全存储和管理密钥"""
    
    def __init__(self, kms_file: str = "./data/auth/kms.json"):
        self.kms_file = kms_file
        self._key_cache: Dict[str, str] = {}
        self._master_key = self._load_or_create_master_key()
        self._fernet = Fernet(self._master_key)
        self._init_kms_store()
    
    def _load_or_create_master_key(self) -> bytes:
        """加载或创建主密钥"""
        master_key_file = "./data/auth/master.key"
        os.makedirs(os.path.dirname(master_key_file), exist_ok=True)
        
        if os.path.exists(master_key_file):
            with open(master_key_file, 'rb') as f:
                return f.read()
        else:
            master_key = Fernet.generate_key()
            with open(master_key_file, 'wb') as f:
                f.write(master_key)
            logger.warning("创建新的主密钥，请妥善保管master.key文件")
            return master_key
    
    def _init_kms_store(self):
        """初始化KMS存储"""
        os.makedirs(os.path.dirname(self.kms_file), exist_ok=True)
        if not os.path.exists(self.kms_file):
            with open(self.kms_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
    
    def _load_kms_store(self) -> Dict[str, str]:
        """加载KMS存储"""
        with open(self.kms_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_kms_store(self, store: Dict[str, str]):
        """保存KMS存储"""
        with open(self.kms_file, 'w', encoding='utf-8') as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    
    def set_key(self, key_name: str, key_value: str):
        """存储密钥"""
        encrypted_value = self._fernet.encrypt(key_value.encode()).decode()
        store = self._load_kms_store()
        store[key_name] = encrypted_value
        self._save_kms_store(store)
        self._key_cache[key_name] = key_value
        logger.info(f"密钥已存储: {key_name}")
    
    def get_key(self, key_name: str) -> Optional[str]:
        """获取密钥"""
        if key_name in self._key_cache:
            return self._key_cache[key_name]
        
        store = self._load_kms_store()
        if key_name in store:
            try:
                decrypted_value = self._fernet.decrypt(store[key_name].encode()).decode()
                self._key_cache[key_name] = decrypted_value
                return decrypted_value
            except Exception as e:
                logger.error(f"密钥解密失败: {key_name}, 错误: {e}")
                return None
        return None
    
    def delete_key(self, key_name: str) -> bool:
        """删除密钥"""
        store = self._load_kms_store()
        if key_name in store:
            del store[key_name]
            self._save_kms_store(store)
            if key_name in self._key_cache:
                del self._key_cache[key_name]
            logger.info(f"密钥已删除: {key_name}")
            return True
        return False
    
    def list_keys(self) -> list:
        """列出所有密钥名称"""
        store = self._load_kms_store()
        return list(store.keys())
    
    def rotate_master_key(self):
        """轮换主密钥"""
        old_fernet = self._fernet
        new_master_key = Fernet.generate_key()
        
        # 加载所有密钥
        store = self._load_kms_store()
        new_store = {}
        
        # 用旧密钥解密，用新密钥加密
        for key_name, encrypted_value in store.items():
            try:
                decrypted = old_fernet.decrypt(encrypted_value.encode()).decode()
                new_encrypted = Fernet(new_master_key).encrypt(decrypted.encode()).decode()
                new_store[key_name] = new_encrypted
            except Exception as e:
                logger.error(f"密钥轮换失败: {key_name}, 错误: {e}")
        
        # 保存新主密钥
        master_key_file = "./data/auth/master.key"
        with open(master_key_file, 'wb') as f:
            f.write(new_master_key)
        
        # 保存新的加密数据
        self._save_kms_store(new_store)
        
        # 更新实例
        self._master_key = new_master_key
        self._fernet = Fernet(new_master_key)
        self._key_cache.clear()
        
        logger.info("主密钥已轮换")


# 全局KMS管理器实例
_kms_manager: Optional[KMSManager] = None


def get_kms_manager() -> KMSManager:
    """获取KMS管理器实例"""
    global _kms_manager
    if _kms_manager is None:
        _kms_manager = KMSManager()
    return _kms_manager


def get_hmac_secret() -> str:
    """获取HMAC密钥"""
    kms = get_kms_manager()
    secret = kms.get_key("hmac_secret")
    if not secret:
        # 如果密钥不存在，生成新的
        import secrets
        secret = secrets.token_urlsafe(32)
        kms.set_key("hmac_secret", secret)
        logger.warning("HMAC密钥不存在，已生成新密钥")
    return secret

