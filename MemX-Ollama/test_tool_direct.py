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

async def test_tool_direct():
    """直接测试工具管理器的文件读取功能"""
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
        
        # 直接调用工具
        logger.info("直接测试文件读取工具")
        result = await tool_mgr.handle_tool_call(
            "file_read",
            {"file_path": "README.md"}
        )
        
        logger.info(f"工具执行结果: {result}")
        print("测试结果:")
        if "content" in result:
            print(result["content"])
        else:
            print(f"错误: {result.get('message', '未知错误')}")
    except Exception as e:
        logger.error(f"测试失败：{e}")
        print(f"测试失败：{e}")
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    asyncio.run(test_tool_direct())
