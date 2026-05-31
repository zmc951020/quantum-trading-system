"""交易验证器 - TradeSecurityValidator
从 trade_security.py 拆分，负责交易权限验证、熔断机制检查、交易时段控制
"""
import os, json, logging
from datetime import datetime, time as dt_time
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TradeSecurityValidator:
    def __init__(self, config_path="trade_security_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.trade_history = []

    def _load_config(self):
        default = {"ip_whitelist":[],"api_keys":[],"trading_hours":{"morning_start":"09:30","morning_end":"11:30","afternoon_start":"13:00","afternoon_end":"15:00"},"circuit_breaker":{"enabled":True,"max_daily_loss":100000,"max_consecutive_losses":5},"max_single_order_amount":1000000}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path,"r",encoding="utf-8") as f:
                    default.update(json.load(f))
            except: pass
        return default

    def _save_config(self):
        try:
            with open(self.config_path,"w",encoding="utf-8") as f:
                json.dump(self.config,f,indent=2,ensure_ascii=False)
        except: pass

    def validate_trade(self, order_info):
        ip = order_info.get("ip",""); api_key = order_info.get("api_key","")
        amount = order_info.get("amount",0); checks = {}
        checks["ip_whitelist"] = self._check_ip_whitelist(ip)
        if not checks["ip_whitelist"]["allowed"]: return {"allowed":False,"reason":checks["ip_whitelist"]["reason"],"checks":checks}
        checks["api_key"] = self._check_api_key(api_key)
        if not checks["api_key"]["allowed"]: return {"allowed":False,"reason":checks["api_key"]["reason"],"checks":checks}
        checks["trading_hours"] = self._check_trading_hours()
        if not checks["trading_hours"]["allowed"]: return {"allowed":False,"reason":checks["trading_hours"]["reason"],"checks":checks}
        checks["order_amount"] = self._check_order_amount(amount)
        if not checks["order_amount"]["allowed"]: return {"allowed":False,"reason":checks["order_amount"]["reason"],"checks":checks}
        checks["circuit_breaker"] = self._check_circuit_breaker()
        if not checks["circuit_breaker"]["allowed"]: return {"allowed":False,"reason":checks["circuit_breaker"]["reason"],"checks":checks}
        self._record_trade(order_info)
        return {"allowed":True,"reason":"OK","checks":checks}

    def _check_ip_whitelist(self, ip):
        wl = self.config.get("ip_whitelist",[])
        if not wl: return {"allowed":True,"reason":"白名单为空"}
        for item in wl:
            if (isinstance(item,dict) and item.get("ip")==ip) or (isinstance(item,str) and item==ip):
                return {"allowed":True,"reason":f"IP {ip} 在白名单"}
        return {"allowed":False,"reason":f"IP {ip} 不在白名单"}

    def _check_api_key(self, api_key):
        keys = self.config.get("api_keys",[])
        if not keys: return {"allowed":True,"reason":"Key列表为空"}
        for item in keys:
            if (isinstance(item,dict) and item.get("key")==api_key) or (isinstance(item,str) and item==api_key):
                return {"allowed":True,"reason":"Key有效"}
        return {"allowed":False,"reason":"无效Key"}

    def _check_trading_hours(self):
        h = self.config.get("trading_hours",{})
        ms = dt_time.fromisoformat(h.get("morning_start","09:30"))
        me = dt_time.fromisoformat(h.get("morning_end","11:30"))
        a_s = dt_time.fromisoformat(h.get("afternoon_start","13:00"))
        ae = dt_time.fromisoformat(h.get("afternoon_end","15:00"))
        now = datetime.now().time()
        if (ms <= now <= me) or (a_s <= now <= ae):
            return {"allowed":True,"reason":f"时段内 {now.strftime('%H:%M')}"}
        return {"allowed":False,"reason":f"非交易时段 {now.strftime('%H:%M')}"}

    def _check_order_amount(self, amount):
        max_a = self.config.get("max_single_order_amount",1000000)
        if amount <= max_a: return {"allowed":True,"reason":f"金额{amount}在限额内"}
        return {"allowed":False,"reason":f"金额{amount}超上限{max_a}"}

    def _check_circuit_breaker(self):
        cb = self.config.get("circuit_breaker",{})
        if not cb.get("enabled",True): return {"allowed":True,"reason":"熔断未启用"}
        today = datetime.now().strftime("%Y-%m-%d")
        losses = sum(1 for t in self.trade_history if t.get("date")==today and t.get("pnl",0)<0)
        if losses >= cb.get("max_consecutive_losses",5):
            return {"allowed":False,"reason":f"连续亏损{losses}次触发熔断"}
        return {"allowed":True,"reason":"熔断通过"}

    def _record_trade(self, order_info):
        now = datetime.now()
        self.trade_history.append({"timestamp":now.timestamp(),"date":now.strftime("%Y-%m-%d"),"symbol":order_info.get("symbol"),"amount":order_info.get("amount"),"side":order_info.get("side"),"ip":order_info.get("ip"),"user_id":order_info.get("user_id")})
        if len(self.trade_history)>1000: self.trade_history = self.trade_history[-1000:]

    def add_trusted_ip(self, ip, description=None):
        if "ip_whitelist" not in self.config: self.config["ip_whitelist"]=[]
        if not any((isinstance(i,dict)and i.get("ip")==ip)or(isinstance(i,str)and i==ip) for i in self.config["ip_whitelist"]):
            self.config["ip_whitelist"].append({"ip":ip,"description":description or "交易服务器","added_at":datetime.now().isoformat()})
            self._save_config()
            return {"success":True,"message":f"IP {ip} 已添加"}
        return {"success":False,"message":"已存在"}

    def add_valid_api_key(self, api_key, name=None):
        if "api_keys" not in self.config: self.config["api_keys"]=[]
        if not any((isinstance(i,dict)and i.get("key")==api_key)or(isinstance(i,str)and i==api_key) for i in self.config["api_keys"]):
            self.config["api_keys"].append({"key":api_key,"name":name or "交易API","added_at":datetime.now().isoformat()})
            self._save_config()
            return {"success":True,"message":"Key已添加"}
        return {"success":False,"message":"已存在"}

trade_validator = TradeSecurityValidator()