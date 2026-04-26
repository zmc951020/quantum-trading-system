import os
import logging
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class FileTools:
    def __init__(self):
        self.allowed_extensions = [
            '.txt', '.md', '.json', '.yaml', '.yml', 
            '.csv', '.log', '.config', '.ini'
        ]
        self.max_file_size = 10 * 1024 * 1024  # 10MB
    
    def is_safe_path(self, path: str) -> bool:
        """检查路径是否安全"""
        try:
            # 解析路径
            path_obj = Path(path).resolve()
            
            # 检查是否包含危险路径
            dangerous_patterns = ['..', '~', '/etc', '/proc', '/sys']
            for pattern in dangerous_patterns:
                if pattern in str(path_obj):
                    return False
            
            # 检查文件扩展名
            ext = path_obj.suffix.lower()
            if ext not in self.allowed_extensions:
                return False
            
            return True
        except Exception as e:
            logger.error(f"路径安全检查失败: {e}")
            return False
    
    def read_file(self, file_path: str) -> Optional[str]:
        """安全读取文件内容"""
        try:
            # 安全检查
            if not self.is_safe_path(file_path):
                logger.warning(f"不安全的文件路径: {file_path}")
                return None
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.warning(f"文件不存在: {file_path}")
                return None
            
            # 检查文件大小
            if os.path.getsize(file_path) > self.max_file_size:
                logger.warning(f"文件过大: {file_path}")
                return None
            
            # 读取文件
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            logger.info(f"成功读取文件: {file_path}")
            return content
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return None
    
    def list_directory(self, directory: str) -> Optional[List[str]]:
        """安全列出目录内容"""
        try:
            # 安全检查
            if not self.is_safe_path(directory):
                logger.warning(f"不安全的目录路径: {directory}")
                return None
            
            # 检查目录是否存在
            if not os.path.isdir(directory):
                logger.warning(f"目录不存在: {directory}")
                return None
            
            # 列出目录内容
            entries = []
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    entries.append(f"📄 {item}")
                elif os.path.isdir(item_path):
                    entries.append(f"📁 {item}")
            
            logger.info(f"成功列出目录: {directory}")
            return entries
        except Exception as e:
            logger.error(f"列出目录失败: {e}")
            return None
