# -*- coding: utf-8 -*-
"""
P0-C v2 日线全市场选股扫描（底座引擎正确语义验证，三方案）
====================================================
前视控制：T 日盘后选股 → T+1 日开盘买入 → 持有 N 日卖出。

方案A1：用户战法日线可算版 6 条（忠实 7 条，无低位分位；均线"向上发散"宽松化 MA5>MA10 且 MA5>MA20）
方案A2：用户战法 6 条 + 低位分位≤20%（"底部+启动"完整语义）
方案B ：实现版 6 条对照（现价>4/低位≤20%/量比3-10/涨幅2-8%/换手2-15%/成交额2-20亿）

输出：results/p0c_*_20261023.{csv,md}
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

# 用户战法参数（忠实记忆版）
USER = dict(pct_min=0.02, pct_max=0.05, vr5_min=1.0,
            to_min=0.05, to_max=0.10, mc_min=50e8, mc_max=200e8,
            vol_step=True, vol_cap=3.0, ma_bull=True, low=False)
USER_LOW = dict(USER, low=True)          # +低位分位≤20%
IMPL = dict(price_min=4.0, low=True, pct_min=0.02, pct_max=0.08,
            vr20_min=3.0, vr20_max=10.0, to_min=0.02, to_max=0.15,
            amt_min=2e8, amt_max=20e8, ma_bull=False)

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

def passes(r, p):
    ok = True
    if "price_min" in p:
        ok = ok and r["close"] >= p["price_min"]
    if p.get("low"):
        ok = ok and (r["low_rank"] <= 0.20 if not pd.isna(r["low_rank"]) else False)
    if "pct_min" in p:
        ok = ok and (p["pct_min"] <= r["pct"] <= p["pct_max"] if not pd.isna(r["pct"]) else False)
    if "vr5_min" in p:
        ok = ok and (r["vr5"] >= p["vr5_min"] if not pd.isna(r["vr5"]) else False)
    if "vr20_min" in p:
        ok = ok and (p["vr20_min"] <= r["vr20"] <= p["vr20_max"] if not pd.isna(r["vr20"]) else False)
    if "to_min" in p:
        ok = ok and (p["to_min"] <= r["turnover"] <= p["to_max"] if not pd.isna(r["turnover"]) else False)
    if "mc_min" in p:
        ok = ok and (p["mc_min"] <= r["mktcap"] <= p["mc_max"] if not pd.isna(r["mktcap"]) else False)
    if "amt_min" in p:
        ok = ok and (p["amt_min"] <= r["amount"] <= p["amt_max"] if not pd.isna(r["amount"]) else False)
    if p.get("vol_step"):
        v_up = r["v_up3"] if not pd.isna(r["v_up3"]) else False
        v_calm = r["v_calm"] if not pd.isna(r["v_calm"]) else False
        vr5 = r["vr5"] if not pd.isna(r["vr5"]) else 0.0
        ok = ok and bool(v_up) and bool(v_calm) and vr5 <= p.get("vol_cap", 99)
    if p.get("ma_bull"):
        # "向上发散"宽松版：MA5>MA10 且 MA5>MA20（不要求 MA10>MA20，允许 20 线走平初升）
        if not pd.isna(r["ma20"]):
            ok = ok and r["ma5"] > r["ma10"] and r["ma5"] > r["ma20"]
        else:
            ok = False
    return ok

def main():
    all_df = load_all()
    codes = all_df["code"].unique()
    print(f"股票数={len(codes)}")
    fmap = {c: feats(all_df[all_df["code"]==c]) for c in codes}
    dates = pd.Series(sorted(all_df[all_df["code"]==codes[0]]["date"].unique()))
    scan_dates = dates[dates >= SCAN_START]
    print(f"扫描交易日={len(scan_dates)}")

    schemes = {"A1_user6": USER, "A2_user6_low": USER_LOW, "B_impl6": IMPL}
    daily = {k: {"date": [], "n": [], "pass": []} for k in schemes}
    for dt in scan_dates:
        for k, p in schemes.items():
            lst = []
            for c in codes:
                d = fmap[c]
                if d["date"].iloc[-1] < dt:
                    continue
                sub = d[d["date"] == dt]
                if sub.empty:
                    continue
                if passes(sub.iloc[0], p):
                    lst.append(c)
            daily[k]["date"].append(dt.strftime("%Y-%m-%d"))
            daily[k]["n"].append(len(lst))
            daily[k]["pass"].append(";".join(lst))

    # 收益验证（对 A1/A2/B 各池）
    perf = {k: [] for k in schemes}
    for dt in scan_dates:
        ds = dt.strftime("%Y-%m-%d")
        next_dates = dates[dates > dt]
        if len(next_dates) < 1 + max(HOLD):
            continue
        buy_date = next_dates.iloc[0]
        for k in schemes:
            row = daily[k]
            idx = row["date"].index(ds)
            pool = set(row["pass"][idx].split(";")) if row["pass"][idx] else set()
            if not pool:
                continue
            for N in HOLD:
                if len(next_dates) < 1 + N:
                    continue
                sell_date = next_dates.iloc[N]
                pr = []
                for c in pool:
                    d = fmap[c]
                    b = d[d["date"] == buy_date]; s = d[d["date"] == sell_date]
                    if b.empty or s.empty or b["open"].iloc[0] <= 0:
                        continue
                    pr.append(s["close"].iloc[0] / b["open"].iloc[0] - 1)
                br = []
                for c in codes:
                    d = fmap[c]
                    b = d[d["date"] == buy_date]; s = d[d["date"] == sell_date]
                    if b.empty or s.empty or b["open"].iloc[0] <= 0:
                        continue
                    br.append(s["close"].iloc[0] / b["open"].iloc[0] - 1)
                if pr and br:
                    perf[k].append({"select_date": ds, "buy_date": buy_date.strftime("%Y-%m-%d"),
                                    "sell_date": sell_date.strftime("%Y-%m-%d"), "hold": N,
                                    "n_pass": len(pool), "n_valid": len(pr),
                                    "pool_ret": float(np.mean(pr)), "bench_ret": float(np.mean(br)),
                                    "alpha": float(np.mean(pr) - np.mean(br))})

    # 落盘
    lines = []
    lines.append("# P0-C 日线全市场选股扫描（底座引擎正确语义验证，v2 三方案）")
    lines.append("")
    lines.append("> 日期：2026-10-23 ｜ 数据：daily_data_ext 全市场 499 只（535 CSV 中 36 只读取失败/剔除）")
    lines.append("> 前视控制：T 日盘后选股 → T+1 日开盘买入 → 持有 N 日收盘卖出")
    lines.append("> 触发：用户纠正 P0-B 方法论——底座/热启动是**选股器**，应先在**全市场**扫描选出通过股票（应很少），再在池内股票上验证，而非对固定样本逐信号过滤")
    lines.append("")
    lines.append(f"候选样本 = 499 只 × {len(scan_dates)} 交易日 = {499*len(scan_dates)} 股票日")
    lines.append("")
    lines.append("## 一、每日通过股票数（验证'通过底座引擎的股票应该很少'）")
    lines.append("")
    lines.append("| 方案 | 条件 | 累计通过 | 日均 | 中位 | 最大 | 通过率 |")
    lines.append("|---|---|---|---|---|---|---|")
    name_map = {"A1_user6": "A1 用户战法6条(无低位,均线宽松)", "A2_user6_low": "A2 用户战法6条+低位分位≤20%", "B_impl6": "B 实现版6条(对照)"}
    for k in schemes:
        s = pd.Series(daily[k]["n"])
        tot = 499 * len(scan_dates)
        lines.append(f"| {name_map[k]} | 见下 | {s.sum()} | {s.mean():.2f} | {s.median():.0f} | {s.max()} | {s.sum()/tot*100:.3f}% |")
    lines.append("")
    lines.append("## 二、池内 vs 全市场基准（T+1 开盘买入，持有 N 日）")
    lines.append("")
    for k in schemes:
        lines.append(f"### {name_map[k]}")
        lines.append("")
        lines.append("| 持有日 | 选股日样本 | 池内均收益 | 基准均收益 | 超额alpha | t | p |")
        lines.append("|---|---|---|---|---|---|---|")
        for N in HOLD:
            sub = pd.DataFrame(perf[k])
            sub = sub[sub["hold"] == N] if not sub.empty else sub
            if sub.empty:
                lines.append(f"| {N}日 | 0 | - | - | - | - | - |")
                continue
            a = sub["alpha"].dropna()
            t, p = st.ttest_1samp(a, 0) if len(a) > 1 else (np.nan, np.nan)
            lines.append(f"| {N}日 | {len(sub)} | {sub['pool_ret'].mean()*100:.2f}% | {sub['bench_ret'].mean()*100:.2f}% | {a.mean()*100:.2f}% | {t:.2f} | {p:.4f} |")
        lines.append("")
    lines.append("## 三、参数定义")
    lines.append("```python")
    lines.append("A1 USER = " + str(USER))
    lines.append("A2 USER_LOW = " + str(USER_LOW))
    lines.append("B  IMPL = " + str(IMPL))
    lines.append("```")
    lines.append("")
    lines.append("分时尾盘回踩峰顶线（用户第 7 条）= 精准买点：日线不可模拟，跳过")
    lines.append("")
    lines.append("## 四、结论（待汇总）")
    report = "\n".join(lines)
    with open(os.path.join(OUT_DIR, "p0c_daily_selection_scan_20261023.md"), "w", encoding="utf-8") as f:
        f.write(report)
    for k in schemes:
        pd.DataFrame(daily[k]).to_csv(os.path.join(OUT_DIR, f"p0c_daily_{k}_20261023.csv"), index=False, encoding="utf-8-sig")
    for k in schemes:
        if perf[k]:
            pd.DataFrame(perf[k]).to_csv(os.path.join(OUT_DIR, f"p0c_perf_{k}_20261023.csv"), index=False, encoding="utf-8-sig")

    print("=== 每日通过数 ===")
    for k in schemes:
        s = pd.Series(daily[k]["n"])
        print(f"{k}: sum={s.sum()} mean={s.mean():.2f} median={s.median():.0f} max={s.max()}")
    print("=== 池内收益（仅 A1 示例）===")
    for N in HOLD:
        sub = [x for x in perf["A1_user6"] if x["hold"] == N]
        if sub:
            pr = np.mean([x["pool_ret"] for x in sub]); br = np.mean([x["bench_ret"] for x in sub])
            print(f"N={N}: 样本={len(sub)} pool={pr*100:.2f}% bench={br*100:.2f}% alpha={(pr-br)*100:.2f}%")
    print("报告: " + os.path.join(OUT_DIR, "p0c_daily_selection_scan_20261023.md"))

if __name__ == "__main__":
    main()
