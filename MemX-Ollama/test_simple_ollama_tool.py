import asyncio
import logging
import ollama
from memx.utils.context import set_current_task, clear_current_task
import uuid

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
        
        # 可用函数映射
        available_functions = {
            'file_read': file_read,
        }
        
        # 调用Ollama原生Chat，传入工具
        logger.info("调用Ollama，测试文件读取工具")
        response = ollama.chat(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "读取当前目录下的README.md文件"}],
            tools=[file_read],  # 直接传递函数
        )
        
        logger.info(f"Ollama响应: {response}")
        
        # 处理工具调用
        if hasattr(response.message, 'tool_calls') and response.message.tool_calls:
            logger.info(f"收到工具调用: {response.message.tool_calls}")
            
            for tool_call in response.message.tool_calls:
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments
                
                logger.info(f"工具名称: {function_name}, 参数: {arguments}")
                
                # 调用相应的函数
                if function_name in available_functions:
                    function_to_call = available_functions[function_name]
                    result = function_to_call(**arguments)
                    logger.info(f"工具执行结果: {result}")
                    
                    # 将工具执行结果发送回Ollama
                    second_response = ollama.chat(
                        model="llama3.2:1b",
                        messages=[
                            {"role": "user", "content": "读取当前目录下的README.md文件"},
                            {"role": "assistant", "content": "", "tool_calls": response.message.tool_calls},
                            {"role": "tool", "content": str(result), "tool_call_id": tool_call.id}
                        ]
                    )
                    
                    logger.info(f"Ollama最终结果: {second_response.message.content}")
                    print("测试结果:", second_response.message.content)
                else:
                    logger.warning(f"未知工具：{function_name}")
        else:
            logger.info(f"Ollama直接返回结果: {response.message.content}")
            print("测试结果:", response.message.content)
    except Exception as e:
        logger.error(f"测试失败：{e}")
        print(f"测试失败：{e}")
    finally:
        # 清除任务上下文
        clear_current_task()

if __name__ == "__main__":
    asyncio.run(test_ollama_tool())

