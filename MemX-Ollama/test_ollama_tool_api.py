import json
import urllib.request
import urllib.error
import logging
import uuid
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

def test_ollama_tool_call():
    """测试Ollama工具调用功能"""
    logger.info("测试Ollama工具调用功能")
    
    # 创建任务上下文
    task = {
        "task_id": str(uuid.uuid4()),
        "user_id": "admin",
        "tenant_id": "default"
    }
    
    # 设置线程本地存储
    set_current_task(task)
    
    # 获取工具管理器
    tool_mgr = get_tool_manager()
    
    # 定义工具
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
    }]
    
    try:
        # 调用Ollama API
        response = call_ollama_api({
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": "请读取当前目录下的README.md文件的内容，文件路径为README.md"}],
            "tools": tools,
            "stream": False
        })
        
        logger.info(f"Ollama响应: {response}")
        
        # 检查响应是否为字符串
        if isinstance(response, str):
            logger.error(f"Ollama返回了字符串而不是JSON: {response}")
            return response
        
        # 处理工具调用
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
                    # 调用真正的工具函数
                    import asyncio
                    result = asyncio.run(tool_mgr.handle_tool_call(
                        function_name,
                        {"file_path": file_path}
                    ))
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
                            {"role": "user", "content": "请读取README.md文件的内容"},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    # 检查响应是否为字符串
                    if isinstance(second_response, str):
                        logger.error(f"Ollama返回了字符串而不是JSON: {second_response}")
                        return "文件读取成功，但Ollama处理结果时超时"
                    
                    # 检查响应是否包含错误
                    if "error" in second_response:
                        logger.error(f"Ollama返回了错误: {second_response['error']}")
                        return f"文件读取成功，但Ollama处理结果时出错: {second_response['error']}"
                    
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
                        file_path = parameters.get("file_path")
                        if file_path:
                            # 调用真正的工具函数
                            import asyncio
                            result = asyncio.run(tool_mgr.handle_tool_call(
                                "file_read",
                                {"file_path": file_path}
                            ))
                            logger.info(f"工具执行结果: {result}")
                            
                            # 提取工具执行结果
                            tool_result = result.get("content", str(result))
                            
                            # 将工具执行结果发送回Ollama
                            second_response = call_ollama_api({
                                "model": "llama3.2:1b",
                                "messages": [
                                    {"role": "user", "content": "请读取README.md文件的内容"},
                                    {"role": "assistant", "content": content},
                                    {"role": "tool", "content": tool_result, "tool_call_id": "1"}
                                ],
                                "stream": False
                            })
                            
                            # 检查响应是否为字符串
                            if isinstance(second_response, str):
                                logger.error(f"Ollama返回了字符串而不是JSON: {second_response}")
                                return second_response
                            
                            logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                            return second_response.get('message', {}).get('content', '')
            except json.JSONDecodeError:
                # 不是JSON，直接返回
                pass
            
            return content
    except Exception as e:
        logger.error(f"测试失败：{e}")
        return f"测试失败：{e}"
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    result = test_ollama_tool_call()
    print("测试结果:")
    print(result)

