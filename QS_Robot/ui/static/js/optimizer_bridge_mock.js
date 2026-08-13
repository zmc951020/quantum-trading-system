/**
 * 优化器桥接Mock数据生成器
 * =========================
 * 为策略-优化器关联面板提供可复用的Mock数据生成逻辑。
 * 模块引入: <script src="/static/js/optimizer_bridge_mock.js"></script>
 *
 * 使用:
 *   const result = generateOptimizerMockResult('fourier_rl', 'tau_cluster');
 *   console.log(result.sharpe, result.drawdown, result.iterations);
 */

// 预设优化器参数范围（用于生成合理的Mock数据）
const OPTIMIZER_PARAM_RANGES = {
    tau_cluster: { sharpeRange: [1.2, 3.8], drawdownRange: [3, 12], iterRange: [80, 200] },
    tau_enhanced_optimizer: { sharpeRange: [1.0, 3.5], drawdownRange: [5, 15], iterRange: [60, 180] },
    shepherd_optimizer: { sharpeRange: [0.8, 3.0], drawdownRange: [8, 18], iterRange: [50, 150] },
    gyro_optimizer: { sharpeRange: [1.5, 4.0], drawdownRange: [2, 10], iterRange: [100, 250] },
    genetic: { sharpeRange: [0.5, 2.5], drawdownRange: [10, 25], iterRange: [30, 120] },
    bayesian: { sharpeRange: [0.8, 3.2], drawdownRange: [6, 16], iterRange: [40, 130] },
    grid_search: { sharpeRange: [0.3, 2.0], drawdownRange: [12, 28], iterRange: [20, 80] },
    default: { sharpeRange: [0.5, 3.0], drawdownRange: [10, 20], iterRange: [50, 150] },
};

/**
 * 生成单次优化器Mock结果
 * @param {string} strategyName - 策略名称
 * @param {string} optimizerName - 优化器名称
 * @returns {{sharpe: number, drawdown: number, iterations: number, params: object, timestamp: string}}
 */
function generateOptimizerMockResult(strategyName, optimizerName) {
    const range = OPTIMIZER_PARAM_RANGES[optimizerName] || OPTIMIZER_PARAM_RANGES.default;
    const sharpe = range.sharpeRange[0] + Math.random() * (range.sharpeRange[1] - range.sharpeRange[0]);
    const drawdown = range.drawdownRange[0] + Math.random() * (range.drawdownRange[1] - range.drawdownRange[0]);
    const iterations = Math.floor(range.iterRange[0] + Math.random() * (range.iterRange[1] - range.iterRange[0]));
    return {
        sharpe: parseFloat(sharpe.toFixed(4)),
        drawdown: parseFloat(drawdown.toFixed(2)),
        iterations,
        params: {
            u: parseFloat((0.1 + Math.random() * 0.9).toFixed(2)),
            n: Math.floor(3 + Math.random() * 7),
            threshold: parseFloat((0.5 + Math.random() * 0.5).toFixed(2)),
        },
        timestamp: new Date().toISOString(),
    };
}

/**
 * 批量生成多个策略-优化器组合的Mock结果
 * @param {string[]} strategyNames - 策略名称列表
 * @param {string[]} optimizerNames - 优化器名称列表
 * @returns {Array<{strategy: string, optimizer: string, result: object}>}
 */
function batchGenerateOptimizerMock(strategyNames, optimizerNames) {
    const results = [];
    for (const s of strategyNames) {
        for (const o of optimizerNames) {
            results.push({
                strategy: s,
                optimizer: o,
                result: generateOptimizerMockResult(s, o),
            });
        }
    }
    return results;
}

/**
 * 生成用于热力图展示的Mock数据矩阵
 * @param {string[]} strategyNames - 策略名称列表
 * @param {string[]} optimizerNames - 优化器名称列表
 * @returns {{strategies: string[], optimizers: string[], matrix: number[][]}}
 */
function generateOptimizerHeatmapMock(strategyNames, optimizerNames) {
    const matrix = [];
    for (const s of strategyNames) {
        const row = [];
        for (const o of optimizerNames) {
            const r = generateOptimizerMockResult(s, o);
            row.push(parseFloat(r.sharpe.toFixed(2)));
        }
        matrix.push(row);
    }
    return {
        strategies: strategyNames,
        optimizers: optimizerNames,
        matrix,
        generated_at: new Date().toISOString(),
    };
}

/**
 * 格式化Mock结果为可读HTML
 * @param {string} strategyName - 策略名称
 * @param {string} optimizerName - 优化器名称
 * @param {object} result - generateOptimizerMockResult 返回的结果
 * @returns {string} HTML字符串
 */
function formatOptimizerMockHTML(strategyName, optimizerName, result) {
    const color = result.sharpe >= 2.5 ? '#00c853' : result.sharpe >= 1.5 ? '#ffab40' : '#ff5252';
    return `<span style="color:${color};">
        ✅ Mock优化完成: ${strategyName} x ${optimizerName}
        | 最佳夏普: ${result.sharpe.toFixed(2)}
        | 最大回撤: ${result.drawdown.toFixed(1)}%
        | 迭代: ${result.iterations}轮
        | 参数: u=${result.params.u}, n=${result.params.n}
    </span>`;
}

console.log('[OptimizerBridgeMock] 工具函数已加载: generateOptimizerMockResult, batchGenerateOptimizerMock, generateOptimizerHeatmapMock');