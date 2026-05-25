#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略API - Aurora系统对外策略接口
提供策略注册、查询、管理等功能
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StrategyInfo:
    """策略信息"""
    name: str
    version: str = "1.0"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"  # active / paused / archived


class StrategyAPI:
    """策略API管理器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.strategies: Dict[str, StrategyInfo] = {}
        self._load_strategies()

    def register_strategy(
        self,
        name: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        version: str = "1.0",
    ) -> Dict[str, Any]:
        """注册策略"""
        if name in self.strategies:
            return {"status": "error", "message": f"策略 {name} 已存在"}

        strategy = StrategyInfo(
            name=name,
            version=version,
            description=description,
            parameters=parameters or {},
            tags=tags or [],
        )
        self.strategies[name] = strategy
        logger.info(f"策略已注册: {name} v{version}")

        return {
            "status": "success",
            "message": f"策略 {name} 已注册",
            "strategy": {
                "name": strategy.name,
                "version": strategy.version,
                "description": strategy.description,
                "parameters": strategy.parameters,
                "tags": strategy.tags,
                "created_at": strategy.created_at,
            },
        }

    def get_strategy(self, name: str) -> Optional[Dict[str, Any]]:
        """获取策略信息"""
        strategy = self.strategies.get(name)
        if not strategy:
            return None
        return {
            "name": strategy.name,
            "version": strategy.version,
            "description": strategy.description,
            "parameters": strategy.parameters,
            "tags": strategy.tags,
            "status": strategy.status,
            "created_at": strategy.created_at,
        }

    def list_strategies(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有策略"""
        result = []
        for name, strategy in self.strategies.items():
            if status and strategy.status != status:
                continue
            result.append({
                "name": strategy.name,
                "version": strategy.version,
                "status": strategy.status,
                "description": strategy.description,
                "tags": strategy.tags,
            })
        return result

    def update_parameters(self, name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """更新策略参数"""
        strategy = self.strategies.get(name)
        if not strategy:
            return {"status": "error", "message": f"策略 {name} 不存在"}

        strategy.parameters.update(parameters)
        logger.info(f"策略 {name} 参数已更新")

        return {
            "status": "success",
            "message": f"策略 {name} 参数已更新",
            "parameters": strategy.parameters,
        }

    def set_status(self, name: str, status: str) -> Dict[str, Any]:
        """设置策略状态"""
        strategy = self.strategies.get(name)
        if not strategy:
            return {"status": "error", "message": f"策略 {name} 不存在"}

        valid_statuses = ["active", "paused", "archived"]
        if status not in valid_statuses:
            return {"status": "error", "message": f"无效状态。有效值: {valid_statuses}"}

        strategy.status = status
        logger.info(f"策略 {name} 状态已设置为 {status}")

        return {"status": "success", "message": f"策略 {name} 状态已设为 {status}"}

    def delete_strategy(self, name: str) -> Dict[str, Any]:
        """删除策略"""
        if name not in self.strategies:
            return {"status": "error", "message": f"策略 {name} 不存在"}

        del self.strategies[name]
        logger.info(f"策略已删除: {name}")

        return {"status": "success", "message": f"策略 {name} 已删除"}

    def get_summary(self) -> Dict[str, Any]:
        """获取策略摘要"""
        active = sum(1 for s in self.strategies.values() if s.status == "active")
        paused = sum(1 for s in self.strategies.values() if s.status == "paused")
        archived = sum(1 for s in self.strategies.values() if s.status == "archived")

        return {
            "total": len(self.strategies),
            "active": active,
            "paused": paused,
            "archived": archived,
            "strategies": list(self.strategies.keys()),
        }

    def _load_strategies(self) -> None:
        """从配置文件加载策略"""
        # 预加载默认策略
        self.register_strategy(
            name="gbm_gyro_v1",
            description="GBM陀螺策略 - 布朗运动随机微分方程驱动",
            parameters={"drift": 0.1, "volatility": 0.2, "steps": 100},
            tags=["gyro", "gbm"],
        )
        self.register_strategy(
            name="hmm_grid_v1",
            description="HMM网格策略 - 隐马尔可夫模型状态驱动",
            parameters={"n_states": 3, "lookback": 60},
            tags=["hmm", "grid"],
        )
        self.register_strategy(
            name="shepherd_v6",
            description="牧羊人v6策略 - 多专家委员会收敛优化",
            parameters={"experts": 6, "convergence_threshold": 0.001},
            tags=["shepherd", "optimization"],
        )


__all__ = ["StrategyAPI", "StrategyInfo"]