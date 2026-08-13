let poolChart = null;
let strategyChart = null;

document.addEventListener('DOMContentLoaded', function() {
    initEventListeners();
    loadPoolSummary();
    loadCandidateStocks();
    loadPushLog();
});

function initEventListeners() {
    document.getElementById('btn-run-pipeline').addEventListener('click', runPipeline);
    document.getElementById('btn-refresh').addEventListener('click', refreshData);
    document.getElementById('btn-back').addEventListener('click', goBack);
}

function goBack() {
    window.location.href = '/';
}

function showLoading(show) {
    document.getElementById('loading-mask').style.display = show ? 'flex' : 'none';
}

async function runPipeline() {
    showLoading(true);
    
    try {
        const response = await fetch('/api/stock_pool/run_pipeline', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ count: 10 })
        });
        
        const data = await response.json();
        
        if (data.success) {
            renderResults(data.data);
            loadPoolSummary();
        } else {
            console.error('Pipeline failed:', data.error);
        }
    } catch (error) {
        console.error('Error running pipeline:', error);
    } finally {
        showLoading(false);
    }
}

async function refreshData() {
    await loadPoolSummary();
}

async function loadPoolSummary() {
    try {
        const response = await fetch('/api/stock_pool/pool_summary');
        const data = await response.json();
        
        if (data.success) {
            updatePoolSummary(data.data);
            renderPoolChart(data.data);
        }
    } catch (error) {
        console.error('Error loading pool summary:', error);
    }
}

function updatePoolSummary(summary) {
    document.getElementById('pool-candidate').textContent = summary.candidate || 0;
    document.getElementById('pool-classified').textContent = summary.classified || 0;
    document.getElementById('pool-watchlist').textContent = summary.watchlist || 0;
    document.getElementById('pool-adaptive').textContent = summary.adaptive || 0;
    document.getElementById('pool-trading').textContent = summary.trading || 0;
    
    const total = Object.values(summary).reduce((a, b) => a + (b || 0), 0);
    document.getElementById('stat-final').textContent = summary.trading || 0;
}

function renderResults(data) {
    updateStats(data);
    renderSimulationTable(data.simulated);
    renderFinalList(data.final);
    renderStrategyChart(data.simulated);
}

function updateStats(data) {
    document.getElementById('stat-total').textContent = data.filtered?.length || 0;
    document.getElementById('stat-passed').textContent = data.filtered?.length || 0;
    document.getElementById('stat-matched').textContent = data.simulated?.length || 0;
    document.getElementById('stat-final').textContent = data.final?.length || 0;
}

function renderSimulationTable(simulated) {
    const tbody = document.getElementById('simulation-table-body');
    
    if (!simulated || simulated.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px;">暂无模拟数据</td></tr>';
        return;
    }
    
    tbody.innerHTML = simulated.map(item => `
        <tr>
            <td><span class="stock-name">${item.code} ${item.name}</span></td>
            <td><span class="strategy-name">${item.strategy}</span></td>
            <td>${formatPercent(item.total_return)}%</td>
            <td>${item.sharpe_ratio}</td>
            <td>${formatPercent(item.max_drawdown)}%</td>
            <td>${item.win_rate}%</td>
            <td><span class="score">${item.sim_score}</span></td>
        </tr>
    `).join('');
}

function renderFinalList(final) {
    const container = document.getElementById('final-list');
    
    if (!final || final.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span class="empty-icon">🔍</span>
                <span class="empty-text">暂无入选股票</span>
            </div>
        `;
        return;
    }
    
    container.innerHTML = final.map(item => {
        const gradeClass = item.score >= 80 ? 'excellent' : 'good';
        const gradeText = item.score >= 80 ? '优秀' : '良好';
        
        return `
            <div class="final-card">
                <div class="final-card-header">
                    <span class="final-stock-name">${item.code} ${item.name}</span>
                    <span class="final-grade ${gradeClass}">${gradeText}</span>
                </div>
                <div class="final-card-body">
                    <span class="final-strategy">策略: ${item.strategy}</span>
                    <span class="final-score">${item.score}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderPoolChart(summary) {
    const ctx = document.getElementById('poolChart').getContext('2d');
    
    if (poolChart) {
        poolChart.destroy();
    }
    
    const labels = ['候选池', '分类池', '监控池', '策略适配池', '实盘池'];
    const values = [
        summary.candidate || 0,
        summary.classified || 0,
        summary.watchlist || 0,
        summary.adaptive || 0,
        summary.trading || 0
    ];
    
    const colors = [
        'rgba(99, 102, 241, 0.8)',
        'rgba(245, 158, 11, 0.8)',
        'rgba(16, 185, 129, 0.8)',
        'rgba(139, 92, 246, 0.8)',
        'rgba(239, 68, 68, 0.8)'
    ];
    
    poolChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            cutout: '65%'
        }
    });
}

function renderStrategyChart(simulated) {
    if (!simulated || simulated.length === 0) return;
    
    const ctx = document.getElementById('strategyChart').getContext('2d');
    
    if (strategyChart) {
        strategyChart.destroy();
    }
    
    const strategyCounts = {};
    simulated.forEach(item => {
        strategyCounts[item.strategy] = (strategyCounts[item.strategy] || 0) + 1;
    });
    
    const labels = Object.keys(strategyCounts);
    const values = Object.values(strategyCounts);
    
    const colors = [
        'rgba(59, 130, 246, 0.8)',
        'rgba(16, 185, 129, 0.8)',
        'rgba(245, 158, 11, 0.8)',
        'rgba(239, 68, 68, 0.8)',
        'rgba(139, 92, 246, 0.8)'
    ];
    
    strategyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '匹配数量',
                data: values,
                backgroundColor: colors.slice(0, labels.length),
                borderRadius: 8,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        color: '#94a3b8'
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: '#94a3b8'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

function formatPercent(value) {
    return typeof value === 'number' ? value.toFixed(2) : '0.00';
}

// ========== 候选池股票列表 ==========

async function loadCandidateStocks() {
    try {
        const resp = await fetch('/api/stock_pool/get_pool/candidate');
        const data = await resp.json();
        if (data.success) {
            renderCandidateTable(data.data);
        }
    } catch (error) {
        console.error('Error loading candidate stocks:', error);
    }
}

function renderCandidateTable(stocks) {
    const tbody = document.getElementById('candidate-table-body');
    if (!stocks || stocks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;">暂无候选股票 — 请从集群选股页面推入</td></tr>';
        return;
    }
    tbody.innerHTML = stocks.map(s => `
        <tr>
            <td><span class="stock-name">${s.code}</span></td>
            <td>${s.name || s.code}</td>
            <td>${(s.goodness || 0).toFixed(3)}</td>
            <td><span class="strategy-name">${s.source || '--'}</span></td>
            <td>
                <button class="action-btn btn-tune" onclick="openStrategyTuning('${s.code}')" title="策略参数优化">🔧 调参</button>
                <button class="action-btn btn-backtest" onclick="openBacktest('${s.code}')" title="回测验证">📉 回测</button>
                <button class="action-btn btn-promote" onclick="promoteToLive('${s.code}')" title="推入实盘池">💰 实盘</button>
            </td>
        </tr>
    `).join('');
}

// ========== 股票操作 ==========

function openStrategyTuning(code) {
    // 跳转到策略优化系统，传入股票代码
    if (confirm(`即将对 ${code} 进行策略参数优化，是否继续？\n\n系统将使用历史数据对32个策略进行参数网格搜索，找到最优参数组合。`)) {
        window.open(`/strategy_optimizer?code=${code}`, '_blank');
    }
}

function openBacktest(code) {
    if (confirm(`即将对 ${code} 进行回测验证，是否继续？\n\n系统将使用近3年历史数据运行32个策略，评估夏普比率、最大回撤和胜率。`)) {
        window.open(`/backtest?code=${code}`, '_blank');
    }
}

async function promoteToLive(code) {
    if (!confirm(`确认将 ${code} 推入实盘池？\n\n⚠️ 实盘交易仅限本地机操作，需注册登录用户身份\n⚠️ 请确保已完成回测验证和风控评估`)) {
        return;
    }
    try {
        const resp = await fetch('/cluster_selector/api/push_to_pool', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                stocks: [{code: code, name: code, goodness: 0}],
                level: 'testing',
                u: 0, n: 5,
            }),
        });
        const data = await resp.json();
        if (data.success) {
            alert(`✅ ${code} 已推入测试池，请继续执行回测验证后手动升级到实盘池`);
            loadCandidateStocks();
            loadPoolSummary();
        }
    } catch (error) {
        console.error('Error promoting:', error);
        alert('操作失败: ' + error.message);
    }
}

// ========== 操作日志 ==========

async function loadPushLog() {
    try {
        const resp = await fetch('/cluster_selector/api/push_log?limit=20');
        const data = await resp.json();
        if (data.success) {
            renderPushLog(data.data);
        }
    } catch (error) {
        console.error('Error loading push log:', error);
    }
}

function renderPushLog(logs) {
    const tbody = document.getElementById('push-log-table-body');
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;">暂无操作日志</td></tr>';
        return;
    }
    tbody.innerHTML = logs.reverse().map(log => `
        <tr>
            <td style="font-size:11px;color:#94a3b8;">${(log.timestamp || '').substring(11, 19)}</td>
            <td><span class="strategy-name">${log.source || '--'}</span></td>
            <td style="font-size:11px;">u=${log.u} n=${log.n} → ${log.target_level}</td>
            <td>
                <span style="color:#4caf50;">✅${log.pushed}</span>
                ${log.skipped > 0 ? `<span style="color:#f59e0b;"> ⏭️${log.skipped}</span>` : ''}
                ${(log.codes || []).slice(0, 3).join(', ')}${(log.codes || []).length > 3 ? ' ...' : ''}
            </td>
        </tr>
    `).join('');
}

// ========== 五级流转进度条 ==========

async function updateFlowProgress() {
    try {
        const resp = await fetch('/api/stock_pool/summary');
        const data = await resp.json();
        if (!data.success) return;
        const pools = data.data?.pools || data.data || {};
        const levels = { select: '0', candidate: '0', testing: '0', prelive: '0', live: '0' };
        if (pools.candidate) levels.candidate = String(pools.candidate);
        if (pools.classified) levels.testing = String(pools.classified);
        if (pools.watchlist || pools.adaptive) levels.prelive = String(pools.watchlist || pools.adaptive || 0);
        if (pools.trading) levels.live = String(pools.trading);
        if (pools.candidate && pools.classified) levels.select = String(Number(pools.candidate || 0) + Number(pools.classified || 0));
        else levels.select = levels.candidate;
        for (const [key, val] of Object.entries(levels)) {
            var el = document.getElementById('flow-' + key);
            if (el) el.textContent = val;
        }
    } catch (e) {
        console.error('Flow progress update failed:', e);
    }
}

async function runStockPoolAutoFlow() {
    var steps = document.querySelectorAll('.flow-step');
    steps.forEach(function(s) { s.style.background = '#1a2744'; });
    if (steps[0]) steps[0].style.background = 'rgba(99,102,241,0.3)';
    try {
        var resp = await fetch('/api/stock_pool/auto_flow', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        var data = await resp.json();
        if (data.success) {
            var count = data.data?.flowed || 0;
            steps.forEach(function(s, i) {
                if (i <= Math.min(count, 4)) s.style.background = 'rgba(0,200,83,0.3)';
            });
            alert('✅ 自动流转完成: ' + count + ' 只股票进入下一级');
        } else {
            alert('❌ 流转失败: ' + (data.error || '未知错误'));
        }
    } catch (e) {
        alert('❌ 请求失败: ' + e.message);
    }
    updateFlowProgress();
}

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(updateFlowProgress, 500);
});