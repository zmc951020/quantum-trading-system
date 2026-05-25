#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件清单管理器 - Aurora系统文件版本与完整性管理
管理项目文件的清单、版本追踪和完整性校验
"""

import os
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FileInventoryManager:
    """文件清单管理器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.base_dir = self.config.get("base_dir", os.path.dirname(os.path.abspath(__file__)))
        self.inventory_file = self.config.get(
            "inventory_file",
            os.path.join(self.base_dir, "Aurora_file_inventory.json"),
        )
        self.ignore_patterns = self.config.get("ignore_patterns", [
            "__pycache__", ".git", "node_modules", ".venv", "*.pyc",
            "*.db", "*.log", "stash_*", "backups/",
        ])
        self.inventory: Dict[str, Dict[str, Any]] = {}
        self._load_inventory()

    def scan_and_update(self) -> Dict[str, Any]:
        """扫描文件系统并更新清单"""
        new_inventory = {}
        total_files = 0
        total_size = 0
        changed_files = []
        new_files = []
        removed_files = []

        for root, dirs, files in os.walk(self.base_dir):
            # 过滤忽略的目录
            dirs[:] = [d for d in dirs if not self._should_ignore(os.path.relpath(os.path.join(root, d), self.base_dir))]

            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.base_dir)
                if self._should_ignore(rel_path):
                    continue

                try:
                    stat = os.stat(fpath)
                    file_hash = self._compute_hash(fpath)
                    file_info = {
                        "path": rel_path,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "hash": file_hash,
                        "type": os.path.splitext(fname)[1].lstrip(".") or "unknown",
                    }
                    new_inventory[rel_path] = file_info
                    total_files += 1
                    total_size += stat.st_size

                    # 检测变化
                    if rel_path in self.inventory:
                        if self.inventory[rel_path]["hash"] != file_hash:
                            changed_files.append(rel_path)
                    else:
                        new_files.append(rel_path)
                except (OSError, IOError) as e:
                    logger.warning(f"无法访问文件 {rel_path}: {e}")

        # 检测删除的文件
        for rel_path in self.inventory:
            if rel_path not in new_inventory:
                removed_files.append(rel_path)

        self.inventory = new_inventory
        self._save_inventory()

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "new_files": new_files,
            "changed_files": changed_files,
            "removed_files": removed_files,
            "scanned_at": datetime.now().isoformat(),
        }

    def verify_integrity(self) -> Dict[str, Any]:
        """验证文件完整性"""
        corrupted = []
        verified = 0
        total = 0

        for rel_path, info in self.inventory.items():
            total += 1
            fpath = os.path.join(self.base_dir, rel_path)
            if os.path.exists(fpath):
                try:
                    current_hash = self._compute_hash(fpath)
                    if current_hash != info["hash"]:
                        corrupted.append({
                            "path": rel_path,
                            "expected_hash": info["hash"],
                            "actual_hash": current_hash,
                        })
                    else:
                        verified += 1
                except (OSError, IOError):
                    corrupted.append({
                        "path": rel_path,
                        "error": "无法读取文件",
                    })
            else:
                corrupted.append({
                    "path": rel_path,
                    "error": "文件不存在",
                })

        return {
            "total_tracked": total,
            "verified": verified,
            "corrupted": len(corrupted),
            "corrupted_files": corrupted,
            "integrity_pct": round(verified / total * 100, 2) if total > 0 else 0,
            "checked_at": datetime.now().isoformat(),
        }

    def get_file_types_summary(self) -> Dict[str, int]:
        """按文件类型统计"""
        summary: Dict[str, int] = {}
        for info in self.inventory.values():
            ftype = info.get("type", "unknown")
            summary[ftype] = summary.get(ftype, 0) + 1
        return dict(sorted(summary.items(), key=lambda x: x[1], reverse=True))

    def _compute_hash(self, filepath: str, algorithm: str = "sha256") -> str:
        """计算文件哈希"""
        h = hashlib.new(algorithm)
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _should_ignore(self, rel_path: str) -> bool:
        """判断是否应该忽略某路径"""
        for pattern in self.ignore_patterns:
            if pattern.startswith("*."):
                if rel_path.endswith(pattern[1:]):
                    return True
            elif pattern.endswith("/"):
                if rel_path.startswith(pattern) or pattern.rstrip("/") in rel_path.split(os.sep):
                    return True
            elif pattern in rel_path:
                return True
        return False

    def _load_inventory(self) -> None:
        """加载已有的文件清单"""
        if os.path.exists(self.inventory_file):
            try:
                with open(self.inventory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.inventory = data.get("files", {})
                    logger.info(f"已加载文件清单: {len(self.inventory)} 个文件")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"加载清单文件失败: {e}，将创建新清单")
                self.inventory = {}

    def _save_inventory(self) -> None:
        """保存文件清单"""
        data = {
            "files": self.inventory,
            "updated_at": datetime.now().isoformat(),
            "version": "1.0",
            "base_dir": self.base_dir,
        }
        # 备份旧清单
        if os.path.exists(self.inventory_file):
            backup_path = self.inventory_file + ".backup"
            try:
                os.replace(self.inventory_file, backup_path)
            except OSError:
                pass

        with open(self.inventory_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"文件清单已保存: {len(self.inventory)} 个文件")


__all__ = ["FileInventoryManager"]