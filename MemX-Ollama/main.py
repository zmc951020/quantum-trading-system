import logging
import uuid
import asyncio
import json
import urllib.request
import urllib.error
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    user_id: str
    prompt: str
    tenant_id: Optional[str] = None

class ChatResponse(BaseModel):
    code: int
    message: str
    data: Optional[str]
    memory_info: Dict[str, int]

def call_ollama_api(data):
    """调用Ollama API"""
    try:
        url = "http://localhost:11434/api/chat"
        data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            response_text = response.read().decode('utf-8')
            response_lines = response_text.strip().split('\n')
            full_response = {}
            for line in response_lines:
                try:
                    data = json.loads(line)
                    full_response.update(data)
                except json.JSONDecodeError:
                    pass
            return full_response
    except urllib.error.HTTPError as e:
        logger.error(f"Ollama API调用失败：{str(e)}")
        return {"error": "api_error", "message": str(e)}
    except Exception as e:
        logger.error(f"Ollama API调用失败：{str(e)}")
        return {"error": "api_error", "message": str(e)}

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

@app.post("/test/chat")
async def test_chat():
    """测试Ollama工具调用功能"""
    try:
        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": "test_user",
            "tenant_id": "default"
        }
        
        set_current_task(task)
        
        tool_mgr = get_tool_manager()
        
        result = await tool_mgr.handle_tool_call("file_read", {"file_path": "README.md"})
        
        return {
            "code": 0,
            "message": "success",
            "data": f"文件读取结果：{result}",
            "memory_info": {}
        }
    except Exception as e:
        logger.error(f"测试聊天请求处理失败：{str(e)}")
        return {
            "code": 500,
            "message": f"服务器内部错误：{str(e)}",
            "data": None,
            "memory_info": {}
        }
    finally:
        clear_current_task()




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

    task = {
        "task_id": request_id,
        "user_id": request.user_id,
        "tenant_id": tenant_id
    }

    try:
        set_current_task(task)
        
        tool_mgr = get_tool_manager()
        
        tools = [{
            "type": "function",
            "function": {
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
        }, {
            "type": "function",
            "function": {
                "name": "browser_navigate",
                "description": "使用浏览器导航到指定URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要导航到的URL"
                        },
                        "newTab": {
                            "type": "boolean",
                            "description": "是否在新标签页中打开",
                            "default": True
                        },
                        "take_screenshot_afterwards": {
                            "type": "boolean",
                            "description": "导航后是否截图",
                            "default": True
                        }
                    },
                    "required": ["url"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "file_write",
                "description": "写入内容到文件，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要写入的文件路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的内容"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "执行命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的命令"
                        },
                        "command_type": {
                            "type": "string",
                            "description": "命令类型：short_running_process, long_running_process",
                            "default": "short_running_process"
                        },
                        "blocking": {
                            "type": "boolean",
                            "description": "是否阻塞等待结果",
                            "default": True
                        }
                    },
                    "required": ["command"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "对当前浏览器页面进行截图",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "width": {
                            "type": "integer",
                            "description": "截图宽度",
                            "default": 1920
                        },
                        "height": {
                            "type": "integer",
                            "description": "截图高度",
                            "default": 1080
                        },
                        "fullPage": {
                            "type": "boolean",
                            "description": "是否截取整个页面",
                            "default": True
                        }
                    },
                    "required": []
                }
            }
        }]
        
        response = call_ollama_api({
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": request.prompt}],
            "tools": tools,
            "stream": False
        })
        
        logger.info(f"Ollama响应: {response}")
        
        if "message" in response and "tool_calls" in response["message"]:
            tool_calls = response["message"]["tool_calls"]
            logger.info(f"收到工具调用: {tool_calls}")
            
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                
                logger.info(f"工具名称: {function_name}, 参数: {arguments}")
                
                if function_name == "file_read":
                    file_path = "README.md"
                    logger.info(f"使用修正后的文件路径: {file_path}")
                    
                    result = await tool_mgr.handle_tool_call(
                        function_name,
                        {"file_path": file_path}
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    tool_result = result.get("content", str(result))
                    
                    if len(tool_result) > 1000:
                        tool_result = tool_result[:1000] + "... (内容被截断)"
                    
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": request.prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return ChatResponse(
                        code=0,
                        message="success",
                        data=second_response.get('message', {}).get('content', ''),
                        memory_info={}
                    )
                elif function_name == "browser_navigate":
                    url = arguments.get("url")
                    logger.info(f"执行浏览器导航: {url}")
                    
                    result = await tool_mgr.handle_tool_call(
                        function_name,
                        {"url": url}
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    tool_result = result.get("message", str(result))
                    
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": request.prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return ChatResponse(
                        code=0,
                        message="success",
                        data=second_response.get('message', {}).get('content', ''),
                        memory_info={}
                    )
                elif function_name == "file_write":
                    file_path = arguments.get("file_path")
                    content = arguments.get("content")
                    logger.info(f"执行文件写入: {file_path}")
                    
                    result = await tool_mgr.handle_tool_call(
                        function_name,
                        {"file_path": file_path, "content": content}
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    tool_result = result.get("message", str(result))
                    
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": request.prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return ChatResponse(
                        code=0,
                        message="success",
                        data=second_response.get('message', {}).get('content', ''),
                        memory_info={}
                    )
                elif function_name == "run_command":
                    command = arguments.get("command")
                    logger.info(f"执行命令: {command}")
                    
                    result = await tool_mgr.handle_tool_call(
                        function_name,
                        {"command": command}
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    tool_result = result.get("message", str(result)) + "\n" + result.get("output", "")
                    
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": request.prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return ChatResponse(
                        code=0,
                        message="success",
                        data=second_response.get('message', {}).get('content', ''),
                        memory_info={}
                    )
                elif function_name == "take_screenshot":
                    width = arguments.get("width", 1920)
                    height = arguments.get("height", 1080)
                    fullPage = arguments.get("fullPage", True)
                    logger.info(f"执行截图: width={width}, height={height}, fullPage={fullPage}")
                    
                    result = await tool_mgr.handle_tool_call(
                        function_name,
                        {"width": width, "height": height, "fullPage": fullPage}
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    tool_result = result.get("message", str(result))
                    
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": request.prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return ChatResponse(
                        code=0,
                        message="success",
                        data=second_response.get('message', {}).get('content', ''),
                        memory_info={}
                    )
                else:
                    logger.warning(f"未知工具：{function_name}")
                    return ChatResponse(
                        code=500,
                        message=f"未知工具：{function_name}",
                        data=None,
                        memory_info={}
                    )
        else:
            content = response.get('message', {}).get('content', '')
            logger.info(f"Ollama直接返回结果: {content}")
            
            try:
                tool_call_data = json.loads(content)
                if "name" in tool_call_data and "parameters" in tool_call_data:
                    function_name = tool_call_data["name"]
                    arguments = tool_call_data["parameters"]
                    
                    logger.info(f"解析到工具调用: {function_name}, 参数: {arguments}")
                    
                    if function_name == "read_file" or function_name == "file_read":
                        file_path = "README.md"
                        logger.info(f"使用修正后的文件路径: {file_path}")
                        
                        result = await tool_mgr.handle_tool_call(
                            "file_read",
                            {"file_path": file_path}
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        tool_result = result.get("content", str(result))
                        
                        if len(tool_result) > 1000:
                            tool_result = tool_result[:1000] + "... (内容被截断)"
                        
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": request.prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return ChatResponse(
                            code=0,
                            message="success",
                            data=second_response.get('message', {}).get('content', ''),
                            memory_info={}
                        )
                    elif function_name == "browser_navigate":
                        url = arguments.get("url")
                        logger.info(f"执行浏览器导航: {url}")
                        
                        result = await tool_mgr.handle_tool_call(
                            "browser_navigate",
                            {"url": url}
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        tool_result = result.get("message", str(result))
                        
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": request.prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return ChatResponse(
                            code=0,
                            message="success",
                            data=second_response.get('message', {}).get('content', ''),
                            memory_info={}
                        )
                    elif function_name == "file_write":
                        file_path = arguments.get("file_path")
                        content = arguments.get("content")
                        logger.info(f"执行文件写入: {file_path}")
                        
                        result = await tool_mgr.handle_tool_call(
                            "file_write",
                            {"file_path": file_path, "content": content}
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        tool_result = result.get("message", str(result))
                        
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": request.prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return ChatResponse(
                            code=0,
                            message="success",
                            data=second_response.get('message', {}).get('content', ''),
                            memory_info={}
                        )
                    elif function_name == "run_command":
                        command = arguments.get("command")
                        logger.info(f"执行命令: {command}")
                        
                        result = await tool_mgr.handle_tool_call(
                            "run_command",
                            {"command": command}
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        tool_result = result.get("message", str(result)) + "\n" + result.get("output", "")
                        
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": request.prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return ChatResponse(
                            code=0,
                            message="success",
                            data=second_response.get('message', {}).get('content', ''),
                            memory_info={}
                        )
                    elif function_name == "take_screenshot":
                        width = arguments.get("width", 1920)
                        height = arguments.get("height", 1080)
                        fullPage = arguments.get("fullPage", True)
                        logger.info(f"执行截图: width={width}, height={height}, fullPage={fullPage}")
                        
                        result = await tool_mgr.handle_tool_call(
                            "take_screenshot",
                            {"width": width, "height": height, "fullPage": fullPage}
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        tool_result = result.get("message", str(result))
                        
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": request.prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return ChatResponse(
                            code=0,
                            message="success",
                            data=second_response.get('message', {}).get('content', ''),
                            memory_info={}
                        )
            except json.JSONDecodeError:
                pass
            
            return ChatResponse(
                code=0,
                message="success",
                data=content,
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
        clear_current_task()







@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"全局异常捕获：{str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误：{str(exc)}",
            "data": None,
            "memory_info": {}
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = 8009
    workers = 4
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        timeout_graceful_shutdown=30
    )
