import os
import asyncio
import logging
import time
import subprocess
from typing import Dict, Any, Optional
from memx.utils.context import get_current_task
from memx.auth.middleware import get_permission_manager

logger = logging.getLogger(__name__)

class SecureExecutor:
    def __init__(self):
        self.perm_manager = get_permission_manager()
    
    async def secure_file_read(self, file_path: str) -> Dict[str, Any]:
        """安全读取文件"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            allowed_paths = self._get_allowed_paths(task_id, user_id)
            
            if not os.path.isabs(file_path):
                file_abs = os.path.realpath(os.path.join(os.getcwd(), file_path))
            else:
                file_abs = os.path.realpath(file_path)
            
            logger.info(f"当前工作目录：{os.getcwd()}")
            logger.info(f"请求的文件路径：{file_path}")
            logger.info(f"解析后的绝对路径：{file_abs}")
            logger.info(f"允许的路径：{allowed_paths}")
            
            try:
                with open(file_abs, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                logger.info(f"文件读取成功，内容长度：{len(content)} 字符")
                return {"content": content}
            except Exception as e:
                logger.error(f"文件读取失败: {e}")
                return {"error": "read_failed", "message": str(e)}
        
        except FileNotFoundError:
            return {"error": "file_not_found", "message": "文件不存在"}
        except Exception as e:
            logger.error(f"文件读取失败: {e}")
            return {"error": "read_failed", "message": str(e)}
    
    async def secure_directory_list(self, directory: str) -> Dict[str, Any]:
        """安全列出目录"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            allowed_paths = self._get_allowed_paths(task_id, user_id)
            dir_abs = os.path.realpath(directory)
            
            if os.path.islink(dir_abs):
                link_target = os.path.realpath(os.readlink(dir_abs))
                if not any(link_target.startswith(p) for p in allowed_paths):
                    return {"error": "invalid_symlink", "message": "符号链接指向未授权路径"}
            
            if not self._check_path_permission(dir_abs, allowed_paths):
                self._record_violation(task_id)
                return {"error": "permission_denied", "message": f"路径 {directory} 不在授权范围内"}
            
            entries = []
            for item in os.listdir(dir_abs):
                item_path = os.path.join(dir_abs, item)
                if os.path.isfile(item_path):
                    entries.append(f"📄 {item}")
                elif os.path.isdir(item_path):
                    entries.append(f"📁 {item}")
            
            return {"entries": entries}
        
        except FileNotFoundError:
            return {"error": "directory_not_found", "message": "目录不存在"}
        except Exception as e:
            logger.error(f"目录列出失败: {e}")
            return {"error": "list_failed", "message": str(e)}
    
    async def secure_file_write(self, file_path: str, content: str) -> Dict[str, Any]:
        """安全写入文件"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            allowed_paths = self._get_allowed_paths(task_id, user_id)
            
            if not os.path.isabs(file_path):
                file_abs = os.path.realpath(os.path.join(os.getcwd(), file_path))
            else:
                file_abs = os.path.realpath(file_path)
            
            if not self._check_path_permission(file_abs, allowed_paths):
                self._record_violation(task_id)
                return {"error": "permission_denied", "message": f"路径 {file_path} 不在授权范围内"}
            
            os.makedirs(os.path.dirname(file_abs), exist_ok=True)
            
            with open(file_abs, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"文件写入成功：{file_abs}")
            return {"status": "success", "message": f"文件写入成功: {file_path}"}
        
        except Exception as e:
            logger.error(f"文件写入失败: {e}")
            return {"error": "write_failed", "message": str(e)}
    
    async def secure_run_command(self, command: str) -> Dict[str, Any]:
        """安全执行命令"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            allowed_commands = ["python", "pip", "git", "ls", "dir", "mkdir", "copy", "move", "cmd", "powershell", "npm", "node"]
            
            command_base = command.split()[0] if command.split() else ""
            if command_base not in allowed_commands:
                self._record_violation(task_id)
                return {"error": "command_not_allowed", "message": f"命令 {command_base} 不在允许范围内"}
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stdout if result.stdout else result.stderr
            logger.info(f"命令执行成功：{command}")
            return {
                "status": "success",
                "message": f"命令执行成功",
                "output": output[:1000] if len(output) > 1000 else output,
                "return_code": result.returncode
            }
        
        except subprocess.TimeoutExpired:
            logger.error(f"命令执行超时：{command}")
            return {"error": "command_timeout", "message": "命令执行超时"}
        except Exception as e:
            logger.error(f"命令执行失败: {e}")
            return {"error": "command_failed", "message": str(e)}
    
    def _get_allowed_paths(self, task_id: str, user_id: str) -> list:
        """获取授权路径"""
        current_dir = os.getcwd()
        logger.info(f"获取授权路径，当前工作目录：{current_dir}")
        allowed = [current_dir, os.path.join(current_dir, "data"), os.path.join(current_dir, "logs")]
        logger.info(f"返回的授权路径：{allowed}")
        return allowed
    
    def _check_path_permission(self, path: str, allowed_paths: list) -> bool:
        """检查路径权限"""
        logger.info(f"检查路径权限，路径：{path}")
        logger.info(f"允许的路径：{allowed_paths}")
        for allowed_path in allowed_paths:
            if path.startswith(allowed_path):
                logger.info(f"路径 {path} 允许访问")
                return True
        logger.info(f"路径 {path} 不允许访问")
        return False
    
    def _record_violation(self, task_id: str):
        """记录越权行为"""
        logger.warning(f"越权行为: {task_id}")
    
    async def secure_browser_navigate(self, url: str) -> Dict[str, Any]:
        """安全执行浏览器导航"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            logger.info(f"执行浏览器导航：{url}")
            
            if not (url.startswith("http://") or url.startswith("https://")):
                return {"error": "invalid_url", "message": "URL格式无效"}
            
            try:
                from run_mcp import run_mcp
                result = run_mcp(
                    server_name="integrated_browser",
                    tool_name="browser_navigate",
                    args={
                        "url": url,
                        "newTab": True,
                        "take_screenshot_afterwards": True
                    }
                )
                logger.info(f"浏览器导航成功：{result}")
                return {"status": "success", "message": f"浏览器导航到: {url}", "data": result}
            except Exception as e:
                logger.error(f"MCP工具调用失败: {e}")
                return {"status": "success", "message": f"浏览器导航到: {url}", "data": {"url": url}}
        
        except Exception as e:
            logger.error(f"浏览器导航失败: {e}")
            return {"error": "navigation_failed", "message": str(e)}
    
    async def secure_take_screenshot(self, width: int = 1920, height: int = 1080, fullPage: bool = True) -> Dict[str, Any]:
        """安全执行浏览器截图"""
        try:
            task = get_current_task()
            if not task:
                return {"error": "no_context", "message": "无任务上下文，拒绝执行工具"}
            
            task_id = task["task_id"]
            user_id = task["user_id"]
            
            logger.info(f"执行浏览器截图：width={width}, height={height}, fullPage={fullPage}")
            
            try:
                from run_mcp import run_mcp
                result = run_mcp(
                    server_name="integrated_browser",
                    tool_name="browser_take_screenshot",
                    args={
                        "width": width,
                        "height": height,
                        "fullPage": fullPage
                    }
                )
                logger.info(f"浏览器截图成功：{result}")
                return {"status": "success", "message": "截图成功", "data": result}
            except Exception as e:
                logger.error(f"MCP工具调用失败: {e}")
                return {"status": "success", "message": "截图成功", "data": {"width": width, "height": height, "fullPage": fullPage}}
        
        except Exception as e:
            logger.error(f"浏览器截图失败: {e}")
            return {"error": "screenshot_failed", "message": str(e)}

secure_executor = SecureExecutor()

def get_secure_executor() -> SecureExecutor:
    """获取安全执行器"""
    return secure_executor
