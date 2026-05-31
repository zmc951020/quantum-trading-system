# coding: utf-8
"""
密钥管理器 — 杜绝硬编码密钥
============================
所有敏感配置（API Key / Secret / Token / 数据库密码等）
必须在运行时从环境变量或加密存储加载，禁止以明文硬编码在源码中。

功能：
  - 从环境变量 / .env 文件 / HashiCorp Vault 加载密钥
  - Key-Value 单一入口，全项目通过此模块获取密钥
  - 启动时 BANNER 检查：若任一批次密钥为空则打印告警并退出
  - 运行时不允许修改密钥（Thread-safe 只读缓存）
  - 支持密钥轮换：更新环境变量后调用 reload() 重新加载
  - 所有密钥值在 log 中自动脱敏（只打印 KEY_NAME=***）

使用方式：
    from config.secrets_manager import SecretsManager
    sm = SecretsManager()
    sm.load_from_env()
    deepseek_api_key = sm.get("DEEPSEEK_API_KEY")
"""

import logging
import os
import threading
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ─── 已知必需密钥列表（按模块分类） ───
REQUIRED_KEYS: Dict[str, str] = {
    # 核心AI
    "DEEPSEEK_API_KEY": "DeepSeek AI 引擎访问令牌",
    "DEEPSEEK_API_SECRET": "DeepSeek API Secret（可选）",
    # 数据库
    "DATABASE_URL": "数据库连接字符串 (PostgreSQL/SQLite)",
    "DATABASE_PASSWORD": "数据库密码（若使用PostgreSQL）",
    # 消息推送
    "WEWORK_WEBHOOK_URL": "企业微信机器人Webhook地址",
    "WEWORK_BOT_KEY": "企业微信机器人密钥",
    # API认证
    "JWT_SECRET_KEY": "JWT Token 签名密钥 (HS256 至少32字节)",
    "API_SIGN_SECRET": "API接口签名 HMAC 密钥",
    # 券商API
    "BROKER_API_KEY": "券商API Key",
    "BROKER_API_SECRET": "券商API Secret",
    # 数据源
    "TUSHARE_TOKEN": "Tushare Pro Token",
    "AKSHARE_TOKEN": "AKShare Token（可选）",
    "YAHOO_FINANCE_API_KEY": "Yahoo Finance API Key（可选）",
    # 系统安全
    "ENCRYPTION_KEY": "数据加密主密钥 (AES-256-GCM)",
    "CSRF_SECRET": "CSRF Token Secret",
    "SESSION_SECRET": "Session 加密密钥",
}

# ─── 可选密钥（不加载只告警） ───
OPTIONAL_KEYS: Set[str] = {
    "DEEPSEEK_API_SECRET",
    "AKSHARE_TOKEN",
    "YAHOO_FINANCE_API_KEY",
    "DATABASE_PASSWORD",
}


class SecretsManager:
    """
    密钥管理器 — 单例模式，线程安全

    生命周期：
        sm = SecretsManager()
        sm.load_from_env()           # 加载所有必需密钥
        sm.validate()                # 校验完整性（缺失致命密钥则抛 RuntimeError）
        deepseek_key = sm.get("DEEPSEEK_API_KEY")
    """

    _instance: Optional["SecretsManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._secrets: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._loaded = False
        self._missing_keys: Set[str] = set()
        self._warned_keys: Set[str] = set()

    # ────────── 加载 ──────────

    def load_from_env(self, env_prefix: str = "", dotenv_path: Optional[str] = None) -> "SecretsManager":
        """
        从环境变量加载所有密钥。

        Args:
            env_prefix: 环境变量前缀（如 "AURORA_"），无前缀则直接用 KEY 名匹配
            dotenv_path: .env 文件路径（默认从项目根目录找）

        Returns:
            self（支持链式调用）
        """
        with self._lock:
            # 尝试加载 .env 文件（若 dotenv 可用）
            if dotenv_path is None:
                dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            try:
                from dotenv import load_dotenv
                if os.path.exists(dotenv_path):
                    load_dotenv(dotenv_path)
                    logger.info("已从 %s 加载环境变量", dotenv_path)
            except ImportError:
                logger.debug("python-dotenv 不可用，跳过 .env 加载")

            self._secrets = {}
            self._missing_keys = set()
            self._warned_keys = set()

            for key, description in REQUIRED_KEYS.items():
                env_key = f"{env_prefix}{key}" if env_prefix else key
                value = os.environ.get(env_key) or os.environ.get(key)
                if value:
                    self._secrets[key] = value
                else:
                    if key in OPTIONAL_KEYS:
                        self._warned_keys.add(key)
                    else:
                        self._missing_keys.add(key)

            self._loaded = True
            loaded_count = len(self._secrets)
            logger.info(f"密钥加载完成: {loaded_count}/{len(REQUIRED_KEYS)} 已配置"
                        f"（缺失: {len(self._missing_keys)}, 可选未配: {len(self._warned_keys)}）")
            return self

    def load_from_vault(self, vault_addr: str, vault_token: str, vault_path: str = "secret/aurora") -> "SecretsManager":
        """
        从 HashiCorp Vault 加载密钥。

        Args:
            vault_addr: Vault 服务地址
            vault_token: Vault 认证 Token
            vault_path: 密钥存储路径

        Returns:
            self
        """
        import requests
        with self._lock:
            try:
                headers = {"X-Vault-Token": vault_token}
                resp = requests.get(
                    f"{vault_addr.rstrip('/')}/v1/{vault_path.strip('/')}",
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("data", {})
                self._secrets.update({k: v for k, v in data.items() if k in REQUIRED_KEYS})
                self._loaded = True
                logger.info(f"已从 Vault 加载 {len(self._secrets)} 个密钥")
            except Exception as e:
                logger.error(f"Vault 加载失败: {e}")
                raise RuntimeError(f"Vault 密钥加载失败: {e}") from e
            return self

    def load_as_fallback(self, **kwargs: str) -> "SecretsManager":
        """
        手动注入密钥（仅用于开发/测试，生产禁用）。

        Args:
            **kwargs: key=value 对，仅覆盖未加载的必需密钥
        """
        with self._lock:
            for key, value in kwargs.items():
                if key in REQUIRED_KEYS and key not in self._secrets:
                    self._secrets[key] = value
            if not self._loaded:
                self._loaded = True
            return self

    # ────────── 访问 ──────────

    def get(self, key: str, default: Any = None) -> Optional[str]:
        """
        获取密钥值。

        Args:
            key: 密钥名
            default: 缺失时返回的默认值

        Returns:
            密钥值或 default
        """
        if not self._loaded:
            raise RuntimeError("SecretManager 尚未加载，请先调用 load_from_env()")
        return self._secrets.get(key, default)

    def __getitem__(self, key: str) -> str:
        val = self.get(key)
        if val is None:
            raise KeyError(f"密钥 '{key}' 未配置")
        return val

    def __contains__(self, key: str) -> bool:
        return key in self._secrets

    def all_keys(self) -> Set[str]:
        """返回所有已配置的密钥名"""
        return set(self._secrets.keys())

    # ────────── 验证 ──────────

    def validate(self, strict: bool = True) -> Dict[str, Any]:
        """
        校验密钥完整性。

        Args:
            strict: True=缺失必需密钥则抛 RuntimeError; False=仅返回报告

        Returns:
            {
                'ok': bool,
                'loaded': int,
                'missing': [str, ...],
                'warned': [str, ...],
                'messages': [str, ...]
            }
        """
        result = {
            "ok": len(self._missing_keys) == 0,
            "loaded": len(self._secrets),
            "missing": sorted(self._missing_keys),
            "warned": sorted(self._warned_keys),
            "messages": [],
        }

        for key in sorted(self._missing_keys):
            msg = f"❌ 缺失必需密钥: {key} ({REQUIRED_KEYS.get(key, '未知')})"
            result["messages"].append(msg)
            logger.error(msg)

        for key in sorted(self._warned_keys):
            msg = f"⚠️ 可选密钥未配置: {key} ({REQUIRED_KEYS.get(key, '未知')})"
            result["messages"].append(msg)
            logger.warning(msg)

        if result["ok"]:
            logger.info("✅ 密钥完整性校验通过 (%d/%d)", len(self._secrets), len(REQUIRED_KEYS))
        elif strict:
            raise RuntimeError(
                f"密钥完整性校验失败！缺失 {len(self._missing_keys)} 个必需密钥: "
                f"{', '.join(sorted(self._missing_keys))}"
            )

        return result

    # ────────── 轮换 ──────────

    def reload(self) -> "SecretsManager":
        """重新加载所有密钥（用于密钥轮换后）"""
        logger.info("密钥轮换 — 重新加载环境变量...")
        old_keys = set(self._secrets.keys())
        self.load_from_env()
        new_keys = set(self._secrets.keys())
        changed = old_keys.symmetric_difference(new_keys)
        if changed:
            logger.warning("密钥变更: %s", ", ".join(sorted(changed)))
        return self

    def mask_value(self, key: str) -> str:
        """返回密钥名的脱敏表示（仅用于日志打印）"""
        return f"{key}=***"

    def __repr__(self) -> str:
        return f"<SecretsManager: {len(self._secrets)} keys loaded>"


# ─── 便捷函数 ───

def get_secret(key: str, default: Any = None) -> Optional[str]:
    """获取密钥的快捷函数"""
    return SecretsManager().get(key, default)