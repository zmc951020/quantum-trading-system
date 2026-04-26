from typing import List, Dict, Optional
import logging
import redis
import json
import time
from .utils import validate_config, desensitize

logger = logging.getLogger(__name__)

class SessionMemory:
    def __init__(self):
        self.redis_host = validate_config("REDIS_HOST", "localhost")
        self.redis_port = validate_config("REDIS_PORT", 6379)
        self.redis_password = validate_config("REDIS_PASSWORD", None)
        self.expire_days = validate_config("SESSION_MEM_EXPIRE_DAYS", 30)
        self.key_prefix = "memx:session:"
        self._redis_client = None

    @property
    def redis_client(self) -> redis.Redis:
        if self._redis_client is None:
            self._redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                decode_responses=True,
                max_connections=10
            )
        return self._redis_client

    def _get_key(self, user_id: str, tenant_id: str) -> str:
        return f"{self.key_prefix}{tenant_id}:{user_id}"

    def save(self, user_id: str, history: List[Dict], tenant_id: str = "default") -> bool:
        try:
            key = self._get_key(user_id, tenant_id)
            session_data = {
                "history": history,
                "updated_at": time.time(),
                "tenant_id": tenant_id
            }
            self.redis_client.setex(
                key,
                self.expire_days * 86400,
                json.dumps(session_data)
            )
            logger.info(f"会话保存成功，用户{user_id}，租户{tenant_id}，历史{len(history)}条")
            return True
        except Exception as e:
            logger.error(f"会话保存失败，用户{user_id}，错误：{str(e)}")
            return False

    def load(self, user_id: str, tenant_id: str = "default") -> List[Dict]:
        try:
            key = self._get_key(user_id, tenant_id)
            data = self.redis_client.get(key)
            if data:
                session_data = json.loads(data)
                self.redis_client.expire(key, self.expire_days * 86400)
                logger.info(f"会话加载成功，用户{user_id}，租户{tenant_id}，历史{len(session_data.get('history', []))}条")
                return session_data.get("history", [])
            return []
        except Exception as e:
            logger.error(f"会话加载失败，用户{user_id}，错误：{str(e)}")
            return []

    def delete(self, user_id: str, tenant_id: str = "default") -> bool:
        try:
            key = self._get_key(user_id, tenant_id)
            self.redis_client.delete(key)
            logger.info(f"会话删除成功，用户{user_id}，租户{tenant_id}")
            return True
        except Exception as e:
            logger.error(f"会话删除失败，用户{user_id}，错误：{str(e)}")
            return False

    def list_sessions(self, tenant_id: str = "default") -> List[str]:
        try:
            pattern = f"{self.key_prefix}{tenant_id}:*"
            keys = self.redis_client.keys(pattern)
            return [key.split(":")[-1] for key in keys]
        except Exception as e:
            logger.error(f"会话列表获取失败，租户{tenant_id}，错误：{str(e)}")
            return []