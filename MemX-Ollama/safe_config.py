"""
安全配置模块
提供安全的账号密码管理和API密钥存储

使用方法：
1. 设置环境变量存储敏感信息
2. 使用SafeConfig类读取配置
3. 不要在代码中硬编码任何敏感信息
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from getpass import getpass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SafeConfig:
    """
    安全配置管理类
    所有敏感信息通过环境变量或用户输入获取，不存储在代码中
    """

    def __init__(self):
        self.config_file = os.path.join(os.path.dirname(__file__), "config", "user_config.json")
        self.credentials = {}
        self._load_config()

    def _load_config(self):
        """从配置文件加载配置（不包含敏感信息）"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.credentials = config.get("credentials", {})
                    logger.info("配置文件加载成功")
            except Exception as e:
                logger.warning(f"配置文件加载失败：{str(e)}")

    def save_config(self):
        """保存配置到文件（不包含密码）"""
        config_dir = os.path.dirname(self.config_file)
        os.makedirs(config_dir, exist_ok=True)

        # 只保存非敏感配置
        public_config = {
            "credentials": {
                k: "***MASKED***" if v else "" for k, v in self.credentials.items()
            }
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(public_config, f, indent=2, ensure_ascii=False)
            logger.info("配置保存成功")
        except Exception as e:
            logger.error(f"配置保存失败：{str(e)}")

    def get_xbk_credentials(self) -> Dict[str, Any]:
        """
        获取西部宽客账号凭证（通过用户输入或环境变量）

        Returns:
            包含用户名和密码的字典
        """
        credentials = {
            "username": os.getenv("XBK_USERNAME"),
            "password": os.getenv("XBK_PASSWORD"),
            "api_key": os.getenv("XBK_API_KEY"),
            "api_secret": os.getenv("XBK_API_SECRET")
        }

        # 如果环境变量未设置，提示用户输入
        if not credentials["username"]:
            logger.info("请输入西部宽客账号用户名：")
            credentials["username"] = input().strip()

        if not credentials["password"]:
            logger.info("请输入西部宽客账号密码：")
            credentials["password"] = getpass().strip()

        return credentials

    def set_xbk_credentials(self, username: str, password: str, api_key: str = "", api_secret: str = ""):
        """
        设置西部宽客账号凭证（仅保存在内存中，不写入磁盘）

        Args:
            username: 用户名
            password: 密码
            api_key: API密钥（可选）
            api_secret: API密钥（可选）
        """
        self.credentials["xbk_username"] = username
        self.credentials["xbk_password"] = password
        self.credentials["xbk_api_key"] = api_key
        self.credentials["xbk_api_secret"] = api_secret
        logger.info("凭证已设置（仅保存在内存中）")

    def clear_credentials(self):
        """清除所有凭证信息"""
        self.credentials = {}
        logger.info("所有凭证已清除")

    def get_env_config(self) -> Dict[str, str]:
        """
        获取环境变量配置

        Returns:
            环境变量字典
        """
        return {
            "XBK_USERNAME": os.getenv("XBK_USERNAME", ""),
            "XBK_PASSWORD": os.getenv("XBK_PASSWORD", ""),
            "XBK_API_KEY": os.getenv("XBK_API_KEY", ""),
            "XBK_API_SECRET": os.getenv("XBK_API_SECRET", ""),
            "XBK_API_URL": os.getenv("XBK_API_URL", "https://api.xbk.com"),
            "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            "REDIS_HOST": os.getenv("REDIS_HOST", "localhost"),
            "REDIS_PORT": os.getenv("REDIS_PORT", "6379"),
        }

    def set_env_config(self, key: str, value: str):
        """
        设置环境变量配置

        Args:
            key: 环境变量名
            value: 环境变量值
        """
        os.environ[key] = value
        logger.info(f"环境变量 {key} 已设置")

    def validate_credentials(self, credentials: Dict[str, str]) -> bool:
        """
        验证凭证是否完整

        Args:
            credentials: 凭证字典

        Returns:
            凭证是否完整
        """
        required = ["username", "password"]
        for key in required:
            if not credentials.get(key):
                logger.warning(f"缺少必需凭证：{key}")
                return False
        return True

class SecurityManager:
    """
    安全管理系统
    提供防钓鱼和风控功能
    """

    def __init__(self):
        self.max_single_loss = 0.02  # 最大单笔亏损比例
        self.max_daily_loss = 0.05   # 最大日亏损比例
        self.max_position_ratio = 0.1  # 最大持仓比例
        self.trade_count = 0
        self.daily_trade_count = 0
        self.last_trade_date = None
        self.daily_loss = 0.0

    def check_trade_permission(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        account_balance: float
    ) -> Dict[str, Any]:
        """
        检查交易权限

        Args:
            symbol: 交易对符号
            side: 交易方向（buy/sell）
            quantity: 数量
            price: 价格
            account_balance: 账户余额

        Returns:
            检查结果字典
        """
        # 检查日期，清零日计数
        current_date = strftime("%Y-%m-%d")
        if self.last_trade_date != current_date:
            self.daily_trade_count = 0
            self.daily_loss = 0.0
            self.last_trade_date = current_date

        # 计算交易金额
        trade_value = quantity * price

        # 检查持仓比例
        position_ratio = trade_value / account_balance if account_balance > 0 else 1.0
        if position_ratio > self.max_position_ratio:
            return {
                "allowed": False,
                "reason": f"持仓比例超过限制：{position_ratio:.2%} > {self.max_position_ratio:.2%}"
            }

        # 检查日交易次数
        if self.daily_trade_count >= 100:
            return {
                "allowed": False,
                "reason": f"日交易次数超限：{self.daily_trade_count} >= 100"
            }

        # 检查是否为高风险交易
        high_risk_symbols = ["DOGE", "SHIB", "PEPE"]
        if symbol in high_risk_symbols and position_ratio > 0.05:
            return {
                "allowed": False,
                "reason": f"高风险币种持仓比例限制：{symbol}"
            }

        # 所有检查通过
        return {
            "allowed": True,
            "reason": "检查通过"
        }

    def record_trade(self, symbol: str, side: str, quantity: float, price: float, pnl: float = 0.0):
        """
        记录交易

        Args:
            symbol: 交易对符号
            side: 交易方向
            quantity: 数量
            price: 价格
            pnl: 盈亏
        """
        self.trade_count += 1
        self.daily_trade_count += 1

        if pnl < 0:
            self.daily_loss += abs(pnl)

        logger.info(f"交易记录：{side} {symbol} {quantity}@{price}，盈亏：{pnl}")

    def check_phishing(self, url: str, domain: str) -> bool:
        """
        检查钓鱼风险

        Args:
            url: 访问的URL
            domain: 预期的合法域名

        Returns:
            是否存在钓鱼风险
        """
        # 检查URL是否包含可疑字符
        suspicious_patterns = ["\\", "//", "@", "?", "=", "&"]
        for pattern in suspicious_patterns:
            if pattern in url and url.count(pattern) > 1:
                logger.warning(f"检测到可疑URL模式：{url}")
                return True

        # 检查域名是否匹配
        if domain not in url:
            logger.warning(f"域名不匹配，预期：{domain}，实际：{url}")
            return True

        return False

    def reset_daily_stats(self):
        """重置日统计数据"""
        self.daily_trade_count = 0
        self.daily_loss = 0.0
        self.last_trade_date = None

from time import strftime

# 全局实例
safe_config = SafeConfig()
security_manager = SecurityManager()

def get_safe_config() -> SafeConfig:
    """获取安全配置实例"""
    return safe_config

def get_security_manager() -> SecurityManager:
    """获取安全管理器实例"""
    return security_manager

if __name__ == "__main__":
    # 测试代码
    config = SafeConfig()

    # 测试获取凭证（会提示用户输入）
    # credentials = config.get_xbk_credentials()
    # print(f"凭证：{credentials}")

    # 测试安全检查
    security = SecurityManager()
    check_result = security.check_trade_permission(
        symbol="BTCUSDT",
        side="buy",
        quantity=0.1,
        price=47000,
        account_balance=100000
    )
    print(f"交易权限检查：{check_result}")
