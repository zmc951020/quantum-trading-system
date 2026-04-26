import React from 'react';
import { Layout, Menu, ConfigProvider } from 'antd';
import { 
  DashboardOutlined, 
  SafetyCertificateOutlined, 
  LineChartOutlined, 
  PieChartOutlined, 
  SettingOutlined 
} from '@ant-design/icons';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RiskMonitoring from './pages/RiskMonitoring';
import PerformanceAttribution from './pages/PerformanceAttribution';
import PortfolioMonitoring from './pages/PortfolioMonitoring';
import SystemHealth from './pages/SystemHealth';

const { Header, Sider, Content } = Layout;

function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#1890ff',
        },
      }}
    >
      <Router>
        <Layout style={{ minHeight: '100vh' }}>
          <Sider width={200} style={{ background: '#001529' }}>
            <div style={{ color: 'white', fontSize: '18px', padding: '16px', textAlign: 'center', fontWeight: 'bold' }}>
              量化交易系统
            </div>
            <Menu
              mode="inline"
              theme="dark"
              defaultSelectedKeys={['dashboard']}
              items={[
                {
                  key: 'dashboard',
                  icon: <DashboardOutlined />,
                  label: <Link to="/">仪表盘</Link>,
                },
                {
                  key: 'risk',
                  icon: <SafetyCertificateOutlined />,
                  label: <Link to="/risk">风控监控</Link>,
                },
                {
                  key: 'performance',
                  icon: <LineChartOutlined />,
                  label: <Link to="/performance">绩效归因</Link>,
                },
                {
                  key: 'portfolio',
                  icon: <PieChartOutlined />,
                  label: <Link to="/portfolio">投资组合</Link>,
                },
                {
                  key: 'health',
                  icon: <SettingOutlined />,
                  label: <Link to="/health">系统健康</Link>,
                },
              ]}
            />
          </Sider>
          <Layout>
            <Header style={{ background: 'white', padding: 0, boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)' }}>
              <div style={{ padding: '0 24px', lineHeight: '64px', fontSize: '16px', fontWeight: 'bold' }}>
                量化交易仪表盘
              </div>
            </Header>
            <Content style={{ margin: '24px', padding: '24px', background: 'white', minHeight: 280, borderRadius: '8px', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.09)' }}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/risk" element={<RiskMonitoring />} />
                <Route path="/performance" element={<PerformanceAttribution />} />
                <Route path="/portfolio" element={<PortfolioMonitoring />} />
                <Route path="/health" element={<SystemHealth />} />
              </Routes>
            </Content>
          </Layout>
        </Layout>
      </Router>
    </ConfigProvider>
  );
}

export default App;
