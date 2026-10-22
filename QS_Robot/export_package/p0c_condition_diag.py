# -*- coding: utf-8 -*-
"""P0-C 诊断：单条件通过率 + 组合叠加诊断，定位卡死条件"""
import os, glob
import pandas as pd
import numpy as np

DATA_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext"
SCAN_START = "2025-10-01"
DATA_FROM = "2021-01-01"

def load_all():
    rows = []
    n_fail = 0
    for f in glob.glob(os.path.join(DATA_DIR, "*_daily.csv")):
        code = os.path.basename(f).replace("_daily.csv", "")
        try:
            df = pd.read_csv(f, usecols=["date", "open", "high", "low", "close",
                                         "volume", "amount", "outstanding_share", "turnover"])
        except Exception as e:
            n_fail += 1
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] >= DATA_FROM].copy()
        if len(df) < 250:
            n_fail += 1
            continue
        df["code"] = code
        rows.append(df)
    print(f"读取失败/剔除: {n_fail}")
    return pd.concat(rows, ignore_index=True)

def feats(df):
    df = df.sort_values("date").reset_index(drop=True)
    c, v = df["close"], df["volume"]
    df["pct"] = c.pct_change()
    df["vr5"] = v / v.rolling(5).mean().shift(1)
    df["vr20"] = v / v.rolling(20).mean().shift(1)
    df["mktcap"] = c * df["outstanding_share"]
    lo = c.rolling(60).min().shift(1); hi = c.rolling(60).max().shift(1)
    df["low_rank"] = (c - lo) / (hi - lo).replace(0, np.nan)
    df["ma5"] = c.rolling(5).mean(); df["ma10"] = c.rolling(10).mean(); df["ma20"] = c.rolling(20).mean()
    df["v_up3"] = (v >= v.shift(1)) & (v.shift(1) >= v.shift(2))
    df["v_calm"] = v.rolling(5).max() / v.rolling(5).min().replace(0, np.nan) <= 3.0
    return df

def main():
    all_df = load_all()
    codes = all_df["code"].unique()
    print(f"股票数={len(codes)}")
    fmap = {c: feats(all_df[all_df["code"]==c]) for c in codes}
    dates = pd.Series(sorted(all_df[all_df["code"]==codes[0]]["date"].unique()))
    dates = dates[dates >= SCAN_START]

    # 逐股票拼接为"条件长表"
    cond = {k: [] for k in ["pct24", "vr5_gt1", "turnover_5_10", "mktcap_50_200",
                            "low_le20", "vol_step", "ma_bull", "price_gt4", "allA", "allB"]}
    for c in codes:
        d = fmap[c]
        for dt in dates:
            r = d[d["date"] == dt]
            if r.empty:
                continue
            r = r.iloc[0]
            pct_ok = 0.02 <= r["pct"] <= 0.05 if not pd.isna(r["pct"]) else False
            vr_ok = r["vr5"] >= 1.0 if not pd.isna(r["vr5"]) else False
            to_ok = 0.05 <= r["turnover"] <= 0.10 if not pd.isna(r["turnover"]) else False
            mc_ok = 50e8 <= r["mktcap"] <= 200e8 if not pd.isna(r["mktcap"]) else False
            lo_ok = r["low_rank"] <= 0.20 if not pd.isna(r["low_rank"]) else False
            vs_ok = (bool(r["v_up3"]) if not pd.isna(r["v_up3"]) else False) and \
                    (bool(r["v_calm"]) if not pd.isna(r["v_calm"]) else False) and \
                    (r["vr5"] <= 3.0 if not pd.isna(r["vr5"]) else False)
            ma_ok = r["ma5"] > r["ma10"] > r["ma20"] if not pd.isna(r["ma20"]) else False
            pr_ok = r["close"] >= 4.0
            cond["pct24"].append(pct_ok); cond["vr5_gt1"].append(vr_ok)
            cond["turnover_5_10"].append(to_ok); cond["mktcap_50_200"].append(mc_ok)
            cond["low_le20"].append(lo_ok); cond["vol_step"].append(vs_ok)
            cond["ma_bull"].append(ma_ok); cond["price_gt4"].append(pr_ok)
            # 方案A: 用户战法6条(含低位)
            cond["allA"].append(pct_ok and vr_ok and to_ok and mc_ok and lo_ok and vs_ok and ma_ok)
            # 方案A无低位变体
            # 方案B: 实现版6条
            b_pct = 0.02 <= r["pct"] <= 0.08 if not pd.isna(r["pct"]) else False
            b_vr = 3.0 <= r["vr20"] <= 10.0 if not pd.isna(r["vr20"]) else False
            b_to = 0.02 <= r["turnover"] <= 0.15 if not pd.isna(r["turnover"]) else False
            b_am = 2e8 <= r["amount"] <= 20e8 if not pd.isna(r["amount"]) else False
            cond["allB"].append(pr_ok and lo_ok and b_pct and b_vr and b_to and b_am)

    n = len(cond["pct24"])
    print(f"候选样本数(股票×交易日)={n}")
    print("\n单条件通过率:")
    for k in cond:
        if k.startswith("all"): continue
        print(f"  {k}: {sum(cond[k])}  ({sum(cond[k])/n*100:.3f}%)")
    print("\n组合:")
    print(f"  方案A全6条(用户战法含低位+均线): {sum(cond['allA'])} ({sum(cond['allA'])/n*100:.4f}%)")
    print(f"  方案B全6条(实现版): {sum(cond['allB'])} ({sum(cond['allB'])/n*100:.4f}%)")
    # A 去掉均线 与 去掉低位 的变体
    # 重算 A 无均线
    print("\n变体诊断（方案A逐步松绑）:")
    keysA = ["pct24","vr5_gt1","turnover_5_10","mktcap_50_200","low_le20","vol_step","ma_bull"]
    for drop in [None, "ma_bull", "low_le20", "vol_step", "turnover_5_10"]:
        ks = [k for k in keysA if k != drop]
        cnt = 0
        for i in range(n):
            if all(cond[k][i] for k in ks): cnt += 1
        name = "全6条" if drop is None else f"去掉{drop}"
        print(f"  方案A {name}: {cnt} ({cnt/n*100:.4f}%)")
    # 用户7条中的市值是否与样本池分布有关
    mc_all = [cond["mktcap_50_200"][i] for i in range(n)]
    print(f"\n市值50-200亿占比: {sum(mc_all)/n*100:.2f}%")

if __name__ == "__main__":
    main()
