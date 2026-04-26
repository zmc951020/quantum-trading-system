#!/usr/bin/env python3
"""
综合功能验证测试
测试所有已集成的工具功能
"""

import logging
import asyncio
import json
import urllib.request
import urllib.error
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def call_memx_api(prompt, user_id="test_user"):
    """调用MemX API"""
    try:
        url = "http://localhost:8009/test/chat/noauth"
        data = {
            "user_id": user_id,
            "prompt": prompt
        }
        data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            response_text = response.read().decode('utf-8')
            return json.loads(response_text)
    except urllib.error.HTTPError as e:
        logger.error(f"MemX API调用失败：{str(e)}")
        return {"code": 500, "message": str(e), "data": None}
    except Exception as e:
        logger.error(f"MemX API调用失败：{str(e)}")
        return {"code": 500, "message": str(e), "data": None}

def call_ollama_api(prompt):
    """直接调用Ollama API"""
    try:
        url = "http://localhost:11434/api/chat"
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
                        }
                    },
                    "required": ["url"]
                }
            }
        }]
        data = {
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
            "stream": False
        }
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

async def test_file_read():
    """测试文件读取功能"""
    logger.info("\n测试文件读取功能")
    response = call_memx_api("请读取README.md文件的内容")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_file_write():
    """测试文件写入功能"""
    logger.info("\n测试文件写入功能")
    test_content = f"测试内容 {time.time()}"
    response = call_memx_api(f"请写入'{test_content}'到test_write.txt文件")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_directory_list():
    """测试目录列出功能"""
    logger.info("\n测试目录列出功能")
    response = call_memx_api("请列出当前目录的内容")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_browser_navigate():
    """测试浏览器导航功能"""
    logger.info("\n测试浏览器导航功能")
    response = call_memx_api("请打开新浪网")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_run_command():
    """测试命令执行功能"""
    logger.info("\n测试命令执行功能")
    response = call_memx_api("请执行python --version命令")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_take_screenshot():
    """测试截图功能"""
    logger.info("\n测试截图功能")
    response = call_memx_api("请对当前页面进行截图")
    logger.info(f"响应：{response}")
    return response.get("code") == 0

async def test_ollama_tool_call():
    """测试Ollama直接工具调用"""
    logger.info("\n测试Ollama直接工具调用")
    response = call_ollama_api("请打开新浪网")
    logger.info(f"Ollama响应：{response}")
    if "message" in response and "tool_calls" in response["message"]:
        logger.info("✅ Ollama正确生成了工具调用")
        return True
    else:
        logger.warning("❌ Ollama未能生成工具调用")
        return False

async def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "="*60)
    logger.info("综合功能验证测试")
    logger.info("="*60)

    tests = [
        ("文件读取", test_file_read),
        ("文件写入", test_file_write),
        ("目录列出", test_directory_list),
        ("浏览器导航", test_browser_navigate),
        ("命令执行", test_run_command),
        ("截图功能", test_take_screenshot),
        ("Ollama工具调用", test_ollama_tool_call),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            status = "✅ 通过" if result else "❌ 失败"
            logger.info(f"{test_name}: {status}")
        except Exception as e:
            logger.error(f"{test_name}测试失败: {e}")
            results.append((test_name, False))

    logger.info("\n" + "="*60)
    logger.info("测试结果汇总")
    logger.info("="*60)
    passed = 0
    total = len(results)
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1

    logger.info(f"\n通过: {passed}/{total}")
    logger.info(f"成功率: {passed/total*100:.1f}%")

    if passed == total:
        logger.info("🎉 所有测试通过！")
    else:
        logger.info("⚠️  部分测试失败，需要检查")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
