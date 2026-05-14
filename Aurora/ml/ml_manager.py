# -*- coding: utf-8 -*-
"""
机器学习管理器模块
提供统一的机器学习模型管理接口
"""

import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

class MLManager:
    """
    机器学习管理器
    管理所有机器学习模型的加载、训练和预测
    """

    def __init__(self):
        """初始化ML管理器"""
        self.models = {}
        self.model_dir = os.path.join(os.path.dirname(__file__), 'models')
        self._ensure_model_dir()
        self._load_default_models()

    def _ensure_model_dir(self):
        """确保模型目录存在"""
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)

    def _load_default_models(self):
        """加载默认模型"""
        try:
            # 尝试加载LSTM模型
            try:
                from .models.lstm import LSTM_Model
                self.models['lstm'] = LSTM_Model()
            except Exception as e:
                pass

            # 尝试加载Transformer模型
            try:
                from .models.transformer_ts import TransformerModel
                self.models['transformer'] = TransformerModel()
            except Exception as e:
                pass

            # 尝试加载强化学习模型
            try:
                from .models.ppo_agent import PPOAgent
                self.models['ppo'] = PPOAgent()
            except Exception as e:
                pass

        except Exception as e:
            pass

    def get_model(self, model_name: str) -> Optional[Any]:
        """
        获取指定的机器学习模型

        Args:
            model_name: 模型名称

        Returns:
            模型实例，如果不存在返回None
        """
        return self.models.get(model_name)

    def load_model(self, model_name: str, model_path: str) -> bool:
        """
        加载外部模型

        Args:
            model_name: 模型名称
            model_path: 模型文件路径

        Returns:
            是否加载成功
        """
        try:
            # 这里可以扩展为实际加载模型的逻辑
            self.models[model_name] = {'path': model_path, 'loaded_at': datetime.now()}
            return True
        except Exception as e:
            return False

    def train_model(self, model_name: str, data: Any) -> Dict[str, Any]:
        """
        训练指定模型

        Args:
            model_name: 模型名称
            data: 训练数据

        Returns:
            训练结果
        """
        model = self.get_model(model_name)
        if model and hasattr(model, 'train'):
            try:
                result = model.train(data)
                return {'success': True, 'result': result}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': '模型不存在或不支持训练'}

    def predict(self, model_name: str, input_data: Any) -> Any:
        """
        使用指定模型进行预测

        Args:
            model_name: 模型名称
            input_data: 输入数据

        Returns:
            预测结果
        """
        model = self.get_model(model_name)
        if model and hasattr(model, 'predict'):
            try:
                return model.predict(input_data)
            except Exception as e:
                return None
        return None

    def get_status(self) -> Dict[str, Any]:
        """
        获取ML管理器状态

        Returns:
            状态信息
        """
        return {
            'models': list(self.models.keys()),
            'model_count': len(self.models),
            'model_dir': self.model_dir,
            'status': 'healthy' if self.models else 'warning'
        }

    def list_models(self) -> list:
        """
        列出所有可用模型

        Returns:
            模型名称列表
        """
        return list(self.models.keys())

    def unload_model(self, model_name: str) -> bool:
        """
        卸载指定模型

        Args:
            model_name: 模型名称

        Returns:
            是否卸载成功
        """
        if model_name in self.models:
            del self.models[model_name]
            return True
        return False

# 全局实例
_ml_manager = None

def get_ml_manager() -> MLManager:
    """
    获取全局ML管理器实例

    Returns:
        MLManager: 机器学习管理器实例
    """
    global _ml_manager
    if _ml_manager is None:
        _ml_manager = MLManager()
    return _ml_manager

__all__ = ['MLManager', 'get_ml_manager']
