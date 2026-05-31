#!/usr/bin/env python3
"""
Aurora量化交易系统 — 券商切换与技术分析演示

完整演示流程：
  1. 初始化 BrokerManager，注册多个券商
  2. 动态切换券商（XBK ↔ 中泰 ↔ 模拟）
  3. 股票池管理（候选/精选/黑名单）
  4. 技术分析桥接扫描全流程
  5. 信号→交易执行通路
  6. 健康检查与状态报告

运行方式：
    python demo_broker_switch.py
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo")

# ── 导入核心模块 ──────────────────────────────────────
from broker_interface import BrokerType, ConnectionState, OrderSide, OrderType
from broker_manager import (
    BrokerManager,
    StockPool,
    AnalysisBridge,
    AnalysisSignal,
    StockInfo,
)


def print_header(title: str):
    """打印标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_subtitle(title: str):
    """打印副标题"""
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


def demo_broker_registration(manager: BrokerManager):
    """演示：券商注册"""
    print_header("步骤1：券商注册")

    # 导入适配器
    from adapters.xbk_adapter import XbkAdapter
    from adapters.zhongtai_adapter import ZhongTaiAdapter

    print("  注册西部宽客(XBK)适配器...")
    manager.register("xbk", XbkAdapter(
        simulated=True,
        initial_balance=2_000_000,
    ))

    print("  注册中泰证券适配器...")
    manager.register("zhongtai", ZhongTaiAdapter(
        account_id="ZT_DEFAULT",
        simulated=True,
        initial_balance=1_000_000,
    ))

    print("  注册模拟券商...")
    manager.register("sim", XbkAdapter(
        simulated=True,
        initial_balance=500_000,
    ))

    print(f"\n  已注册券商: {list(manager.brokers.keys())}")
    print(f"  当前活跃: {manager.active_key}")

    # 显示各券商信息
    print_subtitle("券商详情")
    for key, broker in manager.brokers.items():
        info = broker.get_broker_info()
        print(f"  [{key}] {info['name']}")
        print(f"      - 类型: {info['broker_type']}")
        print(f"      - 支持市场: {', '.join(info['market'])}")
        print(f"      - 交易时间: {info.get('trading_hours', 'N/A')}")
        print(f"      - 佣金: {info.get('commission_rate', 0)*100:.2f}%")
        print(f"      - 模拟模式: {info.get('simulated', True)}")


def demo_switch_broker(manager: BrokerManager):
    """演示：券商切换"""
    print_header("步骤2：券商动态切换")

    print("\n  [切换] XBK → 中泰证券...")
    result = manager.switch_to("zhongtai")
    if result.success:
        print(f"  切换成功 → 当前券商: {manager.active_key}")
        info = manager.active_broker.get_broker_info()
        print(f"  券商名称: {info['name']}")

    print("\n  [切换] 中泰 → XBK...")
    result = manager.switch_to("xbk")
    if result.success:
        print(f"  切换成功 → 当前券商: {manager.active_key}")

    print("\n  [测试] 尝试切换到未注册券商...")
    result = manager.switch_to("huatai")
    print(f"  预期失败: {result.message}")

    # 添加切换监听器
    def on_switch(from_key, to_key, old_broker, new_broker):
        print(f"\n  [监听器] 券商切换: {from_key} → {to_key}")

    manager.add_switch_listener(on_switch)
    print("\n  [切换] 已添加切换监听器，演示切换 XBK → 中泰...")
    manager.switch_to("zhongtai")


def demo_stock_pool(manager: BrokerManager):
    """演示：股票池管理"""
    print_header("步骤3：股票池管理")

    pool = StockPool(manager)

    # 添加候选股票
    symbols = [
        "600519.SH", "000858.SZ", "300750.SZ",
        "002415.SZ", "600036.SH", "603259.SH",
        "601318.SH", "000333.SZ",
    ]
    n = pool.add_candidates(symbols)
    print(f"\n  添加候选股票 {n} 只")
    print(f"  候选池: {[s.symbol for s in pool.candidates]}")

    # 给候选股票添加板块信息
    sector_map = {
        "600519.SH": "白酒", "000858.SZ": "白酒",
        "300750.SZ": "新能源", "002415.SZ": "安防",
        "600036.SH": "银行", "603259.SH": "医药",
        "601318.SH": "保险", "000333.SZ": "家电",
    }
    for sym, sector in sector_map.items():
        s = pool.find(sym)
        if s:
            s.sector = sector
            s.name = {
                "600519.SH": "贵州茅台", "000858.SZ": "五粮液",
                "300750.SZ": "宁德时代", "002415.SZ": "海康威视",
                "600036.SH": "招商银行", "603259.SH": "药明康德",
                "601318.SH": "中国平安", "000333.SZ": "美的集团",
            }.get(sym, "")

    # 提升精选池
    promoted = pool.batch_promote(["600519.SH", "300750.SZ", "601318.SH"])
    print(f"\n  提升到精选池: {promoted} 只")
    print(f"  精选池: {[s.symbol for s in pool.selected]}")

    # 添加黑名单
    pool.blacklist_add(["000002.SZ"])
    print(f"\n  黑名单: {pool.blacklist}")

    # 统计
    stats = pool.stats()
    print_subtitle("股票池统计")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    return pool


def demo_analysis_bridge(manager: BrokerManager, pool: StockPool):
    """演示：技术分析桥接"""
    print_header("步骤4：技术分析扫描与评分")

    bridge = AnalysisBridge(manager, pool, max_workers=4)

    print("\n  开始扫描精选池...")
    signals = bridge.scan_and_rank(pool="selected", top_n=5, min_score=30)

    if signals:
        print_subtitle(f"技术评分排名 (Top {len(signals)})")
        for i, sig in enumerate(signals, 1):
            print(f"\n  #{i} {sig.symbol} {sig.name}")
            print(f"      评分: {sig.score:.1f}  趋势: {sig.trend}")
            print(f"      均线: {sig.ma_arrangement}   MACD: {sig.macd_signal}")
            print(f"      RSI: {sig.rsi_value:.1f}  成交量: {sig.volume_signal}")
            print(f"      支撑: {sig.support_level:.2f}  阻力: {sig.resistance_level:.2f}")
    else:
        print("  未产生符合条件的信号")

    # 扫描候选池
    print("\n  开始扫描候选池...")
    signals = bridge.scan_and_rank(pool="candidates", top_n=10)
    print(f"  候选池产生 {len(signals)} 个信号")

    # 获取看涨信号
    bullish = bridge.get_bullish_signals()
    print(f"  其中看涨信号: {len(bullish)} 个")
    for s in bullish:
        print(f"    ✓ {s.symbol} ({s.name}) - 评分 {s.score:.1f}")

    return bridge


def demo_trade_execution(manager: BrokerManager, bridge: AnalysisBridge):
    """演示：交易信号执行"""
    print_header("步骤5：信号执行与交易")

    # 获取账户信息
    result = manager.get_account()
    if result.success:
        acc = result.data
        print("\n  当前账户:")
        print(f"    总资产: {acc.total_asset:,.2f}")
        print(f"    可用资金: {acc.available_cash:,.2f}")
        print(f"    持仓市值: {acc.market_value:,.2f}")

    # 获取Top信号
    signals = bridge.get_top_picks(5)
    if not signals:
        print("\n  无可用信号，跳过交易演示")
        return

    # 尝试执行买入
    buy_signal = next((s for s in signals if s.trend == "bullish" and s.score >= 60), None)
    if buy_signal:
        print(f"\n  [买入信号] {buy_signal.symbol} ({buy_signal.name})")
        print(f"    评分: {buy_signal.score:.1f}  趋势: {buy_signal.trend}")

        # 先获取行情
        ticker = manager.get_ticker(buy_signal.symbol)
        if ticker.success:
            print(f"    当前价格: {ticker.data.last_price:.2f}")

        # 执行交易（演示，不实际下单）
        # result = bridge.execute_signal(buy_signal, position_pct=0.1)
        # print(f"  交易结果: {result.message if not result.success else '成功'}")
        print("    [模拟] 已跳过实际下单，仅在演示中展示流程")
    else:
        print("\n  暂无符合条件的买入信号")


def demo_health_check(manager: BrokerManager):
    """演示：健康检查"""
    print_header("步骤6：券商健康检查")

    health = manager.check_all_health()
    for key, status in health.items():
        status_icon = "✓" if status["healthy"] else "✗"
        print(f"  [{key}] {status_icon} {status}")

    # 当前活跃券商详情
    if manager.active_broker:
        print(f"\n  当前活跃券商: {manager.active_key}")
        hc = manager.active_broker.health_check()
        if hc.success:
            print(f"    连接状态: {hc.data.get('connected', False)}")
            print(f"    延迟: {hc.data.get('latency_ms', 'N/A')}ms")
            print(f"    服务器时间: {hc.data.get('server_time', 'N/A')}")


def demo_real_api_switching(manager: BrokerManager):
    """演示：真实API接入点说明"""
    print_header("真实API接入指南")

    print(textwrap.dedent("""
    当前所有券商均为模拟模式。

    接入真实券商API步骤：

    【西部宽客(XBK)】
      1. 在 config/broker_config.yaml 中填写 api_key/api_secret/api_url
      2. 设置 simulated: false
      3. 实现 xbk_adapter.py 中的 _real_* 方法
      4. 运行: manager.switch_to("xbk")

    【中泰证券】
      1. 在 config/broker_config.yaml 中填写 app_key/app_secret
      2. 设置 simulated: false
      3. 实现 adapters/zhongtai_adapter.py 中的 _real_* 方法
      4. 运行: manager.switch_to("zhongtai")

    【添加新券商】
      1. 创建 adapters/xxx_adapter.py
      2. 实现 BrokerInterface
      3. manager.register("xxx", XxxAdapter(...))
      4. manager.switch_to("xxx")

    所有适配器通过统一的 BrokerInterface 与上层交互，
    技术分析、股票池、交易模块无需任何修改。
    """))


def demo_full_workflow():
    """
    完整演示流程
    """

    print_header("Aurora量化交易系统 — 券商切换与技术分析无缝链接演示")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  系统: Aurora v2.0 (多券商支持)")

    # 1. 初始化
    manager = BrokerManager()

    # 2. 注册券商
    demo_broker_registration(manager)

    # 3. 券商切换
    demo_switch_broker(manager)

    # 切回XBK
    manager.switch_to("xbk")

    # 4. 股票池
    pool = demo_stock_pool(manager)

    # 5. 技术分析
    bridge = demo_analysis_bridge(manager, pool)

    # 6. 交易执行
    demo_trade_execution(manager, bridge)

    # 7. 健康检查
    demo_health_check(manager)

    # 8. API接入指南
    demo_real_api_switching(manager)

    print_header("演示完成")
    print("""
  核心文件清单:
    broker_interface.py       — 券商接口抽象层（所有适配器的契约）
    xbk_adapter.py            — 西部宽客(XBK)适配器
    adapters/zhongtai_adapter.py — 中泰证券适配器
    broker_manager.py         — 券商管理器 + 股票池 + 技术分析桥接
    config/broker_config.yaml — 券商配置文件
    demo_broker_switch.py     — 本演示脚本

  下一步：
    1. 修改 config/broker_config.yaml 配置真实API凭证
    2. 实现对应适配器的 _real_* 方法
    3. 在生产环境中运行: manager.switch_to("xbk")
    """)


if __name__ == "__main__":
    try:
        demo_full_workflow()
    except Exception as e:
        logger.exception(f"演示异常: {e}")
        raise