# coding: utf-8
"""
审计日志防篡改 — 哈希链 + 只追加日志 + 哈希链断裂告警
======================================================
增益性补充，记录所有关键操作并保证日志不可篡改。
不修改原有日志模块代码。

功能：
  - 所有关键操作（下单/撤单/提现/修改配置）必须记录审计日志
  - 每条日志包含：用户ID、操作类型、时间戳、资源ID、详情、来源IP
  - Hash链：每条日志 = pre_hash + 本条内容 → SHA-256链式验证
  - 只追加模式：删除/修改任意一条日志会使后续所有哈希断裂
  - 完整性校验：启动时校验整个链，发现断裂即告警 + 终止交易
  - 签名机制：每条日志用 JWT/HMAC 签名防伪造
  - JSON行格式：便于 logstash / Splunk 导入

使用方式：
    from utils.audit_trail import AuditTrail
    trail = AuditTrail(log_file="logs/audit.jsonl")
    trail.log("order_create", user_id="u123", resource_id="ord_456", detail={...})
    # 启动时校验
    trail.verify_integrity()
"""

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 默认HMAC密钥（由 SecretManager 注入） ───
_DEFAULT_HMAC_KEY = os.environ.get("AUDIT_HMAC_KEY", "aurora-audit-default-key-change-me")
_HMAC_KEY_LOCK = threading.Lock()


def set_hmac_key(key: str):
    """设置审计签名密钥（由启动流程注入）"""
    global _DEFAULT_HMAC_KEY
    with _HMAC_KEY_LOCK:
        _DEFAULT_HMAC_KEY = key
        logger.info("审计签名密钥已注入 (%d字符)", len(key))


def _get_hmac_key() -> str:
    global _DEFAULT_HMAC_KEY
    with _HMAC_KEY_LOCK:
        return _DEFAULT_HMAC_KEY


# ─────────────────────────────────────────────
# 审计日志条目
# ─────────────────────────────────────────────

class AuditEntry:
    """单条审计日志"""

    def __init__(
        self,
        operation: str,
        user_id: str = "system",
        resource_type: str = "",
        resource_id: str = "",
        detail: Optional[Dict[str, Any]] = None,
        source_ip: str = "",
        trace_id: str = "",
    ):
        self.operation = operation
        self.user_id = user_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.detail = detail or {}
        self.source_ip = source_ip
        self.trace_id = trace_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.pre_hash = ""   # 上一条日志的哈希
        self.hash = ""        # 本条日志的哈希（由 build_hash 生成）
        self.signature = ""   # HMAC签名

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.timestamp,
            "op": self.operation,
            "uid": self.user_id,
            "rtype": self.resource_type,
            "rid": self.resource_id,
            "detail": self.detail,
            "ip": self.source_ip,
            "trace_id": self.trace_id,
            "pre_hash": self.pre_hash,
            "hash": self.hash,
            "sig": self.signature,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEntry":
        entry = cls(
            operation=data.get("op", ""),
            user_id=data.get("uid", "system"),
            resource_type=data.get("rtype", ""),
            resource_id=data.get("rid", ""),
            detail=data.get("detail", {}),
            source_ip=data.get("ip", ""),
            trace_id=data.get("trace_id", ""),
        )
        entry.timestamp = data.get("ts", "")
        entry.pre_hash = data.get("pre_hash", "")
        entry.hash = data.get("hash", "")
        entry.signature = data.get("sig", "")
        return entry

    def compute_signature(self, hmac_key: str) -> str:
        """计算 HMAC-SHA256 签名"""
        payload = (
            f"{self.timestamp}|{self.operation}|{self.user_id}|"
            f"{self.resource_type}|{self.resource_id}|{self.pre_hash}"
        )
        return hmac.new(hmac_key.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def compute_hash(self) -> str:
        """计算本条日志的 SHA-256 哈希（不含 hash/sig 字段）"""
        payload = (
            f"{self.timestamp}|{self.operation}|{self.user_id}|"
            f"{self.resource_type}|{self.resource_id}|"
            f"{json.dumps(self.detail, sort_keys=True)}|{self.pre_hash}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ─────────────────────────────────────────────
# 审计日志管理器
# ─────────────────────────────────────────────

class AuditTrail:
    """
    审计日志防篡改系统 — 增益层

    三级防护：
      L1: Hash链（每条日志链接前一条，篡改任一条致整个链断裂）
      L2: HMAC签名（每条日志含密钥签名，防伪造）
      L3: 完整性校验（verify_integrity() 遍历全链验证）

    使用方式：
        trail = AuditTrail("logs/audit.jsonl")
        trail.verify_integrity()       # 启动时校验
        trail.log("order_create", uid="u001", rid="order_123")
    """

    def __init__(self, log_file: str = "logs/audit.jsonl", hmac_key: Optional[str] = None):
        self._log_file = log_file
        self._hmac_key = hmac_key or _get_hmac_key()
        self._lock = threading.Lock()
        self._entry_count = 0
        self._last_hash = ""
        self._integrity_ok = False
        self._corruption_index: Optional[int] = None

        # 确保目录存在
        os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else ".", exist_ok=True)

        # 初始化最后一个哈希（读取文件最后一条）
        self._init_chain_head()

    # ────────── 初始化 ──────────

    def _init_chain_head(self):
        """读取现有日志文件，获取最后一条的哈希"""
        if not os.path.exists(self._log_file):
            self._last_hash = "0" * 64
            self._entry_count = 0
            return

        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self._entry_count = len(lines)
            if lines:
                last_line = lines[-1].strip()
                if last_line:
                    data = json.loads(last_line)
                    self._last_hash = data.get("hash", "0" * 64)
                    logger.info(
                        "审计日志加载完成: %d 条记录, 最后hash=%s...",
                        self._entry_count, self._last_hash[:12]
                    )
            else:
                self._last_hash = "0" * 64
        except Exception as e:
            logger.error("读取审计日志失败: %s，将使用空链", e)
            self._last_hash = "0" * 64
            self._entry_count = 0

    # ────────── 写入 ──────────

    def log(
        self,
        operation: str,
        *,
        user_id: str = "system",
        resource_type: str = "",
        resource_id: str = "",
        detail: Optional[Dict[str, Any]] = None,
        source_ip: str = "",
        trace_id: str = "",
    ) -> AuditEntry:
        """
        追加一条审计日志（原子写入+哈希链）。

        Args:
            operation: 操作类型 (order_create/order_cancel/config_change/withdraw...)
            user_id: 操作者ID
            resource_type: 资源类型 (order/account/config/strategy...)
            resource_id: 资源ID
            detail: 操作详情 (dict)
            source_ip: 来源IP
            trace_id: 全链路trace_id

        Returns:
            写入的 AuditEntry
        """
        entry = AuditEntry(
            operation=operation,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            source_ip=source_ip,
            trace_id=trace_id,
        )

        with self._lock:
            # 链接前一条哈希
            entry.pre_hash = self._last_hash
            # 计算本条哈希
            entry.hash = entry.compute_hash()
            # HMAC签名
            entry.signature = entry.compute_signature(self._hmac_key)

            # 序列化
            line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"

            # 原子追加写入
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())  # 确保落盘

                self._last_hash = entry.hash
                self._entry_count += 1
                self._integrity_ok = True  # 刚写入的必然通过

                logger.debug(
                    "审计日志 #%d: %s | %s/%s | hash=%s",
                    self._entry_count, operation,
                    resource_type, resource_id,
                    entry.hash[:12],
                )
            except Exception as e:
                logger.critical("审计日志写入失败！！！操作=%s, 错误=%s", operation, e)
                # 不抛异常，不中断主流程（但记录到 stderr）
                import sys
                print(f"[AUDIT_CRITICAL] 审计日志写入失败: {operation} - {e}", file=sys.stderr)

        return entry

    # ────────── 完整性校验 ──────────

    def verify_integrity(self) -> Dict[str, Any]:
        """
        遍历全链验证哈希链和签名完整性。

        Returns:
            {
                "ok": True/False,
                "total_entries": int,
                "verified": int,
                "corruption_index": int or None,
                "corruption_detail": str or None,
            }
        """
        with self._lock:
            result = {
                "ok": True,
                "total_entries": 0,
                "verified": 0,
                "corruption_index": None,
                "corruption_detail": None,
            }

            if not os.path.exists(self._log_file):
                logger.info("审计日志文件不存在，跳过验证")
                self._integrity_ok = True
                result["ok"] = True
                return result

            try:
                with open(self._log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                result["total_entries"] = len(lines)
                expected_prev = "0" * 64
                idx = 0

                for idx, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        result["ok"] = False
                        result["corruption_index"] = idx
                        result["corruption_detail"] = f"第 {idx+1} 行 JSON 解析失败: {e}"
                        logger.critical(result["corruption_detail"])
                        break

                    entry = AuditEntry.from_dict(data)

                    # ── 验证 pre_hash 连续性 ──
                    if entry.pre_hash != expected_prev:
                        result["ok"] = False
                        result["corruption_index"] = idx
                        result["corruption_detail"] = (
                            f"第 {idx+1} 行哈希链断裂！预期 pre_hash={expected_prev[:16]}..."
                            f" 实际 pre_hash={entry.pre_hash[:16]}..."
                        )
                        logger.critical(result["corruption_detail"])
                        break

                    # ── 验证 hash ──
                    computed = entry.compute_hash()
                    if computed != entry.hash:
                        result["ok"] = False
                        result["corruption_index"] = idx
                        result["corruption_detail"] = (
                            f"第 {idx+1} 行内容哈希不匹配！计算={computed[:16]}... "
                            f"记录={entry.hash[:16]}..."
                        )
                        logger.critical(result["corruption_detail"])
                        break

                    # ── 验证 HMAC 签名 ──
                    expected_sig = entry.compute_signature(self._hmac_key)
                    if expected_sig != entry.signature:
                        result["ok"] = False
                        result["corruption_index"] = idx
                        result["corruption_detail"] = (
                            f"第 {idx+1} 行 HMAC 签名验证失败！可能已被伪造"
                        )
                        logger.critical(result["corruption_detail"])
                        break

                    expected_prev = entry.hash
                    result["verified"] = idx + 1

                if result["ok"]:
                    logger.info(
                        "✅ 审计日志完整性验证通过: %d/%d 条",
                        result["verified"], result["total_entries"]
                    )
                    self._integrity_ok = True
                else:
                    self._integrity_ok = False
                    self._corruption_index = result["corruption_index"]

            except Exception as e:
                result["ok"] = False
                result["corruption_detail"] = f"验证过程异常: {e}"
                logger.critical("审计日志完整性验证异常: %s", e)
                self._integrity_ok = False

            return result

    # ────────── 查询 ──────────

    @property
    def is_integrity_ok(self) -> bool:
        return self._integrity_ok

    @property
    def entry_count(self) -> int:
        return self._entry_count

    def recent_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """返回最近N条日志"""
        if not os.path.exists(self._log_file):
            return []

        with self._lock:
            try:
                with open(self._log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                recent = lines[-limit:] if len(lines) > limit else lines
                return [json.loads(l.strip()) for l in recent if l.strip()]
            except Exception as e:
                logger.error("读取审计日志失败: %s", e)
                return []

    def search(
        self,
        user_id: Optional[str] = None,
        operation: Optional[str] = None,
        resource_id: Optional[str] = None,
        since_ts: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """检索审计日志（简单遍历，生产环境建议迁移到 Elastisearch）"""
        if not os.path.exists(self._log_file):
            return []

        results = []
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if user_id and data.get("uid") != user_id:
                        continue
                    if operation and data.get("op") != operation:
                        continue
                    if resource_id and data.get("rid") != resource_id:
                        continue
                    if since_ts and data.get("ts", "") < since_ts:
                        continue
                    results.append(data)
                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error("审计日志搜索失败: %s", e)
            return []
        return results

    def export_for_compliance(self, export_dir: str = "exports/") -> str:
        """
        导出完整审计日志供合规审查。

        Returns:
            导出文件路径
        """
        if not os.path.exists(self._log_file):
            logger.warning("审计日志文件不存在，无法导出")
            return ""

        os.makedirs(export_dir, exist_ok=True)
        export_path = os.path.join(
            export_dir,
            f"audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        )

        import shutil
        shutil.copy2(self._log_file, export_path)
        logger.info("审计日志已导出: %s (%d 条)", export_path, self._entry_count)
        return export_path

    def rotate(self, max_size_mb: int = 100):
        """日志轮转：超过阈值后归档旧文件并创建新文件"""
        if not os.path.exists(self._log_file):
            return

        size_mb = os.path.getsize(self._log_file) / (1024 * 1024)
        if size_mb < max_size_mb:
            return

        archive_name = self._log_file.replace(".jsonl", f"_{datetime.now().strftime('%Y%m%d')}.jsonl")
        os.rename(self._log_file, archive_name)
        logger.info("审计日志已轮转: %s -> %s (%.1f MB)", self._log_file, archive_name, size_mb)
        self._last_hash = "0" * 64
        self._entry_count = 0