#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试脚本 - 逐步验证系统模块
"""

import sys
import os

# 添加当前目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("1. 测试数据库管理器...")
print("=" * 60)

try:
    from utils.database_manager import get_database_manager
    db = get_database_manager()
    print("✅ DatabaseManager 初始化成功")
    
    db.insert_system_log('INFO', 'Test', '测试日志')
    print("✅ 写入系统日志成功")
    
    stats = db.get_database_stats()
    print(f"✅ 数据库统计: {stats}")
    
except Exception as e:
    print(f"❌ 数据库管理器错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("2. 测试系统健康监控...")
print("=" * 60)

try:
    from monitor.system_health import get_system_health_monitor
    monitor = get_system_health_monitor()
    print("✅ SystemHealthMonitor 初始化成功")
    
    result = monitor.check_all_modules()
    print(f"✅ 健康检查完成，状态: {result.get('overall_status')}")
    
except Exception as e:
    print(f"❌ 系统健康监控错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("3. 测试安全控制...")
print("=" * 60)

try:
    from risk.data_source_risk_control import get_security_control
    security = get_security_control()
    print("✅ EnhancedSecurityControl 初始化成功")
    
    safe, msg = security.detect_suspicious_input("正常输入")
    print(f"✅ 正常输入测试: {'通过' if safe else '未通过'} - {msg}")
    
    unsafe, msg2 = security.detect_suspicious_input("<script>alert('xss')</script>")
    print(f"✅ XSS检测测试: {'成功拦截' if not unsafe else '未拦截'} - {msg2}")
    
except Exception as e:
    print(f"❌ 安全控制错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("4. 测试监控调度器...")
print("=" * 60)

try:
    from monitor.scheduler import get_monitoring_scheduler, initialize_default_tasks
    initialize_default_tasks()
    scheduler = get_monitoring_scheduler()
    print("✅ MonitoringScheduler 初始化成功")
    
    status = scheduler.get_status()
    print(f"✅ 调度器状态: {status}")
    
except Exception as e:
    print(f"❌ 监控调度器错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("🎉 所有基础测试完成")
print("=" * 60)
