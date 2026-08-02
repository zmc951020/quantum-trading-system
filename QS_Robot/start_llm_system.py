#!/usr/bin/env python3
"""
QS Robot LLM系统启动脚本

功能:
1. 初始化LLM管理器
2. 注册Trae集成
3. 初始化Cline命令行接口
4. 启动桌面应用或命令行模式
"""

import sys
import os

# 添加QS Robot路径
QS_ROBOT_PATH = os.path.dirname(os.path.abspath(__file__))
if QS_ROBOT_PATH not in sys.path:
    sys.path.insert(0, QS_ROBOT_PATH)

def init_llm_system():
    """初始化LLM系统"""
    print("🚀 正在初始化QS Robot LLM系统...")
    
    # 初始化LLM管理器
    from llm_manager import llm_manager
    
    # 注册Trae集成
    from extensions.trae_integration import trae_integration, init_cline
    trae_integration.set_llm_manager(llm_manager)
    trae_integration.register_to_trae()
    
    # 初始化Cline集成
    init_cline(llm_manager)
    
    print("✅ LLM系统初始化完成")
    return llm_manager

def run_cli_mode():
    """运行命令行模式"""
    from extensions.trae_integration import cline_integration
    
    print("\n" + "="*50)
    print("🤖 QS Robot LLM命令行工具")
    print("="*50)
    print("输入 'llm help' 查看帮助")
    print("输入 'exit' 退出")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = input(">>> ")
            if cmd.lower() in ['exit', 'quit']:
                print("👋 再见!")
                break
            
            if cmd.lower().startswith('llm '):
                result = cline_integration.execute_command(cmd[4:])
                print(result)
            elif cmd:
                print(f"未知命令: {cmd}，输入 'llm help' 查看帮助")
                
        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {str(e)}")

def run_gui_mode():
    """运行图形界面模式"""
    from qs_robot_desktop_v2 import QSRobotDesktopV2
    
    app = QSRobotDesktopV2()
    app.root.mainloop()

def main():
    """主入口"""
    # 初始化LLM系统
    llm_manager = init_llm_system()
    
    # 检查运行模式
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        run_cli_mode()
    else:
        run_gui_mode()

if __name__ == "__main__":
    main()