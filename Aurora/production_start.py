#!/usr/bin/env python3
"""
Aurora量化交易系统 - 生产环境启动脚本
使用waitress作为WSGI服务器（Windows兼容）
"""

import os
import sys
import logging
from waitress import serve

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入应用
from visualization import app

# 导入数据库维护模块
db_maintenance_scheduler = None
try:
    from utils.db_maintenance import DatabaseMaintenanceScheduler
    db_maintenance_scheduler = DatabaseMaintenanceScheduler()
    logger.info("[OK] DatabaseMaintenanceScheduler imported successfully")
except Exception as e:
    logger.warning(f"[WARNING] DatabaseMaintenanceScheduler import failed: {e}")

if __name__ == '__main__':
    print("启动Aurora量化交易系统 - 生产环境")
    print("使用waitress作为WSGI服务器")
    print("访问地址: http://0.0.0.0:8000")
    
    # 启动数据库自动维护
    if db_maintenance_scheduler:
        try:
            db_maintenance_scheduler.start_auto_maintenance(interval_minutes=60)
            logger.info("数据库自动维护调度器已启动 (检查间隔: 60分钟)")
        except Exception as e:
            logger.warning(f"启动数据库维护调度器失败: {e}")
    
    # 启动服务器
    serve(app, host='0.0.0.0', port=8000, threads=4)
    
    # 应用退出时停止维护调度器
    if db_maintenance_scheduler:
        try:
            db_maintenance_scheduler.stop_auto_maintenance()
            logger.info("数据库维护调度器已停止")
        except Exception as e:
            logger.warning(f"停止数据库维护调度器失败: {e}")
