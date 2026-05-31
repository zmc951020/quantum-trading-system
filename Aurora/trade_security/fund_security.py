"""资金安全保护验证器 - FundSecurityValidator
从 trade_security.py 拆分，负责完全控制资金提取，默认完全禁止提现
"""
import os, json, logging
from typing import Tuple

logger = logging.getLogger(__name__)

class FundSecurityValidator:
    """极致资金安全保护验证器 - 完全控制资金提取"""

    def __init__(self):
        self.config = self._load_fund_config()
        self.withdrawal_blacklist = set()
        self.withdrawal_whitelist = set()
        self.daily_withdrawal_limits = {}

    def _load_fund_config(self) -> dict:
        config_file = "fund_security_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file,"r",encoding="utf-8") as f:
                    cfg = json.load(f)
                self.withdrawal_blacklist = set(cfg.get("withdrawal_blacklist",[]))
                self.withdrawal_whitelist = set(cfg.get("withdrawal_whitelist",[]))
                self.daily_withdrawal_limits = cfg.get("daily_limits",{})
                return cfg
            except: pass
        return {"global_withdrawal_enabled":False,"withdrawal_blacklist":[],"withdrawal_whitelist":[],"daily_limits":{},"require_admin_approval":True,"allow_only_trading":True}

    def _save_fund_config(self):
        cfg = {"global_withdrawal_enabled":self.config.get("global_withdrawal_enabled",False),"withdrawal_blacklist":list(self.withdrawal_blacklist),"withdrawal_whitelist":list(self.withdrawal_whitelist),"daily_limits":self.daily_withdrawal_limits,"require_admin_approval":self.config.get("require_admin_approval",True),"allow_only_trading":self.config.get("allow_only_trading",True)}
        with open("fund_security_config.json","w",encoding="utf-8") as f:
            json.dump(cfg,f,indent=2,ensure_ascii=False)

    def validate_withdrawal(self, account_id: str, amount: float, admin_approved: bool = False) -> Tuple[bool,str]:
        """资金提现验证 - 极致卡死模式，默认完全禁止"""
        if not self.config.get("global_withdrawal_enabled",False):
            return False, "FUND: 全局提现功能已禁用"
        if self.config.get("allow_only_trading",True):
            return False, "FUND: 仅允许交易操作，禁止资金提取"
        if account_id in self.withdrawal_blacklist:
            return False, f"FUND: 账户 {account_id} 在提现黑名单中"
        if self.withdrawal_whitelist and account_id not in self.withdrawal_whitelist:
            return False, f"FUND: 账户 {account_id} 不在提现白名单中"
        if self.config.get("require_admin_approval",True) and not admin_approved:
            return False, "FUND: 提现需管理员审批"
        daily_limit = self.daily_withdrawal_limits.get(account_id,0)
        if amount > daily_limit and daily_limit > 0:
            return False, f"FUND: 超出每日提现限额 {daily_limit}"
        return True, "FUND: 提现验证通过"

    def block_all_withdrawals(self):
        self.config["global_withdrawal_enabled"] = False
        self.config["allow_only_trading"] = True
        self.config["require_admin_approval"] = True
        self._save_fund_config()
        return {"success":True,"message":"已完全禁用所有资金提现"}

    def add_to_blacklist(self, account_id: str):
        self.withdrawal_blacklist.add(account_id)
        self._save_fund_config()
        return {"success":True,"message":f"账户 {account_id} 已加入提现黑名单"}

    def set_only_trading_mode(self, enabled: bool = True):
        self.config["allow_only_trading"] = enabled
        self._save_fund_config()
        return {"success":True,"message":f"仅交易模式已{'开启' if enabled else '关闭'}"}

fund_security_validator = FundSecurityValidator()