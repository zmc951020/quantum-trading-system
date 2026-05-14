# -*- coding: utf-8 -*-
"""
健康检查API测试脚本
验证可视化界面健康检查功能是否正常工作
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_health_api():
    """测试健康检查API"""
    print("=" * 60)
    print("健康检查API测试")
    print("=" * 60)
    
    try:
        # 测试系统健康监控
        from monitor.system_health import get_system_health_monitor
        
        monitor = get_system_health_monitor()
        print("[OK] 系统健康监控模块初始化成功")
        
        # 执行完整健康检查
        result = monitor.check_all_modules()
        print("[OK] 完整健康检查执行成功")
        
        # 输出结果
        print(f"\n整体状态: {result['overall_status'].value}")
        print(f"检查时间: {result['check_time']}")
        
        print("\n模块状态:")
        for module_name, module_data in result['modules'].items():
            status = module_data['status']
            print(f"  {module_name}: {status}")
        
        if result['warnings']:
            print("\n警告列表:")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        if result['criticals']:
            print("\n严重问题列表:")
            for critical in result['criticals']:
                print(f"  - {critical}")
        
        return True
        
    except Exception as e:
        print(f"[FAILED] 健康检查API测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_database_health():
    """测试数据库健康检查"""
    print("\n" + "=" * 60)
    print("数据库健康检查测试")
    print("=" * 60)
    
    try:
        from utils.database_manager import get_database_manager
        
        db = get_database_manager()
        print("[OK] 数据库管理器初始化成功")
        
        stats = db.get_database_stats()
        print("[OK] 数据库统计获取成功")
        print(f"  日志数: {stats.get('total_logs', 0)}")
        print(f"  交易记录数: {stats.get('total_trades', 0)}")
        print(f"  健康检查数: {stats.get('total_health_checks', 0)}")
        
        # 测试插入健康检查记录
        db.insert_health_check('test', 'healthy', '测试健康检查')
        print("[OK] 健康检查记录插入成功")
        
        return True
        
    except Exception as e:
        print(f"[FAILED] 数据库健康检查测试失败: {str(e)}")
        return False

def test_security_health():
    """测试安全模块健康检查"""
    print("\n" + "=" * 60)
    print("安全模块健康检查测试")
    print("=" * 60)
    
    try:
        from risk.data_source_risk_control import get_security_control
        
        security = get_security_control()
        print("[OK] 安全控制模块初始化成功")
        
        # 测试数据验证
        test_data = {
            'symbol': '600036.SH',
            'price': 50.23,
            'volume': 1000000,
            'timestamp': '2026-05-14 10:30:00'
        }
        
        is_valid, message = security.validate_realtime_data(test_data, 'test_source')
        print(f"[OK] 数据验证: {is_valid} - {message}")
        
        return True
        
    except Exception as e:
        print(f"[FAILED] 安全模块健康检查测试失败: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("=" * 70)
    print("健康检查集成测试")
    print("=" * 70)
    
    results = []
    
    results.append(("系统健康API", test_health_api()))
    results.append(("数据库健康检查", test_database_health()))
    results.append(("安全模块健康检查", test_security_health()))
    
    print("\n" + "=" * 70)
    print("测试报告")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"测试总数: {total}")
    print(f"通过: {passed}")
    print(f"失败: {total - passed}")
    print(f"通过率: {passed / total * 100:.2f}%")
    
    print("\n详细结果:")
    for name, result in results:
        status = "通过" if result else "失败"
        print(f"  {name}: {status}")
    
    if passed == total:
        print("\n🎉 所有测试通过！健康检查集成正常！")
        return 0
    else:
        print("\n⚠️ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
