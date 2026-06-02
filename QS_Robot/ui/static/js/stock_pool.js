let poolChart = null;
let strategyChart = null;

document.addEventListener('DOMContentLoaded', function() {
    initEventListeners();
    loadPoolSummary();
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