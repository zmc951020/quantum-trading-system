# AURORA 系统健康自动化诊断引擎 — 设计文档

**日期**: 2026-06-16  
**状态**: 已确认  
**方案**: 方案A — 一体化巡检模块

## 1. 目标

将 7 层系统审核经验固化为自动化工程能力，支持：
- 手动一键巡检（快速/深度两档）
- 定时自动巡检守护
- 异常告警联动（页面 + 日志 + 桌面通知）
- 历史报告存档与追溯

## 2. 架构

```
QS_Robot/
├── core/
│   └── system_health_checker.py   ← 新增：巡检引擎
├── api/
│   └── gateway.py                 ← 修改：+3 条路由
├── ui/
│   ├── templates/
│   │   └── maintenance.html       ← 修改：新增「系统巡检」Tab
│   └── static/
│       └── js/
│           └── health_check.js    ← 新增：巡检前端交互
└── data/
    └── health_reports/            ← 新增：巡检报告存档目录
```

## 3. 核心数据结构

### 3.1 CheckItem

```python
@dataclass
class CheckItem:
    id: str              # 唯一标识，如 "L1_001"
    name: str            # 中文名称
    layer: str           # 所属层级
    severity: str        # critical / warning / info
    mode: str            # "quick" / "deep" / "both"
    check_fn: Callable   # 检查函数，返回 CheckResult
    timeout: float       # 超时秒数
```

### 3.2 CheckResult

```python
@dataclass
class CheckResult:
    passed: bool
    score: float         # 0-100
    detail: str
    suggestion: str      # 修复建议（失败时）
    elapsed_ms: float
```

### 3.3 HealthReport

```python
@dataclass
class HealthReport:
    report_id: str
    timestamp: datetime
    mode: str            # quick / deep
    overall_score: float
    overall_status: str  # healthy / warning / critical
    layers: Dict[str, LayerResult]
    alerts: List[Alert]
    elapsed_seconds: float
```

## 4. 7 层检查清单

### 快速模式（28 项，~30 秒）

| 层级 | 检查项 | 严重度 |
|------|--------|--------|
| L1 安全认证 | 未认证API拦截、Session有效性、密钥无硬编码、暴力破解防护 | critical×4 |
| L2 业务链路 | 策略列表、优化器列表、回测端点、策略启停 | critical×3, warning×1 |
| L3 系统可靠性 | 健康检查、降级状态、并发请求 | critical×3 |
| L4 数据行情 | 技术指标计算、市场数据源、股票池接口 | warning×3 |
| L5 交易风控 | 风控引擎、资金安全、交易验证 | critical×3 |
| L6 AI智能体 | LLM管理器、Vibe分析、智能体对话 | warning×3 |
| L7 运维部署 | 前端页面、启动脚本、配置文件、审计日志 | critical×1, warning×3 |

### 深度模式（额外扩展，累计 60+ 项，~2 分钟）

- L1：+ 权限边界 / 密码修改 / 用户禁用启用 / IP白名单CRUD
- L2：+ 策略注册表 / 优化器执行 / 牧羊人代理 / 风控评分计算
- L3：+ 30并发压力测试 / 参数同步 / 5002存活探测
- L4：+ 15个技术指标逐一验证 / 多数据源fallback / K线完整性
- L5：+ 黑名单机制 / 紧急冻结 / 止损止盈 / 券商全流程
- L6：+ LLM模型切换 / 29智能体投票 / 全市场扫描 / Cline页面
- L7：+ 所有页面可达 / 404/401处理 / 告警系统 / 参数同步

## 5. 前端页面设计

在 maintenance.html 新增第 5 个 Tab：「系统巡检」

- 顶部操作栏：快速巡检 / 深度巡检 按钮 + 定时巡检开关 + 健康评分大盘
- 中部概览卡：7 张层级卡片横向排列（绿/黄/红状态）
- 底部详情区：可折叠的每层检查项明细，失败项红色高亮 + 修复建议

## 6. 告警联动

- critical 项失败 → 立即告警
- warning 项失败 → 累计 3 项以上告警
- 报告存档到 data/health_reports/，保留最近 30 天
- 告警写入 /api/alerts 体系 + 桌面 QS_Robot 通知

## 7. API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/health/check` | POST | 触发巡检，`{mode: "quick"|"deep"}` |
| `/api/health/report/<id>` | GET | 获取历史报告 |
| `/api/health/scheduler` | POST | 定时巡检开关，`{action: "start"|"stop", interval: 30}` |

## 8. 文件清单

| 操作 | 文件 |
|------|------|
| 新增 | `core/system_health_checker.py` |
| 修改 | `api/gateway.py`（+3 路由） |
| 修改 | `ui/templates/maintenance.html`（新增 Tab） |
| 新增 | `ui/static/js/health_check.js` |
| 新增 | `data/health_reports/`（目录） |