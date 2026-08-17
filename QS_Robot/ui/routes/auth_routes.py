# -*- coding: utf-8 -*-
"""认证 API 路由"""
from flask import request, jsonify, redirect, url_for, make_response
from datetime import datetime, timedelta

from ui.shared.session import USERS, SESSIONS, FAILED_LOGINS, SESSION_TIMEOUT_HOURS, MAX_FAILED_LOGINS, LOGIN_LOCKOUT_MINUTES, create_session, get_session
from core.security import get_password_manager, get_audit_logger, OperationType

password_manager = get_password_manager()
audit_logger = get_audit_logger()


def register_routes(app):
    @app.route('/api/auth/login', methods=['POST'])
    def api_login():
        """登录API - 使用bcrypt密码加密验证"""
        try:
            data = request.get_json()
            username = data.get('username', '')
            password = data.get('password', '')
            city = data.get('city', '')
            ip_address = request.remote_addr

            if ip_address not in ('127.0.0.1', '::1'):
                try:
                    from api.aurora_core_adapter import get_aurora_adapter
                    adapter = get_aurora_adapter()
                    if not adapter.is_ip_whitelisted(ip_address):
                        audit_logger.log(
                            user="anonymous", operation=OperationType.LOGIN,
                            target=username, result="failed",
                            details={"reason": "IP不在白名单中"}, ip_address=ip_address
                        )
                        return jsonify({"success": False, "message": f"IP {ip_address} 不在白名单中，登录被拒绝"}), 403
                except Exception as e:
                    print(f"[Auth] IP白名单检查异常: {e}")

            now = datetime.now()
            if ip_address in FAILED_LOGINS:
                lockout = FAILED_LOGINS[ip_address]
                if lockout.get('blocked_until') and now < lockout['blocked_until']:
                    remaining = int((lockout['blocked_until'] - now).total_seconds())
                    return jsonify({"success": False, "message": f"登录尝试过多，请{remaining}秒后重试"}), 429

            if not username or not password:
                audit_logger.log(user="anonymous", operation=OperationType.LOGIN,
                    target=username, result="failed",
                    details={"reason": "用户名或密码为空"}, ip_address=ip_address)
                return jsonify({"success": False, "message": "用户名或密码不能为空"}), 400

            user = USERS.get(username)
            if not user:
                audit_logger.log(user="anonymous", operation=OperationType.LOGIN,
                    target=username, result="failed",
                    details={"reason": "用户不存在"}, ip_address=ip_address)
                return jsonify({"success": False, "message": "用户名或密码错误"}), 401

            if not password_manager.verify_password_str(password, user['password']):
                if ip_address not in FAILED_LOGINS:
                    FAILED_LOGINS[ip_address] = {'count': 0, 'last_attempt': now}
                FAILED_LOGINS[ip_address]['count'] += 1
                FAILED_LOGINS[ip_address]['last_attempt'] = now
                if FAILED_LOGINS[ip_address]['count'] >= MAX_FAILED_LOGINS:
                    FAILED_LOGINS[ip_address]['blocked_until'] = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                audit_logger.log(user="anonymous", operation=OperationType.LOGIN,
                    target=username, result="failed",
                    details={"reason": "密码错误"}, ip_address=ip_address)
                return jsonify({"success": False, "message": "用户名或密码错误"}), 401

            session_id = create_session(username)
            FAILED_LOGINS.pop(ip_address, None)

            audit_logger.log(user=username, operation=OperationType.LOGIN,
                target=username, result="success",
                details={"role": user['role'], "city": city},
                ip_address=ip_address, session_id=session_id)

            resp = jsonify({"success": True, "message": "登录成功", "session_id": session_id, "user": user})
            resp.set_cookie('session_id', session_id, httponly=True, secure=False,
                          samesite='Strict', max_age=86400)
            return resp
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route('/api/auth/status', methods=['GET'])
    def api_auth_status():
        """检查登录状态"""
        session_id = request.cookies.get('session_id')
        if not session_id:
            session_id = request.headers.get('X-Session-Id')
        session = get_session(session_id)
        if session:
            return jsonify({"success": True, "logged_in": True, "user": session['user']})
        else:
            return jsonify({"success": True, "logged_in": False})

    @app.route('/api/auth/users', methods=['GET'])
    def api_get_users():
        """获取用户列表（管理员权限）"""
        session_id = request.cookies.get('session_id')
        session = get_session(session_id)
        if not session or session['user']['role'] != 'admin':
            return jsonify({"success": False, "message": "权限不足"}), 403
        users = []
        for username, info in USERS.items():
            users.append({'username': username, 'name': info['name'], 'role': info['role'], 'tier': info['tier']})
        return jsonify({"success": True, "data": users})
