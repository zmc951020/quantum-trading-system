#!/usr/bin/env python3
"""
工具调用管理器
处理用户请求并触发相应的工具调用
"""

import re
import json
from typing import Dict, Any, Optional
from ollama_tool_config import ollama_tool_config
from tool_executor import tool_executor
from chain_executor import chain_executor

class ToolManager:
    """
    工具调用管理器
    """
    
    def __init__(self):
        """
        初始化工具管理器
        """
        self.config = ollama_tool_config
    
    def analyze_request(self, request: str) -> Optional[Dict[str, Any]]:
        """
        分析用户请求，确定是否需要调用工具
        
        Args:
            request: 用户请求
            
        Returns:
            工具调用信息，None表示不需要调用工具
        """
        # 遍历触发规则
        for tool_type, rule in self.config.get_trigger_rules().items():
            # 检查是否匹配触发模式
            for pattern in rule["patterns"]:
                match = re.search(pattern, request, re.IGNORECASE)
                if match:
                    # 提取参数
                    params = self._extract_params(request, rule["params"])
                    if params:
                        return {
                            "tool_type": tool_type,
                            "tool": rule["tool"],
                            "params": params,
                            "flow": self.config.get_tool_flow()[tool_type]
                        }
        return None
    
    def _extract_params(self, request: str, param_template: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        从请求中提取参数
        
        Args:
            request: 用户请求
            param_template: 参数模板
            
        Returns:
            提取的参数，None表示提取失败
        """
        params = {}
        
        for key, template in param_template.items():
            if template == "${url}":
                # 提取URL
                url_match = re.search(r'(https?://[^\s]+)', request)
                if url_match:
                    url = url_match.group(1)
                    # 移除URL末尾的非URL字符
                    url = re.sub(r'[^a-zA-Z0-9:/._-]+$', '', url)
                    if self.config.validate_url(url):
                        params[key] = url
                    else:
                        return None
                else:
                    # 处理网站名称，如"打开新浪网"
                    site_match = re.search(r'打开\s*(\w+)网|访问\s*(\w+)网', request)
                    if site_match:
                        # 找到第一个非空的匹配组
                        for i in range(1, 3):
                            if site_match.group(i):
                                site_name = site_match.group(i)
                                # 映射网站名称到URL
                                site_urls = {
                                    "新浪": "https://www.sina.com.cn",
                                    "百度": "https://www.baidu.com",
                                    "谷歌": "https://www.google.com",
                                    "知乎": "https://www.zhihu.com",
                                    "淘宝": "https://www.taobao.com"
                                }
                                if site_name in site_urls:
                                    params[key] = site_urls[site_name]
                                    break
                        else:
                            return None
                    else:
                        return None
            elif template == "${file_path}":
                # 提取文件路径
                # 首先尝试匹配引号包围的文件路径
                quoted_path_match = re.search(r'"([^"]+)"', request)
                if quoted_path_match:
                    path = quoted_path_match.group(1)
                    if '.' in path and any(drive in path for drive in [f"{chr(c)}:" for c in range(ord('A'), ord('Z')+1)] + [f"{chr(c)}:" for c in range(ord('a'), ord('z')+1)]):
                        if self.config.validate_path(path):
                            params[key] = path
                        else:
                            return None
                else:
                    # 更简单的方法：找到第一个以盘符开头的部分
                    # 首先找到所有可能的盘符开头
                    drive_letters = [f"{chr(c)}:" for c in range(ord('A'), ord('Z')+1)]
                    drive_letters.extend([f"{chr(c)}:" for c in range(ord('a'), ord('z')+1)])
                    
                    # 寻找包含盘符的部分
                    for drive in drive_letters:
                        if drive in request:
                            # 从盘符开始提取路径
                            path_start = request.index(drive)
                            # 找到路径的结束位置（文件扩展名之后）
                            path_end = request.find(' ', path_start)
                            if path_end == -1:
                                path_end = len(request)
                            # 提取路径
                            path = request[path_start:path_end].strip()
                            # 确保路径包含文件扩展名
                            if '.' in path:
                                if self.config.validate_path(path):
                                    params[key] = path
                                    break
                    else:
                        return None
            elif template == "${command}":
                # 提取命令
                # 更宽松的命令匹配
                command_match = re.search(r'运行\s*(.+)', request)
                if not command_match:
                    command_match = re.search(r'执行\s*(.+)', request)
                if command_match:
                    command = command_match.group(1).strip()
                    if self.config.validate_command(command):
                        params[key] = command
                    else:
                        return None
                else:
                    return None
            elif template == "${content}":
                # 提取内容（这里简化处理，实际可能需要更复杂的逻辑）
                params[key] = "内容占位符"
            elif template == "${skill_name}":
                # 提取技能名称
                skill_match = re.search(r'使用\s*(\w+)\s*技能|激活\s*(\w+)\s*技能|运行\s*(\w+)\s*技能|执行\s*(\w+)\s*技能', request)
                if skill_match:
                    # 找到第一个非空的匹配组
                    for i in range(1, 5):
                        if skill_match.group(i):
                            params[key] = skill_match.group(i)
                            break
                else:
                    return None
            elif template == "${module_name}":
                # 提取模块名称
                module_match = re.search(r'使用\s*(\w+)\s*模块|激活\s*(\w+)\s*模块|运行\s*(\w+)\s*模块|执行\s*(\w+)\s*模块', request)
                if module_match:
                    # 找到第一个非空的匹配组
                    for i in range(1, 5):
                        if module_match.group(i):
                            params[key] = module_match.group(i)
                            break
                else:
                    return None
            else:
                # 固定参数
                params[key] = template
        
        return params
    
    def execute_tool_call(self, tool_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用
        
        Args:
            tool_info: 工具调用信息
            
        Returns:
            工具调用结果
        """
        # 执行工具调用流程
        tool = tool_info["tool"]
        params = tool_info["params"]
        flow = tool_info["flow"]
        
        # 打印执行流程
        print(f"执行工具调用: {tool}")
        print(f"参数: {json.dumps(params, ensure_ascii=False)}")
        print("执行流程:")
        for step in flow:
            print(f"  - {step}")
        
        # 首先尝试使用链式执行器
        try:
            result = chain_executor.execute_with_chain(tool_info)
            # 检查是否使用了链式执行
            if "chain_executed" in result.get("data", {}) or "前置条件" in result.get("message", ""):
                return result
        except Exception as e:
            print(f"链式执行失败，使用普通执行: {e}")
        
        # 如果链式执行失败或不可用，使用普通工具执行器
        result = tool_executor.execute(tool_info)
        
        return result
    
    def process_request(self, request: str) -> Dict[str, Any]:
        """
        处理用户请求
        
        Args:
            request: 用户请求
            
        Returns:
            处理结果
        """
        # 分析请求
        tool_info = self.analyze_request(request)
        
        if tool_info:
            # 执行工具调用
            result = self.execute_tool_call(tool_info)
            return {
                "type": "tool_call",
                "tool_info": tool_info,
                "result": result
            }
        else:
            # 不需要工具调用，直接返回
            return {
                "type": "direct_response",
                "message": "不需要工具调用，直接响应"
            }

# 创建工具管理器实例
tool_manager = ToolManager()

if __name__ == "__main__":
    # 测试工具管理器
    test_requests = [
        "打开https://www.youtube.com/watch?v=R6fZR_9kmIw网站",
        "读取d:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py文件",
        "运行python strategies/test_all_grid_strategies.py命令"
    ]
    
    for request in test_requests:
        print(f"\n测试请求: {request}")
        result = tool_manager.process_request(request)
        print(f"处理结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
