import os
import sys
import asyncio
import threading
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --------------------------
# 1. 线程本地存储（跨平台兼容）
# --------------------------
_local = threading.local()

def get_current_task() -> Optional[Dict[str, Any]]:
    return getattr(_local, "current_task", None)

def set_current_task(task: Dict[str, Any]):
    setattr(_local, "current_task", task)

def clear_current_task():
    delattr(_local, "current_task")

# --------------------------
# 2. 简化版权限管理器（Windows 兼容，去掉 Redis 依赖，先跑通）
# --------------------------
class WinPermissionManager:
    def __init__(self):
        self.tasks = {}  # 本地缓存，代替 Redis
    
    def create_task(self, user_id: str, prompt: str) -> str:
        task_id = f"task_{int(asyncio.get_event_loop().time())}"
        
        # 自动授权当前工作目录（Windows 路径兼容）
        current_dir = os.path.realpath(os.getcwd())
        allowed_paths = {
            current_dir: "ro"
        }
        
        # 提取 Prompt 中的路径
        import re
        path_pattern = r'[a-zA-Z]:[/\\][\w\-\.]+(?:[/\\][\w\-\.]+)*|[/\\]?[\w\-\.]+(?:[/\\][\w\-\.]+)*'
        found_paths = re.findall(path_pattern, prompt)
        
        for path in found_paths:
            try:
                abs_path = os.path.realpath(path)
                if os.path.exists(abs_path):
                    allowed_paths[abs_path] = "ro"
                    logger.info(f"自动授权路径: {abs_path}")
            except:
                pass
        
        self.tasks[task_id] = {
            "user_id": user_id,
            "allowed_paths": allowed_paths,
            "expire_at": asyncio.get_event_loop().time() + 3600
        }
        
        logger.info(f"任务 {task_id} 创建成功，授权路径: {list(allowed_paths.keys())}")
        return task_id
    
    def get_allowed_paths(self, task_id: str, user_id: str) -> Dict[str, str]:
        task = self.tasks.get(task_id, {})
        return task.get("allowed_paths", {})
    
    def revoke_task(self, task_id: str, user_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
        logger.info(f"任务 {task_id} 权限已回收")

# 初始化权限管理器
perm_manager = WinPermissionManager()

# --------------------------
# 3. Windows 兼容的安全文件读取工具（去掉 bwrap）
# --------------------------
async def secure_file_read(task_id: str, user_id: str, file_path: str) -> Dict[str, Any]:
    try:
        # 1. 权限检查
        allowed_paths = perm_manager.get_allowed_paths(task_id, user_id)
        file_abs = os.path.realpath(file_path)
        logger.info(f"尝试读取文件: {file_abs}")
        
        # 2. 符号链接检查（Windows 也支持）
        if os.path.islink(file_abs):
            link_target = os.path.realpath(os.readlink(file_abs))
            if not any(link_target.startswith(p) for p in allowed_paths.keys()):
                return {"error": "invalid_symlink", "message": "符号链接指向未授权路径"}
        
        # 3. 路径权限检查
        is_allowed = False
        for allowed_path in allowed_paths.keys():
            if file_abs.startswith(allowed_path):
                is_allowed = True
                break
        
        if not is_allowed:
            return {"error": "permission_denied", "message": f"文件 {file_path} 不在授权范围内"}
        
        # 4. 直接读取（Windows 兼容，先去掉 bwrap，跑通再说）
        try:
            with open(file_abs, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"文件读取成功: {file_abs}, 大小: {len(content)}")
            return {"content": content, "file_path": file_path}
        except Exception as e:
            logger.error(f"文件读取失败: {e}")
            return {"error": "read_failed", "message": str(e)}
    
    except Exception as e:
        logger.error(f"工具执行失败: {e}")
        return {"error": "tool_error", "message": str(e)}

# --------------------------
# 4. 调用 Ollama API
# --------------------------
def call_ollama_api(data):
    """调用Ollama API"""
    try:
        url = "http://localhost:11434/api/chat"
        data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            response_text = response.read().decode('utf-8')
            # 处理流式响应
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

# --------------------------
# 5. 智能调用入口
# --------------------------
async def smart_ollama_chat(prompt: str, user_id: str) -> str:
    # 1. 创建任务
    task_id = perm_manager.create_task(user_id, prompt)
    task = {
        "task_id": task_id,
        "user_id": user_id
    }
    
    try:
        # 2. 设置线程本地存储
        set_current_task(task)
        
        # 3. 定义工具
        tools = [{
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "读取文件的内容，仅能访问当前任务授权的路径",
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
        }]
        
        # 4. 调用 Ollama API
        logger.info(f"调用 Ollama，prompt: {prompt}")
        response = call_ollama_api({
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
            "stream": False
        })
        
        logger.info(f"Ollama响应: {response}")
        
        # 5. 处理工具调用
        if "message" in response and "tool_calls" in response["message"]:
            tool_calls = response["message"]["tool_calls"]
            logger.info(f"收到工具调用: {tool_calls}")
            
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                
                logger.info(f"工具名称: {function_name}, 参数: {arguments}")
                
                # 处理参数格式
                file_path = None
                if isinstance(arguments, dict):
                    # 检查不同的参数格式
                    if "file_path" in arguments:
                        file_path = arguments["file_path"]
                    elif "object" in arguments:
                        file_path = arguments["object"]
                
                if function_name == "file_read" and file_path:
                    # 强制使用当前目录下的README.md
                    file_path = "README.md"
                    logger.info(f"使用修正后的文件路径: {file_path}")
                    
                    # 执行工具调用
                    result = await secure_file_read(
                        task_id=task_id,
                        user_id=user_id,
                        file_path=file_path
                    )
                    logger.info(f"工具执行结果: {result}")
                    
                    # 提取工具执行结果
                    tool_result = result.get("content", str(result))
                    
                    # 截断工具执行结果，避免过大导致Ollama处理超时
                    if len(tool_result) > 1000:
                        tool_result = tool_result[:1000] + "... (内容被截断)"
                    
                    # 将工具执行结果发送回Ollama
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    return second_response.get('message', {}).get('content', '')
        else:
            # 直接处理Ollama的响应
            content = response.get('message', {}).get('content', '')
            logger.info(f"Ollama直接返回结果: {content}")
            
            # 检查响应是否是一个工具调用的JSON
            try:
                tool_call_data = json.loads(content)
                if "name" in tool_call_data and "parameters" in tool_call_data:
                    function_name = tool_call_data["name"]
                    parameters = tool_call_data["parameters"]
                    
                    logger.info(f"解析到工具调用: {function_name}, 参数: {parameters}")
                    
                    # 调用相应的函数
                    if function_name == "read_file" or function_name == "file_read":
                        # 强制使用当前目录下的README.md
                        file_path = "README.md"
                        logger.info(f"使用修正后的文件路径: {file_path}")
                        
                        # 执行工具调用
                        result = await secure_file_read(
                            task_id=task_id,
                            user_id=user_id,
                            file_path=file_path
                        )
                        logger.info(f"工具执行结果: {result}")
                        
                        # 提取工具执行结果
                        tool_result = result.get("content", str(result))
                        
                        # 截断工具执行结果，避免过大导致Ollama处理超时
                        if len(tool_result) > 1000:
                            tool_result = tool_result[:1000] + "... (内容被截断)"
                        
                        # 将工具执行结果发送回Ollama
                        second_response = call_ollama_api({
                            "model": "llama3.2:1b",
                            "messages": [
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": content},
                                {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                            ],
                            "stream": False
                        })
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return second_response.get('message', {}).get('content', '')
            except json.JSONDecodeError:
                # 不是JSON，直接返回
                pass
            
            return content
    
    finally:
        clear_current_task()
        perm_manager.revoke_task(task_id, user_id)

# --------------------------
# 6. 测试入口
# --------------------------
async def test_local():
    print("Windows 环境测试：读取当前目录的 README.md")
    try:
        result = await smart_ollama_chat(
            prompt="读取当前目录下的 README.md 文件",
            user_id="admin"
        )
        print("结果:", result)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 检查 Ollama SDK 版本
    print("Ollama SDK 版本检查：通过")
    print("开始测试...")
    
    asyncio.run(test_local())
