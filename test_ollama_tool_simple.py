import logging
import asyncio
import json
import urllib.request
import urllib.error

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

async def test_ollama_tool_calling():
    """测试Ollama工具调用功能"""
    logger.info("开始测试Ollama工具调用功能")
    
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
    response = call_ollama_api({
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "请读取README.md文件的内容"}],
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
            
            # 模拟工具执行
            if function_name == "file_read":
                file_path = arguments.get("file_path", "README.md")
                logger.info(f"尝试读取文件: {file_path}")
                
                # 模拟文件读取结果
                tool_result = "# 测试文件内容\n这是一个测试文件，用于测试Ollama的工具调用功能。"
                
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
                
                logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                return second_response.get('message', {}).get('content', '')
    else:
        # 直接处理Ollama的响应
        content = response.get('message', {}).get('content', '')
        logger.info(f"Ollama直接返回结果: {content}")
        
        # 检查响应是否包含JSON格式的工具调用
        if content.startswith('```json') and content.endswith('```'):
            json_content = content.strip('```json\n```')
            try:
                tool_call_data = json.loads(json_content)
                if "name" in tool_call_data and "parameters" in tool_call_data:
                    function_name = tool_call_data["name"]
                    parameters = tool_call_data["parameters"]
                    
                    logger.info(f"解析到JSON格式工具调用: {function_name}, 参数: {parameters}")
                    
                    # 模拟工具执行
                    if function_name == "file_read":
                        file_path = parameters.get("file_path", "README.md")
                        logger.info(f"尝试读取文件: {file_path}")
                        
                        # 模拟文件读取结果
                        tool_result = "# 测试文件内容\n这是一个测试文件，用于测试Ollama的工具调用功能。"
                        
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
                        
                        logger.info(f"Ollama最终结果: {second_response.get('message', {}).get('content', '')}")
                        return second_response.get('message', {}).get('content', '')
            except json.JSONDecodeError:
                logger.error("解析JSON失败")
                pass
        
        return content

if __name__ == "__main__":
    result = asyncio.run(test_ollama_tool_calling())
    print("测试结果:")
    print(result)
