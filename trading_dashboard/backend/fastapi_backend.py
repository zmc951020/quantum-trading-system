from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
import json
import time
import random
from datetime import datetime

# 创建FastAPI应用
app = FastAPI(
    title="量化交易仪表盘API",
    description="专业级量化交易系统API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模拟数据
portfolio_data = {
    "total_value": 1000000.0,
    "total_pnl": 150000.0,
    "total_pnl_pct": 0.15,
    "sharpe_ratio": 1.5,
    "max_drawdown": -0.15
}

positions_data = {
    "positions": [
        {"symbol": "AAPL", "quantity": 100, "price": 150.0, "weight": 0.25, "pnl": 5000.0},
        {"symbol": "MSFT", "quantity": 50, "price": 300.0, "weight": 0.30, "pnl": 7500.0},
        {"symbol": "GOOG", "quantity": 20, "price": 1000.0, "weight": 0.40, "pnl": 10000.0},
    ],
    "cash": 50000.0,
    "total_positions": 3
}

history_data = {
    "dates": [f"2024-01-{i:02d}" for i in range(1, 101)],
    "values": [1000000.0 * (1 + 0.001 * i + random.normalvariate(0, 0.005)) for i in range(100)]
}

risk_data = {
    "var": -0.025,
    "cvar": -0.035,
    "confidence_level": 0.95,
    "method": "historical"
}

stress_test_data = {
    "2008_financial_crisis": {
        "scenario": "2008_financial_crisis",
        "estimated_loss": -400000.0,
        "estimated_loss_pct": -0.40,
        "stressed_var": -0.05
    },
    "2020_covid": {
        "scenario": "2020_covid",
        "estimated_loss": -350000.0,
        "estimated_loss_pct": -0.35,
        "stressed_var": -0.045
    }
}

performance_data = {
    "total_return": 0.15,
    "benchmark_return": 0.10,
    "alpha": 0.05,
    "information_ratio": 0.8,
    "selection_return": 0.03,
    "allocation_return": 0.02
}

metrics_data = {
    "sharpe_ratio": 1.5,
    "sortino_ratio": 1.8,
    "calmar_ratio": 2.0,
    "max_drawdown": -0.15,
    "win_rate": 0.6,
    "profit_factor": 1.8
}

health_data = {
    "status": "healthy",
    "uptime": 3600.0,
    "services": {
        "risk_service": "healthy",
        "performance_service": "healthy",
        "portfolio_service": "healthy",
        "database": "healthy"
    },
    "timestamp": time.time()
}

health_metrics_data = {
    "cpu_usage": 0.25,
    "memory_usage": 0.4,
    "disk_usage": 0.3,
    "api_response_time": 0.1,
    "error_rate": 0.01
}

# 数据模型
class VaRRequest(BaseModel):
    confidence_level: float = 0.95

class StressTestRequest(BaseModel):
    scenario: str = "2008_financial_crisis"

class PortfolioRequest(BaseModel):
    portfolio_id: str = "portfolio1"

class PerformanceRequest(BaseModel):
    portfolio_id: str = "portfolio1"

# API端点
@app.get("/")
async def root():
    """根路径"""
    return {"message": "量化交易仪表盘API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}

@app.get("/api/risk/scenarios")
async def get_risk_scenarios():
    """获取风险情景列表"""
    scenarios = ["2008_financial_crisis", "2020_covid", "2015_stock_crash", "1987_black_monday", "2022_interest_rate_hike"]
    return scenarios

@app.post("/api/risk/var")
async def calculate_var(request: VaRRequest):
    """计算VaR/CVaR"""
    return risk_data

@app.post("/api/risk/stress-test")
async def run_stress_test(request: StressTestRequest):
    """运行压力测试"""
    scenario = request.scenario
    result = stress_test_data.get(scenario, stress_test_data['2008_financial_crisis'])
    return result

@app.get("/api/portfolio/history")
async def get_portfolio_history():
    """获取投资组合历史数据"""
    return history_data

@app.post("/api/portfolio/overview")
async def get_portfolio_overview(request: PortfolioRequest):
    """获取投资组合概览"""
    return portfolio_data

@app.post("/api/portfolio/positions")
async def get_portfolio_positions(request: PortfolioRequest):
    """获取投资组合持仓"""
    return positions_data

@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """获取性能指标"""
    return metrics_data

@app.post("/api/performance/attribution")
async def get_performance_attribution(request: PerformanceRequest):
    """获取绩效归因"""
    return performance_data

@app.get("/api/health/status")
async def get_health_status():
    """获取健康状态"""
    return health_data

@app.get("/api/health/metrics")
async def get_health_metrics():
    """获取健康指标"""
    return health_metrics_data

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)