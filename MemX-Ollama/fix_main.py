import logging
import uuid
import asyncio
import re
import ollama
from ollama import Tool
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from memx import OllamaMemXBridge, validate_config
from memx.auth import (
    get_current_user,
    get_permission_manager,
    require_permission,
    User,
    Role,
    Permission,
    PermissionManager,
    get_tenant_manager,
    Tenant,
    ApprovalRequest,
    get_analytics
)
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task, get_current_task
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bridge: Optional[OllamaMemXBridge] = None
tool_manager = get_tool_manager()

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge
    logger.info("正在初始化Ollama MemX Bridge...")
    try:
        # 启动监控指标服务
        from memx.auth import setup_metrics
        setup_metrics()
        
        bridge = OllamaMemXBridge()
        logger.info("Ollama MemX Bridge初始化成功")
    except Exception as e:
        logger.error(f"Ollama MemX Bridge初始化失败：{str(e)}")
        raise
    yield
    if bridge:
        await bridge.close()
        logger.info("Ollama MemX Bridge已关闭")

app = FastAPI(
    title="Ollama MemX API",
    description="Ollama永久记忆系统工业级API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "memx-api", "timestamp": time.time()}

@app.get("/")
async def root():
    return {
        "message": "Ollama MemX API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.post("/test/chat/noauth")
async def test_chat_noauth(request: ChatRequest):
    """测试Ollama聊天功能（不需要认证）"""
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt不能为空")

    if not request.user_id or not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id不能为空")

    request_id = str(uuid.uuid4())
    tenant_id = request.tenant_id or "default"

    logger.info(f"收到测试聊天请求，用户：{request.user_id}，租户：{tenant_id}，请求ID：{request_id}")

    # 创建任务上下文
    task = {
        "task_id": request_id,
        "user_id": request.user_id,
        "tenant_id": tenant_id
    }

    try:
        # 设置线程本地存储
        set_current_task(task)
        
        # 获取工具管理器
        tool_mgr = get_tool_manager()
        
        # 定义工具，使用Ollama SDK的Tool类
        file_read_tool = Tool(
            type="function",
            function={
                "name": "file_read",
                "description": "读取文件内容，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要读取的文件路径"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        )
        
        directory_list_tool = Tool(
            type="function",
            function={
                "name": "directory_list",
                "description": "列出目录内容，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "要列出的目录路径"
                        }
                    },
                    "required": ["directory"]
                }
            }
        )
        
        # 工具执行的安全回调
        async def tool_handler(name: str, args: dict) -> Any:
            task = get_current_task()
            if not task:
                raise PermissionError("无任务上下文，拒绝执行工具")
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            logger.info(f"工具调用: {name}, 参数: {args}, 任务: {task_id}")
            
            if name == "file_read":
                result = await tool_mgr.handle_tool_call("file_read", args)
                logger.info(f"文件读取结果：{result}")
                return result
            elif name == "directory_list":
                result = await tool_mgr.handle_tool_call("directory_list", args)
                logger.info(f"目录列出结果：{result}")
                return result
            else:
                logger.warning(f"未知工具：{name}")
                return {"error": "unknown_tool", "message": f"未知工具: {name}"}
        
        # 调用Ollama原生Chat，传入工具和回调
        logger.info(f"调用Ollama，prompt: {request.prompt}")
        response = await ollama.chat(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": request.prompt}],
            tools=[file_read_tool, directory_list_tool],
            tool_call_handler=tool_handler
        )
        
        logger.info(f"Ollama返回结果: {response['message']['content']}")
        return ChatResponse(
            code=0,
            message="success",
            data=response['message']['content'],
            memory_info={}
        )
    
    except Exception as e:
        logger.error(f"聊天请求处理失败：{str(e)}")
        return ChatResponse(
            code=500,
            message=f"服务器内部错误：{str(e)}",
            data=None,
            memory_info={}
        )
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    import uvicorn
    port = int(validate_config("PORT", "8000"))
    workers = int(validate_config("WORKERS", "4"))
    uvicorn.run(
        "fix_main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        timeout_graceful_shutdown=30
    )
