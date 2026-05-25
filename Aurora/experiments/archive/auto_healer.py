#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora 自动修复框架 (Auto Healer)
实现系统健康自我诊断与自动修复能力
支持定时巡检、故障检测、自动修复、告警推送
"""

import json
import os
import sys
import time
import hashlib
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
#  数据模型
# ============================================================================

class Severity(Enum):
    """严重级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealStatus(Enum):
    """修复状态"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    module: str
    check_name: str
    passed: bool
    severity: Severity = Severity.INFO
    message: str = ""
    details: Dict = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RepairAction:
    """修复动作"""
    module: str
    action_name: str
    severity: Severity = Severity.ERROR
    auto_repair_fn: Optional[Callable] = None
    requires_approval: bool = False
    description: str = ""


@dataclass
class RepairResult:
    """修复结果"""
    repair_action: RepairAction
    status: HealStatus = HealStatus.PENDING
    error_message: str = ""
    repaired_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
#  自动修复器核心
# ============================================================================

class AutoHealer:
    """
    Aurora 自动修复器
    职责：定时巡检 → 发现问题 → 自动修复 → 记录日志 → 告警通知
    """

    REPORT_FILE = "auto_healer_report.json"

    def __init__(self, auto_repair: bool = False, silent: bool = False):
        self.auto_repair = auto_repair
        self.silent = silent
        self.health_checks: List[HealthCheckResult] = []
        self.repair_actions: List[RepairAction] = []
        self.repair_history: List[RepairResult] = []
        self._load_history()

    # ----- 日志 -----
    def _log(self, msg: str, level: str = "INFO"):
        if not self.silent:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] [{level}] AutoHealer: {msg}")

    # ----- 历史持久化 -----
    def _load_history(self):
        if os.path.exists(self.REPORT_FILE):
            try:
                with open(self.REPORT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("repair_history", []):
                    self.repair_history.append(RepairResult(
                        repair_action=RepairAction(**item["repair_action"]),
                        status=HealStatus(item.get("status", "pending")),
                        error_message=item.get("error_message", ""),
                        repaired_at=item.get("repaired_at", "")
                    ))
            except Exception as e:
                self._log(f"加载历史记录失败: {e}", "WARNING")

    def _save_history(self):
        report = {
            "generated_at": datetime.now().isoformat(),
            "auto_repair_enabled": self.auto_repair,
            "summary": self.get_summary(),
            "health_checks": [self._serialize_check(c) for c in self.health_checks[-50:]],
            "repair_history": [self._serialize_repair(r) for r in self.repair_history[-50:]],
        }
        try:
            with open(self.REPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            self._log(f"保存报告失败: {e}", "ERROR")

    @staticmethod
    def _serialize_check(c: HealthCheckResult) -> dict:
        return {
            "module": c.module,
            "check_name": c.check_name,
            "passed": c.passed,
            "severity": c.severity.value,
            "message": c.message,
            "details": c.details,
            "checked_at": c.checked_at,
        }

    @staticmethod
    def _serialize_repair(r: RepairResult) -> dict:
        return {
            "repair_action": {
                "module": r.repair_action.module,
                "action_name": r.repair_action.action_name,
                "severity": r.repair_action.severity.value,
                "description": r.repair_action.description,
            },
            "status": r.status.value,
            "error_message": r.error_message,
            "repaired_at": r.repaired_at,
        }

    # =========================================================================
    #  健康检查模块
    # =========================================================================

    def run_health_check(self) -> List[HealthCheckResult]:
        """运行全部健康检查"""
        self._log("开始系统健康检查...")
        self.health_checks = []

        checks = [
            self._check_users_json,
            self._check_trade_security_config,
            self._check_trading_hours_format,
            self._check_backup_freshness,
            self._check_database_integrity,
            self._check_env_config,
            self._check_disk_space,
            self._check_import_errors,
        ]

        for check_fn in checks:
            try:
                results = check_fn()
                if isinstance(results, list):
                    self.health_checks.extend(results)
                else:
                    self.health_checks.append(results)
            except Exception as e:
                self.health_checks.append(HealthCheckResult(
                    module="auto_healer",
                    check_name=check_fn.__name__,
                    passed=False,
                    severity=Severity.ERROR,
                    message=f"检查执行异常: {e}",
                    details={"traceback": traceback.format_exc()}
                ))

        passed = sum(1 for c in self.health_checks if c.passed)
        total = len(self.health_checks)
        self._log(f"健康检查完成: {passed}/{total} 通过")

        # 自动发现并注册修复
        self._discover_repairs()

        # 自动修复（如果启用）
        if self.auto_repair:
            self._execute_auto_repairs()

        self._save_history()
        return self.health_checks

    # ---- 检查1: users.json 弱密码 ----
    def _check_users_json(self) -> HealthCheckResult:
        """检查 users.json 密码强度"""
        result = HealthCheckResult(
            module="users_json",
            check_name="password_strength",
            passed=True,
            severity=Severity.CRITICAL,
        )

        if not os.path.exists("users.json"):
            result.passed = True
            result.message = "users.json 不存在，跳过检查"
            return result

        try:
            with open("users.json", "r", encoding="utf-8") as f:
                users = json.load(f)

            weak_known_hashes = {
                "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9": "admin123",
                "ecd71870d1963316a97e3ac3408c9835ad8cf0f3c1bc703527c30265534f75ae": "test123",
                "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92": "123456",
                "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f": "password123",
            }

            weak_found = []
            for username, info in users.items():
                pwd_hash = info.get("password", "")
                if pwd_hash in weak_known_hashes:
                    known_pw = weak_known_hashes[pwd_hash]
                    weak_found.append(f"{username}:{known_pw}")

            if weak_found:
                result.passed = False
                result.message = f"检测到弱密码用户: {', '.join(weak_found)}"
                result.details = {"weak_users": weak_found}
            else:
                result.message = "所有用户密码强度合格"
        except Exception as e:
            result.passed = False
            result.message = f"检查失败: {e}"

        return result

    # ---- 检查2: 交易安全配置格式 ----
    def _check_trade_security_config(self) -> HealthCheckResult:
        """检查 trade_security_config.json 配置完整性"""
        result = HealthCheckResult(
            module="trade_security_config",
            check_name="config_integrity",
            passed=True,
            severity=Severity.WARNING,
        )

        config_file = "trade_security_config.json"
        if not os.path.exists(config_file):
            result.passed = True
            result.message = "trade_security_config.json 不存在，将使用默认配置"
            return result

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            required_keys = ["trading_hours", "ip_whitelist", "api_keys",
                             "amount_limits", "frequency_limit", "holidays"]
            missing = [k for k in required_keys if k not in config]

            if missing:
                result.passed = False
                result.message = f"缺少配置项: {missing}"
                result.details = {"missing_keys": missing}
            else:
                result.message = "交易安全配置完整"
        except Exception as e:
            result.passed = False
            result.message = f"读取配置失败: {e}"

        return result

    # ---- 检查3: 交易时段格式 ----
    def _check_trading_hours_format(self) -> List[HealthCheckResult]:
        """检查交易时段是否使用分段格式（A股标准）"""
        results = []

        # 检查默认配置
        try:
            import trade_security
            validator = trade_security.TradeSecurityValidator()
            config = validator.config.get("trading_hours", {})

            has_morning_start = "morning_start" in config
            has_morning_end = "morning_end" in config
            has_afternoon_start = "afternoon_start" in config
            has_afternoon_end = "afternoon_end" in config
            has_old_format = "start" in config or "end" in config

            if has_old_format:
                results.append(HealthCheckResult(
                    module="trading_hours",
                    check_name="format_upgrade_needed",
                    passed=False,
                    severity=Severity.CRITICAL,
                    message="交易时段使用旧格式 (start/end)，需升级为分段格式 (morning_start/morning_end/afternoon_start/afternoon_end)",
                    details={"current_config": config}
                ))
            elif has_morning_start and has_afternoon_end:
                results.append(HealthCheckResult(
                    module="trading_hours",
                    check_name="format_ok",
                    passed=True,
                    message="交易时段使用标准分段格式",
                    details={"current_config": config}
                ))
            else:
                results.append(HealthCheckResult(
                    module="trading_hours",
                    check_name="format_incomplete",
                    passed=False,
                    severity=Severity.CRITICAL,
                    message="交易时段配置不完整",
                    details={"current_config": config}
                ))
        except Exception as e:
            results.append(HealthCheckResult(
                module="trading_hours",
                check_name="check_error",
                passed=False,
                severity=Severity.ERROR,
                message=f"检查交易时段失败: {e}"
            ))

        # 检查 trade_security_config.json 文件
        if os.path.exists("trade_security_config.json"):
            try:
                with open("trade_security_config.json", "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                file_hours = file_config.get("trading_hours", {})

                if "start" in file_hours and "morning_start" not in file_hours:
                    results.append(HealthCheckResult(
                        module="trading_hours_file",
                        check_name="file_format_old",
                        passed=False,
                        severity=Severity.WARNING,
                        message="trade_security_config.json 交易时段使用旧格式，建议更新",
                        details={"file_config": file_hours}
                    ))
            except:
                pass

        return results

    # ---- 检查4: 备份新鲜度 ----
    def _check_backup_freshness(self) -> HealthCheckResult:
        """检查关键文件备份是否在24小时内"""
        result = HealthCheckResult(
            module="backup_freshness",
            check_name="recent_backup",
            passed=True,
            severity=Severity.WARNING,
        )

        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            result.passed = False
            result.message = "备份目录不存在"
            return result

        try:
            cutoff = datetime.now() - timedelta(hours=24)
            files = os.listdir(backup_dir)
            recent_files = []

            for f in files:
                fpath = os.path.join(backup_dir, f)
                if os.path.isfile(fpath):
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if mtime > cutoff:
                        recent_files.append(f)

            if not recent_files:
                result.passed = False
                result.message = "超过24小时无新备份"
                result.details = {"backup_dir": backup_dir, "total_files": len(files)}
            else:
                result.message = f"备份正常，最近24小时内有 {len(recent_files)} 个备份文件"
                result.details = {"recent_backups": recent_files[:5]}
        except Exception as e:
            result.passed = False
            result.message = f"检查备份失败: {e}"

        return result

    # ---- 检查5: 数据库完整性 ----
    def _check_database_integrity(self) -> HealthCheckResult:
        """检查 SQLite 数据库完整性"""
        result = HealthCheckResult(
            module="database",
            check_name="sqlite_integrity",
            passed=True,
            severity=Severity.ERROR,
        )

        db_files = ["aurora_backtest.db", "shepherd_optimizer.db"]
        checked = []
        for db_file in db_files:
            if os.path.exists(db_file):
                try:
                    import sqlite3
                    conn = sqlite3.connect(db_file)
                    cursor = conn.execute("PRAGMA integrity_check")
                    status = cursor.fetchone()[0]
                    conn.close()
                    checked.append(f"{db_file}: {status}")
                    if status != "ok":
                        result.passed = False
                except Exception as e:
                    checked.append(f"{db_file}: 检查失败 - {e}")
                    result.passed = False
            else:
                checked.append(f"{db_file}: 文件不存在")

        if result.passed:
            result.message = "数据库完整性正常"
        else:
            result.message = "数据库整性问题"
        result.details = {"databases": checked}

        return result

    # ---- 检查6: .env 配置 ----
    def _check_env_config(self) -> HealthCheckResult:
        """检查 .env 文件是否存在关键配置"""
        result = HealthCheckResult(
            module="env_config",
            check_name="env_completeness",
            passed=True,
            severity=Severity.ERROR,
        )

        env_file = ".env"
        env_example = ".env.example"

        if not os.path.exists(env_file):
            if os.path.exists(env_example):
                result.passed = False
                result.message = ".env 文件缺失，请从 .env.example 复制并配置"
                result.details = {"action": f"cp {env_example} {env_file}"}
            else:
                result.passed = False
                result.message = ".env 和 .env.example 均缺失"
            return result

        try:
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()

            critical_keys = ["SECRET_KEY", "DEEPSEEK_API_KEY"]
            missing = []
            for key in critical_keys:
                if f"{key}=" not in content:
                    missing.append(key)

            # 检查是否使用默认不安全值
            unsafe_patterns = ["your_secret_key_here", "changeme", "default", "admin123"]
            unsafe_found = []
            for pattern in unsafe_patterns:
                if pattern in content.lower():
                    unsafe_found.append(pattern)

            if missing:
                result.passed = False
                result.message = f"缺少关键环境变量: {missing}"
                result.details["missing_keys"] = missing

            if unsafe_found:
                result.passed = False
                result.message = f"检测到不安全默认值: {unsafe_found}"

            if result.passed:
                result.message = ".env 配置完整"
        except Exception as e:
            result.passed = False
            result.message = f"读取 .env 失败: {e}"

        return result

    # ---- 检查7: 磁盘空间 ----
    @staticmethod
    def _check_disk_space() -> HealthCheckResult:
        """检查磁盘空间"""
        result = HealthCheckResult(
            module="disk_space",
            check_name="free_disk_space",
            passed=True,
            severity=Severity.WARNING,
        )

        try:
            import shutil
            usage = shutil.disk_usage(".")
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            pct_used = (usage.used / usage.total) * 100

            result.details = {
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_pct": round(pct_used, 1),
            }

            if free_gb < 1:
                result.passed = False
                result.severity = Severity.CRITICAL
                result.message = f"磁盘空间严重不足: {free_gb:.1f}GB 可用"
            elif free_gb < 5:
                result.passed = False
                result.message = f"磁盘空间偏低: {free_gb:.1f}GB 可用"
            else:
                result.message = f"磁盘空间正常: {free_gb:.1f}GB 可用"
        except Exception as e:
            result.passed = False
            result.message = f"磁盘检查失败: {e}"

        return result

    # ---- 检查8: 核心模块导入 ----
    @staticmethod
    def _check_import_errors() -> HealthCheckResult:
        """检查核心模块能否正确导入"""
        result = HealthCheckResult(
            module="import_check",
            check_name="core_modules_import",
            passed=True,
            severity=Severity.ERROR,
        )

        core_modules = [
            "trade_security",
            "user_manager",
            "strategy_api",
            "deepseek_client",
            "enhanced_evaluator",
        ]

        failed = []
        for mod_name in core_modules:
            try:
                __import__(mod_name)
            except Exception as e:
                failed.append(f"{mod_name}: {e}")

        if failed:
            result.passed = False
            result.message = f"核心模块导入失败: {failed}"
            result.details = {"failed_imports": failed}
        else:
            result.message = "所有核心模块导入正常"

        return result

    # =========================================================================
    #  修复动作发现
    # =========================================================================

    def _discover_repairs(self):
        """根据健康检查结果自动发现可修复项"""
        self.repair_actions = []

        for check in self.health_checks:
            if check.passed:
                continue

            if check.module == "users_json" and check.check_name == "password_strength":
                self.repair_actions.append(RepairAction(
                    module="users_json",
                    action_name="regenerate_weak_passwords",
                    severity=Severity.CRITICAL,
                    auto_repair_fn=self._repair_weak_passwords,
                    requires_approval=False,
                    description=f"重新生成弱密码: {check.message}"
                ))

            elif check.module == "trade_security_config" and check.check_name == "config_integrity":
                self.repair_actions.append(RepairAction(
                    module="trade_security_config",
                    action_name="repair_config_missing_keys",
                    severity=Severity.WARNING,
                    auto_repair_fn=self._repair_trade_config,
                    requires_approval=False,
                    description="修复交易安全配置缺失项"
                ))

            elif check.module == "trading_hours" and check.check_name in ("format_upgrade_needed", "format_incomplete"):
                self.repair_actions.append(RepairAction(
                    module="trading_hours",
                    action_name="upgrade_trading_hours_format",
                    severity=Severity.CRITICAL,
                    auto_repair_fn=self._repair_trading_hours_format,
                    requires_approval=False,
                    description="升级交易时段为A股标准分段格式"
                ))

            elif check.module == "backup_freshness":
                self.repair_actions.append(RepairAction(
                    module="backup_freshness",
                    action_name="create_fresh_backup",
                    severity=Severity.WARNING,
                    auto_repair_fn=self._repair_create_backup,
                    requires_approval=False,
                    description="创建关键文件新备份"
                ))

    # =========================================================================
    #  自动修复方法
    # =========================================================================

    def _execute_auto_repairs(self):
        """执行所有自动修复"""
        for action in self.repair_actions:
            if action.auto_repair_fn and not action.requires_approval:
                self._log(f"自动修复: {action.description}")
                try:
                    success, msg = action.auto_repair_fn()
                    status = HealStatus.SUCCESS if success else HealStatus.FAILED
                    self.repair_history.append(RepairResult(
                        repair_action=action,
                        status=status,
                        error_message=msg if not success else "",
                    ))
                    self._log(f"  结果: {'✅ 成功' if success else '❌ 失败'} - {msg}")
                except Exception as e:
                    self.repair_history.append(RepairResult(
                        repair_action=action,
                        status=HealStatus.FAILED,
                        error_message=str(e),
                    ))
                    self._log(f"  结果: ❌ 异常 - {e}", "ERROR")

    def _repair_weak_passwords(self) -> tuple:
        """修复弱密码"""
        try:
            import secrets
            import string
            import hashlib

            chars = string.ascii_letters + string.digits + "!@#$%^&*"

            if not os.path.exists("users.json"):
                return False, "users.json 不存在"

            with open("users.json", "r", encoding="utf-8") as f:
                users = json.load(f)

            weak_hashes = {
                "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
                "ecd71870d1963316a97e3ac3408c9835ad8cf0f3c1bc703527c30265534f75ae",
                "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",
                "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
            }

            repaired = 0
            for username, info in users.items():
                if info.get("password", "") in weak_hashes:
                    new_pw = ''.join(secrets.choice(chars) for _ in range(20))
                    info["password"] = hashlib.sha256(new_pw.encode()).hexdigest()
                    repaired += 1

            if repaired == 0:
                return True, "无需修复"

            with open("users.json", "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2, ensure_ascii=False)

            return True, f"已修复 {repaired} 个弱密码"
        except Exception as e:
            return False, f"修复密码失败: {e}"

    def _repair_trade_config(self) -> tuple:
        """修复交易安全配置"""
        try:
            config_file = "trade_security_config.json"
            default_config = {
                "trading_hours": {
                    "morning_start": "09:30",
                    "morning_end": "11:30",
                    "afternoon_start": "13:00",
                    "afternoon_end": "15:00"
                },
                "ip_whitelist": [],
                "api_keys": [],
                "amount_limits": {
                    "single_trade_max": 100000,
                    "daily_max": 500000,
                    "per_stock_max": 200000
                },
                "frequency_limit": {
                    "max_per_minute": 10,
                    "max_per_hour": 60
                },
                "holidays": [],
                "circuit_breaker": {
                    "enabled": True,
                    "max_loss_pct": 5.0
                }
            }

            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                for key, value in default_config.items():
                    if key not in existing:
                        existing[key] = value
                final_config = existing
            else:
                final_config = default_config

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(final_config, f, indent=2, ensure_ascii=False)

            return True, "交易安全配置已修复"
        except Exception as e:
            return False, f"修复配置失败: {e}"

    def _repair_trading_hours_format(self) -> tuple:
        """修复交易时段格式为A股标准分段格式"""
        try:
            config_file = "trade_security_config.json"
            target_config = {
                "morning_start": "09:30",
                "morning_end": "11:30",
                "afternoon_start": "13:00",
                "afternoon_end": "15:00"
            }

            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                config["trading_hours"] = target_config
            else:
                config = {"trading_hours": target_config}

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            return True, "交易时段已升级为标准A股分段格式"
        except Exception as e:
            return False, f"修复时段格式失败: {e}"

    def _repair_create_backup(self) -> tuple:
        """创建关键文件备份"""
        try:
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)

            key_files = ["users.json", "trade_security_config.json", ".env"]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backed_up = 0

            for fname in key_files:
                if os.path.exists(fname):
                    import shutil
                    backup_name = f"{os.path.splitext(fname)[0]}.bak.{timestamp}{os.path.splitext(fname)[1]}"
                    shutil.copy2(fname, os.path.join(backup_dir, backup_name))
                    backed_up += 1

            return True, f"已备份 {backed_up} 个关键文件到 backups/"
        except Exception as e:
            return False, f"创建备份失败: {e}"

    # =========================================================================
    #  报告与摘要
    # =========================================================================

    def get_summary(self) -> dict:
        """生成健康摘要"""
        total = len(self.health_checks)
        passed = sum(1 for c in self.health_checks if c.passed)
        failed = total - passed

        critical_failures = [
            c.message for c in self.health_checks
            if not c.passed and c.severity == Severity.CRITICAL
        ]

        recent_repairs = [
            r for r in self.repair_history
            if r.status == HealStatus.SUCCESS
        ][-5:]

        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "health_pct": round(passed / total * 100, 1) if total > 0 else 100,
            "critical_failures": critical_failures,
            "pending_repairs": len(self.repair_actions),
            "recent_repairs": len(recent_repairs),
            "auto_repair_enabled": self.auto_repair,
        }

    def print_report(self):
        """打印健康报告"""
        summary = self.get_summary()
        print("\n" + "=" * 60)
        print("  Aurora 系统健康检查报告")
        print("=" * 60)
        print(f"  检查项: {summary['total_checks']}  通过: {summary['passed']}  失败: {summary['failed']}")
        print(f"  健康度: {summary['health_pct']}%")
        print()

        if summary['critical_failures']:
            print("  ⚠️  严重问题:")
            for msg in summary['critical_failures']:
                print(f"    - {msg}")
            print()

        # 分类打印
        modules_shown = set()
        for check in self.health_checks:
            if not check.passed:
                icon = "🔴" if check.severity == Severity.CRITICAL else "🟡" if check.severity == Severity.WARNING else "🔵"
                prefix = f"  {icon} [{check.module}]"
                if check.module not in modules_shown:
                    modules_shown.add(check.module)
                print(f"{prefix} {check.message}")

        if not any(not c.passed for c in self.health_checks):
            print("  ✅ 所有检查通过！系统状态良好。")

        print(f"\n  自动修复: {'已启用' if self.auto_repair else '已禁用'}")
        if self.repair_actions:
            print(f"  待修复项: {len(self.repair_actions)}")
        print("=" * 60 + "\n")


# ============================================================================
#  定时巡检守护进程
# ============================================================================

class HealerDaemon:
    """自动修复守护进程 - 定时巡检"""

    def __init__(self, interval_minutes: int = 30, auto_repair: bool = False):
        self.interval = interval_minutes
        self.healer = AutoHealer(auto_repair=auto_repair)
        self.running = False

    def start(self):
        """启动守护进程"""
        self.running = True
        print(f"AutoHealer 守护进程已启动，巡检间隔: {self.interval} 分钟")
        print(f"自动修复: {'已启用' if self.healer.auto_repair else '已禁用'}")

        try:
            while self.running:
                # 执行健康检查
                self.healer.run_health_check()
                self.healer.print_report()

                # 等待下一次巡检
                print(f"下次巡检: {datetime.now() + timedelta(minutes=self.interval)}")
                for _ in range(self.interval * 60):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            print("\nAutoHealer 守护进程已停止")
            self.running = False

    def stop(self):
        """停止守护进程"""
        self.running = False


# ============================================================================
#  命令行入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aurora 自动修复框架")
    parser.add_argument("--check", action="store_true", help="执行一次健康检查")
    parser.add_argument("--repair", action="store_true", help="执行自动修复")
    parser.add_argument("--daemon", action="store_true", help="启动守护进程")
    parser.add_argument("--interval", type=int, default=30, help="巡检间隔（分钟）")
    parser.add_argument("--silent", action="store_true", help="静默模式")

    args = parser.parse_args()

    if args.daemon:
        daemon = HealerDaemon(
            interval_minutes=args.interval,
            auto_repair=args.repair or True
        )
        daemon.start()

    elif args.check or args.repair:
        healer = AutoHealer(auto_repair=args.repair, silent=args.silent)
        healer.run_health_check()
        healer.print_report()

        if args.repair and not healer.auto_repair:
            healer._execute_auto_repairs()

    else:
        parser.print_help()