from fastapi import APIRouter
from app.api.endpoints import risk, performance, portfolio, health

router = APIRouter()

# 注册各个模块的路由
router.include_router(risk.router, prefix="/risk", tags=["risk"])
router.include_router(performance.router, prefix="/performance", tags=["performance"])
router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
router.include_router(health.router, prefix="/health", tags=["health"])
