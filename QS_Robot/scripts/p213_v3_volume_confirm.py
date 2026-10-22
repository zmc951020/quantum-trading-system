#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.13 逃顶量能确认降误杀 + 精准性复核
======================================================================
背景（P2.12 定稿，V1.13）：
  V3d（UT_N=5/UT_REC=3/UT_LB=5）可写入候选基线；四维护佑安全性/稳定性
  达标 + 高效性形式 + 精准性临界（胜率 -0.4pp）；逃顶避损 54.1% 有效但
  误杀 45.7% 偏高（卖出后 10 日反弹占比）。

本实验（P2.13）：
  Part A：逃顶量能确认变体扫描——sell_ut 加"UT 触发日量能放大"条件
    （volume > 20 日均量 × mult，mult=1.0/1.2/1.5），对比 V3d 基线：
    逃顶卖出次数、误杀率（卖出后反弹占比）、避损率、总收益/回撤/胜率；
  Part B：精准性复核——基线追高占比补测（p212 未输出基线 chase 值，
    精准性达标线"追高占比降≥20%"需基线参照）+ 胜率口径核对；
  Part C：逃顶量能最优变体 × 反转通道的完整四维护佑重判。

判据（V1.5 §3.2 达标线，测试段）：
  精准性：PF/胜率改善且追高占比降≥20%（追高指标对突破载体不适用，
    以区分度为准——P2-Full 已定）
  高效性：信号效率提升≥20%

用法：D:\anaconda3\python.exe p213_v3_volume_confirm.py
输出：results/p213_v3_volume_confirm_YYYYMMDD.md
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

import p210_v3_reversal_retest as p210
import p2_full_backtest as m

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
RESULT_DIR = os.path.join(QS_ROOT, "results")

UT_N, UT_REC, UT_LB = 5, 3, 5  # V3d 定稿参数


def build_v3d_vol(code, vol_mult=None):
    """build_v3 + vol 列 + sell_ut 量能确认变体。
    vol_mult=None 时 = V3d 基线（无量能）；vol_mult=1.0/1.2/1.5 时
    sell_ut 需同时满足 volume > 20 日均量 × vol_mult（前视安全：
    20 日均量用 i-1 前窗口）。"""
    f = os.path.join(m.DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
        "volume": pd.to_numeric(df.get("volume", pd.Series(np.nan, index=df.index)), errors="coerce"),
    }).dropna(subset=["close", "high", "low"]).tail(m.LOOKBACK + 200).reset_index(drop=True)
    if len(d) < 120:
        return None
    c = d["close"]
    py = m.prev_close("daily_year", code)
    pq = m.prev_close("daily_quarter", code)
    wk = m.week_ema_state(code)
    l1_high = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2_high = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
    kst, sig = m.kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(m.WINDOW_ZONE, min_periods=100).max().shift(1)
    lo = c.rolling(m.WINDOW_ZONE, min_periods=100).min().shift(1)
    span = (hi - lo).replace(0, np.nan)
    pos = (c - lo) / span
    l5 = (pos > 0.5).fillna(False)
    atr = c.diff().abs().rolling(m.WINDOW_ATR).mean()
    l6 = (atr < atr.rolling(m.WINDOW_ATR_MEAN).mean()).fillna(False)
    b4 = (pos < 0.20).fillna(False)
    s3 = p210.ut_series(d["high"].values, c.values, n=UT_N, rec=UT_REC, lb=UT_LB)
    high_pos = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    low_pos = (c / py - 1 < 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    vol = d["volume"]
    vol_ma20 = vol.rolling(20, min_periods=5).mean().shift(1)  # 防前视：i-1 前 20 日均量
    if vol_mult is not None:
        vol_ok = (vol > vol_ma20 * vol_mult).fillna(False)
    else:
        vol_ok = pd.Series(True, index=d.index)
    out = pd.DataFrame({
        "date": d["date"].values, "close": c.values,
        "rL1": (~l1_high).astype(bool).values,
        "rL2": (~l2_high).astype(bool).values,
        "L3": l3.astype(bool).values,
        "L4": l4.astype(bool).values,
        "L5": l5.astype(bool).values,
        "L6": l6.astype(bool).values,
        "b4": b4.astype(bool).values,
        "s3": s3,
        "high_pos": high_pos.astype(bool).values,
        "low_pos": low_pos.astype(bool).values,
        "vol_ok": vol_ok.astype(bool).values,
    }).tail(m.LOOKBACK)
    out["score"] = (out[["rL1", "rL2", "L3", "L5", "L6"]].sum(axis=1)
                    + 2 * out["L4"].astype(int))
    out["reversal"] = (~out["L4"]) & out["low_pos"] & out["b4"]
    out["sell_ut"] = out["L4"] & out["high_pos"] & out["s3"]
    if vol_mult is not None:
        out["sell_ut"] = out["sell_ut"] & out["vol_ok"]  # 量能确认
    out["date_only"] = out["date"].dt.date
    return out


class V3dVolBacktest(m.DonchianBacktest):
    """V3d 模式（量能变体经 sell_ut 列注入），记录逃顶卖出日 fwd10。"""

    def __init__(self, gate_map=None, gated=False, min_score=4):
        super().__init__(gate_map=gate_map, gated=gated, min_score=min_score)
        self.mode = "v3d"

    def _blocked_at(self, g, i):
        if not (self.gated and g is not None):
            return False
        return bool(g["score"] < self.min_score and not g["reversal"])

    def _exit_extra(self, g, i):
        return bool(self.gated and g is not None and g["sell_ut"])

    def run(self, data: pd.DataFrame):
        c = data["close"].values
        h = data["high"].values
        l = data["low"].values
        dates = data["date"].dt.date.values
        n = len(c)
        cash = 100000.0
        shares = 0
        entry_cost = 0.0
        stop_price = 0.0
        peak = 100000.0
        max_dd = 0.0
        trades = []
        opens = []
        blocked = 0
        wins = losses = 0.0
        sell_ut_n = 0
        sell_ut_fwd10 = []

        atr_arr = np.full(n, np.nan)
        for i in range(m.ATR_N, n):
            atr_arr[i] = np.mean([max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
                                  for j in range(i - m.ATR_N + 1, i + 1)])

        equity = np.zeros(n)
        for i in range(n):
            g = self.gate_map.get(dates[i], None)
            if shares > 0:
                exit_ok = (i >= m.EXIT_N and c[i] < np.min(l[i - m.EXIT_N:i])) or c[i] < stop_price
                exit_ok = exit_ok or self._exit_extra(g, i)
                if exit_ok:
                    is_ut = g is not None and self._exit_extra(g, i) and not (
                        (i >= m.EXIT_N and c[i] < np.min(l[i - m.EXIT_N:i])) or c[i] < stop_price)
                    if is_ut:
                        sell_ut_n += 1
                        if i + 10 < n:
                            sell_ut_fwd10.append(c[i + 10] / c[i] - 1.0)
                    proceeds = shares * c[i] * (1 - m.COST)
                    pnl = proceeds - entry_cost
                    cash += proceeds
                    if pnl > 0:
                        wins += pnl
                    else:
                        losses += abs(pnl)
                    trades.append({"action": "sell", "i": i, "date": dates[i],
                                   "price": c[i], "pnl": pnl})
                    shares = 0
            if shares == 0 and i >= m.ENTRY_N:
                entry_sig = c[i] > np.max(h[i - m.ENTRY_N:i])
                if entry_sig:
                    blocked_now = self._blocked_at(g, i)
                    if blocked_now:
                        blocked += 1
                    else:
                        qty = int(cash * m.POS_PCT / c[i] / 100) * 100
                        if qty > 0:
                            entry_cost = qty * c[i] * (1 + m.COST)
                            cash -= entry_cost
                            shares = qty
                            stop_price = c[i] - m.ATR_STOP_MULT * (
                                atr_arr[i] if np.isfinite(atr_arr[i]) else c[i] * 0.02)
                            opens.append({
                                "date": dates[i], "price": c[i],
                                "score": g["score"] if g is not None else np.nan,
                                "L4": g["L4"] if g is not None else np.nan,
                                "L5": g["L5"] if g is not None else np.nan,
                                "reversal": g["reversal"] if g is not None else False,
                                "high_pos": g["high_pos"] if g is not None else False,
                            })
                            trades.append({"action": "buy", "i": i, "date": dates[i],
                                           "price": c[i], "qty": qty})
            equity[i] = cash + shares * c[i]
            if equity[i] > peak:
                peak = equity[i]
            dd = (peak - equity[i]) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        if shares > 0 and n > 0:
            proceeds = shares * c[-1] * (1 - m.COST)
            pnl = proceeds - entry_cost
            cash += proceeds
            if pnl > 0:
                wins += pnl
            else:
                losses += abs(pnl)
            trades.append({"action": "sell", "i": n - 1, "date": dates[-1],
                           "price": c[-1], "pnl": pnl})

        total_return = cash / 100000.0 - 1.0
        pf = wins / losses if losses > 0 else (np.inf if wins > 0 else np.nan)
        rets = np.diff(equity) / np.maximum(equity[:-1], 1e-9)
        sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
        sells = [t for t in trades if t["action"] == "sell"]
        wr = sum(1 for t in sells if t["pnl"] > 0) / len(sells) if sells else 0.0
        report = {
            "total_return": total_return, "max_drawdown": max_dd, "sharpe_ratio": sharpe,
            "pf": pf, "win_rate": wr, "total_trades": len(trades) // 2,
            "final_capital": cash, "wins": wins, "losses": losses, "sell_ut_n": sell_ut_n,
        }
        opens_df = pd.DataFrame(opens) if opens else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5", "reversal", "high_pos"])
        return report, opens_df, blocked, sell_ut_fwd10


def main():
    print("[P2.13] 逃顶量能确认降误杀 + 精准性复核开始...")
    files = sorted(glob.glob(os.path.join(m.DAILY_DIR, "*_daily.csv")))

    all_dates_list = []
    base_maps = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        v3 = build_v3d_vol(code, None)
        if v3 is not None:
            base_maps[code] = v3
            all_dates_list.append(v3["date"].values)
    all_dates = np.sort(np.unique(np.concatenate(all_dates_list)))
    cutoff = all_dates[int(len(all_dates) * m.TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外），池 {len(base_maps)} 只")

    VARIANTS = [("V3d_base(无量能)", None), ("V3e_vol1.0", 1.0),
                ("V3e_vol1.2", 1.2), ("V3e_vol1.5", 1.5)]
    results = {}
    for name, vol_mult in VARIANTS:
        te = []
        for code in list(base_maps.keys()):
            v3 = build_v3d_vol(code, vol_mult)
            if v3 is None:
                continue
            data = m.load_daily(code)
            if data is None or len(data) < 120:
                continue
            gate_map = {row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]),
                                        "L5": bool(row["L5"]), "reversal": bool(row["reversal"]),
                                        "sell_ut": bool(row["sell_ut"]), "high_pos": bool(row["high_pos"])}
                        for _, row in v3.iterrows()}
            d_te = data[data["date"] >= cutoff_dt]
            if len(d_te) < 60:
                continue
            rep, opens_df, blk, su = V3dVolBacktest(gate_map=gate_map, gated=True).run(d_te)
            te.append({"code": code, "report": rep, "opens_df": opens_df, "blocked": blk,
                       "su": su, "gate_map": gate_map, "data": d_te})
        results[name] = {"te": te, "vol_mult": vol_mult}

    L = []
    L.append("# P2.13 逃顶量能确认降误杀 + 精准性复核报告")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 信号源：Donchian 20/10 突破；交易逻辑：ATR×2 止损 + 单票 20% + 0.15% 双边费用")
    L.append(f"- V3d = V2b ≥4/7 主放行 + 空头低位 B4 反转通道 + V3d UT 逃顶卖点（lb=5）")
    L.append(f"- 量能确认：sell_ut 需同时满足 volume > 20 日均量×mult（20 日均量用 i-1 前窗口，防前视）")
    L.append(f"- walk-forward：训练 <{cutoff_dt:%Y-%m-%d} → 测试段样本外，池 {len(base_maps)} 只")
    L.append("")

    L.append("## Part A：逃顶量能确认变体扫描（测试段）")
    L.append("")
    L.append("| 变体 | mult | 逃顶卖出 | 每只 | 误杀率(卖后反弹) | 避损率(卖后下跌) | 卖出日fwd10均值 | 总收益 | 最大回撤 | 胜率 | 开仓 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, r in results.items():
        te = r["te"]
        su = sum(x["report"]["sell_ut_n"] for x in te)
        su_arr = np.concatenate([x["su"] for x in te]) if any(x["su"] for x in te) else np.array([])
        rp = [x["report"] for x in te]
        ret = float(np.mean([x["total_return"] for x in rp]))
        dd = float(np.mean([x["max_drawdown"] for x in rp]))
        wr = float(np.mean([x["win_rate"] for x in rp]))
        nb = float(np.mean([x["total_trades"] for x in rp]))
        if len(su_arr):
            mis = (su_arr > 0).mean()
            avo = (su_arr < 0).mean()
            fwd = su_arr.mean()
        else:
            mis = avo = fwd = np.nan
        mult_s = "—" if r["vol_mult"] is None else f"×{r['vol_mult']}"
        L.append(f"| {name} | {mult_s} | {su} | {su/len(te):.1f} | {mis:.1%} | {avo:.1%} | "
                 f"{fwd:+.4f} | {ret:+.4f} | {dd:.4f} | {wr:.3f} | {nb:.1f} |")
    L.append("")

    # Part B 基线追高补测：基线(gated=False)跑一遍出 chase
    te_b = []
    for code in list(base_maps.keys()):
        v3 = base_maps[code]
        data = m.load_daily(code)
        if data is None or len(data) < 120:
            continue
        gate_map = {row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]),
                                    "L5": bool(row["L5"]), "reversal": bool(row["reversal"]),
                                    "sell_ut": bool(row["sell_ut"]), "high_pos": bool(row["high_pos"])}
                    for _, row in v3.iterrows()}
        d_te = data[data["date"] >= cutoff_dt]
        if len(d_te) < 60:
            continue
        rep, opens_df, blk, _ = V3dVolBacktest(gate_map=gate_map, gated=False).run(d_te)
        te_b.append({"opens_df": opens_df, "report": rep})
    ob_b = pd.concat([x["opens_df"] for x in te_b], ignore_index=True)
    chase_b = ob_b["L5"].eq(True).mean() if len(ob_b) else np.nan
    ban_b = (ob_b["L4"].eq(False) & ob_b["high_pos"].eq(True)).mean() if len(ob_b) else np.nan
    L.append("## Part B：基线追高占比补测（精准性达标线参照）")
    L.append("")
    L.append(f"- **基线（gated=False）追高占比（L5 高位开仓）**：{chase_b:.1%}（p212 未输出，本实验补测）")
    L.append(f"- 基线禁域占比（空头+高位开仓）：{ban_b:.1%}")
    for name, r in results.items():
        ob = pd.concat([x["opens_df"] for x in r["te"]], ignore_index=True)
        chase_v = ob["L5"].eq(True).mean() if len(ob) else np.nan
        ban_v = (ob["L4"].eq(False) & ob["high_pos"].eq(True)).mean() if len(ob) else np.nan
        L.append(f"- {name}：追高占比 {chase_v:.1%}（vs 基线 {chase_b:.1%}，"
                 f"变化 {(chase_v - chase_b) if np.isfinite(chase_v) else 0:+.1%}）｜"
                 f"禁域占比 {ban_v:.1%}")
    L.append("")

    L.append("## 结论（复核后填写）")
    L.append("")
    L.append("（Part A 量能确认最优变体、误杀率是否降至目标 <35%；Part B 基线追高参照下精准性判定；"
             "四维护佑重判；V3 最终定稿参数与写入状态）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p213_v3_volume_confirm_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
