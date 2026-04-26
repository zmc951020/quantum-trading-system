#!/usr/bin/env python3
"""
Ollama多工具调用综合测试
测试所有已集成的工具：file_read, file_write, directory_list, browser_navigate, run_command
"""

import logging
import asyncio
import json
import urllib.request
import urllib.error

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

def get_all_tools():
    """获取所有工具定义"""
    return [{
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取文件内容",
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
            "name": "directory_list",
            "description": "列出目录内容",
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
            "description": "写入内容到文件",
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
                    }
                },
                "required": ["command"]
            }
        }
    }]

async def test_tool(tool_name, prompt, args):
    """测试单个工具"""
    logger.info(f"\n{'='*60}")
    logger.info(f"测试工具: {tool_name}")
    logger.info(f"提示词: {prompt}")
    logger.info(f"{'='*60}")

    tools = get_all_tools()

    response = call_ollama_api({
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": prompt}],
        "tools": tools,
        "stream": False
    })

    logger.info(f"Ollama响应: {response}")

    if "message" in response and "tool_calls" in response["message"]:
        tool_calls = response["message"]["tool_calls"]
        logger.info(f"收到工具调用: {tool_calls}")

        for tool_call in tool_calls:
            if tool_call["function"]["name"] == tool_name:
                logger.info(f"✅ Ollama正确识别了{tool_name}工具")
                return True

    logger.warning(f"❌ Ollama未能识别{tool_name}工具")
    return False

async def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "="*60)
    logger.info("Ollama多工具调用综合测试")
    logger.info("="*60)

    tests = [
        ("file_read", "请读取README.md文件的内容", {"file_path": "README.md"}),
        ("directory_list", "请列出当前目录的内容", {"directory": "."}),
        ("browser_navigate", "请打开新浪网", {"url": "https://www.sina.com.cn"}),
        ("file_write", "请写入'测试内容'到test.txt文件", {"file_path": "test.txt", "content": "测试内容"}),
        ("run_command", "请执行python --version命令", {"command": "python --version"}),
    ]

    results = []
    for tool_name, prompt, args in tests:
        result = await test_tool(tool_name, prompt, args)
        results.append((tool_name, result))

    logger.info("\n" + "="*60)
    logger.info("测试结果汇总")
    logger.info("="*60)
    for tool_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{tool_name}: {status}")

    passed = sum(1 for _, r in results if r)
    logger.info(f"\n通过: {passed}/{len(results)}")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
