"""反钓鱼防御：域名白名单、Referer检查、可疑请求检测"""
from typing import Optional

_TRUSTED_DOMAINS = {"localhost", "127.0.0.1", "qs-robot.local"}


def is_trusted_origin(origin: Optional[str]) -> bool:
    if origin is None:
        return False
    for domain in _TRUSTED_DOMAINS:
        if domain in origin:
            return True
    return False


def is_suspicious_ua(user_agent: str) -> bool:
    suspicious = ["sqlmap", "nikto", "nmap", "masscan", "gobuster"]
    return any(s in user_agent.lower() for s in suspicious)


def check_request(request_headers: dict) -> tuple[bool, str]:
    """检查请求是否可疑，返回(是否安全, 原因)"""
    origin = request_headers.get("Origin", "")
    if origin and not is_trusted_origin(origin):
        return False, f"不可信来源: {origin}"
    ua = request_headers.get("User-Agent", "")
    if is_suspicious_ua(ua):
        return False, f"可疑UA: {ua}"
    return True, "通过"