"""C1-C4 全量回归测试"""
import sys, importlib, traceback

tests = {
    "C1-Bus核心": "from core.integration_bus import get_integration_bus, StrategyIntegrationBus, IntegrationBus",
    "C1-Bus单例": "from core.integration_bus import get_integration_bus; bus = get_integration_bus()",
    "C1-Bus重导出": "from core.integration_bus import get_risk_control_engine, get_data_fetcher, get_stock_pool_manager",
    "C2-工程流审计": "from core.engineering_loop_auditor import EngineeringLoopAuditor",
    "C2-策略审计": "from core.strategy_entry_auditor import StrategyEntryAuditor",
    "C3-Vibe智能体": "from core.vibe_29_agents import VibeAgentAnalyzer, analyze_with_real_data",
    "C3-Alpha因子": "from core.vibe_alpha_factors import AlphaFactorEngine",
    "C4-风控引擎": "from core.risk_control import RiskControlEngine",
    "C4-Agent调度": "from core.agent_dispatcher import AgentDispatcher",
    "C4-基础设施": "from core.infrastructure import AnomalyDetector",
    "核心-Workflow": "from core.workflow_engine import get_workflow_engine",
    "核心-股票池": "from core.stock_pool import get_stock_pool_manager",
    "核心-回测": "from core.backtest_engine import SimpleBacktestEngine",
    "核心-数据": "from core.data_fetcher import get_data_fetcher",
    "核心-Vibe": "from core.vibe_integration import VibeIntegration",
    "核心-集成": "from core.integration_bus import get_integration_bus",
}

passed = 0
failed = 0
for name, code in tests.items():
    try:
        exec(code)
        print(f"  PASS: {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {name} -> {e}")
        failed += 1

print(f"\n结果: {passed}/{passed+failed} 通过 ({passed*100//(passed+failed)}%)")
sys.exit(0 if failed == 0 else 1)