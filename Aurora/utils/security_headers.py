"""安全响应头中间件
P2修补项 - CSRF/XSS/点击劫持/CORS/安全头
用于Aurora Web Dashboard和API
"""
import hashlib, hmac, time, logging
from typing import Optional

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://api.exchange.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

class SecurityHeadersMiddleware:
    def __init__(self, app, csp_policy=None):
        self.app = app
        SECURITY_HEADERS["Content-Security-Policy"] = csp_policy or CSP_POLICY

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            headers = list(headers)
            existing = {h[0].lower() for h in headers}
            for name, value in SECURITY_HEADERS.items():
                if name.lower() not in existing:
                    headers.append((name, value))
            return start_response(status, headers, exc_info)
        return self.app(environ, custom_start_response)

class CSRFValidator:
    def __init__(self, secret="aurora-csrf-secret"):
        self.secret = secret.encode() if isinstance(secret, str) else secret

    def generate_token(self, session_id):
        payload = f"{session_id}:{int(time.time())}"
        sig = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        return sig

    def validate_token(self, session_id, token):
        if not token or not session_id:
            return False
        expected = self.generate_token(session_id)
        return hmac.compare_digest(expected, token)

csrf_validator = CSRFValidator()
CSRF_TOKEN_HEADER = "X-CSRF-Token"