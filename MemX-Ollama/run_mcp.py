#!/usr/bin/env python3
"""
MCP工具调用封装
"""

def run_mcp(server_name, tool_name, args):
    """
    调用MCP工具
    
    Args:
        server_name: MCP服务器名称
        tool_name: 工具名称
        args: 工具参数
        
    Returns:
        工具执行结果
    """
    try:
        # 导入run_mcp函数
        from trae.tools import run_mcp as trae_run_mcp
        return trae_run_mcp(server_name, tool_name, args)
    except Exception as e:
        # 如果导入失败，返回错误信息
        return {"error": str(e)}
