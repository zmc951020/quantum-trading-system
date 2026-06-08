/* ==========================================================================
   机器人浮标组件 - Aurora Robot Floating Widget (Agent Enhanced)
   支持智能体思考过程、工具调用、多步执行可视化
   ========================================================================== */

(function() {
    'use strict';

    const RobotWidget = {
        isOpen: false,
        chatHistory: [],

        init: function() {
            this.createStyles();
            this.createWidget();
            this.bindEvents();
            this.loadStatus();
        },

        createStyles: function() {
            if (document.getElementById('robot-widget-styles')) return;
            const styles = document.createElement('style');
            styles.id = 'robot-widget-styles';
            styles.textContent = `
                #robot-widget-btn {
                    position: fixed; right: 20px; bottom: 20px; z-index: 9998;
                    width: 60px; height: 60px; border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border: 3px solid rgba(255,255,255,0.3); color: white; font-size: 28px;
                    cursor: pointer; box-shadow: 0 8px 25px rgba(102,126,234,0.4);
                    display: flex; align-items: center; justify-content: center;
                    transition: all 0.3s ease;
                }
                #robot-widget-btn:hover { transform: scale(1.1) rotate(10deg); box-shadow: 0 12px 35px rgba(102,126,234,0.55); }
                #robot-widget-btn::before { content: ''; position: absolute; width: 100%; height: 100%; border-radius: 50%; background: inherit; animation: robot-pulse 2s ease-out infinite; opacity: 0; }
                @keyframes robot-pulse { 0% { transform: scale(1); opacity: 0.6; } 100% { transform: scale(1.8); opacity: 0; } }
                #robot-widget-panel {
                    position: fixed; right: 20px; bottom: 90px; z-index: 9999;
                    width: 420px; max-height: 80vh; background: #ffffff;
                    border-radius: 16px; box-shadow: 0 15px 40px rgba(0,0,0,0.15);
                    display: none; flex-direction: column; overflow: hidden;
                    border: 1px solid #e5e7eb;
                }
                #robot-widget-panel.active { display: flex; }
                .rw-header {
                    padding: 16px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; display: flex; justify-content: space-between; align-items: center;
                }
                .rw-header-title { font-size: 15px; font-weight: 600; }
                .rw-header-status { font-size: 11px; opacity: 0.95; background: rgba(255,255,255,0.2); padding: 3px 8px; border-radius: 10px; margin-top: 4px; display: inline-block; }
                .rw-close { background: none; border: none; color: white; font-size: 22px; cursor: pointer; padding: 0; width: 28px; height: 28px; border-radius: 50%; transition: background 0.2s; }
                .rw-close:hover { background: rgba(255,255,255,0.25); }

                .rw-tabs { display: flex; border-bottom: 1px solid #e5e7eb; background: #f9fafb; }
                .rw-tab { flex: 1; padding: 10px 6px; text-align: center; cursor: pointer; font-size: 12px; color: #6b7280; border-bottom: 2px solid transparent; transition: all 0.2s; }
                .rw-tab.active { color: #667eea; border-bottom-color: #667eea; background: white; font-weight: 600; }

                .rw-tab-content { display: none; padding: 14px; overflow-y: auto; flex: 1; max-height: 500px; }
                .rw-tab-content.active { display: block; }

                .rw-chat-messages { margin-bottom: 10px; }
                .rw-msg { margin-bottom: 12px; padding: 12px 14px; border-radius: 12px; font-size: 13px; line-height: 1.6; word-wrap: break-word; }
                .rw-msg-user {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; margin-left: 60px; border-bottom-right-radius: 3px;
                    box-shadow: 0 2px 8px rgba(102,126,234,0.25);
                }
                .rw-msg-bot {
                    background: #f3f4f6; color: #1f2937; margin-right: 40px;
                    border-bottom-left-radius: 3px; border: 1px solid #e5e7eb;
                }

                .rw-msg-actions { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
                .rw-action-btn { background: #e0e7ff; color: #4338ca; border: 1px solid #c7d2fe; padding: 7px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; transition: all 0.2s; font-weight: 500; }
                .rw-action-btn:hover { background: #c7d2fe; transform: translateY(-1px); box-shadow: 0 2px 6px rgba(102,126,234,0.2); }

                .rw-chat-input { display: flex; gap: 8px; border-top: 1px solid #e5e7eb; padding: 12px; background: #fafbfc; }
                .rw-chat-input input {
                    flex: 1; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px;
                    font-size: 13px; outline: none; transition: border-color 0.2s;
                }
                .rw-chat-input input:focus { border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); }
                .rw-chat-input button {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; border: none; padding: 0 18px; border-radius: 8px;
                    cursor: pointer; font-weight: 600; font-size: 13px; transition: transform 0.15s;
                }
                .rw-chat-input button:hover { transform: scale(1.05); }

                .rw-quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                .rw-quick-btn { padding: 14px 10px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; cursor: pointer; text-align: center; font-size: 12px; color: #374151; transition: all 0.2s; }
                .rw-quick-btn:hover { background: #e0e7ff; border-color: #667eea; color: #4338ca; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102,126,234,0.15); }
                .rw-quick-btn-icon { font-size: 22px; display: block; margin-bottom: 5px; }

                .rw-status-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: #f9fafb; border-radius: 8px; margin-bottom: 8px; }
                .rw-status-item:last-child { margin-bottom: 0; }
                .rw-status-name { font-size: 13px; color: #374151; font-weight: 500; }
                .rw-status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e; margin-right: 8px; }
                .rw-status-offline { background: #ef4444; }
                .rw-status-msg { font-size: 11px; color: #6b7280; }

                .rw-notification { padding: 12px; background: #f9fafb; border-radius: 8px; margin-bottom: 8px; border-left: 3px solid #667eea; }
                .rw-notification.success { border-left-color: #22c55e; }
                .rw-notification.warning { border-left-color: #f59e0b; }
                .rw-notification-title { font-size: 13px; font-weight: 600; color: #1f2937; margin-bottom: 3px; }
                .rw-notification-content { font-size: 12px; color: #6b7280; }
                .rw-notification-time { font-size: 11px; color: #9ca3af; margin-top: 5px; }

                .rw-loading { text-align: center; padding: 10px; color: #6b7280; font-size: 12px; }
                .rw-spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #e5e7eb; border-top-color: #667eea; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 6px; }
                @keyframes spin { to { transform: rotate(360deg); } }

                /* === Agent 增强样式 === */
                .rw-thinking {
                    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                    border-left: 3px solid #f59e0b; padding: 10px 12px; margin: 8px 0;
                    border-radius: 8px; font-size: 12px; color: #78350f;
                }
                .rw-thinking-title { font-weight: 600; margin-bottom: 6px; color: #78350f; display: flex; align-items: center; gap: 6px; }
                .rw-thinking-item { margin: 4px 0; padding-left: 8px; color: #78350f; }

                .rw-plan {
                    background: #eff6ff; border: 1px solid #bfdbfe; border-left: 3px solid #3b82f6;
                    padding: 10px 12px; margin: 8px 0; border-radius: 8px; font-size: 12px; color: #1e40af;
                }
                .rw-plan-title { font-weight: 600; margin-bottom: 6px; color: #1e40af; }
                .rw-plan-step { margin: 4px 0; padding-left: 16px; color: #1e40af; position: relative; }
                .rw-plan-step::before { content: '→'; position: absolute; left: 0; }

                .rw-tool-card {
                    background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px;
                    margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                }
                .rw-tool-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #f3f4f6; }
                .rw-tool-name { font-weight: 600; color: #374151; font-size: 13px; display: flex; align-items: center; gap: 8px; }
                .rw-tool-time { font-size: 11px; color: #9ca3af; }
                .rw-tool-content { font-size: 12px; color: #4b5563; line-height: 1.7; }
                .rw-tool-content b, .rw-tool-content strong { color: #1f2937; }
                .rw-tool-content code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #dc2626; font-family: monospace; }

                .rw-result-card {
                    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
                    border: 1px solid #a7f3d0; border-left: 4px solid #10b981;
                    padding: 14px; margin: 10px 0; border-radius: 12px;
                    box-shadow: 0 2px 8px rgba(16,185,129,0.1);
                }
                .rw-result-title { font-weight: 600; color: #065f46; font-size: 14px; margin-bottom: 8px; }
                .rw-result-content { font-size: 12px; color: #065f46; line-height: 1.7; }
                .rw-result-content b, .rw-result-content strong { color: #064e3b; }
                .rw-result-content code { background: rgba(255,255,255,0.6); padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #047857; }

                .rw-error-msg {
                    background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #ef4444;
                    padding: 12px; margin: 10px 0; border-radius: 8px; color: #991b1b; font-size: 13px;
                }
            `;
            document.head.appendChild(styles);
        },

        createWidget: function() {
            if (document.getElementById('robot-widget-btn')) return;
            const btn = document.createElement('button');
            btn.id = 'robot-widget-btn';
            btn.innerHTML = '🤖';
            btn.title = 'Aurora 智能体助手';
            document.body.appendChild(btn);

            const panel = document.createElement('div');
            panel.id = 'robot-widget-panel';
            panel.innerHTML = `
                <div class="rw-header">
                    <div>
                        <div class="rw-header-title">🤖 Aurora 智能体</div>
                        <div class="rw-header-status">
                            <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#22c55e;margin-right:5px;"></span>
                            在线 · 29个智能体就绪
                        </div>
                    </div>
                    <button class="rw-close" onclick="RobotWidget.toggle()">×</button>
                </div>
                <div class="rw-tabs">
                    <div class="rw-tab active" data-tab="chat">💬 对话</div>
                    <div class="rw-tab" data-tab="quick">⚡ 快捷</div>
                    <div class="rw-tab" data-tab="status">📊 状态</div>
                    <div class="rw-tab" data-tab="notif">🔔 通知</div>
                </div>
                <div class="rw-tab-content active" data-tab="chat">
                    <div class="rw-chat-messages" id="rw-chat-messages">
                        <div class="rw-msg rw-msg-bot">
                            👋 您好！我是 <b>Aurora 智能量化助手</b>，具有自主决策和工具调用能力。<br><br>
                            我可以帮您：<br>
                            🔬 调用港大29智能体进行股票分析<br>
                            📊 使用韬定律优化策略参数<br>
                            📈 智能筛选股票池<br>
                            🛡️ 检查系统风险<br>
                            🚀 执行完整自动化流程<br><br>
                            <span style="color:#6b7280;font-size:12px;">💡 试试说："分析600519" 或 "完整流程600519"</span>
                        </div>
                    </div>
                    <div class="rw-chat-input">
                        <input type="text" id="rw-chat-input" placeholder="自然语言指令：如 分析600519、优化策略..." onkeypress="if(event.key==='Enter') RobotWidget.sendChat()" />
                        <button onclick="RobotWidget.sendChat()">发送</button>
                    </div>
                </div>
                <div class="rw-tab-content" data-tab="quick">
                    <div class="rw-quick-grid">
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('tau_optimize')">
                            <span class="rw-quick-btn-icon">📊</span>韬定律优化
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('vibe_analyze')">
                            <span class="rw-quick-btn-icon">🔬</span>港大智能体
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('stock_pool')">
                            <span class="rw-quick-btn-icon">📈</span>股票池筛选
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('backtest')">
                            <span class="rw-quick-btn-icon">📉</span>策略回测
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('risk_check')">
                            <span class="rw-quick-btn-icon">🛡️</span>风险检查
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('full_flow')">
                            <span class="rw-quick-btn-icon">🚀</span>完整流程
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('system_status')">
                            <span class="rw-quick-btn-icon">🖥️</span>系统状态
                        </div>
                        <div class="rw-quick-btn" onclick="RobotWidget.runQuick('help')">
                            <span class="rw-quick-btn-icon">💡</span>功能帮助
                        </div>
                    </div>
                </div>
                <div class="rw-tab-content" data-tab="status">
                    <div id="rw-status-content">
                        <div class="rw-loading"><span class="rw-spinner"></span>加载系统状态...</div>
                    </div>
                </div>
                <div class="rw-tab-content" data-tab="notif">
                    <div id="rw-notifications">
                        <div class="rw-loading"><span class="rw-spinner"></span>加载通知...</div>
                    </div>
                </div>
            `;
            document.body.appendChild(panel);
        },

        bindEvents: function() {
            const self = this;
            const btn = document.getElementById('robot-widget-btn');
            btn.addEventListener('click', function() { self.toggle(); });

            const tabs = document.querySelectorAll('.rw-tab');
            tabs.forEach(tab => {
                tab.addEventListener('click', function() {
                    tabs.forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    const tabName = tab.getAttribute('data-tab');
                    document.querySelectorAll('.rw-tab-content').forEach(content => {
                        content.classList.toggle('active', content.getAttribute('data-tab') === tabName);
                    });
                    if (tabName === 'status') self.loadStatus();
                    if (tabName === 'notif') self.loadNotifications();
                });
            });
        },

        toggle: function() {
            const panel = document.getElementById('robot-widget-panel');
            panel.classList.toggle('active');
            this.isOpen = panel.classList.contains('active');
        },

        /* ============================================================
           核心聊天发送 - 使用智能体系统
           ============================================================ */
        sendChat: function() {
            const input = document.getElementById('rw-chat-input');
            const msg = input.value.trim();
            if (!msg) return;
            input.value = '';

            const messages = document.getElementById('rw-chat-messages');

            // 添加用户消息
            const userMsg = document.createElement('div');
            userMsg.className = 'rw-msg rw-msg-user';
            userMsg.textContent = msg;
            messages.appendChild(userMsg);

            // 添加"思考中"加载消息
            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'rw-msg rw-msg-bot';
            loadingMsg.innerHTML = '<div class="rw-loading"><span class="rw-spinner"></span>🤔 智能体正在分析中...</div>';
            messages.appendChild(loadingMsg);
            messages.scrollTop = messages.scrollHeight;

            const self = this;
            fetch('/api/agent/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            }).then(r => r.json()).then(data => {
                messages.removeChild(loadingMsg);
                if (data.success) {
                    self.renderAgentResponse(messages, data, msg);
                } else {
                    self.renderError(messages, data.error || '执行失败');
                }
                messages.scrollTop = messages.scrollHeight;
            }).catch(err => {
                messages.removeChild(loadingMsg);
                self.renderError(messages, '网络错误：' + err);
                messages.scrollTop = messages.scrollHeight;
            });
        },

        /* ============================================================
           渲染智能体完整响应（思考 + 计划 + 工具 + 结果）
           ============================================================ */
        renderAgentResponse: function(messages, data, userMessage) {
            const self = this;

            // 思考过程
            if (data.thinking && data.thinking.length > 0) {
                const thinkingBox = document.createElement('div');
                thinkingBox.className = 'rw-msg rw-msg-bot';
                let thinkingHtml = '<div class="rw-thinking">';
                thinkingHtml += '<div class="rw-thinking-title">🧠 智能体思考过程</div>';
                data.thinking.forEach(t => {
                    thinkingHtml += `<div class="rw-thinking-item">${self.escapeHtml(t)}</div>`;
                });
                thinkingHtml += '</div>';
                thinkingBox.innerHTML = thinkingHtml;
                messages.appendChild(thinkingBox);
            }

            // 执行计划
            if (data.plan && data.plan.length > 0) {
                const planBox = document.createElement('div');
                planBox.className = 'rw-msg rw-msg-bot';
                let planHtml = '<div class="rw-plan">';
                planHtml += '<div class="rw-plan-title">📋 执行计划</div>';
                data.plan.forEach(step => {
                    planHtml += `<div class="rw-plan-step">${self.escapeHtml(step)}</div>`;
                });
                planHtml += '</div>';
                planBox.innerHTML = planHtml;
                messages.appendChild(planBox);
            }

            // 工具调用结果
            if (data.tool_calls && data.tool_calls.length > 0) {
                data.tool_calls.forEach(tool => {
                    if (!tool) return;
                    const toolCard = document.createElement('div');
                    toolCard.className = 'rw-msg rw-msg-bot';
                    let cardHtml = '<div class="rw-tool-card">';

                    // 工具头部
                    const toolIcon = tool.icon || '⚙️';
                    const toolName = tool.tool_name || tool.tool || '工具调用';
                    const elapsed = tool.elapsed_ms || 0;
                    cardHtml += `<div class="rw-tool-header">
                        <div class="rw-tool-name">${toolIcon} ${self.escapeHtml(toolName)}</div>
                        <div class="rw-tool-time">${elapsed}ms</div>
                    </div>`;

                    // 工具内容
                    if (tool.tool && (tool.tool === 'vibe_29_agents' || tool.tool_name === '港大29智能体投票矩阵')) {
                        cardHtml += self.formatVibeResult(tool.result || {});
                    } else if (tool.tool === 'tau_optimize' || tool.tool_name === '韬定律参数优化器') {
                        cardHtml += self.formatTauResult(tool.result || {});
                    } else if (tool.tool === 'stock_pool_filter' || tool.tool_name === '智能股票池系统') {
                        cardHtml += self.formatStockPoolResult(tool.result || {});
                    } else if (tool.tool === 'backtest_run' || tool.tool_name === '策略回测引擎') {
                        cardHtml += self.formatBacktestResult(tool.result || {});
                    } else if (tool.tool === 'risk_check' || tool.tool_name === '智能风控系统') {
                        cardHtml += self.formatRiskResult(tool.result || {});
                    } else if (tool.tool === 'system_status' || tool.tool_name === '系统监控中心') {
                        cardHtml += self.formatSystemStatusResult(tool.result || {});
                    } else if (tool.tool === 'full_workflow' || tool.tool_name === '完整自动化流程') {
                        cardHtml += self.formatFullFlowResult(tool.result || {});
                    } else if (tool.tool === 'show_help' || tool.tool_name === '帮助中心') {
                        cardHtml += self.formatHelpResult(tool.result || {});
                    } else {
                        // 默认格式化
                        cardHtml += '<div class="rw-tool-content">' + self.formatGenericResult(tool.result || tool.message || '') + '</div>';
                    }

                    cardHtml += '</div>';
                    toolCard.innerHTML = cardHtml;
                    messages.appendChild(toolCard);
                });
            }

            // 最终响应（如果有额外内容）
            const resp = data.response || {};
            const respContent = resp.content || '';
            const actions = resp.actions || [];

            if (respContent && (!data.tool_calls || data.tool_calls.length === 0)) {
                const finalMsg = document.createElement('div');
                finalMsg.className = 'rw-msg rw-msg-bot';
                let html = '<div class="rw-result-card">';
                html += '<div class="rw-result-title">✨ 结果</div>';
                html += '<div class="rw-result-content">' + self.formatContent(respContent) + '</div>';
                html += '</div>';
                if (actions.length > 0) {
                    html += '<div class="rw-msg-actions">';
                    actions.forEach(act => {
                        html += `<button class="rw-action-btn" onclick="RobotWidget.handleAction('${act.action}','${(act.target||'').replace(/'/g,"\\'")}')">${act.label}</button>`;
                    });
                    html += '</div>';
                }
                finalMsg.innerHTML = html;
                messages.appendChild(finalMsg);
            } else if (actions.length > 0) {
                const actionBox = document.createElement('div');
                actionBox.className = 'rw-msg rw-msg-bot';
                let actionHtml = '<div class="rw-msg-actions">';
                actions.forEach(act => {
                    actionHtml += `<button class="rw-action-btn" onclick="RobotWidget.handleAction('${act.action}','${(act.target||'').replace(/'/g,"\\'")}')">${act.label}</button>`;
                });
                actionHtml += '</div>';
                actionBox.innerHTML = actionHtml;
                messages.appendChild(actionBox);
            }

            messages.scrollTop = messages.scrollHeight;
        },

        /* ============================================================
           结果格式化函数
           ============================================================ */
        formatContent: function(text) {
            if (!text) return '';
            return this.escapeHtml(text).replace(/\n/g, '<br>');
        },

        formatGenericResult: function(result) {
            if (!result) return '';
            if (typeof result === 'string') return this.formatContent(result);
            // 通用 JSON 显示
            try {
                return '<pre style="font-size:11px;background:#f3f4f6;padding:8px;border-radius:6px;overflow-x:auto;">' + 
                       JSON.stringify(result, null, 2).substring(0, 500) + '</pre>';
            } catch(e) { return String(result); }
        },

        formatVibeResult: function(result) {
            if (!result) return '';
            const total = result.total_score || 'N/A';
            const decision = result.final_decision || 'N/A';
            const pool = result.recommended_pool || 'N/A';
            const pos = result.recommended_position || 'N/A';
            const vs = result.vote_summary || {};
            const buy = vs.buy_votes || '?';
            const hold = vs.hold_votes || '?';
            const sell = vs.sell_votes || '?';
            const agents = result.agent_votes || [];

            let html = '<div class="rw-tool-content">';
            html += `<b>股票代码：</b><code>${result.symbol || '-'}</code><br>`;
            html += `<b>综合评分：</b><b style="color:#059669;font-size:14px;">${total}/100</b><br>`;
            html += `<b>最终决策：</b><b style="color:#7c3aed;">🎯 ${decision}</b><br>`;
            html += `<b>建议进入：</b>${pool}<br>`;
            html += `<b>建议仓位：</b>${pos}<br><br>`;

            html += '<b>29位智能体投票分布：</b><br>';
            html += `🟢 买入: <b>${buy}</b> 票 &nbsp;&nbsp; `;
            html += `🟡 观望: <b>${hold}</b> 票 &nbsp;&nbsp; `;
            html += `🔴 卖出: <b>${sell}</b> 票<br>`;
            html += `<b>共识度：</b>${vs.consensus_level || '中等'}<br><br>`;

            if (agents.length > 0) {
                html += '<b>核心智能体观点：</b><br>';
                agents.slice(0, 3).forEach(a => {
                    html += `• ${a.name || '智能体'}: ${a.vote || '?'} (评分 ${a.score || '?'})<br>`;
                });
            }
            html += '</div>';
            return html;
        },

        formatTauResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>策略：</b>${result.strategy || '-'}<br>`;
            html += `<b>优化方法：</b>${result.optimization_method || '韬定律'}<br>`;
            html += `<b>评估次数：</b>${result.iterations || '-'}<br>`;
            html += `<b>最佳评分：</b><b style="color:#059669;font-size:14px;">⭐ ${result.best_score || '-'}</b><br><br>`;
            html += '<b>最优参数：</b><br>';
            const params = result.best_params || {};
            for (const k in params) {
                html += `• <code>${k}</code>: <b>${params[k]}</b><br>`;
            }
            if (result.message) {
                html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            }
            html += '</div>';
            return html;
        },

        formatStockPoolResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>筛选标准：</b>${result.criteria || '-'}<br>`;
            html += `<b>筛选结果：</b><b style="color:#059669;">${result.total_filtered || 0} 只股票</b><br><br>`;
            html += '<b>TOP 5 候选：</b><br>';
            (result.top_stocks || []).forEach(s => {
                html += `• <code>${s.symbol}</code> <b>${s.name || ''}</b> - ${s.signal || ''} (评分 ${s.score})<br>`;
            });
            if (result.message) html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            html += '</div>';
            return html;
        },

        formatBacktestResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>回测周期：</b>${result.period || '-'}<br><br>`;
            html += '<b>关键指标：</b><br>';
            html += `📈 总收益率: <b style="color:#059669;">${result.total_return || '?'}%</b><br>`;
            html += `📊 夏普比率: <b>${result.sharpe_ratio || '?'}</b><br>`;
            html += `📉 最大回撤: <b style="color:#dc2626;">${result.max_drawdown || '?'}%</b><br>`;
            html += `🎯 胜率: <b>${result.win_rate || '?'}%</b><br>`;
            html += `🔄 交易次数: <b>${result.trades || '?'}</b><br>`;
            if (result.message) html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            html += '</div>';
            return html;
        },

        formatRiskResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>整体风险等级：</b><b style="color:#059669;">${result.overall_risk || '-'}</b><br>`;
            html += `<b>风险评分：</b>${result.risk_score || '?'}/100<br><br>`;
            html += '<b>检查项：</b><br>';
            (result.checks || []).forEach(c => {
                html += `${c.status || ''} <b>${c.name || ''}</b>: ${c.detail || ''}<br>`;
            });
            if (result.message) html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            html += '</div>';
            return html;
        },

        formatSystemStatusResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>整体状态：</b><b style="color:#059669;">${result.overall || '-'}</b><br><br>`;
            html += '<b>各系统状态：</b><br>';
            (result.systems || []).forEach(s => {
                const isOnline = s.status === 'online';
                const dot = isOnline ? '🟢' : '🔴';
                html += `${dot} ${s.icon || ''} <b>${s.name || ''}</b>: ${s.detail || s.message || '正常'}<br>`;
            });
            if (result.message) html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            html += '</div>';
            return html;
        },

        formatFullFlowResult: function(result) {
            if (!result) return '';
            let html = '<div class="rw-tool-content">';
            html += `<b>目标股票：</b><code>${result.symbol || '-'}</code><br>`;
            html += `<b>执行步骤：</b><b style="color:#059669;">${result.total_steps || 0} 步</b><br><br>`;
            html += '<b>流程详情：</b><br>';
            (result.steps || []).forEach(step => {
                html += `${step.icon || '📌'} <b>步骤${step.step || ''}：</b>${step.name || ''}<br>`;
                html += `<span style="color:#6b7280;padding-left:24px;">&nbsp;&nbsp;${step.summary || ''}</span><br>`;
            });
            html += `<br><b>最终建议：</b><b style="color:#059669;">${result.final_recommendation || '-'}</b><br>`;
            if (result.message) html += `<br><span style="color:#059669;">✨ ${result.message}</span>`;
            html += '</div>';
            return html;
        },

        formatHelpResult: function(result) {
            if (!result || !result.features) return '';
            let html = '<div class="rw-tool-content">';
            html += '<b>我可以帮您完成以下任务：</b><br><br>';
            (result.features || []).forEach(f => {
                html += `${f.icon || '•'} <b>${f.name || '功能'}</b> - ${f.description || ''}<br>`;
            });
            html += '</div>';
            return html;
        },

        /* ============================================================
           错误渲染
           ============================================================ */
        renderError: function(messages, error) {
            const errMsg = document.createElement('div');
            errMsg.className = 'rw-msg rw-msg-bot';
            errMsg.innerHTML = '<div class="rw-error-msg">❌ ' + this.escapeHtml(error) + '</div>';
            messages.appendChild(errMsg);
        },

        escapeHtml: function(s) {
            if (!s) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        },

        /* ============================================================
           操作处理
           ============================================================ */
        handleAction: function(action, target) {
            if (action === 'navigate') {
                window.location.href = target;
            } else if (action === 'analyze_vibe') {
                // 直接发起智能体分析
                const messages = document.getElementById('rw-chat-messages');
                const userMsg = document.createElement('div');
                userMsg.className = 'rw-msg rw-msg-user';
                userMsg.textContent = '分析股票 ' + target;
                messages.appendChild(userMsg);

                const loadingMsg = document.createElement('div');
                loadingMsg.className = 'rw-msg rw-msg-bot';
                loadingMsg.innerHTML = '<div class="rw-loading"><span class="rw-spinner"></span>🤔 正在分析...</div>';
                messages.appendChild(loadingMsg);
                messages.scrollTop = messages.scrollHeight;

                const self = this;
                fetch('/api/agent/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: '分析股票 ' + target })
                }).then(r => r.json()).then(data => {
                    messages.removeChild(loadingMsg);
                    if (data.success) {
                        self.renderAgentResponse(messages, data, '分析 ' + target);
                    } else {
                        self.renderError(messages, data.error || '执行失败');
                    }
                    messages.scrollTop = messages.scrollHeight;
                }).catch(err => {
                    messages.removeChild(loadingMsg);
                    self.renderError(messages, '网络错误：' + err);
                });
            } else if (action === 'full_flow') {
                this.runQuick('full_flow');
            } else if (action === 'quick_cmd') {
                this.runQuick(target);
            } else if (action === 'prompt') {
                const input = document.getElementById('rw-chat-input');
                if (input) { input.value = target; input.focus(); }
            }
        },

        /* ============================================================
           快捷命令
           ============================================================ */
        runQuick: function(command) {
            const messages = document.getElementById('rw-chat-messages');

            // 显示用户命令
            const userMsg = document.createElement('div');
            userMsg.className = 'rw-msg rw-msg-user';
            userMsg.textContent = '[快捷指令] ' + command;
            messages.appendChild(userMsg);

            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'rw-msg rw-msg-bot';
            loadingMsg.innerHTML = '<div class="rw-loading"><span class="rw-spinner"></span>🤔 智能体处理中...</div>';
            messages.appendChild(loadingMsg);
            messages.scrollTop = messages.scrollHeight;

            const self = this;
            // 使用智能体API执行
            fetch('/api/agent/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: command })
            }).then(r => r.json()).then(data => {
                messages.removeChild(loadingMsg);
                if (data.success) {
                    self.renderAgentResponse(messages, data, command);
                } else {
                    self.renderError(messages, data.error || '执行失败');
                }
                messages.scrollTop = messages.scrollHeight;
            }).catch(err => {
                messages.removeChild(loadingMsg);
                self.renderError(messages, '网络错误：' + err);
            });
        },

        /* ============================================================
           系统状态与通知
           ============================================================ */
        loadStatus: function() {
            const el = document.getElementById('rw-status-content');
            if (!el) return;
            fetch('/api/robot/status').then(r => r.json()).then(data => {
                if (data.success && data.systems) {
                    let html = '';
                    for (const key in data.systems) {
                        const sys = data.systems[key];
                        const isOnline = sys.status === 'online';
                        html += `<div class="rw-status-item">
                            <div>
                                <span class="rw-status-dot ${isOnline ? '' : 'rw-status-offline'}"></span>
                                <span class="rw-status-name">${sys.icon || ''} ${sys.name || key}</span>
                            </div>
                            <span class="rw-status-msg">${sys.message || sys.detail || '运行中'}</span>
                        </div>`;
                    }
                    html += `<div style="margin-top:15px;padding:12px;background:#f0fdf4;border-radius:8px;text-align:center;font-size:12px;color:#166534;">
                        📈 今日完成: <b>${data.tasks_completed_today || 0}</b> 个任务<br>
                        🔄 进行中: <b>${data.tasks_running || 0}</b> 个任务
                    </div>`;
                    el.innerHTML = html;
                }
            }).catch(() => {
                el.innerHTML = '<div style="color:#ef4444;font-size:12px;text-align:center;padding:20px;">⚠️ 无法获取系统状态</div>';
            });
        },

        loadNotifications: function() {
            const el = document.getElementById('rw-notifications');
            if (!el) return;
            fetch('/api/robot/notifications').then(r => r.json()).then(data => {
                if (data.success && data.notifications) {
                    let html = '';
                    data.notifications.forEach(n => {
                        html += `<div class="rw-notification ${n.type}">
                            <div class="rw-notification-title">${n.title}</div>
                            <div class="rw-notification-content">${n.content}</div>
                            <div class="rw-notification-time">${n.time}</div>
                        </div>`;
                    });
                    el.innerHTML = html || '<div style="text-align:center;padding:30px;color:#9ca3af;font-size:12px;">📭 暂无通知</div>';
                }
            }).catch(() => {
                el.innerHTML = '<div style="color:#ef4444;font-size:12px;text-align:center;padding:20px;">⚠️ 无法获取通知</div>';
            });
        }
    };

    window.RobotWidget = RobotWidget;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { RobotWidget.init(); });
    } else {
        RobotWidget.init();
    }
})();
