"""L5 交易风控检查"""
import os
import sys
import re
from typing import List, Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l5_checks(hc) -> List[Callable]:
    def _l5_001():
        """风控引擎（合并L2_006+L5_001，检查规则激活状态）"""
        ok, d = hc._api_get("/api/risk/status")
        rules = d.get("data", {}).get("rules", [])
        active = sum(1 for r in rules if r.get("active"))
        return (ok, 100 if active > 0 else 85,
                f"风控引擎: {'在线' if ok else '离线'}, {active}条规则激活",
                "" if active > 0 else "风控在线但无规则激活（交易前需配置）")
    yield ("L5_001", "风控引擎", "L5_交易风控", "critical", "both", _l5_001)

    def _l5_002():
        ok, d = hc._api_get("/api/fund/config")
        return (ok, 100 if ok else 0, f"资金安全: {'通过' if ok else '失败'}", "")
    yield ("L5_002", "资金安全模块", "L5_交易风控", "critical", "both", _l5_002)

    def _l5_003():
        ok, d = hc._api_post("/api/trade/validate",
            {"symbol": "000001", "amount": 100000, "quantity": 1000, "price": 10.5,
             "strategy": "gyro_v7"})
        return (ok, 100 if ok else 0, f"交易验证: {'通过' if ok else '失败'}", "")
    yield ("L5_003", "交易验证端点", "L5_交易风控", "critical", "both", _l5_003)

    # 深度扩展
    def _l5_004():
        ok, d = hc._api_get("/api/risk/stop-loss")
        return (ok, 100 if ok else 0, f"止损止盈: {'通过' if ok else '失败'}", "")
    yield ("L5_004", "止损止盈配置", "L5_交易风控", "critical", "deep", _l5_004)

    def _l5_005():
        ok, d = hc._api_get("/api/broker/list")
        return (ok, 100 if ok else 0, f"券商列表: {'通过' if ok else '失败'}", "")
    yield ("L5_005", "券商接口", "L5_交易风控", "warning", "deep", _l5_005)

    def _l5_006():
        ok, d = hc._api_get("/api/trade/report")
        return (ok, 100 if ok else 0, f"交易报告: {'通过' if ok else '失败'}", "")
    yield ("L5_006", "交易报告", "L5_交易风控", "warning", "deep", _l5_006)

    # 新模块：交易执行器
    def _l5_007():
        try:
            from core.trade_executor import TradeExecutor, get_trade_executor
            te = get_trade_executor()
            stats = te.get_stats()
            signals = stats.get("total_signals", 0)
            orders = stats.get("total_orders", 0)
            filled = stats.get("total_filled", 0)
            breaker = "熔断中" if te._circuit_breaker else "正常"
            return (True, 100 if signals > 0 else 85,
                    f"交易执行器: {breaker}, 信号{signals}→订单{orders}→成交{filled}",
                    "待券商密钥激活" if signals == 0 else "")
        except Exception as e:
            return (False, 0, f"交易执行器: 不可用 - {e}", "检查 core/trade_executor.py")
    yield ("L5_007", "交易执行器", "L5_交易风控", "critical", "both", _l5_007)

    # 新模块：订单管理器
    def _l5_008():
        try:
            from core.order_manager import OrderManager, get_order_manager
            om = get_order_manager()
            stats = om.get_stats()
            total = stats.get("total", 0)
            fill_rate = stats.get("fill_rate", 0)
            db_size = "N/A"
            try:
                db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'orders.db')
                if os.path.exists(db_path):
                    db_size = f"{os.path.getsize(db_path)/1024:.1f}KB"
            except Exception:
                pass
            return (True, 100,
                    f"订单管理器: {total}个订单, 成交率{fill_rate:.1%}, DB={db_size}",
                    "")
        except Exception as e:
            return (False, 0, f"订单管理器: 不可用 - {e}", "检查 core/order_manager.py")
    yield ("L5_008", "订单管理器", "L5_交易风控", "critical", "both", _l5_008)

    def _l5_009():
        """回测手续费检查：回测引擎是否计算佣金"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        if not os.path.exists(fpath):
            return (True, 80, "回测引擎文件检查跳过", "")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            ok = 'commission' in content.lower() or '手续费' in content
            return (ok, 100 if ok else 0,
                    f"回测手续费: {'已计算' if ok else '未检测到'}",
                    "" if ok else "添加佣金计算(万2.5最低5元)")
        except Exception as e:
            return (False, 0, f"检查异常: {e}", "")
    yield ("L5_009", "回测手续费", "L5_交易风控", "critical", "both", _l5_009)

    def _l5_010():
        """回测印花税检查：卖出是否计算印花税"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        if not os.path.exists(fpath):
            return (True, 80, "回测引擎文件检查跳过", "")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            ok = 'stamp' in content.lower() or '印花' in content
            return (ok, 100 if ok else 0,
                    f"回测印花税: {'已计算' if ok else '未检测到'}",
                    "" if ok else "添加印花税计算(卖出千1)")
        except Exception as e:
            return (False, 0, f"检查异常: {e}", "")
    yield ("L5_010", "回测印花税", "L5_交易风控", "critical", "both", _l5_010)

    def _l5_011():
        """回测滑点检查：是否模拟滑点成本"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        if not os.path.exists(fpath):
            return (True, 80, "回测引擎文件检查跳过", "")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            ok = 'slippage' in content.lower() or '滑点' in content
            return (ok, 100 if ok else 50,
                    f"回测滑点: {'已模拟' if ok else '未检测到'}",
                    "" if ok else "添加滑点模拟(建议0.1%)")
        except Exception as e:
            return (False, 0, f"检查异常: {e}", "")
    yield ("L5_011", "回测滑点模拟", "L5_交易风控", "warning", "both", _l5_011)

    def _l5_012():
        """夏普比率检查：回测结果是否包含夏普比率"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        if not os.path.exists(fpath):
            return (True, 80, "回测引擎文件检查跳过", "")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            ok = 'sharpe' in content.lower()
            return (ok, 100 if ok else 0,
                    f"夏普比率: {'已包含' if ok else '未检测到'}",
                    "" if ok else "回测结果必须包含夏普比率")
        except Exception as e:
            return (False, 0, f"检查异常: {e}", "")
    yield ("L5_012", "夏普比率", "L5_交易风控", "critical", "both", _l5_012)

    def _l5_013():
        """前视偏差检测：检查策略代码中是否存在未来函数"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        if not os.path.exists(fpath):
            return (True, 80, "回测引擎文件检查跳过", "")
        lookahead_patterns = ['shift(-1)', 'iloc[i+1]', 'iloc[i-1]', 'lookahead', '未来函数']
        issues = []
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            for pat in lookahead_patterns:
                if pat in content:
                    issues.append(pat)
            ok = len(issues) == 0
            return (ok, 100 if ok else 0,
                    f"前视偏差: {'未发现' if ok else '发现 ' + ', '.join(issues)}",
                    "" if ok else "移除未来函数，使用滞后数据")
        except Exception as e:
            return (False, 0, f"检查异常: {e}", "")
    yield ("L5_013", "前视偏差检测", "L5_交易风控", "critical", "both", _l5_013)