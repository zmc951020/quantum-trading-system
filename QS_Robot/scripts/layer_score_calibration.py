#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
层数打分分布标定（P1b：放行阈值 ≥6/10 的数据标定）
====================================================
目的：用 533 只日线系 + 70 只分钟系历史数据，计算"层数累加打分卡"v0
     可计算层的达标分布，把"放行 ≥6/10"从拍脑袋草案变为分位数推导。

本轮口径（诚实标注，V1.3 台账）：
  可算 6 层 = 方向层 4（年线斜率、季线斜率、KST、周线结构）
            + 位置层 2（zone 分位、VCP 收缩）
  分钟池（70 只）另算 2 层：60min / 30min EMA 排列（时机层-分钟趋势）
  待 P2 接入层（本轮不计分）：缠论校验、背驰、spring/VSA 三维、regime 官方版
  → 本轮为 "6/10 临时口径"，P2 升级 10/10 后重标（实验台账记录）

判定口径（每层达标 = 1 分）：
  L1 年线方向  close / 上年末close - 1 > 0
  L2 季线方向  close / 上季末close - 1 > 0
  L3 KST       KST > 信号线（ROC 10/15/20/30, 平滑10, 信号9, 权重1/2/3/4, A级参数）
  L4 周线结构  周线 EMA20 > EMA50（最新周bar状态）
  L5 zone      现价在 500 日高低点分位 > 0.5
  L6 VCP       ATR20 近 20 日收缩（当前 ATR20 < 60 日 ATR20 均值）
  M1/M2        60min / 30min EMA20 > EMA50（70 只池）

输出：results/layer_score_calibration_YYYYMMDD.md
用法：python layer_score_calibration.py
依赖：D:\anaconda3\python.exe（pandas>=2.2 / numpy）
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

LOOKBACK = 250  # 每只取最近 250 交易日逐日打分
WINDOW_ATR = 20
WINDOW_VCP = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500


def kst_signal(close: pd.Series):
    """KST（P 系列，A 级参数：backtrader 源码实测）。返回 (kst, signal)。"""
    roc = lambda n: close.pct_change(n) * 100.0  # noqa: E731
    k = (roc(10).rolling(10).mean() * 1
         + roc(15).rolling(15).mean() * 2
         + roc(20).rolling(20).mean() * 3
         + roc(30).rolling(30).mean() * 4)
    kst = k.rolling(10).mean()
    sig = kst.rolling(9).mean()
    return kst, sig


def daily_prev_year_close(code: str):
    """daily_year 倒数第二根（上年，已闭合）的 close。失败返回 NaN。"""
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_year", f"{code}.csv"))
        if len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return float("nan")


def daily_prev_quarter_close(code: str):
    """daily_quarter 倒数第二根（上季，已闭合）的 close。"""
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_quarter", f"{code}.csv"))
        if len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return float("nan")


def week_ema_state(code: str):
    """周线 EMA20 vs EMA50 最新状态：True=多头排列。数据不足返回 None。"""
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_week", f"{code}.csv"))
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 50:
            return None
        e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
        e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
        return bool(e20 > e50)
    except Exception:
        return None


def minute_ema_state(code: str, period: str):
    """60/30min EMA20 vs EMA50 最新状态。数据不足返回 None。"""
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, period, f"{code}.csv"))
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 50:
            return None
        e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
        e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
        return bool(e20 > e50)
    except Exception:
        return None


def score_stock(code: str):
    """单股：返回 (n_days, df6) 其中 df6 为 6 层布尔 DataFrame（最近 LOOKBACK 日）。"""
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return 0, None
    df = pd.read_csv(f)
    if "close" not in df.columns or df.empty:
        return 0, None
    # 列名兼容（date 或 time）
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(LOOKBACK + 80)  # 多留 80 根给滚动指标预热
    if len(d) < 80:
        return 0, None
    c = d["close"]
    prev_yr = daily_prev_year_close(code)
    prev_q = daily_prev_quarter_close(code)
    wk = week_ema_state(code)
    # L1 年线方向
    l1 = (c / prev_yr - 1 > 0) if np.isfinite(prev_yr) else pd.Series(False, index=d.index)
    # L2 季线方向
    l2 = (c / prev_q - 1 > 0) if np.isfinite(prev_q) else pd.Series(False, index=d.index)
    # L3 KST
    kst, sig = kst_signal(c)
    l3 = (kst > sig).fillna(False)
    # L4 周线结构（阶段状态，最新周判定；数据不足按 False）
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    # L5 zone：500 日高低点分位
    hi = c.rolling(WINDOW_ZONE, min_periods=100).max()
    lo = c.rolling(WINDOW_ZONE, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    l5 = ((c - lo) / span > 0.5).fillna(False)
    # L6 VCP：ATR20 收缩（当前 ATR20 < 60 日 ATR20 均值）
    # 简化 ATR：用 close 变动近似（|Δclose| 的 WINDOW_ATR 均值）
    atr = c.diff().abs().rolling(WINDOW_ATR).mean()
    atr_mean = atr.rolling(WINDOW_ATR_MEAN).mean()
    l6 = (atr < atr_mean).fillna(False)
    out = pd.DataFrame({
        "L1年线": l1.astype(bool), "L2季线": l2.astype(bool),
        "L3KST": l3.astype(bool), "L4周线": l4.astype(bool),
        "L5zone": l5.astype(bool), "L6VCP": l6.astype(bool),
    }, index=d.index).tail(LOOKBACK)
    return len(out), out


def main():
    print("[P1b] 层数打分分布标定开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    total_score = []
    layer_hits = {"L1年线": 0, "L2季线": 0, "L3KST": 0, "L4周线": 0, "L5zone": 0, "L6VCP": 0}
    n_days_total = 0
    n_stocks = 0
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        n, df6 = score_stock(code)
        if n == 0 or df6 is None:
            continue
        n_stocks += 1
        n_days_total += n
        s = df6.sum(axis=1)
        total_score.append(s)
        for col in layer_hits:
            layer_hits[col] += int(df6[col].sum())
    if not total_score:
        print("无可用样本"); return
    scores = pd.concat(total_score)
    # 分钟池 2 层
    m60 = {"hit": 0, "ok": 0}
    m30 = {"hit": 0, "ok": 0}
    mfiles = sorted(glob.glob(os.path.join(MTF_ROOT, "min60", "*.csv")))
    for f in mfiles:
        code = os.path.basename(f).replace(".csv", "")
        s60 = minute_ema_state(code, "min60")
        s30 = minute_ema_state(code, "min30")
        if s60 is not None:
            m60["ok"] += 1; m60["hit"] += int(s60)
        if s30 is not None:
            m30["ok"] += 1; m30["hit"] += int(s30)

    stamp = datetime.now().strftime("%Y%m%d")
    L = []
    L.append("# 层数打分分布标定报告（P1b）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 样本：{n_stocks} 只日线池 × 最近 {LOOKBACK} 交易日 = {n_days_total:,} 个时点")
    L.append("- 口径：6/10 临时口径（方向 4 + 位置 2）；缠论/背驰/spring-VSA/regime 官方版待 P2 接入，P2 后 10/10 重标")
    L.append("")
    L.append("## 1. 各层达标率（533 只池）")
    L.append("")
    L.append("| 层 | 达标率 | 说明 |")
    L.append("|---|---|---|")
    for col in ["L1年线", "L2季线", "L3KST", "L4周线", "L5zone", "L6VCP"]:
        rate = layer_hits[col] / n_days_total
        L.append(f"| {col} | {rate:.1%} | - |")
    L.append("")
    L.append("## 2. 总分分布（0~6 分，全部时点）")
    L.append("")
    vc = scores.value_counts().sort_index()
    for v in range(7):
        L.append(f"- {v} 分：{vc.get(v, 0):,} 个时点（{vc.get(v, 0) / len(scores):.1%}）")
    L.append("")
    for q in [0.25, 0.50, 0.60, 0.70, 0.75, 0.90]:
        L.append(f"- P{int(q*100)}：{scores.quantile(q):.2f} 分")
    L.append("")
    L.append("## 3. 放行线标定建议（分位数推导，替代拍脑袋 6/10）")
    L.append("")
    # 候选线：P60 / P70 / P75
    p60 = scores.quantile(0.60); p70 = scores.quantile(0.70); p75 = scores.quantile(0.75)
    pass60 = (scores >= p60).mean(); pass70 = (scores >= p70).mean(); pass75 = (scores >= p75).mean()
    L.append(f"- 宽松档：≥{p60:.1f} 分（放行约 {pass60:.0%} 时点）")
    L.append(f"- 中性档：≥{p70:.1f} 分（放行约 {pass70:.0%} 时点）")
    L.append(f"- 严格档：≥{p75:.1f} 分（放行约 {pass75:.0%} 时点）")
    L.append(f"- **建议 v0（6/10 口径）**：≥{p70:.0f}/6（约 {pass70:.0%} 放行，兼顾高效性与安全性；P2 接入 10/10 后按同分位数重标）")
    L.append("")
    L.append("## 4. 分钟池（70 只）时机层-分钟趋势")
    L.append("")
    L.append(f"- 60min EMA20>EMA50：{m60['hit']}/{m60['ok']}（{m60['hit']/m60['ok'] if m60['ok'] else 0:.0%}）")
    L.append(f"- 30min EMA20>EMA50：{m30['hit']}/{m30['ok']}（{m30['hit']/m30['ok'] if m30['ok'] else 0:.0%}）")
    L.append("- spring/背驰/VSA 三维待 P2（本轮不计分）")
    L.append("")
    L.append("## 5. 口径边界与修改空间")
    L.append("")
    L.append("- 本轮 L4 周线结构、L1/L2 为阶段状态（周/季/年级别），L3/L5/L6 逐日；混合口径已在实验台账记录")
    L.append("- 缠论校验、背驰、spring/VSA、regime 官方版 = 待 P2 接入层；接入后 10/10 口径重标放行线")
    L.append("- LOOKBACK/ATR/VCP/zone 窗口参数可在脚本顶部调整后重跑")
    L.append("")
    os.makedirs(RESULT_DIR, exist_ok=True)
    out_path = os.path.join(RESULT_DIR, f"layer_score_calibration_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
