# Aurora量化交易系统全面检查计划

> **面向 AI 代理的工作者：** 使用 superpowers:subagent-driven-development 或 superpowers:dispatching-parallel-agents 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 对Aurora量化交易系统进行功能全面检查，重点验证前端UI界面标签模块操作是否正常实现

**架构：** QS_Robot外壳(5003端口) + Aurora内核(5002端口)，通过API网关代理桥接。10个HTML模板页面，7个API文件，10个核心API路由组

**技术栈：** Flask + Jinja2 + Bootstrap 5 + Python 3 + Windows Service

**检查范围：** 前端UI(10页面) → API网关(7文件) → Aurora内核(5002) → 全局功能验证

---

## 智能体分工

### Agent 1: 前端UI页面完整性检查 (chinese-code-review)
**文件：** 10个HTML模板文件
**检查项：** 导航栏、Tab切换、表单交互、API调用、CSS样式、JS逻辑

### Agent 2: API网关与路由检查 (systematic-debugging)
**文件：** server.py + api/目录下7个文件
**检查项：** 路由注册、代理转发、响应格式、错误处理、认证机制

### Agent 3: Aurora内核集成检查 (verification-before-completion)
**目标：** 5002端口Aurora服务
**检查项：** 策略列表、回测引擎、风控模块、经纪商适配、健康状态

### Agent 4: 全局功能验证 (systematic-debugging)
**目标：** 端到端功能测试
**检查项：** 页面可访问性、API响应正确性、数据流完整性、错误降级

---

## 检查清单

### 一、前端UI页面 (10个页面)

- [ ] **login.html** - 登录页面
  - [ ] 表单字段(用户名/密码)
  - [ ] 登录按钮交互
  - [ ] API: `/api/auth/login` 调用
  - [ ] 错误提示显示
  - [ ] 成功跳转到 `/dashboard`

- [ ] **dashboard.html** - 控制台首页
  - [ ] 导航栏9个链接
  - [ ] Aurora原系统状态面板
  - [ ] 快捷分析输入框
  - [ ] 4个统计卡片
  - [ ] 自动化流程图
  - [ ] 7个核心功能模块卡片
  - [ ] 策略对比分析
  - [ ] 港大29智能体分析面板
  - [ ] 机器人浮标

- [ ] **aurora_main.html** - Aurora主系统Hub
  - [ ] 导航栏
  - [ ] 4个核心模块入口卡片
  - [ ] 策略标签库表格(4策略)
  - [ ] 优化器标签库(6优化器)
  - [ ] 机器人浮标

- [ ] **main_system.html** - 核心平台(9个Tab)
  - [ ] Tab1: 仪表盘(系统总览+收益+日志)
  - [ ] Tab2: 策略管理(8策略列表+筛选+操作按钮)
  - [ ] Tab3: 回测中心(参数配置+6指标+交易记录)
  - [ ] Tab4: 韬定律优化器(参数搜索+结果+模式分析)
  - [ ] Tab5: 技术分析(6指标+综合评分+信号)
  - [ ] Tab6: 股票池(4层轨道+流转规则+详情表)
  - [ ] Tab7: 系统监控(资源+Aurora引擎+5大增益模块)
  - [ ] Tab8: 五层防钓鱼风控(评分+参数+报告+日志)
  - [ ] Tab9: Cline智能体(聊天+快捷回复+模拟对话)

- [ ] **stock_pool.html** - 股票池独立页
  - [ ] 导航栏
  - [ ] 股票池状态面板
  - [ ] 筛选/搜索功能
  - [ ] 系统切换功能

- [ ] **technical_analysis.html** - 技术分析页
  - [ ] 导航栏
  - [ ] 选股+周期配置
  - [ ] 多指标状态条
  - [ ] 综合评分
  - [ ] 强强联合流程

- [ ] **vibe_analysis.html** - Vibe智能体页
  - [ ] 导航栏
  - [ ] 29智能体投票矩阵
  - [ ] 全市场扫描
  - [ ] 投票结果展示

- [ ] **cline_agent.html** - Cline智能体页
  - [ ] 导航栏
  - [ ] 聊天界面
  - [ ] 模型切换
  - [ ] 快捷回复

- [ ] **model_switch.html** - 模型切换页
  - [ ] 导航栏
  - [ ] 模型列表
  - [ ] 切换按钮
  - [ ] 配置保存

- [ ] **index.html** - 智能助手侧边栏
  - [ ] 聊天Tab
  - [ ] 韬定律优化器Tab

### 二、API网关层 (7个文件)

- [ ] **server.py** - Flask主服务
  - [ ] 所有路由注册
  - [ ] Aurora代理转发
  - [ ] 认证中间件
  - [ ] 端口配置

- [ ] **api/gateway.py** - API网关
  - [ ] 统一鉴权
  - [ ] 请求路由分发
  - [ ] 缓存机制

- [ ] **api/aurora_adapter.py** - Aurora适配器
  - [ ] 字段映射
  - [ ] 响应格式转换
  - [ ] 错误处理

- [ ] **api/response_formatter.py** - 响应格式化
  - [ ] 统一格式
  - [ ] 状态码映射

- [ ] **api/routes/strategy_routes.py** - 策略路由
  - [ ] 策略列表
  - [ ] 策略详情

- [ ] **api/routes/backtest_routes.py** - 回测路由
  - [ ] 回测执行
  - [ ] 回测结果

- [ ] **api/routes/risk_routes.py** - 风控路由
  - [ ] 风控状态
  - [ ] 风控配置

- [ ] **api/routes/broker_routes.py** - 经纪商路由
  - [ ] 订单列表
  - [ ] 持仓列表

### 三、Aurora内核 (5002端口)

- [ ] 策略管理模块
- [ ] 回测引擎
- [ ] 风控模块
- [ ] 经纪商适配器
- [ ] 系统健康检查
- [ ] 38个策略数据

### 四、全局功能

- [ ] 所有页面可访问性
- [ ] 导航栏一致性
- [ ] 机器人浮标一致性
- [ ] API响应格式统一
- [ ] 错误处理降级
- [ ] 认证流程完整性
- [ ] 跨页面数据流