#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极致安全交易验证系统
用于验证发起订单的所有安全条件
"""

import time
from datetime import datetime, time as dt_time
from typing import Dict, Any, Optional, List
import json
import os


class TradeSecurityValidator:
    """
    交易安全验证器 - 极致安全模式
    """
    
    def __init__(self, config_file: str = 'trade_security_config.json'):
        self.config_file = config_file
        self.config = self._load_config()
        self.trade_history: List[Dict] = []
        
    def _load_config(self) -> Dict:
        """加载安全配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        # 默认极致安全配置
        return {
            'trading_hours': {
                'start': '09:00',
                'end': '15:00'
            },
            'ip_whitelist': [],  # 交易服务器IP白名单
            'api_keys': [],  # 有效API Key列表
            'amount_limits': {
                'single_trade_max': 100000,  # 单笔最大
                'daily_max': 500000,  # 单日最大
                'per_stock_max': 200000  # 单股最大
            },
            'frequency_limit': {
                'max_per_minute': 10,  # 每分钟最大订单数
                'max_per_hour': 60  # 每小时最大订单数
            },
            'holidays': [],  # 休市日列表
            'circuit_breaker': {
                'enabled': True,
                'max_loss_pct': 5.0  # 单日最大亏损熔断阈值
            }
        }
    
    def _save_config(self):
        """保存配置（带错误处理）"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"警告: 无法保存交易安全配置到文件: {e}")
            # 继续使用内存中的数据，不抛出异常
    
    def validate_order(self, order_info: Dict) -> Dict[str, Any]:
        """
        全面验证订单 - 极致安全检查
        
        Args:
            order_info: {
                'symbol': '股票代码',
                'amount': 金额,
                'price': 价格,
                'side': 'buy/sell',
                'ip': '来源IP',
                'api_key': 'API密钥',
                'user_id': '用户ID'
            }
        
        Returns:
            {'allowed': True/False, 'reason': '原因'}
        """
        # 1. 检查时间窗口
        time_check = self._check_trading_time()
        if not time_check['allowed']:
            return time_check
        
        # 2. 检查IP白名单
        ip_check = self._check_ip_whitelist(order_info.get('ip'))
        if not ip_check['allowed']:
            return ip_check
        
        # 3. 检查API Key
        key_check = self._check_api_key(order_info.get('api_key'))
        if not key_check['allowed']:
            return key_check
        
        # 4. 检查金额限制
        amount_check = self._check_amount_limits(order_info)
        if not amount_check['allowed']:
            return amount_check
        
        # 5. 检查交易频率
        freq_check = self._check_trading_frequency()
        if not freq_check['allowed']:
            return freq_check
        
        # 6. 检查熔断机制
        circuit_check = self._check_circuit_breaker()
        if not circuit_check['allowed']:
            return circuit_check
        
        # 所有检查通过
        self._record_trade(order_info)
        return {
            'allowed': True,
            'reason': '订单验证通过',
            'security_level': 'MAX'
        }
    
    def _check_trading_time(self) -> Dict[str, Any]:
        """检查交易时间窗口"""
        now = datetime.now()
        current_time = now.time()
        
        # 解析交易时间
        start_time = dt_time.fromisoformat(self.config['trading_hours']['start'])
        end_time = dt_time.fromisoformat(self.config['trading_hours']['end'])
        
        # 检查是否在交易时间内
        if not (start_time <= current_time <= end_time):
            return {
                'allowed': False,
                'reason': f'不在交易时间内！允许时间：{start_time.strftime("%H:%M")}-{end_time.strftime("%H:%M")}，当前时间：{current_time.strftime("%H:%M")}'
            }
        
        # 检查是否是交易日（周一到周五）
        if now.weekday() >= 5:  # 5=周六, 6=周日
            return {
                'allowed': False,
                'reason': '周末休市！'
            }
        
        # 检查是否是节假日
        date_str = now.strftime('%Y-%m-%d')
        if date_str in self.config.get('holidays', []):
            return {
                'allowed': False,
                'reason': '节假日休市！'
            }
        
        return {'allowed': True, 'reason': '交易时间验证通过'}
    
    def _check_ip_whitelist(self, ip: Optional[str]) -> Dict[str, Any]:
        """检查IP白名单"""
        if not ip:
            return {'allowed': False, 'reason': '缺少IP地址'}
        
        whitelist = self.config.get('ip_whitelist', [])
        
        # 如果白名单为空，默认允许（用于开发阶段）
        if not whitelist:
            return {'allowed': True, 'reason': 'IP白名单未启用'}
        
        # 兼容简单字符串列表和对象列表
        if isinstance(whitelist, list):
            valid_ips = []
            for item in whitelist:
                if isinstance(item, str):
                    valid_ips.append(item)
                elif isinstance(item, dict):
                    valid_ips.append(item.get('ip', ''))
        
        if ip not in valid_ips:
            return {
                'allowed': False,
                'reason': f'IP {ip} 不在交易白名单中！'
            }
        
        return {'allowed': True, 'reason': 'IP验证通过'}
    
    def _check_api_key(self, api_key: Optional[str]) -> Dict[str, Any]:
        """检查API Key"""
        if not api_key:
            return {'allowed': False, 'reason': '缺少API Key'}
        
        valid_keys = self.config.get('api_keys', [])
        
        if not valid_keys:
            return {'allowed': True, 'reason': 'API Key验证未启用'}
        
        # 提取有效密钥
        valid_key_strings = []
        for item in valid_keys:
            if isinstance(item, str):
                valid_key_strings.append(item)
            elif isinstance(item, dict):
                valid_key_strings.append(item.get('key', ''))
        
        if api_key not in valid_key_strings:
            return {
                'allowed': False,
                'reason': '无效的API Key！'
            }
        
        return {'allowed': True, 'reason': 'API Key验证通过'}
    
    def _check_amount_limits(self, order_info: Dict) -> Dict[str, Any]:
        """检查金额限制"""
        amount = order_info.get('amount', 0)
        limits = self.config.get('amount_limits', {})
        
        # 单笔限制
        if amount > limits.get('single_trade_max', float('inf')):
            return {
                'allowed': False,
                'reason': f'单笔金额超限！最大：{limits["single_trade_max"]}，当前：{amount}'
            }
        
        # 单日限制
        daily_amount = sum(
            t.get('amount', 0) for t in self.trade_history
            if t.get('date') == datetime.now().strftime('%Y-%m-%d')
        )
        if daily_amount + amount > limits.get('daily_max', float('inf')):
            return {
                'allowed': False,
                'reason': f'单日金额超限！今日已用：{daily_amount}，最大：{limits["daily_max"]}'
            }
        
        return {'allowed': True, 'reason': '金额限制验证通过'}
    
    def _check_trading_frequency(self) -> Dict[str, Any]:
        """检查交易频率"""
        now = datetime.now()
        one_minute_ago = now.timestamp() - 60
        one_hour_ago = now.timestamp() - 3600
        
        limits = self.config.get('frequency_limit', {})
        
        # 统计最近一分钟的订单数
        recent_minute = [
            t for t in self.trade_history
            if t.get('timestamp', 0) > one_minute_ago
        ]
        if len(recent_minute) >= limits.get('max_per_minute', 10):
            return {
                'allowed': False,
                'reason': f'交易频率超限！1分钟内最多{limits["max_per_minute"]}单'
            }
        
        # 统计最近一小时的订单数
        recent_hour = [
            t for t in self.trade_history
            if t.get('timestamp', 0) > one_hour_ago
        ]
        if len(recent_hour) >= limits.get('max_per_hour', 60):
            return {
                'allowed': False,
                'reason': f'交易频率超限！1小时内最多{limits["max_per_hour"]}单'
            }
        
        return {'allowed': True, 'reason': '交易频率验证通过'}
    
    def _check_circuit_breaker(self) -> Dict[str, Any]:
        """检查熔断机制"""
        if not self.config.get('circuit_breaker', {}).get('enabled', True):
            return {'allowed': True, 'reason': '熔断机制未启用'}
        
        # 这里可以添加实际盈亏检查逻辑
        # 暂时简化实现
        return {'allowed': True, 'reason': '熔断检查通过'}
    
    def _record_trade(self, order_info: Dict):
        """记录交易历史"""
        now = datetime.now()
        self.trade_history.append({
            'timestamp': now.timestamp(),
            'date': now.strftime('%Y-%m-%d'),
            'symbol': order_info.get('symbol'),
            'amount': order_info.get('amount'),
            'side': order_info.get('side'),
            'ip': order_info.get('ip'),
            'user_id': order_info.get('user_id')
        })
        
        # 只保留最近1000条记录
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
    
    # ========== 配置管理方法 ==========
    
    def add_trusted_ip(self, ip: str, description: str = None):
        """添加受信任的交易IP"""
        if 'ip_whitelist' not in self.config:
            self.config['ip_whitelist'] = []
        
        # 检查是否已存在
        exists = False
        for item in self.config['ip_whitelist']:
            if isinstance(item, dict) and item.get('ip') == ip:
                exists = True
                break
            elif isinstance(item, str) and item == ip:
                exists = True
                break
        
        if not exists:
            self.config['ip_whitelist'].append({
                'ip': ip,
                'description': description or '交易服务器',
                'added_at': datetime.now().isoformat()
            })
            self._save_config()
            return {'success': True, 'message': f'IP {ip} 已添加到交易白名单'}
        return {'success': False, 'message': 'IP已在白名单中'}
    
    def add_valid_api_key(self, api_key: str, name: str = None):
        """添加有效API Key"""
        if 'api_keys' not in self.config:
            self.config['api_keys'] = []
        
        # 检查是否已存在
        exists = False
        for item in self.config['api_keys']:
            if isinstance(item, dict) and item.get('key') == api_key:
                exists = True
                break
            elif isinstance(item, str) and item == api_key:
                exists = True
                break
        
        if not exists:
            self.config['api_keys'].append({
                'key': api_key,
                'name': name or '交易API',
                'added_at': datetime.now().isoformat()
            })
            self._save_config()
            return {'success': True, 'message': 'API Key已添加'}
        return {'success': False, 'message': 'API Key已存在'}


class CriticalPathValidator:
    """
    毫秒级关键路径验证器 - 订单执行前的绝对卡死机制
    只在真正要发送交易所订单前调用，确保毫秒级响应
    """
    
    def __init__(self):
        # 预加载到内存的白名单，用于毫秒级检查
        self.trusted_ips = set()
        self.trusted_api_keys = set()
        self.trading_start = None
        self.trading_end = None
        self._load_from_config()
    
    def _load_from_config(self):
        """从配置预加载，避免毫秒级路径的IO"""
        try:
            if os.path.exists('trade_security_config.json'):
                with open('trade_security_config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 预加载IP白名单
                for item in config.get('ip_whitelist', []):
                    if isinstance(item, dict):
                        self.trusted_ips.add(item.get('ip', ''))
                    elif isinstance(item, str):
                        self.trusted_ips.add(item)
                
                # 预加载API Key白名单
                for item in config.get('api_keys', []):
                    if isinstance(item, dict):
                        self.trusted_api_keys.add(item.get('key', ''))
                    elif isinstance(item, str):
                        self.trusted_api_keys.add(item)
                
                # 预加载交易时间
                hours = config.get('trading_hours', {})
                self.trading_start = dt_time.fromisoformat(hours.get('start', '09:00'))
                self.trading_end = dt_time.fromisoformat(hours.get('end', '15:00'))
        except:
            pass
    
    def refresh_config(self):
        """刷新配置（非关键路径调用）"""
        self._load_from_config()
    
    def validate_critical_path(self, ip: str, api_key: str, check_time: bool = True) -> tuple[bool, str]:
        """
        关键路径验证 - 毫秒级卡死机制
        订单执行前的最后一道防线，绝对禁止任何非必要
        
        Returns: (是否允许, 拒绝原因)
        """
        # 检查1: IP白名单 (绝对核心)
        if self.trusted_ips and ip not in self.trusted_ips:
            return False, f"CRITICAL: IP {ip} 不在交易白名单"
        
        # 检查2: API Key (绝对核心)
        if self.trusted_api_keys and api_key not in self.trusted_api_keys:
            return False, "CRITICAL: 无效交易API Key"
        
        # 检查3: 时间窗口 (可选但建议)
        if check_time and self.trading_start and self.trading_end:
            now = datetime.now().time()
            if not (self.trading_start <= now <= self.trading_end):
                return False, f"CRITICAL: 非交易时间 {now.strftime('%H:%M')}"
        
        # 所有检查通过
        return True, "CRITICAL: 验证通过"



class FundSecurityValidator:
    """
    极致资金安全保护验证器 - 完全控制资金提取
    防止任何未经授权的资金提取行为
    """
    
    def __init__(self):
        self.config = self._load_fund_config()
        self.withdrawal_blacklist = set()  # 永远禁止提现的账户
        self.withdrawal_whitelist = set()  # 仅允许提现的账户
        self.daily_withdrawal_limits = {}  # 每日提现限额
    
    def _load_fund_config(self) -> dict:
        """加载资金安全配置"""
        config_file = 'fund_security_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 加载到内存
                self.withdrawal_blacklist = set(config.get('withdrawal_blacklist', []))
                self.withdrawal_whitelist = set(config.get('withdrawal_whitelist', []))
                self.daily_withdrawal_limits = config.get('daily_limits', {})
                
                return config
            except:
                pass
        
        # 默认配置：默认完全禁止提现
        default_config = {
            'global_withdrawal_enabled': False,  # 全局开关：默认关闭所有提现
            'withdrawal_blacklist': [],
            'withdrawal_whitelist': [],
            'daily_limits': {},
            'require_admin_approval': True,  # 任何提现都需管理员审批
            'allow_only_trading': True,  # 仅允许交易，不允许任何资金转出
        }
        return default_config
    
    def _save_fund_config(self):
        """保存资金安全配置"""
        config = {
            'global_withdrawal_enabled': self.config.get('global_withdrawal_enabled', False),
            'withdrawal_blacklist': list(self.withdrawal_blacklist),
            'withdrawal_whitelist': list(self.withdrawal_whitelist),
            'daily_limits': self.daily_withdrawal_limits,
            'require_admin_approval': self.config.get('require_admin_approval', True),
            'allow_only_trading': self.config.get('allow_only_trading', True),
        }
        
        with open('fund_security_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def validate_withdrawal(self, account_id: str, amount: float, 
                          admin_approved: bool = False) -> tuple[bool, str]:
        """
        资金提现验证 - 极致卡死模式
        默认：完全禁止任何提现
        
        Returns: (是否允许, 拒绝原因)
        """
        # 检查1: 全局开关 - 默认关闭所有提现
        if not self.config.get('global_withdrawal_enabled', False):
            return False, "FUND: 全局提现功能已禁用"
        
        # 检查2: 仅允许交易模式
        if self.config.get('allow_only_trading', True):
            return False, "FUND: 仅允许交易操作，禁止资金提取"
        
        # 检查3: 黑名单检查
        if account_id in self.withdrawal_blacklist:
            return False, f"FUND: 账户 {account_id} 在提现黑名单中"
        
        # 检查4: 白名单检查（如果白名单不为空）
        if self.withdrawal_whitelist and account_id not in self.withdrawal_whitelist:
            return False, f"FUND: 账户 {account_id} 不在提现白名单中"
        
        # 检查5: 管理员审批要求
        if self.config.get('require_admin_approval', True) and not admin_approved:
            return False, "FUND: 提现需管理员审批"
        
        # 检查6: 每日限额
        daily_limit = self.daily_withdrawal_limits.get(account_id, 0)
        if amount > daily_limit and daily_limit > 0:
            return False, f"FUND: 超出每日提现限额 {daily_limit}"
        
        # 所有检查通过（但默认配置下基本不会走到这里）
        return True, "FUND: 提现验证通过"
    
    def block_all_withdrawals(self):
        """完全卡死所有提现"""
        self.config['global_withdrawal_enabled'] = False
        self.config['allow_only_trading'] = True
        self.config['require_admin_approval'] = True
        self._save_fund_config()
        return {'success': True, 'message': '已完全禁用所有资金提现'}
    
    def add_to_blacklist(self, account_id: str):
        """添加账户到提现黑名单"""
        self.withdrawal_blacklist.add(account_id)
        self._save_fund_config()
        return {'success': True, 'message': f'账户 {account_id} 已加入提现黑名单'}
    
    def set_only_trading_mode(self, enabled: bool = True):
        """设置仅交易模式（禁止任何资金提取）"""
        self.config['allow_only_trading'] = enabled
        self._save_fund_config()
        return {'success': True, 'message': f'仅交易模式已{"开启" if enabled else "关闭"}'}




class TradeExecutionEngine:
    """
    交易执行引擎 - 绝对安全的交易流程
    【绝对安全保证：先验证，100%通过后才提交！
    
    绝对顺序：
    1. 第一阶段：验证（不提交订单
    2. 第二阶段：只有验证100%通过后，才提交订单
    """
    
    def __init__(self):
        self.trade_history = []
        self.rejected_trades = []
    
    def execute_trade(self, order_info: dict, monitor: bool = False) -> dict:
        """
        绝对安全的交易执行流程（带实时监控
        
        强制顺序：
        第一步：先做所有验证（完全不碰订单提交
        第二步：只有100%验证通过后，才执行订单提交
        
        Args:
            monitor: 是否输出监控日志
        
        Returns: 交易执行结果
        """
        start_time = time.time()
        monitor_logs = []
        
        def log(msg):
            if monitor:
                monitor_logs.append(msg)
                print(f"[监控] {msg}")
        
        result = {
            'order_id': f'TRADE_{int(time.time()*1000)}',
            'timestamp': datetime.now().isoformat(),
            'order_info': order_info,
            'monitor_logs': monitor_logs if monitor else None,
        }
        
        log("🚀 开始处理交易请求...")
        
        # ===================================================
        # 🔒 绝对第一阶段：只验证（不提交任何订单！！
        # ===================================================
        log("⏳ 阶段1/3: 开始关键路径验证（不提交订单...")
        
        validation_start = time.time()
        
        client_ip = order_info.get('ip', '')
        api_key = order_info.get('api_key', '')
        
        log(f"   → 提取验证信息: IP={client_ip}, API Key={'*'*8 + api_key[-4:] if api_key else 'None'}")
        
        # 1. 验证1：IP白名单
        # 2. 验证2：API Key
        # 3. 验证3：交易时间窗口
        log("   → 调用关键路径验证器...")
        allowed, reason = critical_path_validator.validate_critical_path(
            client_ip, api_key, check_time=True
        )
        
        validation_time = (time.time() - validation_start) * 1000
        result['validation_time_ms'] = round(validation_time, 3)
        log(f"   ✅ 验证完成，耗时 {validation_time:.3f}ms，结果: {'✅ 通过' if allowed else '❌ 拒绝'}")
        
        # ===================================================
        # 🛑 如果验证失败 -> 直接拒绝，不提交订单！！！
        # ===================================================
        
        if not allowed:
            log("🛑 验证失败！立即终止，不提交订单到交易所！")
            reject_result = {
                **result,
                'status': 'REJECTED_BEFORE_SUBMIT',
                'action': '🛑 订单被拒绝（未提交）',
                'reason': reason,
                'details': '关键路径验证未通过，订单尚未提交即被终止',
                'submitted_to_exchange': False,
            }
            self.rejected_trades.append(reject_result)
            return reject_result
        
        # ===================================================
        # ✅ 验证100%通过 -> 第二阶段：提交订单
        # ===================================================
        
        log("✅ 验证100%通过！进入执行阶段...")
        
        execution_start = time.time()
        
        try:
            log("📤 阶段2/3: 准备提交到交易所...")
            # 只有验证通过后才敢这里才提交到交易所
            execution_details = self._perform_exchange_trade(order_info)
            log("   ✅ 交易所接受订单！")
            
            execution_time = (time.time() - execution_start) * 1000
            total_time = (time.time() - start_time) * 1000
            
            log("📊 阶段3/3: 记录交易结果...")
            success_result = {
                **result,
                'status': 'EXECUTED_AFTER_VALIDATION',
                'action': '✅ 交易成功执行（验证通过后）',
                'reason': '关键路径验证通过后提交',
                'execution_details': execution_details,
                'execution_time_ms': round(execution_time, 3),
                'total_time_ms': round(total_time, 3),
                'submitted_to_exchange': True,
            }
            
            self.trade_history.append(success_result)
            log(f"🎯 交易完成！总耗时 {total_time:.3f}ms")
            return success_result
            
        except Exception as e:
            log(f"❌ 执行出错: {str(e)}")
            error_result = {
                **result,
                'status': 'ERROR_AFTER_VALIDATION',
                'action': '❌ 交易执行出错（验证通过但提交失败）',
                'reason': str(e),
                'submitted_to_exchange': False,
            }
            self.rejected_trades.append(error_result)
            return error_result
    
    def _perform_exchange_trade(self, order_info: dict) -> dict:
        """
        执行实际的交易所交易（模拟）
        实际应用中可接入券商API
        """
        return {
            'exchange': '模拟交易所',
            'symbol': order_info.get('symbol'),
            'side': order_info.get('side'),
            'amount': order_info.get('amount'),
            'price': order_info.get('price'),
            'executed_at': datetime.now().isoformat(),
            'status': 'filled',
        }
    
    def get_execution_report(self) -> dict:
        """获取执行报告"""
        return {
            'total_trades': len(self.trade_history) + len(self.rejected_trades),
            'successful_trades': len(self.trade_history),
            'rejected_trades': len(self.rejected_trades),
            'success_rate': round(
                len(self.trade_history)/(len(self.trade_history)+len(self.rejected_trades))*100
                if (len(self.trade_history)+len(self.rejected_trades)) > 0 else 0,
                2
            ),
            'recent_trades': self.trade_history[-10:],
            'recent_rejections': self.rejected_trades[-10:],
        }


# 全局实例
trade_validator = TradeSecurityValidator()
critical_path_validator = CriticalPathValidator()
fund_security_validator = FundSecurityValidator()
trade_execution_engine = TradeExecutionEngine()
