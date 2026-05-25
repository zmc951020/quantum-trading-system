(function(){
'use strict';

// ============================================================
// DATA CONFIGURATION
// ============================================================
var CORE_STRATEGIES = [
    {id:'cls',name:'分类模型策略',desc:'ML多分类',icon:'🤖',category:'core'},
    {id:'lgbm',name:'LightGBM策略',desc:'梯度提升树',icon:'🌳',category:'core'},
    {id:'ensemble',name:'集成学习策略',desc:'多模型投票',icon:'🗣️',category:'core'},
    {id:'dl',name:'深度学习策略',desc:'神经网络',icon:'🧠',category:'core'},
    {id:'rl',name:'强化学习策略',desc:'Q-Learning',icon:'🎮',category:'core'},
    {id:'transformer',name:'Transformer策略',desc:'时间序列注意力',icon:'🔮',category:'core'}
];

var TYPE_STRATEGIES = {
    uptrend: [
        {id:'momentum',name:'动量突破',desc:'趋势跟踪',icon:'🚀',market:'上涨'},
        {id:'movingavg',name:'均线多头排列',desc:'MA金叉共振',icon:'📈',market:'上涨'},
        {id:'breakout',name:'通道突破',desc:'布林上轨',icon:'⚡',market:'上涨'},
        {id:'trendfollow',name:'趋势跟随',desc:'ADX顺势',icon:'🎯',market:'上涨'}
    ],
    downtrend: [
        {id:'short',name:'空头追击',desc:'做空策略',icon:'📉',market:'下跌'},
        {id:'hedge',name:'对冲保护',desc:'风险缓释',icon:'🛡️',market:'下跌'},
        {id:'put',name:'看跌配置',desc:'认沽期权',icon:'⬇️',market:'下跌'},
        {id:'bearspread',name:'熊市价差',desc:'价差套利',icon:'🐻',market:'下跌'}
    ],
    sideways: [
        {id:'grid',name:'网格交易',desc:'区间套利',icon:'🔳',market:'横盘'},
        {id:'meanrev',name:'均值回归',desc:'震荡回归',icon:'🔄',market:'横盘'},
        {id:'pair',name:'配对交易',desc:'协整套利',icon:'🔗',market:'横盘'},
        {id:'rangebound',name:'区间振荡器',desc:'RSI边界',icon:'📊',market:'横盘'}
    ],
    volatile: [
        {id:'straddle',name:'跨式策略',desc:'双向波动',icon:'↕️',market:'波动'},
        {id:'dynamic',name:'动态自适应',desc:'波动率调节',icon:'🌀',market:'波动'},
        {id:'vix',name:'VIX联动',desc:'恐慌指数',icon:'💥',market:'波动'},
        {id:'garch',name:'GARCH预测',desc:'波动率建模',icon:'📐',market:'波动'}
    ]
};

var OPTIMIZERS = [
    {
        id:'shepherd-v5',
        name:'牧羊人智能体优化器',
        version:'V5',
        icon:'🐑⚙️',
        features:['遗传算法','粒子群优化','模拟退火','贝叶斯优化','回测验证','多目标帕累托','参数自编码'],
        stages:['加载策略参数','初始化种群','遗传迭代搜索','粒子群协同优化','模拟退火精调','贝叶斯参数验证','历史回测评估','输出帕累托最优解']
    },
    {
        id:'shepherd-v6',
        name:'牧羊人智能体优化器',
        version:'V6',
        icon:'🐑✨',
        features:['深度强化自演进','自适应变异率','迁移学习','实时市场适配','对抗生成验证','多智能体协同','量子退火模拟','自进化基因库'],
        stages:['加载策略参数','构建市场环境模拟','初始化多智能体群','协同对抗训练','自演进变异搜索','迁移学习适配','实盘模拟验证','基因库优胜劣汰','输出进化最优解']
    }
];

// ============================================================
// STATE
// ============================================================
var activeStrategy = null;
var activeStrategyCategory = '';
var selectedOptimizer = null;
var isOptimizing = false;
var optimizeTimer = null;
var mockInterval = null;

// ============================================================
// DOM HELPERS
// ============================================================
function $(id){ return document.getElementById(id); }

// ============================================================
// STRATEGY RENDERING
// ============================================================
function renderStrategyChips(containerId, strategies){
    var container = $(containerId);
    if(!container) return;
    container.innerHTML = strategies.map(function(s){
        var cat = s.category || s.market || '';
        return '<div class="strategy-chip" data-strategy="'+s.id+'" data-name="'+s.name+'" data-category="'+cat+'" onclick="App.selectStrategy(this)">'+
            '<span class="chip-icon">'+s.icon+'</span>'+
            '<span>'+s.name+'</span>'+
            '<span class="chip-desc">'+s.desc+'</span>'+
        '</div>';
    }).join('');
}

function renderAllStrategies(){
    renderStrategyChips('core-strategies', CORE_STRATEGIES);
    renderStrategyChips('uptrend-strategies', TYPE_STRATEGIES.uptrend);
    renderStrategyChips('downtrend-strategies', TYPE_STRATEGIES.downtrend);
    renderStrategyChips('sideways-strategies', TYPE_STRATEGIES.sideways);
    renderStrategyChips('volatile-strategies', TYPE_STRATEGIES.volatile);
}

// ============================================================
// STRATEGY SELECTION + LINK TO OPTIMIZER
// ============================================================
function selectStrategy(el){
    document.querySelectorAll('.strategy-chip.active').forEach(function(c){c.classList.remove('active');});
    el.classList.add('active');
    activeStrategy = {id: el.dataset.strategy, name: el.dataset.name};
    activeStrategyCategory = el.dataset.category || '';
    $('active-strategy-display').textContent = el.dataset.name;
    $('active-strategy-category').textContent = activeStrategyCategory ? '('+activeStrategyCategory+')' : '';
    $('optimizer-target-strategy').textContent = el.dataset.name + (activeStrategyCategory ? ' ['+activeStrategyCategory+']' : '');
    // Link indicator
    var linkDot = $('link-indicator');
    var linkText = $('link-status-text');
    linkDot.classList.add('connected');
    linkText.textContent = '已联通优化器';
    updateOptimizerButtons();
}

// ============================================================
// OPTIMIZER RENDERING
// ============================================================
function renderOptimizers(){
    var container = $('optimizer-options');
    container.innerHTML = OPTIMIZERS.map(function(o){
        return '<div class="optimizer-option" data-optimizer="'+o.id+'" onclick="App.selectOptimizer(this)">'+
            '<div class="optimizer-radio"></div>'+
            '<div>'+
                '<div>'+
                    '<span class="optimizer-name">'+o.icon+' '+o.name+'</span>'+
                    '<span class="optimizer-version">'+o.version+'</span>'+
                '</div>'+
                '<div class="optimizer-features">'+
                    o.features.map(function(f){return '<span class="optimizer-feature-tag">'+f+'</span>';}).join('')+
                '</div>'+
            '</div>'+
        '</div>';
    }).join('');
}

function selectOptimizer(el){
    document.querySelectorAll('.optimizer-option.selected').forEach(function(o){o.classList.remove('selected');});
    el.classList.add('selected');
    selectedOptimizer = el.dataset.optimizer;
    updateOptimizerButtons();
}

// ============================================================
// BUTTON STATE MANAGEMENT
// ============================================================
function updateOptimizerButtons(){
    var canOptimize = activeStrategy !== null && selectedOptimizer !== null && !isOptimizing;
    $('btn-run-optimize').disabled = !canOptimize;
    $('btn-evolve').disabled = !canOptimize;
}

// ============================================================
// OPTIMIZE RUN
// ============================================================
function runOptimize(){
    if(!activeStrategy || !selectedOptimizer || isOptimizing) return;
    isOptimizing = true;
    updateOptimizerButtons();
    $('btn-run-optimize').disabled = true;
    $('btn-evolve').disabled = true;
    $('btn-view-result').disabled = true;
    var opt = OPTIMIZERS.find(function(o){return o.id === selectedOptimizer;});
    var stages = opt ? opt.stages : ['优化中...'];
    var progressDiv = $('optimizer-progress');
    var progressBar = $('progress-bar');
    var progressStage = $('progress-stage');
    var resultDiv = $('optimize-result');
    resultDiv.classList.remove('active');
    progressDiv.classList.add('active');
    var stageIndex = 0;
    var totalStages = stages.length;
    function advanceStage(){
        if(stageIndex >= totalStages){finishOptimize(opt);return;}
        var pct = Math.floor((stageIndex/totalStages)*100);
        progressBar.style.width = pct+'%';
        progressStage.textContent = (stageIndex+1)+'/'+totalStages+' '+stages[stageIndex]+'...';
        stageIndex++;
        optimizeTimer = setTimeout(advanceStage, 400+Math.random()*350);
    }
    advanceStage();
}

function finishOptimize(opt){
    $('progress-bar').style.width = '100%';
    $('progress-stage').textContent = '✅ 优化完成！';
    isOptimizing = false;
    updateOptimizerButtons();
    $('btn-run-optimize').disabled = false;
    $('btn-evolve').disabled = false;
    $('btn-view-result').disabled = false;
    $('optimizer-progress').classList.remove('active');
    var resultDiv = $('optimize-result');
    resultDiv.classList.add('active');
    var genes = [
        {name:'入场阈值',before:42,after:Math.floor(55+Math.random()*35)},
        {name:'止损比例',before:35,after:Math.floor(60+Math.random()*30)},
        {name:'持仓周期',before:30,after:Math.floor(50+Math.random()*45)},
        {name:'风险权重',before:28,after:Math.floor(60+Math.random()*35)},
        {name:'适应率',before:20,after:Math.floor(55+Math.random()*40)}
    ];
    $('optimize-result-content').innerHTML =
        '<div style="font-size:0.78rem;margin-bottom:8px;color:var(--accent-green);font-weight:800;font-synthesis:none;">✔ '+activeStrategy.name+' 优化完成 ('+(opt?opt.name:'')+' '+(opt?opt.version:'')+')</div>'+
        genes.map(function(g){
            return '<div class="gene-bar-row">'+
                '<span class="gene-bar-label">'+g.name+'</span>'+
                '<div class="gene-bar-track"><div class="gene-bar-fill-before" style="width:'+g.before+'%"></div><div class="gene-bar-fill-after" style="width:'+g.after+'%"></div></div>'+
                '<span style="font-size:0.64rem;color:var(--text-muted);width:60px;text-align:right;">'+g.before+'→'+g.after+'</span>'+
            '</div>';
        }).join('')+
        '<div style="margin-top:8px;font-size:0.7rem;color:var(--accent-green);">📊 综合评分: '+(70+Math.random()*28).toFixed(1)+'分 | 预期收益提升: +'+(12+Math.random()*20).toFixed(1)+'%</div>';
    resultDiv.scrollIntoView({behavior:'smooth'});
}

// ============================================================
// SELF-EVOLVE
// ============================================================
function runEvolve(){
    if(!activeStrategy || !selectedOptimizer || isOptimizing) return;
    runOptimize();
    setTimeout(function(){
        var resultContent = $('optimize-result-content');
        var extra = '<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border-subtle);font-size:0.7rem;color:var(--accent-purple);">'+
            '<div>🧬 自演进记录:</div>'+
            '<div>· 基因库更新: +'+(Math.floor(Math.random()*5)+1)+'条新基因</div>'+
            '<div>· 变异率自适应优化</div>'+
            '<div>· 迁移学习模型更新: 完成</div>'+
        '</div>';
        if(resultContent) resultContent.innerHTML += extra;
    },2600);
}

// ============================================================
// VIEW RESULT
// ============================================================
function viewResult(){
    var resultDiv = $('optimize-result');
    if(resultDiv.classList.contains('active')){
        resultDiv.scrollIntoView({behavior:'smooth'});
    } else {
        alert('暂无历史优化记录，请先运行优化。');
    }
}

// ============================================================
// ECHARTS INITIALIZATION
// ============================================================
function initCharts(){
    if(typeof echarts === 'undefined') return;
    var dates = [];
    for(var i=0;i<60;i++) dates.push(''+(i+1));
    // Price chart
    var priceDom = $('price-chart');
    if(priceDom){
        var priceChart = echarts.init(priceDom);
        var prices = []; var p = 100;
        for(var i=0;i<60;i++){p+=(Math.random()-0.45)*3;prices.push(parseFloat(p.toFixed(2)));}
        priceChart.setOption({
            darkMode:true,backgroundColor:'transparent',
            grid:{left:52,right:15,top:10,bottom:30},
            xAxis:{data:dates,axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:10}},
            yAxis:{axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:10},splitLine:{lineStyle:{color:'#1a2838'}}},
            series:[{type:'line',data:prices,lineStyle:{color:'#4fc3f7',width:1.5},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(79,195,247,0.25)'},{offset:1,color:'rgba(79,195,247,0.02)'}]}},itemStyle:{color:'#4fc3f7'},symbol:'none',smooth:true}],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){priceChart.resize();});
    }
    // Performance chart
    var perfDom = $('performance-chart');
    if(perfDom){
        var perfChart = echarts.init(perfDom);
        var r=0,rets=[];
        for(var i=0;i<60;i++){r+=(Math.random()-0.48)*1.5;rets.push(parseFloat(r.toFixed(2)));}
        perfChart.setOption({
            darkMode:true,backgroundColor:'transparent',
            grid:{left:52,right:15,top:10,bottom:30},
            xAxis:{data:dates,axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:10}},
            yAxis:{axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:10},splitLine:{lineStyle:{color:'#1a2838'}}},
            series:[{type:'line',data:rets,lineStyle:{color:'#69f0ae',width:1.5},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(105,240,174,0.25)'},{offset:1,color:'rgba(105,240,174,0.02)'}]}},itemStyle:{color:'#69f0ae'},symbol:'none',smooth:true}],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){perfChart.resize();});
    }
    // RSI
    var rsiDom = $('rsi-chart');
    if(rsiDom){
        var rsiChart = echarts.init(rsiDom);
        var rsiVal=50,rsiData=[];
        for(var i=0;i<60;i++){rsiVal+=(Math.random()-0.5)*6;rsiVal=Math.max(20,Math.min(80,rsiVal));rsiData.push(parseFloat(rsiVal.toFixed(1)));}
        rsiChart.setOption({
            darkMode:true,backgroundColor:'transparent',
            grid:{left:48,right:15,top:5,bottom:25},
            xAxis:{data:dates,axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:9}},
            yAxis:{min:0,max:100,axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:9},splitLine:{lineStyle:{color:'#1a2838'}}},
            series:[{type:'line',data:rsiData,lineStyle:{color:'#ce93d8',width:1.2},itemStyle:{color:'#ce93d8'},symbol:'none',smooth:true,
                markLine:{silent:true,lineStyle:{color:'#526677',type:'dashed'},data:[{yAxis:70,label:{show:true,color:'#ef5350',fontSize:9,formatter:'70'}},{yAxis:30,label:{show:true,color:'#69f0ae',fontSize:9,formatter:'30'}}]}
            }],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){rsiChart.resize();});
    }
    // MACD
    var macdDom = $('macd-chart');
    if(macdDom){
        var macdChart = echarts.init(macdDom);
        var dif=0,dea=0,difData=[],deaData=[],macdData=[];
        for(var i=0;i<60;i++){dif+=(Math.random()-0.5)*0.4;dea=dif*0.7+dea*0.3;difData.push(parseFloat(dif.toFixed(3)));deaData.push(parseFloat(dea.toFixed(3)));macdData.push(parseFloat(((dif-dea)*2).toFixed(3)));}
        macdChart.setOption({
            darkMode:true,backgroundColor:'transparent',
            grid:{left:58,right:15,top:5,bottom:25},
            xAxis:{data:dates,axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:9}},
            yAxis:{axisLine:{lineStyle:{color:'#1a2838'}},axisLabel:{color:'#526677',fontSize:9},splitLine:{lineStyle:{color:'#1a2838'}}},
            series:[
                {type:'bar',data:macdData,itemStyle:{color:function(p){return p.value>=0?'#ef5350':'#69f0ae';}}},
                {type:'line',data:difData,lineStyle:{color:'#4fc3f7',width:1},symbol:'none',smooth:true},
                {type:'line',data:deaData,lineStyle:{color:'#ffb74d',width:1},symbol:'none',smooth:true}
            ],
            tooltip:{trigger:'axis'}
        });
        window.addEventListener('resize',function(){macdChart.resize();});
    }
}

// ============================================================
// MOCK DATA UPDATE
// ============================================================
function updateMockData(){
    var price = (150+Math.random()*30).toFixed(2);
    var vol = Math.floor(Math.random()*5000000+1000000).toLocaleString('en-US');
    var volatility = (15+Math.random()*15).toFixed(2)+'%';
    var now = new Date();
    var timeStr = now.toLocaleTimeString('zh-CN',{hour12:false})+'.'+String(now.getMilliseconds()).padStart(3,'0');
    $('current-price').textContent = '$'+price;
    $('current-time').textContent = timeStr;
    $('current-volume').textContent = vol;
    $('current-volatility').textContent = volatility;
    // Dashboard stats
    $('total-return').textContent = '+'+(5+Math.random()*20).toFixed(2)+'%';
    $('current-balance').textContent = '$'+(800000+Math.random()*200000).toFixed(0);
    $('current-position').textContent = (40+Math.random()*50).toFixed(1)+'%';
    $('total-trades').textContent = Math.floor(Math.random()*300+100);
    // Decision
    var signals = ['买入','持有','卖出','增持','减持'];
    var regimes = ['上涨趋势','下跌趋势','横盘震荡','高波动'];
    var hmmStates = ['Stable','Transition','Volatile','Trending'];
    var strategies = CORE_STRATEGIES.concat(
        TYPE_STRATEGIES.uptrend,TYPE_STRATEGIES.downtrend,
        TYPE_STRATEGIES.sideways,TYPE_STRATEGIES.volatile
    );
    $('hmm-state').textContent = hmmStates[Math.floor(Math.random()*4)];
    $('trend-type').textContent = ['上涨','下跌','横盘','震荡'][Math.floor(Math.random()*4)];
    $('recommended-signal').textContent = signals[Math.floor(Math.random()*5)];
    $('recommended-position').textContent = (10+Math.random()*60).toFixed(0)+'%';
    $('recommended-strategy').textContent = strategies[Math.floor(Math.random()*strategies.length)].name;
    $('risk-score').textContent = (1+Math.random()*9).toFixed(1)+'/10';
    $('decision-description').textContent = '基于HMM市场状态与优化器输出，建议采取稳健策略，动态调整仓位。';
    $('regime-label').textContent = regimes[Math.floor(Math.random()*4)];
}

// ============================================================
// STOCK POOL & TRADE LOG
// ============================================================
function addStock(){
    var symbol = $('new-stock-symbol').value.trim();
    var name = $('new-stock-name').value.trim();
    if(!symbol){return;}
    var list = $('stock-list');
    var price = (Math.random()*500+20).toFixed(2);
    list.innerHTML += '<div class="stock-item"><span>'+symbol+' - '+(name||symbol)+'</span><span>$'+price+'</span></div>';
    addTrade('添加股票',symbol+'加入股票池');
    $('new-stock-symbol').value = '';
    $('new-stock-name').value = '';
}

function addTrade(type,detail){
    var list = $('trade-list');
    var now = new Date();
    var time = now.toLocaleTimeString('zh-CN',{hour12:false});
    list.innerHTML = '<div class="trade-item">['+time+'] '+type+': '+detail+'</div>' + list.innerHTML;
    // Keep max 50
    var items = list.querySelectorAll('.trade-item');
    for(var i=50;i<items.length;i++){items[i].remove();}
}

// ============================================================
// INIT
// ============================================================
function init(){
    renderAllStrategies();
    renderOptimizers();
    initCharts();
    updateMockData();
    mockInterval = setInterval(updateMockData,2000);
    // Event listeners
    $('btn-run-optimize').addEventListener('click',runOptimize);
    $('btn-evolve').addEventListener('click',runEvolve);
    $('btn-view-result').addEventListener('click',viewResult);
    $('add-stock-btn').addEventListener('click',addStock);
    $('new-stock-symbol').addEventListener('keypress',function(e){if(e.key==='Enter')addStock();});
}

// Export to global for onclick handlers
window.App = {
    selectStrategy: selectStrategy,
    selectOptimizer: selectOptimizer
};

// Start when DOM ready
if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded',init);
} else {
    init();
}

})();