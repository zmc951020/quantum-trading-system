import logging
import urllib.request
import urllib.error
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模拟工具执行函数
def file_read(file_path: str) -> dict:
    """读取文件内容，仅能访问授权路径
    
    Args:
        file_path: 要读取的文件路径
    
    Returns:
        包含文件内容的字典
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        logger.info(f"文件读取成功：{file_path}")
        return {"content": content, "file_path": file_path}
    except Exception as e:
        logger.error(f"文件读取失败：{e}")
        return {"error": "read_failed", "message": str(e)}
def call_ollama_api(data):
    """调用Ollama API"""
    try:
        url = "http://localhost:11434/api/chat"
        data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
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
def test_ollama_tool():
    """测试Ollama API的工具调用功能"""
    try:
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
        
        # 调用Ollama API
        logger.info("调用Ollama，测试文件读取工具")
        response = call_ollama_api({
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": "读取当前目录下的README.md文件"}],
            "tools": tools,
            "stream": False
        })
        
        logger.info(f"Ollama响应: {response}")
        
        # 处理工具调用
        if "message" in response and "tool_calls" in response["message"]:
            tool_calls = response["message"]["tool_calls"]
            logger.info(f"收到工具调用: {tool_calls}")
            
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                
                logger.info(f"工具名称: {function_name}, 参数: {arguments}")
                
                # 调用相应的函数
                if function_name == "file_read":
                    result = file_read(arguments["file_path"])
                    logger.info(f"工具执行结果: {result}")
                    
                    # 将工具执行结果发送回Ollama
                    second_response = call_ollama_api({
                        "model": "llama3.2:1b",
                        "messages": [
                            {"role": "user", "content": "读取当前目录下的README.md文件"},
                            {"role": "assistant", "content": "", "tool_calls": tool_calls},
                            {"role": "tool", "content": str(result), "tool_call_id": tool_call["id"]}
                        ],
                        "stream": False
                    })
                    
                    logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                    print("测试结果:", second_response.get('message', {}).get('content', ''))
                else:
                    logger.warning(f"未知工具：{function_name}")
        else:
            logger.info(f"Ollama直接返回结果: {response.get('message', {}).get('content', '')}")
            print("测试结果:", response.get('message', {}).get('content', ''))
    except Exception as e:
        logger.error(f"测试失败：{e}")
        print(f"测试失败：{e}")

if __name__ == "__main__":
    test_ollama_tool()
