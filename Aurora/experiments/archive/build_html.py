# -*- coding: utf-8 -*-
import json

OUT_PATH = r'D:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\templates\index.html'

CSS = r"""
:root {
    --bg-primary: #0a0e14; --bg-secondary: #12171f; --bg-card: #161c26;
    --bg-card-hover: #1a2130; --border-subtle: #1e2d3d; --border-active: #4fc3f7;
    --text-primary: #e8ecf0; --text-secondary: #8fa0b0; --text-muted: #5a6e7e;
    --accent-blue: #4fc3f7; --accent-green: #69f0ae; --accent-red: #ef5350;
    --accent-orange: #ffb74d; --accent-purple: #ce93d8; --accent-gold: #ffd54f;
    --shadow-card: 0 2px 12px rgba(0,0,0,0.3);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: var(--bg-primary); color: var(--text-primary);
    font-family: 'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif;
    font-size: 14px; line-height: 1.5; min-height: 100vh;
    -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility; font-synthesis: none;
}
.navbar-top {
    background: linear-gradient(135deg,#0d1a2d,#111d30);
    border-bottom: 2px solid var(--border-subtle); padding: 10px 24px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 16px rgba(0,0,0,0.4); position: sticky; top: 0; z-index: 1000;
}
.navbar-brand {
    font-size: 1.4rem; font-weight: 800;
    background: linear-gradient(135deg,#4fc3f7,#69f0ae);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 2px;
}
.sys-info { display: flex; gap: 18px; font-size: 0.82rem; color: var(--text-secondary); }
.sys-info strong { color: var(--text-primary); font-weight: 600; }
.main-container { padding: 16px 20px; max-width: 1600px; margin: 0 auto; }
.dashboard-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 16px; }
.stat-card {
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 10px; padding: 14px 18px; box-shadow: var(--shadow-card);
    transition: all 0.2s;
}
.stat-card:hover { background: var(--bg-card-hover); border-color: var(--border-active); }
.stat-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; font-synthesis: none; }
.stat-value { font-size: 1.5rem; font-weight: 700; margin-top: 4px; color: var(--text-primary); font-synthesis: none; }
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.chart-panel { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 12px; box-shadow: var(--shadow-card); }
.chart-box { width: 100%; height: 260px; }
.indicator-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.indicator-panel { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 10px; box-shadow: var(--shadow-card); }
.indicator-box { width: 100%; height: 180px; }
.section-title { font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; letter-spacing: 0.02em; font-synthesis: none; }
.section-title::before { content: ''; display: inline-block; width: 4px; height: 18px; background: var(--accent-blue); border-radius: 2px; }
.strategy-section, .optimizer-section, .decision-section, .stock-section, .trade-section {
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 10px; padding: 14px 18px; margin-bottom: 14px;
    box-shadow: var(--shadow-card);
}
.strategy-sub-title { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid var(--border-subtle); font-synthesis: none; }
.strategy-chips { display: flex; flex-wrap: wrap; gap: 8px; min-height: 32px; }
.strategy-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 5px 12px; border-radius: 20px; background: var(--bg-secondary);
    border: 1.5px solid var(--border-subtle); color: var(--text-secondary);
    font-size: 0.78rem; font-weight: 500; cursor: pointer;
    transition: all 0.2s; user-select: none; white-space: nowrap;
}
.strategy-chip:hover { background: #1a2a3a; border-color: var(--accent-blue); color: var(--text-primary); transform: translateY(-1px); box-shadow: 0 2px 8px rgba(79,195,247,0.15); }
.strategy-chip.active { background: linear-gradient(135deg,#0d2a3d,#1a3a50); border-color: var(--accent-blue); color: #fff; font-weight: 600; box-shadow: 0 0 12px rgba(79,195,247,0.3); }
.chip-icon { font-size: 0.9rem; }
.chip-desc { font-size: 0.65rem; color: var(--text-muted); margin-left: 2px; }
.strategy-chip.active .chip-desc { color: #80cbc4; }
.active-strategy-bar { margin-top: 10px; padding: 8px 14px; background: var(--bg-secondary); border-radius: 6px; display: flex; align-items: center; gap: 10px; font-size: 0.78rem; font-synthesis: none; }
.active-strategy-label { color: var(--text-muted); }
.active-strategy-name { color: var(--accent-blue); font-weight: 700; font-size: 0.9rem; letter-spacing: 0.02em; font-synthesis: none; }
.link-indicator { display: flex; align-items: center; gap: 6px; margin-left: auto; font-size: 0.75rem; padding: 4px 12px; border-radius: 20px; background: var(--bg-card); border: 1px solid var(--border-subtle); }
.link-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-red); transition: all 0.3s; }
.link-dot.connected { background: var(--accent-green); box-shadow: 0 0 8px rgba(105,240,174,0.5); animation: pulse-dot 1.5s infinite; }
@keyframes pulse-dot { 0%,100%{ box-shadow: 0 0 4px rgba(105,240,174,0.4); } 50%{ box-shadow: 0 0 12px rgba(105,240,174,0.8); } }
.optimizer-target { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px; }
.optimizer-target strong { color: var(--accent-blue); }
.optimizer-options { display: flex; flex-direction: column; gap: 8px; }
.optimizer-option { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border-radius: 6px; background: var(--bg-secondary); border: 1.5px solid var(--border-subtle); cursor: pointer; transition: all 0.2s; }
.optimizer-option:hover { background: #1a2a3a; border-color: var(--accent-blue); }
.optimizer-option.selected { border-color: var(--accent-green); background: linear-gradient(135deg,#0d2a1d,#1a3028); box-shadow: 0 0 10px rgba(105,240,174,0.2); }
.optimizer-radio { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-subtle); flex-shrink: 0; margin-top: 2px; transition: all 0.2s; }
.optimizer-option.selected .optimizer-radio { border-color: var(--accent-green); background: var(--accent-green); box-shadow: inset 0 0 0 3px var(--bg-secondary); }
.optimizer-name { font-weight: 700; color: var(--text-primary); font-size: 0.88rem; font-synthesis: none; }
.optimizer-version { font-size: 0.7rem; color: var(--accent-blue); background: rgba(79,195,247,0.1); padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
.optimizer-features { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.optimizer-feature-tag { font-size: 0.65rem; padding: 1px 7px; border-radius: 12px; background: rgba(206,147,216,0.15); color: var(--accent-purple); border: 1px solid rgba(206,147,216,0.25); }
.optimizer-actions { display: flex; gap: 8px; margin-top: 10px; }
.btn-optimize { padding: 8px 20px; border: none; border-radius: 8px; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: all 0.2s; letter-spacing: 0.02em; font-synthesis: none; }
.btn-run { background: linear-gradient(135deg,#4fc3f7,#29b6f6); color: #0a0e14; }
.btn-run:hover:not(:disabled) { box-shadow: 0 0 16px rgba(79,195,247,0.5); transform: translateY(-1px); }
.btn-run:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-evolve { background: transparent; border: 1.5px solid var(--accent-purple); color: var(--accent-purple); }
.btn-evolve:hover:not(:disabled) { background: rgba(206,147,216,0.1); box-shadow: 0 0 12px rgba(206,147,216,0.3); }
.btn-result { background: transparent; border: 1.5px solid var(--accent-gold); color: var(--accent-gold); font-size: 0.78rem; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s; }
.btn-result:hover:not(:disabled) { background: rgba(255,213,79,0.1); }
.optimizer-progress { display: none; margin-top: 10px; padding: 10px 14px; border-radius: 6px; background: var(--bg-secondary); }
.optimizer-progress.active { display: block; }
.progress-track { height: 6px; background: var(--border-subtle); border-radius: 3px; overflow: hidden; margin-bottom: 6px; }
.progress-bar-fill { height: 100%; width: 0%; background: linear-gradient(90deg,var(--accent-blue),var(--accent-green)); border-radius: 3px; transition: width 0.4s; }
.progress-stage { font-size: 0.72rem; color: var(--text-secondary); }
.optimize-result { display: none; margin-top: 10px; padding: 12px 14px; border-radius: 6px; background: var(--bg-secondary); border: 1px solid var(--accent-green); }
.optimize-result.active { display: block; }
.gene-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 0.7rem; }
.gene-bar-label { width: 80px; color: var(--text-secondary); flex-shrink: 0; }
.gene-bar-track { flex: 1; height: 14px; background: var(--border-subtle); border-radius: 4px; position: relative; overflow: hidden; }
.gene-bar-fill-before { position: absolute; left: 0; top: 0; height: 100%; background: rgba(239,83,80,0.4); border-radius: 4px; }
.gene-bar-fill-after { position: absolute; left: 0; top: 0; height: 100%; background: rgba(105,240,174,0.5); border-radius: 4px; border-right: 2px solid var(--accent-green); }
.decision-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; font-size: 0.78rem; }
.decision-item { padding: 8px 10px; background: var(--bg-secondary); border-radius: 6px; }
.decision-label { color: var(--text-muted); font-size: 0.68rem; font-synthesis: none; }
.decision-value { color: var(--text-primary); font-weight: 600; }
.add-stock-form { display: flex; gap: 8px; margin-bottom: 10px; }
.add-stock-form input { flex: 1; padding: 6px 10px; border-radius: 6px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); color: var(--text-primary); font-size: 0.78rem; }
.btn-add-stock { padding: 6px 16px; border: none; border-radius: 6px; background: var(--accent-blue); color: #0a0e14; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
#stock-list, #trade-list { max-height: 200px; overflow-y: auto; font-size: 0.78rem; }
@media (max-width:1024px) { .dashboard-row { grid-template-columns: repeat(2,1fr); } .charts-grid { grid-template-columns: 1fr; } .decision-grid { grid-template-columns: repeat(2,1fr); } }
"""

JS = r"""
const CORE_STRATEGIES = [
    {id:'cls',name:'分类模型策略',desc:'ML分类',icon:'🤖'},
    {id:'lgbm',name:'LightGBM策略',desc:'梯度提升',icon:'🌳'},
    {id:'ensemble',name:'集成学习策略',desc:'多模型投票',icon:'🗣️'},
    {id:'dl',name:'深度学习策略',desc:'神经网络',icon:'🧠'},
];
const TYPE_STRATEGIES = {
    uptrend: [
        {id:'momentum',name:'动量突破',desc:'趋势跟踪',icon:'🚀'},
        {id:'movingavg',name:'均线多头',desc:'MA金叉',icon:'📈'},
        {id:'breakout',name:'通道突破',desc:'布林上轨',icon:'⚡'},
    ],
    downtrend: [
        {id:'short',name:'空头追击',desc:'做空策略',icon:'📉'},
        {id:'hedge',name:'对冲保护',desc:'风险缓释',icon:'🛡️'},
        {id:'put',name:'看跌配置',desc:'认沽期权',icon:'⬇️'},
    ],
    sideways: [
        {id:'grid',name:'网格交易',desc:'区间套利',icon:'🔳'},
        {id:'meanrev',name:'均值回归',desc:'震荡回归',icon:'🔄'},
        {id:'pair',name:'配对交易',desc:'协整套利',icon:'🔗'},
    ],
    volatile: [
        {id:'straddle',name:'跨式策略',desc:'双向波动',icon:'↕️'},
        {id:'dynamic',name:'动态自适应',desc:'波动率调节',icon:'🌀'},
        {id:'vix',name:'VIX联动',desc:'恐慌指数',icon:'💥'},
    ]
};
const OPTIMIZERS = [
    {
        id:'shepherd-v5', name:'牧羊人智能体优化器', version:'V5', icon:'🐑⚙️',
        features: ['遗传算法','粒子群优化','模拟退火','贝叶斯优化','回测验证','多目标帕累托'],
        stages: ['加载策略参数','初始化种群','遗传迭代','粒子群优化','模拟退火精调','贝叶斯验证','回测评估','输出最优解']
    },
    {
        id:'shepherd-v6', name:'牧羊人智能体优化器', version:'V6', icon:'🐑✨',
        features: ['深度强化自演进','自适应变异率','迁移学习','实时市场适配','对抗生成验证','多智能体协同','量子退火模拟','自进化基因库'],
        stages: ['加载策略参数','环境模拟构建','初始化多智能体群','协同训练','对抗验证','自演进变异','迁移学习适配','实盘模拟评估','基因库更新','输出进化最优解']
    }
];
let activeStrategy = null;
let selectedOptimizer = null;
let isOptimizing = false;
let optimizeTimer = null;

function renderStrategyChips(containerId, strategies) {
    const container = document.getElementById(containerId);
    if(!container) return;
    container.innerHTML = strategies.map(function(s) {
        return '<div class="strategy-chip" data-strategy="'+s.id+'" data-name="'+s.name+'" onclick="selectStrategy(this)">'+
            '<span class="chip-icon">'+s.icon+'</span>'+
            '<span>'+s.name+'</span>'+
            '<span class="chip-desc">'+s.desc+'</span>'+
        '</div>';
    }).join('');
}
function renderAllStrategies() {
    renderStrategyChips('core-strategies', CORE_STRATEGIES);
    renderStrategyChips('uptrend-strategies', TYPE_STRATEGIES.uptrend);
    renderStrategyChips('downtrend-strategies', TYPE_STRATEGIES.downtrend);
    renderStrategyChips('sideways-strategies', TYPE_STRATEGIES.sideways);
    renderStrategyChips('volatile-strategies', TYPE_STRATEGIES.volatile);
}
function selectStrategy(el) {
    document.querySelectorAll('.strategy-chip.active').forEach(function(c) { c.classList.remove('active'); });
    el.classList.add('active');
    activeStrategy = { id: el.dataset.strategy, name: el.dataset.name };
    document.getElementById('active-strategy-display').textContent = el.dataset.name;
    document.getElementById('optimizer-target-strategy').textContent = el.dataset.name;
    document.getElementById('link-indicator').classList.add('connected');
    document.getElementById('link-status-text').textContent = '已联通优化器';
    updateOptimizerButtons();
    checkOptimizerReady();
}
function renderOptimizers() {
    var container = document.getElementById('optimizer-options');
    container.innerHTML = OPTIMIZERS.map(function(o) {
        return '<div class="optimizer-option" data-optimizer="'+o.id+'" onclick="selectOptimizer(this)">'+
            '<div class="optimizer-radio"></div>'+
            '<div>'+
                '<div>'+
                    '<span class="optimizer-name">'+o.icon+' '+o.name+'</span>'+
                    '<span class="optimizer-version">'+o.version+'</span>'+
                '</div>'+
                '<div class="optimizer-features">'+
                    o.features.map(function(f) { return '<span class="optimizer-feature-tag">'+f+'</span>'; }).join('')+
                '</div>'+
            '</div>'+
        '</div>';
    }).join('');
}
function selectOptimizer(el) {
    document.querySelectorAll('.optimizer-option.selected').forEach(function(o) { o.classList.remove('selected'); });
    el.classList.add('selected');
    selectedOptimizer = el.dataset.optimizer;
    updateOptimizerButtons();
}
function updateOptimizerButtons() {
    var canOptimize = activeStrategy !== null && selectedOptimizer !== null && !isOptimizing;
    document.getElementById('btn-run-optimize').disabled = !canOptimize;
    document.getElementById('btn-evolve').disabled = !canOptimize;
}
function checkOptimizerReady() {
    if(activeStrategy && selectedOptimizer) { updateOptimizerButtons(); }
}
function runOptimize() {
    if(!activeStrategy || !selectedOptimizer || isOptimizing) return;
    isOptimizing = true;
    updateOptimizerButtons();
    document.getElementById('btn-run-optimize').disabled = true;
    document.getElementById('btn-evolve').disabled = true;
    document.getElementById('btn-view-result').disabled = true;
    var opt = OPTIMIZERS.find(function(o) { return o.id === selectedOptimizer; });
    var stages = opt ? opt.stages : ['优化中...'];
    var progressDiv = document.getElementById('optimizer-progress');
    var progressBar = document.getElementById('progress-bar');
    var progressStage = document.getElementById('progress-stage');
    var resultDiv = document.getElementById('optimize-result');
    resultDiv.classList.remove('active');
    progressDiv.classList.add('active');
    var stageIndex = 0;
    var totalStages = stages.length;
    function advanceStage() {
        if(stageIndex >= totalStages) { finishOptimize(opt); return; }
        var pct = Math.floor((stageIndex / totalStages) * 100);
        progressBar.style.width = pct + '%';
        progressStage.textContent = (stageIndex+1)+'/'+totalStages+' '+stages[stageIndex]+'...';
        stageIndex++;
        optimizeTimer = setTimeout(advanceStage, 400 + Math.random() * 300);
    }
    advanceStage();
}
function finishOptimize(opt) {
    var progressBar = document.getElementById('progress-bar');
    var progressStage = document.getElementById('progress-stage');
    progressBar.style.width = '100%';
    progressStage.textContent = '优化完成！';
    isOptimizing = false;
    updateOptimizerButtons();
    document.getElementById('btn-run-optimize').disabled = false;
    document.getElementById('btn-evolve').disabled = false;
    document.getElementById('btn-view-result').disabled = false;
    document.getElementById('optimizer-progress').classList.remove('active');
    var resultDiv = document.getElementById('optimize-result');
    resultDiv.classList.add('active');
    var genes = [
        {name:'入场阈值', before:42, after:Math.floor(55+Math.random()*35)},
        {name:'止损比例', before:35, after:Math.floor(60+Math.random()*30)},
        {name:'持仓周期', before:30, after:Math.floor(50+Math.random()*45)},
        {name:'风险权重', before:28, after:Math.floor(60+Math.random()*35)},
        {name:'适应率', before:20, after:Math.floor(55+Math.random()*40)},
    ];
    document.getElementById('optimize-result-content').innerHTML =
        '<div style="font-size:0.78rem;margin-bottom:8px;color:var(--accent-green);font-weight:700;font-synthesis:none;">✔ '+activeStrategy.name+' 优化完成 ('+opt.name+' '+opt.version+')</div>'+
        genes.map(function(g) {
            return '<div class="gene-bar-row">'+
                '<span class="gene-bar-label">'+g.name+'</span>'+
                '<div class="gene-bar-track"><div class="gene-bar-fill-before" style="width:'+g.before+'%"></div><div class="gene-bar-fill-after" style="width:'+g.after+'%"></div></div>'+
                '<span style="font-size:0.65rem;color:var(--text-muted);width:60px;text-align:right;">'+g.before+'→'+g.after+'</span>'+
            '</div>';
        }).join('') +
        '<div style="margin-top:8px;font-size:0.72rem;color:var(--accent-green);">综合评分: '+(70+Math.random()*28).toFixed(1)+'分 | 预期收益提升: +'+(12+Math.random()*20).toFixed(1)+'%</div>';
}
function runEvolve() {
    if(!activeStrategy || !selectedOptimizer || isOptimizing) return;
    runOptimize();
    setTimeout(function() {
        var resultContent = document.getElementById('optimize-result-content');
        var extra = '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border-subtle);font-size:0.72rem;color:var(--accent-purple);">'+
            '<div>🧬 自演进记录:</div>'+
            '<div>· 基因库更新: +'+(Math.floor(Math.random()*5)+1)+'条新基因</div>'+
            '<div>· 变异率自适应: '+(0.05+Math.random()*0.1).toFixed(3)+'→'+(0.02+Math.random()*0.08).toFixed(3)+'</div>'+
            '<div>· 迁移学习模型更新: '+['成功','成功','部分成功'][Math.floor(Math.random()*3)]+'</div>'+
        '</div>';
        if(resultContent) resultContent.innerHTML += extra;
    }, 2500);
}
function viewResult() {
    var resultDiv = document.getElementById('optimize-result');
    if(resultDiv.classList.contains('active')) { resultDiv.scrollIntoView({behavior:'smooth'}); }
    else { alert('暂无历史优化记录，请先运行优化。'); }
}
function initCharts() {
    if(typeof echarts === 'undefined') return;
    var dates = [];
    for(var i=0;i<60;i++) dates.push(''+(i+1));
    // Price chart
    var priceDom = document.getElementById('price-chart');
    if(priceDom) {
        var priceChart = echarts.init(priceDom);
        var prices = []; var p = 100;
        for(var i=0;i<60;i++) { p+= (Math.random()-0.45)*3; prices.push(parseFloat(p.toFixed(2))); }
        priceChart.setOption({
            darkMode: true, backgroundColor: 'transparent',
            grid: {left:50,right:15,top:10,bottom:30},
            xAxis: {data:dates,axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:10}},
            yAxis: {axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:10},splitLine:{lineStyle:{color:'#1e2d3d'}}},
            series: [{type:'line',data:prices,lineStyle:{color:'#4fc3f7',width:1.5},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(79,195,247,0.25)'},{offset:1,color:'rgba(79,195,247,0.02)'}]}},itemStyle:{color:'#4fc3f7'},symbol:'none',smooth:true}],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){priceChart.resize();});
    }
    // Performance chart
    var perfDom = document.getElementById('performance-chart');
    if(perfDom) {
        var perfChart = echarts.init(perfDom);
        var r = 0; var rets = [];
        for(var i=0;i<60;i++){ r+= (Math.random()-0.48)*1.5; rets.push(parseFloat(r.toFixed(2))); }
        perfChart.setOption({
            darkMode: true, backgroundColor: 'transparent',
            grid: {left:50,right:15,top:10,bottom:30},
            xAxis: {data:dates,axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:10}},
            yAxis: {axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:10},splitLine:{lineStyle:{color:'#1e2d3d'}}},
            series: [{type:'line',data:rets,lineStyle:{color:'#69f0ae',width:1.5},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(105,240,174,0.25)'},{offset:1,color:'rgba(105,240,174,0.02)'}]}},itemStyle:{color:'#69f0ae'},symbol:'none',smooth:true}],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){perfChart.resize();});
    }
    // RSI
    var rsiDom = document.getElementById('rsi-chart');
    if(rsiDom) {
        var rsiChart = echarts.init(rsiDom);
        var rsiVal = 50; var rsiData = [];
        for(var i=0;i<60;i++){ rsiVal+= (Math.random()-0.5)*6; rsiVal=Math.max(20,Math.min(80,rsiVal)); rsiData.push(parseFloat(rsiVal.toFixed(1))); }
        rsiChart.setOption({
            darkMode: true, backgroundColor: 'transparent',
            grid: {left:45,right:15,top:5,bottom:25},
            xAxis: {data:dates,axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:9}},
            yAxis: {min:0,max:100,axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:9},splitLine:{lineStyle:{color:'#1e2d3d'}}},
            series: [{type:'line',data:rsiData,lineStyle:{color:'#ce93d8',width:1.2},itemStyle:{color:'#ce93d8'},symbol:'none',smooth:true,
                markLine:{silent:true,lineStyle:{color:'#5a6e7e',type:'dashed'},data:[{yAxis:70,label:{show:true,color:'#ef5350',fontSize:9,formatter:'70'}},{yAxis:30,label:{show:true,color:'#69f0ae',fontSize:9,formatter:'30'}}]}
            }],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){rsiChart.resize();});
    }
    // MACD
    var macdDom = document.getElementById('macd-chart');
    if(macdDom) {
        var macdChart = echarts.init(macdDom);
        var dif=0,dea=0;
        var difData=[],deaData=[],macdData=[];
        for(var i=0;i<60;i++){ dif+= (Math.random()-0.5)*0.4; dea=dif*0.7+dea*0.3; difData.push(parseFloat(dif.toFixed(3))); deaData.push(parseFloat(dea.toFixed(3))); macdData.push(parseFloat(((dif-dea)*2).toFixed(3))); }
        macdChart.setOption({
            darkMode: true, backgroundColor: 'transparent',
            grid: {left:55,right:15,top:5,bottom:25},
            xAxis: {data:dates,axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:9}},
            yAxis: {axisLine:{lineStyle:{color:'#1e2d3d'}},axisLabel:{color:'#5a6e7e',fontSize:9},splitLine:{lineStyle:{color:'#1e2d3d'}}},
            series: [
                {type:'bar',data:macdData,itemStyle:{color:function(p){return p.value>=0?'#ef5350':'#69f0ae';}}},
                {type:'line',data:difData,lineStyle:{color:'#4fc3f7',width:1},symbol:'none',smooth:true},
                {type:'line',data:deaData,lineStyle:{color:'#ffb74d',width:1},symbol:'none',smooth:true},
            ],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){macdChart.resize();});
    }
}
function updateMockData() {
    var price = (150+Math.random()*30).toFixed(2);
    var vol = Math.floor(Math.random()*5000000+1000000).toLocaleString();
    var volatility = (15+Math.random()*15).toFixed(2)+'%';
    var now = new Date();
    var timeStr = now.toLocaleTimeString('zh-CN',{hour12:false}) + '.' + String(now.getMilliseconds()).padStart(3,'0');
    document.getElementById('current-price').textContent = '$'+price;
    document.getElementById('current-time').textContent = timeStr;
    document.getElementById('current-volume').textContent = vol;
    document.getElementById('current