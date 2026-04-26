from fastapi import APIRouter, HTTPException
from app.schemas.risk import VaRRequest, VaRResponse, StressTestRequest, StressTestResponse
from app.services.risk_service import RiskService

router = APIRouter()
risk_service = RiskService()

@router.post("/var", response_model=VaRResponse)
def calculate_var(request: VaRRequest):
    """计算VaR和CVaR"""
    try:
        result = risk_service.calculate_var(
            returns=request.returns,
            confidence_level=request.confidence_level,
            method=request.method
        )
        return VaRResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stress-test", response_model=StressTestResponse)
def run_stress_test(request: StressTestRequest):
    """运行压力测试"""
    try:
        result = risk_service.run_stress_test(
            portfolio_values=request.portfolio_values,
            scenario=request.scenario
        )
        return StressTestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/scenarios")
def get_stress_scenarios():
    """获取可用的压力测试场景"""
    return risk_service.get_stress_scenarios()
