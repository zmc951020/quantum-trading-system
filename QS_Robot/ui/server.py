
import os
import sys
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

# ============================================================
# Windows控制台UTF-8编码补丁 (解决'gbk' codec无法编码emoji的问题)
# ============================================================
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加QS Robot到路径
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, current_dir)

from config.config import config
from llm_manager import llm_manager
from extensions.data_sources import AuroraDataSource
from qs_robot_core import QSRobotCore

# 导入股票池智能管理系统
from stock_pool.main import StockPoolSystem

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # 允许跨域

# 初始化数据源和机器人核心
data_source = AuroraDataSource()
data_source.connect()
robot_core = QSRobotCore()

# 初始化股票池系统
stock_pool_system = StockPoolSystem()


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    """统一导航主页"""
    return render_template('dashboard.html')


@app.route('/stock_pool')
def stock_pool_page():
    """股票池智能管理系统页面"""
    return render_template('stock_pool.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """聊天接口 - 集成QS Robot智能核心"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        
        # 先尝试用 QS Robot 核心处理命令
        response = robot_core.process_command(user_message)
        
        return jsonify({"success": True, "response": response})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/system/connect', methods=['POST'])
def connect_system():
    """连接量化系统"""
    success = data_source.connect()
    return jsonify({"success": success})


@app.route('/api/system/status', methods=['GET'])
def system_status():
    """获取系统状态"""
    try:
        strategies = data_source.get_data({"type": "strategies"})
        health = data_source.get_data({"type": "health"})
        return jsonify({
            "success": True,
            "data": {
                "connected": data_source.is_connected(),
                "strategies": strategies,
                "health": health,
                "llm_available": llm_manager.active_provider is not None and llm_manager.active_provider.is_available()
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 股票池管理 API ====================

@app.route('/api/stock_pool/generate_stocks', methods=['POST'])
def generate_stocks():
    """生成示例股票数据"""
    try:
        data = request.get_json()
        count = data.get('count', 10)
        stocks = stock_pool_system.generate_sample_stocks(count)
        
        result = []
        for stock in stocks:
            result.append({
                'code': stock.code,
                'name': stock.name,
                'market': stock.market,
                'price': stock.price,
                'pe': stock.pe,
                'pb': stock.pb,
                'roe': stock.roe,
                'volume': stock.volume,
                'volatility': stock.volatility,
                'trend_strength': stock.trend_strength,
                'quality_score': stock.quality_score,
                'sector': stock.sector,
                'industry': stock.industry
            })
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/stock_pool/run_pipeline', methods=['POST'])
def run_pipeline():
    """运行股票筛选评估流程"""
    try:
        data = request.get_json()
        count = data.get('count', 10)
        
        stocks = stock_pool_system.generate_sample_stocks(count)
        results = stock_pool_system.run_full_pipeline(stocks)
        
        formatted_results = {
            'filtered': [],
            'simulated': [],
            'final': [],
            'pool_summary': stock_pool_system.pool_manager.get_pool_summary()
        }
        
        for f in results['filtered']:
            formatted_results['filtered'].append({
                'code': f['stock'].code,
                'name': f['stock'].name,
                'scores': f['scores'],
                'passed': f['passed']
            })
        
        for s in results['simulated']:
            formatted_results['simulated'].append({
                'code': s['stock'].code,
                'name': s['stock'].name,
                'strategy': s['strategy'].name,
                'strategy_type': s['strategy'].type,
                'total_return': s['simulation'].total_return,
                'sharpe_ratio': s['simulation'].sharpe_ratio,
                'max_drawdown': s['simulation'].max_drawdown,
                'win_rate': s['simulation'].win_rate,
                'trades': s['simulation'].trades,
                'sim_score': s['simulation'].score
            })
        
        for f in results['final']:
            formatted_results['final'].append({
                'code': f['stock'].code,
                'name': f['stock'].name,
                'strategy': f['strategy'].name,
                'score': f['score'],
                'grade': f['grade']
            })
        
        return jsonify({"success": True, "data": formatted_results})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/stock_pool/pool_summary', methods=['GET'])
def pool_summary():
    """获取股票池摘要"""
    try:
        summary = stock_pool_system.pool_manager.get_pool_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/stock_pool/get_pool/<pool_type>', methods=['GET'])
def get_pool(pool_type):
    """获取指定股票池的股票"""
    try:
        stocks = stock_pool_system.pool_manager.get_pool(pool_type)
        result = []
        for stock in stocks:
            result.append({
                'code': stock.code,
                'name': stock.name,
                'price': stock.price,
                'quality_score': stock.quality_score
            })
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/stock_pool/strategies', methods=['GET'])
def get_strategies():
    """获取策略列表"""
    try:
        strategies = stock_pool_system.matcher.strategy_profiles
        result = []
        for s in strategies:
            result.append({
                'name': s.name,
                'type': s.type,
                'volatility_profile': s.volatility_profile,
                'min_liquidity': s.min_liquidity,
                'ideal_trend': s.ideal_trend,
                'min_return': s.min_return
            })
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 韬定律优化器集群 API ====================

@app.route('/api/tau/info', methods=['GET'])
def tau_info():
    """获取韬定律集群信息"""
    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        return jsonify({"success": True, "data": mgr.get_tau_cluster_info()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/tau/optimize', methods=['POST'])
def tau_optimize():
    """运行韬定律集群优化"""
    try:
        data = request.get_json()
        strategy_name = data.get('strategy', '')
        param_ranges = data.get('param_ranges')
        coarse_points = int(data.get('coarse_points', 30))
        refined_points = int(data.get('refined_points', 50))
        target = data.get('target', 'sharpe_ratio')

        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_tau_cluster_optimization(
            strategy_name=strategy_name,
            param_ranges=param_ranges,
            coarse_points=coarse_points,
            refined_points=refined_points,
            target=target
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/tau/eval', methods=['POST'])
def tau_eval():
    """单次参数评估（带缓存）"""
    try:
        data = request.get_json()
        strategy_name = data.get('strategy', '')
        params = data.get('params', {})

        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_tau_single_eval(strategy_name, params)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/tau/status', methods=['GET'])
def tau_status():
    """集群状态和统计"""
    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        info = mgr.get_tau_cluster_info()
        return jsonify({"success": True, "data": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/tau/bernoulli', methods=['POST'])
def tau_bernoulli():
    """韬定律集群: 伯努利-康达策略优化"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '伯努利-康达策略')
        iterations = int(data.get('iterations', 50))
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_tau_bernoulli_optimization(strategy_name=strategy_name, iterations=iterations)
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/tau/shepherd', methods=['POST'])
def tau_shepherd():
    """韬定律集群: 智能标的轮动68因子优化"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '智能标的轮动')
        coarse = int(data.get('coarse_points', 35))
        refined = int(data.get('refined_per_group', 15))
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        result = mgr.run_tau_shepherd_optimization(
            strategy_name=strategy_name,
            coarse_points=coarse,
            refined_per_group=refined,
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/tau/modules', methods=['GET'])
def tau_modules():
    """获取韬定律集群的策略感知模块列表"""
    try:
        from core.enhanced_strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        return jsonify(mgr.get_tau_cluster_modules())
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/static/<path:filename>')
def static_files(filename):
    """提供静态文件"""
    return send_from_directory('static', filename)


# ==================== 韬定律集成总线 API - 自动化流程 ====================

@app.route('/api/integration/info', methods=['GET'])
def integration_info():
    """获取集成总线状态信息"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        return jsonify(bus.get_workflow_report())
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/integration/optimize', methods=['POST'])
def integration_optimize():
    """流程1: 单策略韬定律自动优化"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '')
        if not strategy_name:
            return jsonify({"success": False, "error": "需要策略名称参数"}), 400
        
        coarse_points = int(data.get('coarse_points', 30))
        refined_points = int(data.get('refined_points', 15))
        
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.auto_optimize_strategy(
            strategy_name=strategy_name,
            coarse_points=coarse_points,
            refined_points_per_region=refined_points
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/integration/stock_pool', methods=['POST'])
def integration_stock_pool():
    """流程2: 策略-股票池自动匹配"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '')
        if not strategy_name:
            return jsonify({"success": False, "error": "需要策略名称参数"}), 400
        
        stock_count = int(data.get('stock_count', 20))
        
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.auto_match_stock_pool(
            strategy_name=strategy_name,
            stock_count=stock_count
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/integration/full_workflow', methods=['POST'])
def integration_full_workflow():
    """流程3: 完整自动化流程 (优化→股票池→交易配置)"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '')
        if not strategy_name:
            return jsonify({"success": False, "error": "需要策略名称参数"}), 400
        
        coarse_points = int(data.get('coarse_points', 25))
        refined_points = int(data.get('refined_points', 10))
        
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.auto_full_workflow(
            strategy_name=strategy_name,
            coarse_points=coarse_points,
            refined_points_per_region=refined_points
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/integration/batch_optimize', methods=['POST'])
def integration_batch_optimize():
    """流程4: 批量优化多个策略"""
    try:
        data = request.get_json() or {}
        strategy_names = data.get('strategies', [])
        if not strategy_names:
            return jsonify({"success": False, "error": "需要策略名称列表参数"}), 400
        
        coarse_points = int(data.get('coarse_points', 20))
        refined_points = int(data.get('refined_points', 10))
        
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.auto_batch_optimize(
            strategy_names=strategy_names,
            coarse_points=coarse_points,
            refined_points_per_region=refined_points
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/integration/apply', methods=['POST'])
def integration_apply():
    """流程5: 应用优化结果到交易配置"""
    try:
        data = request.get_json() or {}
        strategy_name = data.get('strategy', '')
        if not strategy_name:
            return jsonify({"success": False, "error": "需要策略名称参数"}), 400
        
        min_score = float(data.get('min_score', 0.3))
        
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        result = bus.auto_apply_optimization(
            strategy_name=strategy_name,
            min_score_threshold=min_score
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/integration/health_check', methods=['GET'])
def integration_health_check():
    """流程6: 系统健康检查与重优化"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        force = request.args.get('force', '').lower() in ['true', '1', 'yes']
        result = bus.check_and_reoptimize(force_reoptimize=force)
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("QS Robot 智能助手启动中...")
    print("访问地址: http://localhost:5001")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)

