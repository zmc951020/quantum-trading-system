from fastapi import APIRouter, HTTPException
from app.schemas.performance import AttributionRequest, AttributionResponse
from app.services.performance_service import PerformanceService

router = APIRouter()
performance_service = PerformanceService()

@router.post("/attribution", response_model=AttributionResponse)
def calculate_attribution(request: AttributionRequest):
    """计算绩效归因"""
    try:
        result = performance_service.calculate_attribution(
            portfolio_returns=request.portfolio_returns,
            benchmark_returns=request.benchmark_returns
        )
        return AttributionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/metrics")
def get_performance_metrics():
    """获取性能指标"""
    return performance_service.get_performance_metrics()
