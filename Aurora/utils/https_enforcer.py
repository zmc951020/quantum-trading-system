"""HTTPS强制执行器
P1-6修补项 - 生产环境HTTPS/TLS强制执行
部署前必须启用，确保所有API流量加密传输
"""
import logging, ssl, os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

RECOMMENDED_CIPHERS = (
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256"
)

class HTTPSEnforcer:
    """HTTPS 强制执行器

    用途：
    - 开发环境：记录HTTPS缺失警告
    - 生产环境：强制重定向到HTTPS，拒绝明文请求
    """

    def __init__(self, strict_mode=None):
        self.strict_mode = strict_mode if strict_mode is not None else (
            os.getenv("AURORA_ENV", "development") == "production"
        )
        logger.info(f"HTTPSEnforcer 初始化: strict_mode={self.strict_mode}")

    def enforce(self, request_scheme="http", request_path="/"):
        """检查请求是否使用HTTPS"""
        if request_scheme == "https":
            return True, None

        msg = f"检测到明文HTTP请求: {request_path}"
        if self.strict_mode:
            logger.critical(f"[安全阻断] {msg} - 生产环境禁止HTTP")
            return False, {
                "status": "403",
                "body": '{"error":"HTTPS required","message":"请使用HTTPS访问Aurora系统，HTTP请求已被阻断"}',
                "headers": [("Content-Type", "application/json")]
            }
        else:
            logger.warning(f"[安全警告] {msg} - 开发环境仅记录日志")
            return True, None

    def get_ssl_context(self, cert_file=None, key_file=None):
        """获取推荐的SSL上下文配置"""
        cert_path = cert_file or os.getenv("AURORA_SSL_CERT", "/etc/ssl/aurora/cert.pem")
        key_path = key_file or os.getenv("AURORA_SSL_KEY", "/etc/ssl/aurora/key.pem")

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            logger.warning(f"SSL证书文件缺失: cert={cert_path}, key={key_path}")
            return ssl.create_default_context()

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        context.set_ciphers(RECOMMENDED_CIPHERS)
        context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        context.verify_mode = ssl.CERT_REQUIRED

        logger.info(f"SSL上下文已配置: TLSv1.2+, 证书={cert_path}")
        return context

class HSTSEnforcer:
    """HTTP Strict Transport Security 辅助器"""

    MAX_AGE = 31536000
    INCLUDE_SUBDOMAINS = True
    PRELOAD = True

    @classmethod
    def get_hsts_header(cls):
        header = f"max-age={cls.MAX_AGE}"
        if cls.INCLUDE_SUBDOMAINS:
            header += "; includeSubDomains"
        if cls.PRELOAD:
            header += "; preload"
        return header

https_enforcer = HTTPSEnforcer()
hsts = HSTSEnforcer()