from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from app.api.routes import router as api_router
from app.services.risk_service import RiskService
from app.services.performance_service import PerformanceService

# 全局服务实例
risk_service = RiskService()
performance_service = PerformanceService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    print("正在初始化服务...")
    risk_service.initialize()
    performance_service.initialize()
    yield
    # 关闭时
    print("正在关闭服务...")

# 创建FastAPI应用
app = FastAPI(
    title="量化交易仪表盘API",
    description="提供风控、绩效归因和策略监控等功能",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该设置具体的前端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "量化交易仪表盘API", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
