"""审计追踪：操作日志记录、安全事件审计、HMAC防篡改"""
import json, logging, os, hmac, hashlib
from datetime import datetime
from typing import Optional

logger = logging.getLogger("audit_trail")
_HMAC_KEY = os.environ.get("AUDIT_HMAC_KEY", "qs_robot_audit_2024").encode()
_AUDIT_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "audit.log")


def _ensure_log_dir():
    os.makedirs(os.path.dirname(_AUDIT_LOG_PATH), exist_ok=True)


def _sign_entry(entry: dict) -> str:
    """对审计条目生成HMAC-SHA256签名"""
    data = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
    return hmac.new(_HMAC_KEY, data, hashlib.sha256).hexdigest()


def log_event(event_type: str, user: str, action: str, detail: Optional[dict] = None,
              ip: str = "", result: str = "success") -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "user": user,
        "action": action,
        "detail": detail or {},
        "ip": ip,
        "result": result,
    }
    entry["hmac"] = _sign_entry(entry)
    _ensure_log_dir()
    with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info(f"[Audit] {event_type} | {user} | {action} | {result}")


def log_login(user: str, ip: str, success: bool) -> None:
    log_event("login", user, "用户登录", ip=ip, result="success" if success else "failed")


def log_trade(user: str, symbol: str, action: str, quantity: float, price: float) -> None:
    log_event("trade", user, f"{action} {symbol}", detail={"symbol": symbol, "qty": quantity, "price": price})


def log_config_change(user: str, key: str, old_val: str, new_val: str) -> None:
    log_event("config", user, f"修改配置 {key}", detail={"old": old_val, "new": new_val})


def query_events(event_type: Optional[str] = None, limit: int = 100) -> list[dict]:
    events = []
    try:
        _ensure_log_dir()
        if not os.path.exists(_AUDIT_LOG_PATH):
            return events
        with open(_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    if event_type is None or e.get("event_type") == event_type:
                        events.append(e)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return events[-limit:]