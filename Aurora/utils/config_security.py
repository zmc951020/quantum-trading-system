"""配置安全审计
P3-2修补项 - 敏感配置加密/环境变量校验/配置备份
"""
import os, re, hashlib, json
from datetime import datetime

SENSITIVE_KEYWORDS = [
    "api_key", "apikey", "secret", "password", "token",
    "private_key", "access_key", "auth", "credential",
    "jwt_secret", "encryption_key", "db_password", "redis_password"
]

def mask_value(key, value):
    lower = key.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in lower:
            if isinstance(value, str) and len(value) > 8:
                return value[:4] + "****" + value[-4:]
            elif isinstance(value, str) and len(value) >= 3:
                return value[0] + "***"
            return "***HIDDEN***"
    return value

class ConfigSecurityAuditor:
    def __init__(self):
        self.findings = []

    def audit_env_file(self, path=".env"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            self.findings.append({"level": "WARN", "message": f"配置文件 {path} 不存在"})
            return self.findings

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key = stripped.split("=")[0].strip()
                lower_key = key.lower()
                for kw in SENSITIVE_KEYWORDS:
                    if kw in lower_key:
                        val = stripped.split("=", 1)[1].strip()
                        if val and val != "changeme" and val != "your_secret_here":
                            self.findings.append({"level": "INFO", "line": i, "key": key, "message": f"敏感配置已设置: {key}"})
                        else:
                            self.findings.append({"level": "CRITICAL", "line": i, "key": key, "message": f"敏感配置使用默认值: {key}"})

        unsafe_perms = os.stat(path).st_mode & 0o077
        if unsafe_perms:
            self.findings.append({"level": "WARN", "message": f".env 文件权限过宽: {oct(unsafe_perms)}"})

        return self.findings

    def check_env_variables(self):
        required = ["AURORA_ENV", "DEEPSEEK_API_KEY", "JWT_SECRET"]
        for var in required:
            val = os.getenv(var)
            if not val:
                self.findings.append({"level": "WARN", "message": f"环境变量 {var} 未设置"})
        return self.findings

auditor = ConfigSecurityAuditor()