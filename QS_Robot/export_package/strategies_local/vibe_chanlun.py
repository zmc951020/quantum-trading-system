"""缠论（缠中说禅）形态识别引擎 — 笔/中枢/买卖点，纯pandas实现，适配A股"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict

try:
    import czsc
    HAS_CZSC = True
except ImportError:
    HAS_CZSC = False


class SignalEngine:
    """缠论信号引擎：K线→去包含→分型→笔→中枢→买卖点

    参数:
        use_czsc: 优先使用czsc库
        min_bi_bars: 笔最少K线数
    """

    def __init__(self, use_czsc: bool = True, min_bi_bars: int = 5):
        self.use_czsc = use_czsc and HAS_CZSC
        self.min_bi_bars = min_bi_bars

    def generate(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """生成缠论信号：1=买点，-1=卖点，0=无"""
        if self.use_czsc:
            result = self._generate_czsc(df)
        else:
            result = self._generate_builtin(df)
        # FIX T4-20261020: 补 'signal' 兼容键——加载器 GENERATE_DF 只认
        # signals/signal/action/trade 键，原输出键 buy/sell 不被识别 → 信号丢失、策略空转
        if isinstance(result, dict) and 'buy' in result and 'signal' not in result:
            signal = result['buy'].copy()
            signal[result['sell'] == -1] = -1
            result['signal'] = signal
        return result

    def _generate_czsc(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        import czsc
        kline = df[["open", "close", "high", "low", "volume"]].copy()
        kline.columns = ["open", "close", "high", "low", "vol"]
        kline = kline.reset_index(drop=True)
        try:
            c = czsc.CZSC(kline, max_bi_num=50)
            buy = pd.Series(0, index=df.index)
            sell = pd.Series(0, index=df.index)
            buy_type = pd.Series("", index=df.index, dtype=str)
            sell_type = pd.Series("", index=df.index, dtype=str)
            stop_loss = pd.Series(np.nan, index=df.index, dtype=float)
            position_ratio = pd.Series(0.0, index=df.index, dtype=float)
            risk_per_trade = pd.Series(0.02, index=df.index, dtype=float)
            for bs in c.get_signals().get("bi", []):
                if bs.get("signal") == "buy":
                    buy.iloc[int(bs.get("pos", 0))] = 1
                elif bs.get("signal") == "sell":
                    sell.iloc[int(bs.get("pos", 0))] = -1
            return {"buy": buy, "sell": sell, "buy_type": buy_type,
                    "sell_type": sell_type, "stop_loss": stop_loss,
                    "position_ratio": position_ratio, "risk_per_trade": risk_per_trade}
        except Exception:
            return self._generate_builtin(df)

    # ----------------------------------------------------------------
    # 内置简化实现
    # ----------------------------------------------------------------

    def _remove_contained(self, df: pd.DataFrame) -> pd.DataFrame:
        """K线去包含处理（向上/向下处理）"""
        df = df.reset_index(drop=True)
        cols = ["open", "close", "high", "low", "volume"]
        merged: list[dict] = []
        direction = 1  # 1=向上, -1=向下
        for i in range(len(df)):
            if not merged:
                merged.append({c: df.loc[i, c] for c in cols})
                merged[-1]["_idx"] = i
                continue
            prev = merged[-1]
            if (df.loc[i, "high"] > prev["high"] and df.loc[i, "low"] > prev["low"]):
                direction = 1
            elif (df.loc[i, "high"] < prev["high"] and df.loc[i, "low"] < prev["low"]):
                direction = -1
            if self._is_contain(df.loc[i], prev, direction):
                if direction == 1:
                    prev["high"] = max(prev["high"], df.loc[i, "high"])
                    prev["low"] = max(prev["low"], df.loc[i, "low"])
                else:
                    prev["high"] = min(prev["high"], df.loc[i, "high"])
                    prev["low"] = min(prev["low"], df.loc[i, "low"])
                prev["close"] = df.loc[i, "close"]
                prev["volume"] += df.loc[i, "volume"]
            else:
                merged.append({c: df.loc[i, c] for c in cols})
                merged[-1]["_idx"] = i
        return pd.DataFrame(merged).reset_index(drop=True)

    def _is_contain(self, cur: pd.Series, prev: dict, direction: int) -> bool:
        """判断当前K线是否被前一根包含"""
        if direction == 1:
            return cur["high"] <= prev["high"] and cur["low"] >= prev["low"]
        return cur["high"] >= prev["high"] and cur["low"] <= prev["low"]

    def _detect_fx(self, df: pd.DataFrame) -> list[dict]:
        """分型识别：顶分型/底分型"""
        if len(df) < 3:
            return []
        fx_list: list[dict] = []
        for i in range(1, len(df) - 1):
            h_prev, h_cur, h_next = df.loc[i - 1, "high"], df.loc[i, "high"], df.loc[i + 1, "high"]
            l_prev, l_cur, l_next = df.loc[i - 1, "low"], df.loc[i, "low"], df.loc[i + 1, "low"]
            if h_cur > h_prev and h_cur > h_next:
                fx_list.append({"idx": df.index[i], "type": "top", "price": h_cur})
            elif l_cur < l_prev and l_cur < l_next:
                fx_list.append({"idx": df.index[i], "type": "bottom", "price": l_cur})
        return fx_list

    def _detect_bi(self, df: pd.DataFrame, fx_list: list[dict]) -> list[dict]:
        """笔检测：相邻顶底分型间"""
        if len(fx_list) < 2:
            return []
        bi_list: list[dict] = []
        last = fx_list[0]
        for fx in fx_list[1:]:
            if fx["type"] != last["type"]:
                bi_list.append({
                    "start_idx": last["idx"], "end_idx": fx["idx"],
                    "start_price": last["price"], "end_price": fx["price"],
                    "direction": "down" if last["type"] == "top" else "up",
                })
                last = fx
        return bi_list

    def _detect_zs(self, bi_list: list[dict]) -> list[dict]:
        """中枢构建：至少3笔重叠区域"""
        if len(bi_list) < 3:
            return []
        zs_list: list[dict] = []
        for i in range(len(bi_list) - 2):
            highs = [max(bi_list[j]["start_price"], bi_list[j]["end_price"]) for j in range(i, i + 3)]
            lows = [min(bi_list[j]["start_price"], bi_list[j]["end_price"]) for j in range(i, i + 3)]
            zg = min(max(highs), max(lows))
            zd = max(min(highs), min(lows))
            if zg > zd:
                zs_list.append({"start_idx": bi_list[i]["start_idx"],
                                "end_idx": bi_list[i + 2]["end_idx"], "zg": zg, "zd": zd})
        return zs_list

    def _detect_buy_sell_points(self, df: pd.DataFrame, merged: pd.DataFrame,
                                 bi_list: list[dict], zs_list: list[dict]
                                 ) -> Dict[str, pd.Series]:
        """买卖点判定：一买/二买/三买，一卖/二卖/三卖，含止损位与仓位"""
        buy = pd.Series(0, index=df.index, dtype=int)
        sell = pd.Series(0, index=df.index, dtype=int)
        buy_type = pd.Series("", index=df.index, dtype=str)
        sell_type = pd.Series("", index=df.index, dtype=str)
        stop_loss = pd.Series(np.nan, index=df.index, dtype=float)
        position_ratio = pd.Series(0.0, index=df.index, dtype=float)
        risk_per_trade = pd.Series(0.02, index=df.index, dtype=float)

        if len(bi_list) < 4 or not zs_list:
            return {"buy": buy, "sell": sell, "buy_type": buy_type,
                    "sell_type": sell_type, "stop_loss": stop_loss,
                    "position_ratio": position_ratio, "risk_per_trade": risk_per_trade}

        idx_map = merged["_idx"].values if "_idx" in merged.columns else merged.index.values
        last_zs = zs_list[-1]

        def _get_orig_pos(merged_idx: int) -> int:
            if merged_idx < len(idx_map):
                return int(idx_map[merged_idx])
            return merged_idx

        # RSI(14) 序列（基于去包含后的收盘价），用于一买的底背驰判断：
        # 价格创新低但 RSI 不创新低（RSI 抬升）且处于超卖区，才确认一买，避免"接飞刀"。
        _close = merged["close"].astype(float)
        _delta = _close.diff()
        _gain = _delta.clip(lower=0).rolling(14).mean()
        _loss = (-_delta.clip(upper=0)).rolling(14).mean()
        _rs = _gain / _loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + _rs))

        def _rsi_at(merged_idx: int) -> float:
            if 0 <= merged_idx < len(rsi_series):
                v = rsi_series.iloc[merged_idx]
                return float(v) if not pd.isna(v) else float('nan')
            return float('nan')

        prev_down_lows: list[float] = []
        prev_down_rsis: list[float] = []
        prev_up_highs: list[float] = []
        has_buy1 = False
        has_sell1 = False

        for bi in bi_list:
            pos = _get_orig_pos(bi["end_idx"])
            if bi["direction"] == "down":
                cur_low = min(bi["start_price"], bi["end_price"])
                cur_rsi = _rsi_at(bi["end_idx"])
                is_new_low = (not prev_down_lows) or (cur_low < min(prev_down_lows))
                # 底背驰：价格创新低时，要求 RSI 不创新低（>= 前一个向下笔的 RSI）且 <30 超卖。
                # RSI 数据不足(NaN)时不阻断，保持原行为；首笔向下笔无参照也放行。
                divergence_ok = True
                if prev_down_lows and not pd.isna(cur_rsi) and prev_down_rsis:
                    prev_rsi = prev_down_rsis[-1]
                    if not pd.isna(prev_rsi):
                        divergence_ok = (cur_rsi < 30) and (cur_rsi >= prev_rsi)
                if is_new_low and divergence_ok:
                    buy.iloc[pos] = 1
                    buy_type.iloc[pos] = "一买"
                    has_buy1 = True
                    prev_low = min(prev_down_lows) if prev_down_lows else cur_low
                    stop_loss.iloc[pos] = round(prev_low * 0.98, 4)
                    position_ratio.iloc[pos] = 0.3
                elif has_buy1 and prev_down_lows and cur_low > min(prev_down_lows):
                    buy.iloc[pos] = 1
                    buy_type.iloc[pos] = "二买"
                    stop_loss.iloc[pos] = round(cur_low * 0.98, 4)
                    position_ratio.iloc[pos] = 0.5
                elif cur_low > last_zs["zg"]:
                    buy.iloc[pos] = 1
                    buy_type.iloc[pos] = "三买"
                    stop_loss.iloc[pos] = round(last_zs["zd"] * 0.98, 4)
                    position_ratio.iloc[pos] = 0.6
                prev_down_lows.append(cur_low)
                # 记录本笔底部 RSI（NaN 时沿用上一笔，保证背驰比较有值）
                if pd.isna(cur_rsi):
                    cur_rsi = prev_down_rsis[-1] if prev_down_rsis else 50.0
                prev_down_rsis.append(cur_rsi)
            else:
                cur_high = max(bi["start_price"], bi["end_price"])
                if not prev_up_highs or cur_high > max(prev_up_highs):
                    sell.iloc[pos] = -1
                    sell_type.iloc[pos] = "一卖"
                    has_sell1 = True
                    position_ratio.iloc[pos] = 0.3
                elif has_sell1 and prev_up_highs and cur_high < max(prev_up_highs):
                    sell.iloc[pos] = -1
                    sell_type.iloc[pos] = "二卖"
                    position_ratio.iloc[pos] = 0.5
                elif cur_high < last_zs["zd"]:
                    sell.iloc[pos] = -1
                    sell_type.iloc[pos] = "三卖"
                    position_ratio.iloc[pos] = 0.6
                prev_up_highs.append(cur_high)

        return {"buy": buy, "sell": sell, "buy_type": buy_type,
                "sell_type": sell_type, "stop_loss": stop_loss,
                "position_ratio": position_ratio, "risk_per_trade": risk_per_trade}

    def _generate_builtin(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        merged = self._remove_contained(df)
        fx_list = self._detect_fx(merged)
        bi_list = self._detect_bi(merged, fx_list)
        zs_list = self._detect_zs(bi_list)
        return self._detect_buy_sell_points(df, merged, bi_list, zs_list)

    def get_param_space(self) -> Dict[str, list]:
        """返回参数搜索空间，供超参优化器使用"""
        return {
            "min_bi_bars":        list(range(3, 11)),
            "zs_confirm_bars":    list(range(3, 9)),
            "stop_loss_atr_mult": [round(x, 1) for x in np.arange(1.5, 4.1, 0.5)],
            "take_profit_rr":     [round(x, 1) for x in np.arange(1.5, 5.1, 0.5)],
            "buy_confirm_pct":    [round(x, 4) for x in np.arange(0.0, 0.031, 0.005)],
            "sell_confirm_pct":   [round(x, 4) for x in np.arange(0.0, 0.031, 0.005)],
        }

    def get_adaptive_params(self, df: pd.DataFrame) -> Dict[str, float | int]:
        """根据市场波动率动态调整买卖点确认条件和止损止盈"""
        close = df["close"].astype(float)
        daily_ret = close.pct_change().dropna()
        if len(daily_ret) < 20:
            return {"min_bi_bars": self.min_bi_bars, "zs_confirm_bars": 5,
                    "stop_loss_atr_mult": 2.0, "take_profit_rr": 2.5,
                    "buy_confirm_pct": 0.01, "sell_confirm_pct": 0.01}

        vol = daily_ret.rolling(20).std().iloc[-1]
        if pd.isna(vol):
            vol = daily_ret.std()

        if vol > 0.03:
            return {"min_bi_bars": 7, "zs_confirm_bars": 7, "stop_loss_atr_mult": 3.0,
                    "take_profit_rr": 3.5, "buy_confirm_pct": 0.02, "sell_confirm_pct": 0.02}
        if vol > 0.02:
            return {"min_bi_bars": 5, "zs_confirm_bars": 5, "stop_loss_atr_mult": 2.0,
                    "take_profit_rr": 2.5, "buy_confirm_pct": 0.01, "sell_confirm_pct": 0.01}
        if vol > 0.01:
            return {"min_bi_bars": 4, "zs_confirm_bars": 4, "stop_loss_atr_mult": 1.5,
                    "take_profit_rr": 2.0, "buy_confirm_pct": 0.005, "sell_confirm_pct": 0.005}
        return {"min_bi_bars": 3, "zs_confirm_bars": 3, "stop_loss_atr_mult": 1.5,
                "take_profit_rr": 1.5, "buy_confirm_pct": 0.0, "sell_confirm_pct": 0.0}

    def apply_adaptive_params(self, params: Dict[str, float | int]) -> None:
        """应用自适应参数到当前实例"""
        self.min_bi_bars = int(params.get("min_bi_bars", self.min_bi_bars))
        self.zs_confirm_bars = int(params.get("zs_confirm_bars", 5))
        self.stop_loss_atr_mult = float(params.get("stop_loss_atr_mult", 2.0))
        self.take_profit_rr = float(params.get("take_profit_rr", 2.5))
        self.buy_confirm_pct = float(params.get("buy_confirm_pct", 0.01))
        self.sell_confirm_pct = float(params.get("sell_confirm_pct", 0.01))


if __name__ == "__main__":
    try:
        import akshare as ak
    except ImportError:
        print("请先安装 akshare: pip install akshare")
        raise SystemExit(1)

    symbol = "000300"
    print(f"获取 {symbol} 沪深300指数日线数据...")
    raw = ak.stock_zh_index_daily(symbol=f"sh{symbol}")
    df = raw.rename(columns={"date": "date", "open": "open", "high": "high",
                              "low": "low", "close": "close", "volume": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("date").reset_index(drop=True)
    df = df.tail(500)

    engine = SignalEngine(use_czsc=HAS_CZSC, min_bi_bars=5)
    signals = engine.generate(df)

    buy_count = signals["buy"].sum()
    sell_count = signals["sell"].sum()
    print(f"信号统计: 买点={buy_count}, 卖点={sell_count}")
    print(f"\n最近10个交易日信号:")
    for i in range(max(0, len(df) - 10), len(df)):
        b = int(signals["buy"].iloc[i])
        s_val = int(signals["sell"].iloc[i])
        sig = "买" if b == 1 else ("卖" if s_val == -1 else "-")
        print(f"  {df.iloc[i]['date']}: close={df.iloc[i]['close']:.2f}, signal={sig}")