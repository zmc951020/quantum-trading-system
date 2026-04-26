#!/usr/bin/env python3
"""
模型持久化管理器
用于保存和加载机器学习优化成果，实现永久性传承
"""

import os
import json
import pickle
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np

class ModelPersistenceManager:
    """
    模型持久化管理器

    功能：
    1. 自动保存策略参数和模型状态
    2. 保存傅里叶特征提取器的统计信息
    3. 保存市场状态识别器的状态
    4. 支持自动加载最新优化成果
    5. 支持版本管理和回滚
    6. 保存训练历史和性能指标
    """

    def __init__(self, base_dir: str = "./model_storage"):
        """
        初始化模型持久化管理器

        Args:
            base_dir: 模型存储基础目录
        """
        self.base_dir = base_dir
        self.metadata_file = os.path.join(base_dir, "metadata.json")
        self.latest_file = os.path.join(base_dir, "latest_model.pkl")

        # 确保目录存在
        os.makedirs(base_dir, exist_ok=True)

        # 加载元数据
        self.metadata = self._load_metadata()

        # 版本历史
        self.version_history = self.metadata.get("versions", [])

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载元数据失败: {e}")
                return self._create_default_metadata()
        return self._create_default_metadata()

    def _create_default_metadata(self) -> Dict:
        """创建默认元数据"""
        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version_count": 0,
            "versions": [],
            "current_version": None,
            "best_performance": None
        }

    def _save_metadata(self):
        """保存元数据"""
        self.metadata["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存元数据失败: {e}")

    def _generate_version_id(self) -> str:
        """生成版本ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"v_{timestamp}"

    def _calculate_checksum(self, data: Dict) -> str:
        """计算数据校验和"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()[:8]

    def save_strategy_state(
        self,
        strategy_name: str,
        strategy_state: Dict[str, Any],
        performance_metrics: Optional[Dict[str, float]] = None,
        description: str = ""
    ) -> str:
        """
        保存策略状态

        Args:
            strategy_name: 策略名称
            strategy_state: 策略状态字典
            performance_metrics: 性能指标
            description: 描述

        Returns:
            版本ID
        """
        version_id = self._generate_version_id()
        timestamp = datetime.now()

        # 创建版本记录
        version_record = {
            "version_id": version_id,
            "strategy_name": strategy_name,
            "timestamp": timestamp.isoformat(),
            "description": description,
            "performance_metrics": performance_metrics,
            "checksum": self._calculate_checksum(strategy_state),
            "file_path": os.path.join(self.base_dir, f"{version_id}_{strategy_name}.pkl")
        }

        # 保存策略状态
        try:
            # 创建完整模型数据
            model_data = {
                "version_id": version_id,
                "strategy_name": strategy_name,
                "timestamp": timestamp.isoformat(),
                "strategy_state": strategy_state,
                "performance_metrics": performance_metrics,
                "description": description
            }

            with open(version_record["file_path"], 'wb') as f:
                pickle.dump(model_data, f)

            # 更新元数据
            self.metadata["versions"].append(version_record)
            self.metadata["version_count"] = len(self.metadata["versions"])
            self.metadata["current_version"] = version_id

            # 更新最佳性能
            if performance_metrics:
                current_best = self.metadata.get("best_performance")
                if current_best is None or performance_metrics.get("total_return", 0) > current_best.get("total_return", 0):
                    self.metadata["best_performance"] = {
                        **performance_metrics,
                        "version_id": version_id,
                        "timestamp": timestamp.isoformat()
                    }

            self._save_metadata()

            print(f"策略状态已保存: {version_id}")
            print(f"文件路径: {version_record['file_path']}")

            return version_id

        except Exception as e:
            print(f"保存策略状态失败: {e}")
            return None

    def load_strategy_state(
        self,
        version_id: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        加载策略状态

        Args:
            version_id: 版本ID（如果为None，加载最新版本）
            strategy_name: 策略名称（如果指定，优先使用）

        Returns:
            策略状态字典
        """
        # 确定要加载的版本
        if version_id is None:
            if strategy_name:
                # 查找指定策略的最新版本
                for v in reversed(self.metadata["versions"]):
                    if v["strategy_name"] == strategy_name:
                        version_id = v["version_id"]
                        break
            if version_id is None:
                version_id = self.metadata.get("current_version")

        if version_id is None:
            print("没有找到可用的模型版本")
            return None

        # 查找版本记录
        version_record = None
        for v in self.metadata["versions"]:
            if v["version_id"] == version_id:
                version_record = v
                break

        if version_record is None:
            print(f"版本不存在: {version_id}")
            return None

        # 加载策略状态
        try:
            file_path = version_record["file_path"]
            if not os.path.exists(file_path):
                print(f"模型文件不存在: {file_path}")
                return None

            with open(file_path, 'rb') as f:
                model_data = pickle.load(f)

            print(f"已加载模型版本: {version_id}")
            print(f"策略名称: {model_data.get('strategy_name')}")
            print(f"训练时间: {model_data.get('timestamp')}")

            if model_data.get("performance_metrics"):
                print("性能指标:")
                for k, v in model_data["performance_metrics"].items():
                    print(f"  {k}: {v}")

            return model_data.get("strategy_state")

        except Exception as e:
            print(f"加载策略状态失败: {e}")
            return None

    def list_versions(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        列出版本历史

        Args:
            strategy_name: 策略名称（如果为None，列出所有策略）
            limit: 返回数量限制

        Returns:
            版本记录列表
        """
        versions = self.metadata.get("versions", [])

        if strategy_name:
            versions = [v for v in versions if v["strategy_name"] == strategy_name]

        # 按时间倒序排列
        versions = sorted(versions, key=lambda x: x["timestamp"], reverse=True)

        return versions[:limit]

    def get_best_version(self, strategy_name: Optional[str] = None) -> Optional[Dict]:
        """
        获取最佳性能版本

        Args:
            strategy_name: 策略名称

        Returns:
            最佳版本记录
        """
        best = self.metadata.get("best_performance")
        if best and (strategy_name is None or
            any(v["strategy_name"] == strategy_name for v in self.metadata["versions"]
                if v["version_id"] == best.get("version_id"))):
            return best
        return None

    def rollback(self, version_id: str) -> bool:
        """
        回滚到指定版本

        Args:
            version_id: 版本ID

        Returns:
            是否成功
        """
        # 查找版本记录
        version_record = None
        for v in self.metadata["versions"]:
            if v["version_id"] == version_id:
                version_record = v
                break

        if version_record is None:
            print(f"版本不存在: {version_id}")
            return False

        # 更新当前版本
        self.metadata["current_version"] = version_id
        self._save_metadata()

        print(f"已回滚到版本: {version_id}")
        return True

    def export_model_package(
        self,
        version_id: str,
        output_path: str
    ) -> bool:
        """
        导出模型包（包含模型和所有依赖信息）

        Args:
            version_id: 版本ID
            output_path: 输出路径

        Returns:
            是否成功
        """
        # 查找版本记录
        version_record = None
        for v in self.metadata["versions"]:
            if v["version_id"] == version_id:
                version_record = v
                break

        if version_record is None:
            print(f"版本不存在: {version_id}")
            return False

        try:
            # 读取模型数据
            with open(version_record["file_path"], 'rb') as f:
                model_data = pickle.load(f)

            # 创建导出包
            export_package = {
                "model_data": model_data,
                "metadata": version_record,
                "export_timestamp": datetime.now().isoformat(),
                "export_version": "1.0"
            }

            # 保存导出包
            with open(output_path, 'wb') as f:
                pickle.dump(export_package, f)

            print(f"模型包已导出: {output_path}")
            return True

        except Exception as e:
            print(f"导出模型包失败: {e}")
            return False

    def import_model_package(self, package_path: str) -> Optional[str]:
        """
        导入模型包

        Args:
            package_path: 包路径

        Returns:
            版本ID
        """
        try:
            # 读取模型包
            with open(package_path, 'rb') as f:
                package = pickle.load(f)

            model_data = package["model_data"]
            version_id = model_data.get("version_id") or self._generate_version_id()

            # 更新版本记录
            version_record = {
                "version_id": version_id,
                "strategy_name": model_data.get("strategy_name"),
                "timestamp": model_data.get("timestamp"),
                "description": model_data.get("description", ""),
                "performance_metrics": model_data.get("performance_metrics"),
                "checksum": self._calculate_checksum(model_data.get("strategy_state", {})),
                "file_path": os.path.join(self.base_dir, f"{version_id}_{model_data.get('strategy_name')}.pkl")
            }

            # 保存模型数据
            with open(version_record["file_path"], 'wb') as f:
                pickle.dump(model_data, f)

            # 更新元数据
            self.metadata["versions"].append(version_record)
            self.metadata["version_count"] = len(self.metadata["versions"])
            self.metadata["current_version"] = version_id
            self._save_metadata()

            print(f"模型包已导入: {version_id}")
            return version_id

        except Exception as e:
            print(f"导入模型包失败: {e}")
            return None

    def get_statistics(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_versions": self.metadata.get("version_count", 0),
            "strategies": list(set(v["strategy_name"] for v in self.metadata.get("versions", []))),
            "current_version": self.metadata.get("current_version"),
            "best_performance": self.metadata.get("best_performance"),
            "storage_dir": self.base_dir,
            "storage_size_mb": self._get_storage_size()
        }

    def _get_storage_size(self) -> float:
        """获取存储大小（MB）"""
        total_size = 0
        for root, dirs, files in os.walk(self.base_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
        return total_size / (1024 * 1024)


class StrategyStateExtractor:
    """
    策略状态提取器
    从策略对象中提取可序列化的状态
    """

    @staticmethod
    def extract_fourier_rl_state(strategy) -> Dict[str, Any]:
        """
        提取傅里叶策略状态

        Args:
            strategy: FourierRLStrategy实例

        Returns:
            策略状态字典
        """
        state = {
            # 基础参数
            "base_price": strategy.base_price,
            "initial_balance": strategy.initial_balance,
            "current_balance": strategy.current_balance,
            "position": strategy.position,
            "entry_price": strategy.entry_price,

            # 交易统计
            "total_trades": strategy.total_trades,
            "winning_trades": strategy.winning_trades,
            "losing_trades": strategy.losing_trades,
            "profit_history": strategy.profit_history,

            # 风控参数
            "stop_loss_pct": strategy.stop_loss_pct,
            "take_profit_pct": strategy.take_profit_pct,
            "max_position_pct": strategy.max_position_pct,

            # 价格历史摘要
            "price_history_length": len(strategy.price_history),
            "price_history_sample": strategy.price_history[-100:] if len(strategy.price_history) > 0 else [],

            # 市场状态
            "current_regime": strategy.current_regime,

            # 峰值
            "peak_value": strategy.peak_value,

            # 模型训练状态
            "model_trained": strategy.model_trained
        }

        # 提取傅里叶特征提取器状态
        if hasattr(strategy, 'fourier_extractor'):
            state["fourier_extractor"] = {
                "min_window": strategy.fourier_extractor.min_window,
                "max_window": strategy.fourier_extractor.max_window,
                "top_k_cycles": strategy.fourier_extractor.top_k_cycles,
                "cycle_memory": strategy.fourier_extractor.cycle_memory[-10:] if hasattr(strategy.fourier_extractor, 'cycle_memory') else []
            }

        # 提取市场状态识别器状态
        if hasattr(strategy, 'regime_detector'):
            state["regime_detector"] = {
                "n_regimes": strategy.regime_detector.n_regimes,
                "lookback": strategy.regime_detector.lookback,
                "state_mapping": strategy.regime_detector.state_mapping,
                "regime_history": strategy.regime_detector.regime_history[-50:] if hasattr(strategy.regime_detector, 'regime_history') else []
            }

        # 提取双维度市场状态
        if hasattr(strategy, 'dual_market_state'):
            state["dual_market_state"] = {
                "current_hmm_state": strategy.dual_market_state.current_hmm_state,
                "current_trend_type": strategy.dual_market_state.current_trend_type
            }

        return state

    @staticmethod
    def restore_fourier_rl_state(strategy, state: Dict[str, Any]):
        """
        恢复傅里叶策略状态

        Args:
            strategy: FourierRLStrategy实例
            state: 策略状态字典
        """
        # 恢复基础参数
        strategy.base_price = state.get("base_price", strategy.base_price)
        strategy.initial_balance = state.get("initial_balance", strategy.initial_balance)
        strategy.current_balance = state.get("current_balance", strategy.current_balance)
        strategy.position = state.get("position", 0)
        strategy.entry_price = state.get("entry_price", 0)

        # 恢复交易统计
        strategy.total_trades = state.get("total_trades", 0)
        strategy.winning_trades = state.get("winning_trades", 0)
        strategy.losing_trades = state.get("losing_trades", 0)
        strategy.profit_history = state.get("profit_history", [])

        # 恢复风控参数
        strategy.stop_loss_pct = state.get("stop_loss_pct", 0.05)
        strategy.take_profit_pct = state.get("take_profit_pct", 0.15)
        strategy.max_position_pct = state.get("max_position_pct", 0.95)

        # 恢复价格历史
        if "price_history_sample" in state:
            strategy.price_history = state["price_history_sample"].copy() if isinstance(state["price_history_sample"], list) else []

        # 恢复市场状态
        strategy.current_regime = state.get("current_regime", 0)

        # 恢复峰值
        strategy.peak_value = state.get("peak_value", strategy.initial_balance)

        # 恢复模型训练状态
        strategy.model_trained = state.get("model_trained", False)

        # 恢复傅里叶特征提取器状态
        if hasattr(strategy, 'fourier_extractor') and "fourier_extractor" in state:
            fe_state = state["fourier_extractor"]
            strategy.fourier_extractor.min_window = fe_state.get("min_window", 32)
            strategy.fourier_extractor.max_window = fe_state.get("max_window", 256)
            strategy.fourier_extractor.top_k_cycles = fe_state.get("top_k_cycles", 5)
            if "cycle_memory" in fe_state:
                strategy.fourier_extractor.cycle_memory = fe_state["cycle_memory"]

        # 恢复市场状态识别器状态
        if hasattr(strategy, 'regime_detector') and "regime_detector" in state:
            rd_state = state["regime_detector"]
            strategy.regime_detector.n_regimes = rd_state.get("n_regimes", 3)
            strategy.regime_detector.lookback = rd_state.get("lookback", 100)
            strategy.regime_detector.state_mapping = rd_state.get("state_mapping", {0: 0, 1: 1, 2: 2})
            if "regime_history" in rd_state:
                strategy.regime_detector.regime_history = rd_state["regime_history"]

        # 恢复双维度市场状态
        if hasattr(strategy, 'dual_market_state') and "dual_market_state" in state:
            dms_state = state["dual_market_state"]
            strategy.dual_market_state.current_hmm_state = dms_state.get("current_hmm_state", 0)
            strategy.dual_market_state.current_trend_type = dms_state.get("current_trend_type", "range_bound")
