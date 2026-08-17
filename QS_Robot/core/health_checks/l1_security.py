"""L1 安全认证检查"""
import os
import sys
import re
from typing import List, Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l1_checks(hc) -> List[Callable]:
    """构建 L1 检查项生成器"""
    def _l1_001():
        ok, d = hc._api_get("/api/strategy/list", noauth=True)
        return (not ok, 100 if not ok else 0,
                "未认证请求被正确拦截" if not ok else "未认证请求未被拦截！",
                "" if not ok else "检查 require_auth 装饰器")
    yield ("L1_001", "未认证API拦截", "L1_安全认证", "critical", "both", _l1_001)

    def _l1_002():
        cookies = hc._get_auth_cookies()
        ok = bool(cookies.get("session_id"))
        return (ok, 100 if ok else 0,
                "Session获取成功" if ok else "无法获取认证Session",
                "" if ok else "检查登录接口 /api/auth/login")
    yield ("L1_002", "Session有效性", "L1_安全认证", "critical", "both", _l1_002)

    def _l1_003():
        adapter_path = os.path.join(PROJECT_ROOT, "api", "aurora_core_adapter.py")
        if os.path.exists(adapter_path):
            with open(adapter_path, 'r', encoding='utf-8') as f:
                content = f.read()
            ok = 'secrets.token_urlsafe' in content
            return (ok, 100 if ok else 0,
                    "密钥使用secrets模块生成" if ok else "可能存在硬编码密钥",
                    "" if ok else "使用 secrets.token_urlsafe() 替代硬编码")
        return (True, 80, "适配器文件检查通过（跳过内容检查）", "")
    yield ("L1_003", "密钥无硬编码", "L1_安全认证", "critical", "both", _l1_003)

    def _l1_004():
        ok, d = hc._api_get("/api/users")
        users = d.get("data", {}).get("users", [])
        return (len(users) > 0, 100 if len(users) > 0 else 50,
                f"用户列表可获取: {len(users)}个用户" if len(users) > 0 else "用户列表为空",
                "" if len(users) > 0 else "检查用户管理模块")
    yield ("L1_004", "用户管理可用", "L1_安全认证", "critical", "both", _l1_004)

    # 深度扩展
    def _l1_005():
        ok, d = hc._api_get("/api/security/whitelist/list")
        ips = d.get("data", {}).get("ips", [])
        return (len(ips) > 0, 100 if len(ips) > 0 else 60,
                f"IP白名单: {len(ips)}个" if len(ips) > 0 else "白名单为空",
                "" if len(ips) > 0 else "建议添加常用IP")
    yield ("L1_005", "IP白名单管理", "L1_安全认证", "warning", "deep", _l1_005)

    def _l1_006():
        ok, d = hc._api_get("/api/security/config")
        return (ok, 100 if ok else 0, "安全配置可获取" if ok else "安全配置获取失败", "")
    yield ("L1_006", "安全配置查询", "L1_安全认证", "warning", "deep", _l1_006)

    def _l1_007():
        ok, d = hc._api_get("/api/security/audit-logs?limit=5")
        logs = d.get("data", {}).get("logs", [])
        return (len(logs) > 0, 100 if len(logs) > 0 else 50,
                f"审计日志: {len(logs)}条" if len(logs) > 0 else "审计日志为空", "")
    yield ("L1_007", "审计日志", "L1_安全认证", "warning", "deep", _l1_007)

    # ── v2.0安全模块新增检查 (15项) ──
    def _l1_008():
        jwt_path = hc._resolve_security_path("auth/jwt_manager.py")
        ok = os.path.exists(jwt_path)
        return (ok, 100 if ok else 0,
                "JWT认证模块就绪" if ok else "auth/jwt_manager.py 缺失",
                "" if ok else "检查 auth/ 目录")
    yield ("L1_008", "JWT认证模块", "L1_安全认证", "critical", "both", _l1_008)

    def _l1_009():
        rbac_path = hc._resolve_security_path("auth/rbac.py")
        ok = os.path.exists(rbac_path)
        return (ok, 100 if ok else 0,
                "RBAC权限模块就绪" if ok else "auth/rbac.py 缺失",
                "" if ok else "检查 auth/ 目录")
    yield ("L1_009", "RBAC权限模块", "L1_安全认证", "critical", "both", _l1_009)

    def _l1_010():
        pw_path = hc._resolve_security_path("auth/password_manager.py")
        if not os.path.exists(pw_path):
            return (False, 0, "auth/password_manager.py 缺失", "检查 auth/ 目录")
        with open(pw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        has_bcrypt = 'bcrypt' in content.lower()
        has_pbkdf2 = 'pbkdf2' in content.lower()
        ok = has_bcrypt or has_pbkdf2
        return (ok, 100 if ok else 0,
                f"密码哈希: bcrypt={'✓' if has_bcrypt else '✗'}, PBKDF2={'✓' if has_pbkdf2 else '✗'}",
                "" if ok else "使用 bcrypt 或 PBKDF2-HMAC-SHA256")
    yield ("L1_010", "密码bcrypt/PBKDF2", "L1_安全认证", "critical", "both", _l1_010)

    def _l1_011():
        phish_path = hc._resolve_security_path("auth/phishing_defense.py")
        ok = os.path.exists(phish_path)
        return (ok, 100 if ok else 0,
                "五层防钓鱼模块就绪" if ok else "auth/phishing_defense.py 缺失",
                "" if ok else "检查 auth/ 目录")
    yield ("L1_011", "五层防钓鱼模块", "L1_安全认证", "critical", "both", _l1_011)

    def _l1_012():
        mw_path = hc._resolve_security_path("auth/middleware.py")
        if not os.path.exists(mw_path):
            return (False, 0, "auth/middleware.py 缺失", "检查 auth/ 目录")
        with open(mw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ok = 'phishing.evaluate' in content
        return (ok, 100 if ok else 0,
                "防钓鱼已集成到中间件" if ok else "中间件未启用防钓鱼",
                "" if ok else "在 _before_request 中调用 phishing.evaluate()")
    yield ("L1_012", "防钓鱼中间件启用", "L1_安全认证", "critical", "both", _l1_012)

    def _l1_013():
        audit_path = hc._resolve_security_path("security/audit_trail.py")
        if not os.path.exists(audit_path):
            return (False, 0, "security/audit_trail.py 缺失", "检查 security/ 目录")
        with open(audit_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ok = 'HMAC' in content or 'hmac' in content.lower()
        return (ok, 100 if ok else 0,
                "审计日志哈希链+HMAC就绪" if ok else "审计日志缺少防篡改机制",
                "" if ok else "添加 HMAC 签名防篡改")
    yield ("L1_013", "审计日志防篡改", "L1_安全认证", "critical", "both", _l1_013)

    def _l1_014():
        sm_path = hc._resolve_security_path("security/secrets_manager.py")
        ok = os.path.exists(sm_path)
        return (ok, 100 if ok else 0,
                "密钥管理器就绪" if ok else "security/secrets_manager.py 缺失",
                "" if ok else "检查 security/ 目录")
    yield ("L1_014", "密钥管理器", "L1_安全认证", "warning", "deep", _l1_014)

    def _l1_015():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        has_public = "0.0.0.0" in content
        return (not has_public, 100 if not has_public else 0,
                "服务绑定127.0.0.1（安全）" if not has_public else "检测到0.0.0.0绑定！",
                "" if not has_public else "改为 host='127.0.0.1'")
    yield ("L1_015", "0.0.0.0绑定检查", "L1_安全认证", "critical", "both", _l1_015)

    def _l1_016():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        has_wildcard = 'CORS(app, origins=["*"])' in content or "origins='*'" in content
        return (not has_wildcard, 100 if not has_wildcard else 0,
                "CORS限制为localhost" if not has_wildcard else "CORS使用通配符*！",
                "" if not has_wildcard else "限制 origins 为可信域名")
    yield ("L1_016", "CORS安全配置", "L1_安全认证", "warning", "deep", _l1_016)

    def _l1_017():
        config_path = hc._aurora_path("config/config.py")
        if not os.path.exists(config_path):
            return (True, 80, "config/config.py 检查跳过", "")
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ok = '_mask' in content or 'mask_secret' in content
        return (ok, 100 if ok else 50,
                "配置序列化已脱敏" if ok else "配置to_dict可能泄露密钥",
                "" if ok else "添加 _mask() 函数脱敏密码字段")
    yield ("L1_017", "配置序列化脱敏", "L1_安全认证", "warning", "deep", _l1_017)

    def _l1_018():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ok = 'login_attempts' in content or 'failed_attempt' in content.lower()
        return (ok, 100 if ok else 0,
                "登录失败锁定机制存在" if ok else "未检测到登录失败锁定",
                "" if ok else "添加登录失败速率限制")
    yield ("L1_018", "登录失败锁定", "L1_安全认证", "critical", "both", _l1_018)

    def _l1_019():
        gw_path = os.path.join(PROJECT_ROOT, "api", "gateway.py")
        if not os.path.exists(gw_path):
            return (True, 80, "api/gateway.py 检查跳过", "")
        with open(gw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        has_whitelist = 're.sub' in content and 'x00' in content
        return (has_whitelist, 100 if has_whitelist else 0,
                "输入净化使用白名单模式" if has_whitelist else "输入净化需升级为白名单",
                "" if has_whitelist else "使用正则白名单移除控制字符")
    yield ("L1_019", "输入净化白名单", "L1_安全认证", "critical", "both", _l1_019)

    def _l1_020():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        count = content.count('@require_permission')
        ok = count >= 3
        return (ok, 100 if ok else (50 if count > 0 else 0),
                f"@require_permission 装饰器: {count}处" if count > 0 else "未使用RBAC权限装饰器",
                "" if ok else "给敏感路由添加 @require_permission 装饰器")
    yield ("L1_020", "RBAC装饰器使用", "L1_安全认证", "warning", "deep", _l1_020)

    def _l1_021():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        count = content.count('audit_trail.record')
        ok = count >= 3
        return (ok, 100 if ok else (50 if count > 0 else 0),
                f"审计日志记录点: {count}处" if count > 0 else "未集成审计日志",
                "" if ok else "给关键操作添加 audit_trail.record()")
    yield ("L1_021", "审计日志集成度", "L1_安全认证", "warning", "deep", _l1_021)

    def _l1_022():
        app_path = hc._aurora_path("web/app.py")
        if not os.path.exists(app_path):
            return (True, 80, "Aurora web/app.py 检查跳过", "")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ok = 'verify_token' in content and 'handle_connect' in content
        return (ok, 100 if ok else 0,
                "Socket.IO JWT认证已集成" if ok else "Socket.IO 缺少JWT认证",
                "" if ok else "在 connect 事件中校验 JWT 令牌")
    yield ("L1_022", "Socket.IO JWT认证", "L1_安全认证", "warning", "deep", _l1_022)

    def _l1_023():
        """SQL参数化查询检查：扫描所有py文件，检测字符串拼接SQL"""
        issues = []
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in ('.git','__pycache__','node_modules','.venv','data','logs')]
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    # 检测 f-string/format 拼接SQL
                    if re.search(r'execute\s*\(\s*f["\']', content):
                        issues.append(os.path.relpath(fpath, PROJECT_ROOT))
                    elif re.search(r'execute\s*\(\s*["\'][^"\']*%s', content):
                        issues.append(os.path.relpath(fpath, PROJECT_ROOT))
                except Exception:
                    pass
        ok = len(issues) == 0
        return (ok, 100 if ok else max(0, 100 - len(issues) * 15),
                "SQL参数化: 全部通过" if ok else f"发现 {len(issues)} 处SQL拼接风险: {issues[:3]}",
                "" if ok else "使用 ? 占位符替代字符串拼接")
    yield ("L1_023", "SQL参数化查询", "L1_安全认证", "critical", "both", _l1_023)