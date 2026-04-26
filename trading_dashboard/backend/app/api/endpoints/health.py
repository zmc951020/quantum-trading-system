from fastapi import APIRouter
from app.services.health_service import HealthService

router = APIRouter()
health_service = HealthService()

@router.get("/status")
def get_health_status():
    """获取服务健康状态"""
    return health_service.get_status()

@router.get("/metrics")
def get_health_metrics():
    """获取健康指标"""
    return health_service.get_metrics()
