import ollama
import logging
import asyncio
import uuid
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def tool_handler(tool_call):
    """工具调用处理函数"""
    logger.info(f"收到工具调用: {tool_call}")
    
    # 提取工具名称和参数
    function_name = tool_call.function.name
    arguments = tool_call.function.arguments
    
    logger.info(f"工具名称: {function_name}, 参数: {arguments}")
    
    # 创建任务上下文
    task = {
        "task_id": str(uuid.uuid4()),
        "user_id": "admin",
        "tenant_id": "default"
    }
    
    # 设置线程本地存储
    set_current_task(task)
    
    try:
        # 获取工具管理器
        tool_mgr = get_tool_manager()
        
        # 调用工具
        if function_name == "file_read":
            result = await tool_mgr.handle_tool_call(
                function_name,
                arguments
            )
            logger.info(f"工具执行结果: {result}")
            
            # 提取工具执行结果
            tool_result = result.get("content", str(result))
            
            # 截断工具执行结果，避免过大导致Ollama处理超时
            if len(tool_result) > 1000:
                tool_result = tool_result[:1000] + "... (内容被截断)"
            
            return tool_result
        else:
            return f"未知工具: {function_name}"
    finally:
        # 清除任务上下文
        clear_current_task()

async def test_ollama_sdk_tool_call():
    """测试Ollama SDK工具调用功能"""
    logger.info("测试Ollama SDK工具调用功能")
    
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
        response = await ollama.chat(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "请读取当前目录下的README.md文件的内容，文件路径为README.md"}],
            tools=tools,
            tool_call_handler=tool_handler
        )
        
        logger.info(f"Ollama响应: {response}")
        
        # 提取响应内容
        content = response.get("message", {}).get("content", "")
        logger.info(f"Ollama最终结果: {content}")
        return content
    except Exception as e:
        logger.error(f"测试失败：{e}")
        return f"测试失败：{e}"

if __name__ == "__main__":
    result = asyncio.run(test_ollama_sdk_tool_call())
    print("测试结果:")
    print(result)
