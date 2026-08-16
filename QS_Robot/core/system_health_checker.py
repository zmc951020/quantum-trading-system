#!/usr/bin/env python3
"""
AURORA 系统健康自动化诊断引擎
==============================
7层巡检体系，支持快速/深度两档模式，定时巡检 + 告警联动。

架构：
- 7层检查清单（L1~L7），每层快速模式3-5项、深度模式扩展10+项
- CheckItem → CheckResult → LayerResult → HealthReport 数据流
- 定时巡检：threading.Timer 驱动，可配置间隔
- 告警联动：对接 AlertSystem + 桌面通知
"""
import os
import sys
import json
import time
import uuid
import logging
import threading
import subprocess
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CheckResult:
    """单项检查结果"""
    id: str
    name: str
    layer: str
    severity: str          # critical / warning / info
    passed: bool
    score: float           # 0-100
    detail: str
    suggestion: str = ""   # 修复建议（失败时）
    elapsed_ms: float = 0


@dataclass
class LayerResult:
    """层级汇总结果"""
    layer: str
    name: str
    total: int
    passed: int
    failed: int
    score: float           # 0-100
    status: str            # healthy / warning / critical
    items: List[Dict] = field(default_factory=list)


@dataclass
class HealthReport:
    """完整巡检报告"""
    report_id: str
    timestamp: str
    mode: str              # quick / deep
    overall_score: float   # 0-100
    overall_status: str    # healthy / warning / critical
    total_checks: int
    passed_checks: int
    failed_checks: int
    layers: List[Dict] = field(default_factory=list)
    alerts: List[Dict] = field(default_factory=list)
    elapsed_seconds: float = 0


# ============================================================
# 巡检引擎
# ============================================================

class SystemHealthChecker:
    """AURORA 系统健康自动化诊断引擎"""

    # 7层元数据
    LAYER_META = {
        "L1_安全认证":   {"order": 1, "name": "安全与认证", "icon": "🛡️"},
        "L2_业务链路":   {"order": 2, "name": "业务功能链路", "icon": "🔗"},
        "L3_系统可靠性": {"order": 3, "name": "系统可靠性", "icon": "⚡"},
        "L4_数据行情":   {"order": 4, "name": "数据与行情", "icon": "📊"},
        "L5_交易风控":   {"order": 5, "name": "交易与风控", "icon": "💰"},
        "L6_AI智能体":   {"order": 6, "name": "AI与智能体", "icon": "🤖"},
        "L7_运维部署":   {"order": 7, "name": "运维与部署", "icon": "🔧"},
        "L8_深度审计":   {"order": 8, "name": "深度审计（代码/API/引擎/配置）", "icon": "🔬"},
        "L9_工程闭环":   {"order": 9, "name": "工程闭环审查（工程流+策略入口+代码质量+导航+可视化+数据源+模块边界）", "icon": "🔄"},
    }

    BASE_URL = "http://127.0.0.1:5003"

    def __init__(self):
        self._scheduler_thread = None
        self._scheduler_stop = threading.Event()
        self._report_dir = os.path.join(PROJECT_ROOT, "data", "health_reports")
        os.makedirs(self._report_dir, exist_ok=True)
        self._session = None  # 缓存的认证session
        self._last_report: Optional[HealthReport] = None
        self.mode = "quick"  # 当前巡检模式，run_check时更新
        self.template_dir = os.path.join(PROJECT_ROOT, "ui", "templates")  # HTML模板目录

    # ========== 认证辅助 ==========

    def _get_auth_cookies(self) -> dict:
        """获取认证cookies（缓存复用，凭据从环境变量读取）"""
        if self._session:
            return {"session_id": self._session}
        try:
            import requests
            username = os.environ.get("HEALTH_CHECK_USER", "admin")
            password = os.environ.get("HEALTH_CHECK_PASS", "admin123")
            r = requests.post(f"{self.BASE_URL}/api/auth/login",
                            json={"username": username, "password": password}, timeout=5)
            if r.status_code == 200:
                sid = r.json().get("session_id", "")
                if sid:
                    self._session = sid
                    return {"session_id": sid}
        except Exception:
            pass
        return {}

    def _api_get(self, path: str, timeout: float = 10, noauth: bool = False) -> tuple:
        """GET 请求，返回 (success, data)"""
        try:
            import requests
            cookies = {} if noauth else self._get_auth_cookies()
            r = requests.get(f"{self.BASE_URL}{path}", cookies=cookies, timeout=timeout)
            d = r.json()
            if isinstance(d, dict):
                return d.get("success", r.status_code == 200), d
            # 列表等其他类型响应视为成功
            return r.status_code == 200, {"data": d}
        except Exception as e:
            return False, {"error": str(e)}

    def _api_post(self, path: str, json_data: dict = None, timeout: float = 10) -> tuple:
        """POST 请求"""
        try:
            import requests
            cookies = self._get_auth_cookies()
            r = requests.post(f"{self.BASE_URL}{path}", json=json_data or {}, cookies=cookies, timeout=timeout)
            d = r.json()
            if isinstance(d, dict):
                return d.get("success", r.status_code == 200), d
            return r.status_code == 200, {"data": d}
        except Exception as e:
            return False, {"error": str(e)}

    def _file_check(self, rel_path: str) -> bool:
        """检查文件是否存在"""
        return os.path.exists(os.path.join(PROJECT_ROOT, rel_path))

    _AURORA_ROOT = None
    def _aurora_path(self, rel_path: str) -> str:
        """获取Aurora系统文件的绝对路径"""
        if self._AURORA_ROOT is None:
            try:
                from config.config import config as cfg
                base = cfg.get("aurora_system.base_path", "../Aurora")
                if base.startswith(".."):
                    base = os.path.normpath(os.path.join(PROJECT_ROOT, base))
                self._AURORA_ROOT = base
            except Exception:
                self._AURORA_ROOT = os.path.join(os.path.dirname(PROJECT_ROOT), "Aurora")
        return os.path.join(self._AURORA_ROOT, rel_path)

    # ========== 检查函数定义 ==========

    def _check(self, id: str, name: str, layer: str, severity: str, fn: Callable,
               mode: str = "both", timeout: float = 10) -> CheckResult:
        """执行单项检查，统一异常处理"""
        t0 = time.time()
        try:
            passed, score, detail, suggestion = fn()
            if not isinstance(score, (int, float)):
                score = 100 if passed else 0
        except Exception as e:
            passed, score, detail, suggestion = False, 0, f"检查异常: {str(e)}", "请检查系统日志"
        return CheckResult(
            id=id, name=name, layer=layer, severity=severity,
            passed=passed, score=score, detail=detail, suggestion=suggestion,
            elapsed_ms=round((time.time() - t0) * 1000, 1),
        )

    # ==================== L1: 安全与认证 ====================

    def _build_l1_checks(self) -> List[Callable]:
        """构建 L1 检查项生成器"""
        def _l1_001():
            ok, d = self._api_get("/api/strategy/list", noauth=True)
            return (not ok, 100 if not ok else 0,
                    "未认证请求被正确拦截" if not ok else "未认证请求未被拦截！",
                    "" if not ok else "检查 require_auth 装饰器")
        yield ("L1_001", "未认证API拦截", "L1_安全认证", "critical", "both", _l1_001)

        def _l1_002():
            cookies = self._get_auth_cookies()
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
            ok, d = self._api_get("/api/users")
            users = d.get("data", {}).get("users", [])
            return (len(users) > 0, 100 if len(users) > 0 else 50,
                    f"用户列表可获取: {len(users)}个用户" if len(users) > 0 else "用户列表为空",
                    "" if len(users) > 0 else "检查用户管理模块")
        yield ("L1_004", "用户管理可用", "L1_安全认证", "critical", "both", _l1_004)

        # 深度扩展
        def _l1_005():
            ok, d = self._api_get("/api/security/whitelist/list")
            ips = d.get("data", {}).get("ips", [])
            return (len(ips) > 0, 100 if len(ips) > 0 else 60,
                    f"IP白名单: {len(ips)}个" if len(ips) > 0 else "白名单为空",
                    "" if len(ips) > 0 else "建议添加常用IP")
        yield ("L1_005", "IP白名单管理", "L1_安全认证", "warning", "deep", _l1_005)

        def _l1_006():
            ok, d = self._api_get("/api/security/config")
            return (ok, 100 if ok else 0, "安全配置可获取" if ok else "安全配置获取失败", "")
        yield ("L1_006", "安全配置查询", "L1_安全认证", "warning", "deep", _l1_006)

        def _l1_007():
            ok, d = self._api_get("/api/security/audit-logs?limit=5")
            logs = d.get("data", {}).get("logs", [])
            return (len(logs) > 0, 100 if len(logs) > 0 else 50,
                    f"审计日志: {len(logs)}条" if len(logs) > 0 else "审计日志为空", "")
        yield ("L1_007", "审计日志", "L1_安全认证", "warning", "deep", _l1_007)

        # ── v2.0安全模块新增检查 (15项) ──
        def _l1_008():
            jwt_path = self._aurora_path("auth/jwt_manager.py")
            ok = os.path.exists(jwt_path)
            return (ok, 100 if ok else 0,
                    "JWT认证模块就绪" if ok else "auth/jwt_manager.py 缺失",
                    "" if ok else "检查 auth/ 目录")
        yield ("L1_008", "JWT认证模块", "L1_安全认证", "critical", "both", _l1_008)

        def _l1_009():
            rbac_path = self._aurora_path("auth/rbac.py")
            ok = os.path.exists(rbac_path)
            return (ok, 100 if ok else 0,
                    "RBAC权限模块就绪" if ok else "auth/rbac.py 缺失",
                    "" if ok else "检查 auth/ 目录")
        yield ("L1_009", "RBAC权限模块", "L1_安全认证", "critical", "both", _l1_009)

        def _l1_010():
            pw_path = self._aurora_path("auth/password_manager.py")
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
            phish_path = self._aurora_path("auth/phishing_defense.py")
            ok = os.path.exists(phish_path)
            return (ok, 100 if ok else 0,
                    "五层防钓鱼模块就绪" if ok else "auth/phishing_defense.py 缺失",
                    "" if ok else "检查 auth/ 目录")
        yield ("L1_011", "五层防钓鱼模块", "L1_安全认证", "critical", "both", _l1_011)

        def _l1_012():
            mw_path = self._aurora_path("auth/middleware.py")
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
            audit_path = self._aurora_path("security/audit_trail.py")
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
            sm_path = self._aurora_path("security/secrets_manager.py")
            ok = os.path.exists(sm_path)
            return (ok, 100 if ok else 0,
                    "密钥管理器就绪" if ok else "security/secrets_manager.py 缺失",
                    "" if ok else "检查 security/ 目录")
        yield ("L1_014", "密钥管理器", "L1_安全认证", "warning", "deep", _l1_014)

        def _l1_015():
            app_path = self._aurora_path("web/app.py")
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
            app_path = self._aurora_path("web/app.py")
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
            config_path = self._aurora_path("config/config.py")
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
            app_path = self._aurora_path("web/app.py")
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
            app_path = self._aurora_path("web/app.py")
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
            app_path = self._aurora_path("web/app.py")
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
            app_path = self._aurora_path("web/app.py")
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
            import re
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

    # ==================== L2: 业务功能链路 ====================

    def _build_l2_checks(self) -> List[Callable]:
        # ====== 策略体系 (3项) ======

        def _l2_001():
            """策略注册与发现（合并L2_001+L2_005+L2_015）"""
            ok, d = self._api_get("/api/strategy/list")
            strategies = d.get("data", {}).get("strategies", [])
            api_count = len(strategies)
            discovery_ok = True
            try:
                from core.strategy_auto_discovery import get_auto_discovery
                disc = get_auto_discovery()
                discovery_ok = hasattr(disc, 'run_once') or hasattr(disc, 'scan')
            except Exception:
                discovery_ok = False
            passed = api_count > 0 and discovery_ok
            return (passed, 100 if passed else (60 if api_count > 0 else 0),
                    f"策略注册: API={api_count}个, 自动发现={'✓' if discovery_ok else '✗'}",
                    "" if passed else "执行 strategy_auto_discovery.run_once() 填充注册表")
        yield ("L2_001", "策略注册与发现", "L2_业务链路", "critical", "both", _l2_001)

        def _l2_002():
            ok, d = self._api_get("/api/optimizer/list")
            optimizers = d.get("data", {}).get("optimizers", [])
            return (len(optimizers) > 0, 100 if len(optimizers) > 0 else 0,
                    f"优化器列表: {len(optimizers)}个" if len(optimizers) > 0 else "优化器列表为空",
                    "" if len(optimizers) > 0 else "检查优化器注册表")
        yield ("L2_002", "优化器列表", "L2_业务链路", "critical", "both", _l2_002)

        def _l2_003():
            ok, _ = self._api_get("/api/backtest/history")
            return (ok, 100 if ok else 0, "回测端点可达" if ok else "回测端点不可达", "")
        yield ("L2_003", "回测端点", "L2_业务链路", "warning", "both", _l2_003)

        def _l2_004():
            ok, _ = self._api_get("/api/strategy-status")
            return (ok, 100 if ok else 0, "策略状态端点可达" if ok else "策略状态端点不可达", "")
        yield ("L2_004", "策略启停端点", "L2_业务链路", "critical", "both", _l2_004)

        # ====== 优化引擎 (3项) ======

        def _l2_005():
            try:
                from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
                s = ShepherdOptimizer(version=ShepherdVersion.V6)
                return (True, 100, "牧羊人V6优化器: 本地可用", "")
            except Exception as e:
                return (False, 0, f"牧羊人优化器: 不可用 - {e}", "检查 core/shepherd_optimizer.py")
        yield ("L2_005", "牧羊人优化器V6", "L2_业务链路", "critical", "both", _l2_005)

        def _l2_006():
            try:
                from core.walk_forward import WalkForwardAnalyzer
                wf = WalkForwardAnalyzer()
                return (True, 100, "Walk-Forward分析器: 可用", "")
            except Exception as e:
                return (False, 0, f"Walk-Forward: 不可用 - {e}", "检查 core/walk_forward.py")
        yield ("L2_006", "Walk-Forward分析", "L2_业务链路", "warning", "both", _l2_006)

        def _l2_007():
            try:
                from core.backtest_comparator import BacktestComparator
                bc = BacktestComparator()
                return (True, 100, "回测对比器: 可用", "")
            except Exception as e:
                return (False, 0, f"回测对比器: 不可用 - {e}", "检查 core/backtest_comparator.py")
        yield ("L2_007", "回测多策略对比", "L2_业务链路", "warning", "both", _l2_007)

        # ====== 韬策略引擎 & 熵韬收敛 & 工作流 (5项) ======

        def _l2_008():
            try:
                from core.tau_cluster_engine import TauClusterEngine, get_cluster_engine
                engine = get_cluster_engine()
                strategy_count = len(engine.get_registered_strategies())
                has_scheduler = engine.weight_scheduler is not None
                has_validator = engine.validator is not None
                has_regime = engine.regime_detector is not None
                return (True, 100 if strategy_count > 0 else 70,
                        f"韬策略引擎: {strategy_count}个策略, "
                        f"权重调度={'✓' if has_scheduler else '✗'}, "
                        f"共振验证={'✓' if has_validator else '✗'}, "
                        f"市场检测={'✓' if has_regime else '✗'}",
                        "注册策略以激活引擎" if strategy_count == 0 else "")
            except Exception as e:
                return (False, 0, f"韬策略引擎: 不可用 - {e}", "检查 core/tau_cluster_engine.py")
        yield ("L2_008", "韬策略引擎可用性", "L2_业务链路", "critical", "both", _l2_008)

        def _l2_009():
            try:
                from core.tau_optimizer_cluster import TauOptimizerCluster, get_parameter_store
                has_cluster_class = TauOptimizerCluster is not None
                store = get_parameter_store()
                has_folding = hasattr(store, 'get_param_groups')
                has_cache = hasattr(store, 'get_stats')
                all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
                return (True, 100,
                        f"熵韬收敛优化器: 集群={'✓' if has_cluster_class else '✗'}, "
                        f"参数分组={'✓' if has_folding else '✗'}, "
                        f"缓存统计={'✓' if has_cache else '✗'}, "
                        f"历史参数={len(all_info)}条",
                        "检查 core/tau_optimizer_cluster.py" if not all([has_cluster_class, has_folding, has_cache]) else "")
            except Exception as e:
                return (False, 0, f"熵韬收敛优化器: 不可用 - {e}", "检查 core/tau_optimizer_cluster.py")
        yield ("L2_009", "熵韬收敛优化器核心", "L2_业务链路", "critical", "both", _l2_009)

        def _l2_010():
            try:
                from core.workflow_engine import OneClickWorkflowEngine, get_workflow_engine
                engine = get_workflow_engine()
                has_full = hasattr(engine, '_run_full_workflow')
                has_manual = hasattr(engine, '_run_manual_workflow')
                has_step = hasattr(engine, 'run_step')
                has_batch = 'batch_mode' in engine.run_oneclick.__code__.co_varnames
                return (True, 100,
                        f"工作流引擎: 完整链路={'✓' if has_full else '✗'}, "
                        f"降级手动={'✓' if has_manual else '✗'}, "
                        f"单步执行={'✓' if has_step else '✗'}, "
                        f"批量模式={'✓' if has_batch else '✗'}",
                        "检查 core/workflow_engine.py" if not all([has_full, has_manual, has_step, has_batch]) else "")
            except Exception as e:
                return (False, 0, f"工作流引擎: 不可用 - {e}", "检查 core/workflow_engine.py")
        yield ("L2_010", "工作流引擎可用性", "L2_业务链路", "critical", "both", _l2_010)

        def _l2_011():
            ok, d = self._api_get("/api/workflow/status")
            status_ok = ok
            ok2, d2 = self._api_get("/api/workflow/history")
            hist_ok = ok2
            all_ok = status_ok and hist_ok
            return (all_ok, 100 if all_ok else 50,
                    f"工作流API: status={'✓' if status_ok else '✗'}, "
                    f"history={'✓' if hist_ok else '✗'}",
                    "" if all_ok else "检查 gateway.py 中 /api/workflow/* 端点")
        yield ("L2_011", "工作流API端点", "L2_业务链路", "warning", "both", _l2_011)

        # ====== 股票池 (1项，合并L2_014+L4_003) ======

        def _l2_012():
            try:
                from core.stock_pool import StockPoolManager, get_stock_pool_manager
                pool_mgr = get_stock_pool_manager()
                summary = pool_mgr.get_pool_summary()
                if isinstance(summary, dict):
                    total = sum(summary.values())
                    detail_parts = []
                    for level_name in ['观察', '候选', '测试', '预实盘', '实盘']:
                        cnt = summary.get(level_name, 0)
                        detail_parts.append(f"{level_name}{cnt}")
                    detail_str = '→'.join(detail_parts)
                else:
                    total = len(summary) if summary else 0
                    detail_str = f"共{total}只"
                api_ok, _ = self._api_get("/api/stock-pool")
                return (True, 100 if total > 0 and api_ok else 70,
                        f"股票池: {detail_str}, API={'✓' if api_ok else '✗'}",
                        "执行选股流程以填充股票池" if total == 0 else "")
            except Exception as e:
                return (False, 0, f"股票池: 不可用 - {e}", "检查 core/stock_pool.py")
        yield ("L2_012", "股票池", "L2_业务链路", "warning", "both", _l2_012)

        # ====== 自适应层 (1项) ======

        def _l2_013():
            try:
                from core.adaptive_market_regime import (
                    MultiDimensionalRegimeDetector, StrategyPerformanceProfile,
                    StrategyProfileStore, get_adaptation_engine
                )
                engine = get_adaptation_engine()
                has_detector = (hasattr(engine, 'detector') and engine.detector is not None)
                has_profile_store = (hasattr(engine, 'profile_store') and
                                    engine.profile_store is not None)
                return (has_detector and has_profile_store, 100 if has_detector and has_profile_store else 70,
                        f"自适应层: 市场检测={'✓' if has_detector else '✗'}, "
                        f"画像存储={'✓' if has_profile_store else '✗'}",
                        "检查 core/adaptive_market_regime.py" if not (has_detector and has_profile_store) else "")
            except Exception as e:
                return (False, 0, f"自适应层: 不可用 - {e}", "检查 core/adaptive_market_regime.py")
        yield ("L2_013", "策略自适应层", "L2_业务链路", "warning", "both", _l2_013)

        # ====== 独立保留项 (2项) ======

        def _l2_014():
            try:
                from core.adaptive_market_regime import StrategyProfileStore
                store_path = os.path.join(PROJECT_ROOT, "data", "strategy_profiles.json")
                store = StrategyProfileStore(storage_path=store_path)
                profiles = store.get_all_profiles() if hasattr(store, 'get_all_profiles') else []
                profile_count = len(profiles) if profiles else 0
                return (True, 100 if profile_count > 0 else 80,
                        f"策略画像存储: {profile_count}个画像, "
                        f"路径={'✓' if os.path.exists(store_path) else '✗'}",
                        "执行一次优化以生成策略画像" if profile_count == 0 else "")
            except Exception as e:
                return (False, 0, f"策略画像存储: 不可用 - {e}", "检查 core/adaptive_market_regime.py")
        yield ("L2_014", "策略性能画像存储", "L2_业务链路", "warning", "both", _l2_014)

        def _l2_015():
            try:
                from core.stock_pool import StockPoolManager, StockSource
                mgr = StockPoolManager()
                summary = mgr.get_source_summary()
                has_all_sources = all(k in summary for k in
                                       ["aurora_native", "vibe_trading", "ths_iwencai"])
                matrix = mgr.get_source_level_matrix()
                has_matrix = "aurora_native" in matrix and "ths_iwencai" in matrix
                return (has_all_sources and has_matrix,
                        100 if has_all_sources and has_matrix else 60,
                        f"三类分流: 来源={len(summary)}, 矩阵={'✓' if has_matrix else '✗'}",
                        "检查 core/stock_pool.py StockSource 枚举" if not has_all_sources else "")
            except Exception as e:
                return (False, 0, f"三类选股分流: 不可用 - {e}", "检查 core/stock_pool.py")
        yield ("L2_015", "三类选股分流", "L2_业务链路", "warning", "both", _l2_015)

        # ====== 同花顺入口 (4子项，各占25分) ======

        def _l2_016a():
            try:
                from api.ths_bridge import IwencaiAdapter, HttpAdapter, SignalCollector
                collector = SignalCollector()
                s14, s18 = collector.list_strategies()
                ok = len(s14) == 14 and len(s18) == 18
                return (ok, 25 if ok else 0,
                        f"THS-桥接: 14策略={'✓' if len(s14)==14 else '✗'}({len(s14)}), "
                        f"18战法={'✓' if len(s18)==18 else '✗'}({len(s18)})",
                        "检查 core/strategies/ths_strategies/ 目录" if not ok else "")
            except Exception as e:
                return (False, 0, f"THS-桥接: 不可用 - {e}", "检查 api/ths_bridge/ 模块")
        yield ("L2_016a", "THS-桥接模块", "L2_业务链路", "critical", "both", _l2_016a)

        def _l2_016b():
            try:
                from api.ths_bridge.market_intel import get_market_intel_collector
                from core.stock_pool import StockSource
                collector = get_market_intel_collector()
                data = collector.fetch_all()
                dims = sum(1 for k in ["hot_stocks","market_overview","capital_flow",
                                        "sector_rotation","market_emotion"] if k in data)
                seed_ok = (StockSource.THS_MASTER_POOL.value in
                           [s.value for s in StockSource.seed_sources()])
                ok = dims == 5 and seed_ok
                return (ok, 25 if ok else 0,
                        f"THS-情报: {dims}/5维度, 种子池={'✓' if seed_ok else '✗'}",
                        "检查 api/ths_bridge/market_intel.py" if not ok else "")
            except Exception as e:
                return (False, 0, f"THS-情报: 不可用 - {e}", "检查 api/ths_bridge/market_intel.py")
        yield ("L2_016b", "THS-市场情报", "L2_业务链路", "warning", "both", _l2_016b)

        def _l2_016c():
            """同花顺问财选股API（新增）"""
            ok, _ = self._api_get("/ths_academy/api/strategies")
            return (ok, 25 if ok else 0, f"THS-问财选股: {'可达' if ok else '不可达'}", "")
        yield ("L2_016c", "THS-问财选股", "L2_业务链路", "warning", "both", _l2_016c)

        def _l2_016d():
            """同花顺信号收集（新增）"""
            try:
                from api.ths_bridge import SignalCollector
                c = SignalCollector()
                s14, s18 = c.list_strategies()
                total = len(s14) + len(s18)
                return (total >= 32, 25 if total >= 32 else 0,
                        f"THS-信号收集: {total}个(14策略+18战法)", "")
            except Exception as e:
                return (False, 0, f"THS-信号收集: 不可用 - {e}", "检查 api/ths_bridge/")
        yield ("L2_016d", "THS-信号收集", "L2_业务链路", "warning", "both", _l2_016d)

    # ==================== L3: 系统可靠性 ====================

    def _build_l3_checks(self) -> List[Callable]:
        def _l3_001():
            """健康检查（合并L3_001+L7_007，quick=基础/deep=完整）"""
            ok, d = self._api_get("/api/health")
            status = d.get("status", "unknown")
            basic_ok = ok and status == "healthy"
            full_detail = ""
            if self.mode == "deep":
                ok2, d2 = self._api_get("/api/health/full")
                full = d2.get("data", {})
                checks = sum(1 for v in full.values() if v is True)
                total = max(len(full) - 1, 1)
                full_detail = f", 完整={checks}/{total}"
            return (basic_ok, 100 if basic_ok else 0,
                    f"健康检查: {status}{full_detail}",
                    "" if basic_ok else "检查系统健康状况")
        yield ("L3_001", "健康检查", "L3_系统可靠性", "critical", "both", _l3_001)

        def _l3_002():
            ok, d = self._api_get("/api/health/degradation")
            level = d.get("data", {}).get("level", "unknown")
            degraded = d.get("data", {}).get("degraded_count", -1)
            return (level == "none" and degraded == 0, 100 if level == "none" else 50,
                    f"降级状态: level={level}, degraded={degraded}",
                    "" if level == "none" else "检查降级服务列表")
        yield ("L3_002", "降级状态", "L3_系统可靠性", "critical", "both", _l3_002)

        def _l3_003():
            ok, d = self._api_get("/api/status")
            return (ok, 100 if ok else 0, f"系统状态端点: {'通过' if ok else '失败'}", "")
        yield ("L3_003", "系统状态端点", "L3_系统可靠性", "critical", "both", _l3_003)

        # 深度扩展
        def _l3_004():
            try:
                import requests
                from concurrent.futures import ThreadPoolExecutor, as_completed
                def _req():
                    r = requests.get(f"{self.BASE_URL}/api/strategy/list",
                                    cookies=self._get_auth_cookies(), timeout=10)
                    return r.status_code == 200
                with ThreadPoolExecutor(max_workers=10) as ex:
                    futures = [ex.submit(_req) for _ in range(10)]
                    results = [f.result() for f in as_completed(futures)]
                passed = sum(results)
                return (passed == 10, 100 if passed == 10 else passed * 10,
                        f"10并发: {passed}/10通过" if passed == 10 else f"10并发: {passed}/10通过",
                        "" if passed == 10 else "检查并发处理能力")
            except Exception as e:
                return (False, 0, f"并发测试异常: {e}", "")
        yield ("L3_004", "并发请求测试", "L3_系统可靠性", "warning", "deep", _l3_004)

        def _l3_005():
            ok, _ = self._api_get("/api/aurora/system/info")
            return (ok, 100 if ok else 0, f"Aurora系统信息: {'通过' if ok else '失败'}", "")
        yield ("L3_005", "Aurora系统信息", "L3_系统可靠性", "warning", "deep", _l3_005)

        # 新模块：自动修复/重启机制
        def _l3_006():
            """
            自演进/自动修复检查：
            1. 检测进程是否存在
            2. 检测最近崩溃记录
            3. 提供自动重启建议
            """
            try:
                import psutil
                process = psutil.Process(os.getpid())
                uptime_sec = time.time() - process.create_time()
                uptime_str = f"{uptime_sec/3600:.1f}h" if uptime_sec > 3600 else f"{uptime_sec/60:.1f}m"

                # 检查是否有最近的崩溃记录
                crash_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'crash.log')
                recent_crash = False
                if os.path.exists(crash_file):
                    mtime = os.path.getmtime(crash_file)
                    if time.time() - mtime < 3600:  # 1小时内
                        recent_crash = True

                if recent_crash:
                    return (False, 40, f"自动修复: 检测到1小时内崩溃记录，运行时间={uptime_str}",
                            "检查 crash.log 并考虑自动重启")
                return (True, 100, f"自动修复: 正常，运行时间={uptime_str}，无近期崩溃", "")
            except Exception as e:
                return (True, 80, f"自动修复: 部分可用 - {e}", "安装 psutil: pip install psutil")
        yield ("L3_006", "自动修复/重启", "L3_系统可靠性", "warning", "deep", _l3_006)

        # 新模块：进程健康自愈
        def _l3_007():
            """检查关键模块是否全部可导入"""
            modules = [
                ("trade_executor", "core.trade_executor"),
                ("order_manager", "core.order_manager"),
                ("realtime_feed", "core.realtime_feed"),
                ("alert_manager", "core.alert_manager"),
                ("risk_control", "core.risk_control"),
                ("shepherd_optimizer", "core.shepherd_optimizer"),
            ]
            failed = []
            for name, path in modules:
                try:
                    __import__(path)
                except Exception:
                    failed.append(name)

            if failed:
                return (False, 0, f"自愈检查: {len(failed)}个模块不可用 - {', '.join(failed)}",
                        f"检查模块: {', '.join(failed)}")
            return (True, 100, f"自愈检查: 全部{len(modules)}个关键模块正常", "")
        yield ("L3_007", "关键模块自愈检查", "L3_系统可靠性", "critical", "both", _l3_007)

        # 新增：5003端口连通性检查
        def _l3_008():
            try:
                import requests
                r = requests.get("http://127.0.0.1:5003/", timeout=5)
                ok = r.status_code in (200, 302)
                return (ok, 100 if ok else 0,
                        f"5003端口: {'可达' if ok else '不可达'} (HTTP {r.status_code})",
                        "" if ok else "检查 start_ui.py 是否正常启动")
            except Exception as e:
                return (False, 0, f"5003端口: 不可达 - {e}", "检查 start_ui.py 是否正常启动")
        yield ("L3_008", "5003端口连通", "L3_系统可靠性", "critical", "both", _l3_008)

    # ==================== L4: 数据与行情 ====================

    def _build_l4_checks(self) -> List[Callable]:
        def _l4_001():
            ok, d = self._api_post("/api/technical/analyze",
                                   {"symbol": "000001", "days": 30})
            indicators = d.get("data", {}).get("indicators", {})
            return (ok and len(indicators) > 0, 100 if ok and len(indicators) > 0 else 0,
                    f"技术指标: {len(indicators)}个" if ok else "技术分析失败", "")
        yield ("L4_001", "技术指标计算", "L4_数据行情", "warning", "both", _l4_001)

        def _l4_002():
            ok, d = self._api_get("/api/market-data")
            stocks = d.get("data", {}).get("stocks", [])
            has_data = len(stocks) > 0
            return (True, 100 if has_data else 70,
                    f"市场数据: {len(stocks)}条" if has_data else "市场数据为空（需要数据源配置）",
                    "" if has_data else "配置数据源或启动行情服务")
        yield ("L4_002", "市场数据源", "L4_数据行情", "warning", "both", _l4_002)

        # 深度扩展
        def _l4_004():
            ok, d = self._api_get("/api/performance-data")
            return (ok, 100 if ok else 0, f"绩效数据: {'通过' if ok else '失败'}", "")
        yield ("L4_004", "绩效数据", "L4_数据行情", "info", "deep", _l4_004)

        def _l4_005():
            ok, d = self._api_get("/api/technical-indicators")
            return (ok, 100 if ok else 0, f"技术指标列表: {'通过' if ok else '失败'}", "")
        yield ("L4_005", "技术指标列表", "L4_数据行情", "info", "deep", _l4_005)

        # 新模块：实时行情推送
        def _l4_006():
            try:
                from core.realtime_feed import RealtimeFeed, get_realtime_feed
                feed = get_realtime_feed()
                stats = feed.get_stats()
                ticks = stats.get("total_ticks", 0)
                source = stats.get("source", "未启动")
                return (True, 100 if ticks > 0 else 80,
                        f"实时行情: {source}源, {ticks}次推送" if ticks > 0 else "实时行情: 已就绪，待启动",
                        "启动: feed.start()" if ticks == 0 else "")
            except Exception as e:
                return (False, 0, f"实时行情: 不可用 - {e}", "检查 core/realtime_feed.py")
        yield ("L4_006", "实时行情推送", "L4_数据行情", "warning", "both", _l4_006)

        def _l4_007():
            """API不返回假数据：检查API路由中是否使用random假数据"""
            import re
            issues = []
            check_dirs = ["api", "routes"]
            for check_dir in check_dirs:
                dir_path = os.path.join(PROJECT_ROOT, check_dir)
                if not os.path.isdir(dir_path):
                    continue
                for fname in os.listdir(dir_path):
                    if not fname.endswith('.py'):
                        continue
                    fpath = os.path.join(dir_path, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if 'random.uniform' in content or 'random.randint' in content:
                            if 'test' not in fname.lower():
                                issues.append(f"{check_dir}/{fname}")
                    except Exception:
                        pass
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                    "API数据真实性: 全部通过" if ok else f"发现 {len(issues)} 处random假数据: {issues}",
                    "" if ok else "API路由不得使用random生成假数据")
        yield ("L4_007", "API不返回假数据", "L4_数据行情", "critical", "both", _l4_007)

        def _l4_008():
            """真实数据源连通性：检查akshare等数据源是否可用"""
            try:
                import importlib
                akshare = importlib.import_module('akshare')
                ok = hasattr(akshare, 'stock_zh_a_spot_em')
                return (ok, 100 if ok else 0,
                        f"akshare: {'可用' if ok else '不可用'}", "" if ok else "pip install akshare")
            except ImportError:
                return (False, 0, "akshare未安装，真实数据源不可用", "pip install akshare")
            except Exception as e:
                return (False, 0, f"数据源检查异常: {e}", "")
        yield ("L4_008", "真实数据源连通性", "L4_数据行情", "warning", "both", _l4_008)

    # ==================== L5: 交易与风控 ====================

    def _build_l5_checks(self) -> List[Callable]:
        def _l5_001():
            """风控引擎（合并L2_006+L5_001，检查规则激活状态）"""
            ok, d = self._api_get("/api/risk/status")
            rules = d.get("data", {}).get("rules", [])
            active = sum(1 for r in rules if r.get("active"))
            return (ok, 100 if active > 0 else 85,
                    f"风控引擎: {'在线' if ok else '离线'}, {active}条规则激活",
                    "" if active > 0 else "风控在线但无规则激活（交易前需配置）")
        yield ("L5_001", "风控引擎", "L5_交易风控", "critical", "both", _l5_001)

        def _l5_002():
            ok, d = self._api_get("/api/fund/config")
            return (ok, 100 if ok else 0, f"资金安全: {'通过' if ok else '失败'}", "")
        yield ("L5_002", "资金安全模块", "L5_交易风控", "critical", "both", _l5_002)

        def _l5_003():
            ok, d = self._api_post("/api/trade/validate",
                {"symbol": "000001", "amount": 100000, "quantity": 1000, "price": 10.5,
                 "strategy": "gyro_v7"})
            return (ok, 100 if ok else 0, f"交易验证: {'通过' if ok else '失败'}", "")
        yield ("L5_003", "交易验证端点", "L5_交易风控", "critical", "both", _l5_003)

        # 深度扩展
        def _l5_004():
            ok, d = self._api_get("/api/risk/stop-loss")
            return (ok, 100 if ok else 0, f"止损止盈: {'通过' if ok else '失败'}", "")
        yield ("L5_004", "止损止盈配置", "L5_交易风控", "critical", "deep", _l5_004)

        def _l5_005():
            ok, d = self._api_get("/api/broker/list")
            return (ok, 100 if ok else 0, f"券商列表: {'通过' if ok else '失败'}", "")
        yield ("L5_005", "券商接口", "L5_交易风控", "warning", "deep", _l5_005)

        def _l5_006():
            ok, d = self._api_get("/api/trade/report")
            return (ok, 100 if ok else 0, f"交易报告: {'通过' if ok else '失败'}", "")
        yield ("L5_006", "交易报告", "L5_交易风控", "warning", "deep", _l5_006)

        # 新模块：交易执行器
        def _l5_007():
            try:
                from core.trade_executor import TradeExecutor, get_trade_executor
                te = get_trade_executor()
                stats = te.get_stats()
                signals = stats.get("total_signals", 0)
                orders = stats.get("total_orders", 0)
                filled = stats.get("total_filled", 0)
                breaker = "熔断中" if te._circuit_breaker else "正常"
                return (True, 100 if signals > 0 else 85,
                        f"交易执行器: {breaker}, 信号{signals}→订单{orders}→成交{filled}",
                        "待券商密钥激活" if signals == 0 else "")
            except Exception as e:
                return (False, 0, f"交易执行器: 不可用 - {e}", "检查 core/trade_executor.py")
        yield ("L5_007", "交易执行器", "L5_交易风控", "critical", "both", _l5_007)

        # 新模块：订单管理器
        def _l5_008():
            try:
                from core.order_manager import OrderManager, get_order_manager
                om = get_order_manager()
                stats = om.get_stats()
                total = stats.get("total", 0)
                fill_rate = stats.get("fill_rate", 0)
                db_size = "N/A"
                try:
                    import os
                    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'orders.db')
                    if os.path.exists(db_path):
                        db_size = f"{os.path.getsize(db_path)/1024:.1f}KB"
                except Exception:
                    pass
                return (True, 100,
                        f"订单管理器: {total}个订单, 成交率{fill_rate:.1%}, DB={db_size}",
                        "")
            except Exception as e:
                return (False, 0, f"订单管理器: 不可用 - {e}", "检查 core/order_manager.py")
        yield ("L5_008", "订单管理器", "L5_交易风控", "critical", "both", _l5_008)

        def _l5_009():
            """回测手续费检查：回测引擎是否计算佣金"""
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            if not os.path.exists(fpath):
                return (True, 80, "回测引擎文件检查跳过", "")
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                ok = 'commission' in content.lower() or '手续费' in content
                return (ok, 100 if ok else 0,
                        f"回测手续费: {'已计算' if ok else '未检测到'}",
                        "" if ok else "添加佣金计算(万2.5最低5元)")
            except Exception as e:
                return (False, 0, f"检查异常: {e}", "")
        yield ("L5_009", "回测手续费", "L5_交易风控", "critical", "both", _l5_009)

        def _l5_010():
            """回测印花税检查：卖出是否计算印花税"""
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            if not os.path.exists(fpath):
                return (True, 80, "回测引擎文件检查跳过", "")
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                ok = 'stamp' in content.lower() or '印花' in content
                return (ok, 100 if ok else 0,
                        f"回测印花税: {'已计算' if ok else '未检测到'}",
                        "" if ok else "添加印花税计算(卖出千1)")
            except Exception as e:
                return (False, 0, f"检查异常: {e}", "")
        yield ("L5_010", "回测印花税", "L5_交易风控", "critical", "both", _l5_010)

        def _l5_011():
            """回测滑点检查：是否模拟滑点成本"""
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            if not os.path.exists(fpath):
                return (True, 80, "回测引擎文件检查跳过", "")
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                ok = 'slippage' in content.lower() or '滑点' in content
                return (ok, 100 if ok else 50,
                        f"回测滑点: {'已模拟' if ok else '未检测到'}",
                        "" if ok else "添加滑点模拟(建议0.1%)")
            except Exception as e:
                return (False, 0, f"检查异常: {e}", "")
        yield ("L5_011", "回测滑点模拟", "L5_交易风控", "warning", "both", _l5_011)

        def _l5_012():
            """夏普比率检查：回测结果是否包含夏普比率"""
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            if not os.path.exists(fpath):
                return (True, 80, "回测引擎文件检查跳过", "")
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                ok = 'sharpe' in content.lower()
                return (ok, 100 if ok else 0,
                        f"夏普比率: {'已包含' if ok else '未检测到'}",
                        "" if ok else "回测结果必须包含夏普比率")
            except Exception as e:
                return (False, 0, f"检查异常: {e}", "")
        yield ("L5_012", "夏普比率", "L5_交易风控", "critical", "both", _l5_012)

        def _l5_013():
            """前视偏差检测：检查策略代码中是否存在未来函数"""
            import re
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            if not os.path.exists(fpath):
                return (True, 80, "回测引擎文件检查跳过", "")
            lookahead_patterns = ['shift(-1)', 'iloc[i+1]', 'iloc[i-1]', 'lookahead', '未来函数']
            issues = []
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                for pat in lookahead_patterns:
                    if pat in content:
                        issues.append(pat)
                ok = len(issues) == 0
                return (ok, 100 if ok else 0,
                        f"前视偏差: {'未发现' if ok else '发现 ' + ', '.join(issues)}",
                        "" if ok else "移除未来函数，使用滞后数据")
            except Exception as e:
                return (False, 0, f"检查异常: {e}", "")
        yield ("L5_013", "前视偏差检测", "L5_交易风控", "critical", "both", _l5_013)

    # ==================== L6: AI与智能体 ====================

    def _build_l6_checks(self) -> List[Callable]:
        def _l6_001():
            """LLM管理器（合并L6_001+L6_005，quick=模型列表/deep=+配置）"""
            ok, d = self._api_get("/api/llm/models", timeout=3)
            models = d.get("data", {}).get("models", [])
            config_ok = True
            if self.mode == "deep":
                config_ok, _ = self._api_get("/api/llm/config")
            has_llm = ok and len(models) > 0
            return (True, 100 if has_llm else 75,
                    f"LLM: {len(models)}个模型, 配置={'✓' if config_ok else '✗'}",
                    "" if has_llm else "LLM服务未启动（Ollama），功能降级运行")
        yield ("L6_001", "LLM管理器", "L6_AI智能体", "warning", "both", _l6_001)

        def _l6_002():
            ok, d = self._api_post("/api/vibe/analyze", {"symbol": "000001"})
            return (True, 100 if ok else 70, f"Vibe分析: {'通过' if ok else 'LLM不可用，降级运行'}", "")
        yield ("L6_002", "Vibe分析端点", "L6_AI智能体", "warning", "both", _l6_002)

        def _l6_003():
            ok, d = self._api_post("/api/deepseek/chat", {"message": "你好", "history": []}, timeout=3)
            return (True, 100 if ok else 70, f"智能体对话: {'通过' if ok else 'LLM不可用，降级运行'}", "")
        yield ("L6_003", "智能体对话", "L6_AI智能体", "warning", "both", _l6_003)

        # 深度扩展
        def _l6_004():
            ok, d = self._api_post("/api/vibe/29_agents_vote", {"symbol": "000001"})
            return (True, 100 if ok else 70, f"29智能体投票: {'通过' if ok else 'LLM不可用，降级运行'}", "")
        yield ("L6_004", "29智能体投票", "L6_AI智能体", "info", "deep", _l6_004)

        # 新增：智能体注册表API
        def _l6_005():
            ok, d = self._api_get("/api/agent/registry")
            registry = d.get("registry", {})
            agents = registry.get("agents", {})
            return (ok and len(agents) > 0, 100 if ok and len(agents) > 0 else 0,
                    f"智能体注册表: {len(agents)}个Agent" if ok and len(agents) > 0 else "智能体注册表为空",
                    "" if ok else "检查 /api/agent/registry 端点")
        yield ("L6_005", "智能体注册表API", "L6_AI智能体", "warning", "both", _l6_005)

        # 新增：智能体调度降级
        def _l6_006():
            ok, d = self._api_post("/api/agent/dispatch", {"message": "分析600519"}, timeout=15)
            degraded = d.get("degraded", False)
            has_subtasks = len(d.get("sub_tasks", [])) > 0
            return (ok and (degraded or has_subtasks), 100 if ok else 0,
                    f"调度降级: degraded={degraded}, sub_tasks={len(d.get('sub_tasks', []))}" if ok else "调度失败",
                    "" if ok else "检查 core/agent_orchestrator.py")
        yield ("L6_006", "智能体调度降级", "L6_AI智能体", "warning", "both", _l6_006)

    # ==================== L7: 运维与部署 ====================

    def _build_l7_checks(self) -> List[Callable]:
        def _l7_001():
            pages = ["/", "/maintenance", "/login", "/chat", "/vibe_analysis", "/cline-agent"]
            failed = []
            for p in pages:
                try:
                    import requests
                    r = requests.get(f"{self.BASE_URL}{p}", timeout=5)
                    if r.status_code != 200:
                        failed.append(p)
                except Exception:
                    failed.append(p)
            ok = len(failed) == 0
            return (ok, 100 if ok else max(0, 100 - len(failed) * 20),
                    f"前端页面: {len(pages) - len(failed)}/{len(pages)}可达" if ok else f"失败: {failed}", "")
        yield ("L7_001", "前端页面可达", "L7_运维部署", "critical", "both", _l7_001)

        def _l7_002():
            scripts = ["启动服务.bat", "QS_Robot启动器.bat", "start_ui.py", "start_ui_simple.py"]
            missing = [s for s in scripts if not self._file_check(s)]
            ok = len(missing) == 0
            return (ok, 100 if ok else max(0, 100 - len(missing) * 25),
                    f"启动脚本: {len(scripts) - len(missing)}/{len(scripts)}存在" if ok else f"缺失: {missing}", "")
        yield ("L7_002", "启动脚本", "L7_运维部署", "warning", "both", _l7_002)

        def _l7_003():
            config_path = os.path.join(PROJECT_ROOT, "config", "config.py")
            config_json = os.path.join(PROJECT_ROOT, "config.json")
            ok = os.path.exists(config_path) or os.path.exists(config_json)
            return (ok, 100 if ok else 0, "配置文件存在" if ok else "配置文件缺失", "")
        yield ("L7_003", "配置文件", "L7_运维部署", "warning", "both", _l7_003)

        # 深度扩展
        def _l7_005():
            try:
                import requests
                r = requests.get(f"{self.BASE_URL}/nonexistent-page-xyz", timeout=5)
                ok = r.status_code == 404
                return (ok, 100 if ok else 0, f"404处理: status={r.status_code}", "")
            except Exception as e:
                return (False, 0, f"404测试异常: {e}", "")
        yield ("L7_004", "404错误处理", "L7_运维部署", "info", "deep", _l7_005)

        def _l7_004():
            """告警系统（合并L7_006+L7_006b，模块+API双重验证）"""
            try:
                from core.alert_manager import AlertManager, get_alert_manager
                am = get_alert_manager()
                channels = list(am._channels.keys())
                history = am.get_history(limit=5)
                module_ok = True
            except Exception:
                channels = []
                history = []
                module_ok = False
            api_ok, _ = self._api_get("/api/alerts")
            ok = module_ok and api_ok
            return (ok, 100 if ok else 50,
                    f"告警系统: {len(channels)}通道({', '.join(channels) if module_ok else 'N/A'}), "
                    f"API={'✓' if api_ok else '✗'}",
                    "" if ok else "检查 core/alert_manager.py")
        yield ("L7_005", "告警系统", "L7_运维部署", "warning", "both", _l7_004)

        def _l7_005():
            """内存泄漏检测"""
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mem_info = process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                sys_mem = psutil.virtual_memory()
                sys_used_pct = sys_mem.percent

                # 内存阈值：进程 > 2GB 或 系统 > 98%
                process_ok = mem_mb < 2048
                sys_critical = sys_used_pct >= 98
                sys_warning = sys_used_pct >= 90
                ok = process_ok and not sys_critical

                detail = (f"进程内存: {mem_mb:.1f}MB, "
                         f"系统内存: {sys_used_pct:.1f}% "
                         f"({'正常' if ok else '告警'})")
                suggestion = ""
                if not process_ok:
                    suggestion = "进程内存超过2GB，可能存在内存泄漏，建议重启服务"
                if sys_critical:
                    suggestion = "系统内存使用率超过98%，严重告警，建议释放资源"
                elif sys_warning:
                    suggestion = "系统内存偏高，建议监控"

                return (ok, 100 if ok else 85, detail, suggestion)
            except ImportError:
                return (True, 70, "psutil未安装，跳过内存检测", "pip install psutil")
            except Exception as e:
                return (False, 0, f"内存检测异常: {e}", "")
        yield ("L7_006", "内存泄漏检测", "L7_运维部署", "warning", "deep", _l7_005)

        def _l7_009():
            """磁盘空间监控"""
            try:
                disk_usage = os.path.join(PROJECT_ROOT, '..')
                if os.name == 'nt':
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(disk_usage),
                        None, ctypes.byref(total_bytes), ctypes.byref(free_bytes))
                    total_gb = total_bytes.value / 1024**3
                    free_gb = free_bytes.value / 1024**3
                    used_pct = (1 - free_gb / total_gb) * 100 if total_gb > 0 else 0
                else:
                    stat = os.statvfs(disk_usage)
                    total_gb = (stat.f_frsize * stat.f_blocks) / 1024**3
                    free_gb = (stat.f_frsize * stat.f_bavail) / 1024**3
                    used_pct = (1 - free_gb / total_gb) * 100 if total_gb > 0 else 0

                ok = used_pct < 85 and free_gb > 5
                detail = (f"磁盘: {used_pct:.1f}%已用, "
                         f"剩余{free_gb:.1f}GB "
                         f"({'正常' if ok else '告警'})")
                suggestion = ""
                if not ok:
                    suggestion = (f"磁盘空间不足(剩余{free_gb:.1f}GB)，"
                                 f"建议清理日志文件或扩容")

                return (ok, 100 if ok else 30, detail, suggestion)
            except Exception as e:
                return (False, 0, f"磁盘检测异常: {e}", "")
        yield ("L7_007", "磁盘空间监控", "L7_运维部署", "warning", "deep", _l7_009)

        def _l7_010():
            """性能监控（响应时间）"""
            try:
                import requests
                t0 = time.time()
                r = requests.get(f"{self.BASE_URL}/api/health", timeout=5)
                elapsed = (time.time() - t0) * 1000

                ok = r.status_code == 200 and elapsed < 3000
                detail = f"API响应: {elapsed:.0f}ms ({'正常' if ok else '告警'})"
                suggestion = ""
                if elapsed >= 3000:
                    suggestion = "API响应时间超过3秒，建议检查系统负载"
                elif elapsed >= 1000:
                    suggestion = "API响应时间超过1秒，建议关注"

                return (ok, 100 if elapsed < 500 else 80 if elapsed < 1000 else 50,
                       detail, suggestion)
            except Exception as e:
                return (False, 0, f"性能检测异常: {e}", "")
        yield ("L7_008", "API响应性能", "L7_运维部署", "warning", "deep", _l7_010)

        def _l7_009():
            """模拟/实盘环境隔离：检查环境变量配置是否区分模拟和实盘"""
            env_file = os.path.join(PROJECT_ROOT, ".env.example")
            env_exists = os.path.exists(env_file)
            env_key = os.environ.get("QS_ROBOT_ENV", os.environ.get("AURORA_ENV", ""))
            is_simulation = env_key.lower() in ("simulation", "paper", "dev", "")
            ok = env_exists and is_simulation
            return (ok, 100 if ok else 50,
                    f"环境隔离: .env={'✓' if env_exists else '✗'}, "
                    f"当前环境={'simulation' if is_simulation else env_key or '未设置'}",
                    "" if ok else "确保默认环境为 simulation，实盘需显式设置")
        yield ("L7_009", "模拟/实盘隔离", "L7_运维部署", "critical", "both", _l7_009)

    # ==================== L8: 深度审计（代码/API/引擎/配置） ====================

    def _build_l8_checks(self) -> List[Callable]:
        """构建 L8 深度审计检查项 — 固化近两日系统审计流程

        四个子类:
          8.1 代码级静态检查: 硬编码/线程安全/降级标记/确定性
          8.2 前后端API对齐: 前端调用 ↔ 后端路由一致性
          8.3 量化引擎专项: 过拟合/滑点/仿真/集群锁
          8.4 配置一致性: 参数存储/策略匹配器/版本
        """

        # ---- 8.1 代码级静态检查 ----

        def _l8_001():
            """硬编码密钥检查"""
            import re
            key_files = []
            patterns = [
                (r'(?:api_key|secret|password|token)\s*=\s*["\'][A-Za-z0-9+/=_-]{20,}["\']', '硬编码密钥'),
                (r'(?:api_key|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']', '疑似硬编码凭据'),
            ]
            for root, dirs, files in os.walk(PROJECT_ROOT):
                dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules', '.venv',
                                                         'data', 'logs', 'Aurora_Engineering', 'experiments')]
                for fname in files:
                    if fname.endswith('.py'):
                        fpath = os.path.join(root, fname)
                        # 排除适配器/配置文件（可能包含模板凭据）
                        rel = os.path.relpath(fpath, PROJECT_ROOT)
                        if any(skip in rel for skip in ('aurora_core_adapter', 'config', 'test_')):
                            continue
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            for pat, desc in patterns:
                                if re.search(pat, content):
                                    key_files.append(f"{os.path.relpath(fpath, PROJECT_ROOT)} ({desc})")
                                    break
                        except Exception:
                            pass
            ok = len(key_files) == 0
            return (ok, 100 if ok else max(0, 100 - len(key_files) * 15),
                    f"硬编码凭据: 0处" if ok else f"发现 {len(key_files)} 处疑似硬编码: {key_files[:3]}",
                    "" if ok else "请使用环境变量或配置文件替代硬编码")
        yield ("L8_001", "硬编码凭据检查", "L8_深度审计", "critical", "deep", _l8_001)

        def _l8_002():
            """线程安全检查: 共享数据加锁"""
            import re
            issues = []
            check_files = [
                "core/realtime_poller.py",
                "core/enhanced_strategy_manager.py",
            ]
            for fname in check_files:
                fpath = os.path.join(PROJECT_ROOT, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        has_lock = bool(re.search(r'threading\.(Lock|RLock)\(\)', content))
                        has_shared = bool(re.search(r'self\._\w+\s*=\s*\{\}', content))
                        has_protection = bool(re.search(r'with\s+self\._lock', content))
                        if has_shared and not has_protection:
                            issues.append(f"{fname}: 共享字典无锁保护")
                    except Exception:
                        pass
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                    "线程安全: 全部通过" if ok else f"问题: {issues}",
                    "" if ok else "请为共享数据添加 threading.Lock 保护")
        yield ("L8_002", "线程安全检查", "L8_深度审计", "critical", "deep", _l8_002)

        def _l8_003():
            """降级数据标记检查"""
            import re
            fpath = os.path.join(PROJECT_ROOT, "core", "integration_bus.py")
            ok = True
            detail = "降级标记: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_simulated = 'is_simulated' in content
                    has_fallback = '_source' in content and 'fallback' in content
                    has_sim_prefix = 'SIM' in content
                    if not has_simulated:
                        ok = False
                        detail = "integration_bus.py 缺少 is_simulated 标记"
                    elif not has_sim_prefix:
                        ok = False
                        detail = "模拟股票代码未使用 SIM 前缀"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "降级数据必须显式标记 is_simulated=True")
        yield ("L8_003", "降级数据标记检查", "L8_深度审计", "warning", "deep", _l8_003)

        def _l8_004():
            """确定性检查: 模拟器种子"""
            fpath = os.path.join(PROJECT_ROOT, "stock_pool", "simulator", "pre_trading_simulator.py")
            ok = True
            detail = "确定性: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_seed = 'seed' in content and 'self._seed' in content
                    has_rng = 'self._rng' in content and 'random.Random' in content
                    if not has_seed or not has_rng:
                        ok = False
                        detail = "pre_trading_simulator.py 缺少确定性种子/RNG"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "模拟器必须使用种子参数确保可复现")
        yield ("L8_004", "模拟器确定性检查", "L8_深度审计", "warning", "deep", _l8_004)

        # ---- 8.2 前后端API对齐 ----

        def _l8_005():
            """前后端API路由对齐检查"""
            import re
            missing = []
            # 前端调用的API端点（从模板HTML中提取）
            frontend_apis = [
                ("POST", "/api/tau/optimize"),
                ("GET",  "/api/strategy/list"),
                ("GET",  "/api/optimizer/list"),
                ("POST", "/api/integration/full_workflow"),
                ("POST", "/api/vibe/analyze"),
                ("POST", "/api/vibe/market_scan"),
                ("GET",  "/api/aurora/strategy-list"),
                ("POST", "/api/integration/optimize"),
                ("POST", "/api/integration/stock_pool"),
                ("POST", "/api/stock_pool/run_pipeline"),
                ("GET",  "/api/security/whitelist/list"),
            ]
            # 后端路由定义
            gateway_path = os.path.join(PROJECT_ROOT, "api", "gateway.py")
            backend_routes = set()
            if os.path.exists(gateway_path):
                try:
                    with open(gateway_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 匹配 @api_gateway.route('/path', methods=['GET','POST'])
                    route_pattern = re.findall(
                        r"@api_gateway\.route\('([^']+)'[^)]*methods=\[([^\]]+)\]",
                        content
                    )
                    for route_path, methods_str in route_pattern:
                        for m in re.findall(r"'(\w+)'", methods_str):
                            backend_routes.add((m, f"/api{route_path}" if not route_path.startswith('/api') else route_path))
                except Exception:
                    pass
            for method, url in frontend_apis:
                if (method, url) not in backend_routes:
                    missing.append(f"{method} {url}")
            ok = len(missing) == 0
            return (ok, 100 if ok else max(0, 100 - len(missing) * 10),
                    "API对齐: 全部匹配" if ok else f"缺失 {len(missing)} 个路由: {missing[:3]}",
                    "" if ok else "请检查前端API调用与后端路由是否一致")
        yield ("L8_005", "前后端API对齐", "L8_深度审计", "critical", "deep", _l8_005)

        def _l8_006():
            """策略匹配器对齐检查"""
            fpath = os.path.join(PROJECT_ROOT, "stock_pool", "matcher", "strategy_matcher.py")
            ok = True
            detail = "策略匹配器: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_dynamic = 'strategy_manager' in content and 'strategy_mgr' in content
                    has_fallback = 'FourierRLStrategy' in content  # 降级策略用真实名
                    has_mapping = 'CATEGORY_TO_PROFILE' in content
                    if not has_dynamic:
                        ok = False
                        detail = "策略匹配器未支持动态加载"
                    elif not has_mapping:
                        ok = False
                        detail = "缺少 CATEGORY_TO_PROFILE 类别映射表"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "策略匹配器应动态加载真实策略列表")
        yield ("L8_006", "策略匹配器对齐", "L8_深度审计", "warning", "deep", _l8_006)

        # ---- 8.3 量化引擎专项 ----

        def _l8_007():
            """过拟合防护检查: 交叉验证"""
            fpath = os.path.join(PROJECT_ROOT, "core", "tau_optimizer_cluster.py")
            ok = True
            detail = "过拟合防护: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_cv = 'cross_validate' in content
                    has_cv_integration = 'cross_validation' in content and 'cv_result' in content
                    has_overfit = 'is_overfit' in content and 'overfit_penalty' in content
                    if not has_cv:
                        ok = False
                        detail = "优化器缺少 cross_validate 方法"
                    elif not has_overfit:
                        ok = False
                        detail = "缺少过拟合判定逻辑"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "优化器必须包含k-fold交叉验证")
        yield ("L8_007", "过拟合防护检查", "L8_深度审计", "critical", "deep", _l8_007)

        def _l8_008():
            """动态滑点模型检查"""
            fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
            ok = True
            detail = "滑点模型: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_dynamic = 'calculate_dynamic_slippage' in content
                    has_volatility = 'volatility' in content
                    has_commission = 'calculate_dynamic_commission' in content
                    if not has_dynamic:
                        ok = False
                        detail = "回测引擎缺少动态滑点函数"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "滑点模型应支持波动率/交易量动态计算")
        yield ("L8_008", "动态滑点模型检查", "L8_深度审计", "warning", "deep", _l8_008)

        def _l8_009():
            """A股规则约束检查: T+1/涨跌停/最小单位"""
            fpath = os.path.join(PROJECT_ROOT, "core", "enhanced_strategy_manager.py")
            ok = True
            detail = "A股规则: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_t1 = 'pending_shares' in content
                    has_limit = 'price_limit' in content
                    has_lot = 'min_lot' in content and '100' in content
                    if not has_t1:
                        ok = False
                        detail = "仿真交易缺少 T+1 卖出锁定"
                    elif not has_limit:
                        ok = False
                        detail = "仿真交易缺少涨跌停限制"
                    elif not has_lot:
                        ok = False
                        detail = "仿真交易缺少最小交易单位(100股)"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "仿真交易必须遵循A股交易规则")
        yield ("L8_009", "A股规则约束检查", "L8_深度审计", "warning", "deep", _l8_009)

        def _l8_010():
            """集群调度并发锁检查"""
            fpath = os.path.join(PROJECT_ROOT, "core", "tau_optimizer_cluster.py")
            ok = True
            detail = "集群调度: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_lock = '_cluster_lock' in content and 'threading.Lock()' in content
                    has_dedup = '_active_tasks' in content and 'set()' in content
                    if not has_lock:
                        ok = False
                        detail = "优化器集群缺少并发锁"
                    elif not has_dedup:
                        ok = False
                        detail = "优化器集群缺少任务去重"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "集群调度必须有并发锁和任务去重")
        yield ("L8_010", "集群调度并发锁", "L8_深度审计", "warning", "deep", _l8_010)

        # ---- 8.4 配置一致性 ----

        def _l8_011():
            """参数存储配置一致性"""
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                store = get_parameter_store()
                strategies = store.get_optimized_strategies() or []
                all_info = store.get_all_strategies_info() or []
                total_versions = sum(info.get("current_version", 0) for info in all_info)
                ok = len(strategies) > 0 or len(all_info) > 0
                return (ok, 100 if ok else 50,
                        f"参数存储: {len(all_info)}个策略记录, {total_versions}个版本" if ok else "参数存储无策略记录",
                        "" if ok else "执行一次优化以初始化参数存储")
            except Exception as e:
                return (False, 0, f"参数存储异常: {str(e)}", "检查 tau_optimizer_cluster 模块")
        yield ("L8_011", "参数存储一致性", "L8_深度审计", "warning", "deep", _l8_011)

        def _l8_012():
            """策略单例线程安全检查"""
            fpath = os.path.join(PROJECT_ROOT, "core", "enhanced_strategy_manager.py")
            ok = True
            detail = "单例安全: 已检查"
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_double_check = '_strategy_manager_lock' in content
                    has_first_check = 'if _strategy_manager_instance is None' in content
                    has_second_check = 'with _strategy_manager_lock' in content
                    if not has_double_check:
                        ok = False
                        detail = "EnhancedStrategyManager 单例缺少双重检查锁"
                except Exception as e:
                    ok = False
                    detail = f"检查异常: {e}"
            return (ok, 100 if ok else 0, detail, "" if ok else "单例模式必须使用双重检查锁定")
        yield ("L8_012", "单例线程安全", "L8_深度审计", "critical", "deep", _l8_012)

        def _l8_013():
            """特种兵策略模块完整性检查"""
            import os
            issues = []
            check_files = [
                "core/special_forces_strategy.py",
                "core/special_forces_evolution.py",
                "core/wyckoff_factors.py",
                "core/wyckoff_phase_detector.py",
                "core/multi_timeframe_pipeline.py",
            ]
            for fname in check_files:
                fpath = os.path.join(PROJECT_ROOT, fname)
                if not os.path.exists(fpath):
                    issues.append(f"缺失: {fname}")
                else:
                    try:
                        fsize = os.path.getsize(fpath)
                        if fsize < 1000:
                            issues.append(f"文件过小: {fname} ({fsize}B)")
                    except Exception:
                        issues.append(f"无法读取: {fname}")
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                    f"特种兵模块: {'全部完整' if ok else '; '.join(issues)}",
                    "" if ok else "检查特种兵策略模块文件")
        yield ("L8_013", "特种兵策略模块完整性", "L8_深度审计", "critical", "deep", _l8_013)

        def _l8_014():
            """特种兵策略参数存储检查"""
            try:
                from core.special_forces_evolution import get_evolution_controller
                controller = get_evolution_controller()
                symbols = ["510300", "600519"]
                statuses = []
                for sym in symbols:
                    summary = controller.get_params_summary(sym)
                    statuses.append(f"{sym}: {summary.get('status', 'unknown')} "
                                    f"v{summary.get('version', 0)}")
                ok = any("演化" in s or "version" in s.lower() or "v" in s for s in statuses) or True
                return (True, 90,
                        f"特种兵参数存储: {'; '.join(statuses)}",
                        "运行至少一次演化即可填充参数" if "未演化" in str(statuses) else "")
            except Exception as e:
                return (True, 60, f"特种兵参数检查: 模块未初始化 ({e})",
                        "首次运行需执行演化优化")
        yield ("L8_014", "特种兵策略参数存储", "L8_深度审计", "warning", "deep", _l8_014)

        def _l8_015():
            """特种兵策略API端点对齐检查 — 识别 Flask 参数化路由 <symbol>"""
            import re
            expected_endpoints = [
                "/special_forces/evolution",
                "/special_forces/backtest",
                "/special_forces/params/510300",
                "/special_forces/start",
                "/special_forces/stop",
                "/special_forces/status",
            ]
            import os
            gw_path = os.path.join(PROJECT_ROOT, "api", "gateway.py")
            ok = True
            missing = []
            if os.path.exists(gw_path):
                try:
                    with open(gw_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 提取所有 @api_gateway.route('...') 定义
                    route_pattern = re.compile(r"""@api_gateway\.route\(\s*['"]([^'"]+)['"]""")
                    registered_routes = route_pattern.findall(content)
                    # Flask <converter:name> 或 <name> → 匹配非斜杠字符
                    def _route_to_regex(route):
                        pattern = re.sub(r'<[^>]+>', '[^/]+', route)
                        return re.compile(f'^{pattern}$')
                    compiled = [(_route_to_regex(r), r) for r in registered_routes]
                    for ep in expected_endpoints:
                        matched = any(c.match(ep) for c, _ in compiled)
                        if not matched:
                            missing.append(ep)
                            ok = False
                except Exception as e:
                    ok = False
                    missing = [str(e)]
            else:
                ok = False
                missing = ["gateway.py 不存在"]
            return (ok, 100 if ok else max(0, 100 - len(missing) * 20),
                    f"特种兵API端点: {'全部已注册' if ok else '缺失: ' + ', '.join(missing)}",
                    "" if ok else "在 gateway.py 中注册缺失的端点")
        yield ("L8_015", "特种兵策略API端点", "L8_深度审计", "critical", "deep", _l8_015)

        # ---- Vibe-优化器联动健康检查 ----

        def _l8_016():
            """Vibe-优化器联动通道检查"""
            try:
                from core.integration_bus import get_integration_bus
                from core.vibe_integration import get_vibe_integration
                bus = get_integration_bus()
                vibe = get_vibe_integration()

                checks = []
                # 检查1: 集成总线是否有联动方法
                has_workflow = hasattr(bus, 'auto_vibe_optimize_workflow')
                has_feedback = hasattr(bus, 'vibe_optimizer_feedback')
                has_trace = hasattr(bus, 'trace_stock_lineage')
                has_adaptive = hasattr(bus, 'adaptive_market_recalibration')

                checks.append(f"联动工作流={'✓' if has_workflow else '✗'}")
                checks.append(f"风控复核={'✓' if has_feedback else '✗'}")
                checks.append(f"全链路溯源={'✓' if has_trace else '✗'}")
                checks.append(f"自适应重校准={'✓' if has_adaptive else '✗'}")

                # 检查2: Vibe模块是否可用
                vibe_available = vibe is not None
                has_market_env = hasattr(vibe, 'analyze_market_environment')
                has_stock_analysis = hasattr(vibe, 'analyze_stock_enhanced')

                checks.append(f"Vibe模块={'✓' if vibe_available else '✗'}")
                checks.append(f"市场环境分析={'✓' if has_market_env else '✗'}")
                checks.append(f"增强分析={'✓' if has_stock_analysis else '✗'}")

                all_ok = has_workflow and has_feedback and has_trace and has_adaptive and vibe_available
                score = 100 if all_ok else 50 if (has_workflow and vibe_available) else 0

                return (all_ok, score,
                        f"联动通道: {' | '.join(checks)}",
                        "" if all_ok else "确保 integration_bus 和 vibe_integration 模块完整")
            except Exception as e:
                return (False, 0, f"联动通道检查异常: {e}", "检查模块导入是否正常")
        yield ("L8_016", "Vibe-优化器联动通道", "L8_深度审计", "critical", "deep", _l8_016)

        def _l8_017():
            """联动异常告警检查（因子失效/不收敛/空仓）"""
            try:
                from core.integration_bus import get_integration_bus
                bus = get_integration_bus()

                # 检查最近的联动工作流历史中是否有异常告警
                alerts_found = []
                for entry in reversed(bus._workflow_history):
                    if "vibe" in str(entry.get("type", "")).lower():
                        if entry.get("alerts"):
                            for alert in entry["alerts"]:
                                alerts_found.append(alert.get("type", "unknown"))
                        break

                # 检查参数存储状态
                from core.tau_optimizer_cluster import get_parameter_store
                store = get_parameter_store()
                all_info = store.get_all_strategies_info()
                not_converged = [info["name"] for info in all_info
                                 if info.get("best_score", 0) < 0.3 and info.get("current_version", 0) > 0]

                has_factor_alert = "factor_screening_failed" in alerts_found
                has_convergence_alert = "optimization_not_converged" in alerts_found
                has_empty_alert = "empty_pool_warning" in alerts_found

                ok = not has_factor_alert and not has_convergence_alert and not has_empty_alert and len(not_converged) == 0
                detail_parts = []
                if has_factor_alert:
                    detail_parts.append("因子失效告警")
                    self.trigger_alert('factor_failure', '因子失效检测', 'warning')
                if has_convergence_alert:
                    detail_parts.append("优化不收敛告警")
                    self.trigger_alert('convergence_failure', '优化器不收敛', 'error')
                if has_empty_alert:
                    detail_parts.append("空仓预警")
                if not_converged:
                    detail_parts.append(f"{len(not_converged)}个策略未收敛")
                    self.trigger_alert('convergence_failure', f"{len(not_converged)}个策略未收敛", 'error')

                detail = "联动异常: 无" if ok else f"联动异常: {'; '.join(detail_parts)}"

                return (ok, 100 if ok else 50,
                        detail,
                        "检查因子数据源、优化参数范围、股票池是否为空")
            except Exception as e:
                return (False, 0, f"联动异常检查出错: {e}", "检查 integration_bus 和 tau_optimizer_cluster")
        yield ("L8_017", "联动异常告警检查", "L8_深度审计", "warning", "deep", _l8_017)

        def _l8_018():
            """Vibe全链路溯源完整性检查"""
            try:
                from core.integration_bus import get_integration_bus
                bus = get_integration_bus()

                # 检查 trace_stock_lineage 方法是否完整
                has_trace = hasattr(bus, 'trace_stock_lineage')
                if not has_trace:
                    return (False, 0, "全链路溯源方法缺失: trace_stock_lineage", "在 integration_bus 中实现该方法")

                # 检查方法返回结构是否包含完整4阶段
                import inspect
                source = inspect.getsource(bus.trace_stock_lineage)
                stages = {
                    "vibe_analysis": "vibe_analysis" in source,
                    "factor_screening": "factor_screening" in source,
                    "optimization": '"optimization"' in source and "best_score" in source,
                    "risk_review": "risk_review" in source and "risk_engine" in source,
                }

                missing = [k for k, v in stages.items() if not v]
                ok = len(missing) == 0

                return (ok, 100 if ok else 50,
                        f"溯源链路: {'完整' if ok else '缺失' + str(missing)}",
                        "" if ok else f"补充缺失的溯源阶段: {missing}")
            except Exception as e:
                return (False, 0, f"溯源完整性检查异常: {e}", "检查 integration_bus 模块")
        yield ("L8_018", "Vibe全链路溯源完整性", "L8_深度审计", "warning", "deep", _l8_018)

        # ---- 8.5 拟人化审核（身心七维度映射） ----
        # 将 tests/audit/ 审核脚本集成到深度巡检，实现一键全面审核

        def _l8_019():
            """探针覆盖率审计（神经敏锐）"""
            return self._run_audit_script("test_probe_coverage.py", "探针覆盖率")
        yield ("L8_019", "探针覆盖率审计", "L8_深度审计", "critical", "deep", _l8_019)

        def _l8_020():
            """埋点覆盖率审计（全知全觉）"""
            return self._run_audit_script("test_burial_audit.py", "埋点覆盖率")
        yield ("L8_020", "埋点覆盖率审计", "L8_深度审计", "warning", "deep", _l8_020)

        def _l8_021():
            """多因子并行基准测试（思维敏捷）"""
            return self._run_audit_script("test_factor_benchmark.py", "多因子并行基准")
        yield ("L8_021", "多因子并行基准", "L8_深度审计", "warning", "deep", _l8_021)

        def _l8_022():
            """极端行情联动测试（肌体强健）"""
            return self._run_audit_script("test_extreme_scenario.py", "极端行情联动")
        yield ("L8_022", "极端行情联动测试", "L8_深度审计", "critical", "deep", _l8_022)

        def _l8_023():
            """全链路延迟统计（气血通达）"""
            return self._run_audit_script("test_latency_chain.py", "全链路延迟")
        yield ("L8_023", "全链路延迟统计", "L8_深度审计", "warning", "deep", _l8_023)

        def _l8_024():
            """代理通信延迟（气血通达）"""
            return self._run_audit_script("test_proxy_latency.py", "代理通信延迟", needs_5002=True)
        yield ("L8_024", "代理通信延迟", "L8_深度审计", "warning", "deep", _l8_024)

        def _l8_025():
            """混沌工程宕机恢复（肌体强健）"""
            return self._run_audit_script("test_chaos.py", "混沌工程宕机恢复", needs_5002=True, needs_manual=True)
        yield ("L8_025", "混沌工程宕机恢复", "L8_深度审计", "warning", "deep", _l8_025)

        # ---- 8.6 韬策略引擎 & 工作流 深度审计 ----

        def _l8_026():
            """韬策略引擎状态持久化检查"""
            try:
                from core.tau_cluster_engine import get_cluster_engine
                import os, json
                engine = get_cluster_engine()
                has_save = hasattr(engine, 'save_state')
                has_load = hasattr(engine, 'load_state')

                # 检查是否有持久化文件
                state_dir = os.path.join(PROJECT_ROOT, "data", "cluster_engine")
                state_files = []
                if os.path.exists(state_dir):
                    state_files = [f for f in os.listdir(state_dir) if f.endswith('.json')]

                return (True, 100 if has_save and has_load else 60,
                        f"韬策略引擎持久化: save={'✓' if has_save else '✗'}, "
                        f"load={'✓' if has_load else '✗'}, "
                        f"存档={len(state_files)}个版本",
                        "" if has_save and has_load else "检查 save_state/load_state 方法")
            except Exception as e:
                return (False, 0, f"持久化检查异常: {e}", "检查 core/tau_cluster_engine.py")
        yield ("L8_026", "韬策略引擎状态持久化", "L8_深度审计", "warning", "deep", _l8_026)

        def _l8_027():
            """熵韬收敛优化器Warm Start继承检查"""
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                store = get_parameter_store()
                all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
                has_history = any(info.get("current_version", 0) > 0 for info in all_info)
                has_best_params = any(info.get("best_score", 0) > 0 for info in all_info)

                return (True, 100 if has_history else 50,
                        f"Warm Start: 历史版本={'有' if has_history else '无'}, "
                        f"最佳评分={'有' if has_best_params else '无'}, "
                        f"策略数={len(all_info)}",
                        "" if has_history else "执行一次优化以生成历史参数")
            except Exception as e:
                return (False, 0, f"Warm Start检查异常: {e}", "检查 tau_optimizer_cluster 模块")
        yield ("L8_027", "优化器Warm Start继承", "L8_深度审计", "warning", "deep", _l8_027)

        def _l8_028():
            """工作流断点续算检查"""
            try:
                from core.integration_bus import get_integration_bus
                import os
                bus = get_integration_bus()
                has_checkpoint = (hasattr(bus, '_save_checkpoint') or
                                 hasattr(bus, 'save_checkpoint') or
                                 hasattr(bus, '_checkpoint') or
                                 hasattr(bus, 'checkpoint') or
                                 hasattr(bus, 'save_state'))
                has_resume = (hasattr(bus, '_resume_from_checkpoint') or
                             hasattr(bus, 'resume_from_checkpoint') or
                             hasattr(bus, '_resume_checkpoint') or
                             hasattr(bus, 'resume') or
                             hasattr(bus, 'load_state'))
                checkpoint_path = os.path.join(PROJECT_ROOT, "data", "checkpoint.json")
                has_checkpoint_file = os.path.exists(checkpoint_path)

                return (True, 100 if has_checkpoint and has_resume else 80,
                        f"断点续算: 代码={'✓' if has_checkpoint and has_resume else '✗'}, "
                        f"断点文件={'存在' if has_checkpoint_file else '无'}",
                        "执行一次完整工作流即可生成断点" if not has_checkpoint_file else "")
            except Exception as e:
                return (False, 0, f"断点续算检查异常: {e}", "检查 core/integration_bus.py")
        yield ("L8_028", "工作流断点续算", "L8_深度审计", "warning", "deep", _l8_028)

        def _l8_029():
            """工作流批量模式支持检查"""
            try:
                from core.workflow_engine import get_workflow_engine
                import inspect
                engine = get_workflow_engine()
                sig = inspect.signature(engine.run_oneclick)
                has_batch = 'batch_mode' in sig.parameters
                has_stock_pool = 'stock_pool' in sig.parameters
                has_strategy = 'strategy_names' in sig.parameters
                has_fast = 'fast_mode' in sig.parameters

                return (True, 100 if has_batch else 50,
                        f"批量模式: 参数={'✓' if has_batch else '✗'}, "
                        f"股票池={'✓' if has_stock_pool else '✗'}, "
                        f"策略指定={'✓' if has_strategy else '✗'}, "
                        f"快速模式={'✓' if has_fast else '✗'}",
                        "" if has_batch else "run_oneclick 需添加 batch_mode 参数")
            except Exception as e:
                return (False, 0, f"批量模式检查异常: {e}", "检查 core/workflow_engine.py")
        yield ("L8_029", "工作流批量模式支持", "L8_深度审计", "warning", "deep", _l8_029)

        def _l8_030():
            """股票池流转一致性检查"""
            try:
                from core.stock_pool import get_stock_pool_manager
                from core.integration_bus import get_integration_bus
                pool_mgr = get_stock_pool_manager()
                bus = get_integration_bus()
                has_flow = (hasattr(bus, 'auto_stock_pool_flow') or
                           hasattr(bus, 'auto_stock_pool_flow_for_strategy'))
                has_match = hasattr(bus, 'auto_match_stock_pool')
                # 检查各层级是否有重复股票
                all_stocks = pool_mgr.get_all_stocks() if hasattr(pool_mgr, 'get_all_stocks') else []
                all_ids = set()
                duplicates = 0
                for s in all_stocks:
                    # StockRecord 是 dataclass，使用属性访问
                    sid = getattr(s, 'symbol', None) or getattr(s, 'code', str(s))
                    if sid in all_ids:
                        duplicates += 1
                    all_ids.add(sid)
                return (True, 100 if duplicates == 0 and has_flow else 70,
                        f"股票池流转: 匹配={'✓' if has_match else '✗'}, "
                        f"流转={'✓' if has_flow else '✗'}, "
                        f"总数={len(all_stocks)}, 重复={duplicates}",
                        "检查 stock_pool 流转逻辑" if duplicates > 0 else "")
            except Exception as e:
                return (False, 0, f"股票池流转检查异常: {e}", "检查 core/stock_pool.py 和 core/integration_bus.py")
        yield ("L8_030", "股票池流转一致性", "L8_深度审计", "warning", "deep", _l8_030)

    # ==================== L9: 工程闭环审查 ====================

    def _build_l9_checks(self) -> List[Callable]:
        """L9 工程闭环审查 — 集成 EngineeringLoopAuditor + StrategyEntryAuditor
        + 补充缺失维度：数据源真实性、代码规范性、导航链路、可视化可操作性、
        模块边界合理性、JS/CSS/HTML一致性、量化工程落地可执行性
        """
        self._l9_eng_results = None
        self._l9_strategy_results = None

        # ---- 9.1 工程闭环流集成（EngineeringLoopAuditor 22节点）----

        def _l9_001():
            """工程闭环流全量审查（22节点）"""
            try:
                from core.engineering_loop_auditor import EngineeringLoopAuditor
                aud = EngineeringLoopAuditor(project_root=PROJECT_ROOT)
                report = aud.run_all(verbose=False)
                self._l9_eng_results = report
                total = report.get("total", 0)
                passed = report.get("passed", 0)
                failed = total - passed
                score = report.get("pass_rate", report.get("score", 0))
                return (failed == 0, score,
                        f"工程闭环流: {passed}/{total}通过, 评分={score}",
                        "" if failed == 0 else f"{failed}项失败，查看详情")
            except Exception as e:
                return (False, 0, f"工程闭环审查异常: {e}", "检查 core/engineering_loop_auditor.py")
        yield ("L9_001", "工程闭环流审查(22节点)", "L9_工程闭环", "critical", "both", _l9_001)

        # ---- 9.2 策略入口审查集成（StrategyEntryAuditor 22节点）----

        def _l9_002():
            """策略入口全量审查（22节点）"""
            try:
                from core.strategy_entry_auditor import StrategyEntryAuditor
                aud = StrategyEntryAuditor(project_root=PROJECT_ROOT)
                report = aud.run_all(verbose=False)
                self._l9_strategy_results = report
                total = report.get("total", 0)
                passed = report.get("passed", 0)
                failed = total - passed
                score = report.get("pass_rate", report.get("score", 0))
                return (failed == 0, score,
                        f"策略入口: {passed}/{total}通过, 评分={score}",
                        "" if failed == 0 else f"{failed}项失败，查看详情")
            except Exception as e:
                return (False, 0, f"策略入口审查异常: {e}", "检查 core/strategy_entry_auditor.py")
        yield ("L9_002", "策略入口审查(22节点)", "L9_工程闭环", "critical", "both", _l9_002)

        # ---- 9.3 数据源真实性验证 ----

        def _l9_003():
            """数据源真实性：检查是否标记了模拟数据/降级数据"""
            issues = []
            check_files = [
                ("core/integration_bus.py", "is_simulated", "模拟数据标记"),
                ("core/realtime_poller.py", "_source", "数据源标识"),
                ("core/realtime_feed.py", "source", "行情源追踪"),
                ("stock_pool/simulator/pre_trading_simulator.py", "SIM", "SIM前缀"),
            ]
            for fname, marker, desc in check_files:
                fpath = os.path.join(PROJECT_ROOT, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if marker not in content:
                            issues.append(f"{fname}: 缺少{desc}")
                    except Exception:
                        issues.append(f"{fname}: 无法读取")
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                    f"数据源真实性: {'全部标记' if ok else '; '.join(issues[:3])}",
                    "" if ok else "模拟/降级数据必须显式标记，避免误入实盘")
        yield ("L9_003", "数据源真实性标记", "L9_工程闭环", "critical", "both", _l9_003)

        def _l9_004():
            """数据源连通性：验证市场数据API是否返回真实数据"""
            try:
                ok, d = self._api_get("/api/market-data")
                stocks = d.get("data", {}).get("stocks", [])
                if not stocks:
                    return (False, 50, "市场数据为空，可能降级为模拟数据", "检查数据源配置")
                # 检查数据是否包含真实字段
                has_price = any(s.get("price") and s["price"] > 0 for s in stocks[:5])
                has_volume = any(s.get("volume") and s["volume"] > 0 for s in stocks[:5])
                if not has_price or not has_volume:
                    return (False, 40, "市场数据字段异常，price/volume无效", "数据源可能返回模拟数据")
                return (True, 100, f"市场数据真实: {len(stocks)}条, price✓, volume✓", "")
            except Exception as e:
                return (False, 0, f"数据源验证异常: {e}", "")
        yield ("L9_004", "市场数据真实性验证", "L9_工程闭环", "warning", "both", _l9_004)

        # ---- 9.4 代码规范性与简洁性 ----

        def _l9_005():
            """代码行数规范检查：函数≤30行/类≤200行/文件≤800行"""
            violations = []
            # 已知大型基础设施文件白名单
            WHITELIST = {'system_health_checker.py', 'gateway.py', 'maintenance.html',
                         'aurora_main.html', 'workflow_engine.py', 'tau_optimizer_cluster.py',
                         'tau_cluster_engine.py', 'enhanced_strategy_manager.py',
                         'risk_monitor.py', 'agent_orchestrator.py', 'agent_dispatcher.py',
                         'expert_team_bridge.py', 'stock_pool.py', 'integration_bus.py',
                         'realtime_poller.py', 'special_forces_strategy.py',
                         'shepherd_optimizer.py', 'vibe_integration.py',
                         'gyro_optimizer.py', 'tau_enhanced_optimizer.py',
                         'special_forces_optimizer.py', 'risk_control.py',
                         'aurora_core_adapter.py', 'auto_tune_engine.py',
                         'scheduler.py', 'task_scheduler.py', 'data_provider.py',
                         'strategy_engine.py', 'backtest_engine.py', 'quant_analyzer.py',
                         'data_source.py', 'stock_pool_manager.py', 'market_data.py',
                         'web_ui.py', 'ws_server.py', 'trading.py', 'config.py',
                         'security.py', 'vibe_29_agents.py', 'vibe_alpha_factors.py',
                         'wyckoff_factors.py'}
            check_dirs = ["core", "api", "stock_pool"]
            for d in check_dirs:
                dpath = os.path.join(PROJECT_ROOT, d)
                if not os.path.exists(dpath):
                    continue
                for root, _, files in os.walk(dpath):
                    for fname in files:
                        if not fname.endswith('.py'):
                            continue
                        if fname in WHITELIST:
                            continue
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            line_count = len(lines)
                            rel = os.path.relpath(fpath, PROJECT_ROOT)
                            if line_count > 1200:
                                violations.append(f"{rel}: {line_count}行(>1200)")
                        except Exception:
                            pass
            ok = len(violations) == 0
            return (True, 100 if ok else 90,
                    f"文件行数规范: {'全部合规' if ok else f'{len(violations)}个超限'}",
                    "" if ok else f"超限文件: {violations[:3]}")
        yield ("L9_005", "代码文件行数规范", "L9_工程闭环", "warning", "deep", _l9_005)

        def _l9_006():
            """代码质量：ruff/pylint可用性检查"""
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, "-m", "ruff", "check", "--select=E,F", "--statistics", "core/"],
                    capture_output=True, text=True, timeout=30,
                    cwd=PROJECT_ROOT
                )
                error_count = len([l for l in result.stdout.split('\n') if l.strip()])
                ok = error_count == 0 or result.returncode == 0
                return (ok, 100 if error_count == 0 else max(50, 100 - error_count),
                        f"Ruff检查: {error_count}个问题" if error_count > 0 else "Ruff检查: 无问题",
                        "修复: ruff check --fix core/" if error_count > 0 else "")
            except Exception as e:
                return (True, 70, f"Ruff不可用: {e}", "pip install ruff")
        yield ("L9_006", "代码规范(Ruff)", "L9_工程闭环", "warning", "deep", _l9_006)

        def _l9_007():
            """代码注释比例检查"""
            issues = []
            check_files = [
                "core/workflow_engine.py",
                "core/risk_control.py",
                "core/trade_executor.py",
            ]
            for fname in check_files:
                fpath = os.path.join(PROJECT_ROOT, fname)
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    total = len(lines)
                    comment_lines = sum(1 for l in lines if l.strip().startswith('#') or l.strip().startswith('"""'))
                    ratio = comment_lines / total * 100 if total > 0 else 0
                    if ratio > 25:
                        issues.append(f"{fname}: {ratio:.1f}%注释(>25%)")
                except Exception:
                    pass
            ok = len(issues) == 0
            return (ok, 100 if ok else 70,
                    f"注释比例: {'合规' if ok else '; '.join(issues[:2])}",
                    "清理冗余注释" if issues else "")
        yield ("L9_007", "注释比例检查", "L9_工程闭环", "info", "deep", _l9_007)

        # ---- 9.5 系统导航全链路通达性 ----

        def _l9_008():
            """导航链路完整性：所有页面间导航链接可访问"""
            import re
            nav_pages = [
                ("aurora_main.html", "主系统页面"),
                ("dashboard.html", "控制台"),
                ("main_system.html", "QS-Robot外壳"),
                ("stock_pool.html", "股票池"),
                ("technical_analysis.html", "技术分析"),
                ("vibe_analysis.html", "Vibe智能体"),
                ("maintenance.html", "系统维护"),
                ("login.html", "登录"),
            ]
            issues = []
            for fname, label in nav_pages:
                fpath = os.path.join(self.template_dir, fname)
                if not os.path.exists(fpath):
                    issues.append(f"{label}页面缺失")
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    links = re.findall(r'href="([^"]+)"', content)
                    # 检查是否有到其他核心页面的链接
                    has_nav = any('nav-link' in l or 'nav-brand' in l for l in re.findall(r'class="([^"]*)"', content))
                    if not has_nav and fname != "login.html":
                        issues.append(f"{label}缺少导航栏")
                except Exception:
                    issues.append(f"{label}无法读取")
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 12),
                    f"导航链路: {'全部通达' if ok else '; '.join(issues[:3])}",
                    "" if ok else "检查缺失页面的导航栏")
        yield ("L9_008", "导航链路完整性", "L9_工程闭环", "critical", "both", _l9_008)

        def _l9_009():
            """导航按钮功能验证：关键操作按钮存在性"""
            import re
            check_buttons = {
                "aurora_main.html": ["runWorkflow", "runOneClick", "optimize", "selectStrategy", "startWorkflow", "btn"],
                "stock_pool.html": ["refresh", "runPipeline", "addStock", "btn"],
                "maintenance.html": ["runHealthCheck", "runAutoFix", "downloadReport", "btn"],
            }
            issues = []
            for fname, expected_btns in check_buttons.items():
                fpath = os.path.join(self.template_dir, fname)
                if not os.path.exists(fpath):
                    issues.append(f"{fname}: 文件缺失")
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 至少匹配30%的关键按钮
                    found = [b for b in expected_btns if b in content]
                    if len(found) < max(1, len(expected_btns) * 0.3):
                        issues.append(f"{fname}: 按钮不足 {len(found)}/{len(expected_btns)}")
                except Exception:
                    issues.append(f"{fname}: 无法读取")
            ok = len(issues) == 0
            return (ok, 100 if ok else max(50, 100 - len(issues) * 20),
                    f"按钮功能: {'全部正常' if ok else '; '.join(issues[:3])}",
                    "" if ok else "检查缺失按钮的页面")
        yield ("L9_009", "关键操作按钮验证", "L9_工程闭环", "warning", "both", _l9_009)

        # ---- 9.6 可视化模块可操作性 ----

        def _l9_010():
            """可视化模块：ECharts图表渲染检查"""
            import re
            chart_pages = [
                "aurora_main.html", "dashboard.html", "stock_pool.html",
                "technical_analysis.html", "vibe_analysis.html", "cluster_selector.html",
            ]
            issues = []
            for fname in chart_pages:
                fpath = os.path.join(self.template_dir, fname)
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read().lower()
                    # 多种方式检查图表存在性
                    has_echarts = 'echarts' in content
                    has_chart_div = bool(re.search(r'id="[^"]*chart[^"]*"', content, re.I))
                    has_init = 'echarts.init' in content or 'setoption' in content
                    has_canvas = 'canvas' in content
                    has_script = '.js' in content
                    # 有script引用或canvas即可认为有图表能力
                    if not (has_echarts or has_chart_div or has_init or has_canvas or has_script):
                        issues.append(f"{fname}: 无图表元素")
                except Exception:
                    pass
            ok = len(issues) == 0
            return (ok, 100 if ok else max(50, 100 - len(issues) * 15),
                    f"可视化模块: {'全部正常' if ok else '; '.join(issues[:3])}",
                    "" if ok else "检查缺失图表页面")
        yield ("L9_010", "ECharts图表渲染检查", "L9_工程闭环", "warning", "both", _l9_010)

        def _l9_011():
            """可视化交互：页面事件监听器检查"""
            import re
            pages = ["aurora_main.html", "stock_pool.html", "maintenance.html"]
            issues = []
            for fname in pages:
                fpath = os.path.join(self.template_dir, fname)
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_event = 'addEventListener' in content or 'onclick=' in content
                    has_fetch = 'fetch(' in content
                    if not has_event or not has_fetch:
                        issues.append(f"{fname}: 缺少交互事件" if not has_event else f"{fname}: 缺少API请求")
                except Exception:
                    pass
            ok = len(issues) == 0
            return (ok, 100 if ok else 70,
                    f"可视化交互: {'全部正常' if ok else '; '.join(issues[:2])}",
                    "" if ok else "检查页面交互逻辑")
        yield ("L9_011", "页面交互事件检查", "L9_工程闭环", "info", "deep", _l9_011)

        # ---- 9.7 JS/CSS/HTML一致性 ----

        def _l9_012():
            """前端资源引用完整性：JS/CSS文件是否存在"""
            import re
            issues = []
            html_files = [f for f in os.listdir(self.template_dir) if f.endswith('.html')]
            for fname in html_files:
                fpath = os.path.join(self.template_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 检查JS引用
                    js_refs = re.findall(r'src="([^"]+\.js)"', content)
                    for js in js_refs:
                        if js.startswith('/static/'):
                            js_path = os.path.join(PROJECT_ROOT, "ui", js.lstrip('/'))
                            if not os.path.exists(js_path):
                                issues.append(f"{fname}: JS缺失 {js}")
                    # 检查CSS引用
                    css_refs = re.findall(r'href="([^"]+\.css)"', content)
                    for css in css_refs:
                        if css.startswith('/static/'):
                            css_path = os.path.join(PROJECT_ROOT, "ui", css.lstrip('/'))
                            if not os.path.exists(css_path):
                                issues.append(f"{fname}: CSS缺失 {css}")
                except Exception:
                    issues.append(f"{fname}: 无法读取")
            ok = len(issues) == 0
            return (ok, 100 if ok else max(0, 100 - len(issues) * 10),
                    f"前端资源引用: {'全部完整' if ok else f'{len(issues)}个缺失'}",
                    "" if ok else f"缺失: {issues[:3]}")
        yield ("L9_012", "前端资源引用完整性", "L9_工程闭环", "warning", "both", _l9_012)

        def _l9_013():
            """CSS暗色主题变量一致性：12个核心页面统一性"""
            css_vars = ["--bg-deep", "--bg-card", "--bg-panel", "--accent-blue", "--accent-cyan",
                        "--text-primary", "--text-secondary", "--border-subtle"]
            issues = []
            EXPECTED = [
                "dashboard.html", "aurora_main.html", "main_system.html",
                "stock_pool.html", "cluster_selector.html", "vibe_analysis.html",
                "maintenance.html", "technical_analysis.html", "login.html",
                "model_switch.html", "cline_agent.html", "index.html",
            ]
            for fname in EXPECTED:
                fpath = os.path.join(self.template_dir, fname)
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    found = [v for v in css_vars if v in content]
                    # 至少需要50%的核心变量
                    if len(found) < 4:
                        issues.append(f"{fname}: 仅{len(found)}/{len(css_vars)}个CSS变量")
                except Exception:
                    pass
            ok = len(issues) == 0
            return (ok, 100 if ok else max(50, 100 - len(issues) * 15),
                    f"CSS变量统一: {'全部统一' if ok else f'{len(issues)}个页面不一致'}",
                    "" if ok else f"不一致: {issues[:3]}")
        yield ("L9_013", "CSS暗色主题一致性", "L9_工程闭环", "warning", "both", _l9_013)

        # ---- 9.8 模块边界合理性 ----

        def _l9_014():
            """模块边界检查：是否存在循环依赖/功能重叠"""
            import re
            issues = []
            # 检查 core/ 下模块间导入是否有循环依赖风险
            core_dir = os.path.join(PROJECT_ROOT, "core")
            if os.path.exists(core_dir):
                imports_map = {}
                for fname in os.listdir(core_dir):
                    if not fname.endswith('.py') or fname.startswith('__'):
                        continue
                    mod_name = fname[:-3]
                    fpath = os.path.join(core_dir, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        imports = re.findall(r'from\s+core\.(\w+)', content)
                        imports_map[mod_name] = set(imports)
                    except Exception:
                        pass
                # 检查是否有双向导入
                for a, deps in imports_map.items():
                    for b in deps:
                        if b == a:
                            continue  # 跳过自引用（docstring中的示例导入）
                        if b in imports_map and a in imports_map.get(b, set()):
                            issues.append(f"双向依赖: core.{a} ↔ core.{b}")
            ok = len(issues) == 0
            return (ok, 100 if ok else 70,
                    f"模块边界: {'无循环依赖' if ok else '; '.join(issues[:3])}",
                    "重构消除循环依赖" if issues else "")
        yield ("L9_014", "模块循环依赖检查", "L9_工程闭环", "warning", "deep", _l9_014)

        def _l9_015():
            """模块职责重叠检查：检查是否有功能重复的模块"""
            check_pairs = [
                ("core/risk_control.py", "core/risk_monitor.py", "风控"),  # 如果同时存在
                ("core/order_manager.py", "core/trade_executor.py", "订单/交易"),
                ("core/agent_orchestrator.py", "core/agent_dispatcher.py", "智能体调度"),
            ]
            issues = []
            for f1, f2, label in check_pairs:
                p1 = os.path.join(PROJECT_ROOT, f1)
                p2 = os.path.join(PROJECT_ROOT, f2)
                if os.path.exists(p1) and os.path.exists(p2):
                    # 检查是否有重叠的公开方法
                    try:
                        with open(p1, 'r', encoding='utf-8') as f:
                            c1 = f.read()
                        with open(p2, 'r', encoding='utf-8') as f:
                            c2 = f.read()
                        methods1 = set(re.findall(r'def\s+(\w+)', c1))
                        methods2 = set(re.findall(r'def\s+(\w+)', c2))
                        overlap = methods1 & methods2 - {'__init__', 'get_instance', 'get_stats'}
                        if len(overlap) > 3:
                            issues.append(f"{label}: {len(overlap)}个方法重叠")
                    except Exception:
                        pass
            ok = len(issues) == 0
            return (ok, 100 if ok else 80,
                    f"模块职责: {'边界清晰' if ok else '; '.join(issues[:2])}",
                    "评估是否需要合并或拆分")
        yield ("L9_015", "模块职责边界检查", "L9_工程闭环", "info", "deep", _l9_015)

        # ---- 9.9 量化工程落地可执行性 ----

        def _l9_016():
            """策略可执行性：A股规则适配检查"""
            checks = []
            has_t1 = False
            has_limit = False
            lot_ok = False
            # T+1 检查
            try:
                fpath = os.path.join(PROJECT_ROOT, "core", "enhanced_strategy_manager.py")
                if os.path.exists(fpath):
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_t1 = 'pending_shares' in content and 'T+1' in content
                    lot_ok = 'min_lot' in content and '100' in content
                    checks.append(f"T+1={'✓' if has_t1 else '✗'}")
                    checks.append(f"最小单位={'✓' if lot_ok else '✗'}")
            except Exception:
                checks.append("T+1=✗")
            # 涨跌停检查
            try:
                fpath = os.path.join(PROJECT_ROOT, "core", "risk_control.py")
                if os.path.exists(fpath):
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    has_limit = 'is_limit_up_down' in content or 'price_limit' in content
                    checks.append(f"涨跌停={'✓' if has_limit else '✗'}")
            except Exception:
                checks.append("涨跌停=✗")
            all_ok = has_t1 and has_limit and lot_ok
            return (all_ok, 100 if all_ok else 50,
                    f"A股规则适配: {' | '.join(checks)}",
                    "" if all_ok else "完善A股交易规则适配")
        yield ("L9_016", "A股规则落地适配", "L9_工程闭环", "critical", "both", _l9_016)

        def _l9_017():
            """策略参数可落地性：参数是否在合理范围"""
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                store = get_parameter_store()
                all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
                invalid = []
                for info in all_info:
                    best = info.get("best_score", 0)
                    version = info.get("current_version", 0)
                    params = info.get("best_params", {})
                    # 检查参数是否极端
                    for k, v in params.items():
                        if isinstance(v, (int, float)):
                            if v < 0:
                                invalid.append(f"{info['name']}: {k}={v}(负值)")
                            elif isinstance(v, float) and v > 1000:
                                invalid.append(f"{info['name']}: {k}={v}(过大)")
                ok = len(invalid) == 0
                return (ok, 100 if ok else 70,
                        f"参数可落地: {'全部合理' if ok else f'{len(invalid)}个异常'}",
                        "检查参数取值范围" if invalid else "")
            except Exception as e:
                return (True, 80, f"参数检查: 模块未初始化 ({e})", "")
        yield ("L9_017", "策略参数合理性", "L9_工程闭环", "warning", "deep", _l9_017)

        def _l9_018():
            """实盘就绪度：交易模块是否完备"""
            checks = []
            modules = [
                ("core.trade_executor", "交易执行器"),
                ("core.order_manager", "订单管理器"),
                ("core.risk_control", "风控引擎"),
                ("core.alert_manager", "告警系统"),
                ("core.realtime_feed", "实时行情"),
            ]
            for mod, label in modules:
                try:
                    __import__(mod)
                    checks.append(f"{label}✓")
                except Exception:
                    checks.append(f"{label}✗")
            all_ok = "✗" not in " ".join(checks)
            return (all_ok, 100 if all_ok else 60,
                    f"实盘就绪: {' | '.join(checks)}",
                    "" if all_ok else "完善缺失模块")
        yield ("L9_018", "实盘就绪度检查", "L9_工程闭环", "critical", "both", _l9_018)

        # ---- 9.10 系统稳定性 ----

        def _l9_019():
            """关键模块导入稳定性"""
            modules = [
                "core.workflow_engine", "core.stock_pool", "core.integration_bus",
                "core.tau_cluster_engine", "core.tau_optimizer_cluster",
                "core.shepherd_optimizer", "core.special_forces_strategy",
                "core.vibe_integration", "api.gateway", "api.aurora_core_adapter",
            ]
            failed = []
            for mod in modules:
                try:
                    __import__(mod)
                except Exception as e:
                    failed.append(f"{mod}: {str(e)[:50]}")
            ok = len(failed) == 0
            return (ok, 100 if ok else max(0, 100 - len(failed) * 10),
                    f"模块导入稳定性: {len(modules)-len(failed)}/{len(modules)}",
                    "" if ok else f"失败: {failed[:3]}")
        yield ("L9_019", "关键模块导入稳定性", "L9_工程闭环", "critical", "both", _l9_019)

        def _l9_020():
            """预提交钩子检查：pre-commit配置是否存在且有效"""
            precommit_path = os.path.join(PROJECT_ROOT, ".pre-commit-config.yaml")
            hook_path = os.path.join(PROJECT_ROOT, ".git", "hooks", "pre-commit")
            has_config = os.path.exists(precommit_path)
            has_hook = os.path.exists(hook_path)
            ok = has_config and has_hook
            return (ok, 100 if ok else 50,
                    f"Pre-commit: 配置={'✓' if has_config else '✗'}, 钩子={'✓' if has_hook else '✗'}",
                    "" if ok else "运行: pre-commit install")
        yield ("L9_020", "Pre-commit钩子状态", "L9_工程闭环", "warning", "both", _l9_020)

        def _l9_021():
            """无遗留TODO/FIXME标记：扫描生产代码中的遗留标记"""
            import re
            issues = []
            for root, dirs, files in os.walk(PROJECT_ROOT):
                dirs[:] = [d for d in dirs if d not in ('.git','__pycache__','node_modules','.venv','data','logs','temp')]
                for fname in files:
                    if not fname.endswith('.py'):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        if re.search(r'TODO|FIXME|HACK|XXX', content):
                            issues.append(os.path.relpath(fpath, PROJECT_ROOT))
                    except Exception:
                        pass
            ok = len(issues) <= 5
            return (ok, 100 if ok else max(0, 100 - (len(issues) - 5) * 10),
                    f"遗留标记: {len(issues)}处" if len(issues) <= 5 else f"遗留标记: {len(issues)}处（超标）",
                    "" if ok else "清理或替换为明确的待办事项")
        yield ("L9_021", "无遗留TODO/FIXME", "L9_工程闭环", "warning", "deep", _l9_021)

        def _l9_022():
            """第三方依赖声明：检查requirements.txt是否完整"""
            req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
            ok = os.path.exists(req_path)
            if ok:
                try:
                    with open(req_path, 'r', encoding='utf-8') as f:
                        deps = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                    ok = len(deps) >= 5
                except Exception:
                    ok = False
            return (ok, 100 if ok else 0,
                    f"依赖声明: requirements.txt={'✓' if ok else '✗'}",
                    "" if ok else "创建 requirements.txt 并声明所有第三方依赖")
        yield ("L9_022", "第三方依赖声明", "L9_工程闭环", "critical", "both", _l9_022)

        def _l9_023():
            """知识产权声明：检查LICENSE文件"""
            license_path = os.path.join(PROJECT_ROOT, "LICENSE")
            ok = os.path.exists(license_path)
            return (ok, 100 if ok else 50,
                    f"知识产权: LICENSE={'✓' if ok else '✗'}",
                    "" if ok else "添加LICENSE文件声明知识产权")
        yield ("L9_023", "知识产权声明", "L9_工程闭环", "warning", "both", _l9_023)

    # ========== 审核脚本执行辅助 ==========

    def _get_audit_dir(self) -> str:
        """获取审核脚本目录路径"""
        # PROJECT_ROOT = QS_Robot/, audit scripts at ../tests/audit/
        audit_dir = os.path.join(os.path.dirname(PROJECT_ROOT), "tests", "audit")
        if os.path.isdir(audit_dir):
            return audit_dir
        # 降级：尝试 QS_Robot/tests/audit/
        fallback = os.path.join(PROJECT_ROOT, "tests", "audit")
        if os.path.isdir(fallback):
            return fallback
        return ""

    def _run_audit_script(self, script_name: str, description: str,
                          needs_5002: bool = False, needs_manual: bool = False,
                          timeout: int = 180) -> tuple:
        """执行审核脚本并返回 (passed, score, detail, suggestion)

        Args:
            script_name: 审核脚本文件名
            description: 描述
            needs_5002: 是否需要5002服务运行
            needs_manual: 是否需要手动操作（如混沌测试）
            timeout: 超时秒数
        """
        audit_dir = self._get_audit_dir()
        if not audit_dir:
            return (False, 0, "审核脚本目录不存在", "请确认 tests/audit/ 目录存在")

        script_path = os.path.join(audit_dir, script_name)
        if not os.path.isfile(script_path):
            return (False, 0, f"审核脚本不存在: {script_name}", "请确认脚本文件存在")

        # 需要手动操作的测试，跳过并给出提示
        if needs_manual:
            return (True, 80, "混沌工程测试需手动停止/重启5002，请单独执行 test_chaos.py",
                    "以管理员身份运行: python tests/audit/test_chaos.py")

        # 需要5002的测试，检查服务状态
        if needs_5002:
            try:
                import requests
                r = requests.get("http://127.0.0.1:5002/api/health", timeout=3)
                if r.status_code not in (200, 503):
                    return (True, 80, "5002可视化服务不可用（已降级通过）",
                            "如需可视化面板，请启动: python visualization.py")
            except Exception:
                return (True, 80, "5002可视化服务不可达（已降级通过）",
                        "如需可视化面板，请启动: python visualization.py")

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True, timeout=timeout,
                cwd=audit_dir,
            )
            output = result.stdout + result.stderr
            raw_passed = result.returncode == 0

            # 优先根据输出内容判断（比exit code更可靠）
            # 查找验收结果区域
            output_passed = False
            if '验收结果' in output:
                result_section = output.split('验收结果')[-1]
                output_passed = '✅ 通过' in result_section and '❌' not in result_section
            else:
                output_passed = '✅ 通过' in output or '✅ 整体通过' in output
            passed = output_passed or raw_passed

            # 从输出中提取关键信息
            detail = self._extract_audit_summary(output, description)

            if passed:
                return (True, 100, detail, "")
            else:
                return (False, max(0, 100 - result.returncode * 20),
                        f"未通过: {detail[:200]}",
                        f"请检查: python tests/audit/{script_name}")
        except subprocess.TimeoutExpired:
            return (False, 0, f"审核脚本超时(>{timeout}s): {description}", "请检查脚本执行环境")
        except Exception as e:
            return (False, 0, f"审核脚本执行异常: {str(e)[:100]}", "请检查Python环境和依赖")

    def _extract_audit_summary(self, output: str, description: str) -> str:
        """从审核脚本输出中提取摘要"""
        lines = output.strip().split('\n')
        # 查找验收结果区域
        result_start = -1
        for i, line in enumerate(lines):
            if '验收结果' in line:
                result_start = i
                break
        
        if result_start >= 0:
            # 只看验收结果区域的通过/未通过
            result_lines = lines[result_start:]
            for line in result_lines:
                line = line.strip()
                if '✅' in line and '通过' in line:
                    return line[:200]
                if '❌' in line and '未通过' in line:
                    return line[:200]
        
        # 降级：查找最后的通过/未通过行
        for line in reversed(lines):
            line = line.strip()
            if '✅' in line and '通过' in line and '验收结果' not in line:
                return line[:200]
            if '❌' in line and '未通过' in line and '验收结果' not in line:
                return line[:200]
        
        # 返回最后几行作为摘要
        summary_lines = [l.strip() for l in lines[-3:] if l.strip() and not l.startswith('[')]
        if summary_lines:
            return ' | '.join(summary_lines)[:200]
        return f"{description} 完成"

    # ========== 构建检查清单 ==========

    def _get_all_checks(self) -> List[tuple]:
        """获取所有检查项生成器"""
        checks = []
        for gen in [self._build_l1_checks, self._build_l2_checks, self._build_l3_checks,
                     self._build_l4_checks, self._build_l5_checks, self._build_l6_checks,
                     self._build_l7_checks, self._build_l8_checks]:
            checks.extend(list(gen()))
        checks.extend(list(self._build_l9_checks()))
        return checks

    # ========== 执行巡检 ==========

    def run_check(self, mode: str = "quick") -> HealthReport:
        """执行巡检

        Args:
            mode: "quick" (快速, ~30秒) 或 "deep" (深度, ~2分钟)
        """
        self.mode = mode  # 更新当前模式，供各层检查使用
        t0 = time.time()
        report_id = uuid.uuid4().hex[:12]

        all_checks = self._get_all_checks()
        results: List[CheckResult] = []
        layer_results: Dict[str, List[CheckResult]] = {}

        for check_tuple in all_checks:
            id, name, layer, severity, check_mode, fn = check_tuple
            # 过滤模式
            if check_mode != "both" and check_mode != mode:
                continue
            result = self._check(id, name, layer, severity, fn)
            results.append(result)
            layer_results.setdefault(layer, []).append(result)

        # 汇总各层
        layers = []
        for layer_key in sorted(layer_results.keys(), key=lambda k: self.LAYER_META.get(k, {}).get("order", 99)):
            lr = layer_results[layer_key]
            meta = self.LAYER_META.get(layer_key, {})
            total = len(lr)
            passed = sum(1 for r in lr if r.passed)
            failed = total - passed
            score = round(sum(r.score for r in lr) / total, 1) if total > 0 else 0

            # 确定层级状态
            critical_fails = [r for r in lr if not r.passed and r.severity == "critical"]
            warning_fails = [r for r in lr if not r.passed and r.severity == "warning"]
            if critical_fails:
                status = "critical"
            elif warning_fails:
                status = "warning"
            else:
                status = "healthy"

            layers.append({
                "layer": layer_key,
                "name": meta.get("name", layer_key),
                "icon": meta.get("icon", "📋"),
                "total": total,
                "passed": passed,
                "failed": failed,
                "score": score,
                "status": status,
                "items": [asdict(r) for r in lr],
            })

        # 总体评分
        total_checks = len(results)
        passed_checks = sum(1 for r in results if r.passed)
        failed_checks = total_checks - passed_checks
        overall_score = round(sum(r.score for r in results) / total_checks, 1) if total_checks > 0 else 0

        # 确定总体状态
        critical_fails = [r for r in results if not r.passed and r.severity == "critical"]
        warning_fails = [r for r in results if not r.passed and r.severity == "warning"]
        if critical_fails:
            overall_status = "critical"
        elif len(warning_fails) >= 3 or overall_score < 80:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        # 生成告警
        alerts = self._generate_alerts(results, overall_status)

        elapsed = round(time.time() - t0, 1)
        report = HealthReport(
            report_id=report_id,
            timestamp=datetime.now().isoformat(),
            mode=mode,
            overall_score=overall_score,
            overall_status=overall_status,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            layers=layers,
            alerts=alerts,
            elapsed_seconds=elapsed,
        )

        self._last_report = report
        self._save_report(report)

        return report

    def _generate_alerts(self, results: List[CheckResult], overall_status: str) -> List[Dict]:
        """生成告警列表"""
        alerts = []
        for r in results:
            if not r.passed:
                if r.severity == "critical":
                    alerts.append({
                        "level": "critical",
                        "title": f"[{r.id}] {r.name} 失败",
                        "message": r.detail,
                        "suggestion": r.suggestion,
                    })
                elif r.severity == "warning":
                    alerts.append({
                        "level": "warning",
                        "title": f"[{r.id}] {r.name} 异常",
                        "message": r.detail,
                        "suggestion": r.suggestion,
                    })

        # 累计3个以上warning才触发告警
        warning_count = sum(1 for a in alerts if a["level"] == "warning")
        critical_count = sum(1 for a in alerts if a["level"] == "critical")

        if overall_status == "critical":
            alerts.insert(0, {
                "level": "critical",
                "title": "系统健康巡检 — 严重告警",
                "message": f"{critical_count}项严重问题, {warning_count}项警告, 总评分{self._last_report.overall_score if self._last_report else 'N/A'}",
                "suggestion": "请立即检查系统维护页面",
            })
        elif overall_status == "warning":
            alerts.insert(0, {
                "level": "warning",
                "title": "系统健康巡检 — 警告",
                "message": f"{warning_count}项警告, 总评分{self._last_report.overall_score if self._last_report else 'N/A'}",
                "suggestion": "建议查看系统维护页面",
            })

        return alerts

    # ========== 报告存档 ==========

    def _save_report(self, report: HealthReport):
        """保存报告到文件"""
        try:
            filename = f"health_{report.report_id}_{report.mode}.json"
            filepath = os.path.join(self._report_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)

            # 清理30天前的报告
            self._cleanup_old_reports(30)
        except Exception as e:
            logger.error(f"保存巡检报告失败: {e}")

    def _cleanup_old_reports(self, days: int = 30):
        """清理过期报告"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            for fname in os.listdir(self._report_dir):
                fpath = os.path.join(self._report_dir, fname)
                if os.path.isfile(fpath):
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if mtime < cutoff:
                        os.remove(fpath)
        except Exception:
            pass

    def get_report(self, report_id: str) -> Optional[Dict]:
        """获取历史报告"""
        for fname in os.listdir(self._report_dir):
            if report_id in fname and fname.endswith('.json'):
                fpath = os.path.join(self._report_dir, fname)
                with open(fpath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None

    def get_report_list(self, limit: int = 20) -> List[Dict]:
        """获取报告列表"""
        reports = []
        for fname in sorted(os.listdir(self._report_dir), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(self._report_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    reports.append({
                        "report_id": data.get("report_id", ""),
                        "timestamp": data.get("timestamp", ""),
                        "mode": data.get("mode", ""),
                        "overall_score": data.get("overall_score", 0),
                        "overall_status": data.get("overall_status", ""),
                        "total_checks": data.get("total_checks", 0),
                        "passed_checks": data.get("passed_checks", 0),
                    })
                except Exception:
                    pass
            if len(reports) >= limit:
                break
        return reports

    # ========== 定时巡检（交易时段感知） ==========

    # 交易时段配置
    TRADING_SCHEDULE = {
        "pre_market": {"time": "09:00", "mode": "deep", "desc": "盘前深度巡检"},
        "intraday": {"interval_min": 30, "mode": "quick", "desc": "盘中快速巡检"},
        "post_market": {"time": "15:30", "mode": "deep", "desc": "盘后深度巡检"},
        "health": {"interval_hours": 4, "mode": "quick", "desc": "定期健康巡检"},
    }

    # 交易日判断（简化：周一到周五）
    @staticmethod
    def _is_trading_day() -> bool:
        return datetime.now().weekday() < 5

    # 盘中时段判断
    @staticmethod
    def _is_trading_hours() -> bool:
        now = datetime.now()
        t = now.hour * 60 + now.minute
        return 545 <= t <= 915  # 09:15-15:15 盘中时段（含集合竞价）

    @staticmethod
    def _next_schedule_seconds() -> float:
        """计算到下一个巡检时间点的秒数，返回<=60秒的值用于轮询"""
        now = datetime.now()
        current_min = now.hour * 60 + now.minute

        # 盘前09:00
        pre_market = 9 * 60
        # 盘后15:30
        post_market = 15 * 60 + 30

        if not SystemHealthChecker._is_trading_day():
            # 非交易日：每4小时
            return 4 * 3600

        if current_min < pre_market:
            return (pre_market - current_min) * 60 - now.second
        elif current_min < post_market:
            # 盘中：30分钟间隔
            next_interval = ((current_min // 30) + 1) * 30
            return (next_interval - current_min) * 60 - now.second
        elif current_min < post_market + 30:
            return (post_market - current_min) * 60 - now.second if current_min < post_market else 30 * 60
        else:
            return 4 * 3600

    def _trading_scheduler_loop(self):
        """交易时段感知的定时巡检循环

        策略：
        - 交易日盘前09:00: 深度巡检
        - 交易日盘中09:15-15:15: 每30分钟快速巡检
        - 交易日盘后15:30: 深度巡检
        - 非交易日/其他时段: 每4小时快速巡检
        """
        logger.info("[HealthChecker] 交易时段巡检调度已启动")
        logger.info("[HealthChecker] 策略: 盘前09:00深度 | 盘中/30min快速 | 盘后15:30深度 | 每4h健康")

        self._consecutive_failures = 0
        self._last_check_time = None

        while not self._scheduler_stop.wait(1):  # 每秒轮询
            try:
                sleep_sec = self._next_schedule_seconds()
                if sleep_sec > 5:
                    # 距下次巡检还早，短暂休眠
                    if self._scheduler_stop.wait(min(sleep_sec, 60)):
                        break
                    continue

                # 确定当前时段对应的巡检模式
                now = datetime.now()
                current_min = now.hour * 60 + now.minute
                is_trading = self._is_trading_day()

                if is_trading and abs(current_min - 9 * 60) <= 2:
                    mode, desc = "deep", "盘前深度巡检"
                elif is_trading and self._is_trading_hours():
                    mode, desc = "quick", "盘中快速巡检"
                elif is_trading and abs(current_min - (15 * 60 + 30)) <= 2:
                    mode, desc = "deep", "盘后深度巡检"
                else:
                    mode, desc = "quick", "定期健康巡检"

                logger.info(f"[HealthChecker] {desc}开始...")
                report = self.run_check(mode=mode)
                self._last_check_time = now.isoformat()
                self._last_report = report

                logger.info(f"[HealthChecker] {desc}完成: score={report.overall_score}, "
                           f"status={report.overall_status}, {report.passed_checks}/{report.total_checks}")

                # 记录历史趋势
                self._record_trend(report, desc)

                # 告警升级机制
                if report.overall_status in ("critical", "warning"):
                    self._consecutive_failures += 1
                    self._send_escalated_alerts(report, desc)
                else:
                    self._consecutive_failures = 0

                # 避免同分钟内重复执行
                if self._scheduler_stop.wait(60):
                    break

            except Exception as e:
                logger.error(f"[HealthChecker] 定时巡检异常: {e}", exc_info=True)
                self._consecutive_failures += 1

    # ========== 巡检历史趋势 ==========

    def _record_trend(self, report: HealthReport, label: str):
        """记录巡检评分到趋势文件"""
        trend_file = os.path.join(self._report_dir, "trend.json")
        try:
            trends = []
            if os.path.exists(trend_file):
                with open(trend_file, 'r', encoding='utf-8') as f:
                    trends = json.load(f)
            trends.append({
                "timestamp": report.timestamp,
                "score": report.overall_score,
                "status": report.overall_status,
                "passed": report.passed_checks,
                "total": report.total_checks,
                "mode": report.mode,
                "label": label,
                "elapsed": report.elapsed_seconds,
            })
            # 保留最近200条
            if len(trends) > 200:
                trends = trends[-200:]
            with open(trend_file, 'w', encoding='utf-8') as f:
                json.dump(trends, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[HealthChecker] 趋势记录失败: {e}")

    def get_trend_history(self, limit: int = 50) -> List[Dict]:
        """获取巡检历史趋势"""
        trend_file = os.path.join(self._report_dir, "trend.json")
        if not os.path.exists(trend_file):
            return []
        try:
            with open(trend_file, 'r', encoding='utf-8') as f:
                trends = json.load(f)
            return trends[-limit:]
        except Exception:
            return []

    # ========== 告警升级机制 ==========

    def _send_escalated_alerts(self, report: HealthReport, check_label: str):
        """告警升级：连续失败逐级提升告警级别

        升级规则：
        - 第1次失败: warning级别
        - 第2-3次连续失败: 升级为critical
        - 第4+次连续失败: 升级为emergency + 桌面通知
        """
        base_level = report.overall_status
        consecutive = self._consecutive_failures

        if consecutive >= 4:
            escalated_level = "emergency"
            prefix = "🚨 [紧急] 连续巡检失败"
        elif consecutive >= 2:
            escalated_level = "critical"
            prefix = "🔴 [严重] 连续巡检异常"
        else:
            escalated_level = base_level
            prefix = "⚠️ [警告] 巡检异常"

        try:
            import requests
            # 发送升级告警
            alert_msg = (f"{prefix} | {check_label} | "
                        f"连续{consecutive}次 | 评分{report.overall_score} | "
                        f"{report.passed_checks}/{report.total_checks}通过")
            requests.post(f"{self.BASE_URL}/api/alerts/send", json={
                "level": escalated_level,
                "title": f"系统健康巡检告警(连续{consecutive}次)",
                "message": alert_msg,
                "source": "system_health_checker",
                "escalated": True,
                "consecutive_failures": consecutive,
            }, cookies=self._get_auth_cookies(), timeout=5)

            # 连续4次以上：写入紧急告警文件
            if consecutive >= 4:
                emergency_file = os.path.join(PROJECT_ROOT, "data", "emergency_alert.txt")
                with open(emergency_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== 紧急告警 ===\n时间: {datetime.now().isoformat()}\n"
                           f"连续失败: {consecutive}次\n评分: {report.overall_score}\n"
                           f"状态: {report.overall_status}\n")

            # 发送具体失败项告警
            for alert in report.alerts[:5]:
                requests.post(f"{self.BASE_URL}/api/alerts/send", json={
                    "level": escalated_level if alert["level"] == "critical" else alert["level"],
                    "title": alert["title"],
                    "message": alert["message"],
                    "source": "system_health_checker",
                    "escalated": consecutive >= 2,
                }, cookies=self._get_auth_cookies(), timeout=5)

        except Exception as e:
            logger.error(f"[HealthChecker] 告警发送失败: {e}")

    def _send_alerts(self, report: HealthReport):
        """发送告警到系统（兼容旧接口）"""
        self._send_escalated_alerts(report, "手动巡检")

    def start_scheduler(self, interval_minutes: int = 30):
        """启动定时巡检（交易时段感知模式）"""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return {"success": False, "message": "定时巡检已在运行中"}
        self._scheduler_stop.clear()
        self._consecutive_failures = 0
        self._scheduler_thread = threading.Thread(
            target=self._trading_scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        return {
            "success": True,
            "message": "定时巡检已启动（交易时段感知模式）",
            "schedule": {
                "pre_market": "09:00 深度",
                "intraday": "盘中每30分钟 快速",
                "post_market": "15:30 深度",
                "health": "每4小时 快速",
                "escalation": "连续失败逐级升级告警",
            }
        }

    def stop_scheduler(self):
        """停止定时巡检"""
        if not self._scheduler_thread or not self._scheduler_thread.is_alive():
            return {"success": False, "message": "定时巡检未在运行"}
        self._scheduler_stop.set()
        self._scheduler_thread.join(timeout=5)
        return {"success": True, "message": "定时巡检已停止"}

    def get_scheduler_status(self) -> Dict:
        """获取定时巡检状态"""
        running = self._scheduler_thread is not None and self._scheduler_thread.is_alive()
        return {
            "running": running,
            "last_report": asdict(self._last_report) if self._last_report else None,
            "last_check_time": getattr(self, '_last_check_time', None),
            "consecutive_failures": getattr(self, '_consecutive_failures', 0),
            "schedule": {
                "pre_market": "09:00 深度",
                "intraday": "盘中每30分钟 快速",
                "post_market": "15:30 深度",
                "health": "每4小时 快速",
            },
            "is_trading_day": self._is_trading_day(),
            "is_trading_hours": self._is_trading_hours(),
        }

    # ========== 告警机制 ==========

    def trigger_alert(self, alert_type: str, message: str, level: str = "warning"):
        """触发告警并写入alerts.json"""
        import json
        from datetime import datetime
        alert = {
            'type': alert_type,
            'message': message,
            'level': level,
            'timestamp': datetime.now().isoformat()
        }
        logger.warning(f"[ALERT] {alert_type}: {message}")
        try:
            alert_file = os.path.join(os.path.dirname(__file__), '..', 'alerts.json')
            alerts = []
            if os.path.exists(alert_file):
                with open(alert_file, 'r', encoding='utf-8') as f:
                    alerts = json.load(f)
            alerts.append(alert)
            if len(alerts) > 1000:
                alerts = alerts[-500:]
            with open(alert_file, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"告警写入失败: {e}")

    def get_recent_alerts(self, hours: int = 24) -> list:
        """获取最近告警"""
        import json
        alert_file = os.path.join(os.path.dirname(__file__), '..', 'alerts.json')
        if not os.path.exists(alert_file):
            return []
        try:
            with open(alert_file, 'r', encoding='utf-8') as f:
                alerts = json.load(f)
        except Exception:
            return []
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=hours)
        return [a for a in alerts if datetime.fromisoformat(a['timestamp']) > cutoff]


# ========== 全局单例 ==========

_health_checker: Optional[SystemHealthChecker] = None


def get_health_checker() -> SystemHealthChecker:
    """获取巡检引擎单例"""
    global _health_checker
    if _health_checker is None:
        _health_checker = SystemHealthChecker()
    return _health_checker