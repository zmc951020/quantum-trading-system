# -*- coding: utf-8 -*-
"""
数据库更新与策略逻辑综合测试
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_database_manager():
    """测试数据库管理器"""
    print("=" * 60)
    print("TEST 1: 数据库管理器测试")
    print("=" * 60)
    
    try:
        from utils.database_manager import get_db_manager
        
        db = get_db_manager()
        print("[OK] 数据库管理器初始化成功")
        
        db.insert_system_log('INFO', 'Test', '数据库测试日志')
        print("[OK] 日志插入成功")
        
        stats = db.get_database_stats()
        print("[OK] 统计查询成功")
        print("   日志数:", stats.get('total_logs', 0))
        print("   交易记录数:", stats.get('total_trades', 0))
        print("   健康检查数:", stats.get('total_health_checks', 0))
        
        db.insert_health_check('test_component', 'healthy', '测试通过')
        print("[OK] 健康检查记录成功")
        
        return True
        
    except Exception as e:
        print("[FAILED] 数据库管理器测试失败:", str(e))
        return False

def test_data_source_risk_control():
    """测试数据源安全控制"""
    print("\n" + "=" * 60)
    print("TEST 2: 数据源安全控制测试")
    print("=" * 60)
    
    try:
        from risk.data_source_risk_control import get_security_control
        
        security = get_security_control()
        print("[OK] 安全控制模块初始化成功")
        
        test_data = {
            'symbol': '600036.SH',
            'price': 50.23,
            'volume': 1000000,
            'timestamp': '2026-05-14 10:30:00'
        }
        
        is_valid, message = security.validate_realtime_data(test_data, 'test_source')
        print("[OK] 数据验证:", is_valid, "-", message)
        
        malicious_data = {
            'symbol': 'TEST',
            'price': 99999999,
            'volume': -100,
            'timestamp': '2026-05-14 10:30:00'
        }
        
        is_valid, message = security.validate_realtime_data(malicious_data, 'malicious_source')
        print("[OK] 异常数据检测:", is_valid, "-", message)
        
        return True
        
    except Exception as e:
        print("[FAILED] 安全控制测试失败:", str(e))
        return False

def test_backtest_system():
    """测试回测系统"""
    print("\n" + "=" * 60)
    print("TEST 3: 回测系统测试")
    print("=" * 60)
    
    try:
        from auto_backtest.auto_backtest_system import get_backtest_system
        from auto_backtest.strategy_discovery import get_strategy_discovery
        
        backtest_system = get_backtest_system()
        discovery = get_strategy_discovery()
        
        print("[OK] 回测系统初始化成功")
        
        status = backtest_system.get_status()
        print("[OK] 系统状态获取成功")
        print("   系统名称:", status.get('system_name'))
        print("   策略数:", status.get('total_strategies'))
        
        new_strategies = discovery.detect_new_strategies()
        print("[OK] 策略发现完成，发现", len(new_strategies), "个策略")
        
        return True
        
    except Exception as e:
        print("[FAILED] 回测系统测试失败:", str(e))
        return False

def test_scheduler():
    """测试监控调度器"""
    print("\n" + "=" * 60)
    print("TEST 4: 监控调度器测试")
    print("=" * 60)
    
    try:
        from monitor.scheduler import get_monitoring_scheduler
        
        scheduler = get_monitoring_scheduler()
        print("[OK] 监控调度器初始化成功")
        
        status = scheduler.get_status()
        print("[OK] 调度器状态:", status)
        
        return True
        
    except Exception as e:
        print("[FAILED] 调度器测试失败:", str(e))
        return False

def test_system_health():
    """测试系统健康监控"""
    print("\n" + "=" * 60)
    print("TEST 5: 系统健康监控测试")
    print("=" * 60)
    
    try:
        from monitor.system_health import get_system_health_monitor
        
        monitor = get_system_health_monitor()
        print("[OK] 健康监控模块初始化成功")
        
        result = monitor.check_all_modules()
        print("[OK] 健康检查完成")
        print("   总体状态:", result.get('overall_status'))
        print("   模块数:", len(result.get('modules', [])))
        
        return True
        
    except Exception as e:
        print("[FAILED] 健康监控测试失败:", str(e))
        return False

def main():
    """主测试函数"""
    print("=" * 70)
    print("数据库更新与策略逻辑综合审核测试")
    print("=" * 70)
    
    results = []
    
    results.append(("数据库管理器", test_database_manager()))
    results.append(("数据源安全控制", test_data_source_risk_control()))
    results.append(("回测系统", test_backtest_system()))
    results.append(("监控调度器", test_scheduler()))
    results.append(("系统健康监控", test_system_health()))
    
    print("\n" + "=" * 70)
    print("测试报告")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print("测试总数:", total)
    print("通过:", passed)
    print("失败:", total - passed)
    print("通过率:", "{:.2f}%".format(passed / total * 100))
    
    print("\n详细结果:")
    for name, result in results:
        status = "通过" if result else "失败"
        print("  {}: {}".format(name, status))
    
    if passed == total:
        print("\n所有测试通过！系统功能完整可用！")
        return 0
    else:
        print("\n部分测试失败，请检查相关模块")
        return 1

if __name__ == "__main__":
    sys.exit(main())
