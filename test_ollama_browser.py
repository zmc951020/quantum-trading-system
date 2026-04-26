#!/usr/bin/env python3
"""
测试Ollama浏览器工具调用功能
"""

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

async def test_ollama_browser_tool():
    """测试Ollama浏览器工具调用功能"""
    logger.info("开始测试Ollama浏览器工具调用功能")
    
    # 定义工具
    tools = [{
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
    }]
    
    # 调用Ollama API
    response = call_ollama_api({
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "请打开新浪网"}],
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
            if function_name == "browser_navigate":
                url = arguments.get("url", "https://www.sina.com.cn")
                logger.info(f"尝试导航到: {url}")
                
                # 模拟浏览器导航结果
                tool_result = f"浏览器已成功导航到: {url}"
                
                # 将工具执行结果发送回Ollama
                second_response = call_ollama_api({
                    "model": "llama3.2:1b",
                    "messages": [
                        {"role": "user", "content": "请打开新浪网"},
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
        return content

if __name__ == "__main__":
    result = asyncio.run(test_ollama_browser_tool())
    print("测试结果:")
    print(result)
