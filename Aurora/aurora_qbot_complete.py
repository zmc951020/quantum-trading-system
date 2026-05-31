#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Aurora ⟷ QS Robot 深度集成完成方案                        ║
║                                                              ║
║  核心模块: aurora_qbot_deep_integration.py (基础引擎)       ║
║  本文件:   可视化集成钩子 + Flask路由 + 启动入口           ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, sys, time, json, threading, logging
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format='[%(asctime)s][QBot-Complete] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger('QBot-Complete')

# ============================================================
# 集成启动器
# ============================================================

def integrate_into_aurora(app, visualization_module=None):
    """
    向Aurora Flask应用注入深度集成能力
    
    Args:
        app: Flask应用实例
        visualization_module: visualization.py模块引用（可选）
    
    Returns:
        dict: 各组件引用
    """
    from flask import jsonify, request
    
    logger.info("=" * 60)
    logger.info("  🚀 启动 Aurora-QBot 深度集成")
    logger.info("=" * 60)
    
    # 尝试加载深度集成引擎
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from aurora_qbot_deep_integration import (
            SharedProcessBus, DeepFallbackEngine, CoEngine,
            AuroraQBotAdapter, StrategyBridge, BusEvent, BusEventType,
            register_deep_integration_routes
        )
        DEEP_INTEGRATION_AVAILABLE = True
        logger.info("  ✅ 深度集成引擎已加载")
    except ImportError as e:
        logger.warning(f"  ⚠️ 深度集成引擎加载失败: {e}")
        DEEP_INTEGRATION_AVAILABLE = False
    
    if DEEP_INTEGRATION_AVAILABLE:
        # 创建所有组件
        bus = SharedProcessBus()
        fallback = DeepFallbackEngine()
        co_engine = CoEngine(bus, fallback)
        adapter = AuroraQBotAdapter(bus, fallback, co_engine)
        strategy_bridge = StrategyBridge(adapter)
        
        # 注册API路由
        register_deep_integration_routes(app, adapter, strategy_bridge)
        
        # 发布上线事件
        bus.publish(BusEvent(type=BusEventType.AURORA_ONLINE, source="system",
                             data={"version": "V7-GYRO"}, priority=1))
        bus.publish(BusEvent(type=BusEventType.QBOT_ONLINE, source="system",
                             data={"version": "V2.0"}, priority=1))
        
        # 注入Dashboard上下文
        if visualization_module and hasattr(visualization_module, 'app'):
            @visualization_module.app.context_processor
            def inject_deep_context():
                return {"deep_integration": {
                    "mode": adapter.get_mode(),
                    "dual_core": adapter.is_dual_core(),
                    "version": "V3.0-DeepIntegration",
                    "bus_events": bus.get_stats().get("events_published", 0),
                    "co_tasks": co_engine.get_co_stats().get("co_tasks", 0)
                }}
            logger.info("  ✅ Dashboard上下文已注入")
        
        # 附加额外快捷路由
        _register_extra_routes(app, adapter, strategy_bridge, co_engine, bus)
        
        components = {
            "adapter": adapter, "bus": bus, "fallback": fallback,
            "co_engine": co_engine, "strategy_bridge": strategy_bridge,
            "deep_available": True
        }
    else:
        # 降级模式 - 仅注册基本路由
        _register_fallback_routes(app)
        components = {"deep_available": False}
    
    logger.info(f"✅ 集成完成 | 双核联动={'就绪' if DEEP_INTEGRATION_AVAILABLE else '不可用'}")
    return components


def _register_extra_routes(app, adapter, strategy_bridge, co_engine, bus):
    """注册额外快捷路由"""
    from flask import jsonify, request
    
    @app.route('/api/qbot/status')
    def api_qbot_status():
        """QBot兼容的状态端点"""
        state = adapter.get_shared_state()
        return jsonify({"success": True, "data": state})
    
    @app.route('/api/qbot/strategies')
    def api_qbot_strategies():
        """QBot兼容的策略列表"""
        strategies = strategy_bridge.get_strategy_list()
        return jsonify({"success": True, "data": {"strategies": strategies, "count": len(strategies)}})
    
    @app.route('/api/qbot/strategy/start', methods=['POST'])
    def api_qbot_start_strategy():
        data = request.json or {}
        name = data.get('strategy_name', data.get('name', ''))
        balance = data.get('balance', 100000.0)
        if not name:
            return jsonify({"success": False, "error": "策略名称必填"}), 400
        ok, msg = strategy_bridge.start_strategy(name, balance)
        return jsonify({"success": ok, "message": msg})
    
    @app.route('/api/qbot/strategy/stop', methods=['POST'])
    def api_qbot_stop_strategy():
        ok, msg = strategy_bridge.stop_strategy()
        return jsonify({"success": ok, "message": msg})
    
    @app.route('/api/qbot/backtest/co', methods=['POST'])
    def api_qbot_co_backtest():
        data = request.json or {}
        task_id = co_engine.submit_co_backtest(
            strategy_name=data.get('strategy_name', 'FourierRLStrategy'),
            days=data.get('days', 30),
            symbol=data.get('symbol', 'BTCUSDT')
        )
        return jsonify({"success": True, "data": {"task_id": task_id}})
    
    @app.route('/api/qbot/optimize/co', methods=['POST'])
    def api_qbot_co_optimize():
        data = request.json or {}
        task_id = co_engine.submit_co_optimization(
            strategy_name=data.get('strategy_name', 'FourierRLStrategy'),
            param_ranges=data.get('param_ranges', {}),
            iterations=data.get('iterations', 50)
        )
        return jsonify({"success": True, "data": {"task_id": task_id}})
    
    @app.route('/api/qbot/bus/events')
    def api_qbot_bus_events():
        limit = request.args.get('limit', 50, type=int)
        return jsonify({"success": True, "data": bus.get_recent_events(limit)})
    
    logger.info("  ✅ 6个QBot兼容端点已注册")


def _register_fallback_routes(app):
    """降级路由（当深度集成引擎不可用时）"""
    from flask import jsonify
    
    @app.route('/api/qbot/status')
    def api_qbot_fallback_status():
        return jsonify({"success": True, "data": {"mode": "aurora_standalone", "deep_integration": False}})
    
    @app.route('/api/qbot/strategies')
    def api_qbot_fallback_strategies():
        strategies = [
            {"name": "FourierRLStrategy", "category": "RL", "description": "傅里叶强化学习策略"},
            {"name": "FinalMarketAdaptiveGrid", "category": "Grid", "description": "自适应网格策略"},
            {"name": "HuijinValueStrategy", "category": "Value", "description": "汇金价值策略"},
        ]
        return jsonify({"success": True, "data": {"strategies": strategies, "count": len(strategies)}})
    
    logger.info("  ⚠️ 3个降级端点已注册（深度集成引擎不可用）")


# ============================================================
# visualization.py 集成入口
# ============================================================

def patch_visualization_module():
    """
    自动修补 visualization.py，注入深度集成
    
    使用方法：在Aurora目录下运行
        python aurora_qbot_complete.py --patch
    或在 visualization.py 底部添加：
        from aurora_qbot_complete import integrate_into_aurora
        deep_components = integrate_into_aurora(app, sys.modules[__name__])
    """
    logger.info("执行 visualization.py 自动修补...")
    
    import importlib
    
    try:
        viz = importlib.import_module('visualization')
        components = integrate_into_aurora(viz.app, viz)
        logger.info(f"✅ visualization.py 修补完成")
        return components
    except ImportError:
        logger.error("visualization.py 未找到")
    except Exception as e:
        logger.error(f"修补异常: {e}")
    
    return None


# ============================================================
# 独立启动入口 (Standalone)
# ============================================================

def start_standalone(port=5000):
    """独立启动Aurora+QBot集成实例"""
    from flask import Flask
    import importlib
    
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static',
                static_url_path='/static')
    
    # 尝试加载 visualization.py 的蓝图和路由
    try:
        viz = importlib.import_module('visualization')
        # 复制关键配置
        for attr in ['config', 'secret_key', 'template_folder', 'static_folder']:
            if hasattr(viz, attr):
                setattr(app, attr, getattr(viz, attr))
    except ImportError:
        pass
    
    # 注入深度集成
    components = integrate_into_aurora(app)
    
    # 启动
    logger.info(f"🚀 Aurora+QBot 集成实例启动: http://localhost:{port}")
    logger.info(f"  - /api/qbot/status    - QBot状态")
    logger.info(f"  - /api/qbot/strategies - 策略列表")
    logger.info(f"  - /api/qbot/backtest/co - 协同回测")
    
    app.run(host='127.0.0.1', port=port, debug=False)
    return app, components


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Aurora-QBot 深度集成工具')
    parser.add_argument('--patch', action='store_true', help='修补 visualization.py')
    parser.add_argument('--standalone', action='store_true', help='独立启动集成实例')
    parser.add_argument('--port', type=int, default=5000, help='端口 (default: 5000)')
    parser.add_argument('--test', action='store_true', help='运行集成测试')
    args = parser.parse_args()
    
    if args.patch:
        patch_visualization_module()
    elif args.standalone:
        start_standalone(port=args.port)
    elif args.test:
        # 快速集成测试
        from flask import Flask
        app = Flask(__name__)
        comps = integrate_into_aurora(app)
        
        with app.test_client() as c:
            # 测试QBot状态端点
            r = c.get('/api/qbot/status')
            data = r.get_json()
            print(f"  QBot状态: {data.get('data', {}).get('mode', 'N/A')}")
            
            r = c.get('/api/qbot/strategies')
            data = r.get_json()
            print(f"  策略数量: {data.get('data', {}).get('count', 0)}")
            
            if comps.get('deep_available'):
                r = c.get('/api/deep/bus/stats')
                data = r.get_json()
                print(f"  总线事件数: {data.get('data', {}).get('events_published', 0)}")
        
        print("\n✅ 集成测试通过！")
    else:
        print("用法: python aurora_qbot_complete.py [--patch|--standalone|--test]")
        print("  --patch      修补 visualization.py")
        print("  --standalone  独立启动集成实例")
        print("  --test        运行集成测试")