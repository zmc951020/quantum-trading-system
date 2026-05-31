# -*- coding: utf-8 -*-
"""Aurora JWT 认证与 RBAC 权限"""

import jwt, hashlib, hmac, time, secrets, os
from typing import Optional, Dict

SECRET = os.getenv("AURORA_JWT_SECRET", "aurora-jwt-secret-2026")

def create_token(user_id: str, role: str = "viewer") -> str:
    payload = {"sub": user_id, "role": role, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, SECRET, algorithm="HS256")

def verify_token(token: str) -> Optional[Dict]:
    try: return jwt.decode(token, SECRET, algorithms=["HS256"])
    except: return None

ROLES = {
    "super_admin": ["*"],
    "admin": ["user:manage", "trade:execute", "system:config"],
    "trader": ["trade:execute", "trade:view"],
    "viewer": ["trade:view"],
}

def has_permission(role: str, perm: str) -> bool:
    perms = ROLES.get(role, [])
    return "*" in perms or perm in perms

def hash_password(pw: str) -> Dict:
    s = secrets.token_hex(16)
    return {"hash": hashlib.sha256((pw + s).encode()).hexdigest(), "salt": s}

def verify_password(pw: str, salt: str, h: str) -> bool:
    return hmac.compare_digest(hashlib.sha256((pw + salt).encode()).hexdigest(), h)

DEFAULT_USERS = {
    "admin": {"user_id": "admin", "role": "super_admin", "password": "admin123"},
    "trader": {"user_id": "trader", "role": "trader", "password": "trader123"},
}