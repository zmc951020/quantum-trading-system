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

async def test_tool_manager():
    """测试工具管理器的功能"""
    logger.info("开始测试工具管理器")
    
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
        
        # 测试文件读取工具
        logger.info("测试文件读取工具")
        result = await tool_mgr.handle_tool_call(
            "file_read",
            {"file_path": "README.md"}
        )
        
        logger.info(f"文件读取结果: {result}")
        
        if "content" in result:
            print("测试成功！")
            print("文件内容:")
            print(result["content"])
        else:
            print("测试失败！")
            print(f"错误信息: {result.get('message', '未知错误')}")
            
    except Exception as e:
        logger.error(f"测试失败：{e}")
        print(f"测试失败：{e}")
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    print("测试工具管理器的功能")
    print("=" * 50)
    asyncio.run(test_tool_manager())
