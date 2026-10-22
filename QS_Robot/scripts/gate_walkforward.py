#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
V2 修复候选 walk-forward 样本外验证（P2B）
============================================
背景：P2A-4 显示 V2（L1/L2 低位加分）在 250 日全样本上放行段 fwd10 +0.0354/PF2.80。
     按闸门纪律（F5 阈值漂移/多重检验），同一数据 3 版择优不能直接上线，
     必须做训练/测试时间分离的样本外验证。

设计：
  1. 构建 V2 打分（6 层：rL1/rL2 低位加分 + KST + 周线 EMA + zone + VCP），全池 500 日
  2. 按全局日历时间切分：训练段 = 前 60% 日期，测试段 = 后 40% 日期
  3. 训练段：标定放行线（≥4/6 与分位数两口径）
  4. 测试段（样本外）：验证放行 vs 否决（fwd10，含费 0.15%），并跑 3/6~6/6 敏感性
  5. 判据：测试段放行段含费均收益 > 否决段 且 PF>1 = V2 样本外有效（可进入 P2 正式回测）

输出：results/gate_walkforward_YYYYMMDD.md
用法：python gate_walkforward.py
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

LOOKBACK = 500
TRAIN_RATIO = 0.60
WINDOW_ATR = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500
COST = 0.0015
THRESHOLDS = (3, 4, 5, 6)


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
    return kst, kst.rolling(9).mean()


def build_v2(code: str):
    """V2 打分：rL1/rL2 低位加分（close < 上年末/上季末收盘）+ L3..L6。"""
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(LOOKBACK + 200)
    if len(d) < 80:
        return None
    c = d["close"]
    py = prev_close("daily_year", code)
    pq = prev_close("daily_quarter", code)
    wk = week_ema_state(code)
    l1_high = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2_high = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
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
        "rL1": (~l1_high).astype(bool).values,   # 低位加分
        "rL2": (~l2_high).astype(bool).values,
        "L3": l3.astype(bool).values,
        "L4": l4.astype(bool).values,
        "L5": l5.astype(bool).values,
        "L6": l6.astype(bool).values,
    }).tail(LOOKBACK)
    out["score"] = out[["rL1", "rL2", "L3", "L4", "L5", "L6"]].sum(axis=1)
    out["fwd10"] = out["close"].shift(-10) / out["close"] - 1.0
    out["code"] = code
    return out


def stats(df: pd.DataFrame):
    r = df["fwd10"].dropna() - COST
    if len(r) == 0:
        return None
    w = r[r > 0]; l = r[r < 0]
    pf = (w.sum() / abs(l.sum())) if len(l) and l.sum() != 0 else np.nan
    return {"n": len(df), "mean": r.mean(), "wr": (r > 0).mean(), "pf": pf}


def main():
    print("[P2B] V2 walk-forward 验证开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    rows = []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        r = build_v2(code)
        if r is not None:
            rows.append(r)
    all_df = pd.concat(rows, ignore_index=True)
    all_df = all_df.dropna(subset=["fwd10"])  # 排除测试段末尾无收益
    dates = np.sort(all_df["date"].unique())
    cutoff = dates[int(len(dates) * TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)  # 兼容 numpy datetime64
    train = all_df[all_df["date"] < cutoff_dt]
    test = all_df[all_df["date"] >= cutoff_dt]
    print(f"训练段：{train['date'].nunique()} 日 / 测试段：{test['date'].nunique()} 日（cutoff={cutoff_dt:%Y-%m-%d}）")

    L = []
    L.append("# V2 修复候选 walk-forward 样本外验证报告（P2B）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 样本：{all_df['code'].nunique()} 只 × 最近 {LOOKBACK} 日；费用 0.15% 双边")
    L.append(f"- 切分：训练段 {train['date'].nunique()} 日（<{cutoff_dt:%Y-%m-%d}） / 测试段 {test['date'].nunique()} 日（样本外）")
    L.append("- V2 打分：rL1/rL2 低位加分 + KST + 周线EMA + zone + VCP（6 层）")
    L.append("")

    L.append("## 1. 训练段标定（放行线分布）")
    L.append("")
    s_tr = train["score"]
    vc = s_tr.value_counts().sort_index()
    for v in range(7):
        L.append(f"- {v} 分：{vc.get(v, 0):,}（{vc.get(v, 0)/len(s_tr):.1%}）")
    for q in [0.5, 0.7, 0.75]:
        L.append(f"- P{int(q*100)}：{s_tr.quantile(q):.2f} 分")
    L.append("")

    L.append("## 2. 测试段（样本外）放行 vs 否决（默认 ≥4/6）")
    L.append("")
    g_pass = test[test["score"] >= 4]
    g_rej = test[test["score"] < 4]
    sp = stats(g_pass); sr = stats(g_rej)
    L.append("| 组 | n | 含费均收益 | 胜率 | PF |")
    L.append("|---|---|---|---|---|")
    if sp and sr:
        L.append(f"| 放行≥4/6 | {sp['n']:,} | {sp['mean']:+.4f} | {sp['wr']:.1%} | {sp['pf']:.2f} |")
        L.append(f"| 否决<4/6 | {sr['n']:,} | {sr['mean']:+.4f} | {sr['wr']:.1%} | {sr['pf']:.2f} |")
        L.append(f"| 差值 | — | {sp['mean']-sr['mean']:+.4f} | — | — |")
    L.append("")

    L.append("## 3. 测试段敏感性扫描（3/6 ~ 6/6）")
    L.append("")
    L.append("| 放行线 | 放行率 | 含费均收益 | 胜率 | PF | n |")
    L.append("|---|---|---|---|---|---|")
    for thr in THRESHOLDS:
        g = test[test["score"] >= thr]
        s = stats(g)
        if s:
            L.append(f"| ≥{thr}/6 | {len(g)/len(test):.1%} | {s['mean']:+.4f} | {s['wr']:.1%} | {s['pf']:.2f} | {s['n']:,} |")
    L.append("")

    L.append("## 4. 样本外置换检验（测试段）")
    L.append("")
    r_test = test["fwd10"].dropna().values
    mask = test.loc[test["fwd10"].notna(), "score"].values >= 4
    actual = r_test[mask].mean() - r_test[~mask].mean()
    np.random.seed(20261022)
    diffs = []
    for _ in range(2000):
        idx = np.random.choice(len(r_test), mask.sum(), replace=False)
        diffs.append(r_test[idx].mean() - np.delete(r_test, idx).mean())
    diffs = np.array(diffs)
    p = (np.abs(diffs) >= abs(actual)).mean()
    L.append(f"- 实际放行-否决收益差（测试段）：{actual:+.4f}")
    L.append(f"- 置换分布 std：{diffs.std():.4f}")
    L.append(f"- **置换检验 p 值：{p:.4f}**（{'样本外显著' if p < 0.05 else '样本外未达显著'}）")
    L.append("")

    L.append("## 5. 结论")
    L.append("")
    L.append("（复核后填写：V2 是否样本外有效、是否进入正式回测）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"gate_walkforward_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
