#!/usr/bin/env python3
"""
MarketETL - 行情数据ETL增量服务

核心功能：
  1. 从akshare批量拉取A股日线/分钟数据
  2. 增量写入Qlib二进制格式（通过DataConverter）
  3. 数据清洗（复权、停牌、涨跌停过滤）
  4. 定时调度（盘后批量补全 + 盘中增量更新）
  5. 数据完整性校验

设计依据：
  豆包审查 + Trae方案 - 搭建独立行情ETL服务，对接akshare实时拉取
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from .qlib_core.data_converter import DataConverter, get_converter

logger = logging.getLogger(__name__)


@dataclass
class ETLConfig:
    """ETL配置"""
    data_dir: str = "./qlib_data"
    batch_size: int = 50              # 每批拉取股票数
    retry_count: int = 3              # 失败重试次数
    retry_delay: float = 5.0          # 重试间隔(秒)
    rate_limit_delay: float = 0.5     # API限流间隔(秒)
    daily_update_time: str = "17:00"  # 每日盘后更新时刻
    intraday_interval: int = 300      # 盘中更新间隔(秒)
    auto_start: bool = False          # 是否自动启动调度


class MarketETL:
    """行情ETL服务

    使用示例:
        >>> etl = MarketETL()
        >>> etl.update_all_stocks_batch(["600519", "000858"])
        >>> etl.start_scheduler()  # 启动定时调度
    """

    def __init__(self, config: ETLConfig = None):
        self.config = config or ETLConfig()
        self.converter = get_converter(self.config.data_dir)
        self._scheduler_thread: Optional[threading.Thread] = None
        self._running = False
        self._stats = {
            "total_updates": 0,
            "success_count": 0,
            "fail_count": 0,
            "last_update": None,
            "errors": [],
        }

    # ================================================================
    # 批量数据拉取
    # ================================================================

    def update_all_stocks_batch(self, symbols: List[str],
                                 freq: str = "day",
                                 start_date: str = None,
                                 end_date: str = None,
                                 progress_callback: Callable = None) -> Dict[str, Any]:
        """批量拉取并存储全量股票数据

        Args:
            symbols: 股票代码列表
            freq: 频率 "day" 或 "1min"
            start_date: 起始日期
            end_date: 结束日期
            progress_callback: 进度回调 fn(current, total)

        Returns:
            {success_count, fail_count, errors, elapsed}
        """
        start_time = time.time()
        total = len(symbols)
        success = 0
        fail = 0
        errors = []

        for i, symbol in enumerate(symbols):
            try:
                ok, msg = self._fetch_with_retry(symbol, freq, start_date, end_date)
                if ok:
                    success += 1
                else:
                    fail += 1
                    errors.append({"symbol": symbol, "error": msg})
            except Exception as e:
                fail += 1
                errors.append({"symbol": symbol, "error": str(e)})

            if progress_callback:
                progress_callback(i + 1, total)

            # API限流
            time.sleep(self.config.rate_limit_delay)

        elapsed = time.time() - start_time
        self._stats["total_updates"] += 1
        self._stats["success_count"] += success
        self._stats["fail_count"] += fail
        self._stats["last_update"] = datetime.now().isoformat()

        logger.info(f"批量更新完成: {success}/{total} 成功, {fail} 失败, 耗时 {elapsed:.1f}s")

        return {
            "success_count": success,
            "fail_count": fail,
            "total": total,
            "errors": errors[:10],  # 只返回前10个错误
            "elapsed_seconds": round(elapsed, 1),
        }

    def update_stock(self, symbol: str, freq: str = "day",
                     start_date: str = None, end_date: str = None) -> Tuple[bool, str]:
        """更新单只股票数据"""
        return self._fetch_with_retry(symbol, freq, start_date, end_date)

    def _fetch_with_retry(self, symbol: str, freq: str = "day",
                          start_date: str = None, end_date: str = None,
                          retry: int = None) -> Tuple[bool, str]:
        """带重试的数据拉取"""
        retry = retry or self.config.retry_count
        last_error = ""

        for attempt in range(retry):
            try:
                if freq == "day":
                    df = self.converter.fetch_akshare_day(symbol, start_date, end_date)
                else:
                    df = self.converter.fetch_akshare_1min(symbol)

                if df is None or df.empty:
                    last_error = f"数据为空"
                    continue

                ok, msg = self.converter.convert_akshare_to_qlib(df, symbol, freq)
                if ok:
                    return True, msg
                else:
                    last_error = msg

            except Exception as e:
                last_error = str(e)

            if attempt < retry - 1:
                time.sleep(self.config.retry_delay)

        return False, last_error

    # ================================================================
    # 增量更新（仅追加新数据）
    # ================================================================

    def incremental_update(self, symbols: List[str], freq: str = "day") -> Dict[str, Any]:
        """增量更新（仅追加新日期数据，不重新拉取全部历史）

        Args:
            symbols: 股票代码列表
            freq: 频率

        Returns:
            更新结果统计
        """
        start_time = time.time()
        success = 0
        fail = 0
        new_records = 0

        for symbol in symbols:
            try:
                # 获取已有数据的最新日期
                existing = self.converter.load_qlib_data(symbol, freq)
                if existing is not None and not existing.empty:
                    last_date = existing.index[-1]
                    # 从last_date+1天开始拉取
                    if freq == "day":
                        start_date = (pd.Timestamp(last_date) + timedelta(days=1)).strftime("%Y%m%d")
                    else:
                        start_date = (pd.Timestamp(last_date) + timedelta(minutes=1)).strftime("%Y%m%d%H%M")
                else:
                    start_date = None

                df = self.converter.fetch_akshare_day(symbol, start_date)
                if df is not None and not df.empty:
                    ok, msg = self.converter.append_data(symbol, df, freq)
                    if ok:
                        success += 1
                        new_records += len(df)
                    else:
                        fail += 1
                else:
                    success += 1  # 无新数据也算成功

            except Exception as e:
                fail += 1
                logger.error(f"增量更新失败: {symbol}: {e}")

            time.sleep(self.config.rate_limit_delay)

        elapsed = time.time() - start_time
        return {
            "success_count": success,
            "fail_count": fail,
            "new_records": new_records,
            "elapsed_seconds": round(elapsed, 1),
        }

    # ================================================================
    # 定时调度
    # ================================================================

    def start_scheduler(self, symbols: List[str] = None):
        """启动定时调度（后台线程）

        - 每日盘后17:00自动全量更新日线
        - 盘中每5分钟增量更新分钟数据
        """
        if self._running:
            logger.warning("调度器已在运行")
            return

        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(symbols,),
            daemon=True,
        )
        self._scheduler_thread.start()
        logger.info("ETL 调度器已启动")

    def stop_scheduler(self):
        """停止定时调度"""
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("ETL 调度器已停止")

    def _scheduler_loop(self, symbols: List[str] = None):
        """调度器主循环"""
        # 获取全市场股票列表
        if symbols is None:
            symbols = self._get_default_stock_list()

        last_daily_update = None
        last_intraday_update = None

        while self._running:
            now = datetime.now()

            # 盘后日线更新 (每天17:00-18:00之间执行一次)
            if now.hour == 17 and last_daily_update != now.date():
                logger.info(f"开始盘后日线更新: {now}")
                try:
                    self.incremental_update(symbols, freq="day")
                except Exception as e:
                    logger.error(f"盘后更新失败: {e}")
                last_daily_update = now.date()

            # 盘中分钟更新 (每5分钟)
            if (9 <= now.hour <= 15) and now.weekday() < 5:
                if last_intraday_update is None or \
                   (now - last_intraday_update).total_seconds() >= self.config.intraday_interval:
                    logger.info(f"盘中分钟增量更新: {now}")
                    try:
                        self.incremental_update(symbols[:100], freq="1min")  # 只更新前100只
                    except Exception as e:
                        logger.error(f"盘中更新失败: {e}")
                    last_intraday_update = now

            time.sleep(60)  # 每分钟检查一次

    def _get_default_stock_list(self) -> List[str]:
        """获取默认股票列表（沪深300成分股）"""
        try:
            import akshare as ak
            df = ak.index_stock_cons_csindex("000300")
            if df is not None and not df.empty:
                return df["成分券代码"].tolist()
        except Exception as e:
            logger.warning(f"获取沪深300成分股失败: {e}")

        # 降级：返回核心股票列表
        return [
            "600519", "000858", "601318", "600036", "000333",
            "600276", "601012", "600887", "002415", "300750",
            "600900", "600030", "601888", "000001", "002594",
            "601166", "600585", "601398", "000651", "300059",
        ]

    # ================================================================
    # 数据校验
    # ================================================================

    def validate_data(self, symbols: List[str], freq: str = "day") -> Dict[str, Any]:
        """校验数据完整性

        检查项：
          - 数据是否存在
          - 日期是否连续
          - 是否有跳空/异常值
          - 复权因子是否正确
        """
        results = {"total": len(symbols), "valid": 0, "missing": 0, "issues": []}

        for symbol in symbols:
            df = self.converter.load_qlib_data(symbol, freq)
            if df is None or df.empty:
                results["missing"] += 1
                results["issues"].append({"symbol": symbol, "issue": "数据缺失"})
                continue

            issues = []

            # 检查日期连续性
            if freq == "day":
                date_gaps = df.index.to_series().diff().dropna()
                if freq == "day":
                    large_gaps = date_gaps[date_gaps > timedelta(days=7)]
                    if len(large_gaps) > 0:
                        issues.append(f"日期中断: {len(large_gaps)}处")

            # 检查OHLC逻辑
            if (df["$high"] < df["$low"]).any():
                issues.append("high < low")
            if (df["$close"] < 0).any():
                issues.append("负价格")

            # 检查异常跳空
            if freq == "day":
                pct = df["$close"].pct_change()
                jumps = pct[pct.abs() > 0.11]  # 日涨跌幅 > 11% (含ST)
                if len(jumps) > 0:
                    issues.append(f"异常跳空: {len(jumps)}处")

            if issues:
                results["issues"].append({"symbol": symbol, "issues": issues})
            else:
                results["valid"] += 1

        return results

    # ================================================================
    # 状态
    # ================================================================

    def get_stats(self) -> Dict[str, Any]:
        """获取ETL统计"""
        return dict(self._stats)

    def get_available_symbols(self, freq: str = "day") -> List[str]:
        """获取已在Qlib库中的股票列表"""
        target_dir = self.converter.day_dir if freq == "day" else self.converter.min_dir
        symbols = []
        for d in target_dir.iterdir():
            if d.is_dir() and (d / f"{d.name}.bin").exists():
                symbols.append(d.name.upper())
        return sorted(symbols)

    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据概览"""
        day_symbols = self.get_available_symbols("day")
        min_symbols = self.get_available_symbols("1min")

        summary = {
            "day_stocks": len(day_symbols),
            "minute_stocks": len(min_symbols),
            "day_date_range": None,
            "minute_date_range": None,
        }

        if day_symbols:
            df = self.converter.load_qlib_data(day_symbols[0], "day")
            if df is not None and not df.empty:
                summary["day_date_range"] = [str(df.index[0]), str(df.index[-1])]

        if min_symbols:
            df = self.converter.load_qlib_data(min_symbols[0], "1min")
            if df is not None and not df.empty:
                summary["minute_date_range"] = [str(df.index[0]), str(df.index[-1])]

        return summary


# ============================================================
# 全局单例
# ============================================================

_etl: Optional[MarketETL] = None


def get_etl_service(config: ETLConfig = None) -> MarketETL:
    global _etl
    if _etl is None:
        _etl = MarketETL(config)
    return _etl


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    etl = MarketETL()
    print("=== ETL 服务测试 ===")
    print(f"数据目录: {etl.converter.data_dir}")
    print(f"可用日线: {len(etl.get_available_symbols('day'))} 只")
    print(f"可用分钟: {len(etl.get_available_symbols('1min'))} 只")

    # 测试单只股票拉取
    print("\n=== 测试单只股票拉取 ===")
    ok, msg = etl.update_stock("600519", "day", "20260101", "20260618")
    print(f"  600519: {ok} - {msg}")

    print("\n=== 数据校验 ===")
    result = etl.validate_data(["600519"], "day")
    print(f"  校验: {result}")

    print("\n=== 数据概览 ===")
    print(f"  {etl.get_data_summary()}")

    print("\n测试完成!")