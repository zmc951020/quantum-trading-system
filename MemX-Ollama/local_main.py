import sys
import os
import logging
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入核心模块
from memx import OllamaMemXBridge, validate_config

# 创建FastAPI应用
app = FastAPI(
    title="Ollama MemX API",
    description="Ollama永久记忆系统工业级API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局Ollama MemX Bridge实例
bridge = None

@app.on_event("startup")
async def startup_event():
    """启动时初始化Ollama MemX Bridge"""
    global bridge
    try:
        logger.info("正在初始化Ollama MemX Bridge...")
        bridge = OllamaMemXBridge()
        logger.info("Ollama MemX Bridge初始化成功")
    except Exception as e:
        logger.error(f"Ollama MemX Bridge初始化失败：{str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    if bridge:
        await bridge.close()
        logger.info("Ollama MemX Bridge已关闭")

# 数据模型
class ChatRequest(BaseModel):
    user_id: str
    prompt: str
    tenant_id: Optional[str] = None

class ChatResponse(BaseModel):
    code: int
    message: str
    data: Optional[str]
    memory_info: Dict[str, int]

class MemorySearchRequest(BaseModel):
    query: str
    tenant_id: Optional[str] = None
    limit: Optional[int] = 3

class MemoryDeleteRequest(BaseModel):
    user_id: str
    tenant_id: Optional[str] = None

# API接口
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "memx-api", "timestamp": 1234567890}

@app.get("/")
async def root():
    return {
        "service": "Ollama MemX",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt不能为空")

    if not request.user_id or not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id不能为空")

    request_id = str(uuid.uuid4())
    tenant_id = request.tenant_id or "default"

    logger.info(f"收到聊天请求，用户：{request.user_id}，租户：{tenant_id}，请求ID：{request_id}")

    try:
        result = await bridge.chat_with_memory(
            request_id=request_id,
            user_id=request.user_id,
            prompt=request.prompt,
            tenant_id=tenant_id
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"聊天请求处理失败：{str(e)}")
        return ChatResponse(
            code=500,
            message=f"服务器内部错误：{str(e)}",
            data=None,
            memory_info={}
        )

@app.post("/memory/search")
async def search_memory(request: MemorySearchRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query不能为空")

    tenant_id = request.tenant_id or "default"
    limit = request.limit or 3

    try:
        long_mem = bridge.vector_mem.search(tenant_id, request.query, limit)
        graph_mem = bridge.graph_mem.query_related(request.query, tenant_id, limit)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "vector_memory": long_mem,
                "graph_memory": graph_mem
            }
        }
    except Exception as e:
        logger.error(f"记忆搜索失败：{str(e)}")
        return {
            "code": 500,
            "message": f"搜索失败：{str(e)}",
            "data": None
        }

@app.post("/memory/delete")
async def delete_memory(request: MemoryDeleteRequest):
    if not request.user_id or not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id不能为空")

    tenant_id = request.tenant_id or "default"

    try:
        session_deleted = bridge.session_mem.delete(request.user_id, tenant_id)
        graph_deleted = bridge.graph_mem.delete_user_data(tenant_id)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "session_deleted": session_deleted,
                "graph_deleted": graph_deleted
            }
        }
    except Exception as e:
        logger.error(f"记忆删除失败：{str(e)}")
        return {
            "code": 500,
            "message": f"删除失败：{str(e)}",
            "data": None
        }

@app.get("/memory/sessions/{tenant_id}")
async def list_sessions(tenant_id: str):
    try:
        sessions = bridge.session_mem.list_sessions(tenant_id)
        return {
            "code": 0,
            "message": "success",
            "data": {
                "tenant_id": tenant_id,
                "session_count": len(sessions),
                "sessions": sessions
            }
        }
    except Exception as e:
        logger.error(f"会话列表获取失败：{str(e)}")
        return {
            "code": 500,
            "message": f"获取失败：{str(e)}",
            "data": None
        }

if __name__ == "__main__":
    import uvicorn
    port = int(validate_config("PORT", "8000"))
    workers = int(validate_config("WORKERS", "4"))
    uvicorn.run(
        "local_main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        timeout_graceful_shutdown=30
    )