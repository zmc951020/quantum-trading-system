#!/usr/bin/env python3
"""
AKShare 数据源适配器

对接东方财富/新浪财经等数据源，提供A股股票数据。
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from core.data_bus import create_kline_format, create_financial_format
from core.data_sources.base_adapter import BaseDataSourceAdapter


class AKShareAdapter(BaseDataSourceAdapter):
    """AKShare 数据源适配器"""

    name = "akshare"

    def _init(self):
        """初始化 AKShare"""
        self._ak = None
        try:
            import akshare as ak
            self._ak = ak
            self._available = True
            print(f"[AKShareAdapter] AKShare已加载")
        except ImportError:
            print(f"[AKShareAdapter] AKShare未安装，使用模拟模式")
            self._available = True  # 模拟模式仍可用

    # --------------------------------------------------------
    # K线数据获取
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        """获取K线数据（从AKShare获取，或生成模拟数据）"""
        try:
            if self._ak is not None:
                data = self._fetch_kline(symbol, period, days)
                if data is not None and data.get("count", 0) > 0:
                    return data

            # AKShare不可用或获取失败，使用模拟数据
            return self._generate_mock_kline(symbol, days)

        except Exception as e:
            print(f"[AKShareAdapter] get_kline异常: {e}")
            return self._generate_mock_kline(symbol, days)

    def _fetch_kline(self, symbol: str, period: str, days: int) -> Optional[Dict[str, Any]]:
        """通过 AKShare 获取 K线"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days * 2 + 30)

            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")

            period_map = {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly",
                "1min": "1",
                "5min": "5",
                "15min": "15",
                "30min": "30",
                "60min": "60"
            }

            ak_period = period_map.get(period, "daily")

            if period in ["daily", "weekly", "monthly"]:
                df = self._ak.stock_zh_a_hist(
                    symbol=symbol,
                    period=ak_period,
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq"
                )
            else:
                df = self._ak.stock_zh_a_minute(
                    symbol=symbol,
                    period=ak_period,
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq"
                )

            if df is None or df.empty:
                return None

            return self._normalize_kline(symbol, df, period)
        except Exception as e:
            print(f"[AKShareAdapter] AKShare获取K线失败 {symbol}: {e}")
            return None

    def _normalize_kline(self, symbol: str, df, period: str) -> Dict[str, Any]:
        """标准化 AKShare 返回的 K线数据"""
        try:
            # 中文列名映射
            col_map = {
                "日期": "dates",
                "时间": "dates",
                "开盘": "opens",
                "最高": "highs",
                "最低": "lows",
                "收盘": "closes",
                "收盘价": "closes",
                "成交量": "volumes"
            }

            # 查找可用列名
            date_col = None
            open_col = None
            high_col = None
            low_col = None
            close_col = None
            vol_col = None

            for col in df.columns:
                mapped = col_map.get(str(col), str(col).lower())
                if mapped == "dates" and date_col is None:
                    date_col = col
                elif mapped in ("opens", "open") and open_col is None:
                    open_col = col
                elif mapped in ("highs", "high") and high_col is None:
                    high_col = col
                elif mapped in ("lows", "low") and low_col is None:
                    low_col = col
                elif mapped in ("closes", "close") and close_col is None:
                    close_col = col
                elif mapped in ("volumes", "volume") and vol_col is None:
                    vol_col = col

            # 提取数据
            n = len(df)
            dates = []
            opens = []
            highs = []
            lows = []
            closes = []
            volumes = []

            for i in range(n):
                try:
                    row = df.iloc[i]
                    d = str(row[date_col]) if date_col is not None else f"day_{i}"
                    o = float(row[open_col]) if open_col is not None else 0.0
                    h = float(row[high_col]) if high_col is not None else 0.0
                    l = float(row[low_col]) if low_col is not None else 0.0
                    c = float(row[close_col]) if close_col is not None else 0.0
                    v = float(row[vol_col]) if vol_col is not None else 0.0

                    dates.append(d)
                    opens.append(o)
                    highs.append(h)
                    lows.append(l)
                    closes.append(c)
                    volumes.append(v)
                except (ValueError, TypeError, KeyError):
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
                source="AKShare"
            )
        except Exception as e:
            print(f"[AKShareAdapter] 标准化K线失败: {e}")
            return None

    def _generate_mock_kline(self, symbol: str, days: int) -> Dict[str, Any]:
        """生成模拟K线数据（当AKShare不可用时）"""
        import random
        random.seed(hash(symbol) & 0xFFFFFFFF)

        n = min(days, 500)
        base_price = 10.0 + (hash(symbol) % 50) / 10.0

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        price = base_price
        end_date = datetime.now()

        for i in range(n):
            d = end_date - timedelta(days=n - i)
            dates.append(d.strftime("%Y-%m-%d"))

            change = random.uniform(-0.03, 0.03)
            open_p = price * (1 + random.uniform(-0.01, 0.01))
            close_p = price * (1 + change)
            high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.01))
            low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.01))
            vol = random.uniform(500000, 2000000)

            opens.append(round(open_p, 2))
            highs.append(round(high_p, 2))
            lows.append(round(low_p, 2))
            closes.append(round(close_p, 2))
            volumes.append(round(vol, 0))

            price = close_p

        return create_kline_format(
            symbol=symbol,
            name=f"{symbol}(模拟)",
            market="A股",
            period="daily",
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            source="AKShare-Mock"
        )

    # --------------------------------------------------------
    # 财务数据获取
    # --------------------------------------------------------

    def get_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        try:
            if self._ak is not None:
                return self._fetch_financial(symbol)
        except Exception as e:
            print(f"[AKShareAdapter] get_financial异常: {e}")

        # 模拟财务数据
        return self._generate_mock_financial(symbol)

    def _fetch_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """通过 AKShare 获取财务数据（增强版）"""
        try:
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
                "source": "AKShare"
            }

            # 1. 获取估值指标
            try:
                df = self._ak.stock_a_indicator_lg(symbol)
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    for col in df.columns:
                        col_str = str(col)
                        if "pe" in col_str.lower():
                            result["pe"] = float(row[col]) if row[col] else None
                        elif "pb" in col_str.lower():
                            result["pb"] = float(row[col]) if row[col] else None
                        elif "eps" in col_str.lower():
                            result["eps"] = float(row[col]) if row[col] else None
                        elif "roe" in col_str.lower():
                            result["roe"] = float(row[col]) if row[col] else None
            except Exception as e:
                print(f"[AKShareAdapter] 获取估值指标失败: {e}")

            # 2. 获取财务报表摘要
            try:
                df = self._ak.stock_financial_report_sina(symbol)
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    result["revenue_growth"] = float(row.get("同比增长率", 0)) / 100 if row.get("同比增长率") else None
            except Exception as e:
                pass

            # 3. 获取行业分类
            try:
                df = self._ak.stock_industry(symbol)
                if df is not None and not df.empty:
                    result["industry"] = str(df.iloc[0].get("所属行业", ""))
            except Exception as e:
                pass

            # 4. 获取市值数据
            try:
                df = self._ak.stock_a_share_spot()
                if df is not None and not df.empty:
                    match = df[df["股票代码"] == symbol]
                    if not match.empty:
                        row = match.iloc[0]
                        result["total_market_cap"] = float(row.get("最新市值", 0)) / 10000 if row.get("最新市值") else None
            except Exception as e:
                pass

            return result
        except Exception as e:
            print(f"[AKShareAdapter] AKShare获取财务数据失败: {e}")
            return self._generate_mock_financial(symbol)

    def _generate_mock_financial(self, symbol: str) -> Dict[str, Any]:
        """生成模拟财务数据"""
        import random
        random.seed(hash(symbol) & 0xFFFFFFFF)
        return create_financial_format(
            symbol=symbol,
            pe=round(8 + random.random() * 30, 2),
            pb=round(0.5 + random.random() * 5, 2),
            eps=round(random.random() * 3, 2),
            roe=round(5 + random.random() * 20, 2),
            total_market_cap=round(100 + random.random() * 900, 2),
            industry="金融",
            source="AKShare-Mock"
        )

    # --------------------------------------------------------
    # 实时数据
    # --------------------------------------------------------

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        try:
            if self._ak is not None:
                df = self._ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    match = df[df.iloc[:, 1].astype(str).str.contains(symbol, na=False)]
                    if not match.empty:
                        row = match.iloc[0]
                        return {
                            "symbol": symbol,
                            "price": float(row.get("最新价", 0)),
                            "change_pct": float(row.get("涨跌幅", 0)),
                            "volume": float(row.get("成交量", 0)),
                            "amount": float(row.get("成交额", 0)),
                            "source": "AKShare"
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
            if self._ak is not None:
                df = self._ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    result = []
                    for i in range(min(len(df), 500)):
                        row = df.iloc[i]
                        code = str(row.iloc[1]) if len(df.columns) > 1 else f"{i:06d}"
                        name = str(row.iloc[2]) if len(df.columns) > 2 else f"股票{code}"
                        result.append({"code": code, "name": name})
                    return result
        except Exception as e:
            pass
        return []

    # --------------------------------------------------------
    # 扩展功能
    # --------------------------------------------------------

    def get_index_components(self, index_code: str = "000300") -> List[str]:
        """获取指数成分股代码列表"""
        try:
            if self._ak is None:
                return []

            index_map = {
                "000300": "沪深300",
                "000001": "上证指数",
                "399001": "深证成指",
                "399006": "创业板指"
            }

            try:
                df = self._ak.index_stock_cons(index_code)
                if df is not None and not df.empty:
                    return [str(row.iloc[1]) for _, row in df.iterrows()]
            except Exception:
                pass

            # 备用接口
            try:
                df = self._ak.stock_zh_a_index_cons(symbol=index_code)
                if df is not None and not df.empty:
                    return [str(row["股票代码"]) for _, row in df.iterrows()]
            except Exception:
                pass

        except Exception as e:
            print(f"[AKShareAdapter] 获取指数成分股失败: {e}")

        # 返回模拟数据
        return [f"{i:06d}" for i in range(600001, 600031)]

    def get_concept_plates(self) -> List[Dict]:
        """获取概念板块列表"""
        try:
            if self._ak is not None:
                df = self._ak.stock_board_concept_name()
                if df is not None and not df.empty:
                    result = []
                    for _, row in df.iterrows():
                        result.append({
                            "code": str(row.iloc[0]),
                            "name": str(row.iloc[1])
                        })
                    return result
        except Exception as e:
            print(f"[AKShareAdapter] 获取概念板块失败: {e}")
        return []

    def get_stock_concepts(self, symbol: str) -> List[str]:
        """获取股票所属概念板块"""
        try:
            if self._ak is not None:
                df = self._ak.stock_board_concept_cons(symbol)
                if df is not None and not df.empty:
                    return [str(row.iloc[1]) for _, row in df.iterrows()]
        except Exception as e:
            print(f"[AKShareAdapter] 获取股票概念板块失败: {e}")
        return []
