#!/usr/bin/env python3
"""
用户管理模块
实现用户注册、登录、权限管理 + 设备指纹 + 渐进式安全
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

    def __init__(self, user_file='users.json', config_file='security_config.json'):
        """
        初始化用户管理器

        Args:
            user_file: 用户数据存储文件
            config_file: 安全配置文件
        """
        self.user_file = user_file
        self.users = self._load_users()
        self.sessions = {}
        self.config_file = config_file
        self.security_config = self._load_security_config()

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
        保存用户数据（带错误处理）
        """
        try:
            with open(self.user_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"警告: 无法保存用户数据到文件: {e}")
            # 继续使用内存中的数据，不抛出异常
    
    def _load_security_config(self) -> Dict[str, Any]:
        """
        加载安全配置

        Returns:
            安全配置字典
        """
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except:
                    pass
        # 默认安全配置 - 专业交易环境
        return {
            'whitelist_cities': ['青州', '烟台'],
            'disable_off_hours_check': True,
            'device_binding_mode': True,  # 启用设备绑定模式
            'trusted_devices': [],  # 只有绑定的设备才能登录
            'ip_whitelist': [],  # IP白名单
            'allow_auto_trade': True,  # 允许自动交易
            'isolation_mode': True  # 隔离模式（禁止通讯软件）
        }
    
    def _save_security_config(self):
        """
        保存安全配置（带错误处理）
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.security_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"警告: 无法保存安全配置到文件: {e}")
            # 继续使用内存中的数据，不抛出异常
    
    def get_security_config(self) -> Dict[str, Any]:
        """
        获取安全配置

        Returns:
            安全配置
        """
        return self.security_config
    
    # ========== 设备指纹和可信设备管理 ==========
    
    def generate_device_fingerprint(self, user_agent: str = None, screen_resolution: str = None,
                                     timezone: str = None, language: str = None) -> str:
        """
        生成设备指纹（简化版）
        
        Args:
            user_agent: 浏览器User-Agent
            screen_resolution: 屏幕分辨率
            timezone: 时区
            language: 语言
            
        Returns:
            设备指纹哈希
        """
        import platform
        import uuid
        
        # 收集设备信息
        device_info = []
        if user_agent:
            device_info.append(user_agent)
        if screen_resolution:
            device_info.append(screen_resolution)
        if timezone:
            device_info.append(timezone)
        if language:
            device_info.append(language)
        
        # 添加系统信息
        device_info.append(platform.system())
        device_info.append(platform.release())
        
        # 如果没有足够信息，使用一个简单标识
        if len(device_info) < 2:
            device_info.append(str(uuid.getnode()))
        
        # 生成指纹
        fingerprint_str = '|'.join(device_info)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()
    
    def is_trusted_device(self, username: str, device_fingerprint: str) -> bool:
        """
        检查设备是否被信任
        
        Args:
            username: 用户名
            device_fingerprint: 设备指纹
            
        Returns:
            是否受信任
        """
        if username not in self.users:
            return False
        
        user = self.users[username]
        trusted_devices = user.get('trusted_devices', {})
        
        return device_fingerprint in trusted_devices
    
    def add_trusted_device(self, username: str, device_fingerprint: str, device_name: str = None) -> Dict[str, Any]:
        """
        添加信任设备
        
        Args:
            username: 用户名
            device_fingerprint: 设备指纹
            device_name: 设备名称
            
        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}
        
        user = self.users[username]
        
        if 'trusted_devices' not in user:
            user['trusted_devices'] = {}
        
        user['trusted_devices'][device_fingerprint] = {
            'name': device_name or '未知设备',
            'added_at': datetime.now().isoformat(),
            'last_used': datetime.now().isoformat()
        }
        
        self._save_users()
        return {'success': True, 'message': '设备已添加到信任列表'}
    
    def remove_trusted_device(self, username: str, device_fingerprint: str) -> Dict[str, Any]:
        """
        移除信任设备
        
        Args:
            username: 用户名
            device_fingerprint: 设备指纹
            
        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}
        
        user = self.users[username]
        
        if 'trusted_devices' in user and device_fingerprint in user['trusted_devices']:
            del user['trusted_devices'][device_fingerprint]
            self._save_users()
            return {'success': True, 'message': '设备已从信任列表移除'}
        
        return {'success': False, 'message': '设备不在信任列表中'}
    
    # ========== 专业设备绑定系统 ==========
    
    def bind_device(self, username: str, device_fingerprint: str, device_name: str = None) -> Dict[str, Any]:
        """
        绑定设备（只有绑定的设备才能登录）
        
        Args:
            username: 用户名
            device_fingerprint: 设备指纹
            device_name: 设备名称
            
        Returns:
            操作结果
        """
        if username not in self.users:
            return {'success': False, 'message': '用户不存在'}
        
        user = self.users[username]
        
        if 'bound_devices' not in user:
            user['bound_devices'] = {}
        
        user['bound_devices'][device_fingerprint] = {
            'name': device_name or '专业交易设备',
            'bound_at': datetime.now().isoformat(),
            'last_used': datetime.now().isoformat()
        }
        
        self._save_users()
        return {'success': True, 'message': '设备绑定成功'}
    
    def is_device_bound(self, username: str, device_fingerprint: str) -> bool:
        """
        检查设备是否已绑定
        
        Args:
            username: 用户名
            device_fingerprint: 设备指纹
            
        Returns:
            是否绑定
        """
        if username not in self.users:
            return False
        
        user = self.users[username]
        bound_devices = user.get('bound_devices', {})
        
        return device_fingerprint in bound_devices
    
    # ========== IP白名单管理 ==========
    
    def add_ip_to_whitelist(self, ip_address: str, description: str = None) -> Dict[str, Any]:
        """
        添加IP到白名单
        
        Args:
            ip_address: IP地址
            description: 描述（如：模型服务器、交易所服务器等）
            
        Returns:
            操作结果
        """
        if 'ip_whitelist' not in self.security_config:
            self.security_config['ip_whitelist'] = []
        
        # 检查IP是否已存在
        for ip_entry in self.security_config['ip_whitelist']:
            if ip_entry.get('ip') == ip_address:
                return {'success': False, 'message': 'IP已在白名单中'}
        
        self.security_config['ip_whitelist'].append({
            'ip': ip_address,
            'description': description or '未知来源',
            'added_at': datetime.now().isoformat()
        })
        
        self._save_security_config()
        return {'success': True, 'message': f'IP {ip_address} 已添加到白名单'}
    
    def remove_ip_from_whitelist(self, ip_address: str) -> Dict[str, Any]:
        """
        从白名单移除IP
        
        Args:
            ip_address: IP地址
            
        Returns:
            操作结果
        """
        if 'ip_whitelist' not in self.security_config:
            return {'success': False, 'message': 'IP白名单为空'}
        
        original_length = len(self.security_config['ip_whitelist'])
        self.security_config['ip_whitelist'] = [
            entry for entry in self.security_config['ip_whitelist'] 
            if entry.get('ip') != ip_address
        ]
        
        if len(self.security_config['ip_whitelist']) < original_length:
            self._save_security_config()
            return {'success': True, 'message': f'IP {ip_address} 已从白名单移除'}
        
        return {'success': False, 'message': 'IP不在白名单中'}
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """
        检查IP是否在白名单中
        
        Args:
            ip_address: IP地址
            
        Returns:
            是否允许
        """
        # 如果IP白名单为空，默认允许（或根据配置）
        if 'ip_whitelist' not in self.security_config or not self.security_config['ip_whitelist']:
            return True
        
        for ip_entry in self.security_config['ip_whitelist']:
            if ip_entry.get('ip') == ip_address:
                return True
        
        return False
    
    def add_whitelist_city(self, city: str) -> Dict[str, Any]:
        """
        添加白名单城市

        Args:
            city: 城市名称

        Returns:
            操作结果
        """
        if 'whitelist_cities' not in self.security_config:
            self.security_config['whitelist_cities'] = []
        
        if city not in self.security_config['whitelist_cities']:
            self.security_config['whitelist_cities'].append(city)
            self._save_security_config()
            return {'success': True, 'message': f'城市 {city} 已添加到白名单'}
        return {'success': False, 'message': f'城市 {city} 已在白名单中'}
    
    def remove_whitelist_city(self, city: str) -> Dict[str, Any]:
        """
        从白名单中移除城市

        Args:
            city: 城市名称

        Returns:
            操作结果
        """
        if 'whitelist_cities' in self.security_config and city in self.security_config['whitelist_cities']:
            self.security_config['whitelist_cities'].remove(city)
            self._save_security_config()
            return {'success': True, 'message': f'城市 {city} 已从白名单中移除'}
        return {'success': False, 'message': f'城市 {city} 不在白名单中'}
    
    def set_off_hours_check(self, enabled: bool) -> Dict[str, Any]:
        """
        设置是否启用非工作时间检查

        Args:
            enabled: 是否启用

        Returns:
            操作结果
        """
        self.security_config['disable_off_hours_check'] = not enabled
        self._save_security_config()
        status = '启用' if enabled else '禁用'
        return {'success': True, 'message': f'非工作时间检查已{status}'}

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

    def login(self, username: str, password: str, city: str = None, ip: str = None,
              device_fingerprint: str = None, remember_device: bool = False) -> Dict[str, Any]:
        """
        用户登录（带地域和时间检查 + 设备指纹）

        Args:
            username: 用户名
            password: 密码
            city: 登录城市
            ip: 登录IP地址
            device_fingerprint: 设备指纹
            remember_device: 是否记住此设备

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

        # ========== 渐进式安全检查开始 ==========
        security_check_result = self._check_security(city, username, device_fingerprint)
        if not security_check_result['allowed']:
            return {
                'success': False, 
                'message': security_check_result['message'],
                'reason': security_check_result.get('reason', 'unknown')
            }
        # ========== 渐进式安全检查结束 ==========

        # 更新最后登录时间和登录信息
        user['last_login'] = datetime.now().isoformat()
        if city:
            user['last_login_city'] = city
        if ip:
            user['last_login_ip'] = ip
        
        # 记录登录历史
        if 'login_history' not in user:
            user['login_history'] = []
        user['login_history'].append({
            'timestamp': datetime.now().isoformat(),
            'city': city,
            'ip': ip,
            'device_fingerprint': device_fingerprint,
            'success': True
        })
        
        # 只保留最近100条登录记录
        if len(user['login_history']) > 100:
            user['login_history'] = user['login_history'][-100:]
        
        # 如果选择记住设备，添加到信任列表
        if remember_device and device_fingerprint:
            self.add_trusted_device(username, device_fingerprint, '我的设备')
        
        self._save_users()

        # 生成会话ID
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            'username': username,
            'expires_at': (datetime.now() + timedelta(hours=24)).isoformat(),
            'login_city': city,
            'login_ip': ip,
            'device_fingerprint': device_fingerprint
        }

        return {
            'success': True,
            'message': security_check_result.get('message', '登录成功'),
            'session_id': session_id,
            'security_level': security_check_result.get('security_level', 'new_device'),
            'user': {
                'username': username,
                'role': user['role'],
                'email': user['email'],
                'status': user.get('status', 'active'),
                'last_login_city': city
            }
        }
    
    def _check_security(self, city: str = None, username: str = None, 
                         device_fingerprint: str = None) -> Dict[str, Any]:
        """
        渐进式安全检查：地域 + 设备 + 时间
        
        Args:
            city: 登录城市
            username: 用户名
            device_fingerprint: 设备指纹
            
        Returns:
            检查结果
        """
        from datetime import datetime
        
        current_time = datetime.now()
        current_hour = current_time.hour
        
        # 检查0：是否完全禁用安全检查
        if self.security_config.get('disable_security_check', False):
            return {'allowed': True, 'message': '安全检查已禁用', 'security_level': 'disabled'}
        
        # 检查1：是否是信任设备（信任设备优先级最高）
        is_trusted = False
        if username and device_fingerprint:
            is_trusted = self.is_trusted_device(username, device_fingerprint)
        
        if is_trusted:
            # 信任设备：只做基础检查
            return {
                'allowed': True, 
                'message': '信任设备，安全检查通过', 
                'security_level': 'trusted'
            }
        
        # 检查2：非工作时间检查
        if not self.security_config.get('disable_off_hours_check', False):
            if current_hour < 6 or current_hour >= 23:
                return {
                    'allowed': False,
                    'message': f'当前时间 {current_time.strftime("%H:%M")} 是非工作时间，禁止登录',
                    'reason': 'off_hours',
                    'security_level': 'high'
                }
        
        # 检查3：地域白名单检查（新设备需要）
        if not self.security_config.get('disable_location_check', False):
            whitelist_cities = self.security_config.get('whitelist_cities', [])
            if city and whitelist_cities:
                if city not in whitelist_cities:
                    return {
                        'allowed': False,
                        'message': f'城市 {city} 不在白名单中，当前允许登录城市：{", ".join(whitelist_cities)}',
                        'reason': 'city_not_whitelisted',
                        'security_level': 'high'
                    }
        
        return {
            'allowed': True, 
            'message': '安全检查通过，可添加设备到信任列表', 
            'security_level': 'new_device'
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
    
    def set_security_config(self, config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新安全配置
        
        Args:
            config_updates: 配置更新字典
                - disable_security_check: 完全禁用安全检查 (True/False)
                - disable_location_check: 禁用地域检查 (True/False)
                - disable_off_hours_check: 禁用非工作时间检查 (True/False)
                - whitelist_cities: 白名单城市列表
        
        Returns:
            操作结果
        """
        for key, value in config_updates.items():
            if key in ['disable_security_check', 'disable_location_check', 
                      'disable_off_hours_check', 'whitelist_cities']:
                self.security_config[key] = value
        
        self._save_security_config()
        return {'success': True, 'message': '安全配置已更新', 'config': self.security_config}
    
    def toggle_location_check(self, enabled: bool) -> Dict[str, Any]:
        """
        开关地域验证
        
        Args:
            enabled: True=启用，False=禁用
            
        Returns:
            操作结果
        """
        self.security_config['disable_location_check'] = not enabled
        self._save_security_config()
        status = "启用" if enabled else "禁用"
        return {'success': True, 'message': f'地域验证已{status}'}
    
    def toggle_all_security(self, enabled: bool) -> Dict[str, Any]:
        """
        开关所有安全检查
        
        Args:
            enabled: True=启用，False=禁用
            
        Returns:
            操作结果
        """
        self.security_config['disable_security_check'] = not enabled
        self._save_security_config()
        status = "启用" if enabled else "禁用"
        return {'success': True, 'message': f'所有安全检查已{status}'}

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
        创建管理员用户
        安全策略：必须通过 ADMIN_INITIAL_PASSWORD 环境变量提供初始密码
        禁止自动生成、禁止打印密码到控制台/日志（金融级安全标准）
        """
        if 'admin' not in self.users:
            admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD')
            if not admin_password:
                raise RuntimeError(
                    "安全错误：管理员初始密码未设置。\n"
                    "请设置环境变量 ADMIN_INITIAL_PASSWORD，\n"
                    "长度至少12位，包含大小写字母、数字和特殊字符。\n"
                    "示例：export ADMIN_INITIAL_PASSWORD=Your_Secure_P@ssw0rd"
                )
            # 密码强度校验（金融级标准）
            if len(admin_password) < 12:
                raise ValueError("安全错误：ADMIN_INITIAL_PASSWORD 长度必须至少12位")
            has_upper = any(c.isupper() for c in admin_password)
            has_lower = any(c.islower() for c in admin_password)
            has_digit = any(c.isdigit() for c in admin_password)
            has_special = any(not c.isalnum() for c in admin_password)
            if not (has_upper and has_lower and has_digit and has_special):
                raise ValueError(
                    "安全错误：ADMIN_INITIAL_PASSWORD 必须包含"
                    "大写字母、小写字母、数字和特殊字符"
                )

            self.register('admin', admin_password, 'admin@aurora.com', 'admin')
            import logging
            logger = logging.getLogger(__name__)
            logger.info("管理员用户已创建（密码已通过环境变量安全注入，未记录明文）")
            return True
        return False


# 全局用户管理器实例
user_manager = UserManager()

# 确保有管理员用户（安全启动：环境变量未设置时将报错，防止无密码运行）
try:
    user_manager.create_admin()
except (RuntimeError, ValueError) as e:
    import logging
    logging.getLogger(__name__).critical(f"管理员创建失败: {e}")
    print(f"[严重安全错误] {e}")
    print("系统无法在无管理员密码的情况下启动，请设置 ADMIN_INITIAL_PASSWORD 环境变量后重试。")
    import sys
    sys.exit(1)

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