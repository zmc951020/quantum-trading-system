import json
import urllib.request
import urllib.error
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def call_api(endpoint, data):
    """调用API"""
    try:
        url = f"http://localhost:8000{endpoint}"
        data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            response_text = response.read().decode('utf-8')
            return json.loads(response_text)
    except urllib.error.HTTPError as e:
        logger.error(f"API调用失败：{str(e)}")
        return {"error": "api_error", "message": str(e)}
    except Exception as e:
        logger.error(f"API调用失败：{str(e)}")
        return {"error": "api_error", "message": str(e)}

def test_chat_noauth():
    """测试无认证聊天接口"""
    logger.info("测试无认证聊天接口")
    
    # 测试工具调用
    response = call_api("/test/chat/noauth", {
        "user_id": "test_user",
        "prompt": "读取当前目录下的 README.md 文件"
    })
    
    logger.info(f"API响应: {response}")
    
    if "code" in response and response["code"] == 0:
        print("测试成功！")
        print(f"响应数据: {response['data']}")
    else:
        print("测试失败！")
        print(f"错误信息: {response.get('message', '未知错误')}")

def test_chat():
    """测试聊天接口"""
    logger.info("测试聊天接口")
    
    # 测试工具调用
    response = call_api("/test/chat", {})
    
    logger.info(f"API响应: {response}")
    
    if "code" in response and response["code"] == 0:
        print("测试成功！")
        print(f"响应数据: {response['data']}")
    else:
        print("测试失败！")
        print(f"错误信息: {response.get('message', '未知错误')}")

if __name__ == "__main__":
    print("测试main.py中的工具调用功能")
    print("=" * 50)
    
    # 测试无认证聊天接口
    print("\n测试1: 无认证聊天接口")
    print("-" * 30)
    test_chat_noauth()
    
    # 测试聊天接口
    print("\n测试2: 聊天接口")
    print("-" * 30)
    test_chat()
