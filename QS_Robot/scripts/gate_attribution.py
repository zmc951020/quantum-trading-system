#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
放行线证伪复核与分层归因（P2A-3）
====================================
背景：gate_validation 显示 ≥4/6 放行段 fwd10 显著劣于否决段（-0.0117 vs +0.0039），
     且放行线越严收益越差。按闸门纪律，证伪结论成立前必须：
  ① 独立复核：000001 逐时点重算打分与 fwd10，与主脚本逻辑对照（不同实现路径）
  ② 分层归因：6 层各自作为"放行条件"的 fwd10 均收益 vs 全样本基线——定位反向驱动层
  ③ 长窗稳健性：LOOKBACK=500 复核"放行 vs 否决"整体结论是否稳健（排除 250 日窗口巧合）

判定输出：results/gate_attribution_YYYYMMDD.md
用法：python gate_attribution.py
依赖：D:\anaconda3\python.exe
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

WINDOW_ATR = 20
WINDOW_VCP = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500
LAYERS = ["L1年线", "L2季线", "L3KST", "L4周线", "L5zone", "L6VCP"]


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


def kst_signal(close: pd.Series):
    roc = lambda n: close.pct_change(n) * 100.0  # noqa: E731
    k = (roc(10).rolling(10).mean() * 1 + roc(15).rolling(15).mean() * 2
         + roc(20).rolling(20).mean() * 3 + roc(30).rolling(30).mean() * 4)
    kst = k.rolling(10).mean()
    sig = kst.rolling(9).mean()
    return kst, sig


def build(code: str, lookback: int):
    """独立实现（与 gate_validation 不同路径：直接用收盘环比与状态提取）返回 DataFrame。"""
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(lookback + 200)
    if len(d) < 80:
        return None
    c = d["close"]
    py = prev_close("daily_year", code)
    pq = prev_close("daily_quarter", code)
    wk = week_ema_state(code)
    l1 = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2 = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
    kst, sig = kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(WINDOW_ZONE, min_periods=100).max()
    lo = c.rolling(WINDOW_ZONE, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    l5 = ((c - lo) / span > 0.5).fillna(False)
    atr = c.diff().abs().rolling(WINDOW_ATR).mean()
    l6 = (atr < atr.rolling(WINDOW_ATR_MEAN).mean()).fillna(False)
    out = pd.DataFrame({
        "date": d["date"].values, "close": c.values,
        "L1年线": l1.astype(bool).values, "L2季线": l2.astype(bool).values,
        "L3KST": l3.astype(bool).values, "L4周线": l4.astype(bool).values,
        "L5zone": l5.astype(bool).values, "L6VCP": l6.astype(bool).values,
    }).tail(lookback)
    out["score"] = out[LAYERS].sum(axis=1)
    out["fwd10"] = out["close"].shift(-10) / out["close"] - 1.0
    out["code"] = code
    return out


def main():
    print("[P2A-3] 证伪复核与归因开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))

    # ① 独立复核 000001（与 gate_validation 逻辑不同实现路径）
    v = build("000001", 250)
    if v is not None:
        s = v[["date", "close", "score", "fwd10"]].tail(5)
        print("000001 末5行复核：")
        print(s.to_string(index=False))

    # ② 归因：全池 250 日
    rows = []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        r = build(code, 250)
        if r is not None:
            rows.append(r)
    a250 = pd.concat(rows, ignore_index=True)
    n_pts = len(a250)
    base = a250["fwd10"].dropna().mean()

    # ③ 长窗 500 日
    rows5 = []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        r = build(code, 500)
        if r is not None:
            rows5.append(r)
    a500 = pd.concat(rows5, ignore_index=True)
    n_pts5 = len(a500)
    base5 = a500["fwd10"].dropna().mean()
    g_pass5 = a500[a500["score"] >= 4]
    g_rej5 = a500[a500["score"] < 4]

    L = []
    L.append("# 放行线证伪复核与分层归因报告（P2A-3）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 250 日池：{len(a250['code'].unique())} 只 × {n_pts:,} 时点；基线 fwd10 均收益 {base:+.4f}")
    L.append(f"- 500 日池：{len(a500['code'].unique())} 只 × {n_pts5:,} 时点；基线 fwd10 均收益 {base5:+.4f}")
    L.append("- 实现说明：本脚本独立重写（环比+状态提取路径），与 gate_validation 实现路径不同")
    L.append("")

    L.append("## 1. 000001 独立复核（250 日末 5 时点）")
    L.append("")
    if v is not None:
        for _, r in v.tail(5).iterrows():
            L.append(f"- {r['date']:%Y-%m-%d} close={r['close']:.2f} score={int(r['score'])} fwd10={r['fwd10']:+.4f}")
    L.append("")

    L.append("## 2. 分层归因（250 日池：每层达标组的 fwd10 均收益 vs 基线）")
    L.append("")
    L.append("| 层 | 达标时点 | 达标组均收益 | 基线 | 方向判定 |")
    L.append("|---|---|---|---|---|")
    for col in LAYERS:
        g = a250[a250[col]]
        m = g["fwd10"].dropna().mean()
        direction = "正向贡献" if m > base else ("反向拖累" if m < base - 0.003 else "中性")
        L.append(f"| {col} | {len(g):,} | {m:+.4f} | {base:+.4f} | {direction} |")
    L.append("")

    L.append("## 3. 长窗 500 日稳健性复核（放行 ≥4/6 vs 否决）")
    L.append("")
    m_pass = g_pass5["fwd10"].dropna().mean()
    m_rej = g_rej5["fwd10"].dropna().mean()
    L.append(f"- 放行段：{len(g_pass5):,} 时点，fwd10 均收益 {m_pass:+.4f}")
    L.append(f"- 否决段：{len(g_rej5):,} 时点，fwd10 均收益 {m_rej:+.4f}")
    L.append(f"- 差值：{m_pass - m_rej:+.4f}")
    L.append(f"- 结论：{'500 日窗口确认放行劣于否决（证伪稳健）' if m_pass < m_rej else '500 日窗口结论反转（250 日窗口可能是特殊期）'}")
    L.append("")

    L.append("## 4. 证伪判定")
    L.append("")
    L.append("（由复核后填写：证伪是否成立、哪些层反向、修复方向）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"gate_attribution_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
