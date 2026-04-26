import asyncio
import logging
import ollama
from ollama import Tool
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task
import uuid

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_ollama_tool():
    """测试Ollama SDK的工具调用功能"""
    try:
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
        
        # 调用Ollama原生Chat，传入工具和回调
        logger.info("调用Ollama，测试文件读取工具")
        response = await ollama.chat(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "读取当前目录下的README.md文件"}],
            tools=tool_mgr.get_ollama_tools(),
            tool_call_handler=tool_mgr.handle_tool_call
        )
        
        logger.info(f"Ollama返回结果: {response['message']['content']}")
        print("测试结果:", response['message']['content'])
    except Exception as e:
        logger.error(f"测试失败：{e}")
        print(f"测试失败：{e}")
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    asyncio.run(test_ollama_tool())
