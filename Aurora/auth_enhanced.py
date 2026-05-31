#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora 增强认证安全模块 v2.0
- JWT Token 双因子认证
- 会话管理与过期策略
- API白名单/IP限制
- 密码强度与轮换策略
- 审计日志
"""

import os, sys, json, time, hashlib, hmac, uuid, logging, threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from user_manager import UserManager

logger = logging.getLogger("EnhancedAuth")

class EnhancedAuthManager(UserManager):
    """增强认证管理 - 继承 UserManager"""

    def __init__(self, users_file="users.json", config: Optional[Dict] = None):
        super().__init__(users_file)
        self.config = config or {}
        self._sessions: Dict[str, Dict] = {}
        self._failed_attempts: Dict[str, deque] = {}
        self._ip_whitelist: set = set(self.config.get("ip_whitelist", []))
        self._ip_blacklist: set = set(self.config.get("ip_blacklist", []))
        self._audit_log: deque = deque(maxlen=1000)
        self._lock = threading.Lock()

        # 安全参数
        self.max_failed_attempts = self.config.get("max_failed_attempts", 5)
        self.lockout_minutes = self.config.get("lockout_minutes", 15)
        self.session_timeout = self.config.get("session_timeout", 3600)
        self.token_secret = self.config.get("token_secret", os.urandom(32).hex())
        self.password_min_length = 8
        self.totp_window = 30  # 30秒TOTP窗口

        logger.info("增强认证管理初始化完成")

    # ========== JWT Token管理 ==========
    def generate_token(self, username: str, role: str = "user") -> str:
        """生成JWT风格Token"""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": username, "role": role, "iat": int(time.time()),
            "exp": int(time.time() + self.session_timeout),
            "jti": uuid.uuid4().hex[:12]
        }
        data = f"{self._b64_encode(json.dumps(header))}.{self._b64_encode(json.dumps(payload))}"
        signature = hmac.new(self.token_secret.encode(), data.encode(), hashlib.sha256).hexdigest()
        token = f"{data}.{signature}"
        with self._lock:
            self._sessions[username] = {"token": token, "created": datetime.now(), "role": role}
        return token

    def verify_token(self, token: str) -> Optional[Dict]:
        """验证Token"""
        try:
            parts = token.split(".")
            if len(parts) != 3: return None
            payload = json.loads(self._b64_decode(parts[1]))
            if payload.get("exp", 0) < time.time(): return None
            expected_sig = hmac.new(self.token_secret.encode(),
                                     f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(parts[2], expected_sig): return None
            return {"username": payload["sub"], "role": payload["role"]}
        except: return None

    # ========== 双因子认证 ==========
    def generate_totp_secret(self, username: str) -> str:
        """生成TOTP密钥"""
        secret = uuid.uuid4().hex[:16]
        self.users[username]["totp_secret"] = secret
        self._save_users()
        return secret

    def verify_totp(self, username: str, code: str) -> bool:
        """验证TOTP码"""
        secret = self.users.get(username, {}).get("totp_secret")
        if not secret: return False
        t = int(time.time()) // self.totp_window
        for offset in [-1, 0, 1]:
            msg = f"{secret}{t + offset}".encode()
            expected = str(int(hashlib.sha256(msg).hexdigest(), 16) % 1000000).zfill(6)
            if hmac.compare_digest(code, expected): return True
        return False

    # ========== 安全登录 ==========
    def secure_login(self, username: str, password: str, totp_code: str = "",
                     ip: str = "127.0.0.1") -> Dict[str, Any]:
        """安全登录（用户名校验 -> 密码校验 -> IP检查 -> TOTP -> 防暴力破解）"""
        self._audit("login_attempt", {"username": username, "ip": ip})

        # IP黑名单
        if ip in self._ip_blacklist:
            return {"status": "denied", "reason": "IP在黑名单中"}

        # 防暴力破解
        if self._is_locked(username):
            return {"status": "locked", "reason": f"账户已锁定{self.lockout_minutes}分钟"}

        # 用户名校验
        if username not in self.users:
            self._record_failure(username, ip)
            return {"status": "denied", "reason": "用户名或密码错误"}

        user = self.users[username]

        # 密码校验（加盐SHA256）
        if not self._verify_password(password, user.get("password_hash", "")):
            self._record_failure(username, ip)
            self._audit("login_failed", {"username": username, "ip": ip, "reason": "密码错误"})
            return {"status": "denied", "reason": "用户名或密码错误"}

        # TOTP双因子（如果启用）
        if user.get("totp_enabled") and not self.verify_totp(username, totp_code):
            self._audit("totp_failed", {"username": username})
            return {"status": "denied", "reason": "双因子验证码错误"}

        # IP白名单检查（可选严格模式）
        if self._ip_whitelist and self.config.get("strict_ip_check"):
            if ip not in self._ip_whitelist:
                return {"status": "denied", "reason": "IP不在白名单中"}

        # 成功
        token = self.generate_token(username, user.get("role", "user"))
        self._clear_failures(username)
        self._audit("login_success", {"username": username, "ip": ip})
        return {"status": "ok", "token": token, "username": username, "role": user.get("role")}

    # ========== 会话管理 ==========
    def logout(self, username: str):
        """登出"""
        with self._lock:
            self._sessions.pop(username, None)
        self._audit("logout", {"username": username})

    def session_cleanup(self):
        """清理过期会话"""
        now = time.time()
        expired = [u for u, s in self._sessions.items()
                    if now - s["created"].timestamp() > self.session_timeout]
        for u in expired:
            self._sessions.pop(u, None)

    # ========== 密码策略 ==========
    def check_password_strength(self, password: str) -> Dict[str, Any]:
        """密码强度检查"""
        score = 0
        checks = []
        if len(password) >= self.password_min_length:
            score += 20; checks.append("长度合格")
        else: checks.append(f"长度不足(需{self.password_min_length}位)")
        if any(c.isupper() for c in password):
            score += 20; checks.append("包含大写")
        if any(c.islower() for c in password):
            score += 20; checks.append("包含小写")
        if any(c.isdigit() for c in password):
            score += 20; checks.append("包含数字")
        if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            score += 20; checks.append("包含特殊字符")
        level = "弱" if score < 40 else "中" if score < 80 else "强"
        return {"score": score, "level": level, "checks": checks, "acceptable": score >= 60}

    def force_password_rotation(self, username: str, new_password: str) -> bool:
        """密码轮换"""
        if username not in self.users: return False
        self.users[username]["password_hash"] = self._hash_password(new_password)
        self.users[username]["password_changed_at"] = datetime.now().isoformat()
        self._save_users()
        self._audit("password_rotated", {"username": username})
        return True

    # ========== IP管理 ==========
    def add_ip_whitelist(self, ip: str):
        self._ip_whitelist.add(ip)
    def add_ip_blacklist(self, ip: str):
        self._ip_blacklist.add(ip)
    def remove_ip_whitelist(self, ip: str):
        self._ip_whitelist.discard(ip)

    # ========== 审计 ==========
    def _audit(self, action: str, detail: Dict):
        self._audit_log.append({"action": action, "detail": detail, "timestamp": datetime.now().isoformat()})
    def get_audit_log(self, limit: int = 50) -> list:
        return list(self._audit_log)[-limit:]

    # ========== 内部方法 ==========
    def _is_locked(self, username: str) -> bool:
        if username not in self._failed_attempts: return False
        recent = [t for t in self._failed_attempts[username]
                  if (datetime.now() - t).total_seconds() < self.lockout_minutes * 60]
        return len(recent) >= self.max_failed_attempts

    def _record_failure(self, username: str, ip: str):
        if username not in self._failed_attempts:
            self._failed_attempts[username] = deque(maxlen=self.max_failed_attempts * 2)
        self._failed_attempts[username].append(datetime.now())

    def _clear_failures(self, username: str):
        self._failed_attempts.pop(username, None)

    def _verify_password(self, password: str, pwd_hash: str) -> bool:
        return self._hash_password(password) == pwd_hash

    def _hash_password(self, password: str) -> str:
        salt = self.config.get("password_salt", "aurora_salt_2024")
        return hashlib.sha256(f"{salt}{password}{salt}".encode()).hexdigest()

    @staticmethod
    def _b64_encode(data: str) -> str:
        import base64
        return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
    @staticmethod
    def _b64_decode(data: str) -> str:
        import base64
        padding = 4 - len(data) % 4
        return base64.urlsafe_b64decode((data + "=" * padding).encode()).decode()


if __name__ == "__main__":
    auth = EnhancedAuthManager()
    auth.users["admin"] = {"password_hash": auth._hash_password("admin123"), "role": "admin", "totp_enabled": False}
    result = auth.secure_login("admin", "admin123")
    print(json.dumps({k: v for k, v in result.items() if k != "token"}, indent=2))
    print(f"密码强度: {auth.check_password_strength('Weak')}")
    print(f"密码强度: {auth.check_password_strength('Str0ng!P@ss')}")