"""密钥管理器：环境变量密钥加载、密钥轮换"""
import os, logging
from typing import Optional

logger = logging.getLogger("secrets_manager")

_SECRET_MAP = {
    "JWT_SECRET": "qs_robot_jwt_secret_default",
    "DB_ENCRYPT_KEY": "qs_robot_db_default",
    "API_KEY": "",
    "TRADE_PASSWORD": "",
}


def get_secret(key: str) -> Optional[str]:
    return os.environ.get(key, _SECRET_MAP.get(key))


def list_secret_keys() -> list[str]:
    return list(_SECRET_MAP.keys())


def is_secret_configured(key: str) -> bool:
    val = os.environ.get(key, "")
    return bool(val) and val != _SECRET_MAP.get(key, "")


def check_secrets() -> dict[str, bool]:
    return {k: is_secret_configured(k) for k in _SECRET_MAP}