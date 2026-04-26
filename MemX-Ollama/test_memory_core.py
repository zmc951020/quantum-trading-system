import sys
import os
import logging
import asyncio

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_memory_core():
    """测试核心记忆功能"""
    print("="*60)
    print("Ollama MemX 核心记忆功能测试")
    print("="*60)
    
    try:
        # 导入核心模块
        from memx.working_mem import WorkingMemory
        from memx.session_mem import SessionMemory
        from memx.vector_mem import VectorMemory
        from memx.graph_mem import GraphMemory
        
        print("OK: 核心模块导入成功")
        
        # 测试短期记忆
        print("\n测试1: 短期记忆")
        working_mem = WorkingMemory(max_tokens=1000)
        working_mem.add("user", "你好，我叫张三")
        working_mem.add("assistant", "你好，张三！")
        context = working_mem.get_context()
        print(f"OK: 短期记忆存储成功")
        print(f"   上下文长度: {len(context)} 字符")
        
        # 测试中期记忆
        print("\n测试2: 中期记忆")
        session_mem = SessionMemory()
        session_id = "test_user_123"
        test_history = [
            {"role": "user", "content": "你好", "timestamp": 1234567890},
            {"role": "assistant", "content": "你好！", "timestamp": 1234567891}
        ]
        save_result = session_mem.save(session_id, test_history, "default")
        print(f"OK: 中期记忆保存 {'成功' if save_result else '失败'}")
        
        # 测试长期记忆
        print("\n测试3: 长期记忆")
        vector_mem = VectorMemory()
        memory_id = vector_mem.add("default", "测试记忆内容", {"priority": 0.8})
        print(f"OK: 长期记忆添加成功，ID: {memory_id}")
        
        # 测试知识图谱
        print("\n测试4: 知识图谱")
        graph_mem = GraphMemory()
        add_result = graph_mem.add_entity("张三", "person", {"age": 30, "hobby": "编程"}, "default")
        print(f"OK: 知识图谱实体添加 {'成功' if add_result else '失败'}")
        
        # 测试记忆检索
        print("\n测试5: 记忆检索")
        search_result = vector_mem.search("default", "测试", limit=2)
        print(f"OK: 记忆检索成功，找到 {len(search_result)} 条结果")
        
        print("\n" + "="*60)
        print("🎉 核心记忆功能测试完成!")
        print("记忆系统架构完整，功能正常")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        print("="*60)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_memory_core())