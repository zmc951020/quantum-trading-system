import time
from typing import Dict

class HealthService:
    """健康服务"""
    
    def __init__(self):
        self.start_time = time.time()
        self.services = {
            "risk_service": "healthy",
            "performance_service": "healthy",
            "portfolio_service": "healthy",
            "database": "healthy",
            "redis": "healthy"
        }
    
    def get_status(self) -> Dict:
        """获取服务健康状态"""
        uptime = time.time() - self.start_time
        
        return {
            "status": "healthy",
            "uptime": uptime,
            "services": self.services,
            "timestamp": time.time()
        }
    
    def get_metrics(self) -> Dict:
        """获取健康指标"""
        return {
            "cpu_usage": 0.25,  # 模拟CPU使用率
            "memory_usage": 0.4,  # 模拟内存使用率
            "disk_usage": 0.3,  # 模拟磁盘使用率
            "api_response_time": 0.1,  # 模拟API响应时间
            "error_rate": 0.01  # 模拟错误率
        }
