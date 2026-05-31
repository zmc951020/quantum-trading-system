"""毫秒级关键路径验证器 - CriticalPathValidator
从 trade_security.py 拆分，负责订单执行前的绝对卡死验证
"""
import os, json, logging
from datetime import datetime, time as dt_time
from typing import Tuple

logger = logging.getLogger(__name__)

class CriticalPathValidator:
    """毫秒级关键路径验证器：预加载到内存，IO-free检查"""

    def __init__(self):
        self.trusted_ips = set()
        self.trusted_api_keys = set()
        self.morning_start = None
        self.morning_end = None
        self.afternoon_start = None
        self.afternoon_end = None
        self._load_from_config()

    def _load_from_config(self):
        try:
            if os.path.exists("trade_security_config.json"):
                with open("trade_security_config.json","r",encoding="utf-8") as f:
                    cfg = json.load(f)
                for item in cfg.get("ip_whitelist",[]):
                    self.trusted_ips.add(item.get("ip","") if isinstance(item,dict) else item)
                for item in cfg.get("api_keys",[]):
                    self.trusted_api_keys.add(item.get("key","") if isinstance(item,dict) else item)
                hours = cfg.get("trading_hours",{})
                self.morning_start = dt_time.fromisoformat(hours.get("morning_start","09:30"))
                self.morning_end = dt_time.fromisoformat(hours.get("morning_end","11:30"))
                self.afternoon_start = dt_time.fromisoformat(hours.get("afternoon_start","13:00"))
                self.afternoon_end = dt_time.fromisoformat(hours.get("afternoon_end","15:00"))
        except: pass

    def refresh_config(self):
        self._load_from_config()

    def validate_critical_path(self, ip: str, api_key: str, check_time: bool = True) -> Tuple[bool,str]:
        """关键路径验证 - 毫秒级卡死机制"""
        if self.trusted_ips and ip not in self.trusted_ips:
            return False, f"CRITICAL: IP {ip} 不在交易白名单"
        if self.trusted_api_keys and api_key not in self.trusted_api_keys:
            return False, "CRITICAL: 无效交易API Key"
        if check_time and self.morning_start and self.afternoon_end:
            now = datetime.now().time()
            in_morning = self.morning_start <= now <= self.morning_end
            in_afternoon = self.afternoon_start <= now <= self.afternoon_end
            if not (in_morning or in_afternoon):
                return False, f"CRITICAL: 非交易时间 {now.strftime('%H:%M')}"
        return True, "CRITICAL: 验证通过"

critical_path_validator = CriticalPathValidator()