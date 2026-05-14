#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易策略系统API服务
提供策略管理和西部宽客系统集成接口
"""

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json
import os

# 导入策略管理器和西部宽客集成
from strategy_manager import get_strategy_manager, StrategyType
from xbk_integration import get_xbk_integration, get_technical_analyzer

# 创建FastAPI应用
app = FastAPI(
    title="量化交易策略系统API",
    description="提供策略管理和西部宽客系统集成接口",
    version="1.0.0"
)

# 配置静态文件服务
app.mount("/", StaticFiles(directory=".", html=True), name="static")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取策略管理器
manager = get_strategy_manager()

# 数据模型
class StrategySwitchRequest(BaseModel):
    strategy_type: str

class StrategyConfigRequest(BaseModel):
    strategy_type: str
    config: Dict[str, Any]

class OrderRequest(BaseModel):
    symbol: str
    side: str  # buy/sell
    type: str  # market/limit
    quantity: float
    price: Optional[float] = None

class CancelOrderRequest(BaseModel):
    order_id: str

class TechnicalAnalysisRequest(BaseModel):
    symbol: str
    interval: str = "1h"

# 健康检查
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "量化交易策略系统API运行正常"}

# 获取系统状态
@app.get("/status")
async def get_system_status():
    current_strategy = manager.get_current_strategy()
    strategies = manager.get_available_strategies()
    
    return {
        "current_strategy": current_strategy,
        "strategies": strategies,
        "status": "running"
    }

# 策略管理接口

@app.get("/strategies")
async def get_strategies():
    """
    获取可用策略列表
    """
    strategies = manager.get_available_strategies()
    return {"data": strategies, "total": len(strategies)}

@app.post("/strategies/switch")
async def switch_strategy(request: StrategySwitchRequest):
    """
    切换策略
    """
    try:
        strategy_type = StrategyType(request.strategy_type)
        success = manager.switch_strategy(strategy_type)
        if success:
            return {"success": True, "message": f"策略切换成功: {request.strategy_type}"}
        else:
            raise HTTPException(status_code=400, detail="策略切换失败")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的策略类型")

@app.get("/strategies/current")
async def get_current_strategy():
    """
    获取当前策略
    """
    current_strategy = manager.get_current_strategy()
    if current_strategy:
        return {"data": current_strategy}
    else:
        return {"data": None, "message": "当前没有运行的策略"}

@app.post("/strategies/stop")
async def stop_strategy(request: StrategySwitchRequest):
    """
    停止策略
    """
    try:
        strategy_type = StrategyType(request.strategy_type)
        success = manager.stop_strategy(strategy_type)
        if success:
            return {"success": True, "message": f"策略已停止: {request.strategy_type}"}
        else:
            raise HTTPException(status_code=400, detail="策略停止失败")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的策略类型")

@app.post("/strategies/pause")
async def pause_strategy(request: StrategySwitchRequest):
    """
    暂停策略
    """
    try:
        strategy_type = StrategyType(request.strategy_type)
        success = manager.pause_strategy(strategy_type)
        if success:
            return {"success": True, "message": f"策略已暂停: {request.strategy_type}"}
        else:
            raise HTTPException(status_code=400, detail="策略暂停失败")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的策略类型")

@app.post("/strategies/resume")
async def resume_strategy(request: StrategySwitchRequest):
    """
    恢复策略
    """
    try:
        strategy_type = StrategyType(request.strategy_type)
        success = manager.resume_strategy(strategy_type)
        if success:
            return {"success": True, "message": f"策略已恢复: {request.strategy_type}"}
        else:
            raise HTTPException(status_code=400, detail="策略恢复失败")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的策略类型")

@app.post("/strategies/config")
async def update_strategy_config(request: StrategyConfigRequest):
    """
    更新策略配置
    """
    try:
        strategy_type = StrategyType(request.strategy_type)
        success = manager.update_strategy_config(strategy_type, request.config)
        if success:
            return {"success": True, "message": f"策略配置已更新: {request.strategy_type}"}
        else:
            raise HTTPException(status_code=400, detail="策略配置更新失败")
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的策略类型")

# 西部宽客系统接口

@app.get("/xbk/account")
async def get_xbk_account():
    """
    获取西部宽客账户信息
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    account = xbk.get_account_info()
    if account:
        return account
    else:
        raise HTTPException(status_code=500, detail="获取账户信息失败")

@app.get("/xbk/positions")
async def get_xbk_positions():
    """
    获取西部宽客持仓信息
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    positions = xbk.get_positions()
    return {"data": positions, "total": len(positions)}

@app.get("/xbk/market")
async def get_xbk_market(symbol: str):
    """
    获取西部宽客行情数据
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    market_data = xbk.get_market_data(symbol)
    if market_data:
        return market_data
    else:
        raise HTTPException(status_code=500, detail="获取行情数据失败")

@app.get("/xbk/kline")
async def get_xbk_kline(symbol: str, interval: str = "1h", limit: int = 100):
    """
    获取西部宽客K线数据
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    kline_data = xbk.get_kline_data(symbol, interval, limit)
    if kline_data:
        return {"data": kline_data}
    else:
        raise HTTPException(status_code=500, detail="获取K线数据失败")

@app.post("/xbk/order")
async def place_xbk_order(request: OrderRequest):
    """
    西部宽客下单
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    result = xbk.place_order(
        symbol=request.symbol,
        side=request.side,
        order_type=request.type,
        quantity=request.quantity,
        price=request.price
    )
    if result:
        return result
    else:
        raise HTTPException(status_code=500, detail="下单失败")

@app.post("/xbk/cancel")
async def cancel_xbk_order(request: CancelOrderRequest):
    """
    西部宽客取消订单
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    result = xbk.cancel_order(request.order_id)
    if result:
        return result
    else:
        raise HTTPException(status_code=500, detail="取消订单失败")

@app.post("/xbk/analyze")
async def analyze_xbk_symbol(request: TechnicalAnalysisRequest):
    """
    西部宽客技术分析
    """
    analyzer = get_technical_analyzer()
    analysis = analyzer.analyze_symbol(request.symbol, request.interval)
    if analysis:
        return analysis
    else:
        raise HTTPException(status_code=500, detail="技术分析失败")

@app.get("/xbk/strategies")
async def get_xbk_strategies():
    """
    获取西部宽客可用策略
    """
    xbk = get_xbk_integration()
    if not xbk.get_state().value == "CONNECTED":
        xbk.connect()
    
    strategies = xbk.get_strategies()
    return {"data": strategies, "total": len(strategies)}

# 信号管理接口

@app.get("/signals")
async def get_signals():
    """
    获取交易信号
    """
    # 模拟信号数据
    signals = [
        {
            "id": "1",
            "type": "SIGNAL_BUY",
            "symbol": "601398.SH",
            "price": 5.82,
            "timestamp": "2024-01-01T12:00:00",
            "reason": "MACD金叉",
            "status": "PENDING"
        },
        {
            "id": "2",
            "type": "SIGNAL_REDUCE",
            "symbol": "601318.SH",
            "price": 48.50,
            "timestamp": "2024-01-01T12:05:00",
            "reason": "RSI超买",
            "status": "PENDING"
        },
        {
            "id": "3",
            "type": "SIGNAL_ALERT",
            "symbol": "601857.SH",
            "price": 6.20,
            "timestamp": "2024-01-01T12:10:00",
            "reason": "价格突破",
            "status": "PENDING"
        }
    ]
    return {"data": signals, "total": len(signals)}

@app.post("/signals/confirm/{signal_id}")
async def confirm_signal(signal_id: str):
    """
    确认信号
    """
    return {"success": True, "message": f"信号 {signal_id} 已确认"}

@app.post("/signals/execute/{signal_id}")
async def execute_signal(signal_id: str):
    """
    执行信号
    """
    return {"success": True, "message": f"信号 {signal_id} 已执行"}

# 主函数
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )
