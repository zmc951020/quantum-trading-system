# -*- coding: utf-8 -*-
"""
P0-D 矛盾深度分析：为什么"更优秀的股票池"收益反而没有跑赢基准？
=================================================================
用户闸门质疑（2026-10-23）：底座/热启动挑选的是更优秀的股票，结果收益更低——矛盾未深挖即放过，违背思维工程闸门。

待验证假设（逐个检验）：
  H1 时序错位：战法语义是"T 日盘中尾盘买"，我却用"T+1 开盘买"——追高当日已涨 2-5% 的股票，承担隔夜/开盘跳空
  H2 基准偏高：499 只池本身是用户精选优质池，用池内等权做基准偏高；应对比全市场（此处以 499 池对照说明其影响）
  H3 条件内部结构：换手/涨幅/市值分桶的收益差异
  H4 样本不足：75 个选股日、多数池仅 1 只 → 置信区间检验

前视控制：所有选股指标用 T 日及之前数据。
"""
import os, glob
import pandas as pd
import numpy as np
from scipy import stats as st

DATA_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext"
OUT_DIR = r"D:\Gupiao\升级vscode\QS_Robot\results"
SCAN_START = "2025-10-01"
DATA_FROM = "2021-01-01"
HOLD = [5, 10, 20]

USER = dict(pct_min=0.02, pct_max=0.05, vr5_min=1.0,
            to_min=0.05, to_max=0.10, mc_min=50e8, mc_max=200e8,
            vol_step=True, vol_cap=3.0, ma_bull=True, low=False)

def load_all():
    rows, n_fail = [], 0
    for f in glob.glob(os.path.join(DATA_DIR, "*_daily.csv")):
        code = os.path.basename(f).replace("_daily.csv", "")
        try:
            df = pd.read_csv(f, usecols=["date", "open", "high", "low", "close",
                                         "volume", "amount", "outstanding_share", "turnover"])
        except Exception:
            n_fail += 1
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] >= DATA_FROM].copy()
        if len(df) < 250:
            n_fail += 1
            continue
        df["code"] = code
        rows.append(df)
    return pd.concat(rows, ignore_index=True)

def feats(df):
    df = df.sort_values("date").reset_index(drop=True)
    c, v = df["close"], df["volume"]
    df["pct"] = c.pct_change()
    df["vr5"] = v / v.rolling(5).mean().shift(1)
    df["mktcap"] = c * df["outstanding_share"]
    df["ma5"] = c.rolling(5).mean(); df["ma10"] = c.rolling(10).mean(); df["ma20"] = c.rolling(20).mean()
    df["v_up3"] = (v >= v.shift(1)) & (v.shift(1) >= v.shift(2))
    df["v_calm"] = v.rolling(5).max() / v.rolling(5).min().replace(0, np.nan) <= 3.0
    return df

def passes(r, p):
    ok = True
    if p.get("low"):
        ok = ok and (r["low_rank"] <= 0.20 if not pd.isna(r["low_rank"]) else False)
    if "pct_min" in p:
        ok = ok and (p["pct_min"] <= r["pct"] <= p["pct_max"] if not pd.isna(r["pct"]) else False)
    if "vr5_min" in p:
        ok = ok and (r["vr5"] >= p["vr5_min"] if not pd.isna(r["vr5"]) else False)
    if "to_min" in p:
        ok = ok and (p["to_min"] <= r["turnover"] <= p["to_max"] if not pd.isna(r["turnover"]) else False)
    if "mc_min" in p:
        ok = ok and (p["mc_min"] <= r["mktcap"] <= p["mc_max"] if not pd.isna(r["mktcap"]) else False)
    if p.get("vol_step"):
        v_up = r["v_up3"] if not pd.isna(r["v_up3"]) else False
        v_calm = r["v_calm"] if not pd.isna(r["v_calm"]) else False
        vr5 = r["vr5"] if not pd.isna(r["vr5"]) else 0.0
        ok = ok and bool(v_up) and bool(v_calm) and vr5 <= p.get("vol_cap", 99)
    if p.get("ma_bull"):
        if not pd.isna(r["ma20"]):
            ok = ok and r["ma5"] > r["ma10"] and r["ma5"] > r["ma20"]
        else:
            ok = False
    return ok

def main():
    all_df = load_all()
    codes = all_df["code"].unique()
    fmap = {c: feats(all_df[all_df["code"]==c]) for c in codes}
    dates = pd.Series(sorted(all_df[all_df["code"]==codes[0]]["date"].unique()))
    scan_dates = dates[dates >= SCAN_START]

    # 收集 A1 通过股票日（含次日行为所需数据）
    recs = []
    for dt in scan_dates:
        for c in codes:
            d = fmap[c]
            if d["date"].iloc[-1] < dt:
                continue
            sub = d[d["date"] == dt]
            if sub.empty:
                continue
            r = sub.iloc[0]
            if not passes(r, USER):
                continue
            # 次日
            nxt = d[d["date"] > dt].head(1)
            nxt_close_at = None
            nxt_open = nxt["open"].iloc[0] if not nxt.empty else np.nan
            nxt_close = nxt["close"].iloc[0] if not nxt.empty else np.nan
            # 未来收益（T 收盘→T+N 收盘；T+1 开盘→T+1+N 收盘）
            fwd = d[d["date"] > dt]
            row = {"code": c, "date": dt.strftime("%Y-%m-%d"),
                   "pct": r["pct"], "turnover": r["turnover"],
                   "mktcap": r["mktcap"], "n_pass": None}
            for N in HOLD:
                if len(fwd) >= N:
                    row[f"ret_close_N{N}"] = fwd.iloc[N-1]["close"] / r["close"] - 1
                else:
                    row[f"ret_close_N{N}"] = np.nan
            for N in HOLD:
                if len(fwd) >= 1 + N:
                    row[f"ret_open_N{N}"] = fwd.iloc[N]["close"] / nxt_open - 1
                else:
                    row[f"ret_open_N{N}"] = np.nan
            if not nxt.empty:
                row["overnight_gap"] = nxt_open / r["close"] - 1
                row["nxt_day_ret"] = nxt_close / nxt_open - 1
            recs.append(row)

    dfp = pd.DataFrame(recs)
    print(f"A1 通过股票日总数={len(dfp)}")

    # ---- H1：时序对比（T收盘买 vs T+1开盘买）----
    print("\n=== H1 时序对比（同一批通过股票）===")
    for N in HOLD:
        a = dfp[f"ret_close_N{N}"].dropna()
        b = dfp[f"ret_open_N{N}"].dropna()
        print(f"N={N}: T收盘买 n={len(a)} mean={a.mean()*100:.2f}%  |  T+1开盘买 n={len(b)} mean={b.mean()*100:.2f}%  |  差={ (a.mean()-b.mean())*100:.2f}pp")

    # ---- 隔夜+次日行为 ----
    print("\n=== 通过股票的隔夜跳空与次日行为 ===")
    og = dfp["overnight_gap"].dropna()
    nr = dfp["nxt_day_ret"].dropna()
    print(f"隔夜跳空: n={len(og)} mean={og.mean()*100:.2f}%  (正=开盘高于昨收，即追高)"
          f"\n次日全天(开→收): n={len(nr)} mean={nr.mean()*100:.2f}%")

    # ---- H2：基准对比（全市场同日含"涨幅2-5%"对照组 vs 全市场全部）----
    print("\n=== H2 基准结构分析 ===")
    # 全市场所有股票日的 T收盘→T+10收盘 平均
    all_ret10, all_pct25_ret10 = [], []
    for c in codes:
        d = fmap[c]
        d = d[d["date"] >= SCAN_START]
        for i in range(len(d) - 11):
            close_i = d["close"].iloc[i]
            pct = d["pct"].iloc[i]
            if pd.isna(pct) or close_i <= 0:
                continue
            r10 = d["close"].iloc[i+10] / close_i - 1
            all_ret10.append(r10)
            if 0.02 <= pct <= 0.05:
                all_pct25_ret10.append(r10)
    ar = np.mean(all_ret10); apr = np.mean(all_pct25_ret10)
    print(f"全市场(499池) 任意日持有10日: n={len(all_ret10)} mean={ar*100:.2f}%")
    print(f"全市场 当日涨2-5%的股票日 持有10日: n={len(all_pct25_ret10)} mean={apr*100:.2f}%  <- '条件1涨幅'本身的市场平均")
    print(f"A1池内 ret_close_10 mean={dfp['ret_close_N10'].mean()*100:.2f}%")

    # ---- H3：分桶 ----
    print("\n=== H3 条件内部结构分桶（T收盘→10日）===")
    bins_to = [(0.05, 0.07), (0.07, 0.10)]
    for lo, hi in bins_to:
        sub = dfp[(dfp["turnover"] >= lo) & (dfp["turnover"] < hi)]
        if len(sub):
            print(f"换手 {lo*100:.0f}-{hi*100:.0f}%: n={len(sub)} ret10={sub['ret_close_N10'].mean()*100:.2f}%")
    bins_pct = [(0.02, 0.035), (0.035, 0.05)]
    for lo, hi in bins_pct:
        sub = dfp[(dfp["pct"] >= lo) & (dfp["pct"] < hi)]
        if len(sub):
            print(f"涨幅 {lo*100:.1f}-{hi*100:.1f}%: n={len(sub)} ret10={sub['ret_close_N10'].mean()*100:.2f}%")

    # ---- H4：样本量/置信区间 ----
    print("\n=== H4 样本量与置信区间（A1池 vs 基准，ret_close_10）===")
    pool10 = dfp["ret_close_N10"].dropna()
    t, p = st.ttest_1samp(pool10, 0)
    ci = st.t.interval(0.95, len(pool10)-1, loc=pool10.mean(), scale=st.sem(pool10))
    print(f"n={len(pool10)} mean={pool10.mean()*100:.2f}% CI95=[{ci[0]*100:.2f}%, {ci[1]*100:.2f}%] t={t:.2f} p={p:.4f}")

    dfp.to_csv(os.path.join(OUT_DIR, "p0d_contradiction_analysis_20261023.csv"), index=False, encoding="utf-8-sig")
    print("\n落盘: " + os.path.join(OUT_DIR, "p0d_contradiction_analysis_20261023.csv"))

if __name__ == "__main__":
    main()
