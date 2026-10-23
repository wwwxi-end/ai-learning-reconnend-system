/**
 * ECharts 辅助工具函数
 * 提供统一的图表初始化、更新和响应式处理
 */

// 注册全局ECharts实例管理
window._echartInstances = window._echartInstances || {};

/**
 * 创建或更新ECharts图表
 * @param {string} containerId - 容器ID
 * @param {object} option - ECharts配置
 * @param {boolean} clear - 是否清除旧配置
 */
function createChart(containerId, option, clear = false) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    let chart = window._echartInstances[containerId];
    if (!chart || chart.isDisposed()) {
        chart = echarts.init(container, null, { renderer: 'canvas' });
        window._echartInstances[containerId] = chart;
    }
    if (clear) chart.clear();
    chart.setOption(option);
    return chart;
}

/**
 * 生成分数颜色（ECharts颜色字符串）
 */
function scoreColor(score) {
    if (score === null || score === undefined) return '#d9d9d9';
    if (score >= 60) return '#52c41a';
    if (score >= 40) return '#faad14';
    return '#ff4d4f';
}

/**
 * 生成标准柱状图配置
 */
function barChartOption(categories, values, colors, title = '') {
    return {
        title: title ? { text: title, textStyle: { fontSize: 13 } } : undefined,
        tooltip: { trigger: 'axis', formatter: '{b}: {c}分' },
        grid: { left: '3%', right: '3%', bottom: '20%', containLabel: true },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { rotate: 30, fontSize: 10, interval: 0 }
        },
        yAxis: { type: 'value', max: 100, name: '分数' },
        series: [{
            type: 'bar',
            barMaxWidth: 40,
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: colors ? colors[i] : scoreColor(v), borderRadius: [4, 4, 0, 0] }
            })),
            label: { show: true, position: 'top', fontSize: 10, formatter: (params) => {
                const val = params.value;
                return Number.isInteger(val) ? val : val.toFixed(2);
            }},
            markLine: {
                data: [{ yAxis: 60, lineStyle: { color: '#ff4d4f', type: 'dashed', width: 1.5 } }],
                label: { formatter: '60分线' }
            }
        }]
    };
}

/**
 * 生成雷达图配置
 */
function radarChartOption(indicators, values, seriesName = '掌握程度') {
    return {
        tooltip: {},
        radar: {
            indicator: indicators,
            radius: '65%',
            splitArea: { areaStyle: { color: ['#f0f7ff', '#fff', '#f0f7ff', '#fff', '#f0f7ff'] } }
        },
        series: [{
            type: 'radar',
            name: seriesName,
            data: [{
                value: values,
                name: seriesName,
                areaStyle: { color: 'rgba(24, 144, 255, 0.2)' },
                lineStyle: { color: '#1890ff', width: 2 },
                itemStyle: { color: '#1890ff' }
            }]
        }]
    };
}

/**
 * 生成饼图配置
 */
function pieChartOption(data, title = '') {
    return {
        title: title ? { text: title, left: 'center', textStyle: { fontSize: 13 } } : undefined,
        tooltip: { trigger: 'item', formatter: '{b}: {c}个 ({d}%)' },
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        series: [{
            type: 'pie',
            radius: ['38%', '65%'],
            data: data,
            label: { show: true, formatter: '{b}\n{c}个' },
            emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' } }
        }]
    };
}

/**
 * 生成折线图配置（学习趋势）
 */
function lineChartOption(dates, scores, kpNames) {
    return {
        tooltip: {
            trigger: 'axis',
            formatter: params => {
                const p = params[0];
                return `${p.axisValue}<br>${kpNames[p.dataIndex] || ''}<br>分数: <b>${p.value}</b>`;
            }
        },
        grid: { left: '3%', right: '3%', bottom: '10%', containLabel: true },
        xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', min: 0, max: 100, name: '分数' },
        series: [{
            type: 'line', smooth: true,
            data: scores,
            symbol: 'circle', symbolSize: 6,
            lineStyle: { color: '#1890ff', width: 2 },
            itemStyle: { color: params => scoreColor(params.value) },
            areaStyle: { color: { type: 'linear', x:0, y:0, x2:0, y2:1,
                colorStops: [{offset:0, color:'rgba(24,144,255,0.2)'}, {offset:1, color:'rgba(24,144,255,0)'}] } },
            markLine: {
                data: [{ yAxis: 60, lineStyle: { color: '#ff4d4f', type: 'dashed' } }],
                label: { formatter: '60分线' }
            }
        }]
    };
}

// 响应式：窗口大小变化时自动调整所有图表
window.addEventListener('resize', () => {
    Object.values(window._echartInstances).forEach(chart => {
        if (chart && !chart.isDisposed()) chart.resize();
    });
});

// Jinja2 自定义过滤器兼容（在前端解析 JSON 标签列表）
// 注意：from_json 过滤器需要在 Flask 注册
if (typeof window !== 'undefined') {
    window.fromJson = function(str) {
        try { return JSON.parse(str || '[]'); } catch { return []; }
    };
}
