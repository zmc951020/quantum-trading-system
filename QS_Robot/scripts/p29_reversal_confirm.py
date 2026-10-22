#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.9 反转确认条件实验（买点侧 + 卖点侧镜像）
============================================
背景（Q5/Q6 立项，V1.10 定稿）：
  - 买点侧（P2.7）：空头+低位向上突破 = 反转买点候选（fwd10 +0.0100，
    反转候选 +0.0905）——需反转确认条件叠加后专门放行（V2 反转确认通道）；
  - 卖点侧（P2.8）：多头+高位向下突破 = 逃顶卖点候选（fwd10 -0.0089，
    避损 7.95%）——需顶部反转确认条件（逃顶卖点确认）。

本实验（P2.9）回答（实证闸门 2，逐条件测独立增量）：
  买点侧候选集（空头+低位 且 向上突破）上测 4 个反转确认条件：
    B1 RSI(14) 底背离（价格新低而 RSI 抬高）
    B2 MACD DIF 底背驰（价格新低而 DIF 抬高）
    B3 威科夫 spring（跌破近期低点后 3 根内收回）
    B4 关键支撑位反弹（500 日区间分位 < 20%）
  卖点侧候选集（多头+高位 且 向下突破）上测 4 个顶部确认条件（镜像）：
    S1 RSI(14) 顶背离（价格新高而 RSI 走低）
    S2 MACD DIF 顶背驰（价格新高而 DIF 走低）
    S3 威科夫 UT（突破近期高点后 3 根内回落）
    S4 压力位滞涨（500 日区间分位 > 80%）

评估口径（每条件）：
  - 命中 vs 未命中 的 fwd10 均值差 + Welch 检验（独立增量闸门）
  - 买点侧：命中 fwd10 应显著 > 未命中（确认提升）；
  - 卖点侧：命中 fwd10 应显著 < 未命中（更负 = 逃顶质量更高）；
  - 同源共线检查：条件间重叠率 + 条件命中组的 500 日分位分布 vs 整体
    （若条件只是低位/高位强度的另一表达，标注需分层验证）。
  - 保留量闸门：条件命中数应 >= 200（避免小样本噪声）。

输出：results/p29_reversal_confirm_YYYYMMDD.md
用法：D:\anaconda3\python.exe p29_reversal_confirm.py
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 700
ENTRY_N = 20
INDEX_EXCLUDE = {"000300", "399001", "399006", "000905", "000852"}
DIV_WIN = 60
DIV_LB = 10


def rsi(close, period=14):
    delta = close.diff()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)


def macd_dif(close, fast=12, slow=26):
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()


def prev_close(mtf_dir: str, code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, mtf_dir, f"{code}.csv"))
        if len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return float("nan")


def week_ema_state(code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_week", f"{code}.csv"))
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 50:
            return None
        return bool(c.ewm(span=20, adjust=False).mean().iloc[-1]
                    > c.ewm(span=50, adjust=False).mean().iloc[-1])
    except Exception:
        return None


def load_daily(code: str):
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
    }).dropna(subset=["close", "high", "low"]).tail(LOOKBACK).reset_index(drop=True)
    return out


def welch2(a, b):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) < 5 or len(b) < 5:
        return None
    t_stat = (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df_w = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1) + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1))
    p = 2 * (1 - stats.t.cdf(abs(t_stat), df_w))
    return t_stat, p


def bearish_div(low, signal, i, win=DIV_WIN, lb=DIV_LB):
    """底背离：窗口内两个价格谷，晚谷价格更低但 signal 抬高，且晚谷临近信号日"""
    w0 = max(0, i - win)
    seg = slice(w0, i)
    seg_low = low[seg]
    if len(seg_low) < win // 2:
        return False
    j_min = w0 + int(np.argmin(seg_low))          # 绝对最低谷（晚谷）
    if j_min <= w0 or j_min >= i or i - j_min > lb:
        return False
    j_prev = w0 + int(np.argmin(low[w0:j_min]))   # 早谷（j_min 之前的最低）
    if j_prev < w0 or j_prev >= j_min:
        return False
    if low[j_min] < low[j_prev] and signal[j_min] > signal[j_prev]:
        return True
    return False


def bullish_div(high, signal, i, win=DIV_WIN, lb=DIV_LB):
    """顶背离：窗口内两个价格峰，晚峰价格更高但 signal 走低，且晚峰临近信号日"""
    w0 = max(0, i - win)
    seg = slice(w0, i)
    seg_high = high[seg]
    if len(seg_high) < win // 2:
        return False
    j_max = w0 + int(np.argmax(seg_high))         # 绝对最高峰（晚峰）
    if j_max <= w0 or j_max >= i or i - j_max > lb:
        return False
    j_prev = w0 + int(np.argmax(high[w0:j_max]))  # 早峰
    if j_prev < w0 or j_prev >= j_max:
        return False
    if high[j_max] > high[j_prev] and signal[j_max] < signal[j_prev]:
        return True
    return False


def spring_ok(low, close, i, lb=10, n=5, rec=3):
    for k in range(max(0, i - lb), i):
        ref = float(np.min(low[max(0, k - n):k]))
        if low[k] < ref and float(np.max(close[k:k + rec])) > ref:
            return True
    return False


def ut_ok(high, close, i, lb=10, n=5, rec=3):
    for k in range(max(0, i - lb), i):
        ref = float(np.max(high[max(0, k - n):k]))
        if high[k] > ref and float(np.min(close[k:k + rec])) < ref:
            return True
    return False


def pos_500(close, i):
    seg = close[max(0, i - 500):i]
    lo, hi = float(np.min(seg)), float(np.max(seg))
    if hi <= lo:
        return 0.5
    return (close[i] - lo) / (hi - lo)


def main():
    print("[P2.9] 反转确认条件实验开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    buy_rows, sell_rows = [], []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        if code in INDEX_EXCLUDE:
            continue
        data = load_daily(code)
        if data is None or len(data) < 160:
            continue
        c = data["close"].values
        h = data["high"].values
        l = data["low"].values
        dates = data["date"].dt.date.values
        n = len(c)
        r = rsi(data["close"]).values
        dif = macd_dif(data["close"]).values
        py = prev_close("daily_year", code)
        wk = week_ema_state(code)
        if wk is None:
            continue
        short_bear = not wk
        long_bull = wk
        for i in range(ENTRY_N, n):
            hi20 = float(np.max(h[i - ENTRY_N:i]))
            lo20 = float(np.min(l[i - ENTRY_N:i]))
            fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
            if not np.isfinite(fwd10):
                continue
            high_pos = bool(np.isfinite(py) and c[i] > py)
            low_pos = bool(np.isfinite(py) and c[i] < py)
            pos = pos_500(c, i)
            base = {
                "date": str(dates[i]), "code": code, "close": c[i],
                "pos500": pos, "fwd10": fwd10,
            }
            # 买点侧：空头+低位 向上突破
            if short_bear and low_pos and c[i] > hi20:
                base.update({
                    "b_rsi_div": bearish_div(l, r, i),
                    "b_macd_div": bearish_div(l, dif, i),
                    "b_spring": spring_ok(l, c, i),
                    "b_support": pos < 0.20,
                })
                buy_rows.append(base)
            # 卖点侧：多头+高位 向下突破
            if long_bull and high_pos and c[i] < lo20:
                base.update({
                    "s_rsi_div": bullish_div(h, r, i),
                    "s_macd_div": bullish_div(h, dif, i),
                    "s_ut": ut_ok(h, c, i),
                    "s_pressure": pos > 0.80,
                })
                sell_rows.append(base)

    buy_df = pd.DataFrame(buy_rows)
    sell_df = pd.DataFrame(sell_rows)
    print(f"买点侧候选集：{len(buy_df)} ｜ 卖点侧候选集：{len(sell_df)}")

    L = []
    L.append("# P2.9 反转确认条件实验报告（实证闸门 2：独立增量）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("- 口径：530 纯净个股池测试段；买点侧=空头+低位向上突破（Donchian 20），"
             "卖点侧=多头+高位向下突破；fwd10=信号后 10 日收益（买点越高越好，卖点越负越好）")
    L.append("- 闸门：每条件命中数 ≥200；买点侧命中 fwd10 显著 > 未命中；卖点侧显著 < 未命中；"
             "条件重叠率与分位分布做同源共线检查")
    L.append("")

    def report_side(title, df, conds, direction):
        L.append(f"## {title}")
        L.append("")
        L.append(f"- 候选集总量：{len(df)}，基线 fwd10 = {df['fwd10'].mean():+.4f}"
                 f"（{(df['fwd10'] > 0).mean():.1%} 正收益）")
        L.append("")
        L.append("| 条件 | 命中数 | 保留率 | 命中 fwd10 | 未命中 fwd10 | 增量 | Welch t | p | 判定 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for col, name in conds:
            hit = df[df[col]]
            miss = df[~df[col]]
            if len(hit) < 200:
                L.append(f"| {name} | {len(hit)} | {len(hit) / len(df):.1%} | "
                         f"{hit['fwd10'].mean():+.4f} | {miss['fwd10'].mean():+.4f} | "
                         f"{hit['fwd10'].mean() - miss['fwd10'].mean():+.4f} | — | — | 样本不足(<200) |")
                continue
            w = welch2(hit["fwd10"].values, miss["fwd10"].values)
            if w is None:
                L.append(f"| {name} | {len(hit)} | {len(hit) / len(df):.1%} | "
                         f"{hit['fwd10'].mean():+.4f} | {miss['fwd10'].mean():+.4f} | — | — | — | 检验样本不足 |")
                continue
            delta = hit["fwd10"].mean() - miss["fwd10"].mean()
            if direction == "buy":
                ok = w[1] < 0.05 and delta > 0
            else:
                ok = w[1] < 0.05 and delta < 0
            verdict = "**通过（独立增量）**" if ok else "未通过（增量不显著或方向不符）"
            L.append(f"| {name} | {len(hit)} | {len(hit) / len(df):.1%} | "
                     f"{hit['fwd10'].mean():+.4f} | {miss['fwd10'].mean():+.4f} | "
                     f"{delta:+.4f} | {w[0]:.2f} | {w[1]:.4g} | {verdict} |")
        L.append("")
        # 条件间重叠率（同源共线检查）
        L.append(f"**条件重叠率（同源共线检查）**：")
        cols = [c for c, _ in conds]
        for i in range(len(cols)):
            a = df[df[cols[i]]]
            if not len(a):
                continue
            ov = []
            for j in range(len(cols)):
                if i == j:
                    continue
                ov.append(f"{conds[j][1]}={len(a[a[cols[j]]]) / len(a):.0%}")
            L.append(f"- 命中 {conds[i][1]} 的信号中，同时命中：{'；'.join(ov)}")
        L.append("")
        # 命中组分位分布 vs 整体
        L.append(f"**条件命中组的 500 日分位 vs 整体**（分位越低=越低位，越高=越高位）：")
        for col, name in conds:
            hit = df[df[col]]
            if len(hit):
                L.append(f"- {name}：命中组 pos500 均值 {hit['pos500'].mean():.2f}"
                         f" vs 整体 {df['pos500'].mean():.2f}")
        L.append("")

    report_side("## 1. 买点侧：空头+低位反转买点的反转确认条件", buy_df, [
        ("b_rsi_div", "B1 RSI 底背离"),
        ("b_macd_div", "B2 MACD 底背驰"),
        ("b_spring", "B3 威科夫 spring"),
        ("b_support", "B4 关键支撑位反弹(pos<0.20)"),
    ], "buy")

    report_side("## 2. 卖点侧：多头+高位逃顶卖点的顶部确认条件", sell_df, [
        ("s_rsi_div", "S1 RSI 顶背离"),
        ("s_macd_div", "S2 MACD 顶背驰"),
        ("s_ut", "S3 威科夫 UT"),
        ("s_pressure", "S4 压力位滞涨(pos>0.80)"),
    ], "sell")

    L.append("## 3. 结论（闸门 2）")
    L.append("")
    L.append("> 通过条件（独立增量）将并入 V2 反转确认通道（买点侧）与逃顶卖点确认（卖点侧）；"
             "未通过或样本不足条件标注待扩窗复核；条件重叠率高者需分层验证（控制主条件后测次条件增量）。")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p29_reversal_confirm_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
