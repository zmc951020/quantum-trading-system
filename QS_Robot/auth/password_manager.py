"""密码策略管理器：哈希、校验、强度检查"""
import hashlib, os, re


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split(":", 1)
    computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return computed.hex() == h


def check_password_strength(password: str) -> tuple[bool, str]:
    """检查密码强度，返回(是否通过, 原因)"""
    if len(password) < 8:
        return False, "密码长度至少8位"
    if not re.search(r"[A-Z]", password):
        return False, "需包含大写字母"
    if not re.search(r"[a-z]", password):
        return False, "需包含小写字母"
    if not re.search(r"\d", password):
        return False, "需包含数字"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "需包含特殊字符"
    return True, "通过"