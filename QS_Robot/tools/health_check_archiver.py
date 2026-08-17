#!/usr/bin/env python3
"""
QS_Robot 一键巡检 - 架构与提示词存档
=====================================
系统维护深度巡检的9层架构定义、执行入口和标准提示词模板。
存档时间: 2026-08-17
巡检结果: 147项/130通过/88%通过率/85.2分

使用方式:
  1. 终端执行: python tools/health_check_archiver.py
  2. AI提示词: 参考本文件末尾的 PROMPT_TEMPLATE 字段
  3. API调用:  POST /api/health/check  body={"mode":"deep"}
"""

from dataclasses import dataclass, field
from typing import List, Dict
import json, time

# ============================================================
# 9层巡检架构定义
# ============================================================

ARCHITECTURE = {
    "L1": {
        "name": "安全与认证",
        "checks": [
            "JWT令牌管理", "RBAC权限控制", "密码策略", "反钓鱼防御",
            "认证中间件", "审计追踪", "密钥管理", "安全扫描(SAST)",
            "SQL注入检测", "XSS防护", "CSRF防护", "API限流",
            "配置安全", "依赖漏洞", "沙箱隔离", "文件上传安全",
            "会话管理", "日志脱敏", "数据加密", "网络隔离",
            "容器安全", "供应链安全", "端口安全",
        ],
        "weight": "critical",
        "description": "金融级安全标准，覆盖认证、授权、审计、加密全链路",
    },
    "L2": {
        "name": "业务功能链路",
        "checks": [
            "策略入口-同花顺", "策略入口-韬策略集群", "策略入口-Vibe智能体",
            "工程流-选股到候选池", "工程流-候选池到测试迭代",
            "工程流-测试到预实盘", "工程流-预实盘到实盘",
            "工程流-实盘到交易", "工程流-8阶段工作流引擎",
            "优化器-总数统计", "优化器-策略关联可视化",
            "优化器-API端点", "优化器-闭环链路",
            "Vibe-29智能体注册", "Vibe-分析推荐链路",
            "Vibe-推荐到交易", "Aurora策略-4个", "可视化页面完整性",
            "API端点可用性",
        ],
        "weight": "critical",
        "description": "三大策略入口的完整业务链路验证",
    },
    "L3": {
        "name": "系统可靠性",
        "checks": [
            "Flask服务可用性", "数据库连接", "缓存(Redis)", "消息队列",
            "日志系统", "错误处理", "超时控制", "重试机制",
        ],
        "weight": "critical",
        "description": "基础设施可用性与容错能力",
    },
    "L4": {
        "name": "数据与行情",
        "checks": [
            "AKShare数据源", "数据路由", "K线数据获取", "实时行情",
            "历史数据完整性", "数据缓存", "数据格式兼容",
        ],
        "weight": "high",
        "description": "数据源可用性与数据链路完整性",
    },
    "L5": {
        "name": "交易与风控",
        "checks": [
            "订单管理器", "交易执行器", "风控引擎", "止损止盈",
            "仓位管理", "滑点保护", "熔断机制", "告警去重",
            "持仓校验", "资金计算精度", "交易日志审计",
            "模拟盘/实盘分离", "60秒告警冷却",
        ],
        "weight": "critical",
        "description": "交易执行安全与风控规则完整性",
    },
    "L6": {
        "name": "AI与智能体",
        "checks": [
            "LLM可用性", "Ollama连接", "Vibe-Trading引擎", "29智能体投票",
            "回测引擎", "Alpha因子引擎",
        ],
        "weight": "high",
        "description": "AI模型与智能体可用性",
    },
    "L7": {
        "name": "运维与部署",
        "checks": [
            "端口5003一致性", "健康检查端点", "日志轮转", "磁盘空间",
            "内存使用", "CPU使用", "进程状态", "服务重启恢复",
            "pre-commit钩子",
        ],
        "weight": "high",
        "description": "系统运维与部署健康度",
    },
    "L8": {
        "name": "深度审计（代码/API/引擎/配置）",
        "checks": [
            "代码质量(Sonar)", "API端点全量测试", "Vibe模块注册表",
            "Vibe模块文件", "Vibe API端点", "Vibe模块导入",
            "配置完整性", "依赖版本", "引擎初始化", "回测回归",
            "工程循环审计(19项)", "策略入口审计(22项)",
            "安全审计(SAST)", "SQL注入审计", "前视偏差检测",
            "代码复杂度", "覆盖率", "Lint检查",
            "模块边界合规", "循环依赖检测", "可视化面板完整性",
            "数据源桥接", "导航链路", "全模块端到端信号",
            "数据链路", "工程流闭环", "降级模块监控",
        ],
        "weight": "warning",
        "description": "代码质量、API完整性和工程闭环深度审计",
    },
    "L9": {
        "name": "工程闭环审查（工程流+策略入口+代码质量+导航+可视化+数据源+模块边界）",
        "checks": [
            "Vibe模块注册表完整性(78模块)", "Vibe模块文件存在性",
            "Vibe API端点可用性", "Vibe关键模块导入稳定性",
            "Vibe可视化面板可操作性", "Vibe全模块端到端信号测试",
            "Vibe数据链路验证", "Vibe工程流闭环验证",
            "Vibe降级模块状态监控", "工程循环审计(19项)",
            "策略入口审计(22项)", "代码质量检查",
            "导航链路验证", "可视化面板完整性",
            "数据源接入验证", "模块边界合规",
            "Aurora策略完整性", "集群选股器集成",
            "工作流引擎", "策略入口审计器",
            "8阶段工作流", "10阶段工作流",
            "优化器关联", "Vibe智能体关联",
            "前端页面路由", "API路由完整性",
            "降级模块率<50%", "信号生成覆盖率",
            "数据源注册", "数据路由导入",
            "K线数据获取", "策略模块数>=15",
        ],
        "weight": "warning",
        "description": "Vibe-Trading全模块集成与工程闭环最终审查",
    },
}

# ============================================================
# 本次深度巡检结果 (2026-08-17)
# ============================================================

LAST_RESULT = {
    "timestamp": "2026-08-17 12:58:42",
    "mode": "deep",
    "overall_score": 85.2,
    "overall_status": "critical",
    "total_checks": 147,
    "passed_checks": 130,
    "failed_checks": 17,
    "elapsed_seconds": 660.4,
    "pass_rate": "88%",
    "layer_breakdown": {
        "L1_安全与认证": "15/23 (65%)",
        "L2_业务功能链路": "19/19 (100%)",
        "L3_系统可靠性": "8/8 (100%)",
        "L4_数据与行情": "7/7 (100%)",
        "L5_交易与风控": "12/13 (92%)",
        "L6_AI与智能体": "5/6 (83%)",
        "L7_运维与部署": "7/9 (78%)",
        "L8_深度审计": "28/30 (93%)",
        "L9_工程闭环": "29/32 (91%)",
    },
    "critical_issues": [
        "auth/jwt_manager.py 缺失",
        "auth/rbac.py 缺失",
        "auth/password_manager.py 缺失",
        "auth/phishing_defense.py 缺失",
        "auth/middleware.py 缺失",
        "security/audit_trail.py 缺失",
        "SQL拼接风险: core/database.py, core/session_memory.py",
        "前视偏差(lookahead): 策略代码中存在未来数据引用",
        "Vibe-Trading回测引擎初始化失败: ChinaAEngine config缺失",
        "AKShare网络连接不稳定(热点股/板块轮动/情绪获取失败)",
        "Aurora连接丢失(切换到模拟降级模式)",
    ],
    "warnings": [
        "security/secrets_manager.py 缺失",
        "Vibe-Trading 32个模块以降级模式运行",
        "LLM不可用降级机制需验证",
        "pre-commit钩子状态需确认",
    ],
}

# ============================================================
# 标准提示词模板
# ============================================================

PROMPT_TEMPLATE = """
## QS_Robot 一键巡检提示词

### 执行指令
对 QS_Robot 系统执行深度巡检，覆盖9层架构，输出完整巡检报告。

### 巡检架构（9层）
| 层级 | 名称 | 权重 | 检查项数 | 说明 |
|------|------|------|----------|------|
| L1 | 安全与认证 | critical | 23 | 金融级安全标准 |
| L2 | 业务功能链路 | critical | 19 | 三大策略入口链路 |
| L3 | 系统可靠性 | critical | 8 | 基础设施可用性 |
| L4 | 数据与行情 | high | 7 | 数据源完整性 |
| L5 | 交易与风控 | critical | 13 | 交易执行安全 |
| L6 | AI与智能体 | high | 6 | AI模型可用性 |
| L7 | 运维与部署 | high | 9 | 系统运维健康度 |
| L8 | 深度审计 | warning | 30 | 代码/API/引擎审计 |
| L9 | 工程闭环审查 | warning | 32 | Vibe全模块集成 |

### 执行方式
1. **API方式**: `POST /api/health/check` body=`{"mode":"deep"}`
2. **直接运行**: `python -c "from core.system_health_checker import SystemHealthChecker; r=SystemHealthChecker().run_check('deep'); print(f'评分:{r.overall_score} 状态:{r.overall_status}')"`
3. **快速模式**: `mode="quick"` 跳过AKShare网络请求

### 预期输出
- 总体评分(0-100)和状态(healthy/warning/critical)
- 9层各层通过率
- 失败项详情
- 严重/警告告警列表
- 总耗时

### 重点检查项（本次发现）
- [ ] auth/ 安全模块缺失(jwt/rbac/password/phishing/middleware/audit)
- [ ] SQL注入风险(core/database.py, core/session_memory.py)
- [ ] 前视偏差检测
- [ ] Vibe-Trading 78模块端到端信号
- [ ] 降级模块率 < 50%
- [ ] 工程流闭环(选股→入池→交易)
- [ ] 数据链路(数据源→K线→信号)
- [ ] 可视化面板可操作性
- [ ] Aurora连接状态
- [ ] AKShare网络连通性
"""

# ============================================================
# 执行入口
# ============================================================

def print_architecture():
    """打印9层架构"""
    print("=" * 70)
    print("QS_Robot 一键巡检 - 9层架构")
    print("=" * 70)
    for layer_id in sorted(ARCHITECTURE.keys()):
        layer = ARCHITECTURE[layer_id]
        print(f"\n{layer_id}: {layer['name']} [{layer['weight']}]")
        print(f"  描述: {layer['description']}")
        print(f"  检查项: {len(layer['checks'])}")
        for i, check in enumerate(layer['checks'][:5], 1):
            print(f"    {i}. {check}")
        if len(layer['checks']) > 5:
            print(f"    ... 共{len(layer['checks'])}项")
    print(f"\n总计: {sum(len(l['checks']) for l in ARCHITECTURE.values())} 检查项")

def print_last_result():
    """打印最近一次巡检结果"""
    print("\n" + "=" * 70)
    print("最近巡检结果 (2026-08-17)")
    print("=" * 70)
    print(f"状态: {LAST_RESULT['overall_status']}")
    print(f"评分: {LAST_RESULT['overall_score']}")
    print(f"通过率: {LAST_RESULT['pass_rate']}")
    print(f"耗时: {LAST_RESULT['elapsed_seconds']}s")
    print(f"\n层级明细:")
    for layer, result in LAST_RESULT['layer_breakdown'].items():
        print(f"  {layer}: {result}")
    print(f"\n严重问题 ({len(LAST_RESULT['critical_issues'])}):")
    for issue in LAST_RESULT['critical_issues']:
        print(f"  - {issue}")
    print(f"\n警告 ({len(LAST_RESULT['warnings'])}):")
    for w in LAST_RESULT['warnings']:
        print(f"  - {w}")

def print_prompt_template():
    """打印标准提示词模板"""
    print("\n" + "=" * 70)
    print("AI提示词模板 (可直接复制使用)")
    print("=" * 70)
    print(PROMPT_TEMPLATE)

def run_health_check(mode="quick"):
    """执行一键巡检"""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core.system_health_checker import SystemHealthChecker
        checker = SystemHealthChecker()
        print(f"正在执行{mode}模式巡检...")
        t0 = time.time()
        result = checker.run_check(mode=mode)
        elapsed = time.time() - t0

        print(f"\n状态: {result.overall_status}")
        print(f"评分: {result.overall_score}")
        print(f"检查项: {result.total_checks} | 通过: {result.passed_checks} | 失败: {result.failed_checks}")
        print(f"耗时: {elapsed:.1f}s")

        for layer in result.layers:
            name = layer.get("name", "?")
            total = layer.get("total", 0)
            passed = layer.get("passed", 0)
            print(f"  {name}: {passed}/{total}")

        if result.alerts:
            print(f"\n告警 ({len(result.alerts)}):")
            for a in result.alerts[:5]:
                print(f"  [{a.get('level','?')}] {a.get('message','')}")

        return result
    except ImportError:
        print("错误: 无法导入 SystemHealthChecker，请确保在项目目录下运行")
        return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode in ("quick", "deep"):
            run_health_check(mode)
        elif mode == "--prompt":
            print_prompt_template()
        elif mode == "--result":
            print_last_result()
        elif mode == "--all":
            print_architecture()
            print_last_result()
            print_prompt_template()
        else:
            print(f"用法: python {sys.argv[0]} [quick|deep|--prompt|--result|--all]")
    else:
        print_architecture()
        print_last_result()
        print("\n使用 'python tools/health_check_archiver.py deep' 执行深度巡检")
        print("使用 'python tools/health_check_archiver.py --prompt' 查看AI提示词")