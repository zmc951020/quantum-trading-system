# Aurora 系统健康诊断工作流

## 触发条件
- 诊断、检查、故障、健康检查、health check、系统监控

## 核心能力
10大维度系统诊断 + 增强监控能力。

## 工作流程

### 第一步：环境检查
1. Python版本验证：3.9+
2. 依赖包检查：requirements.txt
3. 磁盘空间检查
4. 内存和CPU状态

### 第二步：数据库检查
1. SQLite连接测试
2. WAL模式验证
3. 数据库完整性：PRAGMA integrity_check
4. 连接池状态：ConnectionPool 5连接

### 第三步：模块加载检查
- deepseek_client.py
- qwen_client.py
- data_aggregator.py
- broker_interface.py
- trade_security.py（696行）
- risk_manager.py
- strategy_monitor.py

### 第四步：API端点检查
- GET /api/health
- GET /api/strategies
- GET /api/backtest/history
- POST /api/trade

### 第五步：数据源检查
4源冗余验证：Yahoo Finance、东方财富、Tushare、AKShare

### 第六步：安全检查
- 白名单状态
- API密钥有效性
- 防火墙规则

### 第七步：维护任务
- 日志轮转检查
- 数据库VACUUM
- 缓存清理
- 备份验证

### 第八步：系统监控增强（skill03增强）
- Prometheus指标收集
- Grafana仪表板状态
- GPU使用率监控
- 推理延迟监控

## 关键文件
- system_health.py
- test_complete_health_check.py
- test_health_check.py
- monitor/

## 诊断输出
生成详细诊断报告到 diagnosis_report.md
包含enhanced_evaluator.py的评分体系。