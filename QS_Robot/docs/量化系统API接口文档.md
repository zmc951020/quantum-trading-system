
# Aurora量化系统API接口文档

## 系统信息

| 项目 | 信息 |
|------|------|
| 系统名称 | Aurora量化交易系统 |
| 主入口 | main.py |
| 生产启动 | production_start.py |
| Web界面 | visualization.py (Flask后端) |
| 系统路径 | d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora |

---

## 核心模块

### 1. 策略模块
| 文件 | 功能 |
|------|------|
| strategies/ | 策略目录 |
| shepherd_v5_comprehensive.py | Shepherd V5优化器 |
| shepherd_v6_comprehensive.py | Shepherd V6优化器（五行门系统） |
| strategy_api.py | 策略API接口 |
| strategy_monitor.py | 策略监控 |

### 2. 优化器模块
| 文件 | 功能 |
|------|------|
| optimizer_enhanced.py | 增强优化器 |
| shepherd_five_line_optimizer.py | 五行策略优化器 |

### 3. 回测模块
| 文件 | 功能 |
|------|------|
| auto_backtest/ | 自动回测系统 |
| backtests/ | 回测目录 |

### 4. 风控模块
| 文件 | 功能 |
|------|------|
| risk_enhanced.py | 增强风控 |
| security_enhancer.py | 安全增强 |

### 5. 监控模块
| 文件 | 功能 |
|------|------|
| monitor/system_health.py | 系统健康检查 |
| monitoring/ | 监控目录 |

---

## Web API端点 (基于visualization.py)

### 基础路径
`http://localhost:5000/` (默认端口5000)

### 主要端点
- `/login` - 登录界面
- `/api/deepseek/chat` - DeepSeek聊天接口
- 更多端点待探索...

---

## 系统启动方式
```python
# 方式1 - 主入口
python main.py start

# 方式2 - 生产启动
python production_start.py

# 方式3 - 实时交易
python real_time_trading.py
```

---

## 待完善内容

此文档将在探索过程中持续更新完善。
