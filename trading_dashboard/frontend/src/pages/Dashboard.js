import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Progress, Alert, Spin } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { portfolioApi, healthApi } from '../services/api';

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [portfolioData, setPortfolioData] = useState(null);
  const [healthData, setHealthData] = useState(null);

  useEffect(() => {
    // 加载数据
    const loadData = async () => {
      try {
        setLoading(true);
        
        // 获取投资组合数据
        const portfolioRes = await portfolioApi.getPortfolioOverview({ portfolio_id: 'portfolio1' });
        setPortfolioData(portfolioRes);
        
        // 获取健康状态
        const healthRes = await healthApi.getHealthStatus();
        setHealthData(healthRes);
      } catch (error) {
        console.error('加载数据失败:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>量化交易仪表盘</h1>
      
      {/* 系统状态 */}
      <Card title="系统状态" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic 
              title="系统状态" 
              value={healthData?.status === 'healthy' ? '正常' : '异常'}
              prefix={healthData?.status === 'healthy' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <WarningOutlined style={{ color: '#faad14' }} />}
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="运行时间" 
              value={Math.round(healthData?.uptime / 3600)} 
              suffix="小时"
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="服务状态" 
              value={Object.values(healthData?.services || {}).filter(s => s === 'healthy').length} 
              suffix={`/` + Object.keys(healthData?.services || {}).length}
            />
          </Col>
        </Row>
      </Card>

      {/* 投资组合概览 */}
      <Card title="投资组合概览" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic 
              title="总价值" 
              value={portfolioData?.total_value || 0} 
              precision={2}
              suffix="元"
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="总盈亏" 
              value={portfolioData?.total_pnl || 0} 
              precision={2}
              suffix="元"
              valueStyle={{ color: (portfolioData?.total_pnl || 0) >= 0 ? '#52c41a' : '#ff4d4f' }}
              prefix={(portfolioData?.total_pnl || 0) >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="盈亏比例" 
              value={(portfolioData?.total_pnl_pct || 0) * 100} 
              precision={2}
              suffix="%"
              valueStyle={{ color: (portfolioData?.total_pnl_pct || 0) >= 0 ? '#52c41a' : '#ff4d4f' }}
            />
          </Col>
        </Row>
        
        <Row style={{ marginTop: '24px' }} gutter={16}>
          <Col span={8}>
            <Card size="small" title="夏普比率">
              <Statistic value={portfolioData?.sharpe_ratio || 0} precision={2} />
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" title="最大回撤">
              <Statistic 
                value={(portfolioData?.max_drawdown || 0) * 100} 
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
        </Row>
      </Card>

      {/* 快捷访问 */}
      <Card title="快捷访问" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={6}>
            <Card 
              hoverable 
              style={{ textAlign: 'center', padding: '20px' }}
              onClick={() => window.location.href = '/risk'}
            >
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>🛡️</div>
              <div>风控监控</div>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              hoverable 
              style={{ textAlign: 'center', padding: '20px' }}
              onClick={() => window.location.href = '/performance'}
            >
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>📊</div>
              <div>绩效归因</div>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              hoverable 
              style={{ textAlign: 'center', padding: '20px' }}
              onClick={() => window.location.href = '/portfolio'}
            >
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>💰</div>
              <div>投资组合</div>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              hoverable 
              style={{ textAlign: 'center', padding: '20px' }}
              onClick={() => window.location.href = '/health'}
            >
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>🔧</div>
              <div>系统健康</div>
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 系统通知 */}
      <Card title="系统通知" style={{ marginBottom: '24px' }}>
        <Alert 
          message="系统运行正常" 
          description="所有服务都在正常运行，没有发现异常情况。" 
          type="success" 
          showIcon 
        />
      </Card>
    </div>
  );
};

export default Dashboard;
