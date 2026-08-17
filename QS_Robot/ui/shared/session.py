"""共享会话管理模块，供 ui/server.py 和 api/gateway.py 共同导入"""
import os
import uuid
from datetime import datetime, timedelta

def _get_user_password(username: str, default: str) -> str:
    env_key = f"AURORA_USER_{username.upper()}"
    return os.environ.get(env_key, default)

USERS = {
    'admin': {'password': _get_user_password('admin', 'admin123'), 'role': 'admin', 'name': '系统管理员', 'tier': 1, 'force_password_change': True},
    'trader': {'password': _get_user_password('trader', 'trader123'), 'role': 'trader', 'name': '交易员', 'tier': 2, 'force_password_change': True},
    'analyst': {'password': _get_user_password('analyst', 'analyst123'), 'role': 'analyst', 'name': '分析师', 'tier': 3, 'force_password_change': True},
    'risk': {'password': _get_user_password('risk', 'risk123'), 'role': 'risk', 'name': '风控员', 'tier': 4, 'force_password_change': True},
    'viewer': {'password': _get_user_password('viewer', 'viewer123'), 'role': 'viewer', 'name': '查看员', 'tier': 5, 'force_password_change': True},
    'guest': {'password': _get_user_password('guest', 'guest'), 'role': 'guest', 'name': '访客', 'tier': 6, 'force_password_change': True},
}

SESSIONS = {}
FAILED_LOGINS = {}

SESSION_TIMEOUT_HOURS = 2
MAX_FAILED_LOGINS = 5
LOGIN_LOCKOUT_MINUTES = 15

def create_session(username):
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        'username': username,
        'user': USERS[username],
        'created_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(hours=SESSION_TIMEOUT_HOURS)
    }
    return session_id

def get_session(session_id):
    session = SESSIONS.get(session_id)
    if session and session['expires_at'] > datetime.now():
        return session
    return None