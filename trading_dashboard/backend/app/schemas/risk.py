from pydantic import BaseModel, Field
from typing import List, Optional

class VaRRequest(BaseModel):
    returns: List[float] = Field(..., description="收益率数据")
    confidence_level: float = Field(default=0.95, description="置信水平")
    method: str = Field(default="historical", description="计算方法: historical, parametric, monte_carlo")

class VaRResponse(BaseModel):
    var: float = Field(..., description="风险价值")
    cvar: float = Field(..., description="条件风险价值")
    confidence_level: float = Field(..., description="置信水平")
    method: str = Field(..., description="计算方法")

class StressTestRequest(BaseModel):
    portfolio_values: List[float] = Field(..., description="投资组合价值数据")
    scenario: str = Field(..., description="压力测试场景")

class StressTestResponse(BaseModel):
    scenario: str = Field(..., description="压力测试场景")
    estimated_loss: float = Field(..., description="估计损失")
    estimated_loss_pct: float = Field(..., description="估计损失百分比")
    stressed_var: float = Field(..., description="压力测试后的VaR")
