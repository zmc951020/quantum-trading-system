#!/usr/bin/env python3
"""
Ollama工具调用配置
定义工具调用的触发机制和流程
"""

import json
from typing import Dict, List, Any

class OllamaToolConfig:
    """
    Ollama工具调用配置类
    """
    
    def __init__(self):
        """
        初始化工具配置
        """
        # 工具调用触发规则
        self.trigger_rules = {
            "browser": {
                "patterns": [
                    r"打开.*网站",
                    r"访问.*网址",
                    r"浏览.*页面",
                    r"查看.*网页",
                    r"导航到.*",
                    r"搜索.*",
                    r"打开.*网",
                    r"访问.*网",
                ],
                "tool": "browser_navigate",
                "params": {
                    "url": "${url}",
                    "newTab": True,
                    "take_screenshot_afterwards": True
                }
            },
            "file_read": {
                "patterns": [
                    r"读取.*文件",
                    r"查看.*文件",
                    r"检查.*文件",
                    r"读取.*代码",
                    r"查看.*代码",
                    r"读取文件.*",
                    r"查看文件.*",
                    r"读取.*",
                    r"查看.*",
                ],
                "tool": "Read",
                "params": {
                    "file_path": "${file_path}"
                }
            },
            "file_write": {
                "patterns": [
                    r"写入.*文件",
                    r"创建.*文件",
                    r"修改.*文件",
                    r"更新.*文件",
                ],
                "tool": "Write",
                "params": {
                    "file_path": "${file_path}",
                    "content": "${content}"
                }
            },
            "run_command": {
                "patterns": [
                    r"运行.*命令",
                    r"执行.*命令",
                    r"启动.*服务",
                    r"测试.*代码",
                ],
                "tool": "RunCommand",
                "params": {
                    "command": "${command}",
                    "target_terminal": "new",
                    "command_type": "short_running_process",
                    "blocking": True,
                    "requires_approval": False
                }
            },
            "skill": {
                "patterns": [
                    r"使用.*技能",
                    r"激活.*技能",
                    r"运行.*技能",
                    r"执行.*技能",
                ],
                "tool": "Skill",
                "params": {
                    "name": "${skill_name}"
                }
            },
            "intelligent_module": {
                "patterns": [
                    r"使用.*模块",
                    r"激活.*模块",
                    r"运行.*模块",
                    r"执行.*模块",
                ],
                "tool": "IntelligentModule",
                "params": {
                    "name": "${module_name}"
                }
            },
            "adaptive_mode": {
                "patterns": [
                    r"激活.*自动化自适应模式",
                    r"启动.*自动化自适应模式",
                    r"开启.*自动化自适应模式",
                    r"让.*激活自动化自适应模式",
                ],
                "tool": "AdaptiveMode",
                "params": {
                    "mode": "automated"
                }
            }
        }
        
        # 工具调用流程
        self.tool_flow = {
            "browser": [
                "解析用户请求，提取URL",
                "验证URL合法性",
                "调用browser_navigate工具",
                "处理返回结果",
                "向用户展示结果"
            ],
            "file_read": [
                "解析用户请求，提取文件路径",
                "验证文件路径合法性",
                "调用Read工具",
                "处理返回结果",
                "向用户展示文件内容"
            ],
            "file_write": [
                "解析用户请求，提取文件路径和内容",
                "验证文件路径合法性",
                "调用Write工具",
                "处理返回结果",
                "向用户确认操作结果"
            ],
            "run_command": [
                "解析用户请求，提取命令",
                "验证命令合法性",
                "调用RunCommand工具",
                "处理返回结果",
                "向用户展示命令执行结果"
            ],
            "skill": [
                "解析用户请求，提取技能名称",
                "验证技能是否可用",
                "调用Skill工具",
                "处理返回结果",
                "向用户展示技能执行结果"
            ],
            "intelligent_module": [
                "解析用户请求，提取模块名称",
                "验证模块是否可用",
                "调用IntelligentModule工具",
                "处理返回结果",
                "向用户展示模块执行结果"
            ],
            "adaptive_mode": [
                "解析用户请求，确认激活命令",
                "验证模式参数",
                "调用AdaptiveMode工具",
                "处理返回结果",
                "向用户确认模式激活"
            ]
        }
        
        # 安全控制配置（极大权限）
        self.security_config = {
            "allowed_paths": [
                "d:\\",
                "c:\\"
            ],
            "allowed_commands": [
                "python",
                "pip",
                "git",
                "ls",
                "dir",
                "mkdir",
                "copy",
                "move",
                "cmd",
                "powershell",
                "npm",
                "yarn",
                "cmake",
                "make",
                "gcc",
                "g++"
            ],
            "allowed_urls": [
                "https://*",
                "http://*"
            ],
            "max_file_size": 10485760,  # 10MB
            "max_command_output": 100000,  # 100000字符
            "enable_skills": True,  # 启用技能
            "enable_intelligent_modules": True,  # 启用智能模块
            "enable_auto_start": True,  # 启用开机自启
            "enable_auto_trigger": True,  # 启用自动触发
            "enable_underlying_logic": True,  # 启用底层逻辑技能激发
            "max_permission": True  # 最大权限
        }
    
    def get_trigger_rules(self) -> Dict[str, Any]:
        """
        获取工具调用触发规则
        
        Returns:
            触发规则字典
        """
        return self.trigger_rules
    
    def get_tool_flow(self) -> Dict[str, List[str]]:
        """
        获取工具调用流程
        
        Returns:
            工具调用流程字典
        """
        return self.tool_flow
    
    def get_security_config(self) -> Dict[str, Any]:
        """
        获取安全配置
        
        Returns:
            安全配置字典
        """
        return self.security_config
    
    def validate_path(self, path: str) -> bool:
        """
        验证路径是否在允许范围内
        
        Args:
            path: 要验证的路径
            
        Returns:
            是否在允许范围内
        """
        # 转换路径为小写，忽略大小写
        path_lower = path.lower()
        for allowed_path in self.security_config["allowed_paths"]:
            allowed_path_lower = allowed_path.lower()
            if path_lower.startswith(allowed_path_lower):
                return True
        return False
    
    def validate_command(self, command: str) -> bool:
        """
        验证命令是否在允许范围内
        
        Args:
            command: 要验证的命令
            
        Returns:
            是否在允许范围内
        """
        for allowed_command in self.security_config["allowed_commands"]:
            if command.startswith(allowed_command):
                return True
        return False
    
    def validate_url(self, url: str) -> bool:
        """
        验证URL是否在允许范围内
        
        Args:
            url: 要验证的URL
            
        Returns:
            是否在允许范围内
        """
        # 简化处理：由于我们设置了极大权限，允许所有http和https的URL
        if url.startswith("http://") or url.startswith("https://"):
            return True
        return False

# 创建配置实例
ollama_tool_config = OllamaToolConfig()

# 导出配置
def export_config() -> Dict[str, Any]:
    """
    导出配置
    
    Returns:
        配置字典
    """
    return {
        "trigger_rules": ollama_tool_config.get_trigger_rules(),
        "tool_flow": ollama_tool_config.get_tool_flow(),
        "security_config": ollama_tool_config.get_security_config()
    }

if __name__ == "__main__":
    # 测试配置
    config = export_config()
    print(json.dumps(config, indent=2, ensure_ascii=False))
