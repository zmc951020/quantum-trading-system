#!/usr/bin/env python3
"""Cline命令行工具启动脚本"""

import sys
import os

QS_ROBOT_PATH = os.path.dirname(os.path.abspath(__file__))
if QS_ROBOT_PATH not in sys.path:
    sys.path.insert(0, QS_ROBOT_PATH)

from llm_manager import llm_manager
from extensions.trae_integration import init_cline, cline_integration

def main():
    print("\n" + "="*50)
    print("🤖 QS Robot LLM命令行工具")
    print("="*50)
    print("输入命令（如：help, list, status）")
    print("输入 'exit' 退出")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = input(">>> ").strip()
            
            if cmd.lower() in ['exit', 'quit']:
                print("👋 再见!")
                break
            
            if cmd:
                result = cline_integration.execute_command(cmd)
                print(result)
            
            print()
            
        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {str(e)}\n")

if __name__ == "__main__":
    init_cline(llm_manager)
    main()