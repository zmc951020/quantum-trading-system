#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最高级防钓鱼安全监控系统
实现：行为监控、指令签名、异常拦截、全链路审计
军工级安全防护
"""
import os
import sys
import logging
import threading
import time
import hashlib
import hmac
import json
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import psutil
import socket
import getmac

logger = logging.getLogger(__name__)

class SecurityMonitor:
    """防钓鱼安全监控器"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        
        # 安全配置
        self.api_key = os.getenv('SECURITY_API_KEY', os.urandom(32).hex())
        self.ip_whitelist: Set[str] = set(['127.0.0.1', 'localhost'])
        self.device_fingerprint = self._get_device_fingerprint()
        
        # 异常检测阈值
        self.max_order_per_minute = 10
        self.max_order_amount = 1000000  # 单笔最大金额
        self.suspicious_keywords = ['phish', 'hack', 'inject', 'malicious', '钓鱼', '盗号']
        
        # 审计日志
        self.audit_log: List[Dict[str, Any]] = []
        
        # 调用计数
        self._call_counter = {}
        
        # 冻结状态
        self._frozen = False
        
    def _get_device_fingerprint(self) -> str:
        """获取设备指纹"""
        try:
            hostname = socket.gethostname()
            mac = getmac.get_mac_address()
            cpu = psutil.cpu_count()
            mem = psutil.virtual_memory().total
            
            fingerprint = f"{hostname}:{mac}:{cpu}:{mem}"
            return hashlib.sha256(fingerprint.encode()).hexdigest()
        except:
            return hashlib.sha256(os.urandom(32)).hexdigest()
            
    def sign_order(self, order: Dict[str, Any]) -> str:
        """对下单指令进行签名，防止篡改"""
        order_str = json.dumps(order, sort_keys=True)
        return hmac.new(
            self.api_key.encode(),
            order_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
    def verify_order(self, order: Dict[str, Any], signature: str) -> bool:
        """验证订单签名"""
        expected = self.sign_order(order)
        return hmac.compare_digest(expected, signature)
        
    def check_ip(self, ip: str) -> bool:
        """检查IP是否在白名单"""
        if ip not in self.ip_whitelist:
            logger.critical(f"⚠️ 非白名单IP尝试访问: {ip}")
            self.freeze_system()
            return False
        return True
        
    def check_device(self, device_fp: str) -> bool:
        """检查设备指纹"""
        if device_fp != self.device_fingerprint:
            logger.critical(f"⚠️ 非授权设备尝试访问: {device_fp}")
            self.freeze_system()
            return False
        return True
        
    def check_order(self, order: Dict[str, Any], ip: str, device_fp: str) -> bool:
        """检查订单是否异常"""
        # 1. IP检查
        if not self.check_ip(ip):
            return False
            
        # 2. 设备检查
        if not self.check_device(device_fp):
            return False
            
        # 3. 冻结检查
        if self._frozen:
            logger.critical("系统已冻结，拒绝所有订单")
            return False
            
        # 4. 金额检查
        amount = order.get('amount', 0)
        if amount > self.max_order_amount:
            logger.critical(f"⚠️ 单笔订单金额过大: {amount}, 拦截!")
            self.freeze_system()
            return False
            
        # 5. 频率检查
        now = int(time.time() / 60)
        count = self._call_counter.get(now, 0)
        if count >= self.max_order_per_minute:
            logger.critical(f"⚠️ 下单频率过高: {count}次/分钟, 拦截!")
            self.freeze_system()
            return False
        self._call_counter[now] = count + 1
        
        # 6. 恶意参数检查
        order_str = str(order).lower()
        for keyword in self.suspicious_keywords:
            if keyword in order_str:
                logger.critical(f"⚠️ 检测到恶意关键词: {keyword}, 拦截!")
                self.freeze_system()
                return False
                
        # 7. 记录审计日志
        self._log_audit('order', order, ip)
        
        return True
        
    def check_api_call(self, endpoint: str, params: Dict[str, Any], ip: str):
        """检查API调用"""
        # IP检查
        if ip not in self.ip_whitelist:
            logger.critical(f"⚠️ 非白名单IP API调用: {ip}, {endpoint}")
            self.freeze_system()
            return False
            
        # 参数检查
        params_str = str(params).lower()
        for keyword in self.suspicious_keywords:
            if keyword in params_str:
                logger.critical(f"⚠️ API调用检测到恶意参数: {keyword}")
                self.freeze_system()
                return False
                
        # 审计日志
        self._log_audit('api_call', {'endpoint': endpoint, 'params': params}, ip)
        return True
        
    def freeze_system(self):
        """冻结整个系统，防止进一步操作"""
        with self._lock:
            if self._frozen:
                return
            self._frozen = True
            
        logger.critical("🚨 系统已安全冻结! 所有交易已暂停，请人工检查!")
        
        # 紧急撤销所有未完成订单
        self._emergency_cancel_orders()
        
    def unfreeze_system(self, password: str) -> bool:
        """解冻系统，需要管理员密码"""
        # 验证管理员密码
        admin_pass = os.getenv('ADMIN_PASSWORD', '')
        if password != admin_pass:
            logger.warning("解冻密码错误")
            return False
            
        with self._lock:
            self._frozen = False
            self._call_counter = {}
            
        logger.info("系统已解冻")
        return True
        
    def _emergency_cancel_orders(self):
        """紧急撤销所有订单"""
        # 这里会调用券商API撤销所有未完成订单
        logger.warning("紧急撤销所有未完成订单")
        
    def _log_audit(self, action: str, data: Any, ip: str):
        """记录审计日志，不可篡改"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'data': data,
            'ip': ip,
            'device': self.device_fingerprint
        }
        
        # 链式哈希，确保日志不可篡改
        if self.audit_log:
            last_hash = hashlib.sha256(json.dumps(self.audit_log[-1]).encode()).hexdigest()
            entry['prev_hash'] = last_hash
            
        self.audit_log.append(entry)
        
        # 写入文件
        with open('./security_audit.log', 'a') as f:
            f.write(json.dumps(entry) + '\n')
            
    def is_frozen(self) -> bool:
        return self._frozen
        
# 全局单例
_security: Optional[SecurityMonitor] = None

def get_security_monitor() -> SecurityMonitor:
    global _security
    if _security is None:
        _security = SecurityMonitor()
    return _security
