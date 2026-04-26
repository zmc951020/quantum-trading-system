import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Button, Spin, Progress, Tag } from 'antd';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { portfolioApi } from '../services/api';

const PortfolioMonitoring = () => {
  const [loading, setLoading] = useState(false);
  const [portfolioData, setPortfolioData] = useState(null);
  const [positionsData, setPositionsData] = useState(null);
  const [historyData, setHistoryData] = useState(null);

  useEffect(() => {
    // 加载投资组合数据
    const loadData = async () => {
      try {
        setLoading(true);
        
        // 获取投资组合概览
        const portfolioRes = await portfolioApi.getPortfolioOverview({ portfolio_id: 'portfolio1' });
        setPortfolioData(portfolioRes);
        
        // 获取持仓信息
        const positionsRes = await portfolioApi.getPositions({ portfolio_id: 'portfolio1' });
        setPositionsData(positionsRes);
        
        // 获取历史数据
        const historyRes = await portfolioApi.getPortfolioHistory();
        setHistoryData(historyRes);
      } catch (error) {
        console.error('加载数据失败:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // 加载数据
  const loadData = async () => {
    try {
      setLoading(true);
      
      // 获取投资组合概览
      const portfolioRes = await portfolioApi.getPortfolioOverview({ portfolio_id: 'portfolio1' });
      setPortfolioData(portfolioRes);
      
      // 获取持仓信息
      const positionsRes = await portfolioApi.getPositions({ portfolio_id: 'portfolio1' });
      setPositionsData(positionsRes);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 持仓数据转换为饼图数据
  const pieData = positionsData?.positions.map(pos => ({
    name: pos.symbol,
    value: pos.weight * 100
  })) || [];

  // 饼图颜色
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>投资组合监控</h1>

      {/* 投资组合概览 */}
      <Card title="投资组合概览" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Button type="primary" onClick={loadData} loading={loading}>
              刷新数据
            </Button>
          </Col>
        </Row>

        {portfolioData && (
          <Row style={{ marginTop: '24px' }} gutter={16}>
            <Col span={6}>
              <Card size="small" title="总价值">
                <Statistic 
                  value={portfolioData.total_value} 
                  precision={2} 
                  suffix="元"
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="总盈亏">
                <Statistic 
                  value={portfolioData.total_pnl} 
                  precision={2} 
                  suffix="元"
                  valueStyle={{ color: portfolioData.total_pnl >= 0 ? '#52c41a' : '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="盈亏比例">
                <Statistic 
                  value={portfolioData.total_pnl_pct * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: portfolioData.total_pnl_pct >= 0 ? '#52c41a' : '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="夏普比率">
                <Statistic value={portfolioData.sharpe_ratio} precision={2} />
              </Card>
            </Col>
          </Row>
        )}

        {/* 资金曲线 */}
        {historyData && (
          <div style={{ marginTop: '24px', height: '400px' }}>
            <h3>资金曲线</h3>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={historyData.dates.map((date, index) => ({
                date,
                value: historyData.values[index]
              }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip formatter={(value) => [`${value.toFixed(2)}元`, '资金']} />
                <Legend />
                <Line type="monotone" dataKey="value" name="资金" stroke="#1890ff" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* 持仓分析 */}
      <Card title="持仓分析" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={12}>
            <h3>持仓分布</h3>
            {positionsData && (
              <div style={{ height: '400px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      outerRadius={150}
                      fill="#8884d8"
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => [`${value.toFixed(2)}%`, '权重']} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Col>
          <Col span={12}>
            <h3>持仓详情</h3>
            {positionsData && (
              <Table 
                dataSource={positionsData.positions}
                columns={[
                  { title: '标的', dataIndex: 'symbol', key: 'symbol' },
                  { title: '数量', dataIndex: 'quantity', key: 'quantity' },
                  { title: '价格', dataIndex: 'price', key: 'price' },
                  { title: '权重', dataIndex: 'weight', key: 'weight', render: (weight) => `${(weight * 100).toFixed(2)}%` },
                  { 
                    title: '盈亏', 
                    dataIndex: 'pnl', 
                    key: 'pnl',
                    render: (pnl) => (
                      <span style={{ color: pnl >= 0 ? '#52c41a' : '#ff4d4f' }}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}元
                      </span>
                    )
                  },
                ]}
                pagination={false}
              />
            )}
            {positionsData && (
              <div style={{ marginTop: '20px' }}>
                <Card size="small" title="现金">
                  <Statistic value={positionsData.cash} precision={2} suffix="元" />
                </Card>
              </div>
            )}
          </Col>
        </Row>
      </Card>

      {/* 风险分析 */}
      <Card title="风险分析" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Card size="small" title="最大回撤">
              <Statistic 
                value={portfolioData?.max_drawdown * 100 || 0} 
                precision={2} 
                suffix="%"
                valueStyle={{ color: '#ff4d4f' }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" title="风险暴露">
              <Progress 
                percent={75} 
                status="normal" 
                strokeColor={{ from: '#108ee9', to: '#87d068' }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" title="持仓数量">
              <Statistic value={positionsData?.total_positions || 0} />
            </Card>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default PortfolioMonitoring;
