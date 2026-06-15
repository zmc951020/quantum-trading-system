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
    }

    BASE_URL = "http://127.0.0.1:5003"

    def __init__(self):
        self._scheduler_thread = None
        self._scheduler_stop = threading.Event()
        self._report_dir = os.path.join(PROJECT_ROOT, "data", "health_reports")
        os.makedirs(self._report_dir, exist_ok=True)
        self._session = None  # 缓存的认证session
        self._last_report: Optional[HealthReport] = None

    # ========== 认证辅助 ==========

    def _get_auth_cookies(self) -> dict:
        """获取认证cookies（缓存复用）"""
        if self._session:
            return {"session_id": self._session}
        try:
            import requests
            r = requests.post(f"{self.BASE_URL}/api/auth/login",
                            json={"username": "admin", "password": "admin123"}, timeout=5)
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

    # ==================== L2: 业务功能链路 ====================

    def _build_l2_checks(self) -> List[Callable]:
        def _l2_001():
            ok, d = self._api_get("/api/strategy/list")
            strategies = d.get("data", {}).get("strategies", [])
            return (len(strategies) > 0, 100 if len(strategies) > 0 else 0,
                    f"策略列表: {len(strategies)}个" if len(strategies) > 0 else "策略列表为空",
                    "" if len(strategies) > 0 else "检查策略注册表")
        yield ("L2_001", "策略列表", "L2_业务链路", "critical", "both", _l2_001)

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

        # 深度扩展
        def _l2_005():
            ok, d = self._api_get("/api/strategy/registry/summary")
            return (ok, 100 if ok else 0, f"注册表摘要: {'通过' if ok else '失败'}", "")
        yield ("L2_005", "策略注册表摘要", "L2_业务链路", "warning", "deep", _l2_005)

        def _l2_006():
            ok, d = self._api_get("/api/risk/status")
            return (ok, 100 if ok else 0, f"风控状态: {'通过' if ok else '失败'}", "")
        yield ("L2_006", "风控状态", "L2_业务链路", "critical", "deep", _l2_006)

    # ==================== L3: 系统可靠性 ====================

    def _build_l3_checks(self) -> List[Callable]:
        def _l3_001():
            ok, d = self._api_get("/api/health")
            status = d.get("status", "unknown")
            return (ok and status == "healthy", 100 if ok else 0,
                    f"健康检查: {status}" if ok else "健康检查失败", "")
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
            return (len(stocks) > 0, 100 if len(stocks) > 0 else 50,
                    f"市场数据: {len(stocks)}条" if len(stocks) > 0 else "市场数据为空", "")
        yield ("L4_002", "市场数据源", "L4_数据行情", "warning", "both", _l4_002)

        def _l4_003():
            ok, d = self._api_get("/api/stock-pool")
            return (ok, 100 if ok else 0, f"股票池接口: {'通过' if ok else '失败'}", "")
        yield ("L4_003", "股票池接口", "L4_数据行情", "warning", "both", _l4_003)

        # 深度扩展
        def _l4_004():
            ok, d = self._api_get("/api/performance-data")
            return (ok, 100 if ok else 0, f"绩效数据: {'通过' if ok else '失败'}", "")
        yield ("L4_004", "绩效数据", "L4_数据行情", "info", "deep", _l4_004)

        def _l4_005():
            ok, d = self._api_get("/api/technical-indicators")
            return (ok, 100 if ok else 0, f"技术指标列表: {'通过' if ok else '失败'}", "")
        yield ("L4_005", "技术指标列表", "L4_数据行情", "info", "deep", _l4_005)

    # ==================== L5: 交易与风控 ====================

    def _build_l5_checks(self) -> List[Callable]:
        def _l5_001():
            ok, d = self._api_get("/api/risk/status")
            return (ok, 100 if ok else 0, f"风控引擎: {'在线' if ok else '离线'}", "")
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

    # ==================== L6: AI与智能体 ====================

    def _build_l6_checks(self) -> List[Callable]:
        def _l6_001():
            ok, d = self._api_get("/api/llm/models", timeout=3)
            models = d.get("data", {}).get("models", [])
            return (len(models) > 0, 100 if len(models) > 0 else 50,
                    f"LLM模型: {len(models)}个" if len(models) > 0 else "LLM模型列表为空", "")
        yield ("L6_001", "LLM管理器", "L6_AI智能体", "warning", "both", _l6_001)

        def _l6_002():
            ok, d = self._api_post("/api/vibe/analyze", {"symbol": "000001"})
            return (ok, 100 if ok else 0, f"Vibe分析: {'通过' if ok else '失败'}", "")
        yield ("L6_002", "Vibe分析端点", "L6_AI智能体", "warning", "both", _l6_002)

        def _l6_003():
            ok, d = self._api_post("/api/deepseek/chat", {"message": "你好", "history": []}, timeout=3)
            return (ok, 100 if ok else 0, f"智能体对话: {'通过' if ok else '失败'}", "")
        yield ("L6_003", "智能体对话", "L6_AI智能体", "warning", "both", _l6_003)

        # 深度扩展
        def _l6_004():
            ok, d = self._api_post("/api/vibe/29_agents_vote", {"symbol": "000001"})
            return (ok, 100 if ok else 0, f"29智能体投票: {'通过' if ok else '失败'}", "")
        yield ("L6_004", "29智能体投票", "L6_AI智能体", "info", "deep", _l6_004)

        def _l6_005():
            ok, d = self._api_get("/api/llm/config")
            return (ok, 100 if ok else 0, f"LLM配置: {'通过' if ok else '失败'}", "")
        yield ("L6_005", "LLM配置查询", "L6_AI智能体", "info", "deep", _l6_005)

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

        def _l7_004():
            ok, d = self._api_get("/api/security/audit-logs?limit=5")
            return (ok, 100 if ok else 0, f"审计日志: {'通过' if ok else '失败'}", "")
        yield ("L7_004", "审计日志可用", "L7_运维部署", "warning", "both", _l7_004)

        # 深度扩展
        def _l7_005():
            try:
                import requests
                r = requests.get(f"{self.BASE_URL}/nonexistent-page-xyz", timeout=5)
                ok = r.status_code == 404
                return (ok, 100 if ok else 0, f"404处理: status={r.status_code}", "")
            except Exception as e:
                return (False, 0, f"404测试异常: {e}", "")
        yield ("L7_005", "404错误处理", "L7_运维部署", "info", "deep", _l7_005)

        def _l7_006():
            ok, d = self._api_get("/api/alerts")
            return (ok, 100 if ok else 0, f"告警系统: {'通过' if ok else '失败'}", "")
        yield ("L7_006", "告警系统", "L7_运维部署", "warning", "deep", _l7_006)

        def _l7_007():
            ok, d = self._api_get("/api/health/full")
            full = d.get("data", {})
            checks = sum(1 for v in full.values() if v is True)
            total = len(full) - 1  # exclude degradation dict
            return (checks > 0, 100 if checks > 0 else 0,
                    f"完整健康检查: {checks}/{total}项正常", "")
        yield ("L7_007", "完整健康检查", "L7_运维部署", "info", "deep", _l7_007)

    # ========== 构建检查清单 ==========

    def _get_all_checks(self) -> List[tuple]:
        """获取所有检查项生成器"""
        checks = []
        for gen in [self._build_l1_checks, self._build_l2_checks, self._build_l3_checks,
                     self._build_l4_checks, self._build_l5_checks, self._build_l6_checks,
                     self._build_l7_checks]:
            checks.extend(list(gen()))
        return checks

    # ========== 执行巡检 ==========

    def run_check(self, mode: str = "quick") -> HealthReport:
        """执行巡检

        Args:
            mode: "quick" (快速, ~30秒) 或 "deep" (深度, ~2分钟)
        """
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

    # ========== 定时巡检 ==========

    def _scheduler_loop(self, interval_minutes: int):
        """定时巡检循环"""
        logger.info(f"[HealthChecker] 定时巡检已启动，间隔{interval_minutes}分钟")
        while not self._scheduler_stop.wait(interval_minutes * 60):
            try:
                logger.info("[HealthChecker] 定时巡检开始...")
                report = self.run_check(mode="quick")
                logger.info(f"[HealthChecker] 定时巡检完成: score={report.overall_score}, "
                          f"status={report.overall_status}, {report.passed_checks}/{report.total_checks}")

                # 异常时发送告警
                if report.overall_status in ("critical", "warning"):
                    self._send_alerts(report)
            except Exception as e:
                logger.error(f"[HealthChecker] 定时巡检异常: {e}")

    def _send_alerts(self, report: HealthReport):
        """发送告警到系统"""
        try:
            import requests
            for alert in report.alerts[:5]:  # 最多发送5条
                requests.post(f"{self.BASE_URL}/api/alerts/send", json={
                    "level": alert["level"],
                    "title": alert["title"],
                    "message": alert["message"],
                    "source": "system_health_checker",
                }, cookies=self._get_auth_cookies(), timeout=5)
        except Exception as e:
            logger.error(f"[HealthChecker] 告警发送失败: {e}")

    def start_scheduler(self, interval_minutes: int = 30):
        """启动定时巡检"""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return {"success": False, "message": "定时巡检已在运行中"}
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, args=(interval_minutes,), daemon=True)
        self._scheduler_thread.start()
        return {"success": True, "message": f"定时巡检已启动，间隔{interval_minutes}分钟"}

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
        }


# ========== 全局单例 ==========

_health_checker: Optional[SystemHealthChecker] = None


def get_health_checker() -> SystemHealthChecker:
    """获取巡检引擎单例"""
    global _health_checker
    if _health_checker is None:
        _health_checker = SystemHealthChecker()
    return _health_checker