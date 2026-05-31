#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  QS Robot 桌面端 V3.0                                      ║
║  Aurora深度集成 — Flask Web控制面板                        ║
╚══════════════════════════════════════════════════════════════╝

启动方式:
  1. 双击 启动QS机器人.bat
  2. 命令行: python qs_robot_desktop.py
  3. 命令行: python qs_robot_desktop.py --port 5001

访问: http://localhost:5001
"""

import os, sys, json, time, threading, logging
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context

logging.basicConfig(level=logging.INFO, format='[%(asctime)s][QBot-Desktop] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger('QBot-Desktop')

# DeepSeek / Qwen 客户端（AI 对话助手）
_deepseek_client = None
_qwen_client = None

def _get_ai_client(model: str = "deepseek"):
    """懒加载AI客户端"""
    global _deepseek_client, _qwen_client
    if model == "qwen" or model == "通义千问":
        if _qwen_client is None:
            try:
                from qwen_client import QwenClient
                api_key = os.environ.get("DASHSCOPE_API_KEY", "")
                if api_key:
                    _qwen_client = QwenClient(api_key=api_key)
                    logger.info("✅ Qwen 客户端已加载")
            except Exception as e:
                logger.warning(f"Qwen 客户端加载失败: {e}")
        return _qwen_client
    # 默认 deepseek
    if _deepseek_client is None:
        try:
            from deepseek_client import DeepSeekClient
            api_key = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if api_key:
                _deepseek_client = DeepSeekClient(api_key=api_key)
                logger.info("✅ DeepSeek 客户端已加载")
            else:
                logger.warning("⚠️ DEEPSEEK_API_KEY 未设置，AI 助手暂不可用")
        except Exception as e:
            logger.warning(f"DeepSeek 客户端加载失败: {e}")
    return _deepseek_client

# AI 助手系统提示词 — Aurora 全局知识库
AI_SYSTEM_PROMPT = """你是一个高级量化交易系统专家助手，代号「Aurora QBot」，运行在Aurora量化交易平台上。

你是整个系统的智能神经中枢，能为用户解答系统功能、策略知识、回测方法、优化技巧、风控规则、部署运维等问题。

## 你的知识范围

### 1. 系统架构
- Aurora 是基于 Python 3.9+ 的量化交易平台
- 核心技术栈：Flask Web、SQLite (WAL模式)、DeepSeek V4 AI引擎、Qwen AI引擎
- 数据源：东方财富 + Yahoo Finance + Tushare + AKShare（四源冗余）
- 部署方式：Docker + Gunicorn + HTTPS
- 监控体系：Prometheus + Grafana
- QS Robot 是 Aurora 的桌面控制面板 + 智能助手，端口5001

### 2. 策略管理（33个策略）
- 用户可以通过策略面板查看、启动、停止策略
- 策略分类包括：RL强化学习、傅里叶分析、HMM隐马尔可夫、动量策略、网格策略等
- 常用策略：FourierRLStrategy（傅里叶强化学习）、GaussianHMMStrategy（高斯隐马尔可夫）、SectorMomentumStrategy（板块动量）
- 启动策略需要指定资金量（默认100000元）
- 策略状态可在面板实时查看

### 3. 回测中心
- 回测需要选择策略名称和回测天数（1-365天）
- 回测结果关键指标：总收益(%)、夏普比率、最大回撤(%)、胜率(%)、总交易次数
- 夏普比率 > 1 表示风险调整后收益优秀
- 最大回撤越小越好，表示策略抗风险能力强
- 回测使用模拟市场数据，结果仅供参考

### 4. 策略优化器
- 支持参数优化：设定参数范围后自动迭代寻优
- 使用遗传算法或贝叶斯优化
- 优化迭代次数建议 50-200 次
- 优化结果会保存为 JSON 配置文件

### 5. 风控系统
- 资金安全检查：检查 fund_security 模块
- 交易安全检查：检查 TradeSecurity 白名单、熔断、限额
- 数据源检查：验证数据源可用性
- 风控检查按钮可一键运行完整检查

### 6. 交易信号
- 信号来源：策略实时分析市场数据后生成
- 信号包含：买入/卖出/持有建议及置信度
- 可在事件总线面板查看所有信号

### 7. 数据源管理
- 四源切换机制：主数据源故障时自动切换备用源
- 东方财富是国内A股最稳定数据源
- Yahoo Finance 支持国际股票
- Tushare 需要 Token 注册

### 8. 使用帮助
- 启动方式：双击 启动QS机器人.bat 或 python qs_robot_desktop.py
- 默认地址：http://localhost:5001
- 左侧导航切换不同功能面板
- 右上角按钮可执行快速回测和风控检查
- 系统会自动连接 Aurora 核心引擎

### 9. 故障排查
- 如果 QBot 显示"本地模式"，说明 Aurora 核心引擎未启动，先启动 Aurora 主服务
- 如果回测无数据，检查数据源连接（通常是 Yahoo Finance 网络问题）
- 如果策略列表为空，确认 Aurora 策略注册表完整

## 回答规则
- 用简体中文简洁回答
- 涉及具体操作时给出明确步骤
- 涉及数值时给出建议范围
- 遇到不知道的问题，建议用户查看具体模块文档
- 保持专业、友好、高效的态度"""

# 系统托盘
TRAY_AVAILABLE = False
try:
    from qbot_tray import QBotTray
    TRAY_AVAILABLE = True
except Exception:
    pass

# ============================================================
# Flask应用
# ============================================================
app = Flask(__name__, static_folder='static', static_url_path='/static')

# ============================================================
# QBot核心实例
# ============================================================
qs_robot = None
AURORA_CONNECTED = False

def init_robot():
    global qs_robot, AURORA_CONNECTED
    try:
        from qs_robot_core import QSRobotCore
        qs_robot = QSRobotCore()
        ok = qs_robot.initialize(force_connect=True)
        AURORA_CONNECTED = qs_robot._initialized
        return ok
    except Exception as e:
        logger.error(f"QBot初始化失败: {e}")
        qs_robot = None
        AURORA_CONNECTED = False
        return False

# ============================================================
# QBot状态API (供Aurora主界面查询)
# ============================================================
@app.route('/api/qbot/ping')
def api_qbot_ping():
    """供Aurora主界面检测QBot是否在线"""
    try:
        strategy_count = len(qs_robot.get_all_strategies()) if qs_robot else 0
    except Exception:
        strategy_count = 0
    return jsonify({
        "success": True,
        "online": AURORA_CONNECTED or qs_robot is not None,
        "aurora_connected": AURORA_CONNECTED,
        "version": "3.0",
        "strategy_count": strategy_count,
        "timestamp": time.time()
    })

# ============================================================
# AI 对话 API (SSE 流式)
# ============================================================
# 对话历史存储（按 session 简单维护）
_chat_histories: Dict[str, List[Dict[str, str]]] = {}

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """AI 对话助手 — SSE 流式"""
    data = request.json or {}
    message = (data.get('message') or '').strip()
    session_id = data.get('session_id', 'default')
    model_choice = data.get('model', 'deepseek')

    if not message:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    # 初始化/获取对话历史
    if session_id not in _chat_histories:
        _chat_histories[session_id] = []
    history = _chat_histories[session_id]

    # 添加用户消息
    history.append({"role": "user", "content": message})
    # 保持历史长度
    if len(history) > 30:
        history = history[-30:]
        _chat_histories[session_id] = history

    client = _get_ai_client(model_choice)

    if client is None:
        # 离线模式：返回基于规则的回答
        def offline_reply():
            reply = _offline_assistant_reply(message)
            history.append({"role": "assistant", "content": reply})
            yield f"data: {json.dumps({'chunk': reply, 'done': True}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(offline_reply()), mimetype='text/event-stream')

    # 在线模式：调用 DeepSeek/Qwen 流式
    def stream_chat():
        full_reply = ""
        try:
            # 构建消息列表
            messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + history
            stream = client.chat(
                messages=messages,
                model="deepseek-v4-flash",
                temperature=0.7,
                max_tokens=2048,
                stream=True
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_reply += delta.content
                        yield f"data: {json.dumps({'chunk': delta.content, 'done': False}, ensure_ascii=False)}\n\n"
            history.append({"role": "assistant", "content": full_reply})
            _chat_histories[session_id] = history
            yield f"data: {json.dumps({'chunk': '', 'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"AI 对话错误: {e}")
            error_msg = f"抱歉，AI 服务暂时不可用：{str(e)[:100]}"
            full_reply = error_msg
            history.append({"role": "assistant", "content": full_reply})
            _chat_histories[session_id] = history
            yield f"data: {json.dumps({'chunk': error_msg, 'done': True, 'error': True}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(stream_chat()), mimetype='text/event-stream')

@app.route('/api/chat/history', methods=['GET'])
def api_chat_history():
    """获取对话历史"""
    session_id = request.args.get('session_id', 'default')
    return jsonify({"success": True, "data": _chat_histories.get(session_id, [])})

@app.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """清空对话历史"""
    data = request.json or {}
    session_id = data.get('session_id', 'default')
    _chat_histories.pop(session_id, None)
    return jsonify({"success": True, "message": "对话历史已清空"})

def _offline_assistant_reply(message: str) -> str:
    """离线模式：基于关键词的规则回答"""
    msg_lower = message.lower()
    # 策略相关
    if any(k in msg_lower for k in ['策略', 'strategy']):
        return "Aurora 系统包含33个策略，涵盖RL强化学习、傅里叶分析、HMM隐马尔可夫、动量策略、网格策略等。您可以在「策略管理」面板查看全部策略列表。如需回测某个策略，请前往「回测中心」选择策略后运行。"
    if any(k in msg_lower for k in ['回测', 'backtest']):
        return "回测功能使用方法：1) 在左侧导航选择「回测中心」；2) 从下拉框选择要测试的策略；3) 设置回测天数（建议30-120天）；4) 点击「运行」按钮。回测结果会显示总收益、夏普比率、最大回撤、胜率等关键指标。"
    if any(k in msg_lower for k in ['优化', 'optimize', '参数']):
        return "策略优化器支持自动化参数寻优。通过 /api/optimize 接口提交优化任务，系统会使用遗传算法或贝叶斯优化方法迭代搜索最优参数。建议迭代次数：50-200次。优化结果会保存为JSON配置文件。"
    if any(k in msg_lower for k in ['风控', 'risk', '安全']):
        return "Aurora 风控系统覆盖三大模块：1) 资金安全检查 — 确保资金使用合规；2) 交易安全检查 — 白名单、熔断机制、限额控制；3) 数据源检查 — 验证数据可用性。点击「风控监控」面板的「检查」按钮一键运行。"
    if any(k in msg_lower for k in ['数据源', 'data source', 'yahoo', 'tushare', '东方财富']):
        return "Aurora 支持四源数据冗余：东方财富（A股首选）、Yahoo Finance（国际股票）、Tushare（需Token）、AKShare（开源免费）。系统会自动在主数据源故障时切换备用源，确保数据连续性。"
    if any(k in msg_lower for k in ['启动', 'start', '运行']):
        return "启动方式：1) 双击「启动QS机器人.bat」自动启动；2) 命令行执行 python qs_robot_desktop.py；3) 指定端口 python qs_robot_desktop.py --port 5001。启动后浏览器会自动打开 http://localhost:5001。"
    if any(k in msg_lower for k in ['部署', 'deploy', 'docker']):
        return "Aurora 支持 Docker 容器化部署，使用 docker-compose.yml 一键启动。也支持 Gunicorn + HTTPS 生产环境部署。详细步骤请参考 DEPLOYMENT_GUIDE.md。"
    if any(k in msg_lower for k in ['你好', 'hello', '嗨']):
        return "👋 您好！我是 Aurora QBot 智能助手，可以帮您解答系统功能、策略使用、回测方法、优化技巧、风控规则等问题。请随时提问！"
    if any(k in msg_lower for k in ['功能', 'feature', '能做什么']):
        return "QS Robot 是 Aurora 的桌面控制面板，提供以下核心功能：📈 策略管理（33个策略）、🧪 回测中心、🛡️ 风控监控、📡 事件总线、💹 交易信号、📝 系统日志。左侧导航可切换不同面板。"
    # 默认回答
    return "感谢您的提问。Aurora QBot 可以解答系统架构、策略管理、回测优化、风控规则、数据源管理等问题。如您的问题涉及具体操作，可尝试在对应面板中直接查看。如需AI增强回答，请配置 DEEPSEEK_API_KEY 环境变量。"

# QQ风格深色主题HTML模板
# ============================================================
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QS Robot — Aurora深度集成控制台</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{font-family:'Microsoft YaHei','PingFang SC',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh;display:flex;}
        /* 侧边栏 */
        .sidebar{width:240px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;}
        .sidebar-header{padding:20px 16px;border-bottom:1px solid #30363d;}
        .sidebar-header h2{color:#58a6ff;font-size:18px;display:flex;align-items:center;gap:8px;}
        .sidebar-header .robot-icon{font-size:28px;}
        .sidebar-header .subtitle{font-size:11px;color:#8b949e;margin-top:4px;}
        .sidebar-nav{flex:1;padding:12px 0;overflow-y:auto;}
        .nav-item{padding:10px 20px;cursor:pointer;display:flex;align-items:center;gap:10px;font-size:14px;color:#8b949e;transition:all 0.2s;border-left:3px solid transparent;}
        .nav-item:hover{background:#1c2128;color:#c9d1d9;}
        .nav-item.active{background:#1c2128;color:#58a6ff;border-left-color:#58a6ff;}
        .nav-item .nav-icon{font-size:18px;width:24px;text-align:center;}
        .nav-item .badge{background:#238636;color:#fff;font-size:10px;padding:2px 6px;border-radius:10px;margin-left:auto;}
        .sidebar-footer{padding:16px;border-top:1px solid #30363d;font-size:11px;color:#484f58;}
        .status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;}
        .status-dot.online{background:#3fb950;box-shadow:0 0 6px #3fb950;}
        .status-dot.offline{background:#f85149;box-shadow:0 0 6px #f85149;}
        /* 主内容区 */
        .main-content{margin-left:240px;flex:1;padding:24px;display:flex;flex-direction:column;gap:20px;}
        .top-bar{display:flex;justify-content:space-between;align-items:center;padding-bottom:16px;border-bottom:1px solid #30363d;}
        .top-bar h1{font-size:24px;color:#f0f6fc;}
        .top-bar .controls{display:flex;gap:10px;}
        .btn{padding:8px 16px;border:1px solid #30363d;border-radius:6px;background:#21262d;color:#c9d1d9;cursor:pointer;font-size:13px;transition:all 0.2s;}
        .btn:hover{background:#30363d;border-color:#58a6ff;}
        .btn-primary{background:#238636;border-color:#2ea043;color:#fff;}
        .btn-primary:hover{background:#2ea043;}
        .btn-danger{background:#da3633;border-color:#f85149;color:#fff;}
        .btn-danger:hover{background:#f85149;}
        /* 状态卡片 */
        .status-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;}
        .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;}
        .card-label{font-size:12px;color:#8b949e;text-transform:uppercase;}
        .card-value{font-size:24px;font-weight:bold;color:#f0f6fc;margin:6px 0;}
        .card-sub{font-size:12px;color:#484f58;}
        .card-green{border-left:3px solid #3fb950;}
        .card-blue{border-left:3px solid #58a6ff;}
        .card-yellow{border-left:3px solid #d29922;}
        .card-red{border-left:3px solid #f85149;}
        /* 面板区 */
        .panel-section{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
        .panel{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;}
        .panel-header{background:#1c2128;padding:12px 16px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;}
        .panel-header h3{font-size:14px;color:#f0f6fc;display:flex;align-items:center;gap:6px;}
        .panel-body{max-height:500px;overflow-y:auto;}
        /* 策略列表 */
        .strategy-item{padding:10px 16px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center;font-size:13px;}
        .strategy-item:hover{background:#1c2128;}
        .strategy-name{color:#58a6ff;font-weight:500;}
        .strategy-category{color:#8b949e;font-size:11px;padding:2px 6px;background:#21262d;border-radius:4px;}
        .strategy-status{font-size:11px;padding:2px 8px;border-radius:10px;}
        .strategy-status.active{background:#0d3320;color:#3fb950;}
        .strategy-status.inactive{background:#21262d;color:#484f58;}
        /* 回测结果 */
        .bt-result{padding:16px;}
        .bt-row{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-bottom:1px solid #21262d;}
        .bt-metric{color:#8b949e;}
        .bt-value{color:#f0f6fc;font-weight:bold;}
        .bt-value.positive{color:#3fb950;}
        .bt-value.negative{color:#f85149;}
        /* 风险表格 */
        .risk-table{width:100%;font-size:13px;}
        .risk-table th{text-align:left;padding:8px 16px;color:#8b949e;background:#1c2128;border-bottom:1px solid #30363d;}
        .risk-table td{padding:8px 16px;border-bottom:1px solid #21262d;}
        /* 日志区 */
        .log-area{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;font-family:'Consolas','Courier New',monospace;font-size:12px;color:#8b949e;max-height:300px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;}
        .log-line{padding:2px 0;}
        .log-line.error{color:#f85149;}
        .log-line.warn{color:#d29922;}
        .log-line.info{color:#58a6ff;}
        .log-line.success{color:#3fb950;}
        /* 响应式 */
        @media(max-width:900px){.sidebar{width:60px;}.sidebar-header h2,.sidebar-header .subtitle,.nav-item span:not(.nav-icon),.badge{display:none;}.main-content{margin-left:60px;}.panel-section{grid-template-columns:1fr;}}
    </style>
</head>
<body>
    <!-- 侧边栏 -->
    <aside class="sidebar">
        <div class="sidebar-header">
            <h2><span class="robot-icon">🤖</span> QS Robot</h2>
            <div class="subtitle">Aurora Deep Integration V3.0</div>
        </div>
        <nav class="sidebar-nav">
            <div class="nav-item active" data-panel="dashboard">
                <span class="nav-icon">📊</span> 控制面板
            </div>
            <div class="nav-item" data-panel="strategies">
                <span class="nav-icon">📈</span> 策略管理
                <span class="badge" id="strategy-count">0</span>
            </div>
            <div class="nav-item" data-panel="backtest">
                <span class="nav-icon">🧪</span> 回测中心
            </div>
            <div class="nav-item" data-panel="risk">
                <span class="nav-icon">🛡️</span> 风控监控
            </div>
            <div class="nav-item" data-panel="events">
                <span class="nav-icon">📡</span> 事件总线
            </div>
            <div class="nav-item" data-panel="signals">
                <span class="nav-icon">💹</span> 交易信号
            </div>
            <div class="nav-item" data-panel="chat">
                <span class="nav-icon">💬</span> AI 助手
        <span class="badge" style="background:#db61a2;">AI</span>
            </div>
            <div class="nav-item" data-panel="logs">
                <span class="nav-icon">📝</span> 系统日志
            </div>
        </nav>
        <div class="sidebar-footer" id="sidebar-status">
            <span class="status-dot offline"></span> 等待连接...
        </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
        <div class="top-bar">
            <h1>🔭 QS Robot 控制台</h1>
            <div class="controls">
                <button class="btn" onclick="refreshAll()">🔄 刷新</button>
                <button class="btn btn-primary" onclick="runBacktest()">🧪 快速回测</button>
                <button class="btn btn-danger" onclick="runRiskCheck()">🛡️ 风控检查</button>
            </div>
        </div>

        <!-- 状态卡片 -->
        <div class="status-cards" id="status-cards">
            <div class="card card-blue"><div class="card-label">系统模式</div><div class="card-value" id="mode-text">—</div><div class="card-sub">Aurora集成状态</div></div>
            <div class="card card-green"><div class="card-label">可用策略</div><div class="card-value" id="strat-count">0</div><div class="card-sub">来自策略注册表</div></div>
            <div class="card card-yellow"><div class="card-label">活跃任务</div><div class="card-value" id="active-tasks">0</div><div class="card-sub">回测/优化任务</div></div>
            <div class="card card-red"><div class="card-label">风控事件</div><div class="card-value" id="risk-count">0</div><div class="card-sub">最近事件数</div></div>
            <div class="card"><div class="card-label">交易信号</div><div class="card-value" id="signal-count">0</div><div class="card-sub">实时策略信号</div></div>
            <div class="card"><div class="card-label">运行时间</div><div class="card-value" id="uptime">—</div><div class="card-sub">秒</div></div>
        </div>

        <!-- 面板区 -->
        <div class="panel-section">
            <!-- 策略列表 -->
            <div class="panel">
                <div class="panel-header">
                    <h3>📈 可用策略</h3>
                    <button class="btn" onclick="refreshStrategies()">刷新</button>
                </div>
                <div class="panel-body" id="strategy-list">
                    <div class="bt-result" style="text-align:center;color:#484f58;padding:40px;">加载中...</div>
                </div>
            </div>

            <!-- 回测结果 -->
            <div class="panel">
                <div class="panel-header">
                    <h3>🧪 最近回测</h3>
                    <select id="backtest-strategy" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:6px;border-radius:4px;font-size:12px;"></select>
                    <input type="number" id="backtest-days" value="30" min="1" max="365" style="width:60px;background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:6px;border-radius:4px;font-size:12px;">
                    <button class="btn btn-primary" onclick="runBacktest()">运行</button>
                </div>
                <div class="panel-body" id="backtest-result">
                    <div class="bt-result" style="text-align:center;color:#484f58;padding:40px;">选择策略后运行回测</div>
                </div>
            </div>

            <!-- 风控状态 -->
            <div class="panel">
                <div class="panel-header">
                    <h3>🛡️ 风控检查</h3>
                    <button class="btn" onclick="runRiskCheck()">检查</button>
                </div>
                <div class="panel-body" id="risk-result">
                    <div class="bt-result" style="text-align:center;color:#484f58;padding:40px;">点击检查按钮</div>
                </div>
            </div>

            <!-- 事件总线 -->
            <div class="panel">
                <div class="panel-header">
                    <h3>📡 事件总线</h3>
                    <span style="font-size:11px;color:#8b949e;" id="bus-events-count">0事件</span>
                </div>
                <div class="panel-body" id="events-list" style="max-height:400px;">
                    <div class="bt-result" style="text-align:center;color:#484f58;padding:40px;">无事件</div>
                </div>
            </div>
        </div>

        <!-- AI 对话面板 -->
        <div class="panel" style="grid-column:1/-1;display:none;" id="chat-panel">
            <div class="panel-header">
                <h3>💬 AI 智能助手</h3>
                <select id="chat-model" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:6px;border-radius:4px;font-size:12px;margin-right:8px;">
                    <option value="deepseek">DeepSeek V4</option>
                    <option value="qwen">通义千问</option>
                    <option value="offline" selected>离线模式</option>
                </select>
                <button class="btn" onclick="clearChatHistory()">🗑️ 清空</button>
            </div>
            <div class="panel-body" id="chat-body" style="height:420px;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;">
                <div style="text-align:center;color:#8b949e;padding:80px 20px;">
                    <div style="font-size:48px;margin-bottom:16px;">💬</div>
                    <div style="font-size:16px;margin-bottom:8px;">欢迎使用 AI 智能助手</div>
                    <div style="font-size:12px;">可以问我关于策略、回测、优化、风控等任何问题</div>
                    <div style="font-size:11px;color:#484f58;margin-top:12px;">
                        💡 提示：配置 DEEPSEEK_API_KEY 可启用 AI 增强回答
                    </div>
                </div>
            </div>
            <div style="padding:12px 16px;border-top:1px solid #30363d;display:flex;gap:8px;background:#1c2128;">
                <input type="text" id="chat-input" placeholder="输入您的问题，按Enter发送..."
                    style="flex:1;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:10px 14px;border-radius:6px;font-size:13px;"
                    onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMessage();}">
                <button class="btn btn-primary" onclick="sendChatMessage()" id="chat-send-btn" style="min-width:64px;">🚀 发送</button>
            </div>
        </div>

        <!-- 日志 -->
        <div class="panel" style="grid-column:1/-1;">
            <div class="panel-header">
                <h3>📝 系统日志</h3>
                <button class="btn" onclick="document.getElementById('log-body').innerHTML='';">清空</button>
            </div>
            <div class="panel-body log-area" id="log-body"></div>
        </div>
    </main>

    <script>
        // ============================================================
        // QBot Desktop 前端逻辑
        // ============================================================
        const POLL_INTERVAL = 5000; // 5秒轮询
        
        // 日志
        function addLog(msg, type='info') {
            const logBody = document.getElementById('log-body');
            const line = document.createElement('div');
            line.className = `log-line ${type}`;
            line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
            logBody.appendChild(line);
            logBody.scrollTop = logBody.scrollHeight;
        }
        
        // 面板切换
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function() {
                document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                this.classList.add('active');
                const panel = this.dataset.panel;
                // 隐藏所有面板
                document.querySelectorAll('.panel-section').forEach(p => p.style.display = 'grid');
                document.getElementById('chat-panel').style.display = 'none';
                document.getElementById('log-panel-section').style.display = 'block';
                // 显示对应内容
                if (panel === 'chat') {
                    document.querySelectorAll('.panel-section').forEach(p => p.style.display = 'none');
                    document.getElementById('chat-panel').style.display = 'block';
                    document.getElementById('log-panel-section').style.display = 'none';
                    document.getElementById('status-cards').style.display = 'none';
                } else {
                    document.getElementById('status-cards').style.display = 'grid';
                }
                if (panel === 'strategies') refreshStrategies();
                if (panel === 'risk') runRiskCheck();
                if (panel === 'events') refreshEvents();
                if (panel === 'signals') refreshSignals();
                if (panel === 'dashboard') {
                    document.querySelectorAll('.panel-section').forEach(p => p.style.display = 'grid');
                    document.getElementById('status-cards').style.display = 'grid';
                    document.getElementById('chat-panel').style.display = 'none';
                }
            });
        });
        
        // 全量刷新
        async function refreshAll() {
            addLog('全量刷新...', 'info');
            await fetchStatus();
            await refreshStrategies();
            await refreshEvents();
            await refreshSignals();
        }
        
        // 获取系统状态
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                if (data.success) {
                    const s = data.data;
                    document.getElementById('mode-text').textContent = s.dual_core ? '🔗 双核联动' : '⚠️ 降级';
                    document.getElementById('strat-count').textContent = s.strategy_count;
                    document.getElementById('active-tasks').textContent = s.active_tasks;
                    document.getElementById('risk-count').textContent = s.risk_events_count;
                    document.getElementById('signal-count').textContent = s.signal_count;
                    document.getElementById('uptime').textContent = Math.floor(s.uptime_seconds);
                    document.getElementById('strategy-count').textContent = s.strategy_count;
                    document.getElementById('bus-events-count').textContent = (s.bus_stats?.events_published || 0) + '事件';
                    
                    // 侧边栏状态指示
                    const statusDot = document.querySelector('.status-dot');
                    const statusText = document.getElementById('sidebar-status');
                    if (s.deep_integration) {
                        statusDot.className = 'status-dot online';
                        statusText.innerHTML = '<span class="status-dot online"></span> Aurora已连接';
                    } else {
                        statusDot.className = 'status-dot offline';
                        statusText.innerHTML = '<span class="status-dot offline"></span> 本地模式';
                    }
                    
                    // 更新策略下拉框
                    if (s.strategies && s.strategies.length > 0) {
                        const sel = document.getElementById('backtest-strategy');
                        sel.innerHTML = s.strategies.map(st => `<option value="${st.name}">${st.name} [${st.category}]</option>`).join('');
                    }
                }
            } catch(e) {
                addLog('状态获取失败: ' + e.message, 'error');
            }
        }
        
        // 策略列表
        async function refreshStrategies() {
            try {
                const res = await fetch('/api/strategies');
                const data = await res.json();
                const list = document.getElementById('strategy-list');
                if (data.success && data.data.strategies) {
                    const strats = data.data.strategies;
                    list.innerHTML = strats.map(s => `
                        <div class="strategy-item">
                            <div>
                                <span class="strategy-name">${s.name}</span>
                                <span class="strategy-category">${s.category || 'unknown'}</span>
                            </div>
                            <span class="strategy-status ${s.active ? 'active' : 'inactive'}">${s.active ? '● 运行中' : '○ 待命'}</span>
                        </div>
                    `).join('');
                    document.getElementById('strat-count').textContent = data.data.count;
                    document.getElementById('strategy-count').textContent = data.data.count;
                    
                    // 更新回测策略下拉框
                    const sel = document.getElementById('backtest-strategy');
                    sel.innerHTML = strats.map(s => `<option value="${s.name}">${s.name} [${s.category||'?'}]</option>`).join('');
                }
            } catch(e) {
                addLog('策略列表获取失败: ' + e.message, 'error');
            }
        }
        
        // 回测
        async function runBacktest() {
            const strategy = document.getElementById('backtest-strategy').value;
            const days = parseInt(document.getElementById('backtest-days').value) || 30;
            addLog(`提交回测: ${strategy} (${days}天)`, 'info');
            
            const resultDiv = document.getElementById('backtest-result');
            resultDiv.innerHTML = '<div class="bt-result" style="text-align:center;padding:40px;">⏳ 回测进行中...</div>';
            
            try {
                const res = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({strategy_name: strategy, days: days})
                });
                const data = await res.json();
                
                if (data.success) {
                    addLog(`回测已提交: ${data.data.task_id}`, 'success');
                    // 轮询结果
                    pollBacktestResult(data.data.task_id, resultDiv);
                } else {
                    resultDiv.innerHTML = `<div class="bt-result" style="text-align:center;padding:40px;color:#f85149;">❌ ${data.error || '回测失败'}</div>`;
                }
            } catch(e) {
                addLog('回测请求失败: ' + e.message, 'error');
            }
        }
        
        async function pollBacktestResult(taskId, resultDiv, maxAttempts=12) {
            let attempts = 0;
            while (attempts < maxAttempts) {
                await new Promise(r => setTimeout(r, 2000));
                try {
                    const res = await fetch(`/api/task/${taskId}`);
                    const data = await res.json();
                    if (data.success && data.data.result) {
                        const r = data.data.result;
                        resultDiv.innerHTML = `
                            <div class="bt-result">
                                <div class="bt-row"><span class="bt-metric">📊 总收益</span><span class="bt-value ${r.total_return_pct >= 0 ? 'positive' : 'negative'}">${r.total_return_pct}%</span></div>
                                <div class="bt-row"><span class="bt-metric">📈 夏普比率</span><span class="bt-value">${r.sharpe_ratio}</span></div>
                                <div class="bt-row"><span class="bt-metric">📉 最大回撤</span><span class="bt-value negative">${r.max_drawdown}%</span></div>
                                <div class="bt-row"><span class="bt-metric">🎯 胜率</span><span class="bt-value">${r.win_rate}%</span></div>
                                <div class="bt-row"><span class="bt-metric">💹 总交易</span><span class="bt-value">${r.total_trades || 'N/A'}</span></div>
                                <div class="bt-row"><span class="bt-metric">🔗 来源</span><span class="bt-value">${r.source || r.confidence || 'N/A'}</span></div>
                                ${r.confidence_interval ? `<div class="bt-row"><span class="bt-metric">📐 置信区间</span><span class="bt-value">[${r.confidence_interval[0]}, ${r.confidence_interval[1]}]</span></div>` : ''}
                                ${r.warning ? `<div style="color:#d29922;margin-top:8px;font-size:12px;">⚠️ ${r.warning}</div>` : ''}
                            </div>
                        `;
                        addLog(`回测完成: ${r.total_return_pct}% 收益, 夏普=${r.sharpe_ratio}`, 'success');
                        return;
                    }
                } catch(e) {}
                attempts++;
            }
            resultDiv.innerHTML = '<div class="bt-result" style="text-align:center;padding:40px;color:#d29922;">⏰ 回测结果等待超时，请手动刷新</div>';
        }
        
        // 风控检查
        async function runRiskCheck() {
            addLog('执行风控检查...', 'info');
            const resultDiv = document.getElementById('risk-result');
            resultDiv.innerHTML = '<div style="padding:16px;text-align:center;">⏳ 检查中...</div>';
            
            try {
                const res = await fetch('/api/risk');
                const data = await res.json();
                if (data.success) {
                    const r = data.data;
                    let html = `<div style="padding:16px;font-size:13px;">`;
                    html += `<div style="margin-bottom:12px;"><strong>总体状态:</strong> <span style="color:${r.overall_status==='ok'?'#3fb950':'#f85149'};">${r.overall_status}</span></div>`;
                    if (r.checks) {
                        html += '<table class="risk-table"><tr><th>检查项</th><th>状态</th><th>详情</th></tr>';
                        for (const [name, check] of Object.entries(r.checks)) {
                            const statusColor = check.status === 'ok' ? '#3fb950' : check.status === 'warning' ? '#d29922' : '#f85149';
                            html += `<tr><td>${name}</td><td style="color:${statusColor}">${check.status}</td><td>${JSON.stringify(check).substring(0,100)}</td></tr>`;
                        }
                        html += '</table>';
                    }
                    html += '</div>';
                    resultDiv.innerHTML = html;
                }
            } catch(e) {
                addLog('风控检查失败: ' + e.message, 'error');
            }
        }
        
        // 事件总线
        async function refreshEvents() {
            try {
                const res = await fetch('/api/events?limit=20');
                const data = await res.json();
                const list = document.getElementById('events-list');
                if (data.success && data.data) {
                    const events = data.data;
                    list.innerHTML = events.map(e => `
                        <div style="padding:6px 16px;border-bottom:1px solid #21262d;font-size:12px;">
                            <span style="color:#58a6ff;">[${new Date(e.timestamp*1000).toLocaleTimeString()}]</span>
                            <span style="color:#d2a8ff;">${e.type}</span>
                            <span style="color:#8b949e;">← ${e.source}</span>
                        </div>
                    `).join('');
                    if (events.length === 0) list.innerHTML = '<div class="bt-result" style="text-align:center;color:#484f58;padding:40px;">无事件</div>';
                }
            } catch(e) {}
        }
        
        // 交易信号
        async function refreshSignals() {
            try {
                const res = await fetch('/api/signals?limit=20');
                const data = await res.json();
                // 在状态页面显示
            } catch(e) {}
        }
        
        // 初始化
        refreshAll();
        setInterval(refreshAll, POLL_INTERVAL);
        // ============================================================
        // AI 聊天助手功能
        // ============================================================
        let chatSessionId = 'qs_robot_session';
        let chatStreaming = false;
        let currentAssistantBubble = null;
        
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            if (!message || chatStreaming) return;
            
            const chatBody = document.getElementById('chat-body');
            const sendBtn = document.getElementById('chat-send-btn');
            
            // 清除欢迎文字（如果有）
            const welcomeDiv = chatBody.querySelector('div[style*="text-align:center"]');
            if (welcomeDiv && chatBody.children.length === 1) {
                chatBody.innerHTML = '';
            }
            
            // 添加用户消息气泡
            const userBubble = document.createElement('div');
            userBubble.style.cssText = 'align-self:flex-end;max-width:75%;';
            userBubble.innerHTML = `<div style="background:#238636;color:#fff;padding:10px 14px;border-radius:12px 12px 0 12px;font-size:13px;line-height:1.5;word-break:break-word;">${escapeHtml(message)}</div>
                <div style="font-size:10px;color:#484f58;margin-top:2px;text-align:right;">${new Date().toLocaleTimeString()}</div>`;
            chatBody.appendChild(userBubble);
            
            // 添加AI占位气泡（打字效果）
            const aiBubble = document.createElement('div');
            aiBubble.style.cssText = 'align-self:flex-start;max-width:80%;';
            aiBubble.innerHTML = `<div style="background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:10px 14px;border-radius:12px 12px 12px 0;font-size:13px;line-height:1.6;word-break:break-word;" id="ai-text"></div>
                <div style="font-size:10px;color:#484f58;margin-top:2px;">AI助手</div>`;
            chatBody.appendChild(aiBubble);
            currentAssistantBubble = aiBubble.querySelector('#ai-text');
            
            input.value = '';
            chatStreaming = true;
            sendBtn.disabled = true;
            sendBtn.textContent = '⏳';
            
            // 调用API
            const modelChoice = document.getElementById('chat-model')?.value || 'offline';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        session_id: chatSessionId,
                        model: modelChoice
                    })
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let aiText = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    buffer += decoder.decode(value, {stream: true});
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                if (data.chunk) {
                                    aiText += data.chunk;
                                    currentAssistantBubble.textContent = aiText;
                                    chatBody.scrollTop = chatBody.scrollHeight;
                                }
                                if (data.done && data.error) {
                                    currentAssistantBubble.style.color = '#f85149';
                                }
                            } catch(e) {}
                        }
                    }
                }
            } catch(e) {
                currentAssistantBubble.textContent = '网络错误: ' + e.message;
                currentAssistantBubble.style.color = '#f85149';
            }
            
            chatStreaming = false;
            sendBtn.disabled = false;
            sendBtn.textContent = '🚀 发送';
            currentAssistantBubble = null;
            chatBody.scrollTop = chatBody.scrollHeight;
            
            // 聚焦输入框
            document.getElementById('chat-input').focus();
        }
        
        function clearChatHistory() {
            if (!confirm('确定清空对话历史？')) return;
            fetch('/api/chat/clear', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: chatSessionId})
            }).then(() => {
                const chatBody = document.getElementById('chat-body');
                chatBody.innerHTML = `<div style="text-align:center;color:#8b949e;padding:80px 20px;">
                    <div style="font-size:48px;margin-bottom:16px;">💬</div>
                    <div style="font-size:16px;margin-bottom:8px;">对话历史已清空</div>
                    <div style="font-size:12px;">可以继续问我关于策略、回测、优化、风控等任何问题</div>
                </div>`;
                addLog('对话历史已清空', 'info');
            });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        addLog('🟢 QBot Desktop V3.0 已启动', 'success');
        addLog('🔗 正在连接Aurora深度集成引擎...', 'info');
    </script>
</body>
</html>
"""

# ============================================================
# API路由
# ============================================================
@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)

@app.route('/api/status')
def api_status():
    """系统状态"""
    if qs_robot:
        return jsonify({"success": True, "data": qs_robot.get_full_status()})
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/strategies')
def api_strategies():
    """策略列表"""
    if qs_robot:
        strategies = qs_robot.get_all_strategies()
        return jsonify({"success": True, "data": {"strategies": strategies, "count": len(strategies)}})
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/strategy/<name>')
def api_strategy_detail(name):
    """策略详情"""
    if qs_robot:
        detail = qs_robot.get_strategy_detail(name)
        if detail:
            return jsonify({"success": True, "data": detail})
        return jsonify({"success": False, "error": "策略未找到"}), 404
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    """提交回测"""
    if not qs_robot:
        return jsonify({"success": False, "error": "QBot未初始化"})
    data = request.json or {}
    strategy = data.get('strategy_name', data.get('name', 'FourierRLStrategy'))
    days = data.get('days', 30)
    symbol = data.get('symbol', '000001.SZ')
    task_id = qs_robot.submit_backtest(strategy, days, symbol=symbol)
    return jsonify({"success": True, "data": {"task_id": task_id}})

@app.route('/api/task/<task_id>')
def api_task_status(task_id):
    """任务状态"""
    if qs_robot:
        status = qs_robot.get_task_status(task_id)
        if status:
            return jsonify({"success": True, "data": status})
        return jsonify({"success": False, "error": "任务未找到"}), 404
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/risk')
def api_risk():
    """风控检查"""
    if qs_robot:
        return jsonify({"success": True, "data": qs_robot.run_risk_check()})
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    """提交优化"""
    if not qs_robot:
        return jsonify({"success": False, "error": "QBot未初始化"})
    data = request.json or {}
    strategy = data.get('strategy_name', 'FourierRLStrategy')
    iterations = data.get('iterations', 50)
    param_ranges = data.get('param_ranges', {})
    task_id = qs_robot.submit_optimization(strategy, param_ranges, iterations)
    return jsonify({"success": True, "data": {"task_id": task_id}})

@app.route('/api/events')
def api_events():
    """事件列表"""
    if qs_robot:
        events = qs_robot.get_recent_signals(50)
        # 从任务历史获取事件
        try:
            if qs_robot._bus:
                events = qs_robot._bus.get_recent_events(int(request.args.get('limit', 50)))
        except:
            pass
        return jsonify({"success": True, "data": events})
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/signals')
def api_signals():
    """交易信号"""
    if qs_robot:
        signals = qs_robot.get_recent_signals(int(request.args.get('limit', 50)))
        return jsonify({"success": True, "data": signals, "count": len(signals)})
    return jsonify({"success": False, "error": "QBot未初始化"})

@app.route('/api/strategy/start', methods=['POST'])
def api_start_strategy():
    """启动策略"""
    if not qs_robot:
        return jsonify({"success": False, "error": "QBot未初始化"})
    data = request.json or {}
    name = data.get('strategy_name', data.get('name', ''))
    balance = data.get('balance', 100000.0)
    if not name:
        return jsonify({"success": False, "error": "策略名称必填"}), 400
    ok, msg = qs_robot.start_strategy(name, balance)
    return jsonify({"success": ok, "message": msg})

@app.route('/api/strategy/stop', methods=['POST'])
def api_stop_strategies():
    """停止所有策略"""
    if not qs_robot:
        return jsonify({"success": False, "error": "QBot未初始化"})
    ok, msg = qs_robot.stop_all_strategies()
    return jsonify({"success": ok, "message": msg})

# ============================================================
# 启动入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='QS Robot Desktop V3.0')
    parser.add_argument('--port', type=int, default=5001, help='Web端口 (默认5001)')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='绑定地址')
    parser.add_argument('--no-aurora', action='store_true', help='不尝试连接Aurora')
    parser.add_argument('--no-tray', action='store_true', help='不启动系统托盘')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  🤖 QS Robot Desktop V3.0")
    print("  Aurora深度集成 — 量化交易控制面板")
    print("=" * 60)
    
    # 初始化QBot核心
    if not args.no_aurora:
        print("  🔗 正在连接Aurora深度集成引擎...")
        ok = init_robot()
        if ok:
            status = qs_robot.get_full_status()
            print(f"  ✅ Aurora已连接 | 模式: {status['mode']} | 策略: {status['strategy_count']}个")
        else:
            print("  ⚠️ Aurora深度集成不可用，将以本地模式运行")
    else:
        print("  ℹ️ 跳过Aurora连接（--no-aurora）")
    
    # 启动系统托盘
    tray = None
    if TRAY_AVAILABLE and not args.no_tray:
        tray = QBotTray(
            app_host=args.host,
            app_port=args.port,
            on_quit=lambda: os._exit(0)
        )
        tray.run_in_thread()
        print("  🖥️ 系统托盘已启动 (右键图标打开菜单)")
    
    print(f"\n  🌐 启动Web控制面板...")
    print(f"     地址: http://{args.host}:{args.port}")
    
    # 自动打开浏览器
    if not args.no_browser:
        import webbrowser
        threading.Timer(2.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    
    print(f"     按 Ctrl+C 停止 (或右键托盘图标退出)\n")
    
    try:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n  🛑 正在关闭...")
        if tray:
            tray.stop()
        if qs_robot:
            qs_robot.shutdown()
        print("  👋 QS Robot Desktop 已停止")

if __name__ == '__main__':
    main()
