from pydantic import BaseModel, Field
from typing import List, Optional

class AttributionRequest(BaseModel):
    portfolio_returns: List[float] = Field(..., description="投资组合收益率")
    benchmark_returns: List[float] = Field(..., description="基准收益率")

class AttributionResponse(BaseModel):
    total_return: float = Field(..., description="总收益")
    benchmark_return: float = Field(..., description="基准收益")
    alpha: float = Field(..., description="Alpha")
    information_ratio: float = Field(..., description="信息比率")
    selection_return: float = Field(..., description="选股收益")
    allocation_return: float = Field(..., description="配置收益")
