
from abc import ABC, abstractmethod

class BaseDataSource(ABC):
    """数据源基类 - 定义与外部系统通信的标准接口"""
    
    name = "base_data_source"
    description = "基类数据源"
    
    @abstractmethod
    def __init__(self, config=None):
        """
        初始化数据源
        
        Args:
            config: 配置字典
        """
        pass
    
    @abstractmethod
    def connect(self):
        """建立连接"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def is_connected(self):
        """检查是否已连接"""
        pass
    
    @abstractmethod
    def get_data(self, query):
        """
        获取数据
        
        Args:
            query: 查询参数
        
        Returns:
            Any: 查询结果
        """
        pass
    
    @abstractmethod
    def send_command(self, command, params):
        """
        发送命令到系统
        
        Args:
            command: 命令名称
            params: 命令参数
        
        Returns:
            Any: 执行结果
        """
        pass

