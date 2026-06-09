#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora + QS_Robot 统一启动脚本（端口 5002）
=============================================
整合后的单一对外端口服务入口：

端口 5002 统一提供：
  ✓ Aurora 原系统核心功能（策略库、韬定律优化器、自动演进引擎、五层防钓鱼风控）
  ✓ QS_Robot 新功能（港大29智能体分析、全市场扫描、股票池、技术分析、对话助手）

不再需要启动端口 5000 的独立服务，简化钓鱼防空监控和运维。

使用方式：
    python simple_launch_5002.py

访问地址：
    控制台首页:     http://127.0.0.1:5002/dashboard
    主系统:         http://127.0.0.1:5002/main_system
    港大智能体:     http://127.0.0.1:5002/vibe_analysis
    技术分析:       http://127.0.0.1:5002/technical_analysis
    股票池:         http://127.0.0.1:5002/stock_pool
    对话助手:       http://127.0.0.1:5002/chat
    Cline智能体:    http://127.0.0.1:5002/cline-agent
    健康检查API:    http://127.0.0.1:5002/api/health

作者：Aurora 系统整合团队
创建时间：2025
"""

import os
import sys
import logging

# 确保当前目录和 Aurora 根目录在 Python 路径中
AURORA_ROOT = os.path.dirname(os.path.abspath(__file__))
if AURORA_ROOT not in sys.path:
    sys.path.insert(0, AURORA_ROOT)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(AURORA_ROOT, "logs", "launch_5002.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("launch_5002")

print("\n" + "=" * 70)
print("  Aurora + QS_Robot 统一服务启动中")
print("  单一对外端口: 5002")
print("=" * 70)

# 导入 Aurora 核心 Flask 应用
logger.info("正在导入 Aurora 核心模块 (visualization.py) ...")
try:
    from visualization import app
    logger.info("✓ Aurora 核心 Flask 应用加载成功")
except Exception as e:
    logger.error(f"✗ Aurora 核心模块加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 显式调用 QS Robot 深度集成初始化（确保所有路由都注册完成）
logger.info("正在初始化 QS_Robot 深度集成 ...")
try:
    from visualization import _init_qbot_deep_integration
    qbot_report = _init_qbot_deep_integration()
    if qbot_report and isinstance(qbot_report, dict):
        logger.info(f"✓ QS_Robot 集成报告: 新增 {qbot_report.get('new_routes_registered', '?')} 条 API 路由")
    else:
        logger.info("✓ QS_Robot 深度集成已完成")
except Exception as e:
    logger.warning(f"⚠ QS_Robot 集成警告: {e} (不影响 Aurora 原功能)")

print("\n" + "=" * 70)
print("  服务已就绪")
print("=" * 70)
print(f"  [控制台首页]   http://127.0.0.1:5002/dashboard")
print(f"  [主系统]       http://127.0.0.1:5002/main_system")
print(f"  [港大智能体]   http://127.0.0.1:5002/vibe_analysis")
print(f"  [技术分析]     http://127.0.0.1:5002/technical_analysis")
print(f"  [股票池]       http://127.0.0.1:5002/stock_pool")
print(f"  [AI对话]       http://127.0.0.1:5002/chat")
print(f"  [Cline智能体]  http://127.0.0.1:5002/cline-agent")
print(f"  [健康检查]     http://127.0.0.1:5002/api/health")
print(f"  [系统状态]     http://127.0.0.1:5002/api/system/status")
print("=" * 70)
print("  统一服务架构:")
print("    - Aurora 原系统: 策略库 / 韬定律优化器 / 自动演进 / 五层风控")
print("    - QS_Robot 功能: 港大29智能体 / 全市场扫描 / 股票池 / 技术分析")
print("    - 单一端口: 5002 (简化钓鱼防空监控和运维)")
print("=" * 70 + "\n")

# 启动 Flask 应用
try:
    app.run(host="127.0.0.1", port=5002, debug=False, threaded=True)
except OSError as e:
    if "address already in use" in str(e).lower() or "10048" in str(e):
        logger.error(f"端口 5002 已被占用，请先关闭占用端口的进程后重试。")
        logger.error(f"Windows 检查命令: netstat -ano | findstr :5002")
    else:
        logger.error(f"启动失败: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    logger.info("\n服务已手动停止")
except Exception as e:
    logger.error(f"启动异常: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
