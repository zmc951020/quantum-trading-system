#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能模型路由器
实现：免费/收费模型自动切换、智能路由、成本优化
兼容Ollama自主驱动系统
"""
import os
import sys
import logging
import threading
import time
import json
from typing import Dict, Any, Optional, Callable
from enum import Enum
import requests
from cachetools import LRUCache, TTLCache

logger = logging.getLogger(__name__)

class ModelType(Enum):
    FREE = "free"      # 免费模型：Llama3/豆包Mini
    PAID = "paid"      # 收费模型：豆包Pro/DeepSeek

class ModelRouter:
    """智能模型路由器"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._cache = TTLCache(maxsize=1000, ttl=300)  # 5分钟缓存
        self._rate_limiter = {}
        
        # 模型配置
        self.free_model_endpoint = os.getenv('FREE_MODEL_ENDPOINT', 'http://localhost:11434/api/chat')
        self.paid_model_endpoint = os.getenv('PAID_MODEL_ENDPOINT', 'https://api.doubao.com/v1/chat/completions')
        self.paid_api_key = os.getenv('PAID_API_KEY', '')
        
        # 切换阈值
        self.volatility_threshold = 0.02  # 2%波动率触发收费模型
        self.volume_threshold = 2.0       # 2倍成交量触发
        self.breakout_threshold = 0.03    # 3%突破触发
        
        # 状态
        self.current_volatility = 0.0
        self.current_volume_ratio = 1.0
        self.is_breakout = False
        
    def update_market_state(self, volatility: float, volume_ratio: float, is_breakout: bool):
        """更新市场状态，用于模型切换决策"""
        with self._lock:
            self.current_volatility = volatility
            self.current_volume_ratio = volume_ratio
            self.is_breakout = is_breakout
            
    def should_use_paid_model(self) -> bool:
        """判断是否应该使用收费模型"""
        with self._lock:
            # 关键条件：任一条件满足就切收费
            if self.current_volatility > self.volatility_threshold:
                logger.info(f"波动率{self.current_volatility:.1%}超过阈值，使用收费模型")
                return True
                
            if self.current_volume_ratio > self.volume_threshold:
                logger.info(f"成交量{self.current_volume_ratio:.1f}倍放大，使用收费模型")
                return True
                
            if self.is_breakout:
                logger.info("检测到突破形态，使用收费模型")
                return True
                
            return False
            
    def chat(self, prompt: str, system_prompt: str = "") -> str:
        """智能聊天，自动选择模型"""
        # 缓存检查
        cache_key = f"{prompt}:{system_prompt}:{self.should_use_paid_model()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
            
        # 限流检查
        now = time.time()
        if not self._check_rate_limit(now):
            # 限流了，降级用免费
            return self._call_free_model(prompt, system_prompt)
            
        # 自动选择模型
        if self.should_use_paid_model():
            try:
                result = self._call_paid_model(prompt, system_prompt)
                self._cache[cache_key] = result
                return result
            except Exception as e:
                logger.warning(f"收费模型调用失败，降级到免费模型: {e}")
                # 降级
                result = self._call_free_model(prompt, system_prompt)
                self._cache[cache_key] = result
                return result
        else:
            result = self._call_free_model(prompt, system_prompt)
            self._cache[cache_key] = result
            return result
            
    def _call_free_model(self, prompt: str, system_prompt: str) -> str:
        """调用免费Ollama模型"""
        payload = {
            "model": "llama3",
            "messages": [
                {"role": "system", "content": system_prompt or "你是一个量化交易助手"},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }
        
        response = requests.post(self.free_model_endpoint, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data['message']['content']
        
    def _call_paid_model(self, prompt: str, system_prompt: str) -> str:
        """调用收费豆包Pro模型"""
        headers = {
            "Authorization": f"Bearer {self.paid_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "doubao-pro",
            "messages": [
                {"role": "system", "content": system_prompt or "你是一个专业的量化交易分析师"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096
        }
        
        response = requests.post(self.paid_model_endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']
        
    def _check_rate_limit(self, now: float) -> bool:
        """检查限流"""
        # 收费模型每分钟最多10次调用
        minute_key = int(now / 60)
        count = self._rate_limiter.get(minute_key, 0)
        if count >= 10:
            return False
        self._rate_limiter[minute_key] = count + 1
        return True
        
# 全局单例
_router: Optional[ModelRouter] = None

def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
