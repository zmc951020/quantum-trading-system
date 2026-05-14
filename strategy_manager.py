#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略管理器
实现不同策略之间的切换和管理
"""

import os
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StrategyManager')

class StrategyType(Enum):
    """策略类型"""
    HUIJIN_AI = "HUIJIN_AI"
    XBK_SYSTEM = "XBK_SYSTEM"
    MIXED_GRID = "MIXED_GRID"
    ML_STRATEGY = "ML_STRATEGY"

class StrategyStatus(Enum):
    """策略状态"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"

class StrategyConfig:
    """策略配置"""
    def __init__(self, strategy_type: StrategyType, config: Dict):
        self.strategy_type = strategy_type
        self.config = config
        self.created_at = datetime.now()

class StrategyManager:
    """策略管理器"""
    
    def __init__(self):
        self.strategies = {
            StrategyType.HUIJIN_AI: {
                "name": "汇金价值AI轮动策略",
                "description": "聚焦央企国企，中央汇金社保基金持仓，PE<15，跌幅>50%底仓15万，网格做T，金字塔加仓，单票40万封顶",
                "risk_level": "MEDIUM",
                "status": StrategyStatus.IDLE,
                "config": {
                    "target_positions": 5,
                    "total_capital": 3000000,
                    "single_max": 400000,
                    "base_position": 150000
                }
            },
            StrategyType.XBK_SYSTEM: {
                "name": "西部宽客交易系统",
                "description": "实时数据交易系统，支持技术分析、模型策略使用，对接实盘API",
                "risk_level": "MEDIUM",
                "status": StrategyStatus.IDLE,
                "config": {
                    "api_url": "http://localhost:8000",
                    "timeout": 30,
                    "retry_count": 3
                }
            },
            StrategyType.MIXED_GRID: {
                "name": "混合网格策略",
                "description": "分钟级网格交易，自适应市场环境，多因子共振",
                "risk_level": "MEDIUM",
                "status": StrategyStatus.IDLE,
                "config": {
                    "grid_interval": 0.5,
                    "profit_target": 1.0,
                    "max_positions": 10
                }
            },
            StrategyType.ML_STRATEGY: {
                "name": "机器学习策略",
                "description": "基于量子矩阵协变因子的智能预测系统",
                "risk_level": "HIGH",
                "status": StrategyStatus.IDLE,
                "config": {
                    "model_path": "models/ml_strategy.model",
                    "prediction_interval": 5,
                    "confidence_threshold": 0.7
                }
            }
        }
        
        self.current_strategy = None
        self.lock = threading.Lock()
        self.strategy_threads = {}
    
    def get_available_strategies(self) -> List[Dict]:
        """
        获取可用策略列表
        
        Returns:
            List[Dict]: 策略列表
        """
        strategies = []
        for strategy_type, info in self.strategies.items():
            strategies.append({
                "type": strategy_type.value,
                "name": info["name"],
                "description": info["description"],
                "risk_level": info["risk_level"],
                "status": info["status"].value
            })
        return strategies
    
    def get_strategy_info(self, strategy_type: StrategyType) -> Optional[Dict]:
        """
        获取策略信息
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            Dict: 策略信息
        """
        if strategy_type in self.strategies:
            info = self.strategies[strategy_type].copy()
            info["type"] = strategy_type.value
            info["status"] = info["status"].value
            return info
        return None
    
    def switch_strategy(self, strategy_type: StrategyType) -> bool:
        """
        切换策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 切换是否成功
        """
        with self.lock:
            # 检查策略是否存在
            if strategy_type not in self.strategies:
                logger.error(f"策略不存在: {strategy_type.value}")
                return False
            
            # 如果当前有运行中的策略，先停止
            if self.current_strategy and self.current_strategy != strategy_type:
                self.stop_strategy(self.current_strategy)
            
            # 启动新策略
            try:
                self.strategies[strategy_type]["status"] = StrategyStatus.RUNNING
                self.current_strategy = strategy_type
                
                # 启动策略线程
                thread = threading.Thread(target=self._run_strategy, args=(strategy_type,))
                thread.daemon = True
                thread.start()
                self.strategy_threads[strategy_type] = thread
                
                logger.info(f"策略切换成功: {strategy_type.value}")
                return True
            except Exception as e:
                self.strategies[strategy_type]["status"] = StrategyStatus.ERROR
                logger.error(f"策略切换失败: {str(e)}")
                return False
    
    def stop_strategy(self, strategy_type: StrategyType) -> bool:
        """
        停止策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 停止是否成功
        """
        with self.lock:
            if strategy_type not in self.strategies:
                return False
            
            # 停止线程
            if strategy_type in self.strategy_threads:
                # 这里简化处理，实际需要更优雅的线程停止方式
                self.strategy_threads.pop(strategy_type, None)
            
            self.strategies[strategy_type]["status"] = StrategyStatus.IDLE
            
            if self.current_strategy == strategy_type:
                self.current_strategy = None
            
            logger.info(f"策略已停止: {strategy_type.value}")
            return True
    
    def pause_strategy(self, strategy_type: StrategyType) -> bool:
        """
        暂停策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 暂停是否成功
        """
        if strategy_type not in self.strategies:
            return False
        
        self.strategies[strategy_type]["status"] = StrategyStatus.PAUSED
        logger.info(f"策略已暂停: {strategy_type.value}")
        return True
    
    def resume_strategy(self, strategy_type: StrategyType) -> bool:
        """
        恢复策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 恢复是否成功
        """
        if strategy_type not in self.strategies:
            return False
        
        self.strategies[strategy_type]["status"] = StrategyStatus.RUNNING
        logger.info(f"策略已恢复: {strategy_type.value}")
        return True
    
    def get_current_strategy(self) -> Optional[Dict]:
        """
        获取当前策略
        
        Returns:
            Dict: 当前策略信息
        """
        if self.current_strategy:
            return self.get_strategy_info(self.current_strategy)
        return None
    
    def update_strategy_config(self, strategy_type: StrategyType, config: Dict) -> bool:
        """
        更新策略配置
        
        Args:
            strategy_type: 策略类型
            config: 新配置
            
        Returns:
            bool: 更新是否成功
        """
        if strategy_type not in self.strategies:
            return False
        
        self.strategies[strategy_type]["config"].update(config)
        logger.info(f"策略配置已更新: {strategy_type.value}")
        return True
    
    def _run_strategy(self, strategy_type: StrategyType):
        """
        运行策略
        
        Args:
            strategy_type: 策略类型
        """
        logger.info(f"开始运行策略: {strategy_type.value}")
        
        try:
            # 根据策略类型执行不同的逻辑
            if strategy_type == StrategyType.XBK_SYSTEM:
                self._run_xbk_strategy()
            elif strategy_type == StrategyType.HUIJIN_AI:
                self._run_huijin_strategy()
            elif strategy_type == StrategyType.MIXED_GRID:
                self._run_mixed_grid_strategy()
            elif strategy_type == StrategyType.ML_STRATEGY:
                self._run_ml_strategy()
        except Exception as e:
            logger.error(f"策略运行异常: {str(e)}")
            self.strategies[strategy_type]["status"] = StrategyStatus.ERROR
    
    def _run_xbk_strategy(self):
        """
        运行西部宽客策略
        """
        # 导入西部宽客集成模块
        from xbk_integration import get_xbk_integration, get_technical_analyzer
        
        xbk = get_xbk_integration()
        analyzer = get_technical_analyzer()
        
        # 连接到西部宽客系统
        if not xbk.connect():
            logger.error("无法连接西部宽客系统")
            return
        
        try:
            # 主循环
            while self.current_strategy == StrategyType.XBK_SYSTEM:
                # 获取账户信息
                account = xbk.get_account_info()
                if account:
                    logger.info(f"账户余额: {account.get('balance', 'N/A')}")
                
                # 获取持仓
                positions = xbk.get_positions()
                logger.info(f"持仓数量: {len(positions)}")
                
                # 分析BTCUSDT
                analysis = analyzer.analyze_symbol("BTCUSDT")
                if analysis and "signals" in analysis:
                    for signal in analysis["signals"]:
                        logger.info(f"交易信号: {signal['type']} - {signal['reason']}")
                
                # 休眠30秒
                import time
                time.sleep(30)
        finally:
            xbk.disconnect()
    
    def _run_huijin_strategy(self):
        """
        运行汇金价值AI轮动策略
        """
        # 这里可以集成现有的汇金策略逻辑
        logger.info("运行汇金价值AI轮动策略")
        
        import time
        while self.current_strategy == StrategyType.HUIJIN_AI:
            # 模拟策略运行
            logger.info("汇金策略运行中...")
            time.sleep(30)
    
    def _run_mixed_grid_strategy(self):
        """
        运行混合网格策略
        """
        logger.info("运行混合网格策略")
        
        import time
        while self.current_strategy == StrategyType.MIXED_GRID:
            # 模拟策略运行
            logger.info("混合网格策略运行中...")
            time.sleep(30)
    
    def _run_ml_strategy(self):
        """
        运行机器学习策略
        """
        logger.info("运行机器学习策略")
        
        import time
        while self.current_strategy == StrategyType.ML_STRATEGY:
            # 模拟策略运行
            logger.info("机器学习策略运行中...")
            time.sleep(30)
    
    def get_strategy_status(self, strategy_type: StrategyType) -> Optional[StrategyStatus]:
        """
        获取策略状态
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            StrategyStatus: 策略状态
        """
        if strategy_type in self.strategies:
            return self.strategies[strategy_type]["status"]
        return None
    
    def save_state(self, path: str = "strategy_state.json"):
        """
        保存策略状态
        
        Args:
            path: 保存路径
        """
        state = {
            "current_strategy": self.current_strategy.value if self.current_strategy else None,
            "strategies": {},
            "timestamp": datetime.now().isoformat()
        }
        
        for strategy_type, info in self.strategies.items():
            state["strategies"][strategy_type.value] = {
                "status": info["status"].value,
                "config": info["config"]
            }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        logger.info(f"策略状态已保存到: {path}")
    
    def load_state(self, path: str = "strategy_state.json"):
        """
        加载策略状态
        
        Args:
            path: 加载路径
        """
        if not os.path.exists(path):
            logger.warning(f"状态文件不存在: {path}")
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # 恢复当前策略
            if state.get("current_strategy"):
                strategy_type = StrategyType(state["current_strategy"])
                if strategy_type in self.strategies:
                    self.current_strategy = strategy_type
            
            # 恢复策略状态
            for strategy_type_str, strategy_state in state.get("strategies", {}).items():
                try:
                    strategy_type = StrategyType(strategy_type_str)
                    if strategy_type in self.strategies:
                        self.strategies[strategy_type]["status"] = StrategyStatus(strategy_state["status"])
                        self.strategies[strategy_type]["config"].update(strategy_state.get("config", {}))
                except Exception as e:
                    logger.error(f"恢复策略状态失败: {str(e)}")
            
            logger.info(f"策略状态已从: {path} 加载")
        except Exception as e:
            logger.error(f"加载策略状态失败: {str(e)}")

# 全局实例
_strategy_manager = None

def get_strategy_manager() -> StrategyManager:
    """
    获取策略管理器实例
    
    Returns:
        StrategyManager: 策略管理器实例
    """
    global _strategy_manager
    if _strategy_manager is None:
        _strategy_manager = StrategyManager()
    return _strategy_manager

if __name__ == "__main__":
    # 测试代码
    manager = get_strategy_manager()
    
    # 查看可用策略
    strategies = manager.get_available_strategies()
    print("可用策略:")
    for strategy in strategies:
        print(f"- {strategy['name']} ({strategy['type']}) - 状态: {strategy['status']}")
    
    # 切换到西部宽客策略
    print("\n切换到西部宽客策略...")
    success = manager.switch_strategy(StrategyType.XBK_SYSTEM)
    print(f"切换结果: {'成功' if success else '失败'}")
    
    # 查看当前策略
    current = manager.get_current_strategy()
    if current:
        print(f"\n当前策略: {current['name']} - 状态: {current['status']}")
    
    # 等待一段时间
    import time
    time.sleep(10)
    
    # 停止策略
    print("\n停止策略...")
    manager.stop_strategy(StrategyType.XBK_SYSTEM)
    
    # 保存状态
    manager.save_state()
    print("策略状态已保存")
