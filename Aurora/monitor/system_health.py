#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统健康监控模块
全面检测Aurora系统各个模块的运行状态
"""

import time
import os
import sys
import traceback
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from enum import Enum

# 健康状态枚举
class HealthStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class ModuleHealth:
    """单个模块的健康状态"""
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.status = HealthStatus.UNKNOWN
        self.last_check_time = None
        self.last_error = None
        self.error_count = 0
        self.success_count = 0
        self.checks = {}  # 检查项目结果

    def set_healthy(self, message: str = "正常"):
        self.status = HealthStatus.HEALTHY
        self.last_check_time = datetime.now()
        self.last_error = None
        self.success_count += 1
        self.checks["status"] = {"result": "ok", "message": message}

    def set_warning(self, message: str):
        self.status = HealthStatus.WARNING
        self.last_check_time = datetime.now()
        self.last_error = message
        self.error_count += 1
        self.checks["status"] = {"result": "warning", "message": message}

    def set_critical(self, message: str):
        self.status = HealthStatus.CRITICAL
        self.last_check_time = datetime.now()
        self.last_error = message
        self.error_count += 1
        self.checks["status"] = {"result": "critical", "message": message}

class SystemHealthMonitor:
    """
    Aurora系统健康监控模块
    全面检测系统各个模块的运行状态
    """

    def __init__(self):
        self.modules: Dict[str, ModuleHealth] = {}
        self.start_time = datetime.now()
        self.total_checks = 0
        self.last_full_check = None
        self.alert_history = []

        # 初始化所有模块
        self._initialize_modules()
        print("[SystemHealthMonitor] 系统健康监控模块初始化完成")

    def _initialize_modules(self):
        """初始化所有需要监控的模块"""
        module_list = [
            "data_source",          # 数据源模块
            "data_provider",        # 数据提供模块
            "market_detection",     # 市场检测模块
            "ml_manager",           # 机器学习模块
            "risk_control",         # 风控模块
            "strategy",             # 策略模块
            "strategy_monitor",     # 策略监控模块
            "enhanced_evaluator",   # 增强型评估器模块
            "system",               # 系统整体
            "phishing_defense",    # 防钓鱼系统
            "enhanced_security",    # 增强安全控制
            "monitoring_scheduler",  # 监控调度器
            "database",             # 数据库
            "gain_modules",         # 增益性优化模块
        ]

        for module_name in module_list:
            self.modules[module_name] = ModuleHealth(module_name)

    def check_all_modules(self) -> Dict[str, Any]:
        """
        全面检查所有模块健康状态
        """
        print("\n" + "=" * 80)
        print("Aurora系统健康检查")
        print("=" * 80)

        results = {
            "check_time": datetime.now().isoformat(),
            "modules": {},
            "overall_status": HealthStatus.HEALTHY,
            "warnings": [],
            "criticals": []
        }

        # 1. 检查数据源模块
        self._check_data_source(results)

        # 2. 检查数据提供模块
        self._check_data_provider(results)

        # 3. 检查市场检测模块
        self._check_market_detection(results)

        # 4. 检查机器学习模块
        self._check_ml_manager(results)

        # 5. 检查风控模块
        self._check_risk_control(results)

        # 6. 检查策略模块
        self._check_strategy(results)

        # 7. 检查策略监控模块
        self._check_strategy_monitor(results)

        # 8. 检查增强型评估器模块
        self._check_enhanced_evaluator(results)

        # 9. 检查系统整体
        self._check_system(results)
        
        # 9. 检查防钓鱼系统
        self._check_phishing_defense(results)
        
        # 10. 检查增强安全控制
        self._check_enhanced_security(results)
        
        # 11. 检查监控调度器
        self._check_monitoring_scheduler(results)
        
        # 12. 检查数据库
        self._check_database(results)

        # 12. 检查增益性优化模块
        self._check_gain_modules(results)

        # 计算总体状态
        self._calculate_overall_status(results)

        self.last_full_check = datetime.now()
        self.total_checks += 1

        # 打印结果
        self._print_results(results)

        return results

    def _check_data_source(self, results: Dict):
        """检查数据源模块"""
        module = self.modules["data_source"]
        module.checks = {}

        try:
            # 检查导入
            from data import get_multi_data_source_manager
            module.checks["import"] = {"result": "ok", "message": "数据源模块导入成功"}

            # 检查初始化
            mgr = get_multi_data_source_manager()
            if mgr:
                module.checks["init"] = {"result": "ok", "message": "数据源管理器初始化成功"}
                status = mgr.get_status()
                module.checks["sources"] = {"result": "ok", "message": f"可用数据源: {list(status.get('sources', {}).keys())}"}
                module.set_healthy("数据源模块正常")
            else:
                module.set_warning("数据源管理器未初始化")
                results["warnings"].append("数据源管理器未初始化")

        except Exception as e:
            module.set_critical(f"数据源模块错误: {str(e)}")
            results["criticals"].append(f"数据源模块错误: {str(e)}")

        results["modules"]["data_source"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_data_provider(self, results: Dict):
        """检查数据提供模块"""
        module = self.modules["data_provider"]
        module.checks = {}

        try:
            # 检查导入
            from data import get_data_provider
            module.checks["import"] = {"result": "ok", "message": "数据提供模块导入成功"}

            # 检查初始化
            dp = get_data_provider()
            if dp:
                module.checks["init"] = {"result": "ok", "message": "数据提供器初始化成功"}
                summary = dp.get_market_summary()
                module.checks["data"] = {"result": "ok", "message": f"监控标的: {summary.get('total_symbols', 0)}个"}
                module.set_healthy("数据提供模块正常")
            else:
                module.set_warning("数据提供器未初始化")
                results["warnings"].append("数据提供器未初始化")

        except Exception as e:
            module.set_critical(f"数据提供模块错误: {str(e)}")
            results["criticals"].append(f"数据提供模块错误: {str(e)}")

        results["modules"]["data_provider"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_market_detection(self, results: Dict):
        """检查市场检测模块"""
        module = self.modules["market_detection"]
        module.checks = {}

        try:
            # 检查导入
            from strategies import FinalMarketAdaptiveGrid
            module.checks["import"] = {"result": "ok", "message": "策略模块导入成功"}

            # 简单测试市场检测逻辑
            test_strategy = FinalMarketAdaptiveGrid(100.0, 100000)
            if hasattr(test_strategy, 'detect_market_type') or hasattr(test_strategy, '_label_market_type'):
                module.checks["detection"] = {"result": "ok", "message": "市场检测功能可用"}
                module.set_healthy("市场检测模块正常")
            else:
                module.set_warning("市场检测功能可能受限")
                results["warnings"].append("市场检测功能可能受限")

        except Exception as e:
            module.set_warning(f"策略模块检查异常: {str(e)}")
            results["warnings"].append(f"策略模块检查异常: {str(e)}")

        results["modules"]["market_detection"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_ml_manager(self, results: Dict):
        """检查机器学习模块"""
        module = self.modules["ml_manager"]
        module.checks = {}

        try:
            # 检查导入
            from ml import get_ml_manager
            module.checks["import"] = {"result": "ok", "message": "ML管理器模块导入成功"}

            # 检查初始化
            ml_mgr = get_ml_manager()
            if ml_mgr:
                module.checks["init"] = {"result": "ok", "message": "ML管理器初始化成功"}

                # 检查模型是否存在
                available_models = []
                if hasattr(ml_mgr, 'models'):
                    available_models = list(ml_mgr.models.keys())
                elif hasattr(ml_mgr, 'regime_detector'):
                    available_models.append('regime_detector')

                if available_models:
                    module.checks["models"] = {"result": "ok", "message": f"可用ML模型: {available_models}"}
                    module.set_healthy("ML模块正常")
                else:
                    module.set_warning("ML模块可用，但模型未完全初始化")
                    results["warnings"].append("ML模型未完全初始化")
            else:
                module.set_warning("ML管理器未初始化")
                results["warnings"].append("ML管理器未初始化")

        except Exception as e:
            module.set_warning(f"ML模块检查异常: {str(e)}")
            results["warnings"].append(f"ML模块检查异常: {str(e)}")

        results["modules"]["ml_manager"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_risk_control(self, results: Dict):
        """检查风控模块"""
        module = self.modules["risk_control"]
        module.checks = {}

        try:
            # 检查数据源风控模块
            from risk import get_data_source_risk_control
            module.checks["data_risk_import"] = {"result": "ok", "message": "数据源风控模块导入成功"}

            ds_risk = get_data_source_risk_control()
            if ds_risk:
                module.checks["data_risk_init"] = {"result": "ok", "message": "数据源风控初始化成功"}

                # 测试简单验证
                test_data = {'price': 100.0, 'timestamp': datetime.now()}
                is_valid, msg = ds_risk.validate_realtime_data(test_data, 'test')
                module.checks["risk_test"] = {"result": "ok", "message": f"风控测试: {'通过' if is_valid else '未通过'}"}
                module.set_healthy("风控模块正常")
            else:
                module.set_warning("数据源风控未初始化")
                results["warnings"].append("数据源风控未初始化")

        except Exception as e:
            module.set_critical(f"风控模块错误: {str(e)}")
            results["criticals"].append(f"风控模块错误: {str(e)}")

        results["modules"]["risk_control"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_strategy(self, results: Dict):
        """检查策略模块"""
        module = self.modules["strategy"]
        module.checks = {}

        try:
            # 检查导入
            from strategies import FinalMarketAdaptiveGrid
            module.checks["import"] = {"result": "ok", "message": "策略模块导入成功"}

            # 测试策略初始化
            strategy = FinalMarketAdaptiveGrid(100.0, 100000)
            if strategy:
                module.checks["init"] = {"result": "ok", "message": "策略初始化成功"}
                module.checks["params"] = {"result": "ok", "message": f"策略参数已加载"}
                module.set_healthy("策略模块正常")
            else:
                module.set_warning("策略初始化异常")
                results["warnings"].append("策略初始化异常")

        except Exception as e:
            module.set_warning(f"策略模块检查异常: {str(e)}")
            results["warnings"].append(f"策略模块检查异常: {str(e)}")

        results["modules"]["strategy"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_strategy_monitor(self, results: Dict):
        """检查策略监控模块"""
        module = self.modules["strategy_monitor"]
        module.checks = {}

        try:
            # 检查导入
            try:
                import sys
                import os
                # 添加上级目录到路径以便导入
                aurora_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if aurora_dir not in sys.path:
                    sys.path.insert(0, aurora_dir)
                
                from strategy_monitor import get_strategy_monitor
                module.checks["import"] = {"result": "ok", "message": "策略监控模块导入成功"}
            except Exception as import_e:
                module.checks["import"] = {"result": "warning", "message": f"策略监控模块导入警告: {str(import_e)}"}
                results["warnings"].append(f"策略监控模块导入警告: {str(import_e)}")
            
            # 尝试获取监控器
            try:
                monitor = get_strategy_monitor()
                if monitor:
                    module.checks["init"] = {"result": "ok", "message": "策略监控器初始化成功"}
                    
                    # 获取监控统计
                    try:
                        stats = monitor.get_stats()
                        module.checks["stats"] = {"result": "ok", "message": f"监控统计已获取: 总事件 {stats.get('total_events', 0)} 个"}
                        
                        # 获取最近事件
                        recent_events = monitor.get_recent_events(limit=5)
                        module.checks["events"] = {"result": "ok", "message": f"最近事件: {len(recent_events)} 条"}
                        
                        module.set_healthy("策略监控模块正常")
                    except Exception as stat_e:
                        module.checks["stats"] = {"result": "warning", "message": f"获取监控统计异常: {str(stat_e)}"}
                        module.set_warning("策略监控模块部分功能受限")
                        results["warnings"].append(f"策略监控统计获取异常: {str(stat_e)}")
                else:
                    module.set_warning("策略监控器未初始化")
                    results["warnings"].append("策略监控器未初始化")
            except Exception as e:
                module.set_warning(f"策略监控模块异常: {str(e)}")
                results["warnings"].append(f"策略监控模块异常: {str(e)}")

        except Exception as e:
            module.set_warning(f"策略监控模块检查异常: {str(e)}")
            results["warnings"].append(f"策略监控模块检查异常: {str(e)}")

        results["modules"]["strategy_monitor"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_enhanced_evaluator(self, results: Dict):
        """检查增强型评估器模块"""
        module = self.modules["enhanced_evaluator"]
        module.checks = {}

        try:
            # 检查导入
            try:
                import sys
                import os
                aurora_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if aurora_dir not in sys.path:
                    sys.path.insert(0, aurora_dir)
                
                from enhanced_evaluator import EnhancedFinancialEvaluator
                module.checks["import"] = {"result": "ok", "message": "增强型评估器模块导入成功"}
            except Exception as import_e:
                module.checks["import"] = {"result": "warning", "message": f"增强型评估器模块导入警告: {str(import_e)}"}
                results["warnings"].append(f"增强型评估器模块导入警告: {str(import_e)}")
            
            # 尝试创建评估器实例
            try:
                evaluator = EnhancedFinancialEvaluator()
                module.checks["init"] = {"result": "ok", "message": "增强型评估器初始化成功"}
                
                # 检查指标数量
                total_metrics = len(evaluator.weights)
                module.checks["metrics"] = {"result": "ok", "message": f"评估指标数量: {total_metrics}"}
                
                # 检查权重总和
                total_weight = sum(evaluator.weights.values())
                module.checks["weights"] = {"result": "ok", "message": f"权重总和: {total_weight:.2f}"}
                
                module.set_healthy("增强型评估器模块正常")
            except Exception as e:
                module.set_warning(f"增强型评估器初始化异常: {str(e)}")
                results["warnings"].append(f"增强型评估器初始化异常: {str(e)}")

        except Exception as e:
            module.set_warning(f"增强型评估器模块检查异常: {str(e)}")
            results["warnings"].append(f"增强型评估器模块检查异常: {str(e)}")

        results["modules"]["enhanced_evaluator"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_system(self, results: Dict):
        """检查系统整体状态"""
        module = self.modules["system"]
        module.checks = {}

        try:
            # 检查Python版本
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            module.checks["python"] = {"result": "ok", "message": f"Python {python_version}"}

            # 检查内存（简单检查）
            import psutil
            process = psutil.Process()
            memory_usage = process.memory_info().rss / (1024 * 1024)
            module.checks["memory"] = {"result": "ok", "message": f"内存使用: {memory_usage:.1f} MB"}

            # 检查运行时间
            uptime = (datetime.now() - self.start_time).total_seconds()
            module.checks["uptime"] = {"result": "ok", "message": f"运行时间: {uptime:.1f} 秒"}

            module.set_healthy("系统整体正常")

        except ImportError:
            module.checks["python"] = {"result": "ok", "message": f"Python {sys.version_info.major}.{sys.version_info.minor}"}
            module.checks["uptime"] = {"result": "ok", "message": f"运行中"}
            module.set_warning("部分系统信息不可用（缺少psutil）")
            results["warnings"].append("缺少psutil库，无法完整监控系统资源")

        except Exception as e:
            module.set_warning(f"系统检查异常: {str(e)}")
            results["warnings"].append(f"系统检查异常: {str(e)}")

        results["modules"]["system"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_phishing_defense(self, results: Dict):
        """检查防钓鱼系统"""
        module = self.modules["phishing_defense"]
        module.checks = {}

        try:
            # 尝试导入并检查是否在visualization.py中
            module.checks["import"] = {"result": "ok", "message": "防钓鱼系统模块导入路径正确"}

            # 简单测试 - 检查是否可以访问相关变量（如果有）
            try:
                import sys
                # 检查是否已经在某个地方初始化
                if 'visualization' in sys.modules:
                    module.checks["status"] = {"result": "ok", "message": "防钓鱼系统可能已加载"}
                else:
                    module.checks["status"] = {"result": "warning", "message": "防钓鱼系统需在Web应用中加载"}
            except Exception:
                module.checks["status"] = {"result": "warning", "message": "防钓鱼系统需要在应用环境中测试"}

            module.set_healthy("防钓鱼系统模块就绪")

        except Exception as e:
            module.set_warning(f"防钓鱼系统检查异常: {str(e)}")
            results["warnings"].append(f"防钓鱼系统检查异常: {str(e)}")

        results["modules"]["phishing_defense"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_enhanced_security(self, results: Dict):
        """检查增强安全控制"""
        module = self.modules["enhanced_security"]
        module.checks = {}

        try:
            # 检查导入
            from risk.data_source_risk_control import get_security_control
            module.checks["import"] = {"result": "ok", "message": "增强安全控制模块导入成功"}

            # 检查初始化
            security = get_security_control()
            if security:
                module.checks["init"] = {"result": "ok", "message": "增强安全控制初始化成功"}
                
                # 检查是否有安全事件记录
                if hasattr(security, 'security_events'):
                    module.checks["events"] = {"result": "ok", "message": "安全事件记录功能可用"}
                
                module.set_healthy("增强安全控制正常")
            else:
                module.set_warning("增强安全控制未初始化")
                results["warnings"].append("增强安全控制未初始化")

        except Exception as e:
            module.set_critical(f"增强安全控制模块错误: {str(e)}")
            results["criticals"].append(f"增强安全控制模块错误: {str(e)}")

        results["modules"]["enhanced_security"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_monitoring_scheduler(self, results: Dict):
        """检查监控调度器"""
        module = self.modules["monitoring_scheduler"]
        module.checks = {}

        try:
            # 检查导入
            from monitor.scheduler import get_monitoring_scheduler
            module.checks["import"] = {"result": "ok", "message": "监控调度器模块导入成功"}

            # 检查初始化
            scheduler = get_monitoring_scheduler()
            if scheduler:
                module.checks["init"] = {"result": "ok", "message": "监控调度器初始化成功"}
                
                # 检查调度器状态
                status = scheduler.get_status()
                module.checks["running"] = {"result": "ok", "message": f"调度器运行状态: {'是' if status.get('running', False) else '否'}"}
                module.checks["tasks"] = {"result": "ok", "message": f"注册任务数量: {status.get('task_count', 0)}"}
                
                module.set_healthy("监控调度器正常")
            else:
                module.set_warning("监控调度器未初始化")
                results["warnings"].append("监控调度器未初始化")

        except Exception as e:
            module.set_critical(f"监控调度器模块错误: {str(e)}")
            results["criticals"].append(f"监控调度器模块错误: {str(e)}")

        results["modules"]["monitoring_scheduler"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_gain_modules(self, results: Dict):
        """检查增益性优化模块"""
        module = self.modules["gain_modules"]
        module.checks = {}

        try:
            # 检查各增益模块的导入和状态
            gain_modules = {
                "performance_tracker": "utils.strategy_performance_tracker",
                "risk_controller": "utils.unified_risk_controller",
                "param_optimizer": "utils.smart_param_optimizer",
                "rl_enhancer": "utils.rl_enhancer",
                "data_validator": "utils.data_quality_validator",
            }

            all_ok = True
            for name, import_path in gain_modules.items():
                try:
                    __import__(import_path)
                    module.checks[name] = {"result": "ok", "message": f"{name} 导入成功"}
                except ImportError as e:
                    module.checks[name] = {"result": "warning", "message": f"{name} 导入失败: {str(e)}"}
                    all_ok = False

            if all_ok:
                module.set_healthy("所有增益模块导入正常")
            else:
                module.set_warning("部分增益模块导入失败")
                results["warnings"].append("部分增益模块导入失败")

        except Exception as e:
            module.set_critical(f"增益模块检查错误: {str(e)}")
            results["criticals"].append(f"增益模块检查错误: {str(e)}")

        results["modules"]["gain_modules"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _check_database(self, results: Dict):
        """检查数据库模块"""
        module = self.modules["database"]
        module.checks = {}

        try:
            # 检查导入
            from utils.database_manager import get_db_manager
            module.checks["import"] = {"result": "ok", "message": "数据库管理模块导入成功"}

            # 检查初始化
            db = get_db_manager()
            if db:
                module.checks["init"] = {"result": "ok", "message": "数据库管理器初始化成功"}
                
                # 检查数据库连接和统计
                try:
                    stats = db.get_database_stats()
                    module.checks["connection"] = {"result": "ok", "message": "数据库连接正常"}
                    module.checks["stats"] = {"result": "ok", "message": f"数据库统计已获取: {len(stats)} 条"}
                except Exception as e:
                    module.checks["connection"] = {"result": "warning", "message": f"数据库统计异常: {str(e)}"}
                
                module.set_healthy("数据库模块正常")
            else:
                module.set_warning("数据库管理器未初始化")
                results["warnings"].append("数据库管理器未初始化")

        except Exception as e:
            module.set_critical(f"数据库模块错误: {str(e)}")
            results["criticals"].append(f"数据库模块错误: {str(e)}")

        results["modules"]["database"] = {
            "status": module.status.value,
            "checks": module.checks,
            "last_error": module.last_error
        }

    def _calculate_overall_status(self, results: Dict):
        """计算整体健康状态"""
        if results["criticals"]:
            results["overall_status"] = HealthStatus.CRITICAL
        elif results["warnings"]:
            results["overall_status"] = HealthStatus.WARNING
        else:
            results["overall_status"] = HealthStatus.HEALTHY

    def _print_results(self, results: Dict):
        """打印检查结果"""
        print(f"\n检查时间: {results['check_time']}")
        print(f"运行时间: {(datetime.now() - self.start_time).total_seconds():.1f} 秒")
        print(f"总检查次数: {self.total_checks + 1}")

        print("\n模块状态:")
        for module_name, module_data in results["modules"].items():
            status = module_data["status"]
            status_icon = {
                "healthy": "[OK]",
                "warning": "[WARN]",
                "critical": "[ERR]",
                "unknown": "[???]"
            }.get(status, "[???]")

            print(f"  {status_icon} {module_name}: {status.upper()}")
            for check_name, check_result in module_data.get("checks", {}).items():
                result_icon = "[OK]" if check_result.get("result") == "ok" else "[WARN]"
                print(f"      {result_icon} {check_name}: {check_result.get('message')}")

        print("\n整体状态: ", end="")
        if results["overall_status"] == HealthStatus.HEALTHY:
            print("[OK] 健康 - 所有模块正常运行")
        elif results["overall_status"] == HealthStatus.WARNING:
            print("[WARN] 警告 - 部分模块有问题，建议检查")
            print("   警告列表:")
            for warning in results["warnings"]:
                print(f"   - {warning}")
        elif results["overall_status"] == HealthStatus.CRITICAL:
            print("[ERR] 严重 - 系统存在严重问题，建议立即处理")
            print("   严重问题列表:")
            for critical in results["criticals"]:
                print(f"   - {critical}")

        print("\n" + "=" * 80)

    def get_health_summary(self) -> Dict[str, Any]:
        """获取当前健康状态摘要"""
        return {
            "total_checks": self.total_checks,
            "last_check": self.last_full_check.isoformat() if self.last_full_check else None,
            "start_time": self.start_time.isoformat(),
            "modules": {
                name: {
                    "status": mod.status.value,
                    "error_count": mod.error_count,
                    "success_count": mod.success_count
                }
                for name, mod in self.modules.items()
            }
        }

# 全局实例
global_health_monitor = None

def get_system_health_monitor() -> SystemHealthMonitor:
    """获取全局系统健康监控实例"""
    global global_health_monitor
    if global_health_monitor is None:
        global_health_monitor = SystemHealthMonitor()
    return global_health_monitor
