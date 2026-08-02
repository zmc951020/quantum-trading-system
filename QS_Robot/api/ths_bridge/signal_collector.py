"""同花顺策略信号收集器

遍历 14 策略 + 18 高阶战法，收集买入信号，统一推入股票池。
这是同花顺策略进入"选股→股票池→测试→实盘"自动化流程的入口。
"""
import importlib.util
import logging
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Type

from core.strategies.ths_strategies.base import THSBaseStrategy
from core.stock_pool import StockPoolManager, StockSource, PoolLevel, get_stock_pool_manager

logger = logging.getLogger(__name__)

BASE_14 = Path(__file__).parents[2] / "core" / "strategies" / "ths_strategies" / "14_strategies"
BASE_18 = Path(__file__).parents[2] / "core" / "strategies" / "ths_strategies" / "18_advanced"

STRATEGY_MAP_14 = {
    "01_macd_wave.py": "MACDWaveStrategy",
    "02_weekly_breakout.py": "WeeklyBreakoutStrategy",
    "03_dragon_head.py": "DragonHeadStrategy",
    "04_dragon_list_follow.py": "DragonListFollowStrategy",
    "05_ma_long_arrangement.py": "MALongArrangementStrategy",
    "06_expma_double_cross.py": "EXPMADoubleCrossStrategy",
    "07_macd_zero_second_cross.py": "MACDZeroSecondCrossStrategy",
    "08_dmi_adx_strong_trend.py": "DMIADXStrategy",
    "09_boll_upper_breakout.py": "BollUpperBreakoutStrategy",
    "10_five_day_low_suck.py": "FiveDayLowSuckStrategy",
    "11_ten_day_wave.py": "TenDayWaveStrategy",
    "12_twenty_day_lifeline.py": "TwentyDayLifelineStrategy",
    "13_sixty_day_bull_bear.py": "SixtyDayBullBearStrategy",
    "14_four_ma_resonance.py": "FourMAResonanceStrategy",
}

STRATEGY_MAP_18 = {
    "01_dynamic_pool_backtest.py": "DynamicPoolBacktestStrategy",
    "02_volume_price_resonance.py": "VolumePriceResonanceStrategy",
    "03_quant_trend_follow.py": "QuantTrendFollowStrategy",
    "04_iwencai_natural_select.py": "IwencaiNaturalSelectStrategy",
    "05_chip_distribution.py": "ChipDistributionStrategy",
    "06_dragon_tiger_quant_seat.py": "DragonTigerQuantSeatStrategy",
    "07_north_capital_follow.py": "NorthCapitalFollowStrategy",
    "08_volume_ladder.py": "VolumeLadderStrategy",
    "09_market_emotion.py": "MarketEmotionStrategy",
    "10_sector_rotation.py": "SectorRotationStrategy",
    "11_kline_pattern_recognition.py": "KlinePatternRecognitionStrategy",
    "12_alert_state_machine.py": "AlertStateMachineStrategy",
    "13_minute_kline_short.py": "MinuteKlineShortStrategy",
    "14_order_flow_analysis.py": "OrderFlowAnalysisStrategy",
    "15_pyramid_position.py": "PyramidPositionStrategy",
    "16_three_line_cross.py": "ThreeLineCrossStrategy",
    "17_grid_trading.py": "GridTradingStrategy",
    "18_smart_money_tracking.py": "SmartMoneyTrackingStrategy",
}


def _load_class(file_path: Path, class_name: str) -> Type[THSBaseStrategy]:
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


class SignalCollector:
    """同花顺策略信号收集器"""

    def __init__(self, pool_manager: StockPoolManager = None):
        self._pool = pool_manager or get_stock_pool_manager()
        self._strategies_14: List[THSBaseStrategy] = []
        self._strategies_18: List[THSBaseStrategy] = []
        self._load_all_strategies()

    def _load_all_strategies(self):
        for fname, cname in STRATEGY_MAP_14.items():
            try:
                cls = _load_class(BASE_14 / fname, cname)
                self._strategies_14.append(cls())
            except Exception as e:
                logger.error("加载14策略 %s 失败: %s", fname, e)
        for fname, cname in STRATEGY_MAP_18.items():
            try:
                cls = _load_class(BASE_18 / fname, cname)
                self._strategies_18.append(cls())
            except Exception as e:
                logger.error("加载18战法 %s 失败: %s", fname, e)
        logger.info("已加载 %d 策略 + %d 战法", len(self._strategies_14), len(self._strategies_18))

    def scan(self, bars_map: Dict[str, List[dict]],
             params_map: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        """扫描所有股票，收集买入信号

        Args:
            bars_map: {symbol: bars_list}
            params_map: {symbol: {param: value}} 可选

        Returns:
            信号列表 [{symbol, strategy_name, signal, ...}]
        """
        signals = []
        all_strategies = self._strategies_14 + self._strategies_18
        for symbol, bars in bars_map.items():
            for strat in all_strategies:
                params = (params_map or {}).get(symbol, {}).get(strat.NAME, {})
                try:
                    sig = strat.generate_signal(bars, params)
                    if sig and sig.get("action") == "buy":
                        signals.append({
                            "symbol": symbol,
                            "strategy_name": strat.NAME,
                            "risk_level": strat.RISK_LEVEL,
                            "signal": sig,
                        })
                except Exception as e:
                    logger.debug("策略 %s 对 %s 异常: %s", strat.NAME, symbol, e)
        logger.info("扫描完成: %d 只股票 × %d 策略 → %d 信号",
                    len(bars_map), len(all_strategies), len(signals))
        return signals

    def collect_to_pool(self, bars_map: Dict[str, List[dict]],
                        stock_names: Optional[Dict[str, str]] = None,
                        params_map: Optional[Dict[str, Dict]] = None) -> Dict:
        """扫描信号并推入股票池（来源标记为 ths_iwencai）

        Returns:
            推入结果统计
        """
        signals = self.scan(bars_map, params_map)
        added, skipped = 0, 0
        for sig in signals:
            symbol = sig["symbol"]
            name = (stock_names or {}).get(symbol, symbol)
            result = self._pool.add_stock(
                symbol=symbol,
                name=name,
                level=PoolLevel.WATCHLIST,
                source=StockSource.THS_IWENCAI,
                strategy_name=sig["strategy_name"],
                metadata={"signal": sig["signal"], "risk_level": sig["risk_level"]},
            )
            if result.get("success"):
                added += 1
            else:
                skipped += 1
        return {"total_signals": len(signals), "added": added, "skipped": skipped}

    def list_strategies(self) -> Tuple[List[str], List[str]]:
        """列出已加载的策略名"""
        return [s.NAME for s in self._strategies_14], [s.NAME for s in self._strategies_18]
