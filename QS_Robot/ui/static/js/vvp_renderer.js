/**
 * VVP (Vibe Visualization Protocol) 统一渲染器
 * 
 * 根据后端产出的 VVP 数据格式，自动选择合适的 ECharts 图表进行渲染。
 * 后端只负责产出 VVP 数据，前端负责渲染，实现前后端可视化解耦。
 */

const VVPRenderer = {
    /**
     * 渲染单个 VVPChart 到指定 DOM 容器
     * @param {Object} chart - VVPChart 对象
     * @param {string} containerId - DOM 容器 ID
     * @param {function} drillDownCallback - 下钻回调(chart, params)
     */
    render(chart, containerId, drillDownCallback = null) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error('[VVP] 容器不存在:', containerId);
            return null;
        }
        
        // 设置容器大小
        const height = chart.options?.height || 350;
        container.style.height = height + 'px';
        container.style.width = '100%';
        
        const instance = echarts.init(container);
        const option = this._buildOption(chart);
        
        if (option) {
            instance.setOption(option);
            
            // 绑定下钻事件
            if (chart.drill_down && drillDownCallback) {
                instance.on('click', (params) => {
                    drillDownCallback(chart, params);
                });
            }
        }
        
        // 响应式
        window.addEventListener('resize', () => instance.resize());
        return instance;
    },
    
    /**
     * 渲染 VVPResponse（多个图表）到指定容器
     * @param {Object} vvpResponse - VVPResponse 对象
     * @param {string} parentSelector - 父容器选择器
     * @param {function} drillDownCallback - 下钻回调
     */
    renderAll(vvpResponse, parentSelector, drillDownCallback = null) {
        const parent = document.querySelector(parentSelector);
        if (!parent) return;
        
        // 清空容器
        parent.innerHTML = '';
        
        // 添加标题
        if (vvpResponse.title) {
            const titleEl = document.createElement('h3');
            titleEl.textContent = vvpResponse.title;
            titleEl.style.cssText = 'color: #e2e8f0; margin-bottom: 16px;';
            parent.appendChild(titleEl);
        }
        
        if (vvpResponse.description) {
            const descEl = document.createElement('p');
            descEl.textContent = vvpResponse.description;
            descEl.style.cssText = 'color: #94a3b8; font-size: 13px; margin-bottom: 20px;';
            parent.appendChild(descEl);
        }
        
        // 渲染每个图表
        vvpResponse.charts.forEach((chart, idx) => {
            const chartContainer = document.createElement('div');
            chartContainer.id = `vvp_chart_${idx}`;
            chartContainer.style.cssText = 'margin-bottom: 24px; background: var(--bg-card); border-radius: 12px; padding: 16px;';
            parent.appendChild(chartContainer);
            
            this.render(chart, `vvp_chart_${idx}`, drillDownCallback);
        });
    },
    
    /**
     * 根据 VVPChart 构建 ECharts option
     * @param {Object} chart - VVPChart 对象
     * @returns {Object} ECharts option
     */
    _buildOption(chart) {
        const { chart_type, title, data, options } = chart;
        const baseOption = {
            title: { text: title, left: 'left', textStyle: { color: '#e2e8f0', fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
            backgroundColor: 'transparent',
        };
        
        switch (chart_type) {
            case 'line':
                return this._buildLineChart(baseOption, data, options);
            case 'bar':
                return this._buildBarChart(baseOption, data, options);
            case 'scatter':
                return this._buildScatterChart(baseOption, data, options);
            case 'radar':
                return this._buildRadarChart(baseOption, data, options);
            case 'pie':
                return this._buildPieChart(baseOption, data, options);
            case 'heatmap':
                return this._buildHeatmapChart(baseOption, data, options);
            case 'table':
                return this._buildTable(baseOption, data, options);
            case 'sankey':
                return this._buildSankey(baseOption, data, options);
            default:
                console.warn('[VVP] 不支持的图表类型:', chart_type);
                return null;
        }
    },
    
    _buildLineChart(base, data, options) {
        return {
            ...base,
            tooltip: { trigger: 'axis' },
            xAxis: {
                type: 'category',
                data: data.labels,
                name: options.x_axis || '',
                axisLine: { lineStyle: { color: '#475569' } },
                axisLabel: { color: '#94a3b8' },
            },
            yAxis: {
                type: 'value',
                name: (options.y_axis || '') + (options.unit ? ` (${options.unit})` : ''),
                axisLine: { lineStyle: { color: '#475569' } },
                axisLabel: { color: '#94a3b8' },
                splitLine: { lineStyle: { color: '#1e293b' } },
            },
            series: (data.datasets || []).map(ds => ({
                name: ds.label,
                type: ds.type || 'line',
                data: ds.data,
                smooth: true,
                itemStyle: { color: ds.color || '#4ade80' },
                lineStyle: { color: ds.color || '#4ade80' },
            })),
        };
    },
    
    _buildBarChart(base, data, options) {
        return {
            ...base,
            tooltip: { trigger: 'axis' },
            xAxis: {
                type: 'category',
                data: data.labels,
                axisLabel: { color: '#94a3b8' },
            },
            yAxis: {
                type: 'value',
                name: (options.unit || ''),
                axisLabel: { color: '#94a3b8' },
                splitLine: { lineStyle: { color: '#1e293b' } },
            },
            series: (data.datasets || []).map(ds => ({
                name: ds.label,
                type: 'bar',
                data: ds.data,
                itemStyle: {
                    color: ds.color || '#818cf8',
                    borderRadius: [4, 4, 0, 0],
                },
            })),
        };
    },
    
    _buildScatterChart(base, data, options) {
        const points = data.points || [];
        return {
            ...base,
            tooltip: { trigger: 'item' },
            xAxis: {
                type: 'value',
                name: options.x_axis || '',
                axisLabel: { color: '#94a3b8' },
                splitLine: { lineStyle: { color: '#1e293b' } },
            },
            yAxis: {
                type: 'value',
                name: options.y_axis || '',
                axisLabel: { color: '#94a3b8' },
                splitLine: { lineStyle: { color: '#1e293b' } },
            },
            series: [{
                type: 'scatter',
                data: points.map(p => [p.x, p.y, p.label || '']),
                symbolSize: 8,
                itemStyle: { color: '#4ade80' },
            }],
        };
    },
    
    _buildRadarChart(base, data, options) {
        return {
            ...base,
            tooltip: {},
            radar: {
                indicator: (data.indicators || []).map(ind => ({
                    name: ind.name,
                    max: ind.max || 100,
                })),
                axisName: { color: '#94a3b8' },
                splitArea: {
                    areaStyle: { color: ['rgba(129,140,248,0.02)', 'rgba(129,140,248,0.05)'] },
                },
                splitLine: { lineStyle: { color: '#1e293b' } },
            },
            series: (data.datasets || []).map(ds => ({
                name: ds.label,
                type: 'radar',
                data: [{ value: ds.data, name: ds.label }],
                itemStyle: { color: ds.color || '#4ade80' },
                lineStyle: { color: ds.color || '#4ade80' },
                areaStyle: { color: ds.color ? ds.color + '20' : '#4ade8020' },
            })),
        };
    },
    
    _buildPieChart(base, data, options) {
        const pieData = (data.datasets && data.datasets[0]) ? 
            data.datasets[0].data.map((val, i) => ({
                name: data.labels[i] || '',
                value: val,
            })) : [];
        return {
            ...base,
            tooltip: { trigger: 'item' },
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                data: pieData,
                label: { color: '#94a3b8' },
                itemStyle: { borderRadius: 4, borderColor: '#0f172a', borderWidth: 2 },
            }],
        };
    },
    
    _buildHeatmapChart(base, data, options) {
        const heatData = [];
        const yLabels = data.y_labels || [];
        const values = data.values || [];
        for (let i = 0; i < yLabels.length; i++) {
            for (let j = 0; j < (data.x_labels || []).length; j++) {
                heatData.push([j, i, values[i]?.[j] || 0]);
            }
        }
        return {
            ...base,
            tooltip: { position: 'top' },
            grid: { left: '10%', right: '5%', bottom: '10%', top: '10%' },
            xAxis: {
                type: 'category',
                data: data.x_labels || [],
                splitArea: { show: true },
                axisLabel: { color: '#94a3b8' },
            },
            yAxis: {
                type: 'category',
                data: yLabels,
                splitArea: { show: true },
                axisLabel: { color: '#94a3b8' },
            },
            visualMap: {
                min: 0,
                max: Math.max(...heatData.map(d => d[2] || 0), 1),
                calculable: true,
                orient: 'horizontal',
                left: 'center',
                bottom: '0%',
                inRange: { color: ['#1e293b', '#4ade80', '#fbbf24', '#f87171'] },
            },
            series: [{
                type: 'heatmap',
                data: heatData,
                label: { show: false },
            }],
        };
    },
    
    _buildTable(base, data, options) {
        // 表格渲染为 HTML 而非 ECharts
        return null; // 由 renderAll 中的特殊处理替代
    },
    
    _buildSankey(base, data, options) {
        return {
            ...base,
            series: [{
                type: 'sankey',
                layout: 'none',
                data: data.nodes || [],
                links: (data.links || []).map(l => ({
                    source: l.source,
                    target: l.target,
                    value: l.value,
                })),
                label: { color: '#94a3b8' },
                lineStyle: { color: 'gradient', curveness: 0.5 },
            }],
        };
    },
};

// 导出到全局
window.VVPRenderer = VVPRenderer;