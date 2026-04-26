import logging
import re
from typing import Optional, Dict, Any, Union, List, Tuple
from .secure_executor import get_secure_executor

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.secure_executor = get_secure_executor()
        self.permission_manager = None
        self.permissions = None
        self.tools = {
            "file_read": {
                "name": "file_read",
                "description": "读取文件内容，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要读取的文件路径"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            "directory_list": {
                "name": "directory_list",
                "description": "列出目录内容，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "要列出的目录路径"
                        }
                    },
                    "required": ["directory"]
                }
            },
            "browser_navigate": {
                "name": "browser_navigate",
                "description": "使用浏览器导航到指定URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要导航到的URL"
                        },
                        "newTab": {
                            "type": "boolean",
                            "description": "是否在新标签页中打开",
                            "default": True
                        },
                        "take_screenshot_afterwards": {
                            "type": "boolean",
                            "description": "导航后是否截图",
                            "default": True
                        }
                    },
                    "required": ["url"]
                }
            },
            "file_write": {
                "name": "file_write",
                "description": "写入内容到文件，仅能访问授权路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要写入的文件路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的内容"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            },
            "run_command": {
                "name": "run_command",
                "description": "执行命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的命令"
                        },
                        "command_type": {
                            "type": "string",
                            "description": "命令类型：short_running_process, long_running_process",
                            "default": "short_running_process"
                        },
                        "blocking": {
                            "type": "boolean",
                            "description": "是否阻塞等待结果",
                            "default": True
                        }
                    },
                    "required": ["command"]
                }
            },
            "take_screenshot": {
                "name": "take_screenshot",
                "description": "对当前浏览器页面进行截图",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "width": {
                            "type": "integer",
                            "description": "截图宽度",
                            "default": 1920
                        },
                        "height": {
                            "type": "integer",
                            "description": "截图高度",
                            "default": 1080
                        },
                        "fullPage": {
                            "type": "boolean",
                            "description": "是否截取整个页面",
                            "default": True
                        }
                    },
                    "required": []
                }
            }
        }
    
    def _get_permission_manager(self):
        """延迟导入权限管理器，避免循环导入"""
        if not self.permission_manager:
            from memx.auth import get_permission_manager
            self.permission_manager = get_permission_manager()
        return self.permission_manager
    
    def _get_permissions(self):
        """延迟导入权限枚举，避免循环导入"""
        if not self.permissions:
            from memx.auth.models import Permission
            self.permissions = Permission
        return self.permissions
    
    def get_ollama_tools(self) -> List[Dict[str, Any]]:
        """获取Ollama格式的工具列表"""
        ollama_tools = []
        for tool_name, tool_info in self.tools.items():
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_info["description"],
                    "parameters": tool_info["parameters"]
                }
            }
            ollama_tools.append(ollama_tool)
        return ollama_tools
    
    async def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """处理Ollama工具调用"""
        try:
            from memx.utils.context import get_current_task
            task = get_current_task()
            if not task:
                raise PermissionError("无任务上下文，拒绝执行工具")
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            logger.info(f"工具调用: {tool_name}, 参数: {args}, 任务: {task_id}")
            
            if tool_name == "file_read":
                result = await self.secure_executor.secure_file_read(args["file_path"])
                logger.info(f"文件读取结果：{result}")
                return result
            elif tool_name == "directory_list":
                result = await self.secure_executor.secure_directory_list(args["directory"])
                logger.info(f"目录列出结果：{result}")
                return result
            elif tool_name == "browser_navigate":
                result = await self.secure_executor.secure_browser_navigate(args["url"])
                logger.info(f"浏览器导航结果：{result}")
                return result
            elif tool_name == "file_write":
                result = await self.secure_executor.secure_file_write(args["file_path"], args["content"])
                logger.info(f"文件写入结果：{result}")
                return result
            elif tool_name == "run_command":
                result = await self.secure_executor.secure_run_command(args["command"])
                logger.info(f"命令执行结果：{result}")
                return result
            elif tool_name == "take_screenshot":
                result = await self.secure_executor.secure_take_screenshot(
                    args.get("width", 1920),
                    args.get("height", 1080),
                    args.get("fullPage", True)
                )
                logger.info(f"截图结果：{result}")
                return result
            else:
                logger.warning(f"未知工具：{tool_name}")
                return {"error": "unknown_tool", "message": f"未知工具: {tool_name}"}
        except Exception as e:
            logger.error(f"工具调用处理失败: {e}")
            return {"error": "tool_error", "message": str(e)}
    
    def analyze_request(self, request: str) -> Optional[Dict[str, Any]]:
        """分析用户请求，自动识别需要使用的工具"""
        analysis = {
            "needs_tool": False,
            "tool_name": None,
            "action": None,
            "parameters": {}
        }
        
        file_patterns = [
            (r"读取.*文件", "file_read"),
            (r"查看.*文件", "file_read"),
            (r"读取.*内容", "file_read"),
            (r"列出.*目录", "directory_list"),
            (r"查看.*目录", "directory_list")
        ]
        
        for pattern, action in file_patterns:
            if re.search(pattern, request, re.IGNORECASE):
                analysis["needs_tool"] = True
                analysis["tool_name"] = action
                
                path_patterns = [
                    r"文件\s*(.*?)(?:的|内容|$)",
                    r"目录\s*(.*?)(?:的|内容|$)",
                    r"路径\s*(.*?)(?:的|内容|$)"
                ]
                
                param_name = "file_path" if action == "file_read" else "directory"
                
                path_found = False
                
                current_dir_match = re.search(r"当前目录下的(.*?)(?:文件|$)", request, re.IGNORECASE)
                if current_dir_match:
                    path = current_dir_match.group(1).strip()
                    logger.info(f"从'当前目录下的'格式提取到路径：{path}")
                    analysis["parameters"][param_name] = path
                    logger.info(f"最终设置的{param_name}：{path}")
                    path_found = True
                else:
                    for path_pattern in path_patterns:
                        match = re.search(path_pattern, request, re.IGNORECASE)
                        if match:
                            path = match.group(1).strip()
                            logger.info(f"匹配到路径：{path}")
                            if "当前目录" in path:
                                file_name_match = re.search(r"当前目录(.*?)(?:文件|$)", request, re.IGNORECASE)
                                if file_name_match:
                                    path = file_name_match.group(1).strip()
                                    logger.info(f"提取到文件名：{path}")
                                else:
                                    path = "."
                                    logger.info("未提取到文件名，设置为：.")
                            analysis["parameters"][param_name] = path
                            logger.info(f"最终设置的{param_name}：{path}")
                            path_found = True
                            break
                
                if not path_found:
                    if action == "file_read":
                        analysis["parameters"][param_name] = "README.md"
                    else:
                        analysis["parameters"][param_name] = "."
                break
        
        return analysis

tool_manager = ToolManager()

def get_tool_manager() -> ToolManager:
    """获取工具管理器"""
    return tool_manager
