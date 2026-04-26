import logging
import asyncio
from memx.tools.manager import get_tool_manager
from memx.utils.context import set_current_task, clear_current_task

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_file_read():
    """测试文件读取功能"""
    try:
        # 创建任务上下文
        task = {
            "task_id": "test_task",
            "user_id": "test_user",
            "tenant_id": "default"
        }
        
        # 设置线程本地存储
        set_current_task(task)
        
        # 获取工具管理器
        tool_mgr = get_tool_manager()
        
        # 测试文件读取
        result = await tool_mgr.handle_tool_call("file_read", {"file_path": "README.md"})
        
        logger.info(f"文件读取结果: {result}")
        
        if "content" in result:
            logger.info(f"文件内容长度: {len(result['content'])} 字符")
            logger.info(f"文件内容预览: {result['content'][:100]}...")
        else:
            logger.error(f"文件读取失败: {result}")
            
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    asyncio.run(test_file_read())
