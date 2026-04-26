from fastapi import APIRouter, HTTPException
from app.schemas.portfolio import PortfolioRequest, PortfolioResponse, PositionRequest, PositionResponse
from app.services.portfolio_service import PortfolioService

router = APIRouter()
portfolio_service = PortfolioService()

@router.post("/overview", response_model=PortfolioResponse)
def get_portfolio_overview(request: PortfolioRequest):
    """获取投资组合概览"""
    try:
        result = portfolio_service.get_portfolio_overview(
            portfolio_id=request.portfolio_id
        )
        return PortfolioResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/positions", response_model=PositionResponse)
def get_positions(request: PositionRequest):
    """获取持仓信息"""
    try:
        result = portfolio_service.get_positions(
            portfolio_id=request.portfolio_id
        )
        return PositionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history")
def get_portfolio_history():
    """获取投资组合历史数据"""
    return portfolio_service.get_portfolio_history()
