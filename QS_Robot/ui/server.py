import os
import sys
import uuid
import subprocess
import atexit
import signal
import time
import logging
import urllib.request
import urllib.error
import json as _json
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for, make_response
from flask_cors import CORS

logger = logging.getLogger(__name__)

# 共享会话管理（消除 ui/server.py 和 api/gateway.py 之间的循环依赖）
from ui.shared.session import USERS, SESSIONS, FAILED_LOGINS, SESSION_TIMEOUT_HOURS, MAX_FAILED_LOGINS, LOGIN_LOCKOUT_MINUTES, create_session, get_session

def is_logged_in():
    """检查是否已登录（从请求中获取session）"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-Id')
    if not session_id:
        session_id = request.args.get('session_id')
    
    return get_session(session_id) is not None

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
from core.security import get_password_manager, get_audit_logger, OperationType

# 导入股票池智能管理系统
from stock_pool.main import StockPoolSystem

# 安全模块实例
password_manager = get_password_manager()
audit_logger = get_audit_logger()

# 初始化密码哈希（将明文密码转换为bcrypt哈希，确保登录验证通过）
for username, info in USERS.items():
    plain_pw = info['password']
    if not plain_pw.startswith('$2b$') and not plain_pw.startswith('$2a$'):
        info['password'] = password_manager.hash_password_str(plain_pw)
        print(f"[Auth] 用户 {username} 密码已哈希")

app = Flask(__name__, static_folder='static', template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

@app.after_request
def add_security_headers(response):
    """添加安全响应头"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; connect-src 'self'"
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if '/api/' in (request.path or ''):
        response.headers['Cache-Control'] = 'max-age=60, stale-while-revalidate=120'
    elif request.path.endswith(('.js', '.css', '.png', '.svg', '.woff2')):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

# 安全CORS配置：仅允许本地和可信域名
cors_origins = os.environ.get('CORS_ORIGINS', 'http://localhost:5003,http://127.0.0.1:5003')
CORS(app, resources={r"/api/*": {"origins": [o.strip() for o in cors_origins.split(',')]}})

# 禁用模板缓存
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# 初始化数据源和机器人核心
data_source = AuroraDataSource()
data_source.connect()
robot_core = QSRobotCore()

# 初始化股票池系统
stock_pool_system = StockPoolSystem()

# 将服务实例注入 app.config，供拆分后的路由模块使用
app.config['data_source'] = data_source
app.config['robot_core'] = robot_core
app.config['llm_manager'] = llm_manager
app.config['stock_pool_system'] = stock_pool_system

# ============================================================
# 注册API网关蓝图（豆包融合方案）
# 统一通过 gateway.py 管理所有 /api/* 路由，消除路由重复冲突
# ============================================================
try:
    from api.gateway import api_gateway
    app.register_blueprint(api_gateway)
    print("[API Gateway] API网关已注册（统一入口）")
    print("[API Gateway] - /api/aurora/* -> Aurora代理")
    print("[API Gateway] - /api/strategy/* -> 策略路由")
    print("[API Gateway] - /api/backtest/* -> 回测路由")
    print("[API Gateway] - /api/risk/* -> 风控路由")
    print("[API Gateway] - /api/broker/* -> 经纪商路由")
    print("[API Gateway] - /api/status -> 系统状态")
    print("[API Gateway] - /api/health -> 健康检查")
except ImportError as e:
    print(f"[API Gateway] API网关导入失败: {e}")
except Exception as e:
    print(f"[API Gateway] API网关注册失败: {e}")


# ============================================================
# 注册同花顺金融大师学院蓝图
# ============================================================
try:
    from ui.blueprints.ths_academy_bp import bp as ths_academy_bp
    app.register_blueprint(ths_academy_bp)
    print("[THS Academy] 同花顺学院已注册: /ths_academy/")
except ImportError as e:
    print(f"[THS Academy] 蓝图导入失败: {e}")
except Exception as e:
    print(f"[THS Academy] 蓝图注册失败: {e}")


# ============================================================
# 注册市场情报看板蓝图（单页Tab模式，Aurora UI内嵌模块）
# ============================================================
try:
    from ui.blueprints.market_intel_bp import bp as market_intel_bp
    app.register_blueprint(market_intel_bp)
    print("[Market Intel] 市场情报看板已注册: /market_intel/")
except ImportError as e:
    print(f"[Market Intel] 蓝图导入失败: {e}")
except Exception as e:
    print(f"[Market Intel] 蓝图注册失败: {e}")


# ============================================================
# 注册金融大师32策略集群选股器蓝图
# ============================================================
try:
    from ui.blueprints.cluster_selector_bp import bp as cluster_selector_bp
    app.register_blueprint(cluster_selector_bp)
    print("[Cluster Selector] 32策略集群选股器已注册: /cluster_selector/")
except ImportError as e:
    print(f"[Cluster Selector] 蓝图导入失败: {e}")
except Exception as e:
    print(f"[Cluster Selector] 蓝图注册失败: {e}")


# ============================================================
# 注册三入口策略矩阵集群路由（自创/Vibe智能体/金融大师32策略）
# 在 5003 端口 aurora_main.html 内嵌，不新增web页
# ============================================================
try:
    _aurora_path = os.environ.get(
        'AURORA_ROOT',
        config.get('aurora_system.base_path', '')
    )
    if not _aurora_path or not os.path.isdir(_aurora_path):
        raise ImportError(f"Aurora根路径未配置或不存在: {_aurora_path}")
    if _aurora_path not in sys.path:
        sys.path.insert(0, _aurora_path)
    from monitor.cluster_routes import register_cluster_routes
    register_cluster_routes(app)
    print("[Cluster Routes] 三入口策略矩阵集群已挂接到5003端口app")
except ImportError as e:
    print(f"[Cluster Routes] Aurora集群路由导入失败: {e}")
except Exception as e:
    print(f"[Cluster Routes] Aurora集群路由挂接失败: {e}")


# ============================================================
# 模板路由（页面渲染）
# ============================================================

@app.route('/dashboard')
def dashboard_home():
    """控制台首页 - 策略优化+Vibe智能体分析+股票池"""
    return render_template('dashboard.html')


@app.route('/')
def root_home():
    """根路径 - 跳转到控制台首页"""
    return redirect(url_for('dashboard_home'))


@app.route('/chat')
def chat_page():
    """智能助手对话页面 - 可与AI对话"""
    if not is_logged_in():
        return redirect(url_for('login_page'))
    return render_template('index.html')


@app.route('/robot')
def robot_alt():
    """智能助手 - 跳转到首页（含机器人浮标）"""
    return redirect(url_for('dashboard_home'))


@app.route('/login')
def login_page():
    """登录页面"""
    return render_template('login.html')


@app.route('/logout')
def logout():
    """登出"""
    session_id = request.cookies.get('session_id')
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    response = redirect(url_for('login_page'))
    response.set_cookie('session_id', '', expires=0, httponly=True, samesite='Strict')
    return response


@app.route('/main_system')
def main_system_page():
    """QS-Robot 外壳 - 包含导航栏、七大进入模块、模型切换、技术分析"""
    return render_template('main_system.html')


@app.route('/aurora_main')
def aurora_main_page():
    """Aurora 量化主系统 - 策略管理核心、优化器中心、完整工作流（用户主入口）"""
    return render_template('aurora_main.html', entry_mode='main', entry_title='Aurora 主系统')


@app.route('/aurora_core')
def aurora_core_page():
    """Aurora 量化内核 - API直连调试入口（开发者/运维使用，直连5002内核）"""
    return render_template('aurora_main.html', entry_mode='core', entry_title='Aurora 内核直连')


@app.route('/maintenance')
def maintenance_page():
    """系统维护页面 - 安全配置、用户管理、告警系统、系统监控"""
    return render_template('maintenance.html')


@app.route('/stock_pool')
def stock_pool_page():
    """股票池智能管理系统页面"""
    return render_template('stock_pool.html')


@app.route('/technical_analysis')
def technical_analysis_page():
    """技术分析系统页面"""
    return render_template('technical_analysis.html')


@app.route('/cline-agent')
def cline_agent_page():
    """Cline智能体交互页面"""
    return render_template('cline_agent.html')


@app.route('/model-switch')
def model_switch_page():
    """模型切换面板页面"""
    return render_template('model_switch.html')


@app.route('/vibe_analysis')
def vibe_analysis_page():
    """Vibe-Trading智能体可视化分析页面"""
    return render_template('vibe_analysis.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """提供静态文件"""
    return send_from_directory('static', filename)


# ============================================================
# 注册所有UI子路由（从拆分后的模块加载）
# 路由模块: ui/routes/ (auth, stock_pool, tau, integration, vibe, agent, llm, cline, system, desktop)
# 管理器:   ui/managers/ (aurora_manager, vibe_manager)
# ============================================================
from ui.routes import register_all_routes
register_all_routes(app)
print("[UI Routes] UI子路由已注册（模块化拆分）")


# ============================================================
# Aurora 5002 子进程管理（一键启动）
# ============================================================
from ui.managers.aurora_manager import (
    start_aurora_backend as _start_aurora_backend,
    stop_aurora_backend as _stop_aurora_backend,
    is_aurora_running as _is_aurora_running,
    _AURORA_PORT,
)
from ui.managers.vibe_manager import stop_vibe_services as _stop_vibe_services


def _signal_handler(signum, frame):
    """信号处理 - 优雅关闭"""
    print(f"\n收到信号 {signum}，正在关闭系统...")
    _stop_aurora_backend()
    _stop_vibe_services()
    sys.exit(0)


if __name__ == '__main__':
    # 注册信号处理（Ctrl+C 优雅关闭）
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # 注册 atexit 清理（确保子进程被终止）
    atexit.register(_stop_aurora_backend)
    atexit.register(_stop_vibe_services)

    # 检查是否跳过 Aurora 自动启动
    skip_aurora = os.environ.get('SKIP_AURORA_START', '').lower() in ('1', 'true', 'yes')
    if skip_aurora:
        print("[Aurora] SKIP_AURORA_START=1，跳过自动启动 5002")
        print("  请确保 5002 已手动启动: python visualization.py")
    else:
        _start_aurora_backend()

    # 从配置读取端口
    shell_port = config.get('port_allocation.qs_robot_shell', 5003)
    # SSL配置
    ssl_enabled = config.get('ssl.enabled', False)
    ssl_context = None
    if ssl_enabled:
        cert_path = config.get('ssl.cert_path', '')
        key_path = config.get('ssl.key_path', '')
        if cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = (cert_path, key_path)
            print(f"[SSL] 已启用 HTTPS")
        else:
            print(f"[SSL] 证书文件不存在，回退到 HTTP")
    protocol = "https" if ssl_context else "http"

    print("=" * 55)
    print("  QS Robot 智能助手 (5003) - 系统总控总线")
    print(f"  主控面板: {protocol}://localhost:{shell_port}")
    print(f"  Aurora内核: http://127.0.0.1:{_AURORA_PORT} (自动启动)")
    print("  按 Ctrl+C 停止所有服务")
    print("=" * 55)

    try:
        app.run(host='0.0.0.0', port=shell_port, debug=True, use_reloader=False, threaded=True,
                ssl_context=ssl_context)
    finally:
        _stop_aurora_backend()