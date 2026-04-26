import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Button, Spin, Table, Alert } from 'antd';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { performanceApi } from '../services/api';

const PerformanceAttribution = () => {
  const [loading, setLoading] = useState(false);
  const [attributionData, setAttributionData] = useState(null);
  const [metricsData, setMetricsData] = useState(null);

  // 计算绩效归因
  const calculateAttribution = async () => {
    try {
      setLoading(true);
      // 模拟收益率数据
      const portfolioReturns = Array.from({ length: 100 }, () => (Math.random() - 0.4) * 0.01);
      const benchmarkReturns = Array.from({ length: 100 }, () => (Math.random() - 0.5) * 0.01);
      
      const res = await performanceApi.calculateAttribution({
        portfolio_returns: portfolioReturns,
        benchmark_returns: benchmarkReturns
      });
      setAttributionData(res);
    } catch (error) {
      console.error('计算归因失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 获取性能指标
  const getMetrics = async () => {
    try {
      setLoading(true);
      const res = await performanceApi.getPerformanceMetrics();
      setMetricsData(res);
    } catch (error) {
      console.error('获取指标失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 模拟归因数据
  const attributionChartData = [
    { name: '总收益', value: 15 },
    { name: '基准收益', value: 10 },
    { name: 'Alpha', value: 5 },
    { name: '选股收益', value: 3 },
    { name: '配置收益', value: 2 },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>绩效归因</h1>

      {/* 绩效归因计算 */}
      <Card title="绩效归因计算" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Button type="primary" onClick={calculateAttribution} loading={loading}>
              计算绩效归因
            </Button>
          </Col>
          <Col span={8}>
            <Button type="default" onClick={getMetrics} loading={loading}>
              获取性能指标
            </Button>
          </Col>
        </Row>

        {attributionData && (
          <Row style={{ marginTop: '24px' }} gutter={16}>
            <Col span={6}>
              <Card size="small" title="总收益">
                <Statistic 
                  value={attributionData.total_return * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="基准收益">
                <Statistic 
                  value={attributionData.benchmark_return * 100} 
                  precision={2} 
                  suffix="%"
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="Alpha">
                <Statistic 
                  value={attributionData.alpha * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="信息比率">
                <Statistic value={attributionData.information_ratio} precision={2} />
              </Card>
            </Col>
          </Row>
        )}

        {/* 归因图表 */}
        <div style={{ marginTop: '24px', height: '400px' }}>
          <h3>收益归因分析</h3>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={attributionChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value) => [`${value}%`, '收益']} />
              <Legend />
              <Bar dataKey="value" name="收益" fill="#1890ff" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* 性能指标 */}
      <Card title="性能指标" style={{ marginBottom: '24px' }}>
        {metricsData && (
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" title="夏普比率">
                <Statistic value={metricsData.sharpe_ratio} precision={2} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="索提诺比率">
                <Statistic value={metricsData.sortino_ratio} precision={2} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="卡玛比率">
                <Statistic value={metricsData.calmar_ratio} precision={2} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="最大回撤">
                <Statistic 
                  value={metricsData.max_drawdown * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={6} style={{ marginTop: '16px' }}>
              <Card size="small" title="胜率">
                <Statistic 
                  value={metricsData.win_rate * 100} 
                  precision={2} 
                  suffix="%"
                />
              </Card>
            </Col>
            <Col span={6} style={{ marginTop: '16px' }}>
              <Card size="small" title="利润因子">
                <Statistic value={metricsData.profit_factor} precision={2} />
              </Card>
            </Col>
          </Row>
        )}

        {!metricsData && (
          <Alert 
            message="请点击获取性能指标按钮" 
            type="info" 
            showIcon 
          />
        )}
      </Card>

      {/* 归因详情 */}
      <Card title="归因详情" style={{ marginBottom: '24px' }}>
        <Table 
          dataSource={[
            { key: '1', category: '选股收益', value: '3.00%', contribution: '60%' },
            { key: '2', category: '配置收益', value: '2.00%', contribution: '40%' },
            { key: '3', category: '市场时机', value: '0.00%', contribution: '0%' },
            { key: '4', category: '交易成本', value: '-0.50%', contribution: '-10%' },
          ]}
          columns={[
            { title: '类别', dataIndex: 'category', key: 'category' },
            { title: '收益', dataIndex: 'value', key: 'value' },
            { title: '贡献', dataIndex: 'contribution', key: 'contribution' },
          ]}
        />
      </Card>
    </div>
  );
};

export default PerformanceAttribution;
