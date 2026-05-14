#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端口管理模块
用于检测和管理系统端口使用情况
"""

import socket
from typing import List, Tuple


class PortManager:
    """端口管理器"""

    def __init__(self, preferred_ports: List[int] = None):
        if preferred_ports is None:
            self.preferred_ports = [5000, 8000, 8080, 5001, 5002, 3000]
        else:
            self.preferred_ports = preferred_ports

    def is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False

    def get_available_port(self, start_port: int = 5000) -> int:
        """获取可用的端口号"""
        for port in range(start_port, start_port + 100):
            if self.is_port_available(port):
                return port
        raise RuntimeError("无法找到可用端口")

    def check_port_range(self, start: int, end: int) -> List[Tuple[int, bool]]:
        """检查端口范围内的可用性"""
        results = []
        for port in range(start, end + 1):
            results.append((port, self.is_port_available(port)))
        return results

    def find_best_port(self) -> int:
        """找到最佳可用端口"""
        for port in self.preferred_ports:
            if self.is_port_available(port):
                return port
        return self.get_available_port()


_global_port_manager = None

def get_port_manager() -> PortManager:
    """获取全局端口管理器实例"""
    global _global_port_manager
    if _global_port_manager is None:
        _global_port_manager = PortManager()
    return _global_port_manager


if __name__ == '__main__':
    pm = get_port_manager()
    print("端口管理器测试")
    print(f"端口 5000 可用: {pm.is_port_available(5000)}")
    print(f"端口 5001 可用: {pm.is_port_available(5001)}")
    print(f"最佳可用端口: {pm.find_best_port()}")
