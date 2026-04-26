from pydantic import BaseModel, Field
from typing import List, Optional

class PortfolioRequest(BaseModel):
    portfolio_id: str = Field(..., description="投资组合ID")

class Position(BaseModel):
    symbol: str = Field(..., description="标的符号")
    quantity: float = Field(..., description="数量")
    price: float = Field(..., description="价格")
    weight: float = Field(..., description="权重")
    pnl: float = Field(..., description="盈亏")

class PortfolioResponse(BaseModel):
    portfolio_id: str = Field(..., description="投资组合ID")
    total_value: float = Field(..., description="总价值")
    total_pnl: float = Field(..., description="总盈亏")
    total_pnl_pct: float = Field(..., description="总盈亏百分比")
    sharpe_ratio: float = Field(..., description="夏普比率")
    max_drawdown: float = Field(..., description="最大回撤")

class PositionRequest(BaseModel):
    portfolio_id: str = Field(..., description="投资组合ID")

class PositionResponse(BaseModel):
    portfolio_id: str = Field(..., description="投资组合ID")
    positions: List[Position] = Field(..., description="持仓列表")
    cash: float = Field(..., description="现金")
    total_positions: int = Field(..., description="持仓数量")
