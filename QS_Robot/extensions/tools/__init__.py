"""
QS Robot - Tools Module
========================
扩展工具集合：提供一键式优化、状态检查等高级功能。

用法：
  # 导入并使用 Python API
  from extensions.tools.tau_oneclick import TauOneClickOptimizer, main as tau_cli_main

  # 命令行调用（推荐）
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动"

工具列表：
  - tau_oneclick: 韬定律一键式优化器（优化 → 应用最佳参数 → 回测验证）
"""

from .tau_oneclick import TauOneClickOptimizer

__all__ = ["TauOneClickOptimizer"]
