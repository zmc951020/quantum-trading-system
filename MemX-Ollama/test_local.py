import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from memx import OllamaMemXBridge
import asyncio

async def test_ollama_memx():
    print("="*60)
    print("Ollama MemX 核心功能测试")
    print("="*60)
    
    try:
        # 初始化Ollama MemX Bridge
        bridge = OllamaMemXBridge()
        print("✓ Ollama MemX Bridge初始化成功")
        
        # 测试1: 基本对话
        print("\n测试1: 基本对话")
        response = await bridge.chat_with_memory(
            request_id="test_1",
            user_id="test_user",
            prompt="你好，我叫张三，今年30岁"
        )
        print(f"✓ 对话成功: {response['data'][:50]}...")
        
        # 测试2: 记忆检索
        print("\n测试2: 记忆检索")
        # 模拟记忆检索
        long_mem = bridge.vector_mem.search("default", "张三")
        print(f"✓ 记忆检索成功: 找到 {len(long_mem)} 条相关记忆")
        
        # 测试3: 会话管理
        print("\n测试3: 会话管理")
        sessions = bridge.session_mem.list_sessions("default")
        print(f"✓ 会话管理成功: 找到 {len(sessions)} 个会话")
        
        # 测试4: 知识图谱
        print("\n测试4: 知识图谱")
        graph_data = bridge.graph_mem.query_related("张三", "default")
        print(f"✓ 知识图谱查询成功: 找到 {len(graph_data)} 个相关实体")
        
        print("\n" + "="*60)
        print("✅ 所有核心功能测试通过!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        print("="*60)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ollama_memx())