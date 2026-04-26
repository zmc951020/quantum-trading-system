import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Button, Spin, Table, Progress, Tag } from 'antd';
import { healthApi } from '../services/api';

const SystemHealth = () => {
  const [loading, setLoading] = useState(false);
  const [statusData, setStatusData] = useState(null);
  const [metricsData, setMetricsData] = useState(null);

  // 刷新数据
  const refreshData = async () => {
    try {
      setLoading(true);
      
      // 获取健康状态
      const statusRes = await healthApi.getHealthStatus();
      setStatusData(statusRes);
      
      // 获取健康指标
      const metricsRes = await healthApi.getHealthMetrics();
      setMetricsData(metricsRes);
    } catch (error) {
      console.error('获取健康数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // 初始加载数据
    refreshData();
  }, []);

  // 服务状态颜色
  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy': return '#52c41a';
      case 'warning': return '#faad14';
      case 'error': return '#ff4d4f';
      default: return '#1890ff';
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>系统健康监控</h1>

      {/* 系统状态 */}
      <Card title="系统状态" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Button type="primary" onClick={refreshData} loading={loading}>
              刷新数据
            </Button>
          </Col>
        </Row>

        {statusData && (
          <Row style={{ marginTop: '24px' }} gutter={16}>
            <Col span={8}>
              <Card size="small" title="系统状态">
                <Statistic 
                  value={statusData.status === 'healthy' ? '正常' : '异常'}
                  valueStyle={{ color: getStatusColor(statusData.status) }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="运行时间">
                <Statistic 
                  value={Math.round(statusData.uptime / 3600)} 
                  suffix="小时"
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="时间戳">
                <Statistic 
                  value={new Date(statusData.timestamp * 1000).toLocaleString()}
                />
              </Card>
            </Col>
          </Row>
        )}

        {/* 服务状态 */}
        {statusData && (
          <div style={{ marginTop: '24px' }}>
            <h3>服务状态</h3>
            <Table 
              dataSource={Object.entries(statusData.services || {}).map(([name, status], index) => ({
                key: index,
                name: name,
                status: status
              }))}
              columns={[
                { title: '服务名称', dataIndex: 'name', key: 'name' },
                { 
                  title: '状态', 
                  dataIndex: 'status', 
                  key: 'status',
                  render: (status) => (
                    <Tag color={getStatusColor(status)}>
                      {status === 'healthy' ? '正常' : status === 'warning' ? '警告' : '错误'}
                    </Tag>
                  )
                },
              ]}
            />
          </div>
        )}
      </Card>

      {/* 健康指标 */}
      <Card title="健康指标" style={{ marginBottom: '24px' }}>
        {metricsData && (
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" title="CPU使用率">
                <Progress 
                  percent={metricsData.cpu_usage * 100} 
                  status={metricsData.cpu_usage > 0.8 ? 'exception' : metricsData.cpu_usage > 0.6 ? 'warning' : 'normal'}
                />
                <div style={{ marginTop: '8px', textAlign: 'right' }}>
                  {Math.round(metricsData.cpu_usage * 100)}%
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="内存使用率">
                <Progress 
                  percent={metricsData.memory_usage * 100} 
                  status={metricsData.memory_usage > 0.8 ? 'exception' : metricsData.memory_usage > 0.6 ? 'warning' : 'normal'}
                />
                <div style={{ marginTop: '8px', textAlign: 'right' }}>
                  {Math.round(metricsData.memory_usage * 100)}%
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="磁盘使用率">
                <Progress 
                  percent={metricsData.disk_usage * 100} 
                  status={metricsData.disk_usage > 0.8 ? 'exception' : metricsData.disk_usage > 0.6 ? 'warning' : 'normal'}
                />
                <div style={{ marginTop: '8px', textAlign: 'right' }}>
                  {Math.round(metricsData.disk_usage * 100)}%
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" title="API响应时间">
                <Statistic 
                  value={metricsData.api_response_time * 1000} 
                  precision={2} 
                  suffix="ms"
                  valueStyle={{ color: metricsData.api_response_time > 0.5 ? '#ff4d4f' : metricsData.api_response_time > 0.2 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6} style={{ marginTop: '16px' }}>
              <Card size="small" title="错误率">
                <Statistic 
                  value={metricsData.error_rate * 100} 
                  precision={2} 
                  suffix="%"
                  valueStyle={{ color: metricsData.error_rate > 0.05 ? '#ff4d4f' : metricsData.error_rate > 0.01 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
          </Row>
        )}
      </Card>

      {/* 系统通知 */}
      <Card title="系统通知" style={{ marginBottom: '24px' }}>
        <Table 
          dataSource={[
            { key: '1', time: '2024-01-01 10:00:00', message: '系统启动', level: 'info' },
            { key: '2', time: '2024-01-01 10:30:00', message: '风控服务初始化完成', level: 'info' },
            { key: '3', time: '2024-01-01 11:00:00', message: 'API服务启动成功', level: 'info' },
            { key: '4', time: '2024-01-01 11:30:00', message: '数据库连接正常', level: 'info' },
          ]}
          columns={[
            { title: '时间', dataIndex: 'time', key: 'time' },
            { title: '消息', dataIndex: 'message', key: 'message' },
            { 
              title: '级别', 
              dataIndex: 'level', 
              key: 'level',
              render: (level) => (
                <Tag color={level === 'info' ? 'blue' : level === 'warning' ? 'orange' : 'red'}>
                  {level === 'info' ? '信息' : level === 'warning' ? '警告' : '错误'}
                </Tag>
              )
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default SystemHealth;
