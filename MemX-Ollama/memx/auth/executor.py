import logging
import subprocess
import os
from typing import Optional, Dict, Any
from .models import User, Permission
from .manager import PermissionManager

logger = logging.getLogger(__name__)

class PermissionExecutor:
    def __init__(self, permission_manager: PermissionManager):
        self.permission_manager = permission_manager
        self.allowed_commands = {
            "file_read": ["type", "cat"],
            "directory_list": ["dir", "ls"]
        }
    
    def execute_permission(self, user: User, permission: Permission, resource: str, **kwargs) -> Dict[str, Any]:
        """执行权限操作"""
        try:
            # 检查权限
            allowed, details = self.permission_manager.check_permission(
                user=user,
                permission=permission,
                tenant_id=user.tenant_id,
                resource_type="execution",
                resource_id=resource
            )
            
            if not allowed:
                return {
                    "success": False,
                    "error": "权限不足",
                    "details": details
                }
            
            # 根据权限类型执行操作
            if permission == Permission.FILE_OPERATIONS:
                return self._execute_file_operation(resource, **kwargs)
            elif permission == Permission.SYSTEM_ADMIN:
                return self._execute_system_operation(resource, **kwargs)
            else:
                return {
                    "success": False,
                    "error": "不支持的权限操作"
                }
        except Exception as e:
            logger.error(f"执行权限操作失败：{e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _execute_file_operation(self, resource: str, **kwargs) -> Dict[str, Any]:
        """执行文件操作"""
        operation = kwargs.get("operation")
        
        if operation == "read":
            return self._read_file(resource)
        elif operation == "list":
            return self._list_directory(resource)
        else:
            return {
                "success": False,
                "error": "不支持的文件操作"
            }
    
    def _read_file(self, file_path: str) -> Dict[str, Any]:
        """读取文件"""
        try:
            # 安全检查
            if not self._is_safe_path(file_path):
                return {
                    "success": False,
                    "error": "不安全的文件路径"
                }
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": "文件不存在"
                }
            
            # 检查文件大小
            if os.path.getsize(file_path) > 10 * 1024 * 1024:  # 10MB
                return {
                    "success": False,
                    "error": "文件过大"
                }
            
            # 读取文件
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            return {
                "success": True,
                "content": content
            }
        except Exception as e:
            logger.error(f"读取文件失败：{e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _list_directory(self, directory: str) -> Dict[str, Any]:
        """列出目录"""
        try:
            # 安全检查
            if not self._is_safe_path(directory):
                return {
                    "success": False,
                    "error": "不安全的目录路径"
                }
            
            # 检查目录是否存在
            if not os.path.isdir(directory):
                return {
                    "success": False,
                    "error": "目录不存在"
                }
            
            # 列出目录内容
            entries = []
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    entries.append(f"📄 {item}")
                elif os.path.isdir(item_path):
                    entries.append(f"📁 {item}")
            
            return {
                "success": True,
                "entries": entries
            }
        except Exception as e:
            logger.error(f"列出目录失败：{e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _execute_system_operation(self, command: str, **kwargs) -> Dict[str, Any]:
        """执行系统操作"""
        try:
            # 安全检查
            if not self._is_safe_command(command):
                return {
                    "success": False,
                    "error": "不安全的系统命令"
                }
            
            # 执行命令
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            logger.error(f"执行系统命令失败：{e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _is_safe_path(self, path: str) -> bool:
        """检查路径是否安全"""
        try:
            # 解析路径
            import pathlib
            path_obj = pathlib.Path(path).resolve()
            
            # 检查是否包含危险路径
            dangerous_patterns = ['..', '~', '/etc', '/proc', '/sys']
            for pattern in dangerous_patterns:
                if pattern in str(path_obj):
                    return False
            
            # 检查是否在允许的目录内
            allowed_dirs = [".", "data", "logs"]
            path_str = str(path_obj)
            for allowed_dir in allowed_dirs:
                if path_str.startswith(os.path.join(os.getcwd(), allowed_dir)):
                    return True
            
            return False
        except Exception:
            return False
    
    def _is_safe_command(self, command: str) -> bool:
        """检查命令是否安全"""
        # 只允许特定的安全命令
        safe_commands = ["dir", "ls", "echo", "date"]
        for safe_cmd in safe_commands:
            if command.startswith(safe_cmd):
                return True
        return False
