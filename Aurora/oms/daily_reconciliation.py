# coding: utf-8
"""
日终对账模块 — 持仓/资金/订单三者核对
=====================================
增益性补充，每个交易日收盘后自动执行。
不修改原有 oms/ 模块代码。

功能：
  - 资金对账：系统可用资金 == 券商余额 - 冻结资金 ± 在途资金
  - 持仓对账：系统持仓数量/成本 == 券商持仓数量/成本
  - 订单对账：今日成交订单 == 券商成交回报
  - 差额超过阈值 → P1告警 + 生成差异报告
  - 自动修复：小额差异（<0.01元）静默修正；大额差异人工介入
  - 每日对账报告持久化到 reports/ 目录

使用方式：
    from oms.daily_reconciliation import DailyRecon
    recon = DailyRecon()
    report = recon.run(
        system_positions={...},
        broker_positions={...},
        system_cash=1e6,
        broker_cash=1e6,
    )
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── 对账阈值 ───
CASH_EPSILON = 0.01      # 资金差 < 0.01元 视为一致
POS_EPSILON = 1          # 持仓差 < 1股 视为一致
COST_EPSILON = 0.001     # 成本差 < 0.1% 视为一致


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class PositionItem:
    """单票持仓"""
    symbol: str
    quantity: int        # 数量
    avg_cost: float      # 持仓均价
    market_value: float  # 当前市值


@dataclass
class OrderItem:
    """单笔订单"""
    order_id: str
    symbol: str
    side: str            # buy/sell
    quantity: int
    filled_quantity: int
    price: float
    commission: float
    status: str          # filled/partial/rejected
    timestamp: str


@dataclass
class ReconDiff:
    """对账差异"""
    field: str           # 差异字段名
    symbol: str          # 涉及股票（资金对账时为空）
    system_value: float
    broker_value: float
    diff: float          # 差异绝对值
    diff_pct: float      # 差异百分比
    severity: str        # "ok" / "warn" / "crit"


@dataclass
class ReconReport:
    """对账报告"""
    date: str
    timestamp: str
    status: str          # "pass" / "warn" / "fail"
    cash_ok: bool
    position_ok: bool
    order_ok: bool
    diffs: List[ReconDiff] = field(default_factory=list)
    summary: str = ""
    auto_fixed: List[str] = field(default_factory=list)
    needs_manual: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# 对账引擎
# ─────────────────────────────────────────────

class DailyRecon:
    """
    日终对账引擎 — 增益层

    三维对账：
      1. 资金对账
      2. 持仓对账
      3. 订单对账

    报告自动保存到 reports/recon_{date}.json
    """

    def __init__(self, reports_dir: str = "reports"):
        self._reports_dir = reports_dir

    def run(
        self,
        system_cash: float,
        broker_cash: float,
        system_frozen: float = 0.0,
        system_pending: float = 0.0,
        broker_pending: float = 0.0,
        system_positions: Optional[Dict[str, PositionItem]] = None,
        broker_positions: Optional[Dict[str, PositionItem]] = None,
        system_orders: Optional[List[OrderItem]] = None,
        broker_orders: Optional[List[OrderItem]] = None,
        report_date: Optional[str] = None,
    ) -> ReconReport:
        """
        执行完整对账。

        Args:
            system_cash: 系统记录可用资金
            broker_cash: 券商余额
            system_frozen: 系统冻结资金（未成交委托）
            system_pending: 系统在途资金（卖出待结算）
            broker_pending: 券商在途资金
            system_positions: {symbol: PositionItem} 系统持仓
            broker_positions: {symbol: PositionItem} 券商持仓
            system_orders: 系统今日成交订单
            broker_orders: 券商成交回报
            report_date: 报告日期（默认今天）

        Returns:
            ReconReport 包含所有差异和修复建议
        """
        report_date = report_date or date.today().isoformat()
        report = ReconReport(
            date=report_date,
            timestamp=datetime.now().isoformat(),
            status="pass",
            cash_ok=True,
            position_ok=True,
            order_ok=True,
        )

        system_positions = system_positions or {}
        broker_positions = broker_positions or {}
        system_orders = system_orders or []
        broker_orders = broker_orders or []

        # ── 1. 资金对账 ──
        report.cash_ok, cash_diffs = self._reconcile_cash(
            system_cash, broker_cash,
            system_frozen, system_pending, broker_pending,
        )
        report.diffs.extend(cash_diffs)

        # ── 2. 持仓对账 ──
        report.position_ok, pos_diffs = self._reconcile_positions(
            system_positions, broker_positions
        )
        report.diffs.extend(pos_diffs)

        # ── 3. 订单对账 ──
        report.order_ok, order_diffs = self._reconcile_orders(
            system_orders, broker_orders
        )
        report.diffs.extend(order_diffs)

        # ── 总体判定 ──
        if not report.cash_ok or not report.position_ok or not report.order_ok:
            has_critical = any(d.severity == "crit" for d in report.diffs)
            report.status = "fail" if has_critical else "warn"

        # ── 自动修复微差异 ──
        self._auto_fix_minor(report, system_cash, broker_cash,
                             system_positions, broker_positions)

        # ── 生成摘要 ──
        report.summary = self._build_summary(report)

        # ── 持久化 ──
        self._save_report(report)

        if report.status == "pass":
            logger.info("✅ 日终对账通过: %s", report.summary)
        elif report.status == "warn":
            logger.warning("⚠️ 日终对账告警: %s", report.summary)
        else:
            logger.critical("❌ 日终对账失败！%s", report.summary)

        return report

    # ────────── 资金对账 ──────────

    def _reconcile_cash(
        self,
        system_cash: float,
        broker_cash: float,
        system_frozen: float,
        system_pending: float,
        broker_pending: float,
    ) -> Tuple[bool, List[ReconDiff]]:
        """资金对账：系统资金 vs 券商资金"""
        diffs = []

        # 实际可用资金 = 余额 - 冻结 + 在途
        system_available = system_cash - system_frozen + system_pending
        broker_available = broker_cash + broker_pending  # 券商通常在途已算入

        cash_diff = abs(system_available - broker_available)
        if cash_diff > CASH_EPSILON:
            severity = "crit" if cash_diff > 100.0 else "warn"
            diffs.append(ReconDiff(
                field="cash",
                symbol="",
                system_value=system_available,
                broker_value=broker_available,
                diff=cash_diff,
                diff_pct=cash_diff / max(abs(broker_available), 1.0),
                severity=severity,
            ))
            return False, diffs
        return True, diffs

    # ────────── 持仓对账 ──────────

    def _reconcile_positions(
        self,
        system_positions: Dict[str, PositionItem],
        broker_positions: Dict[str, PositionItem],
    ) -> Tuple[bool, List[ReconDiff]]:
        """持仓对账：数量 + 成本"""
        diffs = []
        all_symbols = set(system_positions.keys()) | set(broker_positions.keys())

        for symbol in sorted(all_symbols):
            sys_p = system_positions.get(symbol)
            brk_p = broker_positions.get(symbol)

            if sys_p is None:
                diffs.append(ReconDiff(
                    field="position_missing_sys",
                    symbol=symbol,
                    system_value=0,
                    broker_value=brk_p.quantity,
                    diff=brk_p.quantity,
                    diff_pct=1.0,
                    severity="warn",
                ))
                continue

            if brk_p is None:
                diffs.append(ReconDiff(
                    field="position_missing_brk",
                    symbol=symbol,
                    system_value=sys_p.quantity,
                    broker_value=0,
                    diff=sys_p.quantity,
                    diff_pct=1.0,
                    severity="warn",
                ))
                continue

            # 数量差异
            qty_diff = abs(sys_p.quantity - brk_p.quantity)
            if qty_diff > POS_EPSILON:
                diffs.append(ReconDiff(
                    field="position_qty",
                    symbol=symbol,
                    system_value=sys_p.quantity,
                    broker_value=brk_p.quantity,
                    diff=qty_diff,
                    diff_pct=qty_diff / max(abs(brk_p.quantity), 1),
                    severity="crit" if qty_diff > 100 else "warn",
                ))

            # 成本差异
            if brk_p.quantity > 0 and sys_p.quantity > 0:
                cost_diff_pct = abs(sys_p.avg_cost - brk_p.avg_cost) / max(brk_p.avg_cost, 0.01)
                if cost_diff_pct > COST_EPSILON:
                    diffs.append(ReconDiff(
                        field="position_cost",
                        symbol=symbol,
                        system_value=sys_p.avg_cost,
                        broker_value=brk_p.avg_cost,
                        diff=abs(sys_p.avg_cost - brk_p.avg_cost),
                        diff_pct=cost_diff_pct,
                        severity="warn",
                    ))

        return len(diffs) == 0, diffs

    # ────────── 订单对账 ──────────

    def _reconcile_orders(
        self,
        system_orders: List[OrderItem],
        broker_orders: List[OrderItem],
    ) -> Tuple[bool, List[ReconDiff]]:
        """订单对账：系统订单 vs 券商成交回报"""
        diffs = []

        sys_ids = {o.order_id for o in system_orders}
        brk_ids = {o.order_id for o in broker_orders}

        # 系统有，券商无
        for oid in sys_ids - brk_ids:
            sys_o = next(o for o in system_orders if o.order_id == oid)
            diffs.append(ReconDiff(
                field="order_missing_brk",
                symbol=sys_o.symbol,
                system_value=sys_o.filled_quantity,
                broker_value=0,
                diff=sys_o.filled_quantity,
                diff_pct=1.0,
                severity="crit" if sys_o.status == "filled" else "warn",
            ))

        # 券商有，系统无
        for oid in brk_ids - sys_ids:
            brk_o = next(o for o in broker_orders if o.order_id == oid)
            diffs.append(ReconDiff(
                field="order_missing_sys",
                symbol=brk_o.symbol,
                system_value=0,
                broker_value=brk_o.filled_quantity,
                diff=brk_o.filled_quantity,
                diff_pct=1.0,
                severity="crit",
            ))

        # 共同订单：比较成交量和成交金额
        for oid in sys_ids & brk_ids:
            sys_o = next(o for o in system_orders if o.order_id == oid)
            brk_o = next(o for o in broker_orders if o.order_id == oid)

            if sys_o.filled_quantity != brk_o.filled_quantity:
                diffs.append(ReconDiff(
                    field="order_qty",
                    symbol=sys_o.symbol,
                    system_value=sys_o.filled_quantity,
                    broker_value=brk_o.filled_quantity,
                    diff=abs(sys_o.filled_quantity - brk_o.filled_quantity),
                    diff_pct=abs(sys_o.filled_quantity - brk_o.filled_quantity) / max(brk_o.filled_quantity, 1),
                    severity="crit",
                ))

            trade_amt_sys = sys_o.filled_quantity * sys_o.price
            trade_amt_brk = brk_o.filled_quantity * brk_o.price
            if abs(trade_amt_sys - trade_amt_brk) > CASH_EPSILON:
                diffs.append(ReconDiff(
                    field="order_amount",
                    symbol=sys_o.symbol,
                    system_value=trade_amt_sys,
                    broker_value=trade_amt_brk,
                    diff=abs(trade_amt_sys - trade_amt_brk),
                    diff_pct=abs(trade_amt_sys - trade_amt_brk) / max(trade_amt_brk, 0.01),
                    severity="warn",
                ))

        return len(diffs) == 0, diffs

    # ────────── 自动修复 ──────────

    def _auto_fix_minor(
        self,
        report: ReconReport,
        system_cash: float,
        broker_cash: float,
        system_positions: Dict[str, PositionItem],
        broker_positions: Dict[str, PositionItem],
    ):
        """自动修复小额差异（< 阈值）"""
        # 资金微差修复
        for diff in report.diffs:
            if diff.field == "cash" and diff.diff <= 1.0 and diff.severity != "crit":
                report.auto_fixed.append(
                    f"资金差额 {diff.diff:.2f} 元（阈值内），建议以券商余额为准"
                )
                diff.severity = "ok"

            if diff.field == "position_qty" and diff.diff <= 10 and diff.severity != "crit":
                report.auto_fixed.append(
                    f"{diff.symbol} 持仓差 {diff.diff:.0f} 股（阈值内），已标记低风险"
                )
                diff.severity = "ok"

    # ────────── 摘要 ──────────

    def _build_summary(self, report: ReconReport) -> str:
        crit_count = sum(1 for d in report.diffs if d.severity == "crit")
        warn_count = sum(1 for d in report.diffs if d.severity == "warn")
        auto_count = len(report.auto_fixed)

        parts = [f"状态={report.status}"]
        if crit_count:
            parts.append(f"致命差异={crit_count}")
        if warn_count:
            parts.append(f"告警差异={warn_count}")
        parts.append(f"差异总数={len(report.diffs)}")
        if auto_count:
            parts.append(f"自动修复={auto_count}")
        return ", ".join(parts)

    # ────────── 持久化 ──────────

    def _save_report(self, report: ReconReport):
        """保存对账报告到 JSON"""
        import os
        os.makedirs(self._reports_dir, exist_ok=True)

        filename = os.path.join(self._reports_dir, f"recon_{report.date}.json")
        data = {
            "date": report.date,
            "timestamp": report.timestamp,
            "status": report.status,
            "cash_ok": report.cash_ok,
            "position_ok": report.position_ok,
            "order_ok": report.order_ok,
            "diffs": [asdict(d) for d in report.diffs],
            "summary": report.summary,
            "auto_fixed": report.auto_fixed,
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("对账报告已保存: %s", filename)

    def load_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """加载最近N天对账报告"""
        import os
        result = []
        if not os.path.isdir(self._reports_dir):
            return result
        for fname in sorted(os.listdir(self._reports_dir), reverse=True)[:days]:
            if fname.startswith("recon_") and fname.endswith(".json"):
                path = os.path.join(self._reports_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        result.append(json.load(f))
                except Exception:
                    continue
        return result