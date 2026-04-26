import ollama
import asyncio
import traceback
import os

async def test_ollama():
    try:
        print("测试Ollama连接...")
        
        # 测试基本的生成功能
        print("测试generate功能...")
        response = await ollama.AsyncClient(host="http://localhost:11434").generate(
            model="llama3.2:1b",  # 使用已有的模型
            prompt="你好，我是测试",
            stream=False
        )
        print("生成结果:", response["response"])
        
        # 测试聊天功能
        print("测试chat功能...")
        chat_response = await ollama.AsyncClient(host="http://localhost:11434").chat(
            model="llama3.2:1b",  # 使用已有的模型
            messages=[{"role": "user", "content": "你好，我是测试"}]
        )
        print("聊天结果:", chat_response["message"]["content"])
        
        print("Ollama测试成功!")
    except Exception as e:
        print(f"Ollama测试失败: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # 设置环境变量，禁用代理
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""
    os.environ["ALL_PROXY"] = ""
    
    asyncio.run(test_ollama())