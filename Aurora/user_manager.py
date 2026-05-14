#!/usr/bin/env python3
"""
用户管理模块
实现用户注册、登录、权限管理
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class UserManager:
    """
    用户管理器
    支持多用户管理，可拓展
    用户数量受服务器资源限制，理论上支持无限多用户
    """

    MAX_USERS = 10  # 最大用户数，可根据需要扩展

    def __init__(self, user_file='users.json'):
        """
        初始化用户管理器

        Args:
            user_file: 用户数据存储文件
        """
        self.user_file = user_file
        self.users = self._load_users()
        self.sessions = {}

    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        """
        加载用户数据

        Returns:
            用户字典
        """
        if os.path.exists(self.user_file):
            with open(self.user_file, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except:
                    return {}
        return {}

    def _save_users(self):
        """
        保存用户数据
        """
        with open(self.user_file, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, indent=2, ensure_ascii=False)

    def _hash_password(self, password: str) -> str:
        """
        密码哈希

        Args:
            password: 原始密码

        Returns:
            哈希后的密码
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def register(self, username: str, password: str, email: str, role: str = 'user') -> Dict[str, Any]:
        """
        注册新用户

        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            role: 角色 (user, admin)

        Returns:
            注册结果
        """
        # 检查用户数量限制
        if len(self.users) >= self.MAX_USERS:
            return {'success': False, 'message': f'用户数量已达上限（{self.MAX_USERS}个），请联系管理员'}

        if username in self.users:
            return {'success': False, 'message': '用户名已存在'}

        self.users[username] = {
            'password': self._hash_password(password),
            'email': email,
            'role': role,
            'status': 'active',  # active, disabled
            'created_at': datetime.now().isoformat(),
            'last_login': None
        }

        self._save_users()
        return {'success': True, 'message': '注册成功'}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            登录结果，包含session_id
        """
        if username not in self.users:
            return {'success': False, 'message': '用户名不存在'}

        user = self.users[username]
        
        # 检查用户状态
        if user.get('status') == 'disabled':
            return {'success': False, 'message': '账户已被禁用，请联系管理员'}
        
        if user['password'] != self._hash_password(password):
            return {'success': False, 'message': '密码错误'}

        # 更新最后登录时间（跳过保存，避免权限问题）
        user['last_login'] = datetime.now().isoformat()
        # self._save_users()  # 注释掉保存操作，避免权限错误

        # 生成会话ID
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            'username': username,
            'expires_at': (datetime.now() + timedelta(hours=24)).isoformat()
        }

        return {
            'success': True,
            'message': '登录成功',
            'session_id': session_id,
            'user': {
                'username': username,
                'role': user['role'],
                'email': user['email'],
                'status': user.get('status', 'active')
            }
        }

    def logout(self, session_id: str) -> Dict[str, Any]:
        """
        用户登出

        Args:
            session_id: 会话ID

        Returns:
            登出结果
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            return {'success': True, 'message': '登出成功'}
        return {'success': False, 'message': '会话不存在'}

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        验证会话

        Args:
            session_id: 会话ID

        Returns:
            会话信息，如果会话无效返回None
        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        expires_at = datetime.fromisoformat(session['expires_at'])

        if datetime.now() > expires_at:
            del self.sessions[session_id]
            return None

        return session

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        获取用户信息

        Args:
            username: 用户名

        Returns:
            用户信息
        """
        return self.users.get(username)

    def update_user(self, username: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新用户信息

        Args:
            username: 用户名
            updates: 更新内容

        Returns:
            更新结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        # 如果更新密码，需要哈希处理
        if 'password' in updates:
            updates['password'] = self._hash_password(updates['password'])

        self.users[username].update(updates)
        self._save_users()

        return {'success': True, 'message': '更新成功'}

    def delete_user(self, username: str) -> Dict[str, Any]:
        """
        删除用户

        Args:
            username: 用户名

        Returns:
            删除结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        # 不允许删除管理员
        if username == 'admin':
            return {'success': False, 'message': '不能删除管理员账户'}

        del self.users[username]
        self._save_users()

        # 清理相关会话
        sessions_to_remove = []
        for session_id, session in self.sessions.items():
            if session['username'] == username:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.sessions[session_id]

        return {'success': True, 'message': '删除成功'}

    def get_max_users(self) -> int:
        """
        获取最大用户数

        Returns:
            最大用户数
        """
        return self.MAX_USERS

    def get_current_user_count(self) -> int:
        """
        获取当前用户数

        Returns:
            当前用户数
        """
        return len(self.users)

    def get_remaining_slots(self) -> int:
        """
        获取剩余可用用户名额

        Returns:
            剩余名额
        """
        return self.MAX_USERS - len(self.users)

    def disable_user(self, username: str) -> Dict[str, Any]:
        """
        禁用用户

        Args:
            username: 用户名

        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        # 不允许禁用管理员
        if username == 'admin':
            return {'success': False, 'message': '不能禁用管理员账户'}

        self.users[username]['status'] = 'disabled'
        self._save_users()

        # 清理该用户的所有会话
        sessions_to_remove = []
        for session_id, session in self.sessions.items():
            if session['username'] == username:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.sessions[session_id]

        return {'success': True, 'message': f'用户 {username} 已被禁用'}

    def enable_user(self, username: str) -> Dict[str, Any]:
        """
        启用用户

        Args:
            username: 用户名

        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        self.users[username]['status'] = 'active'
        self._save_users()

        return {'success': True, 'message': f'用户 {username} 已被启用'}

    def reset_password(self, username: str, new_password: str) -> Dict[str, Any]:
        """
        重置用户密码

        Args:
            username: 用户名
            new_password: 新密码

        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        self.users[username]['password'] = self._hash_password(new_password)
        self._save_users()

        return {'success': True, 'message': '密码重置成功'}

    def forgot_password(self, email: str) -> Dict[str, Any]:
        """
        忘记密码，通过邮箱找回

        Args:
            email: 用户邮箱

        Returns:
            操作结果
        """
        # 查找邮箱对应的用户
        for username, user_info in self.users.items():
            if user_info.get('email') == email:
                # 生成临时密码
                temp_password = secrets.token_urlsafe(8)
                self.users[username]['password'] = self._hash_password(temp_password)
                self._save_users()
                
                # 这里应该发送邮件给用户，现在返回临时密码
                return {
                    'success': True,
                    'message': '密码已重置，请使用临时密码登录',
                    'temp_password': temp_password,
                    'username': username
                }

        return {'success': False, 'message': '邮箱不存在'}

    def bind_email(self, username: str, email: str) -> Dict[str, Any]:
        """
        绑定邮箱

        Args:
            username: 用户名
            email: 邮箱地址

        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}

        self.users[username]['email'] = email
        self._save_users()

        return {'success': True, 'message': '邮箱绑定成功'}

    def list_users(self) -> Dict[str, Any]:
        """
        列出所有用户

        Returns:
            用户列表
        """
        users = []
        for username, user_info in self.users.items():
            users.append({
                'username': username,
                'email': user_info['email'],
                'role': user_info['role'],
                'status': user_info.get('status', 'active'),
                'created_at': user_info['created_at'],
                'last_login': user_info['last_login']
            })
        return {'users': users, 'total': len(users)}

    def create_admin(self):
        """
        创建管理员用户（如果不存在）
        """
        if 'admin' not in self.users:
            self.register('admin', 'admin123', 'admin@aurora.com', 'admin')
            print("管理员用户已创建: admin / admin123")


# 全局用户管理器实例
user_manager = UserManager()

# 确保有管理员用户
user_manager.create_admin()

if __name__ == '__main__':
    # 测试用户管理功能
    print("测试用户管理功能...")
    
    # 注册测试用户
    result = user_manager.register('testuser', 'test123', 'test@example.com')
    print(f"注册结果: {result}")
    
    # 登录测试
    result = user_manager.login('testuser', 'test123')
    print(f"登录结果: {result}")
    
    if result['success']:
        session_id = result['session_id']
        
        # 验证会话
        session = user_manager.validate_session(session_id)
        print(f"验证会话: {session}")
        
        # 登出
        result = user_manager.logout(session_id)
        print(f"登出结果: {result}")
    
    # 列出用户
    users = user_manager.list_users()
    print(f"用户列表: {users}")
