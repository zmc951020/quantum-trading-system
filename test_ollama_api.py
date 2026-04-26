import json
import requests
import os

# 测试Ollama API直接调用
def test_ollama_api():
    print("Testing Ollama API directly...")
    
    # 获取MemX-Ollama目录的README.md路径
    memx_ollama_dir = os.path.join(os.getcwd(), "MemX-Ollama")
    readme_path = os.path.join(memx_ollama_dir, "README.md")
    print(f"Looking for README.md at: {readme_path}")
    
    # 检查文件是否存在
    if not os.path.exists(readme_path):
        print(f"README.md not found at: {readme_path}")
        # 尝试列出MemX-Ollama目录的内容
        if os.path.exists(memx_ollama_dir):
            print("Contents of MemX-Ollama directory:")
            for item in os.listdir(memx_ollama_dir):
                print(f"  - {item}")
        return
    
    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file from the local filesystem",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]
    
    # 发送请求到Ollama API
    url = "http://127.0.0.1:11434/api/chat"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "qwen2.5:0.5b",
        "messages": [
            {
                "role": "user",
                "content": f"Please read the file at: {readme_path}"
            }
        ],
        "tools": tools,
        "tool_choice": "auto"
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        
        # 处理流式响应
        response_text = response.text
        print("Ollama API response text:")
        print(response_text)
        
        # 尝试解析每一行JSON
        lines = response_text.strip().split('\n')
        for line in lines:
            if line:
                try:
                    result = json.loads(line)
                    print("\nParsed JSON:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    # 检查是否需要工具调用
                    if "tool_calls" in result and result["tool_calls"]:
                        tool_call = result["tool_calls"][0]
                        if tool_call["function"]["name"] == "file_read":
                            # 尝试解析arguments
                            arguments = tool_call["function"]["arguments"]
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)
                            file_path = arguments.get("file_path")
                            print(f"\nOllama requested to read file: {file_path}")
                            
                            # 模拟工具执行
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                # 将工具执行结果发送回Ollama
                                tool_response_data = {
                                    "model": "qwen2.5:0.5b",
                                    "messages": [
                                        {
                                            "role": "user",
                                            "content": f"Please read the file at: {readme_path}"
                                        },
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "tool_calls": [tool_call]
                                        },
                                        {
                                            "role": "tool",
                                            "tool_call_id": tool_call["id"],
                                            "name": "file_read",
                                            "content": json.dumps({
                                                "content": content,
                                                "size": len(content),
                                                "path": file_path
                                            })
                                        }
                                    ]
                                }
                                
                                tool_response = requests.post(url, headers=headers, data=json.dumps(tool_response_data), timeout=30)
                                tool_response.raise_for_status()
                                tool_response_text = tool_response.text
                                print("\nOllama response after tool execution:")
                                print(tool_response_text)
                                
                            except Exception as e:
                                print(f"Error reading file: {e}")
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    print(f"Line: {line}")
        
    except Exception as e:
        print(f"Error calling Ollama API: {e}")

if __name__ == "__main__":
    test_ollama_api()
