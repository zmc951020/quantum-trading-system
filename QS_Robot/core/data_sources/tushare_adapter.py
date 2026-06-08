#!/usr/bin/env python3
"""
Tushare 数据源适配器

作为 AKShare 的备用数据源，提供更稳定的行情数据。
Tushare 需要注册账号并获取 token，建议通过环境变量配置。
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import os

from core.data_bus import create_kline_format, create_financial_format
from core.data_sources.base_adapter import BaseDataSourceAdapter


class TushareAdapter(BaseDataSourceAdapter):
    """Tushare 数据源适配器"""

    name = "tushare"

    def _init(self):
        """初始化 Tushare"""
        self._ts = None
        self._token = None
        self._available = False

        try:
            import tushare as ts
            self._ts = ts

            # 从环境变量获取 token
            self._token = os.environ.get("TUSHARE_TOKEN", "")
            if self._token:
                self._ts.set_token(self._token)
                self._pro = self._ts.pro_api()
                self._available = True
                print(f"[TushareAdapter] Tushare已加载（使用token）")
            else:
                # 尝试匿名模式（部分接口可用）
                self._available = True
                print(f"[TushareAdapter] Tushare已加载（匿名模式）")

        except ImportError:
            print(f"[TushareAdapter] Tushare未安装，作为降级占位")
            self._available = True  # 保持可用状态作为降级源

    # --------------------------------------------------------
    # K线数据获取
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        """获取K线数据"""
        try:
            if self._ts is not None:
                data = self._fetch_kline(symbol, period, days)
                if data is not None and data.get("count", 0) > 0:
                    return data

            return None  # 返回None，让总线降级到其他源

        except Exception as e:
            print(f"[TushareAdapter] get_kline异常: {e}")
            return None

    def _fetch_kline(self, symbol: str, period: str, days: int) -> Optional[Dict[str, Any]]:
        """通过 Tushare 获取 K线"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days + 30)

            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")

            period_map = {
                "daily": "D",
                "weekly": "W",
                "monthly": "M",
                "1min": "1MIN",
                "5min": "5MIN",
                "15min": "15MIN",
                "30min": "30MIN",
                "60min": "60MIN"
            }

            ts_period = period_map.get(period, "D")

            # 补全股票代码格式
            ts_code = self._format_code(symbol)

            if hasattr(self, '_pro') and self._pro:
                # 专业版接口
                try:
                    df = self._pro.daily(
                        ts_code=ts_code,
                        start_date=start_str,
                        end_date=end_str
                    )
                    if df is not None and not df.empty:
                        return self._normalize_kline(symbol, df, period)
                except Exception:
                    pass

            # 通用接口（需要注意频率限制）
            try:
                df = self._ts.get_hist_data(
                    symbol,
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d"),
                    ktype=ts_period.lower()
                )
                if df is not None and not df.empty:
                    return self._normalize_kline(symbol, df, period)
            except Exception:
                pass

            return None

        except Exception as e:
            print(f"[TushareAdapter] 获取K线失败 {symbol}: {e}")
            return None

    def _format_code(self, symbol: str) -> str:
        """格式化股票代码为 Tushare 格式"""
        symbol = str(symbol).strip()
        if len(symbol) == 6:
            if symbol.startswith('6'):
                return f"{symbol}.SH"
            else:
                return f"{symbol}.SZ"
        return symbol

    def _normalize_kline(self, symbol: str, df, period: str) -> Dict[str, Any]:
        """标准化 Tushare 返回的 K线数据"""
        try:
            dates = []
            opens = []
            highs = []
            lows = []
            closes = []
            volumes = []

            # Tushare 返回的数据可能是降序排列，需要反转
            df = df.sort_index(ascending=True)

            for _, row in df.iterrows():
                try:
                    dates.append(str(row.get('trade_date', '')) or str(row.name))
                    opens.append(float(row.get('open', 0)))
                    highs.append(float(row.get('high', 0)))
                    lows.append(float(row.get('low', 0)))
                    closes.append(float(row.get('close', 0)))
                    volumes.append(float(row.get('volume', 0)))
                except (ValueError, TypeError):
                    continue

            return create_kline_format(
                symbol=symbol,
                name=symbol,
                market="A股",
                period=period,
                dates=dates,
                opens=opens,
                highs=highs,
                lows=lows,
                closes=closes,
                volumes=volumes,
                source="Tushare"
            )
        except Exception as e:
            print(f"[TushareAdapter] 标准化K线失败: {e}")
            return None

    # --------------------------------------------------------
    # 财务数据获取
    # --------------------------------------------------------

    def get_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        try:
            if self._ts is not None and hasattr(self, '_pro') and self._pro:
                return self._fetch_financial(symbol)
        except Exception as e:
            print(f"[TushareAdapter] get_financial异常: {e}")
        return None

    def _fetch_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """通过 Tushare 获取财务数据"""
        try:
            ts_code = self._format_code(symbol)

            result = {
                "symbol": symbol,
                "name": symbol,
                "pe": None,
                "pb": None,
                "eps": None,
                "roe": None,
                "revenue_growth": None,
                "profit_growth": None,
                "total_market_cap": None,
                "industry": None,
                "source": "Tushare"
            }

            # 获取估值数据
            try:
                df = self._pro.daily_basic(ts_code=ts_code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    result["pe"] = float(row.get("pe", 0)) if row.get("pe") else None
                    result["pb"] = float(row.get("pb", 0)) if row.get("pb") else None
                    result["eps"] = float(row.get("eps", 0)) if row.get("eps") else None
            except Exception:
                pass

            # 获取财务指标
            try:
                df = self._pro.fina_indicator(ts_code=ts_code, start_date="20240101")
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    result["roe"] = float(row.get("roe", 0)) if row.get("roe") else None
            except Exception:
                pass

            # 获取行业分类
            try:
                df = self._pro.stock_basic(ts_code=ts_code)
                if df is not None and not df.empty:
                    result["industry"] = str(df.iloc[0].get("industry", ""))
            except Exception:
                pass

            return result
        except Exception as e:
            print(f"[TushareAdapter] 获取财务数据失败: {e}")
            return None

    # --------------------------------------------------------
    # 实时数据
    # --------------------------------------------------------

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        try:
            if self._ts is not None:
                df = self._ts.get_today_all()
                if df is not None and not df.empty:
                    match = df[df["code"] == symbol]
                    if not match.empty:
                        row = match.iloc[0]
                        return {
                            "symbol": symbol,
                            "price": float(row.get("trade", 0)),
                            "change_pct": float(row.get("changepercent", 0)),
                            "volume": float(row.get("volume", 0)),
                            "amount": float(row.get("amount", 0)),
                            "source": "Tushare"
                        }
        except Exception as e:
            pass
        return None

    # --------------------------------------------------------
    # 股票列表
    # --------------------------------------------------------

    def get_stock_list(self, market: str = "A股") -> List[Dict]:
        """获取股票列表"""
        try:
            if self._ts is not None and hasattr(self, '_pro') and self._pro:
                df = self._pro.stock_basic(exchange="", list_status="L")
                if df is not None and not df.empty:
                    result = []
                    for _, row in df.iterrows():
                        result.append({
                            "code": str(row["ts_code"]).split('.')[0],
                            "name": str(row["name"])
                        })
                    return result
        except Exception as e:
            pass
        return []
