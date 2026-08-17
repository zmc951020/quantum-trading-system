"""JWT令牌管理器：签发、验证、刷新"""
import time, jwt, os
from typing import Optional

_SECRET = os.environ.get("JWT_SECRET", "qs_robot_default_secret")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24


def create_token(user_id: str, role: str = "user") -> str:
    payload = {
        "user_id": user_id, "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def refresh_token(token: str) -> Optional[str]:
    payload = verify_token(token)
    if payload is None:
        return None
    return create_token(payload["user_id"], payload.get("role", "user"))