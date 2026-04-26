import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Select, Button, Spin, Alert } from 'antd';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { riskApi } from '../services/api';

const { Option } = Select;

const RiskMonitoring = () => {
  const [loading, setLoading] = useState(false);
  const [varData, setVarData] = useState(null);
  const [stressTestData, setStressTestData] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState('2008_financial_crisis');

  useEffect(() => {
    // 加载压力测试场景
    const loadScenarios = async () => {
      try {
        const res = await riskApi.getStressScenarios();
        setScenarios(res);
      } catch (error) {
        console.error('加载场景失败:', error);
      }
    };

    loadScenarios();
  }, []);

  // 计算VaR
  const calculateVaR = async () => {
    try {
      setLoading(true);
      // 模拟收益率数据
      const returns = Array.from({ length: 100 }, () => (Math.random() - 0.5) * 0.02);
      const res = await riskApi.calculateVaR({
        returns,
        confidence_level: 0.95,
        method: 'historical'
      });
      setVarData(res);
    } catch (error) {
      console.error('计算VaR失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 运行压力测试
  const runStressTest = async () => {
    try {
      setLoading(true);
      // 模拟投资组合价值数据
      const portfolioValues = Array.from({ length: 100 }, (_, i) => 1000000 * (1 + i * 0.001 + Math.random() * 0.02));
      const res = await riskApi.runStressTest({
        portfolio_values: portfolioValues,
        scenario: selectedScenario
      });
      setStressTestData(res);
    } catch (error) {
      console.error('压力测试失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 压力测试场景映射
  const scenarioMapping = {
    '2008_financial_crisis': '2008金融危机',
    '2020_covid': '2020新冠疫情',
    '2015_stock_crash': '2015股灾',
    '1987_black_monday': '1987黑色星期一',
    '2022_interest_rate_hike': '2022美联储加息'
  };

  // 模拟风险数据图表
  const riskChartData = [
    { name: '1月', var: -0.02, cvar: -0.03, actual: -0.01 },
    { name: '2月', var: -0.025, cvar: -0.035, actual: -0.015 },
    { name: '3月', var: -0.02, cvar: -0.03, actual: -0.012 },
    { name: '4月', var: -0.03, cvar: -0.04, actual: -0.018 },
    { name: '5月', var: -0.02, cvar: -0.03, actual: -0.01 },
    { name: '6月', var: -0.025, cvar: -0.035, actual: -0.015 },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>风控监控</h1>

      {/* VaR/CVaR计算 */}
      <Card title="VaR/CVaR计算" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Button type="primary" onClick={calculateVaR} loading={loading}>
              计算VaR/CVaR
            </Button>
          </Col>
        </Row>

        {varData && (
          <Row style={{ marginTop: '24px' }} gutter={16}>
            <Col span={8}>
              <Card size="small" title="VaR (95%)">
                <Statistic 
                  value={varData.var * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="CVaR (95%)">
                <Statistic 
                  value={varData.cvar * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="计算方法">
                <Statistic value={varData.method === 'historical' ? '历史模拟法' : varData.method} />
              </Card>
            </Col>
          </Row>
        )}

        {/* 风险图表 */}
        <div style={{ marginTop: '24px', height: '400px' }}>
          <h3>风险趋势</h3>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={riskChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value) => [`${(value * 100).toFixed(2)}%`, '']} />
              <Legend />
              <Line type="monotone" dataKey="var" name="VaR" stroke="#ff4d4f" strokeWidth={2} />
              <Line type="monotone" dataKey="cvar" name="CVaR" stroke="#faad14" strokeWidth={2} />
              <Line type="monotone" dataKey="actual" name="实际损失" stroke="#52c41a" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* 压力测试 */}
      <Card title="压力测试" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Select
              style={{ width: 200 }}
              value={selectedScenario}
              onChange={setSelectedScenario}
            >
              {scenarios.map(scenario => (
                <Option key={scenario} value={scenario}>
                  {scenarioMapping[scenario] || scenario}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={8}>
            <Button type="primary" onClick={runStressTest} loading={loading}>
              运行压力测试
            </Button>
          </Col>
        </Row>

        {stressTestData && (
          <Row style={{ marginTop: '24px' }} gutter={16}>
            <Col span={8}>
              <Card size="small" title="测试场景">
                <Statistic value={scenarioMapping[stressTestData.scenario] || stressTestData.scenario} />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="估计损失">
                <Statistic 
                  value={stressTestData.estimated_loss} 
                  precision={2} 
                  suffix="元"
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="损失比例">
                <Statistic 
                  value={stressTestData.estimated_loss_pct * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
          </Row>
        )}

        {/* 压力测试结果图表 */}
        <div style={{ marginTop: '24px', height: '400px' }}>
          <h3>压力测试结果</h3>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={[
              { name: '2008金融危机', loss: 40 },
              { name: '2020新冠', loss: 35 },
              { name: '2015股灾', loss: 45 },
              { name: '1987黑色周一', loss: 22 },
              { name: '2022加息', loss: 25 },
            ]}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value) => [`${value}%`, '损失']} />
              <Legend />
              <Bar dataKey="loss" name="损失比例" fill="#ff4d4f" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* 风险指标 */}
      <Card title="风险指标" style={{ marginBottom: '24px' }}>
        <Table 
          dataSource={[
            { key: '1', name: '风险价值 (VaR)', value: '2.5%', status: '正常' },
            { key: '2', name: '条件风险价值 (CVaR)', value: '3.5%', status: '正常' },
            { key: '3', name: '最大回撤', value: '15%', status: '正常' },
            { key: '4', name: '波动率', value: '12%', status: '正常' },
            { key: '5', name: '风险预算使用率', value: '75%', status: '正常' },
          ]}
          columns={[
            { title: '指标名称', dataIndex: 'name', key: 'name' },
            { title: '数值', dataIndex: 'value', key: 'value' },
            { 
              title: '状态', 
              dataIndex: 'status', 
              key: 'status',
              render: (status) => (
                <span style={{ color: status === '正常' ? '#52c41a' : '#ff4d4f' }}>
                  {status}
                </span>
              )
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default RiskMonitoring;
