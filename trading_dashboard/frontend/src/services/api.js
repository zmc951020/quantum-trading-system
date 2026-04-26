import axios from 'axios';

// 创建axios实例
const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// 风控相关API
export const riskApi = {
  // 计算VaR和CVaR
  calculateVaR: (data) => api.post('/risk/var', data),
  // 运行压力测试
  runStressTest: (data) => api.post('/risk/stress-test', data),
  // 获取压力测试场景
  getStressScenarios: () => api.get('/risk/scenarios')
};

// 绩效归因相关API
export const performanceApi = {
  // 计算绩效归因
  calculateAttribution: (data) => api.post('/performance/attribution', data),
  // 获取性能指标
  getPerformanceMetrics: () => api.get('/performance/metrics')
};

// 投资组合相关API
export const portfolioApi = {
  // 获取投资组合概览
  getPortfolioOverview: (data) => api.post('/portfolio/overview', data),
  // 获取持仓信息
  getPositions: (data) => api.post('/portfolio/positions', data),
  // 获取投资组合历史数据
  getPortfolioHistory: () => api.get('/portfolio/history')
};

// 健康检查API
export const healthApi = {
  // 获取服务健康状态
  getHealthStatus: () => api.get('/health/status'),
  // 获取健康指标
  getHealthMetrics: () => api.get('/health/metrics')
};

export default api;
