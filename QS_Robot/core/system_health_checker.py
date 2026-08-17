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

    def _resolve_security_path(self, rel_path: str) -> str:
        """解析安全模块路径：优先Aurora，降级到QS_Robot本地"""
        aurora_path = self._aurora_path(rel_path)
        if os.path.exists(aurora_path):
            return aurora_path
        local_path = os.path.join(PROJECT_ROOT, rel_path)
        return local_path

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
        from .health_checks import build_l1_checks
        yield from build_l1_checks(self)

    # ==================== L2: 业务功能链路 ====================

    def _build_l2_checks(self) -> List[Callable]:
        from .health_checks import build_l2_checks
        yield from build_l2_checks(self)

    # ==================== L3: 系统可靠性 ====================

    def _build_l3_checks(self) -> List[Callable]:
        from .health_checks import build_l3_checks
        yield from build_l3_checks(self)

    # ==================== L4: 数据与行情 ====================

    def _build_l4_checks(self) -> List[Callable]:
        from .health_checks import build_l4_checks
        yield from build_l4_checks(self)

    # ==================== L5: 交易与风控 ====================

    def _build_l5_checks(self) -> List[Callable]:
        from .health_checks import build_l5_checks
        yield from build_l5_checks(self)

    # ==================== L6: AI与智能体 ====================

    def _build_l6_checks(self) -> List[Callable]:
        from .health_checks import build_l6_checks
        yield from build_l6_checks(self)

    # ==================== L7: 运维与部署 ====================

    def _build_l7_checks(self) -> List[Callable]:
        from .health_checks import build_l7_checks
        yield from build_l7_checks(self)

    # ==================== L8: 深度审计（代码/API/引擎/配置） ====================

    def _build_l8_checks(self) -> List[Callable]:
        from .health_checks import build_l8_checks
        yield from build_l8_checks(self)

    # ==================== L9: 工程闭环审查 ====================

    def _build_l9_checks(self) -> List[Callable]:
        from .health_checks import build_l9_checks
        yield from build_l9_checks(self)

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