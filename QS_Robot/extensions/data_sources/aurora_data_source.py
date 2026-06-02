
import os
import sys
import requests
from .base_data_source import BaseDataSource
from config.config import config

class AuroraDataSource(BaseDataSource):
    """Aurora量化系统数据源"""
    
    name = "aurora"
    description = "Aurora量化交易系统"
    
    def __init__(self, config_dict=None):
        """初始化Aurora数据源"""
        self.config = config_dict or {}
        self.base_path = self.config.get("base_path", config.get("aurora_system.base_path"))
        self.api_base = self.config.get("web_api_base", config.get("aurora_system.web_api_base", "http://localhost:5000"))
        self.session = requests.Session()
        self._connected = False
    
    def connect(self):
        """尝试连接Aurora系统"""
        try:
            # 先测试Web API
            resp = self.session.get(f"{self.api_base}/", timeout=3, allow_redirects=True)
            if resp.status_code in [200, 302, 404]:
                # 即使是404也说明服务在运行
                self._connected = True
                print(f"[OK] 已连接到Aurora系统: {self.api_base}")
                return True
            
            # 如果Web API不行，尝试检查路径是否存在
            if os.path.exists(self.base_path):
                print(f"[OK] 找到Aurora系统路径: {self.base_path}")
                self._connected = True
                return True
            
            return False
        except Exception as e:
            print(f"[WARNING] 连接Aurora系统失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self._connected = False
        self.session.close()
    
    def is_connected(self):
        """检查是否已连接"""
        return self._connected
    
    def get_data(self, query):
        """获取数据（目前是占位实现，未来完善）"""
        data_type = query.get("type", "")
        
        if data_type == "strategies":
            return self._get_strategies()
        elif data_type == "health":
            return self._get_health_status()
        else:
            return {"status": "not_implemented", "message": f"类型 {data_type} 尚未实现"}
    
    def _get_strategies(self):
        """获取策略列表（占位）"""
        return {
            "strategies": [
                {"name": "Shepherd V5", "status": "active"},
                {"name": "Shepherd V6", "status": "active"},
                {"name": "Adaptive Grid", "status": "active"}
            ],
            "total": 3
        }
    
    def _get_health_status(self):
        """获取健康状态（占位）"""
        return {
            "status": "healthy",
            "timestamp": "now"
        }
    
    def send_command(self, command, params):
        """发送命令（占位实现）"""
        return {
            "status": "not_implemented",
            "command": command,
            "params": params
        }

