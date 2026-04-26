#!/usr/bin/env python3
"""
调试参数提取
"""

import sys
import os
import re

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ollama_tool_config import ollama_tool_config

print("调试参数提取")
print("=" * 80)

request = "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站"
print(f"请求: {request}")
print()

# 提取URL
url_match = re.search(r'(https?://[^\s]+)', request)
if url_match:
    url = url_match.group(1)
    # 移除URL末尾的非URL字符
    url = re.sub(r'[^a-zA-Z0-9:/._-]+$', '', url)
    print(f"提取的URL: {url}")
    
    # 验证URL
    if ollama_tool_config.validate_url(url):
        print("URL验证成功！")
    else:
        print("URL验证失败！")
        
        # 看看哪些URL是允许的
        print()
        print("允许的URL:")
        allowed_urls = ollama_tool_config.security_config['allowed_urls']
        for allowed in allowed_urls:
            print(f"  - {allowed}")
else:
    print("没有找到URL")
